import logging
import webserver.datastore as ds
from webserver.cache_manager import cache_query_result

class File:
    def __init__(self, file_id, task_id, user_id, filename, filepath, created_at, environment_id=None):
        self.file_id = file_id
        self.task_id = task_id
        self.user_id = user_id
        self.filename = filename
        self.filepath = filepath
        self.created_at = created_at
        self.environment_id = environment_id

    def to_dict(self):
        # Handle created_at which might be a string or datetime object
        created_at_str = None
        if self.created_at:
            if hasattr(self.created_at, 'strftime'):
                # It's a datetime object
                created_at_str = self.created_at.strftime('%Y-%m-%d %H:%M:%S')
            else:
                # It's already a string
                created_at_str = str(self.created_at)
        
        return {
            'file_id': self.file_id,
            'task_id': self.task_id,
            'environment_id': self.environment_id,
            'user_id': self.user_id,
            'filename': self.filename,
            'filepath': self.filepath,
            'created_at': created_at_str
        }

    @staticmethod
    def from_row(row):
        return File(
            file_id=row['file_id'],
            task_id=row.get('task_id'),
            user_id=row['user_id'],
            filename=row['filename'],
            filepath=row['filepath'],
            created_at=row['created_at'],
            environment_id=row.get('environment_id'),
        )

    @staticmethod
    def create_file(task_id, user_id, filename, filepath, environment_id=None):
        logging.info(f"[File.create_file] Storing file for task_id={task_id}, environment_id={environment_id}, filename={filename}, filepath={filepath}")
        # Duplicate check: does a file with this task_id/environment_id and filename already exist?
        if task_id:
            existing = ds.find("SELECT 1 FROM files WHERE task_id = %s AND filename = %s", (task_id, filename))
        elif environment_id:
            existing = ds.find("SELECT 1 FROM files WHERE environment_id = %s AND filename = %s", (environment_id, filename))
        else:
            existing = None
        if existing:
            logging.warning(f"[File.create_file] Duplicate file for task_id={task_id}, environment_id={environment_id}, filename={filename} -- skipping insert.")
            return
        params = (task_id, environment_id, user_id, filename, filepath)
        try:
            ds.execute(
                "INSERT INTO files (task_id, environment_id, user_id, filename, filepath) VALUES (%s, %s, %s, %s, %s)",
                params
            )
            logging.info(f"[File.create_file] Successfully inserted file for task_id={task_id}, environment_id={environment_id}, filename={filename}")
        except Exception as e:
            logging.error(f"[File.create_file] Failed to insert file for task_id={task_id}, environment_id={environment_id}, filename={filename}: {e}")
            raise

    @staticmethod  
    def process_event(task, event_data):
        user_id = event_data.get("user_id")
        filename = event_data.get("filename")
        filepath = event_data.get("filepath")
        logging.info(f"[File.process_event] Processing event for task_id={task.task_id}, filename={filename}, filepath={filepath}")
        if user_id and filename and filepath:
            File.create_file(task.task_id, user_id, filename, filepath)
            logging.info(f"[File.process_event] Stored file {filename} for task_id={task.task_id}")
        else:
            missing = []
            if not user_id:
                missing.append("user_id")
            if not filename:
                missing.append("filename") 
            if not filepath:
                missing.append("filepath")
            logging.warning(f"[File.process_event] Malformed task_file event received - missing fields: {', '.join(missing)}")
            logging.debug(f"[File.process_event] Received payload: {event_data}")

    # ------------------------------------------------------------------
    def read_text(self):
        """Return file contents, always fetching from GCS for managed paths."""
        try:
            # Prefer cached content for GCS-backed files
            if self.filepath and (self.filepath.startswith('tasks/') or self.filepath.startswith('environments/')):
                from webserver.cache_manager import cache_manager
                content = cache_manager.get_file_content(self.filepath)
                return content or ""

            # Fallback: attempt GCS download for any other stored path as a key
            from webserver.storage import GCSFileStorage
            import tempfile
            gcs_storage = GCSFileStorage()
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_path = temp_file.name
            gcs_storage.download_file(self.filepath, temp_path)
            with open(temp_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logging.warning(f"Could not read file via GCS for {self.filepath}: {e}")
            return ""

    def markdown_to_html(self):
        text = self.read_text()
        if not text:
            return ""
        import markdown
        return markdown.markdown(text, extensions=["extra", "tables"])

    @staticmethod
    @cache_query_result("get_files_by_environment")
    def get_files_by_environment(environment_id):
        rows = ds.find_all(
            "SELECT * FROM files WHERE environment_id = %s ORDER BY created_at DESC",
            (environment_id,)
        )
        return [File.from_row(row) for row in rows]

    @staticmethod
    @cache_query_result("get_file")
    def get_file(file_id):
        row = ds.find("SELECT * FROM files WHERE file_id = %s", (file_id,))
        return File.from_row(row) if row else None

    @staticmethod
    def delete_file(file_id, user_id=None):
        params = (file_id,)
        query = "DELETE FROM files WHERE file_id = %s"
        if user_id is not None:
            query += " AND user_id = %s"
            params = (file_id, user_id)
        ds.execute(query, params)

    @staticmethod
    def get_files_by_task(task_id):
        rows = ds.find_all(
            "SELECT * FROM files WHERE task_id = %s ORDER BY created_at DESC",
            (task_id,)
        )
        return [File.from_row(row) for row in rows]

    @staticmethod
    def get_files_by_session(session_id):
        """Get all files associated with a chat session through tasks"""
        rows = ds.find_all(
            """SELECT f.* FROM files f 
               JOIN tasks t ON f.task_id = t.task_id 
               WHERE t.session_id = %s 
               ORDER BY f.created_at DESC""",
            (session_id,)
        )
        return [File.from_row(row) for row in rows]



