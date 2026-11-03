import json
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.db import transaction
from django.db.models import Avg, Count, Exists, OuterRef, F, Prefetch, Sum, IntegerField, ExpressionWrapper
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from accounts.models import User
from .decorators import role_required
from .forms import ReservationForm
from .models import Bill, Reservation, Table, Category, Order, OrderItem, MenuItem, KitchenStation
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
    # Same rule as the bill page: the table has unpaid items and every one is served
    unpaid_items = (
        OrderItem.objects
        .exclude(order__status__in=INACTIVE_ORDER_STATUSES)
        .exclude(status=OrderItem.ITEM_STATUS.CANCELLED)
    )
    tables_with_items = set(unpaid_items.values_list("order__table", flat=True))
    tables_still_waiting = set(
        unpaid_items.exclude(status=OrderItem.ITEM_STATUS.SERVED).values_list("order__table", flat=True)
    )
    return JsonResponse({'tables': sorted(tables_with_items - tables_still_waiting)})


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
        "payment_methods": [
            (value, label, Bill.PAYMENT_LOGOS.get(value))
            for value, label in Bill.PAYMENT_METHOD.choices
        ],
        "proceed_billing": proceed_billing,
        "table_id": table.id,
    })


def build_receipt_data(bill):
    """Collect everything the printer needs from a saved bill."""
    items = (
        OrderItem.objects
        .filter(order__bill=bill)
        .exclude(status=OrderItem.ITEM_STATUS.CANCELLED)
        .select_related("menu_item")
    )
    return {
        "bill_number": bill.bill_number,
        "table_name": bill.table.name,
        "date": timezone.localtime(bill.created_at).strftime("%Y-%m-%d %I:%M %p"),
        "payment_method": bill.get_payment_method_display(),
        "items": [
            {"name": item.menu_item.name, "price": item.price * item.quantity, "qty": item.quantity}
            for item in items
        ],
        "total": bill.total,
    }


@require_POST
@role_required([User.ROLE_CHOICES.BILLING])
def billing_paid_view(request, table_id):
    table = get_object_or_404(Table, pk=table_id)

    payment_method = request.POST.get("payment_method")
    if payment_method not in Bill.PAYMENT_METHOD.values:
        messages.warning(request, "Please choose a payment method.")
        return redirect("billing_view_url", table_id=table.id)

    with transaction.atomic():
        order_items = list(get_billable_items(table.id))

        if not order_items:
            messages.warning(request, f"{table.name} has nothing to bill.")
            return redirect("tables_for_billing_url")

        if any(item.status != OrderItem.ITEM_STATUS.SERVED for item in order_items):
            messages.warning(request, f"{table.name} still has items that are not served.")
            return redirect("billing_view_url", table_id=table.id)

        # Recalculate here so the saved total is always up to date
        bill = Bill.objects.create(
            table=table,
            total=sum(item.item_total for item in order_items),
            payment_method=payment_method,
            billed_by=request.user,
        )

        # .save() on each order so the signal records the Billed status in history
        orders = Order.objects.filter(table=table).exclude(status__in=INACTIVE_ORDER_STATUSES)
        for order in orders:
            order.status = Order.ORDER_STATUS.BILLED
            order.bill = bill
            order.save()

    messages.success(request, f"{table.name} paid: Rs. {bill.total:,.2f} ({bill.get_payment_method_display()}).")

    if not print_restaurant_receipt(build_receipt_data(bill)):
        messages.warning(request, "Receipt printer not reachable, so no receipt was printed.")

    return redirect("bill_detail_url", pk=bill.pk)


@role_required([User.ROLE_CHOICES.BILLING, User.ROLE_CHOICES.OWNER])
def bill_detail_view(request, pk):
    bill = get_object_or_404(Bill.objects.select_related("table", "billed_by"), pk=pk)
    items = (
        OrderItem.objects
        .filter(order__bill=bill)
        .select_related("menu_item")
        .annotate(
            item_total=ExpressionWrapper(F("quantity") * F("price"), output_field=IntegerField())
        )
    )
    return render(request, "orders/bill-detail.html", {
        "bill": bill,
        "items": items,
    })


