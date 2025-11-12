import webserver.datastore as ds
import logging
import uuid

logger = logging.getLogger(__name__)

class ChatSession:
    def __init__(self, session_id, environment_id, user_id, title=None, created_at=None):
        self.session_id = session_id
        self.environment_id = environment_id
        self.user_id = user_id
        self.title = title
        self.created_at = created_at

    def to_dict(self):
        return {
            'session_id': str(self.session_id),
            'environment_id': str(self.environment_id),
            'user_id': str(self.user_id),
            'title': self.title,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

    @staticmethod
    def from_row(row):
        return ChatSession(
            session_id=row['session_id'],
            environment_id=row['environment_id'],
            user_id=row['user_id'],
            title=row.get('title'),
            created_at=row['created_at']
        )

    @staticmethod
    def create_session(environment_id, user_id, title=None):
        if not title:
            title = 'New chat'
        session_id = str(uuid.uuid4())
        params = (session_id, environment_id, user_id, title)
        logging.info(f"[ChatSession.create_session] Creating session: {session_id}, environment_id={environment_id}, user_id={user_id}, title='{title}'")
        try:
            ds.execute(
                "INSERT INTO chat_sessions (session_id, environment_id, user_id, title) VALUES (%s, %s, %s, %s)",
                params
            )
            logging.info(f"[ChatSession.create_session] Session inserted successfully")
            row = ds.find("SELECT * FROM chat_sessions WHERE session_id = %s", (session_id,))
            if row:
                logging.info(f"[ChatSession.create_session] Session found in database: {row}")
                return ChatSession.from_row(row)
            else:
                logging.error(f"[ChatSession.create_session] Session not found after insert: {session_id}")
                return None
        except Exception as e:
            logging.error(f"[ChatSession.create_session] Error creating session: {e}")
            return None

    @staticmethod
    def update_title(session_id, title):
        ds.execute("UPDATE chat_sessions SET title = %s WHERE session_id = %s", (title, session_id))

    @staticmethod
    def get_sessions_by_environment(environment_id, user_id=None):
        if user_id:
            rows = ds.find_all(
                "SELECT * FROM chat_sessions WHERE environment_id = %s AND user_id = %s ORDER BY created_at DESC",
                (environment_id, user_id)
            )
        else:
            rows = ds.find_all(
                "SELECT * FROM chat_sessions WHERE environment_id = %s ORDER BY created_at DESC",
                (environment_id,)
            )
        return [ChatSession.from_row(row) for row in rows]

    @staticmethod
    def get_session(session_id):
        logging.info(f"[ChatSession.get_session] Looking for session: {session_id}")
        row = ds.find("SELECT * FROM chat_sessions WHERE session_id = %s", (session_id,))
        if row:
            logging.info(f"[ChatSession.get_session] Session found: {row}")
            return ChatSession.from_row(row)
        else:
            logging.warning(f"[ChatSession.get_session] Session not found: {session_id}")
            return None

    @staticmethod
    def delete_session(session_id, user_id=None):
        params = (session_id,)
        query = "DELETE FROM chat_sessions WHERE session_id = %s"
        if user_id:
            query += " AND user_id = %s"
            params = (session_id, user_id)
        ds.execute(query, params)
        logging.info(f"Deleted chat session {session_id} for user {user_id}")

    @staticmethod
    def get_sessions_by_user(user_id):
        rows = ds.find_all(
            "SELECT * FROM chat_sessions WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        return [ChatSession.from_row(row) for row in rows] 