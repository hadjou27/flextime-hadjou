from django import forms
from django.utils import timezone

from .models import ActivitySuggestion, AvailabilitySlot

# HTML5 datetime-local fields exchange values in this format.
_DATETIME_LOCAL = '%Y-%m-%dT%H:%M'


class AvailabilitySlotForm(forms.ModelForm):
    class Meta:
        model = AvailabilitySlot
        fields = ['start', 'end']
        widgets = {
            'start': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=_DATETIME_LOCAL),
            'end': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=_DATETIME_LOCAL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The date picker itself blocks past dates (the server still validates).
        now = timezone.localtime().strftime(_DATETIME_LOCAL)
        for field in self.fields.values():
            field.input_formats = [_DATETIME_LOCAL]
            field.widget.attrs['min'] = now


class ActivitySuggestionForm(forms.ModelForm):
    # NOTE: max_participants exists on the model but is intentionally left out of
    # this form for now — the capacity feature is deferred (see SOLUTION.md).
    class Meta:
        model = ActivitySuggestion
        fields = ['category', 'title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Friendly tennis match'}),
            'description': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Optional — any details for your friends.',
            }),
        }
