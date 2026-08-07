import uuid
from pathlib import Path


def attachment_upload_path(instance, filename):
    """
    Randomized storage path — the original filename is never trusted as a
    path component (kept only in Message.original_filename for display).
    """
    ext = Path(filename).suffix.lower()
    return f"attachments/{uuid.uuid4().hex}{ext}"


# A single source of truth for "which color is this username" — used by
# serialize_message()/online_members() (so the live-polled JS just reads
# msg.color) and by the avatar_color template filter (so server-rendered
# archive pages match exactly, no separate hashing logic to keep in sync).
AVATAR_COLORS = [
    "#ef4444", "#f97316", "#eab308", "#22c55e",
    "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899",
]


def avatar_color(username):
    if not username:
        return AVATAR_COLORS[0]
    return AVATAR_COLORS[sum(ord(c) for c in username) % len(AVATAR_COLORS)]
