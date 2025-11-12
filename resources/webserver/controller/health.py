from flask import Blueprint, jsonify
from datetime import datetime
import logging
from webserver.health_checker import health_checker

health_bp = Blueprint('health', __name__, url_prefix='/api/health')

@health_bp.route("/")
def comprehensive_health():
    """Comprehensive health check endpoint."""
    try:
        # Run all health checks
        results = health_checker.run_all_checks()
        
        # Determine overall status
        overall_status, http_status = health_checker.get_overall_status(results)
        
        # Prepare response
        response = {
            'status': overall_status,
            'http_status': http_status,
            'checks': results,
            'timestamp': datetime.now().isoformat()
        }
        
        # Add cache headers for health checks
        response_obj = jsonify(response)
        response_obj.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response_obj.headers['Pragma'] = 'no-cache'
        response_obj.headers['Expires'] = '0'
        
        return response_obj, http_status
        
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Health check failed: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 503

@health_bp.route("/ready")
def readiness_probe():
    """Kubernetes readiness probe endpoint."""
    try:
        # Only check critical services for readiness
        critical_checks = {
            'database': health_checker._check_database,
            'redis': health_checker._check_redis,
        }
        
        results = {}
        for check_name, check_func in critical_checks.items():
            try:
                result = check_func()
                results[check_name] = result
            except Exception as e:
                results[check_name] = {
                    'status': 'error',
                    'message': str(e),
                    'timestamp': datetime.now().isoformat()
                }
        
        # Check if all critical services are healthy
        all_healthy = all(
            result.get('status') == 'healthy' 
            for result in results.values()
        )
        
        if all_healthy:
            return jsonify({
                'status': 'ready',
                'message': 'All critical services are ready',
                'timestamp': datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                'status': 'not_ready',
                'message': 'Critical services are not ready',
                'checks': results,
                'timestamp': datetime.now().isoformat()
            }), 503
            
    except Exception as e:
        logging.error(f"Readiness probe failed: {e}")
        return jsonify({
            'status': 'not_ready',
            'message': f'Readiness probe failed: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 503

@health_bp.route("/live")
def liveness_probe():
    """Kubernetes liveness probe endpoint."""
    try:
        # Simple check that the application is responding
        return jsonify({
            'status': 'alive',
            'message': 'Application is alive',
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logging.error(f"Liveness probe failed: {e}")
        return jsonify({
            'status': 'dead',
            'message': f'Application is not responding: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 503 