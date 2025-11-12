from flask import Blueprint, request, jsonify, send_file, abort
import flask_login
from webserver.model import Environment, File, Task
import os, logging, mimetypes, base64
from webserver.csrf import csrf
from webserver.util import is_valid_uuid

env_bp = Blueprint('environments', __name__, url_prefix='/api/environments')

@env_bp.route('', methods=['GET'])
@flask_login.login_required
def list_environments():
    user_id = flask_login.current_user.user_id
    envs = Environment.get_environments_by_user(user_id)
    if not envs:
        Environment.create_environment("Base environment", user_id, description="Your starter workspace")
        envs = Environment.get_environments_by_user(user_id)
    return jsonify({
        "environments": [e.to_dict() for e in envs]
    })

@csrf.exempt
@env_bp.route('', methods=['POST'])
@flask_login.login_required
def create_environment():
    env_data = request.get_json()
    title = env_data.get("title", "New Environment")
    description = env_data.get("description")
    env = Environment.create_environment(
        title, flask_login.current_user.user_id, description
    )
    return jsonify({"environment_id": env.environment_id})

@env_bp.route('/<env_id>', methods=['GET'])
@flask_login.login_required
def get_environment(env_id):
    env = Environment.get_environment(env_id)
    if not env:
        return jsonify({"error": "Environment not found"}), 404
    tasks = Task.get_tasks_by_environment(env_id, flask_login.current_user.user_id)
    files = File.get_files_by_environment(env_id)
    return jsonify({
        "environment": env.to_dict(),
        "tasks": [t.to_dict() for t in tasks],
        "files": [f.to_dict() for f in files]
    })

