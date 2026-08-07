from django.contrib import admin

from .models import Member, RateLimitHit

admin.site.site_header = "Communicator Admin"
admin.site.site_title = "Communicator Admin"
admin.site.index_title = "Site administration"


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("username", "status", "created_at", "last_seen")
    list_editable = ("status",)  # change status right from the row — no need to open a member first
    list_filter = ("status",)
    search_fields = ("username",)
    actions = ["approve_members", "reject_members"]

    @admin.action(description="Approve selected members")
    def approve_members(self, request, queryset):
        updated = queryset.update(status=Member.APPROVED)
        self.message_user(request, f"Approved {updated} member(s).")

    @admin.action(description="Reject selected members")
    def reject_members(self, request, queryset):
        updated = queryset.update(status=Member.REJECTED)
        self.message_user(request, f"Rejected {updated} member(s).")


@admin.register(RateLimitHit)
class RateLimitHitAdmin(admin.ModelAdmin):
    list_display = ("key", "created_at")
    search_fields = ("key",)
