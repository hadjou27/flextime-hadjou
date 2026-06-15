import secrets

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .managers import UserManager


def generate_share_token() -> str:
    """Return a sufficiently random, URL-safe token for the calendar link."""
    return secrets.token_urlsafe(12)


class User(AbstractBaseUser, PermissionsMixin):
    """A FlexTime user.

    There is only one type of user. Authentication is passwordless (magic
    link), so the email address is the unique identifier and no usable
    password is stored for regular users.

    Each user has exactly one calendar. Rather than a separate Calendar model,
    the shareable link lives directly on the user as a token + slug (see
    SOLUTION.md for the trade-off). The public URL is `<first>-<last>-<token>`;
    the random token makes it effectively unlisted (impossible to guess).
    """

    email = models.EmailField('email address', unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)

    share_token = models.CharField(max_length=32, unique=True, default=generate_share_token)
    share_slug = models.SlugField(max_length=255, unique=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}>'

    def save(self, *args, **kwargs):
        if not self.share_token:
            self.share_token = generate_share_token()
        # The slug embeds the owner's name for readability, but its uniqueness
        # and unguessability come from the random token.
        name_part = slugify(f'{self.first_name}-{self.last_name}')
        self.share_slug = f'{name_part}-{self.share_token}'
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.first_name
