from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    """PostgreSQL extensions used by product search and matching (TD §8.4)."""

    initial = True
    dependencies = []
    operations = [TrigramExtension(), UnaccentExtension()]
