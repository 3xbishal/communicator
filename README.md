# Communicator

A group chat app with no self-serve signup: anyone can request a username,
but an admin has to approve them in Django's admin before they can post.
Once approved, everyone shares a single room — text, file sharing, and
voice notes. Built to run on ordinary shared cPanel hosting (no
WebSockets, no Redis, no background daemons — real-time updates are
short-interval polling against the database).

## How it works, briefly

- **Membership**: you pick a username (no password, no email). That
  creates a *pending* member and signs you into it for this browser. An
  admin approves or rejects pending usernames from the **Approvals**
  dashboard (`/staff/approvals/`) or Django admin. The page you're waiting
  on polls quietly and jumps to the room the moment you're approved — no
  manual refreshing needed.
- **The room**: one shared space. Every approved member sees the same
  message stream and the same "who's online" sidebar. There's no DM/thread
  concept — this app is intentionally single-room.
- **Messages**: text, file attachments, and voice notes (recorded in the
  browser via the mic button) are all just different kinds of the same
  `Message` model, rendered inline in the stream.
- **Day archives**: today's conversation lives at `/chat/` and updates
  live. Past days show up in the sidebar's History list (date, message
  count, last-message preview) and open as a read-only page at
  `/chat/day/2026-08-05/` — no polling on those, they're static history.
- **Deployment target**: shared cPanel hosting via Passenger ("Setup Python
  App"), MySQL, WhiteNoise for static files, and a plain Django view (not
  raw Apache) for serving uploaded attachments so downloads stay gated to
  approved members only.
- **Frontend**: Bootstrap 5, Font Awesome, and jQuery, all loaded from
  CDN (jsDelivr / cdnjs / code.jquery.com) with SRI integrity hashes pinned
  in `templates/base.html`. This is a deliberate choice for a
  polished, properly responsive UI — it does mean visitors' *browsers* need
  to reach those CDNs (the Python server itself needs no outbound access
  for this; CDN requests happen client-side). If you ever need the app to
  work somewhere with no outbound internet at all, those three `<link>`/
  `<script>` tags are the only things that would need to be swapped for
  self-hosted copies under `static/`.

## Local development

```
python -m venv venv
venv\Scripts\activate            # source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env           # cp .env.example .env
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py runserver
```

`.env` defaults to SQLite and `DEBUG=True`, so that's all you need to run
locally. `collectstatic` is required even locally once `DEBUG=False` is
ever set, because static files are served through WhiteNoise's
manifest-hashing storage — see "Static files" below.

`createsuperuser` creates *your* login for `/admin/` — that's the only
password-protected account in the app, and the only way to approve new
members. Everyone else just registers a username.

To test against real MySQL before deploying (recommended at least once, to
catch charset/constraint issues early — see below), set `USE_MYSQL=1` and
the `DB_*` variables in `.env`.

Run the test suite:

```
python manage.py test
```

## Approving members

