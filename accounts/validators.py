"""Email validators used at sign-up.

The format of an email is already checked by Django's EmailField. This adds a
rule on top: reject throwaway / disposable inboxes, so an account is tied to a
real, lasting address (it's also where every magic link is sent).
"""

from django.core.exceptions import ValidationError

# A small, representative denylist. A production app would swap this for a
# maintained list (e.g. the `disposable-email-domains` package) rather than
# hand-curating it here.
DISPOSABLE_EMAIL_DOMAINS = frozenset({
    'mailinator.com',
    'yopmail.com',
    'guerrillamail.com',
    '10minutemail.com',
    'tempmail.com',
    'temp-mail.org',
    'trashmail.com',
    'throwawaymail.com',
    'getnada.com',
    'sharklasers.com',
    'maildrop.cc',
    'dispostable.com',
    'mailnesia.com',
    'fakeinbox.com',
})


def validate_not_disposable_email(value):
    """Reject emails whose domain is a known disposable provider.

    Case-insensitive on the domain. Anything without a domain is left to the
    format validator (EmailField) to reject.
    """
    domain = value.rsplit('@', 1)[-1].lower()
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        raise ValidationError(
            'Please use a permanent email address — disposable addresses are not allowed.',
            code='disposable_email',
        )
