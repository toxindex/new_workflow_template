import redis
import json
import os
import uuid
import logging

from pathlib import Path

# Webserver models and storage
from webserver.socketio import socketio
from webserver.model.task import Task
from webserver.storage import GCSFileStorage

# <----- Utility functions (for workflows) ----->

def get_redis_connection():
    """Get Redis connection with consistent configuration"""
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379"))
    )


def publish_to_celery_updates(event_type, task_id, data):
    """Publish event to celery_updates channel for database processing"""
    r = get_redis_connection()
    event = {
        "type": event_type,
        "task_id": task_id,
        "data": data,
    }
    r.publish("celery_updates", json.dumps(event, default=str))
    logging.info(f"Published {event_type} to celery_updates for task {task_id}")


def publish_to_socketio(event_name, room, data):
    """Emit directly via Flask-SocketIO manager (uses Redis message_queue under the hood)."""
    try:
        socketio.emit(event_name, data, room=room)
        logging.info(f"Emitted {event_name} to Socket.IO room {room}")
    except Exception as e:
        logging.error(f"Failed to emit {event_name} to room {room}: {e}")


def emit_status(task_id, status):
    """Emit task status update to both database and real-time channels"""
    logging.info(f"[emit_status] {task_id} -> {status}")
    
    # Update database directly
    # Ensure status fits DB column (varchar(32))
    status = (status or "")[:32]
    Task.set_status(task_id, status)
    task = Task.get_task(task_id)
    
    # Publish to celery_updates for any additional database processing
    publish_to_celery_updates("task_status_update", task.task_id, task.to_dict())
    
    # Publish to Socket.IO for real-time updates
    publish_to_socketio("task_status_update", f"task_{task_id}", task.to_dict())

def emit_task_message(task_id, message_data):
    """Emit task message to both database and real-time channels"""
    # Publish to celery_updates for database processing
    publish_to_celery_updates("task_message", task_id, message_data)
    
    # Publish to Socket.IO for real-time updates
    task = Task.get_task(task_id)
    if task and getattr(task, 'session_id', None):
        # Emit to chat session room
        publish_to_socketio("new_message", f"chat_session_{task.session_id}", message_data)
    
    # Emit to task room
    publish_to_socketio("task_message", f"task_{task_id}", {
        "type": "task_message",
        "data": message_data,
        "task_id": str(task_id),  # Convert UUID to string for JSON serialization
    })

def emit_task_file(task_id, file_data):
    """Emit task file to both database and real-time channels"""
    # Publish to celery_updates for database processing
    publish_to_celery_updates("task_file", task_id, file_data)
    
    # Publish to Socket.IO for real-time updates
    publish_to_socketio("task_file", f"task_{task_id}", file_data)

def download_gcs_file_to_temp(gcs_path: str, temp_dir: Path) -> Path:
    """Download a file from GCS to a temporary local path with caching."""
    from webserver.cache_manager import cache_manager
    
    # Try to get from cache first
    cached_content = cache_manager.get_file_content(gcs_path)
    if cached_content:
        # Write cached content to temp file
        local_path = temp_dir / f"{uuid.uuid4().hex}_{Path(gcs_path).name}"
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(cached_content)
        return local_path
    
    # Cache miss - download from GCS
    gcs_storage = GCSFileStorage()
    local_path = temp_dir / f"{uuid.uuid4().hex}_{Path(gcs_path).name}"
    gcs_storage.download_file(gcs_path, str(local_path))
    
    # Cache the content for future use
    with open(local_path, 'r', encoding='utf-8') as f:
        content = f.read()
    cache_manager.cache_file_content(gcs_path, content)
    
    return local_path

def upload_local_file_to_gcs(local_path: Path, gcs_path: str, content_type: str = None) -> str:
    """Upload a local file to GCS and return the GCS path."""
    gcs_storage = GCSFileStorage()
    gcs_storage.upload_file(str(local_path), gcs_path, content_type=content_type)
    return gcs_path
