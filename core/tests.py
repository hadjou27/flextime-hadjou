from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .models import (
    ActivitySuggestion, AvailabilitySlot, CalendarAccess, Category, Status,
)

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


class AvailabilitySlotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='sam@example.com', first_name='Sam', last_name='S',
        )
        self.other = User.objects.create_user(
            email='mia@example.com', first_name='Mia', last_name='M',
        )
        self.now = timezone.now()
        self.client.force_login(self.user)

    def _post_slot(self, start, end):
        fmt = '%Y-%m-%dT%H:%M'
        return self.client.post(reverse('core:slot_create'), {
            'start': start.strftime(fmt), 'end': end.strftime(fmt),
        })

    def test_create_slot(self):
        response = self._post_slot(self.now, self.now + timedelta(hours=2))
        self.assertRedirects(response, reverse('core:my_calendar'))
        slot = AvailabilitySlot.objects.get()
        self.assertEqual(slot.owner, self.user)
        self.assertEqual(slot.status, Status.OPEN)

    def test_end_before_start_is_rejected(self):
        response = self._post_slot(self.now, self.now - timedelta(hours=1))
        self.assertEqual(response.status_code, 200)  # re-rendered form
        self.assertFalse(AvailabilitySlot.objects.exists())

    def test_cancel_slot(self):
        slot = AvailabilitySlot.objects.create(
            owner=self.user, start=self.now, end=self.now + timedelta(hours=1),
        )
        self.client.post(reverse('core:slot_cancel', args=[slot.id]))
        slot.refresh_from_db()
        self.assertEqual(slot.status, Status.CANCELLED)

    def test_cannot_cancel_someone_elses_slot(self):
        slot = AvailabilitySlot.objects.create(
            owner=self.other, start=self.now, end=self.now + timedelta(hours=1),
        )
        response = self.client.post(reverse('core:slot_cancel', args=[slot.id]))
        self.assertEqual(response.status_code, 404)

    def test_old_slots_are_hidden_from_my_calendar(self):
        recent = AvailabilitySlot.objects.create(
            owner=self.user, start=self.now, end=self.now + timedelta(hours=1),
        )
        old = AvailabilitySlot.objects.create(
            owner=self.user,
            start=self.now - timedelta(days=10),
            end=self.now - timedelta(days=10) + timedelta(hours=1),
        )
        response = self.client.get(reverse('core:my_calendar'))
        slots = list(response.context['slots'])
        self.assertIn(recent, slots)
        self.assertNotIn(old, slots)


class StateMachineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@example.com', first_name='Owen', last_name='O',
        )
        now = timezone.now()
        self.slot = AvailabilitySlot.objects.create(
            owner=self.user, start=now, end=now + timedelta(hours=2),
        )
        self.tennis = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.TENNIS, title='Tennis',
        )
        self.coffee = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.COFFEE, title='Coffee',
        )

    def _reload(self):
        self.slot.refresh_from_db()
        self.tennis.refresh_from_db()
        self.coffee.refresh_from_db()

    def test_confirm_sets_slot_and_cancels_siblings(self):
        self.tennis.confirm()
        self._reload()
        self.assertEqual(self.tennis.status, Status.CONFIRMED)
        self.assertEqual(self.slot.status, Status.CONFIRMED)
        self.assertEqual(self.coffee.status, Status.CANCELLED)

    def test_only_one_confirmed_activity_per_slot(self):
        self.tennis.status = Status.CONFIRMED
        self.tennis.save()
        with self.assertRaises(IntegrityError):
            self.coffee.status = Status.CONFIRMED
            self.coffee.save()

    def test_close_sets_slot_closed(self):
        self.tennis.confirm()
        self.tennis.close()
        self._reload()
        self.assertEqual(self.tennis.status, Status.CLOSED)
        self.assertEqual(self.slot.status, Status.CLOSED)

    def test_only_confirmed_activity_can_be_closed(self):
        with self.assertRaises(ValidationError):
            self.tennis.close()  # still open

    def test_reopen_is_the_inverse_of_close(self):
        self.tennis.confirm()
        self.tennis.close()
        self.tennis.reopen()
        self._reload()
        self.assertEqual(self.tennis.status, Status.CONFIRMED)
        self.assertEqual(self.slot.status, Status.CONFIRMED)

    def test_only_closed_activity_can_be_reopened(self):
        with self.assertRaises(ValidationError):
            self.tennis.reopen()  # open, not closed

    def test_cancelling_a_slot_cancels_its_activities(self):
        self.slot.cancel()
        self._reload()
        self.assertEqual(self.slot.status, Status.CANCELLED)
        self.assertEqual(self.tennis.status, Status.CANCELLED)
        self.assertEqual(self.coffee.status, Status.CANCELLED)

    def test_cannot_cancel_the_confirmed_activity(self):
        self.tennis.confirm()
        with self.assertRaises(ValidationError):
            self.tennis.cancel()

    def test_can_cancel_an_open_activity(self):
        self.coffee.cancel()
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.status, Status.CANCELLED)


class ActivityCapacityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='cap@example.com', first_name='Cap', last_name='C',
        )
        now = timezone.now()
        self.slot = AvailabilitySlot.objects.create(
            owner=self.user, start=now, end=now + timedelta(hours=1),
        )

    def test_capacity_of_zero_is_rejected(self):
        with self.assertRaises(IntegrityError):
            ActivitySuggestion.objects.create(
                slot=self.slot, category=Category.YOGA, title='Yoga',
                max_participants=0,
            )

    def test_capacity_may_be_blank_for_unlimited(self):
        activity = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.YOGA, title='Yoga',
        )
        self.assertIsNone(activity.max_participants)
