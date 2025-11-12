import webserver.datastore as ds
import logging
import json
import datetime
from pydantic import BaseModel

class MessageSchema(BaseModel):
    role: str
    content: str

class Message():

    ASSISTANT_USER_ID = "00000000-0000-0000-0000-000000000000"

    def __init__(self, message_id, task_id, user_id, role, content, created_at, session_id=None):
        self.message_id = message_id
        self.task_id = task_id
        self.user_id = user_id
        self.role = role
        self.content = content
        self.created_at = created_at
        self.session_id = session_id

    def to_dict(self):
        return {
            'message_id': str(self.message_id),
            'task_id': str(self.task_id),
            'user_id': str(self.user_id),
            'role': self.role,
            'content': self.content,
            'created_at': str(self.created_at),
            'session_id': str(self.session_id) if self.session_id else None,
        }

    
    def to_json(self):
        return json.dumps(self.to_dict())
    
    @staticmethod
    def from_row(row):
        return Message(
            message_id=row['message_id'],
            task_id=row['task_id'],
            user_id=row['user_id'],
            role=row['role'],
            content=row['content'],
            created_at=row['created_at'],
            session_id=row.get('session_id')
        )

    @staticmethod
    def create_message(task_id, user_id, role, content, session_id=None):
        try:
            logging.info(f"[Message.create_message] Called with task_id={task_id}, user_id={user_id}, role={role}, content={content}, session_id={session_id}")
            # Duplicate check: does a message with this task_id, role, and content already exist?
            existing = ds.find("SELECT 1 FROM messages WHERE task_id = %s AND role = %s AND content = %s", (task_id, role, content))
            if existing:
                logging.warning(f"[Message.create_message] Duplicate message for task_id={task_id}, role={role} -- skipping insert.")
                return None
            logging.info(f"[Message.create_message] Storing message for task_id={task_id}, user_id={user_id}, role={role}, content={content}, session_id={session_id}")
            params = (task_id, user_id, role, content, session_id)
            ds.execute(
                "INSERT INTO messages (task_id, user_id, role, content, session_id) VALUES (%s, %s, %s, %s, %s)",
                params
            )
            logging.info(f"[Message.create_message] Message stored for task_id={task_id}")
            # Fetch and return the newly created message
            row = ds.find(
                "SELECT * FROM messages WHERE task_id = %s AND user_id = %s AND role = %s AND content = %s ORDER BY created_at DESC LIMIT 1",
                (task_id, user_id, role, content)
            )
            if row:
                logging.info(f"[Message.create_message] Returning created message for task_id={task_id}, message_id={row.get('message_id')}")
                return Message.from_row(row)
            else:
                logging.error(f"[Message.create_message] Failed to fetch created message for task_id={task_id}")
                return None
        except Exception as e:
            logging.error(f"[Message.create_message] Exception: {e}", exc_info=True)
            return None

    @staticmethod
    def get_messages_by_session(session_id):
        rows = ds.find_all(
            "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,)
        )
        logging.info(f"Retrieved {len(rows)} messages for session_id={session_id}")
        return [Message.from_row(row) for row in rows]

    @staticmethod
    def get_messages(task_id):
        rows = ds.find_all(
            "SELECT * FROM messages WHERE task_id = %s ORDER BY created_at ASC",
            (task_id,)
        )
        logging.info(f"Retrieved {len(rows)} messages for task_id={task_id}")
        return [Message.from_row(row) for row in rows]

    @staticmethod
    def process_event(task, event_data):
        logging.info(f"[Message.process_event] Processing event for task_id={task.task_id}, role={event_data.get('role')}, content={event_data.get('content')}")
        role = event_data.get("role", "assistant")
        content = event_data.get("content")
        session_id = getattr(task, 'session_id', None)
        if content and role:
            user_id = Message.ASSISTANT_USER_ID if role == "assistant" else None
            msg = Message.create_message(task.task_id, user_id, role, content, session_id=session_id)
            logging.info(f"[Message.process_event] Stored message for task_id={task.task_id} from role={role}")
            return msg
        else:
            logging.warning(f"[Message.process_event] Malformed task_message event received data: {event_data}")
            logging.warning(f"[Message.process_event] Role: {role}")
            logging.warning(f"[Message.process_event] Content: {content}")
            return None
