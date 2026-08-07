from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect

from .models import Member


def member_required(view_func):
    """Any registered member, regardless of approval status — used by the
    pending/rejected status pages themselves."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.member:
            return redirect("identity:home")
        return view_func(request, *args, **kwargs)

    return wrapped


def approved_required(view_func):
    """For the chat room and other approved-only HTML pages. Pending/
    rejected members are bounced to their status page instead of the room —
    checked fresh on every request, so a later admin approval or revocation
    takes effect on the member's very next request, no extra plumbing."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.member:
            return redirect("identity:home")
        if request.member.status != Member.APPROVED:
            return redirect("identity:status")
        return view_func(request, *args, **kwargs)

    return wrapped


def api_approved_required(view_func):
    """For JSON/polling endpoints: a redirect would break fetch() callers,
    so respond with 403 JSON instead — the frontend treats this as "you're
    not able to use the room right now, stop polling and reload"."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.member or request.member.status != Member.APPROVED:
            return JsonResponse({"error": "not_approved"}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapped
