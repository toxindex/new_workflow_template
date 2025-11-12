from webserver.model.user import User
from webserver.controller import sendgrid
from webserver import datastore as ds
from webserver.csrf import csrf
from flask import request, jsonify, Blueprint
import flask, flask_login, secrets, datetime, os
import random
import redis
import datetime
import json
import logging
import os
from flask import jsonify, request
import flask_login
from webserver.model import User
from webserver.csrf import csrf
import random

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://toxindex.com')

ERROR_MESSAGES = [
    "Oops! That combo didn't work. Try again?",
    "No luck! Double-check your email and password.",
    "That's not quite right. Give it another shot!",
    "Hmm, those credentials didn't match. Want to try again?",
    "Access denied! But don't give up!",
    "Almost! Check your email and password and try again.",
    "Whoops! That's not the right combo. Try once more?",
    "The login gods say no. Try again?",
    "Not quite! Maybe a typo snuck in?",
    "That didn't work, but you've got this!",
    "Passwords are tricky! Want to try again?",
    "Nope, not this time. But you're getting closer!",
    "The login fairies are not convinced. Try again!",
    "That wasn't it, but persistence pays off!",
    "Keep going! Even the best forget sometimes.",
    "Still locked out! Maybe a coffee break?",
    "Almost cracked it! One more try?",
    "The universe says: not quite. Try again!",
    "You shall not pass... yet! Try again.",
    "Mistakes happen! Give it another go."
]

# Initialize Redis connection for session management
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    decode_responses=True
)

logger = logging.getLogger(__name__)

# Session management constants (defaults, will be overridden by database settings)
DEFAULT_SESSION_TIMEOUT_MINUTES = 15
DEFAULT_SESSION_WARNING_MINUTES = 14
SESSION_KEY_PREFIX = "session:"
SESSION_ACTIVITY_PREFIX = "activity:"

def get_session_settings():
    """Get session settings from database with fallback to defaults."""
    try:
        from webserver.model import SystemSettings
        timeout = SystemSettings.get_setting_int('session_timeout_minutes', DEFAULT_SESSION_TIMEOUT_MINUTES)
        warning = SystemSettings.get_setting_int('session_warning_minutes', DEFAULT_SESSION_WARNING_MINUTES)
        return {
            'timeout_minutes': timeout,
            'warning_minutes': warning
        }
    except Exception as e:
        logger.error(f"Error getting session settings: {e}")
        return {
            'timeout_minutes': DEFAULT_SESSION_TIMEOUT_MINUTES,
            'warning_minutes': DEFAULT_SESSION_WARNING_MINUTES
        }

def get_session_key(user_id: str) -> str:
    """Generate Redis key for user session."""
    return f"{SESSION_KEY_PREFIX}{user_id}"

def get_activity_key(user_id: str) -> str:
    """Generate Redis key for user activity tracking."""
    return f"{SESSION_ACTIVITY_PREFIX}{user_id}"

def update_session_activity(user_id: str):
    """Update user's last activity timestamp in Redis."""
    try:
        settings = get_session_settings()
        activity_key = get_activity_key(user_id)
        redis_client.setex(activity_key, settings['timeout_minutes'] * 60, datetime.datetime.now().isoformat())
        logger.debug(f"Updated activity for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to update activity for user {user_id}: {e}")

def get_session_time_remaining(user_id: str) -> int:
    """Get remaining session time in seconds."""
    try:
        settings = get_session_settings()
        activity_key = get_activity_key(user_id)
        last_activity = redis_client.get(activity_key)
        
        if not last_activity:
            return 0
        
        last_activity_time = datetime.datetime.fromisoformat(last_activity)
        elapsed = (datetime.datetime.now() - last_activity_time).total_seconds()
        remaining = (settings['timeout_minutes'] * 60) - elapsed
        
        return max(0, int(remaining))
    except Exception as e:
        logger.error(f"Failed to get session time remaining for user {user_id}: {e}")
        return 0

def is_session_expired(user_id: str) -> bool:
    """Check if user session has expired."""
    return get_session_time_remaining(user_id) <= 0

def is_session_warning(user_id: str) -> bool:
    """Check if session is in warning state (close to expiry)."""
    try:
        settings = get_session_settings()
        remaining = get_session_time_remaining(user_id)
        return 0 < remaining <= (settings['warning_minutes'] * 60)
    except Exception as e:
        logger.error(f"Error checking session warning: {e}")
        return False

def generate_validation_link(user):
  logger.info(f"Generating validation link for user: {user.user_id}")
  link_token = secrets.token_urlsafe(16)
  expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
  params = (user.user_id, link_token, expiration)
  logger.debug(f"Inserting token {link_token} into user_links")
  ds.execute('INSERT INTO user_links (user_id,link_token,expiration) values (%s,%s,%s)',params)
  return link_token

def generate_password_reset_link(user):
  logger.info(f"Generating password reset link for user: {user.user_id}")
  
  # Clean up any existing expired tokens for this user first
  try:
    ds.execute('DELETE FROM user_links WHERE user_id = (%s) AND expiration < (%s)', (user.user_id, datetime.datetime.now(datetime.timezone.utc)))
  except Exception as e:
    logger.warning(f"Could not clean up expired tokens: {str(e)}")
  
  link_token = secrets.token_urlsafe(16)
  expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)  # Shorter expiration for password reset
  params = (user.user_id, link_token, expiration)
  logger.debug(f"Inserting password reset token {link_token} into user_links")
  ds.execute('INSERT INTO user_links (user_id,link_token,expiration) values (%s,%s,%s)',params)
  return link_token

def validate(user: User):
  logger.info(f"Starting validation for user: {user.email}")
  link = generate_validation_link(user)
  # Use the React SPA route for verification
  route = f"{FRONTEND_URL}/verify/{link}"
  logger.debug(f"Generated verification URL: {route}")
  msg = (
    f"<p>Dear {user.name if user.name else 'User'},</p>"
    "<p>Thank you for registering with Toxindex.com! To complete your registration and activate your account, please click on the link below:</p>"
    f"<p><a href='{route}'><b>Activate My Account</b></a></p>"
    "<p>If you did not request this verification, please ignore this email.</p>"
    "<p>Best regards,<br>The Toxindex Team</p>"
  )
  sendgrid.send(user.email, "Activate Your Toxindex.com Account", msg)

@csrf.exempt
@auth_bp.route('/verification/<token>', methods=['GET'])
def api_verification(token):
    try:
        logger.info(f"Verifying token: {token}")
        token_result = ds.find('SELECT user_id, expiration from user_links WHERE link_token=(%s)', (token,))
        if not token_result:
            logger.warning(f"Invalid token provided: {token}")
            return jsonify({'error': 'Invalid or expired verification token.'}), 400
        
        # Check if token has expired
        if datetime.datetime.now(datetime.timezone.utc) > token_result['expiration']:
            logger.warning(f"Expired token provided: {token}")
            return jsonify({'error': 'Verification token has expired. Please request a new verification email.'}), 400
            
        user_id = token_result['user_id']
        logger.debug(f"Found user_id: {user_id}")
        
        # Check current verification status
        current_status = ds.find('SELECT email_verified FROM users WHERE user_id = (%s)', (user_id,))
        logger.debug(f"Current verification status: {current_status}")
        
        ds.execute('UPDATE users SET email_verified = TRUE WHERE user_id = (%s)', (user_id,))
        logger.info("Updated email_verified to TRUE")
        
        # Verify the update worked
        new_status = ds.find('SELECT email_verified FROM users WHERE user_id = (%s)', (user_id,))
        logger.debug(f"New verification status: {new_status}")
        
        user = User.get(user_id)
        if user is not None:
            logger.info(f"User verified successfully: {user.email}")
            return jsonify({'success': True, 'message': 'Email verified!'})
        
        logger.error("User not found after verification")
        return jsonify({'error': 'Invalid or expired token.'}), 400
    except Exception as e:
        logger.error(f"Verification error: {str(e)}")
        return jsonify({'error': 'Invalid or expired token.'}), 400

