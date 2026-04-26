from django.core.management.base import BaseCommand
from accounts.models import Profile

class Command(BaseCommand):
    help = 'Initialize wallet balance for students'

    def handle(self, *args, **kwargs):
        for profile in Profile.objects.all():
            if profile.account_balance == 0:
                profile.account_balance = 5000
                profile.save()
        self.stdout.write(self.style.SUCCESS('Wallets initialized!'))