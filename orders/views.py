import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, OuterRef, F, Sum, IntegerField, ExpressionWrapper
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from accounts.models import User
from .decorators import role_required
from .models import Table, Category, Order, OrderItem, MenuItem, KitchenStation
from .utils import print_restaurant_receipt
from . import signals  # noqa: F401  (registers the signal handlers)


# Orders that still belong to a table (not paid, not fully cancelled)
INACTIVE_ORDER_STATUSES = [Order.ORDER_STATUS.BILLED, Order.ORDER_STATUS.CANCELLED]


# ---------------------------------------------------------------
# Waiter
# ---------------------------------------------------------------

@role_required([User.ROLE_CHOICES.WAITER])
def tables_view(request):
    tables = Table.objects.all().order_by("id")
    return render(request, "orders/tables.html", {
        'tables': tables
    })


@role_required([User.ROLE_CHOICES.WAITER])
def menu_view(request, table_id):
    table = get_object_or_404(Table, pk=table_id)

    if request.method == "POST":
        try:
            data = json.loads(request.POST.get("order-items") or "{}")
            items = data.get("items") or []
        except json.JSONDecodeError:
            items = []

        # Keep only valid lines with quantity > 0
        clean_items = []
        for line in items:
            try:
                quantity = int(line.get("quantity", 0))
            except (TypeError, ValueError):
                continue
            menu_item = MenuItem.objects.filter(pk=line.get("item_id")).first()
            if menu_item and quantity > 0:
                clean_items.append((menu_item, quantity))

        if not clean_items:
            messages.warning(request, "Order not placed: please add at least one item.")
            return redirect("menu_view_url", table_id=table.id)

        with transaction.atomic():
            order = Order.objects.create(table=table)
            for menu_item, quantity in clean_items:
                OrderItem.objects.create(
                    order=order,
                    menu_item=menu_item,
                    price=menu_item.price,
                    quantity=quantity,
                    priority=menu_item.default_priority,
                )

        messages.success(request, f"Order placed for {table.name}.")
        return redirect("tables_view_url")

    categories = Category.objects.prefetch_related("items")
    orders = (
        Order.objects
        .filter(table=table)
        .exclude(status__in=INACTIVE_ORDER_STATUSES)
        .prefetch_related("items__menu_item")
        .order_by("-created_at")
    )

    return render(request, "orders/menu.html", {
        'categories': categories,
        'table': table,
        'table_id': table.id,
        'orders': orders,
    })


@role_required([User.ROLE_CHOICES.WAITER])
def tables_status_live(request):
    # Table ids that have at least one item ready to be served
    table_ids = Table.objects.filter(
        Exists(
            OrderItem.objects.filter(
                order__table=OuterRef("pk"),
                status=OrderItem.ITEM_STATUS.READY,
            )
        )
    ).values_list("id", flat=True)

    return JsonResponse({'tables': list(table_ids)})


@role_required([User.ROLE_CHOICES.WAITER])
def served_confirmation(request, order_item_id):
    order_item = get_object_or_404(OrderItem, pk=order_item_id)

    if order_item.status != OrderItem.ITEM_STATUS.READY:
        messages.warning(request, f"{order_item.menu_item.name} is not ready to be served.")
        return redirect("menu_view_url", table_id=order_item.order.table.id)

    if request.method == "POST":
        order_item.status = OrderItem.ITEM_STATUS.SERVED
        order_item.save()
        messages.success(request, f"{order_item.menu_item.name} marked as served.")
        return redirect("menu_view_url", table_id=order_item.order.table.id)

    return render(request, "orders/served-confirmation.html", {
        'order_item': order_item
    })


# ---------------------------------------------------------------
# Kitchen
# ---------------------------------------------------------------

def get_kitchen_items(station_code=None):
    """Items still being prepared, grouped by station name."""
    orderitems = (
        OrderItem.objects
        .filter(status=OrderItem.ITEM_STATUS.PREPARING)
        .select_related("menu_item__station", "order__table")
        .order_by("-priority", "order__created_at")
    )
    if station_code:
        orderitems = orderitems.filter(menu_item__station__code=station_code)

    grouped_items = {}
    for item in orderitems:
        station = item.menu_item.station
        station_name = station.name if station else "Unassigned"
        grouped_items.setdefault(station_name, []).append(item)
    return grouped_items


@role_required([User.ROLE_CHOICES.KITCHEN])
def kitchen_dashboard_view(request):
    station_code = request.GET.get('station_code') or ""

    return render(request, "orders/kitchen_dashboard.html", {
        'order_items': get_kitchen_items(station_code),
        'stations': KitchenStation.objects.all().order_by("name"),
        'station_code': station_code,
    })


@role_required([User.ROLE_CHOICES.KITCHEN])
def kitchen_dashboard_live_view(request):
    # Returns only the station cards, used by the 5-second auto refresh
    station_code = request.GET.get('station_code') or ""
    return render(request, "orders/station-cards.html", {
        'order_items': get_kitchen_items(station_code),
        'station_code': station_code,
    })


