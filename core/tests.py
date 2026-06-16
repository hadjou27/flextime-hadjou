from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import CalendarAccess

User = get_user_model()


class SharedCalendarViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email='alice@example.com', first_name='Alice', last_name='A',
        )
        self.bob = User.objects.create_user(
            email='bob@example.com', first_name='Bob', last_name='B',
        )
        self.alice_url = reverse('core:shared_calendar', args=[self.alice.share_slug])

    def test_anonymous_visitor_is_redirected_to_sign_in(self):
        response = self.client.get(self.alice_url)
        self.assertIn(reverse('accounts:sign_in'), response.url)
        self.assertIn('next=', response.url)

    def test_opening_a_link_grants_access(self):
        self.client.force_login(self.bob)
        response = self.client.get(self.alice_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CalendarAccess.objects.filter(creator=self.alice, visitor=self.bob).exists()
        )

    def test_opening_twice_does_not_duplicate_access(self):
        self.client.force_login(self.bob)
        self.client.get(self.alice_url)
        self.client.get(self.alice_url)
        self.assertEqual(
            CalendarAccess.objects.filter(creator=self.alice, visitor=self.bob).count(), 1
        )

    def test_owner_opening_own_link_creates_no_access(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.alice_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_owner'])
        self.assertFalse(CalendarAccess.objects.filter(visitor=self.alice).exists())

    def test_unknown_slug_returns_404(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('core:shared_calendar', args=['nobody-x-zzz']))
        self.assertEqual(response.status_code, 404)


class OtherCalendarsListTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email='alice@example.com', first_name='Alice', last_name='A',
        )
        self.bob = User.objects.create_user(
            email='bob@example.com', first_name='Bob', last_name='B',
        )

    def test_archived_calendars_are_hidden_from_the_list(self):
        access = CalendarAccess.objects.create(creator=self.alice, visitor=self.bob)
        self.client.force_login(self.bob)

        response = self.client.get(reverse('core:my_calendar'))
        self.assertIn(access, response.context['accessible'])

        access.set_archived(True)
        response = self.client.get(reverse('core:my_calendar'))
        self.assertNotIn(access, response.context['accessible'])


class ArchiveBlockActionTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email='alice@example.com', first_name='Alice', last_name='A',
        )
        self.bob = User.objects.create_user(
            email='bob@example.com', first_name='Bob', last_name='B',
        )
        self.access = CalendarAccess.objects.create(creator=self.alice, visitor=self.bob)

    def test_visitor_can_archive_and_restore(self):
        self.client.force_login(self.bob)

        self.client.post(reverse('core:archive_calendar', args=[self.alice.share_slug]))
        self.access.refresh_from_db()
        self.assertTrue(self.access.archived_by_visitor)
        self.assertIsNotNone(self.access.archived_at)

        self.client.post(reverse('core:unarchive_calendar', args=[self.alice.share_slug]))
        self.access.refresh_from_db()
        self.assertFalse(self.access.archived_by_visitor)
        self.assertIsNone(self.access.archived_at)

    def test_owner_can_block_and_unblock(self):
        self.client.force_login(self.alice)

        self.client.post(reverse('core:block_visitor', args=[self.bob.id]))
        self.access.refresh_from_db()
        self.assertTrue(self.access.blocked_by_creator)
        self.assertIsNotNone(self.access.blocked_at)

        self.client.post(reverse('core:unblock_visitor', args=[self.bob.id]))
        self.access.refresh_from_db()
        self.assertFalse(self.access.blocked_by_creator)

    def test_actions_require_post(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('core:archive_calendar', args=[self.alice.share_slug]))
        self.assertEqual(response.status_code, 405)

    def test_owner_cannot_archive_a_visitors_relationship(self):
        # Alice is the creator, not the visitor, so she has no access to archive.
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('core:archive_calendar', args=[self.alice.share_slug])
        )
        self.assertEqual(response.status_code, 404)
