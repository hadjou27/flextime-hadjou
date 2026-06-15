from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class SignInForm(forms.Form):
    """Single form for both sign-in flows.

    Email is always required. First/last name are only needed when the email is
    new (i.e. the user is signing up for the first time).
    """

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autofocus': True}),
    )
    first_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'First name'}),
    )
    last_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'}),
    )

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get('email')
        if not email:
            return cleaned

        # Look up case-insensitively so a returning user is always recognised.
        self.user = User.objects.filter(email__iexact=email).first()

        if self.user is None and (not cleaned.get('first_name') or not cleaned.get('last_name')):
            raise forms.ValidationError(
                "Looks like you're new here — please add your first and last name."
            )
        return cleaned

    def get_or_create_user(self):
        """Return the existing user, or create one from the submitted details."""
        if self.user:
            return self.user
        return User.objects.create_user(
            email=self.cleaned_data['email'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
        )
