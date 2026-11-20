from django.contrib import admin

from .models import (
    Country, Feedback, FieldOfInterest, History, Institute, Profile, Program,
    Recommendation, Scholarship, ScrapeRun, TypeOfDegree,
)


@admin.register(Scholarship)
class ScholarshipAdmin(admin.ModelAdmin):
    list_display = ("title", "university_name", "degree", "country", "source", "is_active", "last_seen_at")
    list_filter = ("is_active", "source", "degree", "country")
    search_fields = ("title", "university_name", "subject", "scholarship_details")
    readonly_fields = ("source", "source_id", "source_url", "attribution", "last_seen_at", "created_at", "updated_at")
    actions = ("mark_active", "mark_inactive")

    @admin.action(description="Show on site")
    def mark_active(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Hide from site")
    def mark_inactive(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(ScrapeRun)
class ScrapeRunAdmin(admin.ModelAdmin):
    list_display = ("source", "started_at", "status", "found", "created", "updated", "deactivated")
    list_filter = ("status", "source")
    readonly_fields = [f.name for f in ScrapeRun._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "highest_qualification", "nationality", "is_verified")
    list_filter = ("is_verified",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("email_token",)


class RecommendationInline(admin.TabularInline):
    model = Recommendation
    extra = 0
    raw_id_fields = ("scholarship",)


@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "profile", "created_at")
    inlines = [RecommendationInline]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("content", "emoji", "profile", "created")


admin.site.register([Country, FieldOfInterest, Institute, Program, TypeOfDegree])
