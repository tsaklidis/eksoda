"""System product categories (requirements §8.9). Idempotent by slug."""

from django.db import migrations

SYSTEM_CATEGORIES = [
    ("groceries", "Groceries"),
    ("dairy-and-eggs", "Dairy and eggs"),
    ("meat-and-fish", "Meat and fish"),
    ("fruits-and-vegetables", "Fruits and vegetables"),
    ("bakery", "Bakery"),
    ("beverages", "Beverages"),
    ("frozen-food", "Frozen food"),
    ("snacks-and-sweets", "Snacks and sweets"),
    ("cleaning-products", "Cleaning products"),
    ("personal-care", "Personal care"),
    ("household-items", "Household items"),
    ("pet-supplies", "Pet supplies"),
    ("restaurants-and-cafes", "Restaurants and cafés"),
    ("pharmacy-and-health", "Pharmacy and health"),
    ("fuel-and-transport", "Fuel and transport"),
    ("clothing-and-footwear", "Clothing and footwear"),
    ("electronics-and-appliances", "Electronics and appliances"),
    ("services", "Services"),
    ("other", "Other"),
]


def seed(apps, schema_editor):
    category = apps.get_model("products", "ProductCategory")
    for slug, name in SYSTEM_CATEGORIES:
        category.objects.update_or_create(household=None, slug=slug, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("products", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
