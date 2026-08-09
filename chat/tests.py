import json
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from identity.models import Member

from .models import Message

# Uploaded test files hit real FileSystemStorage (unlike the DB, storage
# isn't rolled back between tests), so tests that upload attachments use an
# isolated, auto-deleted MEDIA_ROOT instead of the project's real media/.
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="communicator-test-media-")


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


def login_member(client, member):
    session = client.session
    session["member_id"] = member.pk
    session.save()


def make_member(username, status=Member.APPROVED):
    return Member.objects.create(username=username, status=status)


class RoomViewTests(TestCase):
    def test_anonymous_redirected_to_home(self):
        response = Client().get(reverse("chat:room"))
        self.assertRedirects(response, reverse("identity:home"))

    def test_pending_member_redirected_to_status(self):
        member = make_member("alice", status=Member.PENDING)
        client = Client()
        login_member(client, member)
        response = client.get(reverse("chat:room"))
        self.assertRedirects(response, reverse("identity:status"))

    def test_approved_member_sees_room(self):
        member = make_member("alice")
        make_member("bob")
        Message.objects.create(sender=member, kind=Message.TEXT, text="hi all")

        client = Client()
        login_member(client, member)
        response = client.get(reverse("chat:room"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["messages_json"]), 1)
        usernames = {m["username"] for m in response.context["members"]}
        self.assertEqual(usernames, {"alice", "bob"})

    def test_room_excludes_previous_days_messages(self):
        # The live room is today only — older messages belong exclusively
        # to the day archive (see DayViewTests), never mixed in here.
        member = make_member("alice")
        today_message = Message.objects.create(sender=member, kind=Message.TEXT, text="today")
        yesterday_message = Message.objects.create(sender=member, kind=Message.TEXT, text="yesterday")
        backdate(yesterday_message, days_ago=1)

        client = Client()
        login_member(client, member)
        response = client.get(reverse("chat:room"))

        ids = [m["id"] for m in response.context["messages_json"]]
        self.assertEqual(ids, [today_message.pk])

    def test_room_context_includes_todays_date(self):
        # The template stamps this onto .room-shell's data-today attribute
        # so poll-room.js can detect a midnight rollover client-side.
        member = make_member("alice")
        client = Client()
        login_member(client, member)
        response = client.get(reverse("chat:room"))
        self.assertEqual(response.context["today"], timezone.localdate().isoformat())