@require_POST
@role_required([User.ROLE_CHOICES.BILLING, User.ROLE_CHOICES.OWNER])
def bill_reprint_view(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    if print_restaurant_receipt(build_receipt_data(bill)):
        messages.success(request, f"Receipt for {bill.bill_number} sent to the printer.")
    else:
        messages.warning(request, "Receipt printer not reachable, so no receipt was printed.")
    return redirect("bill_detail_url", pk=bill.pk)


@role_required([User.ROLE_CHOICES.BILLING])
def todays_bills_view(request):
    bills = (
        Bill.objects
        .filter(created_at__date=timezone.localdate())
        .select_related("table", "billed_by")
    )
    return render(request, "orders/todays-bills.html", {
        "bills": bills,
        "total": bills.aggregate(total=Sum("total"))["total"] or 0,
    })


# ---------------------------------------------------------------
# Owner
# ---------------------------------------------------------------

OWNER_RANGES = {
    "today": ("Today", 1),
    "7d": ("Last 7 days", 7),
    "30d": ("Last 30 days", 30),
}


@role_required([User.ROLE_CHOICES.OWNER])
def owner_dashboard_view(request):
    range_key = request.GET.get("range", "today")
    if range_key not in OWNER_RANGES:
        range_key = "today"
    range_label, days = OWNER_RANGES[range_key]

    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)

    bills = Bill.objects.filter(created_at__date__gte=start_date)
    summary = bills.aggregate(revenue=Sum("total"), count=Count("id"), average=Avg("total"))

    # Items that were actually sold (served and paid) in this period
    sold_items = OrderItem.objects.filter(
        order__bill__in=bills, status=OrderItem.ITEM_STATUS.SERVED
    )
    items_sold = sold_items.aggregate(qty=Sum("quantity"))["qty"] or 0
    top_items = (
        sold_items
        .values("menu_item__name")
        .annotate(
            qty=Sum("quantity"),
            revenue=Sum(ExpressionWrapper(F("quantity") * F("price"), output_field=IntegerField())),
        )
        .order_by("-qty", "-revenue")[:5]
    )

    cancelled_items = OrderItem.objects.filter(
        status=OrderItem.ITEM_STATUS.CANCELLED,
        order__created_at__date__gte=start_date,
    ).aggregate(qty=Sum("quantity"))["qty"] or 0

    # Revenue split by payment method
    by_method_raw = dict(
        bills.values_list("payment_method").annotate(total=Sum("total")).values_list("payment_method", "total")
    )
    revenue = summary["revenue"] or 0
    payment_split = []
    for value, label in Bill.PAYMENT_METHOD.choices:
        amount = by_method_raw.get(value) or 0
        percent = round(amount / revenue * 100) if revenue else 0
        payment_split.append({"label": label, "amount": amount, "percent": percent})

    # Daily revenue for the chart (always at least the last 7 days)
    chart_days = max(days, 7)
    chart_start = today - timedelta(days=chart_days - 1)
    daily_raw = dict(
        Bill.objects
        .filter(created_at__date__gte=chart_start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("total"))
        .values_list("day", "total")
    )
    daily = [
        {"day": chart_start + timedelta(days=i), "total": daily_raw.get(chart_start + timedelta(days=i)) or 0}
        for i in range(chart_days)
    ]
    max_daily = max((d["total"] for d in daily), default=0)
    for d in daily:
        d["percent"] = round(d["total"] / max_daily * 100) if max_daily else 0

    # What is happening right now
    active_tables = (
        Order.objects.exclude(status__in=INACTIVE_ORDER_STATUSES).values("table").distinct().count()
    )
    in_kitchen = OrderItem.objects.filter(status=OrderItem.ITEM_STATUS.PREPARING).count()
    todays_bookings = Reservation.objects.filter(date=today).exclude(status=Reservation.STATUS.CANCELLED)
    pending_bookings = Reservation.objects.filter(date__gte=today, status=Reservation.STATUS.PENDING).count()

    return render(request, "orders/owner-dashboard.html", {
        "range_key": range_key,
        "range_label": range_label,
        "ranges": [(key, label) for key, (label, _) in OWNER_RANGES.items()],
        "revenue": revenue,
        "bill_count": summary["count"] or 0,
        "average_bill": summary["average"] or 0,
        "items_sold": items_sold,
        "cancelled_items": cancelled_items,
        "top_items": top_items,
        "payment_split": payment_split,
        "daily": daily,
        "active_tables": active_tables,
        "total_tables": Table.objects.count(),
        "in_kitchen": in_kitchen,
        "todays_bookings": todays_bookings.count(),
        "todays_guests": todays_bookings.aggregate(total=Sum("guests"))["total"] or 0,
        "pending_bookings": pending_bookings,
        "recent_bills": bills.select_related("table", "billed_by")[:10],
    })


