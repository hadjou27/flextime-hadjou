from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.my_calendar, name='my_calendar'),
]
