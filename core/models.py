from django.conf import settings
from django.db import models
from django.utils import timezone


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
