from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile


@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance, created, **kwargs):
    """
    Automatically create a Profile when a new User is created.
    Also ensures profile always exists (safety check).
    """

    if created:
        # Assign role based on user type
        if instance.is_superuser:
            role = 'admin'
        else:
            role = 'student'

        Profile.objects.create(
            user=instance,
            role=role
        )

    else:
        # Safety: ensure profile exists (prevents rare crashes)
        Profile.objects.get_or_create(
            user=instance,
            defaults={'role': 'student'}
        )