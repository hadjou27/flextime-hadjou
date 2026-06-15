import re

from django.contrib.auth import get_user_model
from django.core import mail
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
        resp = self.client.post(reverse('accounts:sign_in'), {
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

    def test_new_user_without_name_is_rejected(self):
        resp = self.client.post(reverse('accounts:sign_in'), {'email': 'noname@example.com'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'new here')
        self.assertFalse(User.objects.filter(email='noname@example.com').exists())

    def test_returning_user_needs_only_email(self):
        User.objects.create_user(email='back@example.com', first_name='Back', last_name='Again')
        resp = self.client.post(reverse('accounts:sign_in'), {'email': 'back@example.com'})
        self.assertRedirects(resp, reverse('accounts:link_sent'))
        self.assertEqual(len(mail.outbox), 1)

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
