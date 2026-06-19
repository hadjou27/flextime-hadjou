from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.my_calendar, name='my_calendar'),
    path('agenda/', views.consolidated_calendar, name='consolidated'),
    path('dashboard/', views.creator_dashboard, name='dashboard'),
    path('slots/new/', views.slot_create, name='slot_create'),
    path('slots/<int:slot_id>/', views.slot_detail, name='slot_detail'),
    path('slots/<int:slot_id>/edit/', views.slot_edit, name='slot_edit'),
    path('slots/<int:slot_id>/cancel/', views.slot_cancel, name='slot_cancel'),
    path('slots/<int:slot_id>/activities/new/', views.activity_create, name='activity_create'),
    path('activities/<int:activity_id>/edit/', views.activity_edit, name='activity_edit'),
    path('activities/<int:activity_id>/confirm/', views.activity_confirm, name='activity_confirm'),
    path('activities/<int:activity_id>/close/', views.activity_close, name='activity_close'),
    path('activities/<int:activity_id>/reopen/', views.activity_reopen, name='activity_reopen'),
    path('activities/<int:activity_id>/cancel/', views.activity_cancel, name='activity_cancel'),
    path('activities/<int:activity_id>/interested/', views.interest_add, name='interest_add'),
    path('activities/<int:activity_id>/not-interested/', views.interest_remove, name='interest_remove'),
    path('calendar/<slug:share_slug>/', views.shared_calendar, name='shared_calendar'),
    path('calendar/<slug:share_slug>/archive/', views.archive_calendar, name='archive_calendar'),
    path('calendar/<slug:share_slug>/unarchive/', views.unarchive_calendar, name='unarchive_calendar'),
    path('visitors/<int:visitor_id>/block/', views.block_visitor, name='block_visitor'),
    path('visitors/<int:visitor_id>/unblock/', views.unblock_visitor, name='unblock_visitor'),
]
