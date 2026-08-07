import re

from django import forms

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,19}$")


class RegisterForm(forms.Form):
    """
    Only validates format here — whether the username already exists, and
    what to do about it (block, or let an approved member rejoin), depends
    on that existing member's status and is handled in the view, not here.
    """

    username = forms.CharField(
        label="Username",
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control form-control-lg", "autofocus": True, "autocomplete": "off"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if not USERNAME_RE.match(username):
            raise forms.ValidationError(
                "3-20 characters: lowercase letters, numbers, underscores. Must start with a letter."
            )
        return username
