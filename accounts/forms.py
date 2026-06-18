from django import forms
from django.contrib.auth import get_user_model

from .validators import validate_not_disposable_email

User = get_user_model()


class SignInForm(forms.Form):
    """Returning user: email only. No password, no name — the spec's
    "request a fresh sign-in link by email" flow."""

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autofocus': True}),
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        # Look up case-insensitively so a returning user is always recognised.
        self.user = User.objects.filter(email__iexact=email).first()
        if self.user is None:
            raise forms.ValidationError(
                "We couldn't find an account for that email — sign up first."
            )
        return email

    def get_user(self):
        return self.user


class SignUpForm(forms.Form):
    """New user: first name, last name, and email — the spec's "identifies
    themselves once" flow. Creating the account happens in the view."""

    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'First name', 'autofocus': True}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'}),
    )
    email = forms.EmailField(
        validators=[validate_not_disposable_email],
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account already exists for that email — sign in instead."
            )
        return email

    def create_user(self):
        return User.objects.create_user(
            email=self.cleaned_data['email'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
        )
