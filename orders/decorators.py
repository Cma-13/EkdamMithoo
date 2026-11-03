from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from accounts.models import User
from accounts.utils import get_home_url


def role_required(roles: list):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login_view_url')

            # A superuser can open owner pages even without the owner role
            is_owner_page = User.ROLE_CHOICES.OWNER in roles
            allowed = request.user.role in roles or (is_owner_page and request.user.is_superuser)

            if not allowed:
                # Send the user back to their own dashboard instead of a 403 page
                messages.warning(request, "You don't have access to that page.")
                home_url = get_home_url(request.user)
                if home_url:
                    return redirect(home_url)
                return redirect('logout_view_url')

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
