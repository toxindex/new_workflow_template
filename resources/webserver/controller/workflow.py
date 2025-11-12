from flask import Blueprint, jsonify
import flask_login
import json
import logging
from webserver.controller.task_router import get_workflows_file_path
from webserver.model.user_group import UserGroup

workflow_bp = Blueprint('workflows', __name__, url_prefix='/api/workflows')

@workflow_bp.route('/config', methods=['GET'])
@flask_login.login_required
def get_workflows_config():
    """Serve the workflows configuration from resources directory, filtered by user group"""
    try:
        workflows_file = get_workflows_file_path()
        if not workflows_file.exists():
            return jsonify({"error": "Workflows configuration not found"}), 404
        
        with open(workflows_file, 'r') as f:
            data = json.load(f)
        
        # Get user's accessible workflow IDs from database
        user_id = flask_login.current_user.user_id
        try:
            accessible_workflows = UserGroup.get_accessible_workflows(user_id)
            accessible_workflow_ids = {w['workflow_id'] for w in accessible_workflows}
            
            # If no accessible workflows found, check if user is admin
            if not accessible_workflow_ids:
                user_group = UserGroup.get_user_group(user_id)
                if user_group and user_group.name == 'admin':
                    # Admin gets access to all workflows
                    accessible_workflow_ids = {w.get('workflow_id') for w in data.get('workflows', [])}
                    logging.info(f"Admin user {user_id} gets access to all workflows")
                else:
                    logging.warning(f"No accessible workflows found for user {user_id}, group: {user_group.name if user_group else 'None'}")
                    # Return empty workflows list for non-admin users with no access
                    data['workflows'] = []
        except Exception as e:
            logging.error(f"Error getting accessible workflows for user {user_id}: {e}")
            # Fallback: return all workflows for now (this should be fixed by proper database setup)
            accessible_workflow_ids = {w.get('workflow_id') for w in data.get('workflows', [])}
            logging.warning(f"Using fallback - returning all workflows due to error: {e}")
        
        # Filter the workflows list based on database access permissions
        if 'workflows' in data:
            data['workflows'] = [
                w for w in data['workflows'] 
                if w.get('workflow_id') in accessible_workflow_ids
            ]
        
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error reading workflows config: {e}")
        return jsonify({"error": "Failed to load workflows configuration"}), 500

@workflow_bp.route('/list', methods=['GET'])
@flask_login.login_required
def list_workflows():
    """List available workflows for the current user"""
    try:
        from webserver.model.workflow import Workflow
        user_id = flask_login.current_user.user_id
        workflows = Workflow.get_workflows_by_user(user_id)
        return jsonify({"workflows": [w.to_dict() for w in workflows]})
    except Exception as e:
        logging.error(f"Error listing workflows: {e}")
        return jsonify({"error": "Failed to list workflows"}), 500 