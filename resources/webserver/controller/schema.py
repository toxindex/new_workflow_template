from flask import Blueprint, jsonify
from webserver.tools.toxicity_schema import TOXICITY_SCHEMA
from webserver.csrf import csrf

schema_bp = Blueprint('schema', __name__, url_prefix='/api/schema')

@csrf.exempt
@schema_bp.route('/toxicity', methods=['GET'])
def get_toxicity_schema():
    return jsonify(TOXICITY_SCHEMA) 