**Day to day, use the Approvals dashboard** at `/staff/approvals/` (also
linked in the top nav whenever you're logged in as staff): pending
usernames show up as cards with one-click **Approve** / **Reject**
buttons, and a "Recent decisions" list underneath for context. It's gated
by the same real login as Django admin (`staff_member_required` — visiting
it while logged out sends you to `/admin/login/`), just a friendlier
surface for the one thing you'll do constantly.

**For anything else** (deleting a member, searching, bulk actions across
many at once), Django admin at `/admin/` → **Identity → Members** still
has the full picture, including the same "Approve selected members" /
"Reject selected members" actions in its Actions dropdown.

Either way, approval/rejection is checked fresh on every request the
member makes, so it takes effect immediately — no restart needed, and you
can revoke someone later by changing their status back.

## Deploying to cPanel

### 1. Check the Python version cPanel offers

In cPanel, open **Setup Python App** and look at the version dropdown
first, before anything else. This project targets **Django 5.2 LTS, which
needs Python 3.10+**. Many cPanel hosts (CloudLinux's "Python Selector")
offer 3.10–3.12+. If your host only offers something older, ask them to
enable a newer interpreter before falling back to an older Django — Django
4.2 LTS works down to Python 3.8, but by mid-2026 it is already outside (or
right at the edge of) its own upstream security support window, so treat
that path as "get this working now, upgrade soon," not a stable long-term
choice. If you do need it, change `Django>=5.2,<5.3` in `requirements.txt`
to `Django>=4.2,<4.3` and re-run the test suite.

### 2. Upload the code and create the Python app

1. Upload this project to a directory outside `public_html` if your plan
   allows it (e.g. `~/communicator_app`), or into a subdirectory if not.
   cPanel's Passenger integration serves it at whatever "Application URL"
   you assign regardless of where the folder lives.
2. In **Setup Python App**, create an application:
   - Python version: as decided in step 1.
   - Application root: the folder you uploaded to.
   - Application URL: your domain (or subdomain).
   - Application startup file: `passenger_wsgi.py`
   - Application Entry point: `application`
3. cPanel creates a virtualenv and gives you an "Enter to the virtual
   environment" command. Use it (or the terminal it provides) to install
   dependencies:
   ```
   pip install -r requirements.txt
   ```
4. If available, ask for **multiple threads per process** in the Python
   App config (Passenger supports multithreading for Python apps on most
   cPanel builds). Every request here is short and DB-bound (a poll, a
   send, a small file), so threads buy real concurrency even from a single
   worker process — useful since shared plans often cap you to one process.

### 3. Create the MySQL database

In cPanel's **MySQL Databases** tool:

1. Create a database and a user, and add the user to the database with
   **all privileges**. cPanel prefixes both with your cPanel username,
   e.g. database `communicator` + user `myuser` become
   `myuser_communicator` / `myuser_myuser` (or similar — cPanel shows you
   the exact prefixed names).
2. **Set the database to use `utf8mb4`**, not the legacy 3-byte `utf8`
   some cPanel wizards still default to — plain `utf8` will silently
   corrupt or drop emoji in chat messages. If your MySQL/phpMyAdmin
   defaults the database's collation to something else, change it to
   `utf8mb4_unicode_ci` after creation.

### 4. Configure environment variables

In **Setup Python App**, use the "Environment variables" section rather
than shipping a `.env` file to the server (`.env` is a local-dev
convenience; `load_dotenv()` never overrides a real environment variable,
so setting things here always wins). Set, at minimum:

| Variable | Value |
|---|---|
| `SECRET_KEY` | generate once, see below — then treat as permanent |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `yourdomain.com,www.yourdomain.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://yourdomain.com` (scheme required) |
| `USE_MYSQL` | `1` |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | from step 3 |
| `DB_HOST` | usually `localhost` |

Generate `SECRET_KEY` once with:

```
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

**Treat it as a durable value — back it up, don't casually rotate it.** It
signs both session cookies and CSRF tokens. Since ordinary members have no
password, a member's session cookie *is* their login; rotating
`SECRET_KEY` signs everyone out simultaneously, and since there's no
recovery flow, that means every member re-registering a username and
waiting to be re-approved.

Full list of recognized variables, with defaults, is in `.env.example`.

### 5. Run migrations, collect static files, and create your admin login

Using the same "enter virtualenv" terminal from step 2:

```
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

`collectstatic` is not optional here: static files are served via
WhiteNoise's `CompressedManifestStaticFilesStorage`, which requires a
pre-built manifest (`static_collected/staticfiles.json`) any time
`DEBUG=False` — without it, every page fails with `Missing staticfiles
manifest entry`. Re-run `collectstatic` after any future CSS/JS change and
every deploy. `createsuperuser` is what lets you log into `/admin/` to
approve members — do this before inviting anyone.

### 6. Restart the app

Use the "Restart" button in Setup Python App after any code, dependency, or
environment variable change — Passenger caches the running process and
won't pick up changes otherwise.

### 7. Optional: cron jobs

Add in cPanel's **Cron Jobs**, using the "Enter to the virtual environment"
command shown in Setup Python App as a prefix (or its full path):

- **Daily**: `python manage.py clearsessions` — prunes expired session
  rows. Sessions are long-lived (see below) so this matters more than it
  would with Django's usual 2-week default.

## Design notes specific to shared hosting

These are the constraints that shaped the architecture — useful context if
you're extending this later:

- **No WebSockets, no Redis, no Celery.** Real-time is 3–4s polling
  against small, indexed queries (`identity/middleware.py`,
  `static/js/poll-room.js`, `static/js/status-poll.js`). The poller backs
  off exponentially on errors and pauses entirely when the browser tab is
  hidden, to keep request volume low under Passenger's typically small
  process/thread budget.
- **PyMySQL instead of `mysqlclient`** (`communicator/__init__.py`) —
  shared hosts often lack a C compiler to build `mysqlclient`'s extension;
  PyMySQL is pure Python. The shim is installed at the `communicator`
  package level (not in `passenger_wsgi.py`) specifically so `manage.py
  migrate`/`collectstatic`/`shell` all work from a plain terminal too.
- **Rate limiting is DB-backed** (`identity.models.RateLimitHit`), not
  Django's cache framework — `LocMemCache` (the default) is per-process and
  gives no protection once Passenger runs more than one worker. It guards
  both registration attempts and message sends.
- **Attachments are served through an authenticated Django view**
  (`chat.views.download`), not raw Apache static serving. A file sitting
  under a public static folder is reachable by anyone with the URL, with no
  way to gate it to approved members only. `media/.htaccess` additionally
  disables script execution and directory listing in `MEDIA_ROOT` as
  defense in depth, in case it's ever reachable from a web-executable path
  anyway.
- **Two separate auth systems, deliberately.** Ordinary members use a
  lightweight session-based identity with no password
  (`identity.middleware.MemberMiddleware`) — approval is the only
  gatekeeping. The one sensitive role, approving members, uses Django's
  real `django.contrib.auth` + `/admin/` (the Approvals dashboard at
  `/staff/approvals/` reuses that exact login via
  `staff_member_required`), which is real password auth. They don't share
  a login.
- **Day archives are one aggregate query, not N+1.** `chat.views.
  daily_summaries()` groups messages by calendar day with a single
  `TruncDate` + `Count`/`Max` aggregation, then fetches just the preview
  messages in one follow-up query — so the sidebar's history list stays
  cheap no matter how many days of history accumulate. Archived days are
  plain server-rendered HTML (no polling JS at all), since history doesn't
  change.
- **Chat history is permanent — nothing in the app deletes a Message,
  ever.** When someone leaves (`identity.views.leave` deletes their
  `Member` row so the username is reclaimable), `Message.sender` is
  `SET_NULL` rather than `CASCADE`, and a `sender_username` snapshot taken
  at send time keeps their messages correctly attributed in the room and
  in the day archives even after their account is long gone. The one
  remaining place a message *could* have been deleted — Django admin's
  default delete button/bulk action — is explicitly turned off
  (`MessageAdmin.has_delete_permission` returns `False`). Member accounts
  can still be removed (by leaving, or by an admin); what they said
  can't be.

## Known limitations (by design, for this MVP)

- **One room only** — no channels, no DMs.
- **Approved usernames are unauthenticated handles, not protected
  accounts.** Once a username is approved, typing it on the join screen
  from *any* browser attaches that session to it instantly — no password,
  no verification, unlimited times. This is a deliberate tradeoff (no
  signup friction, matching the "just type a name" brief) but it means
  anyone who knows or guesses an approved username can act as that person
  in the room. If you need real per-person protection instead, that means
  putting a password (or something equivalent) back on approved members,
  which is a real design change, not a config toggle — worth a conscious
  decision, not something to bolt on quietly. Pending/rejected usernames
  still can't be reused by someone else while unresolved.
- **Losing a *pending* registration's session still needs an admin.**
  Only approved usernames get the instant-rejoin above. If you register
  and lose your session before being approved (or after being rejected),
  self-service `identity:leave` isn't reachable — an admin has to free the
  username from the Approvals dashboard (`/staff/approvals/` → Remove).
- **Approval is permanent once granted.** `identity.views.leave` is
  status-aware: for an approved member it only clears the session (the
  `Member` row, and its `status=approved`, are untouched) — signing out
  and typing your username again later never requires re-approval. It's
  only pending/rejected members (who never had an established identity)
  that `leave` deletes outright, which is what frees *their* username for
  a fresh attempt. The nav button reflects this: it reads "Sign out" for
  approved members and "Leave" for anyone else.
- **No moderation beyond initial approval** — an admin can revoke a
  member's access (set them back to pending/rejected in Django admin), but
  there's no per-message delete/mute from within the app itself yet.
- **No real audio/video calling** — voice notes are recorded clips posted
  like any other message, not a live call. True calling would need WebRTC
  and a TURN server, which needs a VPS, not shared cPanel hosting.
