from django.db import models
from django.utils import timezone

from identity.models import Member

from .utils import attachment_upload_path


class Message(models.Model):
    """
    A single shared room — every approved Member posts into the same
    stream, so there's no Conversation/thread concept to model here.
    """

    TEXT = "text"
    FILE = "file"
    VOICE = "voice"
    KIND_CHOICES = [
        (TEXT, "Text"),
        (FILE, "File"),
        (VOICE, "Voice note"),
    ]

    # SET_NULL, not CASCADE: leaving (identity.views.leave) deletes the
    # Member row so the username becomes reclaimable, but that must not
    # wipe the room's message history out from under everyone else.
    # sender_username is a snapshot taken at send time, so history still
    # shows who said what even after the Member row is long gone.
    sender = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages")
    sender_username = models.CharField(max_length=20, blank=True, default="")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=TEXT)
    text = models.TextField(blank=True)

    attachment = models.FileField(upload_to=attachment_upload_path, blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    # Denormalized copy of created_at's date in the app's local timezone,
    # set in save() below. The live room / history archive both filter and
    # group on this instead of on created_at directly, because a plain
    # DateField needs no timezone conversion to query — created_at__date
    # or TruncDate("created_at") would ask the database to convert UTC to
    # TIME_ZONE itself, and on MySQL that means CONVERT_TZ(), which
    # silently returns NULL (matching nothing, ever) unless the server's
    # named-timezone tables are loaded — something shared hosts (cPanel
    # included) essentially never have, since it requires root access to
    # the MySQL install. Storing the already-localized date sidesteps that
    # dependency entirely, on every backend.
    local_date = models.DateField(db_index=True, editable=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"[{self.kind}] {self.sender_id}#{self.pk}"

    def save(self, *args, **kwargs):
        if self.created_at is None:
            self.created_at = timezone.now()
        self.local_date = timezone.localtime(self.created_at).date()
        super().save(*args, **kwargs)
