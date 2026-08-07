from django import template
from django.utils.html import format_html

from chat.utils import avatar_color as _avatar_color

register = template.Library()


@register.filter
def avatar_color(username):
    return _avatar_color(username)


@register.filter
def initial(username):
    return (username or "?")[0].upper()


# Maps short semantic names used in templates to Font Awesome 6 Free
# classes, so templates say {% icon "check" %} rather than hard-coding
# "fa-solid fa-check" everywhere — one place to change if an icon needs
# swapping later.
_ICON_CLASSES = {
    "check": "fa-solid fa-check",
    "x": "fa-solid fa-xmark",
    "x-circle": "fa-solid fa-circle-xmark",
    "trash": "fa-solid fa-trash",
    "send": "fa-solid fa-paper-plane",
    "paperclip": "fa-solid fa-paperclip",
    "mic": "fa-solid fa-microphone",
    "arrow-left": "fa-solid fa-arrow-left",
    "log-out": "fa-solid fa-right-from-bracket",
    "users": "fa-solid fa-users",
    "clock": "fa-solid fa-clock",
    "user-plus": "fa-solid fa-user-plus",
    "shield-check": "fa-solid fa-shield-halved",
    "inbox": "fa-solid fa-inbox",
    "sparkles": "fa-solid fa-comments",
}


@register.simple_tag
def icon(name, css_class=""):
    fa_class = _ICON_CLASSES.get(name)
    if not fa_class:
        return ""
    classes = f"{fa_class} {css_class}".strip()
    return format_html('<i class="{}" aria-hidden="true"></i>', classes)
