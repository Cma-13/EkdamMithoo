from datetime import datetime

from django.conf import settings


def friendly_time(value):
    """'22:00' -> '10 PM', '11:30' -> '11:30 AM'"""
    t = datetime.strptime(value, "%H:%M")
    text = t.strftime("%I:%M %p") if t.minute else t.strftime("%I %p")
    return text.lstrip("0")


def restaurant(request):
    """Restaurant details available in every template as {{ restaurant.name }} etc."""
    return {
        "restaurant": {
            "name": settings.RESTAURANT_NAME,
            "name_nepali": settings.RESTAURANT_NAME_NEPALI,
            "address": settings.RESTAURANT_ADDRESS,
            "phone": settings.RESTAURANT_PHONE,
            "email": settings.RESTAURANT_EMAIL,
            "opening_time": friendly_time(settings.OPENING_TIME),
            "closing_time": friendly_time(settings.CLOSING_TIME),
        }
    }
