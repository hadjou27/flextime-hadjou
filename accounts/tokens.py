"""Magic-link tokens.

A sign-in link carries a signed, time-stamped token instead of a database
row. `django.core.signing` handles the signing and the expiry check, so there
is no token table to store or clean up.
"""

from django.conf import settings
from django.core import signing

SALT = 'magic-link'


def make_login_token(user) -> str:
    """Return a signed token that identifies the user."""
    return signing.dumps({'uid': user.pk}, salt=SALT)


def read_login_token(token: str, max_age: int | None = None) -> int:
    """Return the user id inside a valid token.

    Raises ``signing.SignatureExpired`` if the link is too old and
    ``signing.BadSignature`` if it was tampered with or is malformed.
    """
    if max_age is None:
        max_age = settings.MAGIC_LINK_MAX_AGE
    data = signing.loads(token, salt=SALT, max_age=max_age)
    return data['uid']
