from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Member, RateLimitHit


def login_member(client, member):
    session = client.session
    session["member_id"] = member.pk
    session.save()


class MemberModelTests(TestCase):
    def test_new_member_defaults_to_pending(self):
        member = Member.objects.create(username="alice")
        self.assertEqual(member.status, Member.PENDING)
        self.assertFalse(member.is_approved)

    def test_is_approved_reflects_status(self):
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        self.assertTrue(member.is_approved)

    def test_is_online_within_window(self):
        member = Member.objects.create(username="alice")
        member.last_seen = timezone.now()
        self.assertTrue(member.is_online(window_seconds=45))
        member.last_seen = timezone.now() - timedelta(seconds=100)
        self.assertFalse(member.is_online(window_seconds=45))


class RateLimitHitTests(TestCase):
    def test_allows_up_to_limit_then_blocks(self):
        for _ in range(3):
            self.assertTrue(RateLimitHit.allow("test-key", limit=3, window_seconds=60))
        self.assertFalse(RateLimitHit.allow("test-key", limit=3, window_seconds=60))

    def test_different_keys_are_independent(self):
        for _ in range(3):
            RateLimitHit.allow("key-a", limit=3, window_seconds=60)
        self.assertTrue(RateLimitHit.allow("key-b", limit=3, window_seconds=60))


