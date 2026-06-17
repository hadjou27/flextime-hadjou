import calendar
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ActivitySuggestionForm, AvailabilitySlotForm
from .models import (
    ActivitySuggestion, AvailabilitySlot, CalendarAccess, Interest, Status,
)

User = get_user_model()


@login_required
def my_calendar(request):
    """The owner's home page.

    Shows the user's own availability slots, their shareable link, the calendars
    they can access (their "Other Calendars", split into active and archived),
    and the visitors who can see their own calendar.
    """
    my_accesses = CalendarAccess.objects.filter(visitor=request.user).select_related('creator')
    visitors = CalendarAccess.objects.filter(creator=request.user).select_related('visitor')
    return render(request, 'core/my_calendar.html', {
        'slots': request.user.slots.recent_and_upcoming(),
        'accessible': [a for a in my_accesses if not a.archived_by_visitor],
        'archived': [a for a in my_accesses if a.archived_by_visitor],
        'visitors': visitors,
    })


@login_required
def slot_create(request):
    """Add a new availability slot to the current user's calendar."""
    if request.method == 'POST':
        form = AvailabilitySlotForm(request.POST)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.owner = request.user
            slot.save()
            messages.success(request, 'Availability slot added.')
            return redirect('core:my_calendar')
    else:
        form = AvailabilitySlotForm()
    return render(request, 'core/slot_form.html', {'form': form})


@login_required
@require_POST
def slot_cancel(request, slot_id):
    """Cancel one of the current user's slots."""
    slot = get_object_or_404(AvailabilitySlot, id=slot_id, owner=request.user)
    slot.cancel()
    messages.info(request, 'Slot cancelled.')
    return redirect('core:my_calendar')


@login_required
def shared_calendar(request, share_slug):
    """Open a calendar from its shareable link.

    Visiting a creator's link automatically grants access (no approval) by
    creating a CalendarAccess record. Opening your own link just shows your
    calendar without creating any access record.
    """
    creator = get_object_or_404(User, share_slug=share_slug, is_active=True)
    is_owner = creator == request.user

    access = None
    if not is_owner:
        access, _ = CalendarAccess.objects.get_or_create(
            creator=creator, visitor=request.user,
        )

    slots = creator.slots.recent_and_upcoming().prefetch_related('activities')

    # Blocking: a blocked visitor no longer sees slots created after the block,
    # but keeps the historical slots they could already see.
    if access and access.blocked_by_creator and access.blocked_at:
        slots = slots.filter(created_at__lte=access.blocked_at)

    # The viewer's own interests across this calendar (one query).
    interested_ids = set()
    if not is_owner:
        interested_ids = set(
            Interest.objects
            .filter(user=request.user, activity__slot__owner=creator)
            .values_list('activity_id', flat=True)
        )

    slot_rows = []
    for slot in slots:
        visible = []
        for activity in slot.activities.all():
            # Cancelled activities are hidden from everyone here.
            if activity.status == Status.CANCELLED:
                continue
            # A closed activity is visible only to those already interested.
            if (not is_owner and activity.status == Status.CLOSED
                    and activity.id not in interested_ids):
                continue
            activity.viewer_interested = activity.id in interested_ids
            visible.append(activity)
        slot_rows.append({'slot': slot, 'activities': visible})

    return render(request, 'core/shared_calendar.html', {
        'creator': creator,
        'is_owner': is_owner,
        'access': access,
        'slot_rows': slot_rows,
    })


# --- Visitor actions: archive / unarchive a calendar -----------------------

@login_required
@require_POST
def archive_calendar(request, share_slug):
    access = get_object_or_404(
        CalendarAccess, creator__share_slug=share_slug, visitor=request.user,
    )
    access.set_archived(True)
    messages.info(request, f"Archived {access.creator.get_full_name()}'s calendar.")
    return redirect('core:my_calendar')


@login_required
@require_POST
def unarchive_calendar(request, share_slug):
    access = get_object_or_404(
        CalendarAccess, creator__share_slug=share_slug, visitor=request.user,
    )
    access.set_archived(False)
    messages.info(request, f"Restored {access.creator.get_full_name()}'s calendar.")
    return redirect('core:my_calendar')


# --- Owner actions: block / unblock a visitor ------------------------------

@login_required
@require_POST
def block_visitor(request, visitor_id):
    access = get_object_or_404(
        CalendarAccess, creator=request.user, visitor_id=visitor_id,
    )
    access.set_blocked(True)
    messages.info(request, f"Blocked {access.visitor.get_full_name()}.")
    return redirect('core:my_calendar')


@login_required
@require_POST
def unblock_visitor(request, visitor_id):
    access = get_object_or_404(
        CalendarAccess, creator=request.user, visitor_id=visitor_id,
    )
    access.set_blocked(False)
    messages.info(request, f"Unblocked {access.visitor.get_full_name()}.")
    return redirect('core:my_calendar')


# --- Activities: the owner manages activities inside their own slot ---------

@login_required
def slot_detail(request, slot_id):
    """The owner's management view for one of their slots and its activities."""
    slot = get_object_or_404(AvailabilitySlot, id=slot_id, owner=request.user)
    return render(request, 'core/slot_detail.html', {
        'slot': slot,
        'activities': slot.activities.all(),
    })


@login_required
def creator_dashboard(request):
    """Drill-down for the owner: slot -> activity -> interested users.

    Only first and last names are shown — never email addresses.
    """
    slots = (
        request.user.slots.recent_and_upcoming()
        .prefetch_related('activities__interests__user')
    )
    return render(request, 'core/dashboard.html', {'slots': slots})


