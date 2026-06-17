from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

# Calendar views show only the last 7 days plus all future dates.
VISIBLE_WINDOW = timedelta(days=7)


class Status(models.TextChoices):
    """Four-state vocabulary shared by slots and activities."""
    OPEN = 'open', 'Open'
    CONFIRMED = 'confirmed', 'Confirmed'
    CLOSED = 'closed', 'Closed'
    CANCELLED = 'cancelled', 'Cancelled'


class Category(models.TextChoices):
    """Predefined list of activity categories (per the brief)."""
    TENNIS = 'tennis', 'Tennis'
    RUNNING = 'running', 'Running'
    HIKING = 'hiking', 'Hiking'
    CYCLING = 'cycling', 'Cycling'
    SWIMMING = 'swimming', 'Swimming'
    FOOTBALL = 'football', 'Football'
    BASKETBALL = 'basketball', 'Basketball'
    YOGA = 'yoga', 'Yoga'
    FITNESS = 'fitness', 'Fitness'
    BOARD_GAMES = 'board_games', 'Board Games'
    VIDEO_GAMES = 'video_games', 'Video Games'
    CINEMA = 'cinema', 'Cinema'
    MUSEUM = 'museum', 'Museum'
    RESTAURANT = 'restaurant', 'Restaurant'
    COFFEE = 'coffee', 'Coffee'
    DRINKS = 'drinks', 'Drinks'
    LANGUAGE_EXCHANGE = 'language_exchange', 'Language Exchange'
    NETWORKING = 'networking', 'Networking'
    VOLUNTEERING = 'volunteering', 'Volunteering'
    OTHER = 'other', 'Other'


class CalendarAccess(models.Model):
    """Links a visitor to a creator's calendar.

    A record is created automatically the first time a signed-in visitor opens
    a creator's shared link. The two flags are independent: a visitor can
    archive a calendar the creator has not blocked, and a creator can block a
    visitor who has not archived. Nothing is ever deleted — blocking and
    archiving are reversible state changes, each with its own timestamp.
    """

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='visitor_accesses',   # visitors who can see my calendar
    )
    visitor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calendar_accesses',   # calendars I can see
    )

    blocked_by_creator = models.BooleanField(default=False)
    archived_by_visitor = models.BooleanField(default=False)

    first_accessed_at = models.DateTimeField(auto_now_add=True)
    blocked_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'calendar accesses'
        constraints = [
            # One relationship per (creator, visitor) pair.
            models.UniqueConstraint(
                fields=['creator', 'visitor'],
                name='unique_visitor_per_creator',
            ),
            # A user can never have an access record to their own calendar.
            models.CheckConstraint(
                condition=~models.Q(creator=models.F('visitor')),
                name='no_self_access',
            ),
        ]

    def __str__(self):
        return f'{self.visitor.get_full_name()} → {self.creator.get_full_name()}'

    def set_blocked(self, blocked: bool):
        """Block or unblock this visitor (creator action)."""
        self.blocked_by_creator = blocked
        self.blocked_at = timezone.now() if blocked else None
        self.save(update_fields=['blocked_by_creator', 'blocked_at'])

    def set_archived(self, archived: bool):
        """Archive or unarchive this calendar (visitor action)."""
        self.archived_by_visitor = archived
        self.archived_at = timezone.now() if archived else None
        self.save(update_fields=['archived_by_visitor', 'archived_at'])


class SlotQuerySet(models.QuerySet):
    def recent_and_upcoming(self):
        """Only the last 7 days plus all future slots (per the brief)."""
        return self.filter(start__gte=timezone.now() - VISIBLE_WINDOW)


