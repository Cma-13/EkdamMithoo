from django.contrib import admin
from .models import Bill, Table, Category, MenuItem, Order, OrderItem, OrderHistory, KitchenStation

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["name", "is_reserved"]
    
    
@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ["name", "default_priority", "est_time", "station"]
    


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["table", "status", "created_at"]
    
    
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "status", "price", "quantity"]
    list_filter = ["order__table"]
    list_editable = ["status"]
    
    

@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ["bill_number", "table", "total", "payment_method", "billed_by", "created_at"]
    list_filter = ["payment_method", "created_at"]
    readonly_fields = ["subtotal", "service_charge", "vat", "total", "created_at"]


admin.site.register(KitchenStation)
admin.site.register(Category)
admin.site.register(OrderHistory)