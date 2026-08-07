from django.conf import settings
from django.utils import timezone

from .models import Member


class MemberMiddleware:
    """
    Resolves request.member from the session (set by identity.views on
    registration). This is the app's entire auth model for ordinary
    members — no passwords, just a session pointer to a Member row. (The
    admin approval role is separate and uses Django's real auth/admin.)

    Two independent throttled "touches" happen here, on different cadences:

    - last_seen is updated at most once per PRESENCE_WINDOW_SECONDS, so the
      room's online-members list is meaningful without writing to MySQL on
      every 3-5s poll request.
    - the rolling session expiry (so an active member's long-lived cookie
      age counts from last use, not from registration) is refreshed at
      most once a day, using a marker stored in the session itself so
      checking it costs no extra query.
    """

    SESSION_TOUCH_MARKER = "_expiry_touched_at"
    SESSION_TOUCH_INTERVAL = 60 * 60 * 24  # 1 day

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.member = None
        member_id = request.session.get("member_id")
        if member_id:
            member = Member.objects.filter(pk=member_id).first()
            if member is None:
                del request.session["member_id"]
            else:
                request.member = member
                self._touch_presence(member)
                self._touch_expiry(request)

        return self.get_response(request)

    def _touch_presence(self, member):
        now = timezone.now()
        if (now - member.last_seen).total_seconds() >= settings.PRESENCE_WINDOW_SECONDS:
            member.last_seen = now
            member.save(update_fields=["last_seen"])

    def _touch_expiry(self, request):
        last_touch = request.session.get(self.SESSION_TOUCH_MARKER)
        now_ts = timezone.now().timestamp()
        if last_touch is None or now_ts - last_touch >= self.SESSION_TOUCH_INTERVAL:
            request.session.set_expiry(settings.SESSION_COOKIE_AGE)
            request.session[self.SESSION_TOUCH_MARKER] = now_ts