@csrf.exempt
@auth_bp.route('/login', methods=['POST'])
def api_login():
    try:
        # Accept both JSON and form data
        if request.is_json:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
        else:
            email = request.form.get('email')
            password = request.form.get('password')

        logger.info(f"Login attempt for email: {email}")

        # Normalize email
        email = email.lower().strip()
        
        user = User.get_user(email)
        if not user:
            logger.warning(f"No user found for email: {email}")
            return jsonify({'error': random.choice(ERROR_MESSAGES)}), 401

        if not user.validate_password(password):
            logger.warning(f"Invalid password for user: {email}")
            return jsonify({'error': random.choice(ERROR_MESSAGES)}), 401

        # Check email verification
        logger.debug(f"Email verification status for {email}: {user.email_verified}")
        
        if email != 'test@test.com' and not user.email_verified:
            return jsonify({
                'error': 'Please verify your email before logging in.',
                'needs_verification': True,
                'message': 'Check your email for a verification link, or use the resend verification option.'
            }), 403

        flask_login.login_user(user)
        
        # Set session as permanent and track creation time for timeout management
        flask.session.permanent = True
        # Ensure timezone-naive datetime for consistency
        created_time = datetime.datetime.now()
        if hasattr(created_time, 'tzinfo') and created_time.tzinfo is not None:
            created_time = created_time.replace(tzinfo=None)
        flask.session['_created'] = created_time
        
        # Initialize Redis session tracking
        update_session_activity(user.user_id)
        
        logger.info(f"Login successful for user: {email}")
        return jsonify({'success': True, 'user_id': user.user_id, 'email': user.email})

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred.'}), 500

@csrf.exempt
@auth_bp.route('/logout', methods=['POST'])
def api_logout():
    try:
        user_email = flask_login.current_user.email if flask_login.current_user.is_authenticated else "unknown"
        flask_login.logout_user()
        flask.session.clear()  # Explicitly clear the session
        logger.info(f"Logout successful for user: {user_email}")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({"success": False, "error": "Logout failed"}), 500

@csrf.exempt
@auth_bp.route('/refresh_session', methods=['POST'])
def api_refresh_session():
    """Refresh the user's session to extend the timeout."""
    try:
        if flask_login.current_user.is_authenticated:
            # Update Redis activity tracking
            update_session_activity(flask_login.current_user.user_id)
            
            # Also update Flask session for compatibility
            flask.session.permanent = True
            created_time = datetime.datetime.now()
            if hasattr(created_time, 'tzinfo') and created_time.tzinfo is not None:
                created_time = created_time.replace(tzinfo=None)
            flask.session['_created'] = created_time
            
            logger.info(f"Session refreshed for user {flask_login.current_user.email}")
            return jsonify({'success': True, 'message': 'Session refreshed'})
        else:
            return jsonify({'error': 'Not authenticated'}), 401
    except Exception as e:
        logger.error(f"Session refresh error: {str(e)}")
        return jsonify({'error': 'Session refresh failed'}), 500

@csrf.exempt
@auth_bp.route('/session_status', methods=['GET'])
def api_session_status():
    """Get current session status including time remaining and warning state."""
    try:
        if not flask_login.current_user.is_authenticated:
            return jsonify({'error': 'Not authenticated'}), 401
        
        user_id = flask_login.current_user.user_id
        time_remaining = get_session_time_remaining(user_id)
        is_warning = is_session_warning(user_id)
        is_expired = is_session_expired(user_id)
        
        return jsonify({
            'success': True,
            'timeRemaining': time_remaining,
            'showWarning': is_warning,
            'isExpired': is_expired,
            'sessionTimeoutMinutes': get_session_settings()['timeout_minutes'],
            'sessionWarningMinutes': get_session_settings()['warning_minutes']
        })
    except Exception as e:
        logger.error(f"Session status error: {e}")
        return jsonify({'error': 'Failed to get session status'}), 500

@csrf.exempt
@auth_bp.route('/update_activity', methods=['POST'])
def api_update_activity():
    """Update user activity timestamp."""
    try:
        if not flask_login.current_user.is_authenticated:
            return jsonify({'error': 'Not authenticated'}), 401
        
        user_id = flask_login.current_user.user_id
        update_session_activity(user_id)
        
        return jsonify({'success': True, 'message': 'Activity updated'})
    except Exception as e:
        logger.error(f"Update activity error: {e}")
        return jsonify({'error': 'Failed to update activity'}), 500

@csrf.exempt
@auth_bp.route('/session_settings', methods=['GET'])
@flask_login.login_required
def api_get_session_settings():
    """Get session settings for the current user (non-admin endpoint)."""
    try:
        from webserver.model.system_settings import SystemSettings
        
        settings = {
            'session_timeout_minutes': get_session_settings()['timeout_minutes'],
            'session_warning_minutes': get_session_settings()['warning_minutes'],
            'session_refresh_interval_minutes': SystemSettings.get_setting_int('session_refresh_interval_minutes', 30)
        }
        
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        logging.error(f"Error getting session settings: {e}")
        return jsonify({'error': 'Failed to get session settings'}), 500

