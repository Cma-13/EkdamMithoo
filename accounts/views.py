from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .utils import get_home_url


def login_view(request):
    # Already logged in -> go straight to the right dashboard
    if request.user.is_authenticated:
        home_url = get_home_url(request.user)
        if home_url:
            return redirect(home_url)

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember-me')

        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, 'Wrong username or password.')
            return redirect('login_view_url')

        home_url = get_home_url(user)
        if home_url is None:
            messages.error(request, 'Your account has no role assigned. Please contact the owner.')
            return redirect('login_view_url')

        login(request, user)
        if remember_me is None:
            # Session ends when the browser is closed
            request.session.set_expiry(0)

        return redirect(home_url)

    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    return redirect('login_view_url')
