import webserver.datastore as ds
import logging
import datetime

class UserGroup:
    def __init__(self, group_id, name, description=None, created_at=None):
        self.group_id = group_id
        self.name = name
        self.description = description
        self.created_at = created_at

    def to_dict(self):
        return {
            'group_id': str(self.group_id),
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

    @staticmethod
    def from_row(row):
        return UserGroup(
            group_id=row['group_id'],
            name=row['name'],
            description=row.get('description'),
            created_at=row['created_at']
        )

    @staticmethod
    def get_group(group_id):
        res = ds.find("SELECT * FROM user_groups WHERE group_id = %s", (group_id,))
        return UserGroup.from_row(res) if res else None

    @staticmethod
    def get_group_by_name(name):
        res = ds.find("SELECT * FROM user_groups WHERE name = %s", (name,))
        return UserGroup.from_row(res) if res else None

    @staticmethod
    def get_all_groups():
        rows = ds.find_all("SELECT * FROM user_groups ORDER BY name")
        return [UserGroup.from_row(row) for row in rows]

    @staticmethod
    def create_group(name, description=None):
        params = (name, description)
        ds.execute("INSERT INTO user_groups (name, description) VALUES (%s, %s)", params)
        logging.info(f"created user group {name}")
        res = ds.find("SELECT * FROM user_groups WHERE name = %s ORDER BY created_at DESC LIMIT 1", (name,))
        return UserGroup.from_row(res) if res else None

    @staticmethod
    def update_group(group_id, name=None, description=None):
        if name:
            ds.execute("UPDATE user_groups SET name = %s WHERE group_id = %s", (name, group_id))
        if description is not None:
            ds.execute("UPDATE user_groups SET description = %s WHERE group_id = %s", (description, group_id))
        logging.info(f"updated user group {group_id}")
        return UserGroup.get_group(group_id)

    @staticmethod
    def delete_group(group_id):
        # First, move users to basic group
        basic_group = UserGroup.get_group_by_name('basic')
        if basic_group:
            ds.execute("UPDATE users SET group_id = %s WHERE group_id = %s", (basic_group.group_id, group_id))
        
        # Delete workflow access
        ds.execute("DELETE FROM workflow_group_access WHERE group_id = %s", (group_id,))
        
        # Delete the group
        ds.execute("DELETE FROM user_groups WHERE group_id = %s", (group_id,))
        logging.info(f"deleted user group {group_id}")

    @staticmethod
    def get_user_group(user_id):
        """Get the group for a specific user"""
        res = ds.find("""
            SELECT ug.* FROM user_groups ug
            JOIN users u ON u.group_id = ug.group_id
            WHERE u.user_id = %s
        """, (user_id,))
        return UserGroup.from_row(res) if res else None

    @staticmethod
    def set_user_group(user_id, group_id):
        """Set the group for a specific user"""
        ds.execute("UPDATE users SET group_id = %s WHERE user_id = %s", (group_id, user_id))
        logging.info(f"set user {user_id} to group {group_id}")

    @staticmethod
    def get_users_in_group(group_id):
        """Get all users in a specific group"""
        rows = ds.find_all("""
            SELECT u.*, ug.name as group_name FROM users u
            JOIN user_groups ug ON u.group_id = ug.group_id
            WHERE u.group_id = %s
            ORDER BY u.created_at DESC
        """, (group_id,))
        return rows

    @staticmethod
    def get_all_users_with_groups():
        """Get all users with their group information"""
        rows = ds.find_all("""
            SELECT u.*, ug.name as group_name, ug.description as group_description
            FROM users u
            LEFT JOIN user_groups ug ON u.group_id = ug.group_id
            ORDER BY u.created_at DESC
        """)
        return rows

    @staticmethod
    def get_accessible_workflows(user_id):
        """Get workflows accessible to a specific user based on their group"""
        rows = ds.find_all("""
            SELECT DISTINCT w.* FROM workflows w
            JOIN workflow_group_access wga ON w.workflow_id = wga.workflow_id
            JOIN users u ON u.group_id = wga.group_id
            WHERE u.user_id = %s
            ORDER BY w.workflow_id
        """, (user_id,))
        return rows

    @staticmethod
    def grant_workflow_access(group_id, workflow_id):
        """Grant a group access to a workflow"""
        ds.execute("""
            INSERT INTO workflow_group_access (workflow_id, group_id)
            VALUES (%s, %s)
            ON CONFLICT (workflow_id, group_id) DO NOTHING
        """, (workflow_id, group_id))
        logging.info(f"granted group {group_id} access to workflow {workflow_id}")

    @staticmethod
    def revoke_workflow_access(group_id, workflow_id):
        """Revoke a group's access to a workflow"""
        ds.execute("DELETE FROM workflow_group_access WHERE group_id = %s AND workflow_id = %s", (group_id, workflow_id))
        logging.info(f"revoked group {group_id} access to workflow {workflow_id}") 