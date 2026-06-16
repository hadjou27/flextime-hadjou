from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.my_calendar, name='my_calendar'),
    path('calendar/<slug:share_slug>/', views.shared_calendar, name='shared_calendar'),
    path('calendar/<slug:share_slug>/archive/', views.archive_calendar, name='archive_calendar'),
    path('calendar/<slug:share_slug>/unarchive/', views.unarchive_calendar, name='unarchive_calendar'),
    path('visitors/<int:visitor_id>/block/', views.block_visitor, name='block_visitor'),
    path('visitors/<int:visitor_id>/unblock/', views.unblock_visitor, name='unblock_visitor'),
]
