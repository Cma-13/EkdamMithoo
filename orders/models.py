from decimal import Decimal, ROUND_HALF_UP
import uuid

from django.conf import settings
from django.db import models

class Table(models.Model):
    name = models.CharField(max_length=20)
    is_reserved = models.BooleanField(default=False, null=True)
    
    def __str__(self):
        return self.name

    @property
    def status(self):
        """'occupied' if the table has an active (not billed/cancelled) order,
        'reserved' if marked reserved, otherwise 'free'."""
        has_active_order = self.orders.exclude(
            status__in=[Order.ORDER_STATUS.BILLED, Order.ORDER_STATUS.CANCELLED]
        ).exists()
        if has_active_order:
            return 'occupied'
        if self.is_reserved:
            return 'reserved'
        return 'free'

    def get_status_display(self):
        return self.status.capitalize()
    
class Category(models.Model):
    name = models.CharField(max_length=150)
    
    class Meta:
        verbose_name_plural = 'Categories'
    
    def __str__(self):
        return self.name
 
class KitchenStation(models.Model):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    
    
    def __str__(self):
        return self.name   
    
    
class MenuItem(models.Model):
    
    class PRIORITY_CHOICES(models.TextChoices):
        HIGH = '3', 'High'
        MEDIUM = '2', 'Medium'
        LOW = '1', 'Low'
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')  
    name = models.CharField(max_length=200)
    price = models.PositiveIntegerField()
    description = models.TextField(null = True, blank = True)  
    default_priority = models.CharField(choices=PRIORITY_CHOICES, default=PRIORITY_CHOICES.MEDIUM, max_length=2)
    est_time = models.PositiveIntegerField(help_text="Write estimated preparation time in minutes", null=True, blank=True)
    station = models.ForeignKey(KitchenStation, on_delete=models.SET_NULL, null=True, related_name='items')
    
    def __str__(self):
        return self.name


class Bill(models.Model):
    """A saved payment for one table visit (can cover several orders)."""

    class PAYMENT_METHOD(models.TextChoices):
        CASH = 'cash', 'Cash'
        ESEWA = 'esewa', 'eSewa'
        KHALTI = 'khalti', 'Khalti'
        CARD = 'card', 'Card'

    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name='bills')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD, default=PAYMENT_METHOD.CASH)
    billed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='bills'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.bill_number} - {self.table} - Rs. {self.total}"

    @property
    def bill_number(self):
        return f"B-{self.pk:05d}" if self.pk else "B-NEW"

    @staticmethod
    def calculate(subtotal):
        """Return subtotal, service charge, VAT and total as Decimals.
        Service charge is on the subtotal, VAT is on subtotal + service charge
        (the usual way restaurants in Nepal bill)."""
        two_places = Decimal('0.01')
        subtotal = Decimal(subtotal).quantize(two_places)
        service_charge = (subtotal * Decimal(settings.SERVICE_CHARGE_PERCENT) / 100).quantize(two_places, ROUND_HALF_UP)
        vat = ((subtotal + service_charge) * Decimal(settings.VAT_PERCENT) / 100).quantize(two_places, ROUND_HALF_UP)
        return {
            'subtotal': subtotal,
            'service_charge': service_charge,
            'vat': vat,
            'total': subtotal + service_charge + vat,
        }


class Order(models.Model):
    class ORDER_STATUS(models.TextChoices):
        PENDING = 'p', 'Pending'
        PARTIALLY_SERVED = 'ps', 'Partially Served'
        SERVED = 's', 'Served'
        BILLED = 'b', 'Billed'
        CANCELLED = 'c', 'Cancelled'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=2, choices=ORDER_STATUS, default=ORDER_STATUS.PENDING)
    created_at =  models.DateTimeField(auto_now_add=True)
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, null=True, blank=True, related_name='orders')
    
    def __str__(self):
        return f"{self.table} -> {self.created_at}"
    
class OrderItem(models.Model):
    class ITEM_STATUS(models.TextChoices):
        PREPARING = 'p', 'Preparing'
        READY = 'r', 'Ready'
        SERVED = 's', 'Served'
        CANCELLED = 'c', 'Cancelled'
    
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name='order_items')
    price = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(choices=ITEM_STATUS, max_length=2, default=ITEM_STATUS.PREPARING)
    priority = models.CharField(choices= MenuItem.PRIORITY_CHOICES, default=MenuItem.PRIORITY_CHOICES.MEDIUM, max_length=2)
    

    
    def __str__(self):
        return f"{self.menu_item} × {self.quantity}"
    
    
class OrderHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='histories')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(choices=Order.ORDER_STATUS)
    
    class Meta:
        verbose_name_plural = 'Order Histories'
    def __str__(self):
        return f"{self.order} -> {self.status}"
    
