from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def my_calendar(request):
    """The owner's home page.

    Placeholder for now — it will host the user's availability slots and
    activities. It already shows the user's shareable calendar link.
    """
    return render(request, 'core/my_calendar.html')