class RegistrationFlowTests(TestCase):
    def test_home_shows_registration_form_when_anonymous(self):
        response = Client().get(reverse("identity:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "username")

    def test_valid_registration_creates_pending_member_and_session(self):
        client = Client()
        response = client.post(reverse("identity:home"), {"username": "alice"})
        self.assertRedirects(response, reverse("identity:status"))
        member = Member.objects.get(username="alice")
        self.assertEqual(member.status, Member.PENDING)
        self.assertEqual(client.session["member_id"], member.pk)

    def test_username_is_normalized_to_lowercase(self):
        client = Client()
        client.post(reverse("identity:home"), {"username": "Alice"})
        self.assertTrue(Member.objects.filter(username="alice").exists())

    def test_duplicate_username_rejected_case_insensitively(self):
        Member.objects.create(username="alice")
        client = Client()
        response = client.post(reverse("identity:home"), {"username": "ALICE"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already taken")
        self.assertEqual(Member.objects.filter(username="alice").count(), 1)

    def test_approved_username_can_be_rejoined_instead_of_blocked(self):
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        client = Client()
        response = client.post(reverse("identity:home"), {"username": "alice"})
        self.assertRedirects(response, reverse("chat:room"))
        self.assertEqual(client.session["member_id"], member.pk)
        # No second Member was created — it's the same row.
        self.assertEqual(Member.objects.filter(username="alice").count(), 1)

    def test_approved_username_can_be_rejoined_unlimited_times(self):
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        for _ in range(5):
            client = Client()
            response = client.post(reverse("identity:home"), {"username": "alice"})
            self.assertRedirects(response, reverse("chat:room"))
            self.assertEqual(client.session["member_id"], member.pk)

    def test_pending_username_still_blocks_rejoin(self):
        Member.objects.create(username="alice", status=Member.PENDING)
        client = Client()
        response = client.post(reverse("identity:home"), {"username": "alice"})
        self.assertContains(response, "already taken")
        self.assertEqual(Member.objects.filter(username="alice").count(), 1)

    def test_rejected_username_still_blocks_rejoin(self):
        Member.objects.create(username="alice", status=Member.REJECTED)
        client = Client()
        response = client.post(reverse("identity:home"), {"username": "alice"})
        self.assertContains(response, "already taken")
        self.assertEqual(Member.objects.filter(username="alice").count(), 1)

    def test_invalid_username_format_rejected(self):
        client = Client()
        response = client.post(reverse("identity:home"), {"username": "1bad!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Member.objects.count(), 0)

    def test_registration_is_rate_limited_per_ip(self):
        # A fresh Client() per attempt: once a request registers a member,
        # request.member is set and home() redirects it away from the
        # registration form entirely (by design — see test above), so
        # reusing one client would only ever exercise the first attempt.
        # Django's test client uses a fixed REMOTE_ADDR, matching the real
        # abuse case this guards against: a script retrying without cookies.
        for i in range(10):
            Client().post(reverse("identity:home"), {"username": f"user{i}"})
        response = Client().post(reverse("identity:home"), {"username": "oneMore"})
        self.assertContains(response, "Too many attempts")


class StatusViewTests(TestCase):
    def test_anonymous_redirected_to_home(self):
        response = Client().get(reverse("identity:status"))
        self.assertRedirects(response, reverse("identity:home"))

    def test_pending_member_sees_pending_page(self):
        member = Member.objects.create(username="alice")
        client = Client()
        login_member(client, member)
        response = client.get(reverse("identity:status"))
        self.assertContains(response, "waiting")

    def test_rejected_member_sees_rejected_page(self):
        member = Member.objects.create(username="alice", status=Member.REJECTED)
        client = Client()
        login_member(client, member)
        response = client.get(reverse("identity:status"))
        self.assertContains(response, "declined")

    def test_approved_member_redirected_to_room(self):
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        client = Client()
        login_member(client, member)
        response = client.get(reverse("identity:status"))
        self.assertRedirects(response, reverse("chat:room"))

    def test_status_poll_reports_current_status(self):
        member = Member.objects.create(username="alice")
        client = Client()
        login_member(client, member)
        response = client.get(reverse("identity:status_poll"))
        self.assertEqual(response.json(), {"status": "pending"})

    def test_status_poll_anonymous_is_forbidden(self):
        response = Client().get(reverse("identity:status_poll"))
        self.assertEqual(response.status_code, 403)

    def test_leave_deletes_pending_member_and_frees_the_username(self):
        member = Member.objects.create(username="alice")  # default status: pending
        client = Client()
        login_member(client, member)
        client.post(reverse("identity:leave"))

        self.assertNotIn("member_id", client.session)
        self.assertFalse(Member.objects.filter(pk=member.pk).exists())

        # The whole point: the username must be immediately re-registerable.
        second_client = Client()
        response = second_client.post(reverse("identity:home"), {"username": "alice"})
        self.assertRedirects(response, reverse("identity:status"))
        self.assertTrue(Member.objects.filter(username="alice").exists())

    def test_leave_deletes_pending_member_but_preserves_message_history(self):
        from chat.models import Message

        member = Member.objects.create(username="alice")  # default status: pending
        message = Message.objects.create(sender=member, sender_username="alice", kind=Message.TEXT, text="hi")

        client = Client()
        login_member(client, member)
        client.post(reverse("identity:leave"))

        message.refresh_from_db()
        self.assertIsNone(message.sender_id)
        self.assertEqual(message.sender_username, "alice")

    def test_leave_signs_out_approved_member_without_deleting_them(self):
        # Approval is permanent: leaving an approved member just clears the
        # session, it does not touch their Member row or their messages.
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        client = Client()
        login_member(client, member)
        client.post(reverse("identity:leave"))

        self.assertNotIn("member_id", client.session)
        member.refresh_from_db()
        self.assertEqual(member.status, Member.APPROVED)

        # And they can jump straight back in without any re-approval.
        second_client = Client()
        response = second_client.post(reverse("identity:home"), {"username": "alice"})
        self.assertRedirects(response, reverse("chat:room"))
        self.assertEqual(second_client.session["member_id"], member.pk)

    def test_leave_with_no_member_is_a_harmless_noop(self):
        response = Client().post(reverse("identity:leave"))
        self.assertRedirects(response, reverse("identity:home"))


class MemberMiddlewareTests(TestCase):
    def test_last_seen_is_throttled_not_updated_every_request(self):
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        recent = timezone.now() - timedelta(seconds=5)
        Member.objects.filter(pk=member.pk).update(last_seen=recent)

        client = Client()
        login_member(client, member)
        client.get(reverse("identity:status"))

        member.refresh_from_db()
        self.assertAlmostEqual(member.last_seen, recent, delta=timedelta(seconds=2))

    def test_last_seen_updates_once_stale(self):
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        stale = timezone.now() - timedelta(minutes=5)
        Member.objects.filter(pk=member.pk).update(last_seen=stale)

        client = Client()
        login_member(client, member)
        client.get(reverse("identity:status"))

        member.refresh_from_db()
        self.assertGreater(member.last_seen, stale)


class StaffApprovalsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffer", password="x", is_staff=True)

    def _login_staff(self):
        client = Client()
        client.force_login(self.staff_user)
        return client

    def test_anonymous_redirected_to_admin_login(self):
        response = Client().get(reverse("identity:staff_approvals"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_approved_member_without_staff_flag_is_not_staff(self):
        # A regular approved member (session-based identity) is not staff —
        # staff_member_required checks django.contrib.auth, not request.member.
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        client = Client()
        login_member(client, member)
        response = client.get(reverse("identity:staff_approvals"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_sees_pending_and_recent_decisions(self):
        Member.objects.create(username="pendingone", status=Member.PENDING)
        Member.objects.create(username="approvedone", status=Member.APPROVED)
        client = self._login_staff()
        response = client.get(reverse("identity:staff_approvals"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m.username for m in response.context["pending"]], ["pendingone"])
        self.assertEqual([m.username for m in response.context["recent_decisions"]], ["approvedone"])

    def test_staff_can_approve(self):
        member = Member.objects.create(username="alice")
        client = self._login_staff()
        response = client.post(reverse("identity:staff_approve", args=[member.pk]))
        self.assertRedirects(response, reverse("identity:staff_approvals"))
        member.refresh_from_db()
        self.assertEqual(member.status, Member.APPROVED)

    def test_staff_can_reject(self):
        member = Member.objects.create(username="alice")
        client = self._login_staff()
        client.post(reverse("identity:staff_reject", args=[member.pk]))
        member.refresh_from_db()
        self.assertEqual(member.status, Member.REJECTED)

    def test_non_staff_cannot_approve(self):
        member = Member.objects.create(username="alice")
        response = Client().post(reverse("identity:staff_approve", args=[member.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
        member.refresh_from_db()
        self.assertEqual(member.status, Member.PENDING)

    def test_staff_can_remove_a_stuck_member_and_free_the_username(self):
        # This is the recovery path when the original person has no way to
        # reach their own Leave button (lost session, different browser).
        Member.objects.create(username="stuckuser", status=Member.APPROVED)
        client = self._login_staff()
        response = client.post(reverse("identity:staff_remove_member", args=[Member.objects.get(username="stuckuser").pk]))
        self.assertRedirects(response, reverse("identity:staff_approvals"))
        self.assertFalse(Member.objects.filter(username="stuckuser").exists())

        # The freed username can immediately be re-registered.
        response = Client().post(reverse("identity:home"), {"username": "stuckuser"})
        self.assertRedirects(response, reverse("identity:status"))

    def test_staff_can_remove_regardless_of_status(self):
        pending = Member.objects.create(username="pendingone")
        rejected = Member.objects.create(username="rejectedone", status=Member.REJECTED)
        client = self._login_staff()
        client.post(reverse("identity:staff_remove_member", args=[pending.pk]))
        client.post(reverse("identity:staff_remove_member", args=[rejected.pk]))
        self.assertFalse(Member.objects.filter(pk__in=[pending.pk, rejected.pk]).exists())

    def test_removing_member_preserves_their_messages(self):
        from chat.models import Message

        member = Member.objects.create(username="alice", status=Member.APPROVED)
        message = Message.objects.create(sender=member, sender_username="alice", kind=Message.TEXT, text="hi")

        client = self._login_staff()
        client.post(reverse("identity:staff_remove_member", args=[member.pk]))

        message.refresh_from_db()
        self.assertIsNone(message.sender_id)
        self.assertEqual(message.sender_username, "alice")

    def test_non_staff_cannot_remove(self):
        member = Member.objects.create(username="alice", status=Member.APPROVED)
        response = Client().post(reverse("identity:staff_remove_member", args=[member.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
        self.assertTrue(Member.objects.filter(pk=member.pk).exists())