def _accessible_slot_rows(user):
    """The user's own slots plus the visible slots from every calendar they can
    access (archived calendars excluded, blocking respected)."""
    rows = [
        {'slot': slot, 'owner': user, 'is_own': True}
        for slot in user.slots.recent_and_upcoming()
    ]
    accesses = (
        CalendarAccess.objects
        .filter(visitor=user, archived_by_visitor=False)
        .select_related('creator')
    )
    for access in accesses:
        slots = access.creator.slots.recent_and_upcoming()
        if access.blocked_by_creator and access.blocked_at:
            slots = slots.filter(created_at__lte=access.blocked_at)
        rows += [
            {'slot': slot, 'owner': access.creator, 'is_own': False}
            for slot in slots
        ]
    rows.sort(key=lambda row: row['slot'].start)
    return rows


@login_required
def consolidated_calendar(request):
    """A month grid combining the user's own slots with the visible slots from
    every calendar they can access. Each day cell lists its slots; details live
    behind each one."""
    rows = _accessible_slot_rows(request.user)

    # Group the slots by the calendar day they start on.
    by_day = defaultdict(list)
    for row in rows:
        day = timezone.localtime(row['slot'].start).date()
        by_day[day].append(row)

    # Which month to show (defaults to the current one; navigable via ?y=&m=).
    today = timezone.localdate()
    try:
        year = int(request.GET.get('y', today.year))
        month = int(request.GET.get('m', today.month))
        first = date(year, month, 1)
    except (ValueError, TypeError):
        first, year, month = today.replace(day=1), today.year, today.month

    # Build the weeks (each a list of day cells) for that month.
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        weeks.append([
            {
                'date': day,
                'in_month': day.month == month,
                'is_today': day == today,
                'rows': by_day.get(day, []),
            }
            for day in week
        ])

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)

    return render(request, 'core/consolidated.html', {
        'rows': rows,  # kept for chronological access / tests
        'weeks': weeks,
        'month_label': first.strftime('%B %Y'),
        'weekday_names': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        'prev': prev_month,
        'next': next_month,
    })


@login_required
def activity_create(request, slot_id):
    """Propose a new activity inside one of the owner's slots.

    Only allowed while the slot is still Open: once an activity is confirmed
    (or the slot is closed/cancelled), the choice is made and no new activity
    can be proposed.
    """
    slot = get_object_or_404(AvailabilitySlot, id=slot_id, owner=request.user)
    if slot.status != Status.OPEN:
        messages.error(request, 'You can only add activities while the slot is open.')
        return redirect('core:slot_detail', slot_id=slot.id)
    if request.method == 'POST':
        form = ActivitySuggestionForm(request.POST)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.slot = slot
            activity.save()
            messages.success(request, f'Added "{activity.title}".')
            return redirect('core:slot_detail', slot_id=slot.id)
    else:
        form = ActivitySuggestionForm()
    return render(request, 'core/activity_form.html', {'form': form, 'slot': slot})


def _owner_activity(request, activity_id):
    """Fetch an activity that belongs to one of the current user's slots."""
    return get_object_or_404(
        ActivitySuggestion, id=activity_id, slot__owner=request.user,
    )


def _run_transition(request, activity, action, label):
    """Run a state-machine method, turning ValidationError into a flash message."""
    try:
        action()
        messages.success(request, f'"{activity.title}" {label}.')
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return redirect('core:slot_detail', slot_id=activity.slot_id)


@login_required
@require_POST
def activity_confirm(request, activity_id):
    activity = _owner_activity(request, activity_id)
    return _run_transition(request, activity, activity.confirm, 'confirmed')


@login_required
@require_POST
def activity_close(request, activity_id):
    activity = _owner_activity(request, activity_id)
    return _run_transition(request, activity, activity.close, 'closed')


@login_required
@require_POST
def activity_reopen(request, activity_id):
    activity = _owner_activity(request, activity_id)
    return _run_transition(request, activity, activity.reopen, 'reopened')


@login_required
@require_POST
def activity_cancel(request, activity_id):
    activity = _owner_activity(request, activity_id)
    return _run_transition(request, activity, activity.cancel, 'cancelled')


# --- Interest: a visitor expresses or removes interest in others' activities --

@login_required
@require_POST
def interest_add(request, activity_id):
    """Express interest in someone else's activity.

    Allowed only on activities the visitor can join — i.e. another user's
    Open or Confirmed activity, on a calendar they have access to. Closed and
    cancelled activities can't be newly joined.
    """
    activity = get_object_or_404(
        ActivitySuggestion.objects.select_related('slot__owner'),
        id=activity_id,
    )
    creator = activity.slot.owner

    if creator == request.user:
        messages.error(request, "You can't express interest in your own activity.")
        return redirect('core:slot_detail', slot_id=activity.slot_id)

    has_access = CalendarAccess.objects.filter(
        creator=creator, visitor=request.user,
    ).exists()
    if not has_access:
        messages.error(request, 'You need access to this calendar first.')
        return redirect('core:my_calendar')

    if activity.status not in (Status.OPEN, Status.CONFIRMED):
        messages.error(request, 'This activity can no longer be joined.')
    else:
        Interest.objects.get_or_create(user=request.user, activity=activity)
        messages.success(request, f'You\'re in for "{activity.title}".')

    return redirect('core:shared_calendar', share_slug=creator.share_slug)


@login_required
@require_POST
def interest_remove(request, activity_id):
    """Remove the visitor's interest in an activity.

    Always allowed (even for a closed activity — that's the documented
    "leave a closed activity" path, gated by a confirmation in the UI).
    """
    activity = get_object_or_404(
        ActivitySuggestion.objects.select_related('slot__owner'),
        id=activity_id,
    )
    Interest.objects.filter(user=request.user, activity=activity).delete()
    messages.info(request, f'You left "{activity.title}".')
    return redirect('core:shared_calendar', share_slug=activity.slot.owner.share_slug)
