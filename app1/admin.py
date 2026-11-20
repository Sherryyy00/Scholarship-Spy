from django.contrib import admin

from .models import (
    Country, Feedback, FieldOfInterest, History, Institute, Profile, Program,
    Recommendation, Scholarship, TypeOfDegree,
)


@admin.register(Scholarship)
class ScholarshipAdmin(admin.ModelAdmin):
    list_display = ("title", "university_name", "degree", "country", "apply_date")
    list_filter = ("degree", "country")
    search_fields = ("title", "university_name", "subject", "scholarship_details")


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
