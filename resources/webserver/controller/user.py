from flask import Blueprint, jsonify, request
from webserver.model.user import User
from webserver.model.user_group import UserGroup
import flask_login
from webserver.csrf import csrf

user_bp = Blueprint('users', __name__, url_prefix='/api/users')

@csrf.exempt
@user_bp.route('/me', methods=['GET'])
@flask_login.login_required
def get_current_user():
    """Get current user's profile information"""
    try:
        user = flask_login.current_user
        print(f"Current user: {user.email}, user_id: {user.user_id}")
        
        user_group = UserGroup.get_user_group(user.user_id)
        print(f"User group: {user_group.name if user_group else 'None'}")
        
        return jsonify({
            'user_id': str(user.user_id),
            'email': user.email,
            'email_verified': user.email_verified,
            'group': {
                'name': user_group.name if user_group else 'basic',
                'description': user_group.description if user_group else 'Basic user'
            },
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
        })
    except Exception as e:
        print(f"Error in get_current_user: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to get user profile'}), 500

@csrf.exempt
@user_bp.route('/<user_id>', methods=['GET'])
@flask_login.login_required
def get_user_by_id(user_id):
    """Get user profile by ID (for viewing other users)"""
    try:
        user = User.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user_group = UserGroup.get_user_group(user_id)
        
        return jsonify({
            'user_id': str(user.user_id),
            'email': user.email,
            'group': {
                'name': user_group.name if user_group else 'basic',
                'description': user_group.description if user_group else 'Basic user'
            },
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
        })
    except Exception as e:
        return jsonify({'error': 'Failed to get user profile'}), 500

@csrf.exempt
@user_bp.route('/me/profile', methods=['PUT'])
@flask_login.login_required
def update_current_user_profile():
    """Update current user's profile information"""
    try:
        user = flask_login.current_user
        data = request.get_json()
        
        # Only allow updating certain fields for security
        allowed_fields = ['email']  # Add more fields as needed
        
        updates = {}
        for field in allowed_fields:
            if field in data:
                updates[field] = data[field]
        
        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Update user fields
        if 'email' in updates:
            new_email = updates['email'].lower().strip()
            if User.user_exists(new_email) and new_email != user.email:
                return jsonify({'error': 'Email already in use'}), 409
            # Update email and reset verification
            User.update_email(user.user_id, new_email)
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
    except Exception as e:
        return jsonify({'error': 'Failed to update profile'}), 500

@csrf.exempt
@user_bp.route('/me/password', methods=['PUT'])
@flask_login.login_required
def update_current_user_password():
    """Update current user's password"""
    try:
        user = flask_login.current_user
        data = request.get_json()
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if not all([current_password, new_password, confirm_password]):
            return jsonify({'error': 'All password fields are required'}), 400
        
        if new_password != confirm_password:
            return jsonify({'error': 'New passwords do not match'}), 400
        
        if len(new_password) < 4:
            return jsonify({'error': 'Password must be at least 4 characters long'}), 400
        
        # Verify current password
        if not user.validate_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        # Update password
        user.set_password(new_password)
        User.update_password(user.user_id, user.hashpw)
        
        return jsonify({'success': True, 'message': 'Password updated successfully'})
    except Exception as e:
        return jsonify({'error': 'Failed to update password'}), 500 