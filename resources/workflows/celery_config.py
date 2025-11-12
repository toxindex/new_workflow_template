import os
broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
broker_connection_retry_on_startup = True
worker_max_tasks_per_child = 10
worker_hijack_root_logger = False
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
enable_utc = True

# Enhanced logging configuration
worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
worker_task_log_format = '[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s'
worker_log_color = True

# Task execution logging
task_track_started = True
task_annotations = {
    '*': {
        'rate_limit': '10/m'
    }
}

# Worker settings for better visibility
worker_prefetch_multiplier = 1
worker_disable_rate_limits = False
worker_send_task_events = True
task_send_sent_event = True