from flask import Blueprint, jsonify, send_file, abort
import flask_login
from webserver.model.file import File
import os, mimetypes, base64, logging

import json
import pandas as pd
import csv
import io

file_bp = Blueprint('files', __name__, url_prefix='/api/files')

@file_bp.route('', methods=['GET'])
@flask_login.login_required
def get_user_files():
    user_id = flask_login.current_user.user_id
    files = File.get_files_by_user(user_id)
    return jsonify({'files': [f.to_dict() for f in files]})

@file_bp.route('/<file_id>/inspect', methods=['GET'])
@flask_login.login_required
def inspect_file(file_id):
    file = File.get_file(file_id)
    if not file:
        return jsonify({'error': 'File not found'}), 404
    # Optionally, check user ownership here if needed
    if not file.filepath:
        return jsonify({'error': 'File not found'}), 404
    
    # Handle GCS files with caching
    cached_content = None
    if file.filepath.startswith('environments/') or file.filepath.startswith('tasks/'):
        try:
            from webserver.cache_manager import cache_manager
            
            # Try to get content from cache first
            cached_content = cache_manager.get_file_content(file.filepath)
            if not cached_content:
                # Cache miss - download from GCS
                from webserver.storage import GCSFileStorage
                import tempfile
                
                gcs_storage = GCSFileStorage()
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_path = temp_file.name
                
                # Download from GCS
                gcs_storage.download_file(file.filepath, temp_path)
                file.filepath = temp_path  # Use temp path for processing
                
        except Exception as e:
            logging.error(f"Failed to download file from GCS: {e}")
            return jsonify({'error': 'File not found'}), 404
    
    # Handle local files
    elif not os.path.exists(file.filepath):
        return jsonify({'error': 'File not found'}), 404
    ext = os.path.splitext(file.filename)[1].lower()
    mimetype, _ = mimetypes.guess_type(file.filename)

    # supported file types:
    # .txt, .csv, .json, .md, .markdown, .xlsx, .xls, .png, .jpg, .jpeg, .gif
    try:
        if ext in ['.txt', '.csv', '.json', '.md', '.markdown']:
            # If we have cached content from GCS, use it; otherwise read from local path
            if cached_content is not None:
                content = cached_content
            else:
                with open(file.filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            if ext == '.json':
                try:
                    parsed = json.loads(content)
                    return jsonify({'type': 'json', 'content': parsed, 'filename': file.filename, 'mimetype': mimetype})
                except Exception as e:
                    return jsonify({'type': 'text', 'content': content, 'filename': file.filename, 'mimetype': mimetype, 'warning': f'Invalid JSON: {e}'})
            elif ext in ['.md', '.markdown']:
                # Return raw markdown, not HTML
                return jsonify({'type': 'markdown', 'content': content, 'filename': file.filename, 'mimetype': mimetype})
            elif ext == '.csv':
                reader = csv.reader(io.StringIO(content))
                rows = list(reader)
                return jsonify({'type': 'csv', 'content': rows, 'filename': file.filename, 'mimetype': mimetype})
            else:
                return jsonify({'type': 'text', 'content': content, 'filename': file.filename, 'mimetype': mimetype})
        elif ext in ['.xlsx', '.xls']:
            try:
                df = pd.read_excel(file.filepath)
                preview = df.head(100).to_dict(orient='records')
                columns = list(df.columns)
                return jsonify({'type': 'xlsx', 'content': preview, 'columns': columns, 'filename': file.filename, 'mimetype': mimetype})
            except Exception as e:
                return jsonify({'error': f'Failed to parse Excel: {e}', 'type': 'error', 'filename': file.filename, 'mimetype': mimetype}), 400
        elif ext in ['.png', '.jpg', '.jpeg', '.gif']:
            with open(file.filepath, 'rb') as f:
                data = f.read()
            b64 = base64.b64encode(data).decode('utf-8')
            data_url = f"data:{mimetype};base64,{b64}"
            return jsonify({'type': 'image', 'content': data_url, 'filename': file.filename, 'mimetype': mimetype})
        else:
            return jsonify({'error': 'Preview not supported for this file type', 'type': 'unsupported', 'filename': file.filename, 'mimetype': mimetype}), 415
    except Exception as e:
        logging.error(f"[inspect_file] Exception for file_id={file_id}: {e}")
        return jsonify({'error': str(e), 'type': 'error', 'filename': file.filename, 'mimetype': mimetype}), 500

@file_bp.route('/<file_id>/download', methods=['GET'])
@flask_login.login_required
def download_file(file_id):
    file = File.get_file(file_id)
    if not file or not file.filepath:
        return abort(404)
    
    # Handle GCS files with caching
    if file.filepath.startswith('environments/') or file.filepath.startswith('tasks/'):
        try:
            from webserver.storage import GCSFileStorage
            from webserver.cache_manager import cache_manager
            import tempfile
            import hashlib

            gcs_storage = GCSFileStorage()

            # Get file metadata for ETag
            metadata = cache_manager.get_file_metadata(file.filepath)
            etag = metadata.get('md5_hash', '') if metadata else ''


            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_path = temp_file.name

            # Download from GCS BEFORE sending file
            try:
                gcs_storage.download_file(file.filepath, temp_path)
            except Exception as download_exc:
                logging.error(f"GCS download failed for {file.filepath}: {download_exc}")
                return jsonify({'error': f'Failed to download file from GCS: {download_exc}', 'filepath': file.filepath}), 502

            # Now send the file
            response = send_file(temp_path, as_attachment=True, download_name=file.filename)

            # Add HTTP caching headers
            response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
            if etag:
                response.headers['ETag'] = f'"{etag}"'
            import datetime
            if metadata and metadata.get('created'):
                created = metadata['created']
                dt = None
                if isinstance(created, str):
                    # Try parsing as ISO8601 or RFC3339
                    try:
                        # Remove Z and replace with +00:00 for UTC if present
                        iso_str = created.replace('Z', '+00:00') if 'Z' in created else created
                        dt = datetime.datetime.fromisoformat(iso_str)
                    except Exception:
                        try:
                            # Try parsing RFC 1123/2822 (e.g., 'Mon, 23 Sep 2025 19:21:00 GMT')
                            dt = datetime.datetime.strptime(created, '%a, %d %b %Y %H:%M:%S GMT')
                        except Exception:
                            dt = None
                elif hasattr(created, 'strftime'):
                    dt = created
                if dt:
                    response.headers['Last-Modified'] = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
                else:
                    # Fallback: use string as-is (may be non-standard)
                    response.headers['Last-Modified'] = str(created)

            # Clean up temp file after response is sent
            @response.call_on_close
            def cleanup():
                try:
                    os.unlink(temp_path)
                except Exception as cleanup_exc:
                    logging.warning(f"Failed to clean up temp file {temp_path}: {cleanup_exc}")

            return response

        except Exception as e:
            logging.error(f"Failed to download file from GCS (outer exception): {e}")
            return jsonify({'error': f'Unexpected error during GCS file download: {e}', 'filepath': file.filepath}), 500
    
    # Handle local files
    elif os.path.exists(file.filepath):
        response = send_file(file.filepath, as_attachment=True, download_name=file.filename)
        response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
        return response
    else:
        return abort(404) 