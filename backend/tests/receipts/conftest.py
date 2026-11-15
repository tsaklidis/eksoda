import pytest

from apps.receipts.services import pipeline
from config.celery import app as celery_app


@pytest.fixture
def use_fetcher(monkeypatch):
    """Make the pipeline's default fetcher a fake: ``use_fetcher(FakeFetcher(...))``."""

    def install(fetcher):
        monkeypatch.setattr(pipeline, "default_fetcher", lambda: fetcher)
        return fetcher

    return install


@pytest.fixture
def eager_tasks():
    """Run Celery tasks inline when they are enqueued (``.delay``)."""
    keys = ("task_always_eager", "task_eager_propagates")
    previous = {key: celery_app.conf[key] for key in keys}
    celery_app.conf.update(dict.fromkeys(keys, True))
    yield
    celery_app.conf.update(previous)


@pytest.fixture
def enqueued(monkeypatch) -> list[str]:
    """Record the job ids enqueued for processing instead of sending them to the broker."""
    from apps.receipts import tasks

    job_ids: list[str] = []
    monkeypatch.setattr(tasks.process_import, "delay", job_ids.append)
    return job_ids