@role_required([User.ROLE_CHOICES.KITCHEN])
def kitchen_item_view(request, pk):
    order_item = get_object_or_404(OrderItem, pk=pk)
    station_code = request.GET.get('station_code') or request.POST.get('station_code') or ""

    dashboard_url = reverse("kitchen_dashboard_view_url")
    if station_code:
        dashboard_url = f"{dashboard_url}?{urlencode({'station_code': station_code})}"

    if request.method == "POST":
        if order_item.status != OrderItem.ITEM_STATUS.PREPARING:
            messages.warning(request, f"{order_item.menu_item.name} was already updated.")
            return redirect(dashboard_url)

        action = request.POST.get('status')
        if action == "ready":
            order_item.status = OrderItem.ITEM_STATUS.READY
            messages.success(request, f"{order_item.menu_item.name} marked as ready.")
        elif action == "cancel":
            order_item.status = OrderItem.ITEM_STATUS.CANCELLED
            messages.success(request, f"{order_item.menu_item.name} cancelled.")
        else:
            messages.warning(request, "Unknown action.")
            return redirect(dashboard_url)

        order_item.save()
        return redirect(dashboard_url)

    return render(request, "orders/kitchen_item.html", {
        'order_item': order_item,
        'station_code': station_code,
        'dashboard_url': dashboard_url,
    })


# ---------------------------------------------------------------
# Billing
# ---------------------------------------------------------------

def get_billable_items(table_id):
    """All non-cancelled items of the table's unpaid orders, with line totals."""
    return (
        OrderItem.objects
        .filter(order__table_id=table_id)
        .exclude(order__status__in=INACTIVE_ORDER_STATUSES)
        .exclude(status=OrderItem.ITEM_STATUS.CANCELLED)
        .select_related("menu_item")
        .annotate(
            item_total=ExpressionWrapper(F("quantity") * F("price"), output_field=IntegerField())
        )
    )


@role_required([User.ROLE_CHOICES.BILLING])
def tables_for_billing(request):
    tables = Table.objects.all().order_by("id")
    return render(request, "orders/tables-for-billing.html", {
        'tables': tables
    })


@role_required([User.ROLE_CHOICES.BILLING])
def billing_tables_status_live(request):
    # Tables that have served orders and nothing still in the kitchen -> ready to pay
    active_orders = Order.objects.exclude(status__in=INACTIVE_ORDER_STATUSES)
    served_tables = set(
        active_orders.filter(status=Order.ORDER_STATUS.SERVED).values_list('table', flat=True)
    )
    busy_tables = set(
        active_orders.exclude(status=Order.ORDER_STATUS.SERVED).values_list('table', flat=True)
    )
    return JsonResponse({'tables': list(served_tables - busy_tables)})


@role_required([User.ROLE_CHOICES.BILLING])
def billing_view(request, table_id):
    table = get_object_or_404(Table, pk=table_id)
    order_items = get_billable_items(table.id)
    total = order_items.aggregate(total=Sum("item_total"))["total"] or 0

    # Can only bill when there are items and every one of them has been served
    proceed_billing = (
        order_items.exists()
        and not order_items.exclude(status=OrderItem.ITEM_STATUS.SERVED).exists()
    )

    return render(request, "orders/billing.html", {
        "table": table,
        "items": order_items,
        "total": total,
        "proceed_billing": proceed_billing,
        "table_id": table.id,
    })


@require_POST
@role_required([User.ROLE_CHOICES.BILLING])
def billing_paid_view(request, table_id):
    table = get_object_or_404(Table, pk=table_id)

    with transaction.atomic():
        order_items = list(get_billable_items(table.id))

        if not order_items:
            messages.warning(request, f"{table.name} has nothing to bill.")
            return redirect("tables_for_billing_url")

        if any(item.status != OrderItem.ITEM_STATUS.SERVED for item in order_items):
            messages.warning(request, f"{table.name} still has items that are not served.")
            return redirect("billing_view_url", table_id=table.id)

        # Recalculate the total here so it is always up to date
        total = sum(item.item_total for item in order_items)
        print_data = {
            "table_name": table.name,
            "total": total,
            "items": [
                {"name": item.menu_item.name, "price": item.item_total, "qty": item.quantity}
                for item in order_items
            ],
        }

        # .save() on each order so the signal records the Billed status in history
        orders = Order.objects.filter(table=table).exclude(status__in=INACTIVE_ORDER_STATUSES)
        for order in orders:
            order.status = Order.ORDER_STATUS.BILLED
            order.save()

    messages.success(request, f"{table.name} paid: Rs. {total}.")

    if not print_restaurant_receipt(print_data):
        messages.warning(request, "Receipt printer not reachable, so no receipt was printed.")

    return redirect("tables_for_billing_url")


# ---------------------------------------------------------------
# Public landing page
# ---------------------------------------------------------------

def home_view(request):
    return render(request, "orders/home.html")
