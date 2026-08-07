from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import RegisterForm
from .models import Member, RateLimitHit

RECENT_DECISIONS_LIMIT = 20

REGISTER_LIMIT = 10
REGISTER_WINDOW_SECONDS = 10 * 60


def _client_key(request):
    return request.META.get("REMOTE_ADDR", "unknown")


def home(request):
    if request.member:
        if request.member.status == Member.APPROVED:
            return redirect("chat:room")
        return redirect("identity:status")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            existing = Member.objects.filter(username=username).first()

            if existing and existing.status != Member.APPROVED:
                # Pending/rejected is someone else's unresolved request —
                # still blocked, since there's nothing sensible to "rejoin".
                form.add_error(None, "That username is already taken.")
            elif not RateLimitHit.allow(f"register:{_client_key(request)}", REGISTER_LIMIT, REGISTER_WINDOW_SECONDS):
                form.add_error(None, "Too many attempts. Please wait a few minutes and try again.")
            elif existing:
                # Approved usernames can be rejoined any time, unlimited —
                # there's no password to verify "is this really the same
                # person", so once approved a username behaves like a
                # public room handle, not a protected account. This is a
                # deliberate tradeoff for a no-signup app, not an oversight.
                request.session["member_id"] = existing.pk
                return redirect("chat:room")
            else:
                member = Member.objects.create(username=username)
                request.session["member_id"] = member.pk
                return redirect("identity:status")
    else:
        form = RegisterForm()

    return render(request, "identity/home.html", {"form": form})


def status(request):
    if not request.member:
        return redirect("identity:home")
    if request.member.status == Member.APPROVED:
        return redirect("chat:room")
    template = "identity/rejected.html" if request.member.status == Member.REJECTED else "identity/pending.html"
    return render(request, template)


@require_GET
def status_poll(request):
    if not request.member:
        return JsonResponse({"error": "no_member"}, status=403)
    return JsonResponse({"status": request.member.status})


@require_POST
def leave(request):
    """
    Approval is permanent once granted: an approved member just gets
    signed out of this browser (session cleared, Member row untouched) —
    they rejoin instantly later by typing their username again (see
    home()), no re-approval involved.

    Pending/rejected members have no established identity worth keeping,
    so for them this deletes the Member row outright, freeing the
    username for a fresh attempt — by them or anyone else. There's no
    password to verify "is this really the same person coming back", so a
    freed username is genuinely up for grabs, same as before anyone
    claimed it. Either way, chat.Message.sender is SET_NULL with a
    sender_username snapshot, so nothing that member said is ever affected.
    """
    member = request.member
    was_approved = bool(member and member.status == Member.APPROVED)

    if member and not was_approved:
        member.delete()
    request.session.flush()

    if was_approved:
        messages.info(request, "Signed out. Your approval is permanent — type your username again any time to jump right back in.")
    else:
        messages.info(request, "You've left — that username is free again. Register any time to rejoin.")
    return redirect("identity:home")


@staff_member_required
def staff_approvals(request):
    """
    A friendlier, one-click alternative to Django admin's changelist +
    bulk-action dance for the one thing this app needs done constantly:
    approving new members. Gated by the same real staff login as /admin/
    (staff_member_required redirects anonymous/non-staff visitors to
    /admin/login/) — no separate auth system for this.
    """
    pending = Member.objects.filter(status=Member.PENDING).order_by("created_at")
    recent_decisions = (
        Member.objects.exclude(status=Member.PENDING).order_by("-created_at")[:RECENT_DECISIONS_LIMIT]
    )
    return render(
        request,
        "identity/staff_approvals.html",
        {
            "pending": pending,
            "recent_decisions": recent_decisions,
            "approved_count": Member.objects.filter(status=Member.APPROVED).count(),
            "total_count": Member.objects.count(),
        },
    )


@staff_member_required
@require_POST
def staff_approve(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    member.status = Member.APPROVED
    member.save(update_fields=["status"])
    messages.success(request, f"Approved {member.username}.")
    return redirect("identity:staff_approvals")


@staff_member_required
@require_POST
def staff_reject(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    member.status = Member.REJECTED
    member.save(update_fields=["status"])
    messages.info(request, f"Rejected {member.username}.")
    return redirect("identity:staff_approvals")


@staff_member_required
@require_POST
def staff_remove_member(request, member_id):
    """
    Frees a username outright, regardless of status. This is the recovery
    path for the case identity.views.leave can't handle: someone whose
    session for that member is gone (lost cookies, different browser, or
    they just never came back) has no way to reach their own Leave button,
    so their username stays stuck forever with nobody able to reclaim it.
    An admin doing it here is the only way out. Their chat messages are
    unaffected — see chat.Message.sender_username / the note in leave().
    """
    member = get_object_or_404(Member, pk=member_id)
    username = member.username
    member.delete()
    messages.success(request, f"Removed {username} — that username is free again.")
    return redirect("identity:staff_approvals")
