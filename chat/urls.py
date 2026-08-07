from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.room, name="room"),
    path("day/<str:date_str>/", views.day_view, name="day"),
    path("messages/", views.messages_poll, name="messages_poll"),
    path("send/", views.send_message, name="send"),
    path("attachment/<int:message_id>/", views.download, name="download"),
]
