from django import forms

from .models import AvailabilitySlot

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
        for field in self.fields.values():
            field.input_formats = [_DATETIME_LOCAL]
