from datetime import timedelta

from django.db import models
from django.utils import timezone


class Member(models.Model):
    """
    A chat participant: just a username, no password. Anyone can register
    one, but new members sit in PENDING until an admin approves them via
    Django admin (see identity/admin.py) — that approval step is the only
    gatekeeping this app has, since there's no password to protect an
    account otherwise.

    Identity is session-based (see identity/middleware.py), same as a
    logged-in cookie: whichever browser registered a username is the only
    one that can act as it again later. There is deliberately no recovery
    mechanism (no secret key) — losing the session means registering a new
    username.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending approval"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    username = models.CharField(max_length=20, unique=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

    @property
    def is_approved(self):
        return self.status == self.APPROVED

    def is_online(self, window_seconds):
        return timezone.now() - self.last_seen <= timedelta(seconds=window_seconds)


class RateLimitHit(models.Model):
    """
    Minimal DB-backed rate limiter. Django's cache framework defaults to
    per-process LocMemCache, which doesn't work for throttling across
    Passenger's multiple worker processes (and there's no Redis/memcached
    on shared cPanel hosting) — a handful of rows in the real database is
    cheap and correct across process boundaries instead.
    """

    key = models.CharField(max_length=100, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @classmethod
    def allow(cls, key, limit, window_seconds):
        """Records a hit and returns True if under the limit, False if the
        caller should be throttled. Opportunistically prunes old rows for
        this key so the table doesn't grow unbounded between cron runs."""
        cutoff = timezone.now() - timedelta(seconds=window_seconds)
        cls.objects.filter(key=key, created_at__lt=cutoff).delete()
        if cls.objects.filter(key=key).count() >= limit:
            return False
        cls.objects.create(key=key)
        return True
