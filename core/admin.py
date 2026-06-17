from django.contrib import admin

from .models import ActivitySuggestion, AvailabilitySlot, CalendarAccess, Interest


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


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ('owner', 'start', 'end', 'status')
    list_filter = ('status',)
    search_fields = ('owner__email', 'owner__first_name', 'owner__last_name')
    date_hierarchy = 'start'


@admin.register(ActivitySuggestion)
class ActivitySuggestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'slot', 'status', 'max_participants')
    list_filter = ('status', 'category')
    search_fields = ('title', 'description')


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'activity__title')
    readonly_fields = ('created_at',)
