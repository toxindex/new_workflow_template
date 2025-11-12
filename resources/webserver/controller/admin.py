from flask import Blueprint, request, jsonify
import flask_login
import logging
from webserver.model.user_group import UserGroup
from webserver.model.system_settings import SystemSettings
from webserver.util import is_valid_uuid
import webserver.datastore as ds
from webserver.csrf import csrf
from webserver.cache_manager import cache_manager

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

def require_admin():
    """Decorator to require admin access"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if not flask_login.current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401
            
            user_group = UserGroup.get_user_group(flask_login.current_user.user_id)
            if not user_group or user_group.name != 'admin':
                return jsonify({"error": "Admin access required"}), 403
            
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# ============================================================================
# SYSTEM SETTINGS ENDPOINTS
# ============================================================================

@admin_bp.route('/settings', methods=['GET'])
@flask_login.login_required
@require_admin()
def get_system_settings():
    """Get all system settings"""
    try:
        settings = SystemSettings.get_all_settings()
        return jsonify({
            'success': True,
            'settings': [setting.to_dict() for setting in settings]
        })
    except Exception as e:
        logging.error(f"Error getting system settings: {e}")
        return jsonify({'error': 'Failed to get system settings'}), 500

@admin_bp.route('/settings/<setting_key>', methods=['GET'])
@flask_login.login_required
@require_admin()
def get_system_setting(setting_key):
    """Get a specific system setting"""
    try:
        value = SystemSettings.get_setting(setting_key)
        if value is None:
            return jsonify({'error': 'Setting not found'}), 404
        
        return jsonify({
            'success': True,
            'setting_key': setting_key,
            'setting_value': value
        })
    except Exception as e:
        logging.error(f"Error getting system setting {setting_key}: {e}")
        return jsonify({'error': 'Failed to get system setting'}), 500

@admin_bp.route('/settings/<setting_key>', methods=['PUT'])
@flask_login.login_required
@require_admin()
def update_system_setting(setting_key):
    """Update a system setting"""
    try:
        data = request.get_json()
        if not data or 'setting_value' not in data:
            return jsonify({'error': 'setting_value is required'}), 400
        
        value = data['setting_value']
        description = data.get('description')
        
        # Validate session timeout settings
        if setting_key in ['session_timeout_minutes', 'session_warning_minutes', 'session_refresh_interval_minutes']:
            try:
                int_value = int(value)
                if int_value <= 0:
                    return jsonify({'error': f'{setting_key} must be a positive integer'}), 400
                
                # Additional validation for session settings
                if setting_key == 'session_timeout_minutes' and int_value < 15:
                    return jsonify({'error': 'Session timeout must be at least 15 minutes'}), 400
                if setting_key == 'session_warning_minutes' and int_value >= int_value:
                    return jsonify({'error': 'Warning time must be less than timeout time'}), 400
            except ValueError:
                return jsonify({'error': f'{setting_key} must be a valid integer'}), 400
        
        success = SystemSettings.set_setting(setting_key, value, description)
        if success:
            return jsonify({
                'success': True,
                'message': f'Setting {setting_key} updated successfully'
            })
        else:
            return jsonify({'error': 'Failed to update setting'}), 500
    except Exception as e:
        logging.error(f"Error updating system setting {setting_key}: {e}")
        return jsonify({'error': 'Failed to update system setting'}), 500

@admin_bp.route('/settings/session', methods=['GET'])
@flask_login.login_required
@require_admin()
def get_session_settings():
    """Get session-related settings"""
    try:
        # Get task timeout settings from JSON or individual settings
        task_timeout_json = SystemSettings.get_setting('task_timeout_minutes')
        if task_timeout_json:
            import json
            task_timeouts = json.loads(task_timeout_json)
        else:
            # Fallback to individual settings
            task_timeouts = {
                'toxindex_rap': SystemSettings.get_setting_int('task_timeout_toxindex_rap', 10),
                'toxindex_vanilla': SystemSettings.get_setting_int('task_timeout_toxindex_vanilla', 10),
                'toxindex_json': SystemSettings.get_setting_int('task_timeout_toxindex_json', 10),
                'raptool': SystemSettings.get_setting_int('task_timeout_raptool', 10),
                'pathway_analysis': SystemSettings.get_setting_int('task_timeout_pathway_analysis', 10),
                'default': SystemSettings.get_setting_int('task_timeout_default', 10)
            }
        
        settings = {
            'session_timeout_minutes': SystemSettings.get_setting_int('session_timeout_minutes', 60),
            'session_warning_minutes': SystemSettings.get_setting_int('session_warning_minutes', 5),
            'session_refresh_interval_minutes': SystemSettings.get_setting_int('session_refresh_interval_minutes', 30),
            'task_timeout_minutes': task_timeouts
        }
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        logging.error(f"Error getting session settings: {e}")
        return jsonify({'error': 'Failed to get session settings'}), 500

@admin_bp.route('/settings/session', methods=['PUT'])
@flask_login.login_required
@require_admin()
@csrf.exempt
def update_session_settings():
    """Update session-related settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        # Validate and update session settings
        updates = {}
        for key in ['session_timeout_minutes', 'session_warning_minutes', 'session_refresh_interval_minutes']:
            if key in data:
                try:
                    value = int(data[key])
                    if value <= 0:
                        return jsonify({'error': f'{key} must be a positive integer'}), 400
                    updates[key] = value
                except ValueError:
                    return jsonify({'error': f'{key} must be a valid integer'}), 400
        
        # Validate session timeout vs warning time
        if 'session_timeout_minutes' in updates and 'session_warning_minutes' in updates:
            if updates['session_warning_minutes'] >= updates['session_timeout_minutes']:
                return jsonify({'error': 'Warning time must be less than timeout time'}), 400
        
        # Handle task timeout settings
        if 'task_timeout_minutes' in data:
            task_timeouts = data['task_timeout_minutes']
            if isinstance(task_timeouts, dict):
                # Validate all timeout values
                for key, value in task_timeouts.items():
                    if not isinstance(value, int) or value <= 0:
                        return jsonify({'error': f'Task timeout {key} must be a positive integer'}), 400
                
                # Save as JSON
                import json
                updates['task_timeout_minutes'] = json.dumps(task_timeouts)
        
        # Apply updates
        for key, value in updates.items():
            success = SystemSettings.set_setting(key, value)
            if not success:
                return jsonify({'error': f'Failed to update {key}'}), 500
        
        return jsonify({
            'success': True,
            'message': 'Session settings updated successfully'
        })
    except Exception as e:
        logging.error(f"Error updating session settings: {e}")
        return jsonify({'error': 'Failed to update session settings'}), 500

# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@admin_bp.route('/users', methods=['GET'])
@flask_login.login_required
@require_admin()
def get_all_users():
    """Get all users with their group information (Admin only)"""
    try:
        users = UserGroup.get_all_users_with_groups()
        return jsonify({
            "users": [
                {
                    "user_id": str(user['user_id']),
                    "email": user['email'],
                    "group_name": user.get('group_name', 'No Group'),
                    "group_description": user.get('group_description'),
                    "created_at": user['created_at'].strftime('%Y-%m-%d %H:%M:%S') if user['created_at'] else None
                }
                for user in users
            ]
        })
    except Exception as e:
        logging.error(f"Error getting users: {e}")
        return jsonify({"error": "Failed to get users"}), 500

@admin_bp.route('/users/<user_id>/group', methods=['PUT'])
@flask_login.login_required
@require_admin()
@csrf.exempt
def update_user_group(user_id):
    """Update a user's group (Admin only)"""
    if not is_valid_uuid(user_id):
        return jsonify({"error": "Invalid user ID"}), 400
    
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        
        if not group_id or not is_valid_uuid(group_id):
            return jsonify({"error": "Valid group_id required"}), 400
        
        # Verify the group exists
        group = UserGroup.get_group(group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404
        
        UserGroup.set_user_group(user_id, group_id)
        
        return jsonify({
            "success": True,
            "message": f"User {user_id} assigned to group {group.name}"
        })
    except Exception as e:
        logging.error(f"Error updating user group: {e}")
        return jsonify({"error": "Failed to update user group"}), 500

@admin_bp.route('/groups/<group_id>/users', methods=['GET'])
@flask_login.login_required
@require_admin()
def get_users_in_group(group_id):
    """Get all users in a specific group (Admin only)"""
    if not is_valid_uuid(group_id):
        return jsonify({"error": "Invalid group ID"}), 400
    
    try:
        users = UserGroup.get_users_in_group(group_id)
        return jsonify({
            "users": [
                {
                    "user_id": str(user['user_id']),
                    "email": user['email'],
                    "group_name": user.get('group_name'),
                    "created_at": user['created_at'].strftime('%Y-%m-%d %H:%M:%S') if user['created_at'] else None
                }
                for user in users
            ]
        })
    except Exception as e:
        logging.error(f"Error getting users in group: {e}")
        return jsonify({"error": "Failed to get users in group"}), 500

# ============================================================================
# GROUP MANAGEMENT ENDPOINTS
# ============================================================================

@admin_bp.route('/groups', methods=['GET'])
@flask_login.login_required
@require_admin()
def get_all_groups():
    """Get all user groups (Admin only)"""
    try:
        groups = UserGroup.get_all_groups()
        return jsonify({
            "groups": [group.to_dict() for group in groups]
        })
    except Exception as e:
        logging.error(f"Error getting groups: {e}")
        return jsonify({"error": "Failed to get groups"}), 500

@admin_bp.route('/groups', methods=['POST'])
@flask_login.login_required
@require_admin()
@csrf.exempt
def create_group():
    """Create a new user group (Admin only)"""
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')
        
        if not name:
            return jsonify({"error": "Group name required"}), 400
        
        # Check if group already exists
        existing = UserGroup.get_group_by_name(name)
        if existing:
            return jsonify({"error": "Group with this name already exists"}), 409
        
        group = UserGroup.create_group(name, description)
        if group:
            return jsonify({
                "success": True,
                "group": group.to_dict()
            })
        else:
            return jsonify({"error": "Failed to create group"}), 500
    except Exception as e:
        logging.error(f"Error creating group: {e}")
        return jsonify({"error": "Failed to create group"}), 500

@admin_bp.route('/groups/<group_id>', methods=['PUT'])
@flask_login.login_required
@require_admin()
@csrf.exempt
def update_group(group_id):
    """Update a user group (Admin only)"""
    if not is_valid_uuid(group_id):
        return jsonify({"error": "Invalid group ID"}), 400
    
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')
        
        group = UserGroup.update_group(group_id, name, description)
        if group:
            return jsonify({
                "success": True,
                "group": group.to_dict()
            })
        else:
            return jsonify({"error": "Group not found"}), 404
    except Exception as e:
        logging.error(f"Error updating group: {e}")
        return jsonify({"error": "Failed to update group"}), 500

@admin_bp.route('/groups/<group_id>', methods=['DELETE'])
@flask_login.login_required
@require_admin()
@csrf.exempt
def delete_group(group_id):
    """Delete a user group (Admin only)"""
    if not is_valid_uuid(group_id):
        return jsonify({"error": "Invalid group ID"}), 400
    
    try:
        group = UserGroup.get_group(group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404
        
        # Prevent deletion of admin group
        if group.name == 'admin':
            return jsonify({"error": "Cannot delete admin group"}), 403
        
        UserGroup.delete_group(group_id)
        return jsonify({
            "success": True,
            "message": f"Group {group.name} deleted"
        })
    except Exception as e:
        logging.error(f"Error deleting group: {e}")
        return jsonify({"error": "Failed to delete group"}), 500

# ============================================================================
# WORKFLOW ACCESS MANAGEMENT ENDPOINTS
# ============================================================================

@admin_bp.route('/workflow-access', methods=['GET'])
@flask_login.login_required
@require_admin()
def get_workflow_access():
    """Get workflow access status for all groups and workflows (Admin only)"""
    try:
        # Get all workflows
        from webserver.model.workflow import Workflow
        workflows = Workflow.get_workflows_by_user(None)  # Get all workflows
        
        # Get all groups
        groups = UserGroup.get_all_groups()
        
        # Get all workflow access records
        access_records = ds.find_all("""
            SELECT group_id, workflow_id FROM workflow_group_access
        """)
        
        # Create a set of existing access records for quick lookup
        existing_access = {(str(record['group_id']), record['workflow_id']) for record in access_records}
        
        # Build the response
        access_matrix = []
        for group in groups:
            for workflow in workflows:
                access_matrix.append({
                    'group_id': str(group.group_id),
                    'group_name': group.name,
                    'workflow_id': workflow.workflow_id,
                    'workflow_title': workflow.title,
                    'has_access': (str(group.group_id), workflow.workflow_id) in existing_access
                })
        
        return jsonify({
            "access_matrix": access_matrix,
            "groups": [group.to_dict() for group in groups],
            "workflows": [workflow.to_dict() for workflow in workflows]
        })
    except Exception as e:
        logging.error(f"Error getting workflow access: {e}")
        return jsonify({"error": "Failed to get workflow access"}), 500

@admin_bp.route('/groups/<group_id>/workflows/<int:workflow_id>/access', methods=['POST'])
@flask_login.login_required
@require_admin()
@csrf.exempt
def grant_workflow_access(group_id, workflow_id):
    """Grant a group access to a workflow (Admin only)"""
    if not is_valid_uuid(group_id):
        return jsonify({"error": "Invalid group ID"}), 400
    
    try:
        UserGroup.grant_workflow_access(group_id, workflow_id)
        return jsonify({
            "success": True,
            "message": f"Access granted to workflow {workflow_id}"
        })
    except Exception as e:
        logging.error(f"Error granting workflow access: {e}")
        return jsonify({"error": "Failed to grant workflow access"}), 500

@admin_bp.route('/groups/<group_id>/workflows/<int:workflow_id>/access', methods=['DELETE'])
@flask_login.login_required
@require_admin()
@csrf.exempt
def revoke_workflow_access(group_id, workflow_id):
    """Revoke a group's access to a workflow (Admin only)"""
    if not is_valid_uuid(group_id):
        return jsonify({"error": "Invalid group ID"}), 400
    
    try:
        UserGroup.revoke_workflow_access(group_id, workflow_id)
        return jsonify({
            "success": True,
            "message": f"Access revoked from workflow {workflow_id}"
        })
    except Exception as e:
        logging.error(f"Error revoking workflow access: {e}")
        return jsonify({"error": "Failed to revoke workflow access"}), 500 

@admin_bp.route('/cache/stats', methods=['GET'])
@flask_login.login_required
def get_cache_stats():
    """Get cache statistics for monitoring."""
    try:
        stats = cache_manager.get_cache_stats()
        return jsonify({
            'success': True,
            'cache_stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/cache/clear', methods=['POST'])
@flask_login.login_required
def clear_cache():
    """Clear all caches (admin only)."""
    try:
        # Clear all cache keys
        cache_manager.redis_client.flushdb()
        return jsonify({
            'success': True,
            'message': 'All caches cleared'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 