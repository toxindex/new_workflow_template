import redis
import json
import os
import uuid
import logging
import tempfile
from workflows.celery_app import celery
from webserver.model.message import MessageSchema
from webserver.model.task import Task
from webserver.storage import GCSFileStorage
from webserver.model.file import File
from pathlib import Path
from workflows.utils import emit_status, download_gcs_file_to_temp, upload_local_file_to_gcs, publish_to_celery_updates, publish_to_socketio, get_redis_connection, emit_task_file, emit_task_message
# from toolname import yourtool


@celery.task(bind=True, queue='[toolname]')
def toolname(self, payload):
    """GCS-enabled background task that emits progress messages and uploads files to GCS."""

    
    try:
        r = get_redis_connection()
        task_id = payload.get("task_id")
        user_id = payload.get("user_id")
        file_id = payload.get("payload")

        if not all([task_id, user_id]):
            raise ValueError(f"Missing required fields. task_id={task_id}, user_id={user_id}")

        emit_status(task_id, "fetching file from GCS")
        # Get file info from DB
        file_obj = File.get_file(file_id)
        if not file_obj or not file_obj.filepath:
            raise FileNotFoundError(f"Input file not found for file_id={file_id}")

        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Download input file from GCS
            input_path = download_gcs_file_to_temp(file_obj.filepath, temp_path)

        emit_status(task_id, "starting")

        # THIS IS YOUR TEXT INPUT
        user_query = payload.get("payload")
        emit_status(task_id, "running")

        response = yourtool_function(user_query)
        emit_status(task_id, "sending message")

        # display raw markdown content directly to user
        message = MessageSchema(role="assistant", content=response)
        emit_task_message(task_id, message.model_dump())

        emit_status(task_id, "uploading files to GCS")

        # Create Markdown file
        md_filename = f"probra_result_{uuid.uuid4().hex}.md"
        
        # Upload Markdown file to GCS
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as temp_md_file:
            temp_md_path = temp_md_file.name
            temp_md_file.write(response_content)
        
        try:
            # Upload to GCS
            gcs_storage = GCSFileStorage()
            
            # Upload Markdown file
            md_gcs_path = f"tasks/{task_id}/{md_filename}"
            gcs_storage.upload_file(temp_md_path, md_gcs_path, content_type='text/markdown')
            emit_status(task_id, "files uploaded") # send status to frontend

            # Emit Markdown file event
            md_file_data = {
                "user_id": user_id,
                "filename": md_filename,
                "filepath": md_gcs_path,
                "file_type": "markdown",
                "content_type": "text/markdown"
            }
            emit_task_file(task_id, md_file_data) # send file to frontend
            
        finally:
            # Clean up temporary files
            os.unlink(temp_md_path)
        finished_at = Task.mark_finished(task_id)
        emit_status(task_id, "done")
        return {"done": True, "finished_at": finished_at}

    except Exception as e:
        emit_status(task_id, "error")
        raise  # Re-raise the exception so Celery knows the task failed 