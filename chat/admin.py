from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "sender_username", "kind", "created_at")
    list_filter = ("kind",)
    search_fields = ("sender_username", "text")

    def has_delete_permission(self, request, obj=None):
        # Chat history is permanent by design — nothing in the app itself
        # ever deletes a Message (identity.views.leave sets sender to NULL
        # rather than cascading), and this closes the one remaining path:
        # Django admin's default delete button/bulk action for staff.
        return False
