from celery import shared_task
from django.core.management import call_command


@shared_task(name="accounts.flush_expired_tokens")
def flush_expired_tokens() -> None:
    """Delete expired outstanding/blacklisted JWT refresh tokens (daily, via beat)."""
    call_command("flushexpiredtokens")
