from django.core.management.base import BaseCommand

from accounts.models import User

# One login per role, so the whole flow can be tried quickly
DEMO_STAFF = [
    {"username": "waiter", "first_name": "Demo", "last_name": "Waiter", "role": User.ROLE_CHOICES.WAITER},
    {"username": "kitchen", "first_name": "Demo", "last_name": "Kitchen", "role": User.ROLE_CHOICES.KITCHEN},
    {"username": "billing", "first_name": "Demo", "last_name": "Cashier", "role": User.ROLE_CHOICES.BILLING},
    # Owner gets staff status so the "Manage Menu & Staff" (Django admin) link works
    {"username": "owner", "first_name": "Demo", "last_name": "Owner", "role": User.ROLE_CHOICES.OWNER, "is_staff": True},
]


class Command(BaseCommand):
    help = "Create one demo login for each role (waiter, kitchen, billing, owner)"

    def add_arguments(self, parser):
        parser.add_argument("--password", default="demo12345", help="Password for all demo users")

    def handle(self, *args, **options):
        for data in DEMO_STAFF:
            user, created = User.objects.get_or_create(username=data["username"], defaults=data)
            if created:
                user.set_password(options["password"])
                user.save()
                self.stdout.write(f"Created {user.username} ({user.get_role_display()})")
            else:
                self.stdout.write(f"Skipped {user.username}: already exists")

        self.stdout.write(self.style.SUCCESS(f"Done. Password for new users: {options['password']}"))