def send_password_reset(email):
  user = User.get_user(email)
  if not user:
    return  # Silently return if user doesn't exist
  link = generate_password_reset_link(user)  # Use dedicated password reset function
  # Use the frontend URL for password reset
  route = f"{FRONTEND_URL}/reset_password/{link}"
  msg = (
    "<p>Hello,</p>"
    "<p>You have requested to reset your password. Click the link below to proceed:</p>"
    f"<p><a href='{route}'><b>Reset My Password</b></a></p>"
    "<p>If you did not request this reset, please ignore this email.</p>"
    "<p>Best regards,<br>The Toxindex Team</p>"
  )
  sendgrid.send(email, "Toxindex.com Password Reset", msg)

@csrf.exempt
@auth_bp.route('/forgot_password', methods=['POST'])
def api_forgot_password():
    data = flask.request.get_json()
    email = data.get('email')
    if not email:
        return flask.jsonify({'success': False, 'error': 'Email is required.'}), 400
    if not User.user_exists(email):
        return flask.jsonify({'success': True})  # Don't reveal if user exists
    try:
        send_password_reset(email)
        return flask.jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error sending password reset: {str(e)}")
        return flask.jsonify({'success': False, 'error': 'Failed to send reset email.'}), 500

@csrf.exempt
@auth_bp.route('/reset_password/<token>', methods=['POST'])
def api_reset_password(token):
    logger.info(f"Password reset request for token: {token}")
    try:
        data = flask.request.get_json()
        logger.debug(f"Request data: {data}")
        if not data:
            logger.warning("No request body provided")
            return flask.jsonify({'error': 'Request body is required.'}), 400
            
        password = data.get('password')
        if not password:
            logger.warning("No password provided in request")
            return flask.jsonify({'success': False, 'error': 'Password is required.'}), 400
        
        # Password validation
        if len(password) < 4:
            logger.warning(f"Password too short: {len(password)} characters")
            return flask.jsonify({'success': False, 'error': 'Password must be at least 4 characters long.'}), 400

        # Get user from token and check expiration
        try:
            logger.info(f"Looking up token: {token}")
            token_result = ds.find('SELECT user_id, expiration from user_links WHERE link_token=(%s)', (token,))
            logger.debug(f"Token lookup result: {token_result}")
            
            if not token_result:
                logger.warning(f"No token found for: {token}")
                return flask.jsonify({'error': 'Invalid or expired reset token. Please request a new password reset.'}), 400
            
            # Check if token has expired
            current_time = datetime.datetime.now(datetime.timezone.utc)
            expiration_time = token_result['expiration']
            logger.debug(f"Current time: {current_time}, Token expires: {expiration_time}")
            
            if current_time > expiration_time:
                logger.warning(f"Token expired: {token}")
                return flask.jsonify({'error': 'Reset token has expired. Please request a new password reset.'}), 400
                
            user_id = token_result['user_id']
            logger.debug(f"Token valid for user_id: {user_id}")
        except Exception as e:
            logger.error(f"Database error during token lookup: {str(e)}")
            import traceback
            logger.error(f"Token lookup traceback: {traceback.format_exc()}")
            return flask.jsonify({'error': f'Database error during token verification: {str(e)}'}), 500

        # Get user
        try:
            user = User.get(user_id)
            if user is None:
                return flask.jsonify({'error': 'User account not found. Please contact support.'}), 400
        except Exception as e:
            logger.error(f"Database error during user lookup: {str(e)}")
            import traceback
            logger.error(f"User lookup traceback: {traceback.format_exc()}")
            return flask.jsonify({'error': f'Database error during user lookup: {str(e)}'}), 500

        # Create hashed password using User model's method
        try:
            user.set_password(password)
            User.update_password(user_id, user.hashpw)
            
            # Auto-verify email since they received the reset link via email
            if not user.email_verified:
                logger.info(f"Auto-verifying email for user: {user.email} after password reset")
                ds.execute('UPDATE users SET email_verified = TRUE WHERE user_id = (%s)', (user_id,))
                user.email_verified = True
        except Exception as e:
            logger.error(f"Database error during password update: {str(e)}")
            import traceback
            logger.error(f"Password update traceback: {traceback.format_exc()}")
            return flask.jsonify({'error': f'Database error during password update: {str(e)}'}), 500
        
        # Log the user in
        try:
            flask_login.login_user(user)
        except Exception as e:
            logger.warning(f"Login error after password reset: {str(e)}")
            # Don't fail the entire operation if login fails, but log it
            pass
        
        # Clean up used token
        try:
            ds.execute('DELETE FROM user_links WHERE link_token = (%s)', (token,))
            logger.info(f"Successfully cleaned up used token: {token}")
        except Exception as e:
            logger.warning(f"Could not clean up used token: {str(e)}")
            # Don't fail the operation for this
        
        logger.info(f"Password reset successful for user: {user.email}")
        return flask.jsonify({'success': True})
    except Exception as e:
        logger.error(f"Unexpected password reset error: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return flask.jsonify({'error': 'An unexpected error occurred. Please try again or contact support if the problem persists.'}), 500

@csrf.exempt
@auth_bp.route('/resend_verification', methods=['POST'])
def api_resend_verification():
    """Resend email verification for unverified users"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({'error': 'Request body is required.'}), 400
            
        email = data.get('email')
        if not email:
            return flask.jsonify({'error': 'Email is required.'}), 400
        
        # Normalize email
        email = email.lower().strip()
        
        # Check if user exists
        user = User.get_user(email)
        if not user:
            logger.warning(f"Resend verification requested for non-existent user: {email}")
            # Don't reveal if user exists or not for security
            return flask.jsonify({'success': True, 'message': 'If an account with this email exists, a verification email has been sent.'})
        
        # Check if already verified
        if user.email_verified:
            logger.info(f"Resend verification requested for already verified user: {email}")
            return flask.jsonify({'success': True, 'message': 'This email is already verified.'})
        
        # Use the existing validate function to resend verification
        try:
            validate(user)
            logger.info(f"Verification email resent for user: {email}")
            return flask.jsonify({'success': True, 'message': 'Verification email sent successfully.'})
        except Exception as e:
            logger.error(f"Error sending verification email to {email}: {str(e)}")
            return flask.jsonify({'error': 'Failed to send verification email. Please try again.'}), 500
            
    except Exception as e:
        logger.error(f"Unexpected error in resend verification: {str(e)}")
        return flask.jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500

@csrf.exempt
@auth_bp.route('/register', methods=['POST'])
def api_register():
    try:
        # Accept both JSON and form data
        if request.is_json:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
            password_confirmation = data.get('password_confirmation')
        else:
            email = request.form.get('email')
            password = request.form.get('password')
            password_confirmation = request.form.get('password_confirmation')

        logger.info(f"Registration attempt for email: {email}")

        # Validate input
        if not email or not password or not password_confirmation:
            return jsonify({'error': 'All fields are required.'}), 400

        # Email validation
        email = email.lower().strip()  # Normalize email
        if len(email) < 6 or '@' not in email or '.' not in email:
            return jsonify({'error': 'Please enter a valid email address.'}), 400

        # Password validation
        if len(password) < 4:
            return jsonify({'error': 'Password must be at least 4 characters long.'}), 400
        if password != password_confirmation:
            return jsonify({'error': 'Passwords do not match.'}), 400

        # Check if user exists
        if User.user_exists(email):
            return jsonify({'error': 'Email already registered.'}), 409

        # Create user
        try:
            user = User.create_user(email, password)
        except Exception as e:
            logger.error(f"create_user raised: {str(e)}")
            return jsonify({'error': 'Failed to create user (internal error). Please try again.'}), 500
        
        if user is None:
            logger.error("create_user returned None (likely swallowed exception)")
            return jsonify({'error': 'Failed to create user.'}), 500

        logger.info(f"User created successfully, proceeding to validation")
        
        # Send verification email
        try:
            validate(user)
        except Exception as e:
            logger.error(f"Failed to send verification email: {str(e)}")
            # Don't fail registration if email fails, just notify the user
            return jsonify({
                'success': True,
                'message': 'Account created, but verification email could not be sent. Please contact support.'
            })

        return jsonify({
            'success': True,
            'message': 'Check your email to verify your account.'
        })

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'Registration failed. Please try again.'}), 500