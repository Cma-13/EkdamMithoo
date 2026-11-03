import re
from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from .models import Reservation


def parse_clock(value):
    """'11:00' -> time(11, 0)"""
    return datetime.strptime(value, "%H:%M").time()


def booking_times():
    """Half-hour slots from opening time until 1 hour before closing."""
    start = datetime.combine(datetime.today(), parse_clock(settings.OPENING_TIME))
    last = datetime.combine(datetime.today(), parse_clock(settings.CLOSING_TIME)) - timedelta(hours=1)
    slots = []
    while start <= last:
        slots.append((start.strftime("%H:%M"), start.strftime("%I:%M %p").lstrip("0")))
        start += timedelta(minutes=30)
    return slots


class ReservationForm(forms.ModelForm):
    time = forms.TypedChoiceField(
        choices=booking_times,
        coerce=lambda value: parse_clock(value),
    )

    class Meta:
        model = Reservation
        fields = ["name", "phone", "guests", "date", "time", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.TextInput(attrs={"placeholder": "Birthday, high chair, window seat..."}),
        }
        labels = {
            "name": "Your name",
            "phone": "Phone number",
            "guests": "Guests",
            "note": "Anything we should know? (optional)",
        }

    REQUIRED_MESSAGES = {
        "name": "Please enter your name.",
        "phone": "Please enter a phone number so we can confirm.",
        "guests": "How many people are coming?",
        "date": "Choose a date.",
        "time": "Choose a time.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, message in self.REQUIRED_MESSAGES.items():
            self.fields[name].error_messages["required"] = message
        today = timezone.localdate()
        self.fields["date"].widget.attrs.update({
            "min": today.isoformat(),
            "max": (today + timedelta(days=settings.BOOKING_DAYS_AHEAD)).isoformat(),
        })
        self.fields["guests"].widget.attrs.update({"min": 1, "max": settings.MAX_GUESTS_PER_BOOKING})
        self.fields["phone"].widget.attrs.update({"placeholder": "98XXXXXXXX", "inputmode": "tel"})
        self.fields["name"].widget.attrs.update({"autocomplete": "name"})

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if len(name) < 2:
            raise forms.ValidationError("Please enter your name.")
        return name

    def clean_phone(self):
        # Keep digits only, allow an optional +977 country code
        digits = re.sub(r"\D", "", self.cleaned_data["phone"])
        if digits.startswith("977"):
            digits = digits[3:]
        if not (len(digits) == 10 and digits.startswith("9")) and not (7 <= len(digits) <= 9):
            raise forms.ValidationError("Enter a 10-digit mobile number (98XXXXXXXX) or a landline number.")
        return digits

    def clean_guests(self):
        guests = self.cleaned_data["guests"]
        if guests < 1:
            raise forms.ValidationError("At least 1 guest.")
        if guests > settings.MAX_GUESTS_PER_BOOKING:
            raise forms.ValidationError(
                f"For more than {settings.MAX_GUESTS_PER_BOOKING} guests, please call us."
            )
        return guests

    def clean_date(self):
        date = self.cleaned_data["date"]
        today = timezone.localdate()
        if date < today:
            raise forms.ValidationError("Choose today or a later date.")
        if date > today + timedelta(days=settings.BOOKING_DAYS_AHEAD):
            raise forms.ValidationError(f"Bookings open up to {settings.BOOKING_DAYS_AHEAD} days ahead.")
        return date

    def clean(self):
        cleaned = super().clean()
        date, time = cleaned.get("date"), cleaned.get("time")
        if date and time and date == timezone.localdate():
            now = timezone.localtime().time()
            if time <= now:
                self.add_error("time", "That time has already passed today. Pick a later time.")
        return cleaned
