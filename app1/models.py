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
    """One personal statement a user asked recommendations for."""

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    personal_statement = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name_plural = "histories"

    def __str__(self):
        return self.personal_statement[:50]

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


class Scholarship(models.Model):
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
    scholarship_details = models.TextField(blank=True, default="")
    history = models.ManyToManyField(History, through="Recommendation", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(fields=["title", "link"], name="unique_scholarship_title_link"),
        ]

    def __str__(self):
        return self.title

    def search_text(self):
        """Text the recommender indexes. Title and subject are repeated to weight them higher."""
        parts = [
            self.title, self.title,
            self.subject, self.subject,
            self.degree, self.country, self.university_name,
            self.eligibility, self.scholarship_details,
        ]
        return " ".join(p for p in parts if p)


class Recommendation(models.Model):
    """A scholarship recommended for a statement, with its rank and similarity score."""

    history = models.ForeignKey(History, on_delete=models.CASCADE)
    scholarship = models.ForeignKey(Scholarship, on_delete=models.CASCADE)
    rank = models.PositiveSmallIntegerField()
    score = models.FloatField()

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
