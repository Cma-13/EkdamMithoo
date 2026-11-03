from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save
from .models import Order, OrderHistory, OrderItem


@receiver(pre_save, sender=Order)
def handle_order_pre_save(sender, instance, **kwargs):
    # Remember the old status so post_save can tell if it changed
    old_order = Order.objects.filter(pk=instance.pk).first()
    instance._old_status = old_order.status if old_order else None


@receiver(post_save, sender=Order)
def handle_order_history_creation(sender, instance, **kwargs):
    if instance._old_status != instance.status:
        OrderHistory.objects.create(order=instance, status=instance.status)


@receiver(post_save, sender=OrderItem)
def handle_auto_order_status_update(sender, instance, **kwargs):
    """Keep the order status in sync with its items.

    - every item served/cancelled -> order Served (or Cancelled if nothing was served)
    - some items served           -> order Partially Served
    """
    if instance.status not in (OrderItem.ITEM_STATUS.SERVED, OrderItem.ITEM_STATUS.CANCELLED):
        return

    order = instance.order
    if order.status == Order.ORDER_STATUS.BILLED:
        return

    items = order.items.all()
    done_statuses = (OrderItem.ITEM_STATUS.SERVED, OrderItem.ITEM_STATUS.CANCELLED)
    all_done = all(item.status in done_statuses for item in items)
    any_served = any(item.status == OrderItem.ITEM_STATUS.SERVED for item in items)

    if all_done:
        new_status = Order.ORDER_STATUS.SERVED if any_served else Order.ORDER_STATUS.CANCELLED
    elif any_served:
        new_status = Order.ORDER_STATUS.PARTIALLY_SERVED
    else:
        new_status = order.status

    if new_status != order.status:
        order.status = new_status
        order.save()
