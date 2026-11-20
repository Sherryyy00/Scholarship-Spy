import logging
import uuid

from django.contrib.auth.models import User
from django.db import models
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

PROFILE_PHOTO_MAX = (300, 300)


def new_token():
    return uuid.uuid4().hex


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    email_reminders = models.BooleanField(default=True, help_text="Email me before saved scholarships close")
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    highest_qualification = models.CharField(max_length=100, blank=True, default="")
    cgpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True, default="")
    photo = models.ImageField(default="default.jpg", upload_to="profile_pics")
    email_token = models.CharField(max_length=64, default=new_token, unique=True, editable=False)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username}'s profile"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._shrink_photo()

    def _shrink_photo(self):
        """Keep uploaded profile photos small. Never let a bad image break a save."""
        if not self.photo or self.photo.name == "default.jpg":
            return
        try:
            with Image.open(self.photo.path) as img:
                if img.height > PROFILE_PHOTO_MAX[1] or img.width > PROFILE_PHOTO_MAX[0]:
                    img.thumbnail(PROFILE_PHOTO_MAX)
                    img.save(self.photo.path)
        except (FileNotFoundError, UnidentifiedImageError, ValueError, OSError):
            logger.warning("Could not resize profile photo for %s", self.user_id)


class History(models.Model):
    """One recommendation request: a personal statement, a CV, or both."""

    INPUT_STATEMENT = "statement"
    INPUT_CV = "cv"
    INPUT_BOTH = "both"
    INPUT_CHOICES = [(INPUT_STATEMENT, "Personal statement"), (INPUT_CV, "CV"), (INPUT_BOTH, "Statement and CV")]

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    # The statement as typed. For CV-only requests this is empty.
    personal_statement = models.TextField(blank=True, default="")
    # Cleaned text extracted from an uploaded CV. The file itself is never stored.
    cv_text = models.TextField(blank=True, default="")
    cv_filename = models.CharField(max_length=255, blank=True, default="")
    input_type = models.CharField(max_length=10, choices=INPUT_CHOICES, default=INPUT_STATEMENT)
    target_degree = models.CharField(max_length=20, blank=True, default="")
    target_country = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name_plural = "histories"

    def __str__(self):
        return self.summary

    @property
    def summary(self):
        """Short label for lists: the start of the statement, or the CV file name."""
        if self.personal_statement:
            text = self.personal_statement
            return text if len(text) <= 80 else text[:77].rsplit(" ", 1)[0] + "…"
        return f"CV: {self.cv_filename}" if self.cv_filename else "Recommendation"

    @property
    def query_text(self):
        return " ".join(t for t in (self.personal_statement, self.cv_text) if t)

    @property
    def top_scholarships(self):
        """Recommended scholarships for this statement, best match first."""
        return Scholarship.objects.filter(recommendation__history=self).order_by("recommendation__rank")


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "countries"

    def __str__(self):
        return self.name


class ActiveScholarshipManager(models.Manager):
    """Only listings that are still live at their source. Used by the public site and the recommender."""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Scholarship(models.Model):
    # Where a listing came from. "manual" = admin, "csv" = file import, anything else = a scraper name.
    SOURCE_MANUAL = "manual"
    SOURCE_CSV = "csv"

    title = models.CharField(max_length=300)
    link = models.URLField(max_length=500, blank=True, default="")
    image_link = models.URLField(max_length=500, blank=True, default="")
    university_name = models.CharField(max_length=200, blank=True, default="")
    tution_structure = models.CharField("tuition structure", max_length=100, blank=True, default="")
    degree = models.CharField(max_length=100, blank=True, default="", db_index=True)
    subject = models.CharField(max_length=200, blank=True, default="", db_index=True)
    eligibility = models.CharField(max_length=200, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="", db_index=True)
    apply_date = models.CharField(max_length=200, blank=True, default="")
    # Parsed from apply_date on save (see deadlines.py). "estimated" = no year was given.
    deadline = models.DateField(null=True, blank=True, db_index=True)
    deadline_estimated = models.BooleanField(default=False)
    scholarship_details = models.TextField(blank=True, default="")
    history = models.ManyToManyField(History, through="Recommendation", blank=True)

    # Provenance and freshness
    source = models.CharField(max_length=50, default=SOURCE_MANUAL, db_index=True)
    source_id = models.CharField(max_length=300, blank=True, default="", help_text="Stable ID of the listing at its source")
    source_url = models.URLField(max_length=500, blank=True, default="", help_text="Page the listing was collected from")
    attribution = models.CharField(max_length=300, blank=True, default="")
    last_seen_at = models.DateTimeField(null=True, blank=True, help_text="Last time a scraper found this listing")
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # First manager is the default (used by admin and imports), so it sees everything.
    all_objects = models.Manager()
    objects = ActiveScholarshipManager()

    class Meta:
        ordering = ("title",)
        base_manager_name = "all_objects"
        default_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(fields=["title", "link"], name="unique_scholarship_title_link"),
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=~models.Q(source_id=""),
                name="unique_scholarship_source_id",
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from .deadlines import parse_deadline

        parsed, estimated = parse_deadline(self.apply_date)
        if parsed or not self.deadline or self._apply_date_changed():
            self.deadline, self.deadline_estimated = parsed, estimated
        super().save(*args, **kwargs)

    def _apply_date_changed(self):
        if not self.pk:
            return True
        old = Scholarship.all_objects.filter(pk=self.pk).values_list("apply_date", flat=True).first()
        return old != self.apply_date

    @property
    def days_left(self):
        from .deadlines import days_left
        return days_left(self.deadline)

    @property
    def is_closed(self):
        return self.deadline is not None and self.days_left < 0

    def search_text(self):
        """Text the recommender indexes. Title and subject are repeated to weight them higher."""
        parts = [
            self.title, self.title,
            self.subject, self.subject,
            self.degree, self.country, self.university_name,
            self.eligibility, self.scholarship_details,
        ]
        return " ".join(p for p in parts if p)


