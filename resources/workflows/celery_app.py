import os
from celery import Celery
from . import celery_config

# Broker/backends from env with sensible defaults
broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery = Celery(
    'workflows',
    broker=broker_url,
    backend=result_backend,
)

celery.config_from_object(celery_config)

# Common Celery configuration
celery.conf.update(
    worker_hijack_root_logger=False,
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    worker_log_color=True,
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
)