class MessagesPollViewTests(TestCase):
    def setUp(self):
        self.alice = make_member("alice")
        self.bob = make_member("bob")
        self.client = Client()
        login_member(self.client, self.alice)

    def test_anonymous_is_rejected(self):
        response = Client().get(reverse("chat:messages_poll"))
        self.assertEqual(response.status_code, 403)

    def test_pending_member_is_rejected(self):
        pending = make_member("carol", status=Member.PENDING)
        client = Client()
        login_member(client, pending)
        response = client.get(reverse("chat:messages_poll"))
        self.assertEqual(response.status_code, 403)

    def test_after_cursor_only_returns_newer_messages(self):
        m1 = Message.objects.create(sender=self.bob, kind=Message.TEXT, text="one")
        m2 = Message.objects.create(sender=self.bob, kind=Message.TEXT, text="two")

        response = self.client.get(reverse("chat:messages_poll"), {"after": m1.pk})
        data = json.loads(response.content)
        ids = [m["id"] for m in data["messages"]]
        self.assertEqual(ids, [m2.pk])

    def test_poll_reports_online_members(self):
        response = self.client.get(reverse("chat:messages_poll"), {"after": 0})
        data = json.loads(response.content)
        usernames = {m["username"] for m in data["members"]}
        self.assertEqual(usernames, {"alice", "bob"})

    def test_rejected_and_pending_members_excluded_from_list(self):
        make_member("dave", status=Member.REJECTED)
        make_member("erin", status=Member.PENDING)
        response = self.client.get(reverse("chat:messages_poll"), {"after": 0})
        data = json.loads(response.content)
        usernames = {m["username"] for m in data["members"]}
        self.assertEqual(usernames, {"alice", "bob"})

    def test_poll_excludes_previous_days_messages(self):
        yesterday_message = Message.objects.create(sender=self.bob, kind=Message.TEXT, text="yesterday")
        backdate(yesterday_message, days_ago=1)

        response = self.client.get(reverse("chat:messages_poll"), {"after": 0})
        data = json.loads(response.content)
        self.assertEqual(data["messages"], [])

    def test_poll_reports_todays_date_for_rollover_detection(self):
        # poll-room.js compares this against the date the page loaded with
        # and reloads on mismatch, so a tab left open across midnight
        # cleanly opens a fresh live chat instead of silently appending.
        response = self.client.get(reverse("chat:messages_poll"), {"after": 0})
        data = json.loads(response.content)
        self.assertEqual(data["today"], timezone.localdate().isoformat())


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class SendMessageViewTests(TestCase):
    def setUp(self):
        self.alice = make_member("alice")
        self.client = Client()
        login_member(self.client, self.alice)

    def _send_url(self):
        return reverse("chat:send")

    def test_anonymous_client_is_rejected(self):
        response = Client().post(self._send_url(), {"text": "hi"})
        self.assertEqual(response.status_code, 403)

    def test_pending_member_is_rejected(self):
        pending = make_member("carol", status=Member.PENDING)
        client = Client()
        login_member(client, pending)
        response = client.post(self._send_url(), {"text": "hi"})
        self.assertEqual(response.status_code, 403)

    def test_empty_payload_rejected(self):
        response = self.client.post(self._send_url(), {})
        self.assertEqual(response.status_code, 400)

    def test_text_message_created(self):
        response = self.client.post(self._send_url(), {"text": "hello room"})
        self.assertEqual(response.status_code, 201)
        message = Message.objects.get()
        self.assertEqual(message.kind, Message.TEXT)
        self.assertEqual(message.text, "hello room")
        self.assertEqual(message.sender_id, self.alice.pk)

    def test_file_attachment_created_with_metadata(self):
        upload = SimpleUploadedFile("photo.png", b"fake-bytes", content_type="image/png")
        response = self.client.post(self._send_url(), {"attachment": upload})
        self.assertEqual(response.status_code, 201)
        message = Message.objects.get()
        self.assertEqual(message.kind, Message.FILE)
        self.assertEqual(message.original_filename, "photo.png")
        self.assertEqual(message.size, len(b"fake-bytes"))

    def test_voice_kind_is_honored_for_uploads(self):
        upload = SimpleUploadedFile("clip.webm", b"audio-bytes", content_type="audio/webm")
        self.client.post(self._send_url(), {"attachment": upload, "kind": "voice"})
        message = Message.objects.get()
        self.assertEqual(message.kind, Message.VOICE)

    def test_blocked_extension_rejected(self):
        upload = SimpleUploadedFile("shell.php", b"<?php ?>", content_type="text/plain")
        response = self.client.post(self._send_url(), {"attachment": upload})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.count(), 0)

    def test_send_is_rate_limited(self):
        for _ in range(60):
            self.client.post(self._send_url(), {"text": "spam"})
        response = self.client.post(self._send_url(), {"text": "one too many"})
        self.assertEqual(response.status_code, 429)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class DownloadViewTests(TestCase):
    def setUp(self):
        self.alice = make_member("alice")
        upload = SimpleUploadedFile("doc.txt", b"contents", content_type="text/plain")
        self.message = Message.objects.create(
            sender=self.alice,
            kind=Message.FILE,
            attachment=upload,
            original_filename="doc.txt",
            content_type="text/plain",
            size=8,
        )

    def test_any_approved_member_can_download(self):
        bob = make_member("bob")
        client = Client()
        login_member(client, bob)
        response = client.get(reverse("chat:download", args=[self.message.pk]))
        self.assertEqual(response.status_code, 200)

    def test_pending_member_is_rejected(self):
        pending = make_member("carol", status=Member.PENDING)
        client = Client()
        login_member(client, pending)
        response = client.get(reverse("chat:download", args=[self.message.pk]))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_403(self):
        response = Client().get(reverse("chat:download", args=[self.message.pk]))
        self.assertEqual(response.status_code, 403)

    def test_missing_attachment_404s(self):
        text_message = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="hi")
        client = Client()
        login_member(client, self.alice)
        response = client.get(reverse("chat:download", args=[text_message.pk]))
        self.assertEqual(response.status_code, 404)


def backdate(message, days_ago):
    target = timezone.now() - timedelta(days=days_ago)
    local_day = timezone.localtime(target).date()
    # local_date has to move in lockstep with created_at here — the app
    # queries local_date directly (see chat/views.py), not created_at, so
    # a raw .update() that only touched created_at would leave the message
    # filed under its original (pre-backdate) day.
    Message.objects.filter(pk=message.pk).update(created_at=target, local_date=local_day)
    return local_day