class ScrapeRun(models.Model):
    """One run of one scraper, so you can see in the admin what was collected and when."""

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(s, s.title()) for s in (STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILED)]

    source = models.CharField(max_length=50, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    found = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    deactivated = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return f"{self.source} @ {self.started_at:%Y-%m-%d %H:%M} ({self.status})"


class SavedScholarship(models.Model):
    """A scholarship a user has bookmarked, and where they are with their application."""

    INTERESTED = "interested"
    PREPARING = "preparing"
    APPLIED = "applied"
    INTERVIEW = "interview"
    SUCCESSFUL = "successful"
    UNSUCCESSFUL = "unsuccessful"
    STATUS_CHOICES = [
        (INTERESTED, "Interested"),
        (PREPARING, "Preparing"),
        (APPLIED, "Applied"),
        (INTERVIEW, "Interview"),
        (SUCCESSFUL, "Successful"),
        (UNSUCCESSFUL, "Unsuccessful"),
    ]
    # Reminders only make sense before you've applied.
    REMIND_STATUSES = (INTERESTED, PREPARING)

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="saved")
    scholarship = models.ForeignKey(Scholarship, on_delete=models.CASCADE, related_name="saved_by")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=INTERESTED, db_index=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Which deadline each reminder was sent for, so a new year's deadline gets fresh reminders.
    reminded_14_for = models.DateField(null=True, blank=True)
    reminded_3_for = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("scholarship__deadline", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=["profile", "scholarship"], name="unique_saved_scholarship"),
        ]

    def __str__(self):
        return f"{self.profile.user.username}: {self.scholarship.title} ({self.status})"


class Recommendation(models.Model):
    """A scholarship recommended for a statement, with its rank and similarity score."""

    history = models.ForeignKey(History, on_delete=models.CASCADE)
    scholarship = models.ForeignKey(Scholarship, on_delete=models.CASCADE)
    rank = models.PositiveSmallIntegerField()
    score = models.FloatField()
    # A few words the statement/CV and the scholarship have in common, to explain the match.
    matched_terms = models.CharField(max_length=200, blank=True, default="")

    @property
    def matched_terms_list(self):
        return [t for t in self.matched_terms.split("|") if t]

    class Meta:
        ordering = ("history", "rank")
        constraints = [
            models.UniqueConstraint(fields=["history", "scholarship"], name="unique_recommendation"),
        ]


class Program(models.Model):
    name = models.CharField(max_length=300)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TypeOfDegree(models.Model):
    name = models.CharField(max_length=300)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name


class FieldOfInterest(models.Model):
    """Rows with no profile are site-wide subjects; rows with a profile are a user's interests."""

    name = models.CharField(max_length=300)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name


class Feedback(models.Model):
    content = models.CharField(max_length=500)
    emoji = models.CharField(max_length=100, blank=True, default="")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    # Only approved feedback is shown publicly on the home page. Approve it in the admin.
    is_approved = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("-created",)

    def __str__(self):
        return self.content


class Institute(models.Model):
    name = models.CharField(max_length=300)
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name


class JobRun(models.Model):
    """One run of a scheduled job. The (job, run_date) pair is unique, which is what stops
    a daily job running twice, even when several web workers each run a scheduler."""

    RUNNING, SUCCESS, FAILED = "running", "success", "failed"

    job = models.CharField(max_length=50)
    run_date = models.DateField()
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, default=RUNNING)
    output = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-started_at",)
        constraints = [models.UniqueConstraint(fields=["job", "run_date"], name="unique_job_per_day")]

    def __str__(self):
        return f"{self.job} {self.run_date} ({self.status})"
