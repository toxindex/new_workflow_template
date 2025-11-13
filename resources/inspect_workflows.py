#!/usr/bin/env python3
"""
Script to inspect workflows in the database.
Shows the current workflow configurations, especially task_name values.
"""

import json
import sys
import os

try:
    # Add resources directory to path so we can import datastore
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, os.path.dirname(__file__))
    import datastore as ds
except ImportError:
    print("Error: Could not import datastore")
    print("Make sure you're running this from the correct environment with database access")
    sys.exit(1)

def inspect_workflows():
    """Query and display all workflows from the database."""
    try:
        # Query all workflows
        results = ds.find_all("""
            SELECT workflow_id, title, celery_task, task_name, queue, description
            FROM workflows
            ORDER BY workflow_id
        """)
        
        if not results:
            print("No workflows found in database")
            return
        
        print("\n" + "="*100)
        print("WORKFLOWS IN DATABASE")
        print("="*100)
        print(f"\n{'ID':<5} {'Title':<25} {'Celery Task':<20} {'Task Name':<50} {'Queue':<15}")
        print("-"*100)
        
        for row in results:
            # Handle both tuple and dict-like row objects
            if isinstance(row, dict):
                workflow_id = row.get('workflow_id', 0)
                title = row.get('title', '') or ''
                celery_task = row.get('celery_task', '') or ''
                task_name = row.get('task_name', '') or ''
                queue = row.get('queue', '') or ''
            else:
                workflow_id = row[0]
                title = row[1] or ''
                celery_task = row[2] or ''
                task_name = row[3] or ''
                queue = row[4] or ''
            
            # Truncate long values for display
            title = title[:24] if len(title) > 24 else title
            celery_task = celery_task[:19] if len(celery_task) > 19 else celery_task
            task_name = task_name[:49] if len(task_name) > 49 else task_name
            queue = queue[:14] if len(queue) > 14 else queue
            
            print(f"{workflow_id:<5} {title:<25} {celery_task:<20} {task_name:<50} {queue:<15}")
        
        print("\n" + "="*100)
        print("\nDETAILED VIEW FOR WORKFLOW ID 10 (buildKE):")
        print("="*100)
        
        # Get detailed info for workflow 10
        buildke_result = ds.find_all("""
            SELECT workflow_id, title, description, initial_prompt, 
                   celery_task, task_name, queue
            FROM workflows
            WHERE workflow_id = 10
        """)
        
        if buildke_result:
            row = buildke_result[0]
            # Handle both tuple and dict-like row objects
            if isinstance(row, dict):
                db_workflow_id = row.get('workflow_id', 0)
                db_title = row.get('title', '') or ''
                db_description = row.get('description', '') or ''
                db_initial_prompt = row.get('initial_prompt', '') or ''
                db_celery_task = row.get('celery_task', '') or ''
                db_task_name = row.get('task_name', '') or ''
                db_queue = row.get('queue', '') or ''
            else:
                db_workflow_id = row[0]
                db_title = row[1] or ''
                db_description = row[2] or ''
                db_initial_prompt = row[3] or ''
                db_celery_task = row[4] or ''
                db_task_name = row[5] or ''
                db_queue = row[6] or ''
            
            print(f"\nWorkflow ID:     {db_workflow_id}")
            print(f"Title:            {db_title}")
            print(f"Description:      {db_description}")
            print(f"Initial Prompt:   {db_initial_prompt}")
            print(f"Celery Task:      {db_celery_task}")
            print(f"Task Name:        {db_task_name}")
            print(f"Queue:            {db_queue}")
            
            # Compare with JSON
            print("\n" + "="*100)
            print("COMPARISON WITH JSON FILE:")
            print("="*100)
            
            try:
                json_path = os.path.join(os.path.dirname(__file__), "default_workflows.json")
                with open(json_path, 'r') as f:
                    json_data = json.load(f)
                
                json_workflow = None
                for wf in json_data.get('workflows', []):
                    if wf.get('workflow_id') == 10:
                        json_workflow = wf
                        break
                
                if json_workflow:
                    print(f"\nJSON File Values:")
                    print(f"  Celery Task:      {json_workflow.get('celery_task', 'N/A')}")
                    print(f"  Task Name:        {json_workflow.get('task_name', 'N/A')}")
                    print(f"  Queue:            {json_workflow.get('queue', 'N/A')}")
                    
                    print(f"\nDatabase Values:")
                    print(f"  Celery Task:      {db_celery_task}")
                    print(f"  Task Name:        {db_task_name}")
                    print(f"  Queue:            {db_queue}")
                    
                    # Check if they match
                    print(f"\nStatus:")
                    task_name_match = (db_task_name == json_workflow.get('task_name'))
                    celery_task_match = (db_celery_task == json_workflow.get('celery_task'))
                    queue_match = (db_queue == json_workflow.get('queue'))
                    
                    if task_name_match and celery_task_match and queue_match:
                        print("  ✅ All values match JSON file")
                    else:
                        print("  ⚠️  MISMATCH DETECTED:")
                        if not task_name_match:
                            print(f"     - task_name differs!")
                            print(f"       DB:   '{db_task_name}'")
                            print(f"       JSON: '{json_workflow.get('task_name')}'")
                        if not celery_task_match:
                            print(f"     - celery_task differs!")
                            print(f"       DB:   '{db_celery_task}'")
                            print(f"       JSON: '{json_workflow.get('celery_task')}'")
                        if not queue_match:
                            print(f"     - queue differs!")
                            print(f"       DB:   '{db_queue}'")
                            print(f"       JSON: '{json_workflow.get('queue')}'")
                else:
                    print("Workflow ID 10 not found in JSON file")
            except FileNotFoundError:
                print("Could not find resources/default_workflows.json")
            except Exception as e:
                print(f"Error reading JSON: {e}")
        else:
            print("Workflow ID 10 not found in database")
        
        print("\n" + "="*100)
        
    except Exception as e:
        print(f"Database error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    inspect_workflows()

