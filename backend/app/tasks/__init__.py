"""Celery tasks. Импортируются на старте worker'а через app.worker."""
from app.tasks import calculate_project  # noqa: F401
