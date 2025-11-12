"""
Shared logging utilities for toxindex components.
Provides consistent Cloud Logging integration across all services.
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


class ResilientCloudLoggingHandler(logging.Handler):
    """
    A Cloud Logging handler that gracefully handles timeouts and connection issues.
    Falls back to local logging if Cloud Logging fails.
    """
    
    def __init__(self, service_name: str, fallback_handler: logging.Handler = None):
        super().__init__()
        self.service_name = service_name
        self.fallback_handler = fallback_handler
        self.cloud_handler = None
        self._setup_cloud_handler()
    
    def _setup_cloud_handler(self):
        """Setup the Cloud Logging handler with proper error handling."""
        try:
            from google.cloud import logging as cloud_logging
            from google.cloud.logging.handlers import CloudLoggingHandler
            
            # Initialize Cloud Logging client with timeout configuration
            client = cloud_logging.Client(
                _http=None,  # Use default HTTP client
                _use_grpc=False  # Use HTTP instead of gRPC to avoid gRPC timeout issues
            )
            
            # Create Cloud Logging handler with custom configuration
            self.cloud_handler = CloudLoggingHandler(
                client, 
                name=self.service_name,
                transport=cloud_logging.handlers.transports.BackgroundThreadTransport(
                    client,
                    batch_size=5,   # Very small batch size to prevent timeouts
                    max_latency=15,  # Short max latency
                    max_workers=1    # Single worker
                )
            )
            self.cloud_handler.setLevel(logging.INFO)
            print(f"✅ Cloud Logging handler created for {self.service_name}")
            
        except Exception as e:
            print(f"⚠️  Failed to create Cloud Logging handler for {self.service_name}: {e}")
            self.cloud_handler = None
    
    def emit(self, record):
        """Emit a log record to Cloud Logging, with fallback to local logging."""
        if self.cloud_handler:
            try:
                # Try to emit to Cloud Logging
                self.cloud_handler.emit(record)
            except Exception as e:
                # If Cloud Logging fails, use fallback handler
                if self.fallback_handler:
                    try:
                        self.fallback_handler.emit(record)
                    except Exception:
                        # If even fallback fails, just pass
                        pass
                print(f"⚠️  Cloud Logging failed for {self.service_name}, using fallback: {e}")
        elif self.fallback_handler:
            # If no Cloud Logging handler, use fallback
            try:
                self.fallback_handler.emit(record)
            except Exception:
                # If fallback fails, just pass
                pass


def setup_logging(
    service_name: str,
    log_level: int = logging.INFO,
    logs_root: Optional[Path] = None
) -> None:
    """
    Setup logging with local file, stdout, and Cloud Logging.
    
    Args:
        service_name: Name of the service (e.g., 'webserver', 'celery-worker', 'redis-listener')
        log_level: Logging level (default: INFO)
        logs_root: Optional custom logs directory path
    """
    # Ensure logs directory exists
    if logs_root is None:
        from webserver.data_paths import LOGS_ROOT
        logs_root = LOGS_ROOT()
    
    logs_root.mkdir(parents=True, exist_ok=True)
    log_filename = logs_root / f"{service_name}_{datetime.now().strftime('%Y-%m-%d_%H')}.log"
    
    # Create local handlers
    file_handler = logging.FileHandler(log_filename)
    stream_handler = logging.StreamHandler()
    
    handlers = [file_handler, stream_handler]
    
    # Add Cloud Logging handler if running in GKE and not disabled
    if os.environ.get("KUBERNETES_SERVICE_HOST") and not os.environ.get("DISABLE_CLOUD_LOGGING"):
        try:
            # Use our resilient Cloud Logging handler
            cloud_handler = ResilientCloudLoggingHandler(
                service_name, 
                fallback_handler=stream_handler
            )
            handlers.append(cloud_handler)
            print(f"✅ Cloud Logging enabled for {service_name} in GKE environment")
        except Exception as e:
            print(f"⚠️  Failed to setup Cloud Logging for {service_name}: {e}")
            # Continue without Cloud Logging - local logging will still work
    else:
        if os.environ.get("DISABLE_CLOUD_LOGGING"):
            print(f"ℹ️  Cloud Logging disabled via DISABLE_CLOUD_LOGGING environment variable")
        else:
            print(f"ℹ️  Running {service_name} locally, Cloud Logging disabled")

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=handlers
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_service_startup(service_name: str, **kwargs):
    """
    Log service startup information.
    
    Args:
        service_name: Name of the service
        **kwargs: Additional key-value pairs to log
    """
    logger = get_logger(service_name)
    logger.info(f"🚀 {service_name} starting up")
    
    # Log environment information
    env_info = {
        "KUBERNETES_SERVICE_HOST": os.environ.get("KUBERNETES_SERVICE_HOST", "Not set"),
        "REDIS_HOST": os.environ.get("REDIS_HOST", "localhost"),
        "REDIS_PORT": os.environ.get("REDIS_PORT", "6379"),
        "PGHOST": os.environ.get("PGHOST", "Not set"),
        "PGPORT": os.environ.get("PGPORT", "5432"),
        "PGDATABASE": os.environ.get("PGDATABASE", "Not set"),
        "PGUSER": os.environ.get("PGUSER", "Not set"),
    }
    
    # Add any additional kwargs
    env_info.update(kwargs)
    
    for key, value in env_info.items():
        logger.info(f"📋 {key}: {value}")


def log_service_shutdown(service_name: str):
    """
    Log service shutdown information.
    
    Args:
        service_name: Name of the service
    """
    logger = get_logger(service_name)
    logger.info(f"🛑 {service_name} shutting down") 