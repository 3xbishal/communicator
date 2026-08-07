from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_attachment(uploaded_file):
    ext = Path(uploaded_file.name).suffix.lower()
    if ext in settings.BLOCKED_UPLOAD_EXTENSIONS:
        raise ValidationError(f"Files of type {ext} aren't allowed.")
    if uploaded_file.size > settings.MAX_ATTACHMENT_BYTES:
        limit_mb = settings.MAX_ATTACHMENT_BYTES / (1024 * 1024)
        raise ValidationError(f"File is too large (limit {limit_mb:.0f} MB).")
