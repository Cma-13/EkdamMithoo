from django.urls import reverse
from .models import User


def get_home_url(user):
    """Return the dashboard URL for a logged-in user based on their role.
    Returns None if the user has no usable role."""
    role = user.role

    if role == User.ROLE_CHOICES.WAITER:
        return reverse("tables_view_url")
    if role == User.ROLE_CHOICES.KITCHEN:
        return reverse("kitchen_dashboard_view_url")
    if role == User.ROLE_CHOICES.BILLING:
        return reverse("tables_for_billing_url")
    if role == User.ROLE_CHOICES.OWNER or user.is_superuser:
        return reverse("owner_dashboard_url")

    return None
