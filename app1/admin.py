from django.contrib import admin

from .models import (
    Country, Feedback, FieldOfInterest, History, Institute, Profile, Program,
    JobRun, Recommendation, SavedScholarship, Scholarship, ScrapeRun, TypeOfDegree,
)


@admin.register(Scholarship)
class ScholarshipAdmin(admin.ModelAdmin):
    list_display = ("title", "university_name", "degree", "country", "deadline", "source", "is_active")
    list_filter = ("is_active", "source", "degree", "country")
    search_fields = ("title", "university_name", "subject", "scholarship_details")
    readonly_fields = ("source", "source_id", "source_url", "attribution", "last_seen_at", "created_at", "updated_at",
                       "deadline", "deadline_estimated")
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
    list_display = ("__str__", "profile", "input_type", "target_degree", "created_at")
    list_filter = ("input_type",)
    inlines = [RecommendationInline]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("content", "emoji", "profile", "created", "is_approved")
    list_filter = ("is_approved",)
    list_editable = ("is_approved",)
    actions = ("approve",)

    @admin.action(description="Approve (show on home page)")
    def approve(self, request, queryset):
        queryset.update(is_approved=True)


admin.site.register([Country, FieldOfInterest, Institute, Program, TypeOfDegree])


@admin.register(SavedScholarship)
class SavedScholarshipAdmin(admin.ModelAdmin):
    list_display = ("profile", "scholarship", "status", "updated_at", "reminded_14_for", "reminded_3_for")
    list_filter = ("status",)
    raw_id_fields = ("profile", "scholarship")


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    list_display = ("job", "run_date", "status", "started_at", "finished_at")
    list_filter = ("job", "status")
    readonly_fields = [f.name for f in JobRun._meta.fields]

    def has_add_permission(self, request):
        return False
