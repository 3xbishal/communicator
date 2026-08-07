"""
Django settings for the Communicator project.

Everything environment-specific is read from environment variables so the
exact same codebase runs locally (SQLite, DEBUG on) and on cPanel shared
hosting (MySQL, DEBUG off) without code changes. See .env.example for the
full list of variables and README.md for the cPanel deployment walkthrough.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# On cPanel, prefer setting environment variables directly in the "Setup
# Python App" UI. The .env file is a convenience for local development and
# for hosts where only file-based config is practical; load_dotenv() never
# overrides a variable that's already set in the real environment.
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core -------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-local-dev-only-change-me")

# Treat SECRET_KEY as durable once deployed: it signs session cookies and
# CSRF tokens, so rotating it logs out every member at once — since there's
# no password to log back in with, that means everyone re-registering a
# username and waiting for re-approval. Generate it once, back it up, don't
# casually rotate it.

DEBUG = env_bool("DEBUG", default=True)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

# Required by Django >=4 for any cross-origin POST (including same-site
# POSTs behind some reverse proxies) — must include scheme, e.g.
# "https://example.com". Empty by default so local dev needs no setup.
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")


# --- Applications -------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "identity",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "identity.middleware.MemberMiddleware",
]

ROOT_URLCONF = "communicator.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "communicator.wsgi.application"


# --- Database -------------------------------------------------------------
#
# Local dev defaults to SQLite (zero setup). Set USE_MYSQL=1 (and the DB_*
# vars) to run against MySQL, which you should do at least once before
# deploying to catch charset/constraint quirks early — see README.md.

if env_bool("USE_MYSQL", default=False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
            # Reuse connections across requests instead of reopening a fresh
            # MySQL TCP connection on every poll. Keep this well under the
            # hosting plan's max_user_connections limit (Passenger process
            # count x threads per process) — see README.md.
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- I18N -------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# --- Static & media files ----------------------------------------------
#
# Static assets (CSS/JS) are served by WhiteNoise straight out of the WSGI
# process after `collectstatic` — no Apache static-alias config needed.
#
# Media (user uploads) is deliberately NOT served directly by Apache: a
# file sitting under a static folder is reachable by anyone who has/guesses
# the URL, with no way to gate it to approved members only. Instead
# chat.views.download streams attachments after checking the requester is
# an approved member. MEDIA_ROOT lives outside any web-served static folder.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static_collected"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"  # not exposed by any URLconf; downloads go through chat.views.download
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Uploads --------------------------------------------------------------

# Shared hosts commonly cap request body size around 8-32MB at the Apache
# layer independent of these Django settings — check your cPanel plan and
# keep this at or below it.
MAX_ATTACHMENT_BYTES = int(os.environ.get("MAX_ATTACHMENT_BYTES", 15 * 1024 * 1024))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_ATTACHMENT_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # spill to disk above this instead of buffering in RAM

# Extensions that must never be accepted, even renamed on disk with a
# random UUID name, as defense in depth in case a future deployment ever
# serves MEDIA_ROOT directly from a web-executable location.
BLOCKED_UPLOAD_EXTENSIONS = {
    ".php", ".php3", ".php4", ".php5", ".phtml", ".pl", ".py", ".pyc", ".cgi",
    ".asp", ".aspx", ".sh", ".exe", ".dll", ".jsp", ".htaccess",
}


# --- Sessions & security ---------------------------------------------------
#
# Ordinary member identity is entirely session-based (see
# identity/middleware.py) — no django.contrib.auth user accounts for chat
# members (django.contrib.auth is still used, separately, for the admin who
# approves them at /admin/). A long cookie age means a member stays
# recognized indefinitely once approved; MemberMiddleware rolls the expiry
# forward for active members without writing to the DB on every request.

SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", 60 * 60 * 24 * 730))  # ~2 years
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_SAVE_EVERY_REQUEST = False

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if not DEBUG else None

# Left off (0) by default even in production: enabling HSTS is only safe
# once you've confirmed every path on the domain reliably serves over
# HTTPS (cPanel AutoSSL, no lingering HTTP-only subdomains) — turning it on
# prematurely can lock out visitors for the full duration. Opt in via env
# once that's confirmed, e.g. SECURE_HSTS_SECONDS=31536000.
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 0))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)

# How fresh `Member.last_seen` must be to show as "online" in the UI, and
# how often MemberMiddleware is willing to write a fresher value. Keeping
# these equal caps writes to ~once per this interval per active member,
# which is trivial load even on a modest shared MySQL plan.
PRESENCE_WINDOW_SECONDS = int(os.environ.get("PRESENCE_WINDOW_SECONDS", 45))


LOGIN_URL = "identity:home"

# Django's "error" message level doesn't match any Bootstrap alert class —
# map it to "danger" so templates can use alert-{{ message.tags }} directly
# instead of a lookup table in every template.
from django.contrib.messages import constants as _message_constants  # noqa: E402

MESSAGE_TAGS = {
    _message_constants.ERROR: "danger",
}
