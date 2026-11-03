from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from orders.models import Category, KitchenStation, MenuItem

# Short descriptions shown on the website (only filled in where empty)
DESCRIPTIONS = {
    "Momo (Buff)": "Hand-folded buff momo, steamed and served with tomato-sesame achar.",
    "Momo (Chicken)": "Juicy chicken filling with ginger and coriander, steamed to order.",
    "Momo (Veg)": "Cabbage, carrot and paneer filling with a mild spice.",
    "Chatamari": "Newari rice crêpe topped with egg and minced meat.",
    "Sekuwa": "Charcoal-grilled meat marinated in timur and mountain spices.",
    "Choila": "Smoky grilled buff tossed with mustard oil, chilli and garlic.",
    "Aloo Tama": "Potato and bamboo shoot curry with black-eyed beans.",
    "Wai Wai Sadeko": "Crunchy noodles tossed with onion, tomato, chilli and lemon.",
    "Sel Roti with Aloo Tarkari": "Sweet ring-shaped rice bread with spiced potato curry.",
    "Chiura with Tarkari": "Beaten rice served with seasonal vegetable curry.",
    "Anda Paratha": "Flaky flatbread with egg, served with achar.",
    "Puri Tarkari": "Puffed fried bread with potato curry.",
    "Jeri Swari": "Crispy jeri with soft swari, a classic sweet breakfast.",
    "Dal Bhat Tarkari (Veg)": "Rice, lentil soup, seasonal vegetables, saag and achar.",
    "Dal Bhat Tarkari (Chicken)": "Our everyday dal bhat with home-style chicken curry.",
    "Dal Bhat Tarkari (Mutton)": "Dal bhat with slow-cooked bone-in mutton curry.",
    "Thakali Khana Set": "Thakali-style set with gundruk, ghee, achar and refills.",
    "Gundruk Dhido Set": "Buckwheat dhido with gundruk soup and fresh achar.",
    "Masala Chiya": "Milk tea brewed with cardamom, cinnamon and ginger.",
}

# Featured dishes and the photo (from static/orders/images) to use for each
FEATURED = {
    "Momo (Buff)": "momo.jpg",
    "Thakali Khana Set": "thali set.jpg",
    "Masala Chiya": "masala-chai.jpg",
}


class Command(BaseCommand):
    help = "Add website descriptions, photos and featured dishes to the menu"

    @transaction.atomic
    def handle(self, *args, **options):
        # Masala Chiya is used as a featured dish, so make sure it exists
        drinks, _ = Category.objects.get_or_create(name="Drinks")
        beverage = KitchenStation.objects.filter(code="beverage").first()
        MenuItem.objects.get_or_create(
            name="Masala Chiya",
            defaults={"category": drinks, "price": 60, "est_time": 5, "station": beverage},
        )

        described = 0
        for name, text in DESCRIPTIONS.items():
            described += MenuItem.objects.filter(name=name, description__isnull=True).update(description=text)
            described += MenuItem.objects.filter(name=name, description="").update(description=text)

        images_dir = Path(settings.BASE_DIR) / "orders" / "static" / "orders" / "images"
        for name, image_name in FEATURED.items():
            item = MenuItem.objects.filter(name=name).first()
            if item is None:
                self.stdout.write(self.style.WARNING(f"Skipped '{name}': not on the menu"))
                continue
            item.is_featured = True
            image_path = images_dir / image_name
            if not item.image and image_path.exists():
                with image_path.open("rb") as f:
                    item.image.save(image_name.replace(" ", "-"), File(f), save=False)
            item.save()

        self.stdout.write(self.style.SUCCESS(
            f"Website menu ready: {described} descriptions added, {len(FEATURED)} featured dishes."
        ))
