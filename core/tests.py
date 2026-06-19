from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .models import (
    ActivitySuggestion, AvailabilitySlot, CalendarAccess, Category, Interest, Status,
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
        self.future = self.now + timedelta(days=1)
        self.client.force_login(self.user)

    def _post_slot(self, start, end):
        fmt = '%Y-%m-%dT%H:%M'
        return self.client.post(reverse('core:slot_create'), {
            'start': start.strftime(fmt), 'end': end.strftime(fmt),
        })

    def test_create_slot(self):
        response = self._post_slot(self.future, self.future + timedelta(hours=2))
        self.assertRedirects(response, reverse('core:my_calendar'))
        slot = AvailabilitySlot.objects.get()
        self.assertEqual(slot.owner, self.user)
        self.assertEqual(slot.status, Status.OPEN)

    def test_end_before_start_is_rejected(self):
        response = self._post_slot(self.future, self.future - timedelta(hours=1))
        self.assertEqual(response.status_code, 200)  # re-rendered form
        self.assertFalse(AvailabilitySlot.objects.exists())

    def test_past_slot_is_rejected(self):
        response = self._post_slot(self.now - timedelta(days=1), self.now - timedelta(hours=22))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AvailabilitySlot.objects.exists())

    def test_slot_of_24h_or_more_is_rejected(self):
        response = self._post_slot(self.future, self.future + timedelta(hours=24))
        self.assertEqual(response.status_code, 200)
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

    def _edit_slot(self, slot, start, end):
        fmt = '%Y-%m-%dT%H:%M'
        return self.client.post(reverse('core:slot_edit', args=[slot.id]), {
            'start': start.strftime(fmt), 'end': end.strftime(fmt),
        })

    def test_edit_open_slot(self):
        slot = AvailabilitySlot.objects.create(
            owner=self.user, start=self.future, end=self.future + timedelta(hours=1),
        )
        new_start = self.future + timedelta(days=1)
        new_end = new_start + timedelta(hours=2)
        response = self._edit_slot(slot, new_start, new_end)
        self.assertRedirects(response, reverse('core:slot_detail', args=[slot.id]))
        slot.refresh_from_db()
        self.assertEqual(slot.start.hour, new_start.hour)
        self.assertEqual(slot.end.hour, new_end.hour)

    def test_cannot_edit_a_confirmed_slot(self):
        # A slot is editable only while Open; once Confirmed the time is settled.
        slot = AvailabilitySlot.objects.create(
            owner=self.user, start=self.future, end=self.future + timedelta(hours=1),
            status=Status.CONFIRMED,
        )
        self._edit_slot(slot, self.future + timedelta(days=2),
                        self.future + timedelta(days=2, hours=1))
        slot.refresh_from_db()
        self.assertEqual(slot.start.hour, self.future.hour)  # unchanged

    def test_cannot_edit_someone_elses_slot(self):
        slot = AvailabilitySlot.objects.create(
            owner=self.other, start=self.future, end=self.future + timedelta(hours=1),
        )
        response = self.client.get(reverse('core:slot_edit', args=[slot.id]))
        self.assertEqual(response.status_code, 404)

    def test_edit_warns_when_slot_has_interested_users(self):
        slot = AvailabilitySlot.objects.create(
            owner=self.user, start=self.future, end=self.future + timedelta(hours=1),
        )
        activity = ActivitySuggestion.objects.create(
            slot=slot, category=Category.TENNIS, title='Tennis',
        )
        Interest.objects.create(user=self.other, activity=activity)
        response = self.client.get(reverse('core:slot_edit', args=[slot.id]))
        self.assertContains(response, 'already shown interest')

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

    def test_capacity_may_be_blank_for_unlimited(self):
        activity = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.YOGA, title='Yoga',
        )
        self.assertIsNone(activity.max_participants)


class ActivityViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com', first_name='Owen', last_name='O',
        )
        self.other = User.objects.create_user(
            email='other@example.com', first_name='Otto', last_name='O',
        )
        now = timezone.now()
        self.slot = AvailabilitySlot.objects.create(
            owner=self.owner, start=now, end=now + timedelta(hours=2),
        )
        self.tennis = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.TENNIS, title='Tennis',
        )
        self.client.force_login(self.owner)

    def test_owner_can_create_activity(self):
        response = self.client.post(
            reverse('core:activity_create', args=[self.slot.id]),
            {'category': Category.COFFEE, 'title': 'Coffee', 'description': '', 'max_participants': ''},
        )
        self.assertRedirects(response, reverse('core:slot_detail', args=[self.slot.id]))
        self.assertTrue(self.slot.activities.filter(title='Coffee').exists())

    def test_non_owner_cannot_open_slot_detail(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('core:slot_detail', args=[self.slot.id]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_add_activity_once_slot_is_confirmed(self):
        self.tennis.confirm()  # slot becomes Confirmed
        response = self.client.post(
            reverse('core:activity_create', args=[self.slot.id]),
            {'category': Category.COFFEE, 'title': 'Coffee', 'description': ''},
        )
        self.assertRedirects(response, reverse('core:slot_detail', args=[self.slot.id]))
        self.assertFalse(self.slot.activities.filter(title='Coffee').exists())

    def test_confirm_action(self):
        coffee = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.COFFEE, title='Coffee',
        )
        self.client.post(reverse('core:activity_confirm', args=[self.tennis.id]))
        self.tennis.refresh_from_db()
        self.slot.refresh_from_db()
        coffee.refresh_from_db()
        self.assertEqual(self.tennis.status, Status.CONFIRMED)
        self.assertEqual(self.slot.status, Status.CONFIRMED)
        self.assertEqual(coffee.status, Status.CANCELLED)

    def test_cancel_confirmed_activity_shows_error_not_crash(self):
        self.tennis.confirm()
        response = self.client.post(
            reverse('core:activity_cancel', args=[self.tennis.id]), follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.tennis.refresh_from_db()
        self.assertEqual(self.tennis.status, Status.CONFIRMED)  # unchanged

    def test_non_owner_cannot_act_on_activity(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse('core:activity_confirm', args=[self.tennis.id]))
        self.assertEqual(response.status_code, 404)

    def test_owner_pages_render(self):
        detail = self.client.get(reverse('core:slot_detail', args=[self.slot.id]))
        self.assertEqual(detail.status_code, 200)
        form = self.client.get(reverse('core:activity_create', args=[self.slot.id]))
        self.assertEqual(form.status_code, 200)

    def _edit_activity(self, activity, category, title, description=''):
        return self.client.post(reverse('core:activity_edit', args=[activity.id]), {
            'category': category, 'title': title, 'description': description,
        })

    def test_edit_open_activity_can_change_everything(self):
        response = self._edit_activity(self.tennis, Category.COFFEE, 'Updated', 'New desc')
        self.assertRedirects(response, reverse('core:slot_detail', args=[self.slot.id]))
        self.tennis.refresh_from_db()
        self.assertEqual(self.tennis.title, 'Updated')
        self.assertEqual(self.tennis.category, Category.COFFEE)  # open → category editable

    def test_edit_confirmed_activity_locks_the_category(self):
        self.tennis.confirm()
        self._edit_activity(self.tennis, Category.COFFEE, 'Renamed')
        self.tennis.refresh_from_db()
        self.assertEqual(self.tennis.title, 'Renamed')          # title still editable
        self.assertEqual(self.tennis.category, Category.TENNIS)  # category locked

    def test_cannot_edit_a_cancelled_activity(self):
        self.tennis.cancel()  # open activity → cancel allowed
        self._edit_activity(self.tennis, Category.COFFEE, 'Nope')
        self.tennis.refresh_from_db()
        self.assertEqual(self.tennis.title, 'Tennis')  # unchanged

    def test_cannot_edit_a_closed_activity(self):
        self.tennis.confirm()
        self.tennis.close()
        self._edit_activity(self.tennis, Category.TENNIS, 'Nope')
        self.tennis.refresh_from_db()
        self.assertEqual(self.tennis.title, 'Tennis')  # unchanged (reopen first to edit)

    def test_non_owner_cannot_edit_activity(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('core:activity_edit', args=[self.tennis.id]))
        self.assertEqual(response.status_code, 404)


class InterestTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email='alice@example.com', first_name='Alice', last_name='A',
        )
        self.bob = User.objects.create_user(
            email='bob@example.com', first_name='Bob', last_name='B',
        )
        now = timezone.now()
        self.slot = AvailabilitySlot.objects.create(
            owner=self.alice, start=now + timedelta(hours=1), end=now + timedelta(hours=3),
        )
        self.tennis = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.TENNIS, title='Tennis',
        )
        CalendarAccess.objects.create(creator=self.alice, visitor=self.bob)
        self.client.force_login(self.bob)

    def test_visitor_can_express_interest(self):
        self.client.post(reverse('core:interest_add', args=[self.tennis.id]))
        self.assertTrue(Interest.objects.filter(user=self.bob, activity=self.tennis).exists())

    def test_cannot_express_interest_twice(self):
        self.client.post(reverse('core:interest_add', args=[self.tennis.id]))
        self.client.post(reverse('core:interest_add', args=[self.tennis.id]))
        self.assertEqual(Interest.objects.filter(activity=self.tennis).count(), 1)

    def test_cannot_express_interest_in_own_activity(self):
        self.client.force_login(self.alice)
        self.client.post(reverse('core:interest_add', args=[self.tennis.id]))
        self.assertFalse(Interest.objects.filter(user=self.alice).exists())

    def test_cannot_express_interest_without_access(self):
        carol = User.objects.create_user(
            email='carol@example.com', first_name='Carol', last_name='C',
        )
        self.client.force_login(carol)
        self.client.post(reverse('core:interest_add', args=[self.tennis.id]))
        self.assertFalse(Interest.objects.filter(user=carol).exists())

    def test_cannot_join_a_cancelled_activity(self):
        self.tennis.cancel()
        self.client.post(reverse('core:interest_add', args=[self.tennis.id]))
        self.assertFalse(Interest.objects.filter(activity=self.tennis).exists())

    def test_remove_interest(self):
        Interest.objects.create(user=self.bob, activity=self.tennis)
        self.client.post(reverse('core:interest_remove', args=[self.tennis.id]))
        self.assertFalse(Interest.objects.filter(user=self.bob, activity=self.tennis).exists())

    def test_blocked_visitor_cannot_join_a_post_block_activity(self):
        # Blocking must hold even if the visitor guesses the activity id: a slot
        # created after the block is invisible to them and can't be joined.
        access = CalendarAccess.objects.get(creator=self.alice, visitor=self.bob)
        access.set_blocked(True)
        new_slot = AvailabilitySlot.objects.create(
            owner=self.alice,
            start=timezone.now() + timedelta(hours=1),
            end=timezone.now() + timedelta(hours=2),
        )
        AvailabilitySlot.objects.filter(pk=new_slot.pk).update(
            created_at=access.blocked_at + timedelta(hours=1),
        )
        activity = ActivitySuggestion.objects.create(
            slot=new_slot, category=Category.COFFEE, title='Coffee',
        )
        self.client.post(reverse('core:interest_add', args=[activity.id]))
        self.assertFalse(Interest.objects.filter(user=self.bob, activity=activity).exists())

    def test_blocked_visitor_can_still_join_a_pre_block_activity(self):
        # The slot from setUp existed before the block, so it stays joinable —
        # blocking only cuts off what was created afterwards.
        access = CalendarAccess.objects.get(creator=self.alice, visitor=self.bob)
        access.set_blocked(True)
        self.client.post(reverse('core:interest_add', args=[self.tennis.id]))
        self.assertTrue(Interest.objects.filter(user=self.bob, activity=self.tennis).exists())


class VisibilityTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email='alice@example.com', first_name='Alice', last_name='A',
        )
        self.bob = User.objects.create_user(
            email='bob@example.com', first_name='Bob', last_name='B',
        )
        now = timezone.now()
        self.slot = AvailabilitySlot.objects.create(
            owner=self.alice, start=now + timedelta(hours=1), end=now + timedelta(hours=3),
        )
        self.access = CalendarAccess.objects.create(creator=self.alice, visitor=self.bob)
        self.client.force_login(self.bob)

    def _visible_activity_ids(self):
        response = self.client.get(reverse('core:shared_calendar', args=[self.alice.share_slug]))
        return [a.id for row in response.context['slot_rows'] for a in row['activities']]

    def test_cancelled_activity_is_hidden(self):
        tennis = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.TENNIS, title='Tennis',
        )
        tennis.cancel()
        self.assertNotIn(tennis.id, self._visible_activity_ids())

    def test_closed_activity_hidden_from_non_interested(self):
        tennis = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.TENNIS, title='Tennis',
        )
        tennis.confirm()
        tennis.close()
        self.assertNotIn(tennis.id, self._visible_activity_ids())

    def test_closed_activity_visible_to_already_interested(self):
        tennis = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.TENNIS, title='Tennis',
        )
        Interest.objects.create(user=self.bob, activity=tennis)
        tennis.confirm()
        tennis.close()
        self.assertIn(tennis.id, self._visible_activity_ids())

    def test_blocked_visitor_does_not_see_slots_created_after_block(self):
        self.access.blocked_by_creator = True
        self.access.blocked_at = timezone.now()
        self.access.save()
        now = timezone.now()
        old = AvailabilitySlot.objects.create(
            owner=self.alice, start=now + timedelta(hours=1), end=now + timedelta(hours=2),
        )
        AvailabilitySlot.objects.filter(pk=old.pk).update(
            created_at=self.access.blocked_at - timedelta(hours=1),
        )
        new = AvailabilitySlot.objects.create(
            owner=self.alice, start=now + timedelta(hours=1), end=now + timedelta(hours=2),
        )
        AvailabilitySlot.objects.filter(pk=new.pk).update(
            created_at=self.access.blocked_at + timedelta(hours=1),
        )
        response = self.client.get(reverse('core:shared_calendar', args=[self.alice.share_slug]))
        slot_ids = [row['slot'].id for row in response.context['slot_rows']]
        self.assertIn(old.id, slot_ids)
        self.assertNotIn(new.id, slot_ids)


class DashboardTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email='alice@example.com', first_name='Alice', last_name='Anderson',
        )
        self.bob = User.objects.create_user(
            email='bob@example.com', first_name='Bob', last_name='Brown',
        )
        now = timezone.now()
        self.slot = AvailabilitySlot.objects.create(
            owner=self.alice, start=now + timedelta(hours=1), end=now + timedelta(hours=3),
        )
        self.tennis = ActivitySuggestion.objects.create(
            slot=self.slot, category=Category.TENNIS, title='Tennis',
        )
        Interest.objects.create(user=self.bob, activity=self.tennis)

    def test_dashboard_lists_interested_users_by_name(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bob Brown')

    def test_dashboard_never_exposes_email(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('core:dashboard'))
        self.assertNotContains(response, 'bob@example.com')

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertIn(reverse('accounts:sign_in'), response.url)


class ConsolidatedCalendarTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email='alice@example.com', first_name='Alice', last_name='A',
        )
        self.carol = User.objects.create_user(
            email='carol@example.com', first_name='Carol', last_name='C',
        )
        now = timezone.now()
        self.own = AvailabilitySlot.objects.create(
            owner=self.alice, start=now + timedelta(hours=2), end=now + timedelta(hours=3),
        )
        self.friend_slot = AvailabilitySlot.objects.create(
            owner=self.carol, start=now + timedelta(hours=1), end=now + timedelta(hours=2),
        )
        self.access = CalendarAccess.objects.create(creator=self.carol, visitor=self.alice)
        self.client.force_login(self.alice)

    def _slot_ids(self):
        response = self.client.get(reverse('core:consolidated'))
        return [row['slot'].id for row in response.context['rows']]

    def test_combines_own_and_accessible_slots(self):
        ids = self._slot_ids()
        self.assertIn(self.own.id, ids)
        self.assertIn(self.friend_slot.id, ids)

    def test_rows_are_chronological(self):
        response = self.client.get(reverse('core:consolidated'))
        starts = [row['slot'].start for row in response.context['rows']]
        self.assertEqual(starts, sorted(starts))

    def test_archived_calendar_is_excluded(self):
        self.access.set_archived(True)
        ids = self._slot_ids()
        self.assertNotIn(self.friend_slot.id, ids)
        self.assertIn(self.own.id, ids)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('core:consolidated'))
        self.assertIn(reverse('accounts:sign_in'), response.url)

    def test_grid_weeks_have_seven_days(self):
        response = self.client.get(reverse('core:consolidated'))
        self.assertTrue(response.context['weeks'])
        for week in response.context['weeks']:
            self.assertEqual(len(week), 7)

    def test_month_navigation(self):
        response = self.client.get(reverse('core:consolidated'), {'y': 2030, 'm': 1})
        self.assertContains(response, 'January 2030')
