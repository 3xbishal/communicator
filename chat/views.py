from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import Count, Max
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from identity.decorators import api_approved_required, approved_required
from identity.models import Member, RateLimitHit

from .models import Message
from .utils import avatar_color
from .validators import validate_attachment

MESSAGE_PAGE_SIZE = 50
POLL_PAGE_SIZE = 200
HISTORY_DAY_LIMIT = 30

SEND_LIMIT = 60
SEND_WINDOW_SECONDS = 5 * 60


def serialize_message(message, viewer):
    data = {
        "id": message.pk,
        "kind": message.kind,
        "text": message.text,
        "mine": message.sender_id == viewer.pk,
        "sender": message.sender_username,
        "color": avatar_color(message.sender_username),
        "created_at": message.created_at.isoformat(),
    }
    if message.attachment:
        data["attachment_url"] = reverse("chat:download", args=[message.pk])
        data["original_filename"] = message.original_filename
        data["content_type"] = message.content_type
        data["size"] = message.size
    return data


def online_members(viewer):
    members = Member.objects.filter(status=Member.APPROVED).order_by("username")
    return [
        {
            "username": m.username,
            "online": m.is_online(settings.PRESENCE_WINDOW_SECONDS),
            "mine": m.pk == viewer.pk,
            "color": avatar_color(m.username),
        }
        for m in members
    ]


def _preview_text(message):
    if message is None:
        return ""
    if message.kind == Message.TEXT:
        return message.text[:80]
    if message.kind == Message.VOICE:
        return "\U0001f399️ Voice note"
    return f"\U0001f4ce {message.original_filename or 'File'}"


def daily_summaries(limit=HISTORY_DAY_LIMIT):
    """
    Past days that have at least one message, most recent first, each with
    a message count and a preview of the last message — one aggregate
    query plus one small follow-up fetch for the previews, not N+1.
    Today is deliberately excluded: that's what the live room already is.

    Grouped by the stored local_date column (see Message.save()), not by
    TruncDate("created_at") — the latter asks the database to convert UTC
    to TIME_ZONE itself, which on MySQL requires CONVERT_TZ() and silently
    matches nothing if the server's named-timezone tables aren't loaded (the
    default on most shared hosting, cPanel included).
    """
    today = timezone.localdate()
    rows = list(
        Message.objects.exclude(local_date=today)
        .values("local_date")
        .annotate(count=Count("id"), last_id=Max("id"))
        .order_by("-local_date")[:limit]
    )
    previews = {
        m.pk: m
        for m in Message.objects.filter(pk__in=[r["last_id"] for r in rows])
    }
    return [
        {
            "date": row["local_date"],
            "count": row["count"],
            "preview": _preview_text(previews.get(row["last_id"])),
        }
        for row in rows
    ]


@approved_required
def room(request):
    me = request.member
    # Live room is scoped to today only — anything older lives exclusively
    # in the day archive (see daily_summaries()/day_view below), so this
    # view never mixes yesterday's tail-end messages into a fresh load.
    # Filtered on local_date, not created_at__date — see Message.save().
    recent = list(
        Message.objects.filter(local_date=timezone.localdate()).order_by("-id")[:MESSAGE_PAGE_SIZE]
    )
    recent.reverse()

    return render(
        request,
        "chat/room.html",
        {
            "messages_json": [serialize_message(m, me) for m in recent],
            "last_id": recent[-1].id if recent else 0,
            "members": online_members(me),
            "history": daily_summaries(),
            "active_date": None,
            "today": timezone.localdate().isoformat(),
        },
    )


@approved_required
def day_view(request, date_str):
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404

    if day >= timezone.localdate():
        return redirect("chat:room")

    messages = list(
        Message.objects.filter(local_date=day).order_by("id")
    )
    if not messages:
        raise Http404

    return render(
        request,
        "chat/day.html",
        {
            "day": day,
            "day_messages": messages,
            "members": online_members(request.member),
            "history": daily_summaries(),
            "active_date": day,
        },
    )


@api_approved_required
@require_GET
def messages_poll(request):
    me = request.member
    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        after = 0

    # Same day scoping as room() — if this poll straddles midnight (a tab
    # left open overnight), yesterday's tail simply stops being fetched;
    # today's new messages still come through normally since "today" is
    # recomputed fresh on every request.
    today = timezone.localdate()
    new_messages = list(
        Message.objects.filter(id__gt=after, local_date=today)
        .order_by("id")[:POLL_PAGE_SIZE]
    )

    return JsonResponse(
        {
            "messages": [serialize_message(m, me) for m in new_messages],
            "members": online_members(me),
            # Lets a page left open across midnight notice the day rolled
            # over (poll-room.js compares this against the date it loaded
            # with) and reload into a clean new live chat, instead of
            # silently appending today's messages under yesterday's still
            # on screen.
            "today": today.isoformat(),
        }
    )


@api_approved_required
@require_POST
def send_message(request):
    me = request.member

    if not RateLimitHit.allow(f"send:{me.pk}", SEND_LIMIT, SEND_WINDOW_SECONDS):
        return JsonResponse({"error": "rate_limited"}, status=429)

    text = request.POST.get("text", "").strip()
    uploaded = request.FILES.get("attachment")
    requested_kind = request.POST.get("kind", "")

    if not text and not uploaded:
        return JsonResponse({"error": "empty"}, status=400)

    message = Message(sender=me, sender_username=me.username)

    if uploaded:
        try:
            validate_attachment(uploaded)
        except ValidationError as exc:
            return JsonResponse({"error": str(exc.message)}, status=400)
        message.attachment = uploaded
        message.original_filename = uploaded.name[:255]
        message.content_type = (uploaded.content_type or "")[:100]
        message.size = uploaded.size
        message.kind = Message.VOICE if requested_kind == "voice" else Message.FILE
        message.text = text
    else:
        message.kind = Message.TEXT
        message.text = text

    message.save()

    return JsonResponse(serialize_message(message, me), status=201)


@api_approved_required
@require_GET
def download(request, message_id):
    message = get_object_or_404(Message, pk=message_id)
    if not message.attachment:
        raise Http404

    file_handle = default_storage.open(message.attachment.name, "rb")
    response = FileResponse(
        file_handle,
        content_type=message.content_type or "application/octet-stream",
        filename=message.original_filename or "file",
    )
    response["Cache-Control"] = "private, max-age=86400"
    return response