def safe_parse_date(value):
    """'2026-11-03' -> date, anything empty or invalid -> None."""
    try:
        return parse_date(value or "")
    except ValueError:
        return None


@role_required([User.ROLE_CHOICES.OWNER])
def owner_bills_view(request):
    bills = Bill.objects.select_related("table", "billed_by")

    date_from = safe_parse_date(request.GET.get("from"))
    date_to = safe_parse_date(request.GET.get("to"))
    method = request.GET.get("method") or ""
    if date_from:
        bills = bills.filter(created_at__date__gte=date_from)
    if date_to:
        bills = bills.filter(created_at__date__lte=date_to)
    if method in Bill.PAYMENT_METHOD.values:
        bills = bills.filter(payment_method=method)

    return render(request, "orders/owner-bills.html", {
        "bills": bills[:200],
        "total": bills.aggregate(total=Sum("total"))["total"] or 0,
        "count": bills.count(),
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "method": method,
        "payment_methods": Bill.PAYMENT_METHOD.choices,
    })


# ---------------------------------------------------------------
# Owner: reservations
# ---------------------------------------------------------------

RESERVATION_TABS = {
    "upcoming": "Upcoming",
    "today": "Today",
    "past": "Past",
}


@role_required([User.ROLE_CHOICES.OWNER])
def owner_reservations_view(request):
    tab = request.GET.get("tab", "upcoming")
    if tab not in RESERVATION_TABS:
        tab = "upcoming"

    today = timezone.localdate()
    reservations = Reservation.objects.all()
    if tab == "today":
        reservations = reservations.filter(date=today)
    elif tab == "upcoming":
        reservations = reservations.filter(date__gte=today).exclude(
            status__in=[Reservation.STATUS.CANCELLED, Reservation.STATUS.ARRIVED]
        )
    else:
        reservations = reservations.filter(date__lt=today).order_by("-date", "-time")

    return render(request, "orders/owner-reservations.html", {
        "tab": tab,
        "tabs": RESERVATION_TABS.items(),
        "reservations": reservations[:200],
        "pending_count": Reservation.objects.filter(
            date__gte=today, status=Reservation.STATUS.PENDING
        ).count(),
    })


@require_POST
@role_required([User.ROLE_CHOICES.OWNER])
def reservation_status_view(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    new_status = request.POST.get("status")
    if new_status not in Reservation.STATUS.values:
        messages.warning(request, "Unknown action.")
    else:
        reservation.status = new_status
        reservation.save(update_fields=["status"])
        messages.success(request, f"Booking for {reservation.name} marked as {reservation.get_status_display().lower()}.")

    tab = request.POST.get("tab") or "upcoming"
    return redirect(f"{reverse('owner_reservations_url')}?{urlencode({'tab': tab})}")


# ---------------------------------------------------------------
# Public website
# ---------------------------------------------------------------

# Website hero photo: put your own photo at static/orders/images/website-hero.jpg.
# Until that file exists, the thali photo is used.
HERO_IMAGE = "orders/images/website-hero.jpg"
HERO_FALLBACK = "orders/images/thali set.jpg"


def render_home(request, form, status=200):
    categories = Category.objects.prefetch_related(
        Prefetch("items", queryset=MenuItem.objects.order_by("price", "name"))
    ).filter(items__isnull=False).distinct().order_by("id")

    return render(request, "orders/home.html", {
        "featured_items": MenuItem.objects.filter(is_featured=True).select_related("category")[:3],
        "categories": categories,
        "form": form,
        "booked": request.GET.get("booked") == "1",
        "hero_image": HERO_IMAGE if finders.find(HERO_IMAGE) else HERO_FALLBACK,
    }, status=status)


def home_view(request):
    return render_home(request, ReservationForm())


@require_POST
def reservation_create_view(request):
    form = ReservationForm(request.POST)
    if form.is_valid():
        form.save()
        return redirect(f"{reverse('home_view')}?booked=1#book")
    # Show the page again with the errors next to the fields
    return render_home(request, form, status=400)
