"""Entry point for the Celery CLI.

`celery -A celery_worker worker ...` (and `flower`) imports this module and
expects to find a `celery_app` attribute. We re-export the app defined in
core.background_task — that module also registers all the @task decorators,
so importing it here is what makes the tasks discoverable to the worker.
"""

from core.background_task import celery_app  # noqa: F401

__all__ = ["celery_app"]
