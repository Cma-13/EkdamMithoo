from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from orders.views import home_view, reservation_create_view


urlpatterns = [
    path('', home_view, name='home_view'),
    path('book/', reservation_create_view, name='reservation_create_url'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('orders/', include('orders.urls')),
]

# Serve uploaded menu photos while developing
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
