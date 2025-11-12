import webserver.datastore as ds
import logging
import datetime
import redis
import json


class Task:

    def __init__(
        self,
        task_id,
        title,
        user_id,
        workflow_id,
        environment_id=None,
        celery_task_id=None,
        description=None,
        created_at=None,
        finished_at=None,
        archived=False,
        last_accessed=None,
        session_id=None,
        status=None,
    ):
        self.task_id = task_id
        self.title = title
        self.user_id = user_id
        self.workflow_id = workflow_id
        self.environment_id = environment_id
        self.celery_task_id = celery_task_id
        self.description = description
        self.created_at = created_at
        self.finished_at = finished_at
        self.archived = archived
        self.last_accessed = last_accessed
        self.session_id = session_id
        self.status = status

    def to_dict(self):
        return {
            "task_id": str(self.task_id),
            "title": self.title,
            "user_id": str(self.user_id) if self.user_id else None,
            "workflow_id": self.workflow_id,
            "environment_id": str(self.environment_id) if self.environment_id else None,
            "description": self.description,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
            "finished_at": (
                self.finished_at.isoformat()
                if self.finished_at
                else None
            ),
            "archived": self.archived,
            "last_accessed": (
                self.last_accessed.isoformat()
                if self.last_accessed
                else None
            ),
            "session_id": str(self.session_id) if self.session_id else None,
            "status": self.status,
        }

    @staticmethod
    def from_row(row):
        return Task(
            task_id=row["task_id"],
            title=row["title"],
            user_id=row["user_id"],
            workflow_id=row["workflow_id"],
            environment_id=row.get("environment_id"),
            celery_task_id=row["celery_task_id"],
            description=row.get("description"),
            created_at=row["created_at"], #required
            finished_at=row.get("finished_at"), #optional   
            archived=row.get("archived", False),  #optional with default  
            last_accessed=row.get("last_accessed"),
            session_id=row.get("session_id"),
            status=row.get("status"),
        )

    @staticmethod
    def create_task(
        title,
        user_id,
        workflow_id,
        environment_id=None,
        celery_task_id=None,
        description=None,
        session_id=None,
        created_at=None,
    ):
        if created_at is None:
            created_at = datetime.datetime.now(datetime.timezone.utc)
        logging.info(f"Creating new task with title='{title}' for user_id={user_id}, session_id={session_id}")
        logging.info(f"create_task: created_at={created_at} (type: {type(created_at)})")
        params = (
            title,
            user_id,
            celery_task_id,
            workflow_id,
            environment_id,
            description,
            session_id,
            created_at,
            'processing', # status
        )
        logging.info(f"create_task params: {params}")
        ds.execute(
            "INSERT INTO tasks (title, user_id, celery_task_id, workflow_id, environment_id, description, session_id, created_at, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            params,
        )

        # Fetch and return the newly created task
        res = ds.find(
            "SELECT * FROM tasks WHERE title = %s AND user_id = %s ORDER BY created_at DESC LIMIT 1",
            (title, user_id),
        )
        if res:
            logging.info(f"Successfully created task with id={res['task_id']}")
            return Task.from_row(res)
        else:
            logging.error(f"Failed to create task for user_id={user_id}")
            return None

    @staticmethod
    def get_tasks_by_user(user_id):
        rows = ds.find_all(
            "SELECT *, archived, last_accessed FROM tasks WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        return [Task.from_row(row) for row in rows]

    @staticmethod
    def get_tasks_by_environment(environment_id, user_id=None):
        if user_id:
            rows = ds.find_all(
                "SELECT *, archived, last_accessed FROM tasks WHERE environment_id = %s AND user_id = %s ORDER BY created_at DESC",
                (environment_id, user_id),
            )
        else:
            rows = ds.find_all(
                "SELECT *, archived, last_accessed FROM tasks WHERE environment_id = %s ORDER BY created_at DESC",
                (environment_id,),
            )
        return [Task.from_row(row) for row in rows]

    @staticmethod
    def get_tasks_by_celery_task_id(celery_task_id):
        res = ds.find(
            "SELECT * FROM tasks WHERE celery_task_id = %s", (celery_task_id,)
        )
        return Task.from_row(res) if res else None

    @staticmethod
    def get_task(task_id):
        res = ds.find("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
        return Task.from_row(res) if res else None

    @staticmethod
    def add_message(task_id, user_id, role, content, session_id=None):
        params = (task_id, user_id, role, content, session_id)
        ds.execute(
            "INSERT INTO messages (task_id, user_id, role, content, session_id) VALUES (%s, %s, %s, %s, %s)",
            params,
        )

    @staticmethod
    def update_celery_task_id(task_id, celery_task_id):
        params = (celery_task_id, task_id)
        ds.execute("UPDATE tasks SET celery_task_id = %s WHERE task_id = %s", params)

    @staticmethod
    def set_status(task_id, status):
        """Set the status of a task."""
        params = (status, task_id)
        ds.execute("UPDATE tasks SET status = %s WHERE task_id = %s", params)

    @staticmethod
    def get_messages(task_id, user_id):
        # Check if the task belongs to the user
        task = ds.find(
            "SELECT * FROM tasks WHERE task_id = %s AND user_id = %s",
            (task_id, user_id),
        )
        if not task:
            return []

        rows = ds.find_all(
            "SELECT * FROM messages WHERE task_id = %s ORDER BY created_at ASC",
            (task_id,),
        )
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    @staticmethod
    def mark_finished(task_id):
        finished_at = datetime.datetime.now(datetime.timezone.utc)
        ds.execute(
            "UPDATE tasks SET finished_at = %s, status = 'done' WHERE task_id = %s",
            (finished_at, task_id)
        )
        return finished_at
