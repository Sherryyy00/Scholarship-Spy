from django.contrib.auth.models import User
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import recommender
from .models import Profile, Scholarship


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver([post_save, post_delete], sender=Scholarship)
def refresh_recommender(sender, **kwargs):
    recommender.invalidate()
