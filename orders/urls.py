from django.urls import path
from . import views

urlpatterns = [
    # Waiter
    path("tables/", views.tables_view, name="tables_view_url"),
    path("tables/live/", views.tables_status_live, name="tables_status_live_url"),
    path("menu/<int:table_id>/", views.menu_view, name="menu_view_url"),
    path("order/<int:order_item_id>/served-confirmation/", views.served_confirmation, name="served_confirmation_url"),

    # Kitchen
    path("kitchen/dashboard/", views.kitchen_dashboard_view, name="kitchen_dashboard_view_url"),
    path("kitchen/live/", views.kitchen_dashboard_live_view, name="kitchen_dashboard_view_live_url"),
    path("kitchen/items/<int:pk>/", views.kitchen_item_view, name="kitchen_item_view_url"),

    # Billing
    path("billing/tables/", views.tables_for_billing, name="tables_for_billing_url"),
    path("billing/tables/live/", views.billing_tables_status_live, name="billing_tables_status_live_url"),
    path("billing/<int:table_id>/paid/", views.billing_paid_view, name="billing_paid_view_url"),
    path("billing/<int:table_id>/", views.billing_view, name="billing_view_url"),
    path("billing/bills/today/", views.todays_bills_view, name="todays_bills_url"),
    path("bills/<int:pk>/", views.bill_detail_view, name="bill_detail_url"),
    path("bills/<int:pk>/reprint/", views.bill_reprint_view, name="bill_reprint_url"),

    # Owner
    path("owner/dashboard/", views.owner_dashboard_view, name="owner_dashboard_url"),
    path("owner/bills/", views.owner_bills_view, name="owner_bills_url"),
    path("owner/reservations/", views.owner_reservations_view, name="owner_reservations_url"),
    path("owner/reservations/<int:pk>/status/", views.reservation_status_view, name="reservation_status_url"),
]
