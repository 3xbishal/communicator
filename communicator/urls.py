from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("chat/", include("chat.urls")),
    path("", include("identity.urls")),
]

if settings.DEBUG:
    # Local dev only: MEDIA_ROOT is normally served exclusively through
    # chat.views.download (which checks the requester is a participant).
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
