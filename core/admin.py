from django.contrib import admin

from .models import CalendarAccess


@admin.register(CalendarAccess)
class CalendarAccessAdmin(admin.ModelAdmin):
    list_display = (
        'visitor', 'creator', 'blocked_by_creator', 'archived_by_visitor',
        'first_accessed_at',
    )
    list_filter = ('blocked_by_creator', 'archived_by_visitor')
    search_fields = (
        'creator__email', 'creator__first_name', 'creator__last_name',
        'visitor__email', 'visitor__first_name', 'visitor__last_name',
    )
    readonly_fields = ('first_accessed_at', 'blocked_at', 'archived_at')