@csrf.exempt
@env_bp.route('/<env_id>', methods=['DELETE'])
@flask_login.login_required
def delete_environment(env_id):
    if not is_valid_uuid(env_id):
        logging.error(f"Attempted to delete environment with invalid UUID: {env_id}")
        return jsonify({"success": False, "error": "Invalid environment ID"}), 400
    try:
        files = File.get_files_by_environment(env_id)
        for file in files:
            try:
                if file.filepath and os.path.exists(file.filepath):
                    os.remove(file.filepath)
                    logging.info(f"Deleted file from disk: {file.filepath}")
            except Exception as e:
                logging.warning(f"Failed to remove file from disk: {file.filepath}, error: {e}")
        Environment.delete_environment(env_id, flask_login.current_user.user_id)
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Failed to delete environment {env_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@env_bp.route('/<env_id>/files', methods=['GET'])
@flask_login.login_required
def list_files(env_id):
    if not is_valid_uuid(env_id):
        return jsonify({'error': 'Invalid environment ID'}), 400
    files = File.get_files_by_environment(env_id)
    return jsonify({'files': [f.to_dict() for f in files]})

@csrf.exempt
@env_bp.route('/<env_id>/files', methods=['POST'])
@flask_login.login_required
def upload_file(env_id):
    if not is_valid_uuid(env_id):
        return jsonify({'error': 'Invalid environment ID'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    from werkzeug.utils import secure_filename
    import tempfile
    import uuid
    from webserver.storage import GCSFileStorage
    
    filename = secure_filename(file.filename)
    user_id = flask_login.current_user.user_id
    
    # Check for duplicate file before saving
    files = File.get_files_by_environment(env_id)
    duplicate = any(f.filename == filename for f in files)
    if duplicate:
        logging.warning(f"Duplicate file upload attempted: {filename} for environment {env_id} by user {user_id}")
        return jsonify({'error': 'A file with this name already exists in this environment.'}), 409
    
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name
        
        # Upload to GCS
        gcs_storage = GCSFileStorage()
        gcs_path = f"environments/{env_id}/files/{uuid.uuid4()}_{filename}"
        
        # Determine content type
        content_type = file.content_type or 'application/octet-stream'
        
        # Upload to GCS
        gcs_storage.upload_file(temp_path, gcs_path, content_type)
        
        # Clean up temporary file
        os.unlink(temp_path)
        
        # Store file record in database
        File.create_file(
            task_id=None,
            user_id=user_id,
            filename=filename,
            filepath=gcs_path,  # Store GCS path instead of local path
            environment_id=env_id
        )
        
        # Invalidate related caches
        from webserver.cache_manager import cache_manager
        cache_manager.invalidate_file_caches(gcs_path)
        cache_manager.invalidate_query_caches("get_files_by_environment")
        
        logging.info(f"Uploaded file: {filename} for environment {env_id} by user {user_id} to GCS: {gcs_path}")
        return jsonify({'success': True, 'filename': filename})
        
    except Exception as e:
        # Clean up temporary file if it exists
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        logging.error(f"Failed to upload file {filename} to GCS: {e}")

        if 'GCSFileStorage' in str(type(e)):
            error_message = f'Cloud storage error: {str(e)}'
        elif 'Permission' in str(e):
            error_message = f'Permission denied: {str(e)}'
        elif 'Network' in str(e) or 'Connection' in str(e):
            error_message = f'Network error: {str(e)}'
        elif 'Timeout' in str(e):
            error_message = f'Upload timeout: {str(e)}'
        else:
            error_message = f'Upload failed: {str(e)}'
        return jsonify({'error': error_message}), 500

@env_bp.route('/<env_id>/files/<file_id>', methods=['GET'])
@flask_login.login_required
def get_file_info(env_id, file_id):
    if not is_valid_uuid(env_id) or not is_valid_uuid(file_id):
        return jsonify({'error': 'Invalid environment or file ID'}), 400
    file = File.get_file(file_id)
    if not file or str(file.environment_id) != str(env_id):
        return jsonify({'error': 'File not found'}), 404
    return jsonify(file.to_dict())

@csrf.exempt
@env_bp.route('/<env_id>/files/<file_id>', methods=['DELETE'])
@flask_login.login_required
def delete_file(env_id, file_id):
    if not is_valid_uuid(env_id) or not is_valid_uuid(file_id):
        return jsonify({'error': 'Invalid environment or file ID'}), 400
    try:
        file = File.get_file(file_id)
        if not file or str(file.environment_id) != str(env_id):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        # Delete from GCS if it's a GCS path
        if file.filepath and file.filepath.startswith('environments/'):
            try:
                from webserver.storage import GCSFileStorage
                gcs_storage = GCSFileStorage()
                gcs_storage.delete_file(file.filepath)
                logging.info(f"Deleted file from GCS: {file.filepath}")
            except Exception as e:
                logging.warning(f"Failed to remove file from GCS: {e}")
        # Delete from local disk if it's a local path
        elif file.filepath and os.path.exists(file.filepath):
            try:
                os.remove(file.filepath)
                logging.info(f"Deleted file from local disk: {file.filepath}")
            except Exception as e:
                logging.warning(f"Failed to remove file from disk: {e}")
        
        File.delete_file(file_id, flask_login.current_user.user_id)
        
        # Invalidate related caches
        from webserver.cache_manager import cache_manager
        if file.filepath:
            cache_manager.invalidate_file_caches(file.filepath)
        cache_manager.invalidate_query_caches("get_files_by_environment")
        
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Failed to delete file {file_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@env_bp.route('/<env_id>/files/<file_id>/download', methods=['GET'])
@flask_login.login_required
def download_file(env_id, file_id):
    if not is_valid_uuid(env_id) or not is_valid_uuid(file_id):
        return jsonify({'error': 'Invalid environment or file ID'}), 400
    file = File.get_file(file_id)
    if not file or not file.filepath or str(file.environment_id) != str(env_id):
        return abort(404)
    
    # Handle GCS files
    if file.filepath.startswith('environments/'):
        try:
            from webserver.storage import GCSFileStorage
            import tempfile
            
            gcs_storage = GCSFileStorage()
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Download from GCS
            gcs_storage.download_file(file.filepath, temp_path)
            
            # Send file and clean up
            response = send_file(temp_path, as_attachment=True, download_name=file.filename)
            
            # Clean up temp file after response is sent
            @response.call_on_close
            def cleanup():
                try:
                    os.unlink(temp_path)
                except:
                    pass
            
            return response
            
        except Exception as e:
            logging.error(f"Failed to download file from GCS: {e}")
            return abort(404)
    
    # Handle local files
    elif os.path.exists(file.filepath):
        return send_file(file.filepath, as_attachment=True, download_name=file.filename)
    else:
        return abort(404)
