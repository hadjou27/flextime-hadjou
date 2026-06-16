from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AvailabilitySlotForm
from .models import AvailabilitySlot, CalendarAccess

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

    return render(request, 'core/shared_calendar.html', {
        'creator': creator,
        'is_owner': is_owner,
        'access': access,
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
