import os
import json
from flask_socketio import SocketIO

redis_url = f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/0"
socketio = SocketIO(
    message_queue=redis_url,
    cors_allowed_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://www.toxindex.com",
        "https://toxindex.com"
    ],
    logger=False,
    engineio_logger=False,
    manage_session=False,
    # Optimize polling settings and fix payload issues
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e6,  # Reduced to prevent oversized payloads
    async_mode='gevent',
    # Add error handling for payload issues
    always_connect=True,
    # Increase max payload size but keep reasonable limits
    max_payload_size=1e6,  # Reduced to prevent issues
    # Add compression to reduce payload size
    compression_threshold=512,  # Reduced to compress more aggressively
    # Add better error handling
    cors_credentials=True,
    # Reduce packet fragmentation and set reasonable limits
    max_packet_size=1e5,  # Reduced to prevent oversized packets
    # Add additional settings to prevent payload issues
    json=json,  # Use standard JSON encoder
    # Enable better error handling
    handle_sigint=True,
    # Reduce polling overhead
    cors_headers=["Content-Type", "Authorization"],
    # Enable better packet handling
    allow_upgrades=True
) 