import webserver.datastore as ds
import logging
import json

class Workflow:
    """
    Workflow model - stores metadata about available workflow types.
    This is primarily used as a lookup table for workflow titles, descriptions,
    and initial prompts. Actual workflow execution is handled by the Task model
    and Celery tasks.
    """
    def __init__(self, workflow_id, title, user_id, description=None, initial_prompt=None, created_at=None):
        self.workflow_id = workflow_id
        self.title = title
        self.user_id = user_id
        self.description = description
        self.initial_prompt = initial_prompt
        self.created_at = created_at

    def to_dict(self):
        return {
            'workflow_id': self.workflow_id,
            'title': self.title,
            'user_id': self.user_id,
            'description': self.description,
            'initial_prompt': self.initial_prompt,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

    @staticmethod
    def from_row(row):
        return Workflow(
            workflow_id=row['workflow_id'], 
            title=row['title'], 
            user_id=row['user_id'],
            description=row.get('description'),
            initial_prompt=row.get('initial_prompt'),
            created_at=row['created_at']
        )

    @staticmethod
    def create_workflow(title, user_id=None, description=None, initial_prompt=None):
        params = (title, user_id, description, initial_prompt)
        ds.execute("INSERT INTO workflows (title, user_id, description, initial_prompt) VALUES (%s, %s, %s, %s)", params)
        logging.info(f"created workflow {title} for user {user_id}")
        res = ds.find("SELECT * FROM workflows WHERE title = %s ORDER BY created_at DESC LIMIT 1", (title,))
        return Workflow.from_row(res) if res else None
    
    @staticmethod
    def update_workflow(workflow_id, user_id=None,title=None, description=None, initial_prompt=None):
        params = (title, description, initial_prompt, workflow_id)
        ds.execute("UPDATE workflows SET title = %s, description = %s, initial_prompt = %s WHERE workflow_id = %s", params)
        logging.info(f"updated workflow {workflow_id}")
        return Workflow.get_workflow(workflow_id)
    
    @staticmethod
    def get_workflow(workflow_id):
        res = ds.find("SELECT * FROM workflows WHERE workflow_id = %s", (workflow_id,))
        return Workflow.from_row(res) if res else None

    @staticmethod
    def get_workflows_by_user(user_id):
        if user_id is None:
            rows = ds.find_all("SELECT * FROM workflows WHERE user_id IS NULL ORDER BY created_at DESC")
        else:
            rows = ds.find_all("SELECT * FROM workflows WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        return [Workflow.from_row(row) for row in rows]
    
    @staticmethod
    def load_default_workflows():
        """
        Load default workflows from JSON file into the database.
        This ensures default workflows are always available even if the database is reset.
        """
        with open('resources/default_workflows.json', 'r') as f:
            for w in json.load(f)['workflows']:
                if not ds.find("SELECT 1 FROM workflows WHERE workflow_id = %s", (w['workflow_id'],)):
                    # Filter out fields not accepted by create_workflow
                    create_fields = {k: v for k, v in w.items() if k in ['title', 'description', 'initial_prompt']}
                    Workflow.create_workflow(**create_fields)
                else:
                    # Filter out fields not accepted by update_workflow
                    update_fields = {k: v for k, v in w.items() if k in ['title', 'description', 'initial_prompt']}
                    Workflow.update_workflow(w['workflow_id'], **update_fields)