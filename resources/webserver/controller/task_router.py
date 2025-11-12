"""
Dynamic task router that reads workflows from JSON to determine which Celery task to run.
This eliminates hardcoded if/elif statements and keeps task routing in sync with workflow definitions.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Import Celery app to send tasks by name to specific queues
from workflows.celery_app import celery as celery_app

logger = logging.getLogger(__name__)


def get_workflows_file_path() -> Path:
    """Get the path to the workflows JSON file"""
    return Path(__file__).parent.parent.parent / "resources" / "default_workflows.json"


def load_workflows() -> Dict[int, Dict[str, Any]]:
    """Load workflows from JSON file"""
    try:
        workflows_file = get_workflows_file_path()
        if not workflows_file.exists():
            logger.error(f"Workflows file not found: {workflows_file}")
            return {}
            
        with open(workflows_file, 'r') as f:
            data = json.load(f)
        
        # Create a mapping by workflow_id for easy lookup
        workflows = {}
        for workflow in data['workflows']:
            workflows[workflow['workflow_id']] = workflow
        
        return workflows
    except Exception as e:
        logger.error(f"Failed to load workflows: {e}")
        return {}

def resolve_task_and_queue(workflow: Dict[str, Any]) -> (str, Optional[str]):
    """Resolve the Celery task name and target queue from the workflow definition.
    - If 'task_name' is present, use it directly as the Celery registered task name.
    - Otherwise, derive a default name as 'workflows.{celery_task}.{celery_task}'.
    - If 'queue' is present, use it; otherwise, omit and let Celery route per task declaration.
    """
    celery_task_key = workflow.get('celery_task')
    if not celery_task_key:
        raise ValueError("Workflow is missing 'celery_task'")

    task_name = workflow.get('task_name')
    if not task_name:
        # Default to the canonical Celery name (module.function)
        task_name = f"workflows.{celery_task_key}.{celery_task_key}"

    queue_name = workflow.get('queue')
    return task_name, queue_name


def route_task(workflow_id: int, task_id: str, user_id: str, message: str = "", file_id: str = None):
    """Route a task to the appropriate Celery task/queue based on workflow_id using only JSON config"""
    workflows = load_workflows()
    workflow = workflows.get(workflow_id)

    if not workflow:
        logger.error(f"No workflow found for workflow_id: {workflow_id}")
        return None

    try:
        task_name, queue_name = resolve_task_and_queue(workflow)
    except Exception as e:
        logger.error(f"Failed to resolve task for workflow_id {workflow_id}: {e}")
        return None

    payload = {
        "task_id": task_id,
        "user_id": user_id,
        "user_query": message,
        "file_id": file_id,
    }

    if not payload:
        logger.error(f"Could not create payload for workflow_id: {workflow_id}")
        return None

    logger.info(
        f"Sending workflow_id {workflow_id} to task '{task_name}'"
        + (f" on queue '{queue_name}'" if queue_name else "")
        + f" with payload: {payload}"
    )

    if queue_name:
        return celery_app.send_task(task_name, args=[payload], queue=queue_name)
    return celery_app.send_task(task_name, args=[payload]) 