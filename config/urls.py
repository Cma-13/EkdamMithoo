from django.contrib import admin
from django.urls import path, include
from orders.views import home_view


urlpatterns = [
    path('', home_view, name='home_view'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('orders/', include('orders.urls')),
]
