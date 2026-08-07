"""
Entrypoint cPanel's Passenger app server looks for. Configure this file as
the "Application startup file" in cPanel's Setup Python App UI.

Passenger sets up its own virtualenv and adds this file's directory to
sys.path, so this only needs to point Django at its settings and hand back
the standard WSGI callable.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "communicator.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
