import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .tokens import make_login_token, read_login_token

User = get_user_model()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MagicLinkFlowTests(TestCase):
    def _extract_link(self, body):
        match = re.search(r'http://testserver(\S+)', body)
        self.assertIsNotNone(match, 'No magic link found in the email body.')
        return match.group(1)

    def test_new_user_signs_up_and_signs_in(self):
        resp = self.client.post(reverse('accounts:sign_up'), {
            'email': 'New@Example.com',
            'first_name': 'New',
            'last_name': 'Person',
        })
        self.assertRedirects(resp, reverse('accounts:link_sent'))

        # The user was created, with a normalized email and a share slug.
        user = User.objects.get(email='New@example.com')
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.share_slug.startswith('new-person-'))

        # One email went out; follow its link to finish signing in.
        self.assertEqual(len(mail.outbox), 1)
        link = self._extract_link(mail.outbox[0].body)
        resp = self.client.get(link)
        self.assertRedirects(resp, reverse('core:my_calendar'))
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))

    def test_sign_up_without_name_is_rejected(self):
        resp = self.client.post(reverse('accounts:sign_up'), {'email': 'noname@example.com'})
        self.assertEqual(resp.status_code, 200)  # re-rendered form with errors
        self.assertFalse(User.objects.filter(email='noname@example.com').exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_sign_in_with_unknown_email_is_rejected(self):
        # The sign-in page is email-only; an unknown email is sent to sign up.
        resp = self.client.post(reverse('accounts:sign_in'), {'email': 'stranger@example.com'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'find an account')
        self.assertEqual(len(mail.outbox), 0)

    def test_sign_up_with_existing_email_is_rejected(self):
        User.objects.create_user(email='back@example.com', first_name='Back', last_name='Again')
        resp = self.client.post(reverse('accounts:sign_up'), {
            'email': 'back@example.com', 'first_name': 'Dup', 'last_name': 'Licate',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'already exists')
        self.assertEqual(User.objects.filter(email__iexact='back@example.com').count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_returning_user_needs_only_email(self):
        User.objects.create_user(email='back@example.com', first_name='Back', last_name='Again')
        resp = self.client.post(reverse('accounts:sign_in'), {'email': 'back@example.com'})
        self.assertRedirects(resp, reverse('accounts:link_sent'))
        self.assertEqual(len(mail.outbox), 1)

    def test_sign_up_rejects_a_disposable_email(self):
        resp = self.client.post(reverse('accounts:sign_up'), {
            'email': 'throwaway@mailinator.com', 'first_name': 'Temp', 'last_name': 'User',
        })
        self.assertEqual(resp.status_code, 200)  # re-rendered with the error
        self.assertContains(resp, 'permanent email')
        self.assertFalse(User.objects.filter(email='throwaway@mailinator.com').exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_tampered_token_is_rejected(self):
        user = User.objects.create_user(email='x@example.com', first_name='X', last_name='Y')
        token = make_login_token(user) + 'tampered'
        resp = self.client.get(reverse('accounts:verify', args=[token]))
        self.assertRedirects(resp, reverse('accounts:sign_in'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_expired_token_is_rejected(self):
        user = User.objects.create_user(email='old@example.com', first_name='Old', last_name='Link')
        token = make_login_token(user)
        with self.assertRaises(Exception):
            read_login_token(token, max_age=-1)

    def test_my_calendar_requires_login(self):
        resp = self.client.get(reverse('core:my_calendar'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:sign_in'), resp.url)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    MAGIC_LINK_RATE_LIMIT=2,
    MAGIC_LINK_RATE_WINDOW=600,
)
class MagicLinkRateLimitTests(TestCase):
    """Requesting magic links is capped per email and per IP, so the sign-in form
    can't be used for email bombing or bulk account creation."""

    def setUp(self):
        # The counter lives in the cache, which is shared across tests in the
        # same process — start each test from a clean slate.
        cache.clear()

    def test_too_many_requests_are_blocked(self):
        # A returning user asking for links over and over (email-only sign-in).
        User.objects.create_user(email='spammed@example.com', first_name='S', last_name='P')
        for _ in range(2):  # the first RATE_LIMIT requests go through...
            resp = self.client.post(reverse('accounts:sign_in'), {'email': 'spammed@example.com'})
            self.assertRedirects(resp, reverse('accounts:link_sent'))
        # ...the next one is refused, and no extra email goes out.
        resp = self.client.post(reverse('accounts:sign_in'), {'email': 'spammed@example.com'})
        self.assertRedirects(resp, reverse('accounts:sign_in'))
        self.assertEqual(len(mail.outbox), 2)

    def test_ip_limit_blocks_even_when_email_varies(self):
        # An attacker on one machine cycling through fresh sign-ups (same IP).
        for i in range(2):
            resp = self.client.post(reverse('accounts:sign_up'), {
                'email': f'user{i}@example.com', 'first_name': 'U', 'last_name': str(i),
            })
            self.assertRedirects(resp, reverse('accounts:link_sent'))
        # A brand-new email, but the IP counter has had enough — blocked, and
        # the blocked request creates no account.
        resp = self.client.post(reverse('accounts:sign_up'), {
            'email': 'fresh@example.com', 'first_name': 'F', 'last_name': 'R',
        })
        self.assertRedirects(resp, reverse('accounts:sign_up'))
        self.assertEqual(len(mail.outbox), 2)
        self.assertFalse(User.objects.filter(email='fresh@example.com').exists())

    def test_email_limit_blocks_even_across_different_ips(self):
        # One victim's address targeted from several machines (varying IP).
        User.objects.create_user(email='victim@example.com', first_name='V', last_name='M')
        for i in range(2):
            resp = self.client.post(
                reverse('accounts:sign_in'), {'email': 'victim@example.com'},
                REMOTE_ADDR=f'10.0.0.{i}',
            )
            self.assertRedirects(resp, reverse('accounts:link_sent'))
        # Same email, a fresh IP — still blocked by the per-email counter.
        resp = self.client.post(
            reverse('accounts:sign_in'), {'email': 'victim@example.com'},
            REMOTE_ADDR='10.0.0.99',
        )
        self.assertRedirects(resp, reverse('accounts:sign_in'))
        self.assertEqual(len(mail.outbox), 2)