class DailySummariesTests(TestCase):
    def setUp(self):
        self.alice = make_member("alice")

    def test_excludes_today(self):
        Message.objects.create(sender=self.alice, kind=Message.TEXT, text="hi today")
        from .views import daily_summaries

        self.assertEqual(daily_summaries(), [])

    def test_groups_by_day_with_count_and_most_recent_preview(self):
        from .views import daily_summaries

        m1 = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="first")
        m2 = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="second, this is the latest")
        day = backdate(m1, days_ago=2)
        backdate(m2, days_ago=2)

        summaries = daily_summaries()
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["date"], day)
        self.assertEqual(summaries[0]["count"], 2)
        self.assertIn("latest", summaries[0]["preview"])

    def test_orders_most_recent_day_first(self):
        from .views import daily_summaries

        older = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="older")
        newer = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="newer")
        backdate(older, days_ago=5)
        backdate(newer, days_ago=1)

        summaries = daily_summaries()
        self.assertEqual([s["count"] for s in summaries], [1, 1])
        self.assertGreater(summaries[0]["date"], summaries[1]["date"])


class DayViewTests(TestCase):
    def setUp(self):
        self.alice = make_member("alice")
        self.message = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="yesterday's news")
        self.day = backdate(self.message, days_ago=1)

    def _url(self):
        return reverse("chat:day", args=[self.day.isoformat()])

    def test_anonymous_redirected_to_home(self):
        response = Client().get(self._url())
        self.assertRedirects(response, reverse("identity:home"))

    def test_pending_member_redirected_to_status(self):
        pending = make_member("carol", status=Member.PENDING)
        client = Client()
        login_member(client, pending)
        response = client.get(self._url())
        self.assertRedirects(response, reverse("identity:status"))

    def test_approved_member_sees_that_days_messages(self):
        client = Client()
        login_member(client, self.alice)
        response = client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "yesterday&#x27;s news")

    def test_today_redirects_to_live_room(self):
        today_message = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="today")
        client = Client()
        login_member(client, self.alice)
        today_str = timezone.localdate().isoformat()
        response = client.get(reverse("chat:day", args=[today_str]))
        self.assertRedirects(response, reverse("chat:room"))

    def test_future_date_redirects_to_live_room(self):
        client = Client()
        login_member(client, self.alice)
        future = (timezone.localdate() + timedelta(days=3)).isoformat()
        response = client.get(reverse("chat:day", args=[future]))
        self.assertRedirects(response, reverse("chat:room"))

    def test_day_with_no_messages_404s(self):
        client = Client()
        login_member(client, self.alice)
        empty_day = (timezone.localdate() - timedelta(days=30)).isoformat()
        response = client.get(reverse("chat:day", args=[empty_day]))
        self.assertEqual(response.status_code, 404)

    def test_invalid_date_format_404s(self):
        client = Client()
        login_member(client, self.alice)
        response = client.get(reverse("chat:day", args=["not-a-date"]))
        self.assertEqual(response.status_code, 404)

    def test_only_shows_messages_from_that_day(self):
        # "three days ago" legitimately appears elsewhere on the page (the
        # sidebar's history preview for that other day), so this checks the
        # actual message queryset passed to the template, not raw HTML text.
        other_day_message = Message.objects.create(sender=self.alice, kind=Message.TEXT, text="three days ago")
        backdate(other_day_message, days_ago=3)

        client = Client()
        login_member(client, self.alice)
        response = client.get(self._url())
        self.assertEqual([m.pk for m in response.context["day_messages"]], [self.message.pk])


class MessagePermanenceTests(TestCase):
    """Chat history is permanent by design — see chat/admin.py."""

    def test_staff_cannot_delete_messages_via_admin(self):
        from django.contrib.auth.models import User

        staff = User.objects.create_user(username="staffer", password="x", is_staff=True, is_superuser=True)
        alice = make_member("alice")
        message = Message.objects.create(sender=alice, kind=Message.TEXT, text="permanent")

        client = Client()
        client.force_login(staff)
        response = client.post(
            reverse("admin:chat_message_delete", args=[message.pk]),
            {"post": "yes"},
        )
        # Django admin renders a 403 page rather than performing the
        # deletion when has_delete_permission() is False.
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())

    def test_leaving_never_deletes_a_members_messages(self):
        alice = make_member("alice")
        message = Message.objects.create(sender=alice, kind=Message.TEXT, text="still here")
        alice.delete()
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())