class AvailabilitySlot(models.Model):
    """A period of time during which the owner is available.

    A slot is only a container of time plus a status — it carries no category,
    title, description, or interest of its own. Those belong to its activity
    suggestions. A slot holds one or more activities.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='slots',
    )
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN,
    )
    # Used to decide which slots a blocked visitor may still see: a blocked
    # user keeps access to slots created before they were blocked.
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = SlotQuerySet.as_manager()

    class Meta:
        ordering = ['start']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F('start')),
                name='slot_end_after_start',
            ),
        ]

    def __str__(self):
        return f'{self.owner.get_short_name()}: {self.start:%Y-%m-%d %H:%M}–{self.end:%H:%M}'

    def clean(self):
        if self.start and self.start < timezone.now():
            raise ValidationError({'start': 'A slot must start in the future.'})
        if self.start and self.end:
            if self.end <= self.start:
                raise ValidationError({'end': 'End time must be after the start time.'})
            max_duration = timedelta(hours=settings.SLOT_MAX_DURATION_HOURS)
            if self.end - self.start >= max_duration:
                raise ValidationError({
                    'end': f'A slot must be shorter than {settings.SLOT_MAX_DURATION_HOURS} hours.',
                })

    @transaction.atomic
    def cancel(self):
        """Cancel the slot and, as a side effect, all of its activities.

        Both writes happen in one transaction, so the slot and its activities
        can never end up in inconsistent states.
        """
        self.status = Status.CANCELLED
        self.save(update_fields=['status'])
        self.activities.update(status=Status.CANCELLED)


class ActivitySuggestion(models.Model):
    """A possible activity during a slot.

    Holds all the semantic content (category, title, description) and is the
    thing users express interest in. A slot may hold several of these, but only
    one may be Confirmed at a time.
    """

    slot = models.ForeignKey(
        AvailabilitySlot,
        on_delete=models.CASCADE,
        related_name='activities',
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN,
    )
    # Optional cap on interested participants. Blank/None means no limit.
    max_participants = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            # Only one activity per slot may be Confirmed at a time.
            models.UniqueConstraint(
                fields=['slot'],
                condition=models.Q(status='confirmed'),
                name='one_confirmed_activity_per_slot',
            ),
            # Capacity, if set, must be at least 1 (0 would make no sense).
            models.CheckConstraint(
                condition=models.Q(max_participants__isnull=True) | models.Q(max_participants__gte=1),
                name='activity_capacity_at_least_one',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.get_status_display()})'

    @transaction.atomic
    def confirm(self):
        """Confirm this activity for its slot.

        Side effects (per the brief): the parent slot becomes Confirmed, and
        every other activity in the slot becomes Cancelled.

        We lock the parent slot row for the duration of the transaction
        (``select_for_update``) so two people can't confirm two different
        activities of the same slot at the same time — the second one waits for
        the first to commit, keeping "only one confirmed per slot" true even
        under concurrency.
        """
        slot = AvailabilitySlot.objects.select_for_update().get(pk=self.slot_id)
        if slot.status in (Status.CANCELLED, Status.CLOSED):
            raise ValidationError('Cannot confirm an activity on a closed or cancelled slot.')

        # Cancel the competitors first, so we never momentarily have two
        # confirmed activities (which the unique constraint would reject).
        slot.activities.exclude(pk=self.pk).update(status=Status.CANCELLED)

        self.status = Status.CONFIRMED
        self.save(update_fields=['status'])

        slot.status = Status.CONFIRMED
        slot.save(update_fields=['status'])
        self.slot = slot

    @transaction.atomic
    def close(self):
        """Close the confirmed activity; the parent slot becomes Closed.

        The owner can never close a slot directly — a slot only becomes Closed
        as a side effect of its confirmed activity being closed.
        """
        if self.status != Status.CONFIRMED:
            raise ValidationError('Only the confirmed activity can be closed.')

        slot = AvailabilitySlot.objects.select_for_update().get(pk=self.slot_id)
        self.status = Status.CLOSED
        self.save(update_fields=['status'])

        slot.status = Status.CLOSED
        slot.save(update_fields=['status'])
        self.slot = slot

    @transaction.atomic
    def reopen(self):
        """Reopen a closed activity so people can join again.

        The exact inverse of close(): the activity goes Closed → Confirmed and
        its slot goes Closed → Confirmed. The brief implies this: a closed
        activity's access can be restored "unless the owner reopens it".
        """
        if self.status != Status.CLOSED:
            raise ValidationError('Only a closed activity can be reopened.')

        slot = AvailabilitySlot.objects.select_for_update().get(pk=self.slot_id)
        self.status = Status.CONFIRMED
        self.save(update_fields=['status'])

        slot.status = Status.CONFIRMED
        slot.save(update_fields=['status'])
        self.slot = slot

    def cancel(self):
        """Cancel this single activity, without touching its siblings.

        Cancelling the *confirmed* activity is refused: that would leave the
        slot Confirmed with no confirmed activity. Since 'Cancelled' is a
        terminal state in the brief, undoing a confirmation must go through
        cancelling the whole slot instead.
        """
        if self.status == Status.CONFIRMED:
            raise ValidationError(
                'Cannot cancel the confirmed activity directly — cancel the slot instead.'
            )
        self.status = Status.CANCELLED
        self.save(update_fields=['status'])


class Interest(models.Model):
    """A single user's "I'm in" for a single activity.

    Interest is a simple boolean modelled by the row's existence: a row means
    interested, no row means not interested. A user may be interested in many
    activities, but only once per activity (the unique constraint). Expressing
    interest in one's own activities is prevented in the view, not here.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='interests',
    )
    activity = models.ForeignKey(
        ActivitySuggestion,
        on_delete=models.CASCADE,
        related_name='interests',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'activity'],
                name='one_interest_per_user_per_activity',
            ),
        ]

    def __str__(self):
        return f'{self.user.get_short_name()} → {self.activity.title}'
