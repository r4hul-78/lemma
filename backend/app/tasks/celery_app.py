from celery import Celery
from app.config import settings

# In-memory broker and backend for testing/eager tasks to avoid Redis connection errors
if settings.CELERY_ALWAYS_EAGER:
    broker_url = "memory://"
    result_backend = "cache+memory://"
else:
    broker_url = settings.REDIS_URL
    result_backend = settings.REDIS_URL

celery_app = Celery(
    "lemma_tasks",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks.analysis"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.CELERY_ALWAYS_EAGER,
    task_store_eager_result=True,
)
