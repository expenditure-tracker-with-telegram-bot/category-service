import os
import jwt
from flask import Flask, request, jsonify
from flask_restful import Api, Resource
from pymongo import MongoClient
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

# ENV VARS
MONGO_URI = os.getenv("MONGODB_URI")
PORT = int(os.getenv("PORT", 5003))
JWT_SECRET = os.getenv("JWT_SECRET")

client = MongoClient(MONGO_URI)
db = client.get_default_database()
categories_collection = db.categories

SYSTEM_CATEGORIES = [
    {'name': 'Food',         'type': 'expense', 'system': True},
    {'name': 'Transport',    'type': 'expense', 'system': True},
    {'name': 'Entertainment', 'type': 'expense', 'system': True},
    {'name': 'Utilities',    'type': 'expense', 'system': True},
    {'name': 'Healthcare',   'type': 'expense', 'system': True},
    {'name': 'Salary',       'type': 'income',  'system': True},
    {'name': 'Business',     'type': 'income',  'system': True},
    {'name': 'Investment',   'type': 'income',  'system': True},
]

# Init system categories if not present
for cat in SYSTEM_CATEGORIES:
    if not categories_collection.find_one({'name': cat['name'], 'system': True}):
        cat['created_at'] = datetime.utcnow()
        categories_collection.insert_one(cat)

app = Flask(__name__)
api = Api(app)

def verify_jwt_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user():
    user = request.headers.get('X-User')
    role = request.headers.get('X-Role')
    if user and role:
        return {'Username': user, 'Role': role}

    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        payload = verify_jwt_token(token)
        if payload:
            return payload
    return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or 'Username' not in user:
            return jsonify({"error": "Authentication required"}), 401
        return f(user, *args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.get('Role') != 'Admin':
            return jsonify({"error": "Admin access required"}), 403
        return f(user, *args, **kwargs)
    return decorated

@app.route("/health")
def health():
    return jsonify({"status": "Category Service running", "port": PORT})

@app.route("/category", methods=["POST"])
@require_auth
def create_category(user):
    data = request.json
    name = data.get('name')
    type_ = data.get('type')
    username = user.get('Username')

    if type_ not in ['income', 'expense']:
        return jsonify({"error": "Category type must be 'income' or 'expense'"}), 400

    existing = categories_collection.find_one({
        'name': name,
        '$or': [{'user': username}, {'system': True}]
    })

    if existing:
        return jsonify({"error": "Category already exists"}), 409

    category_data = {
        'name': name,
        'type': type_,
        'user': username,
        'system': False,
        'created_at': datetime.utcnow()
    }
    result = categories_collection.insert_one(category_data)

    return jsonify({
        "message": "Category created successfully",
        "id": str(result.inserted_id),
        "category": {
            "name": name,
            "type": type_,
            "system": False
        }
    })

@app.route("/category", methods=["GET"])
@require_auth
def list_categories(user):
    username = user.get('Username')
    categories = list(categories_collection.find({
        '$or': [{'user': username}, {'system': True}]
    }))
    for cat in categories:
        cat['_id'] = str(cat['_id'])
        if 'created_at' in cat:
            cat['created_at'] = cat['created_at'].isoformat()
    categories.sort(key=lambda x: (not x.get('system', False), x['name']))
    return jsonify({"categories": categories})

@app.route("/category/<name>", methods=["PUT"])
@require_auth
def update_category(user, name):
    data = request.json
    username = user.get('Username')
    existing = categories_collection.find_one({
        'name': name,
        'user': username,
        'system': False
    })
    if not existing:
        return jsonify({"error": "Category not found or cannot be modified (system categories are read-only)"}), 404

    update_data = {}
    new_name = data.get('name')
    type_ = data.get('type')
    if type_ and type_ not in ['income', 'expense']:
        return jsonify({"error": "Category type must be 'income' or 'expense'"}), 400
    if new_name:
        conflict = categories_collection.find_one({
            'name': new_name,
            '$or': [{'user': username}, {'system': True}],
            '_id': {'$ne': existing['_id']}
        })
        if conflict:
            return jsonify({"error": "Category name already exists"}), 409
        update_data['name'] = new_name
    if type_:
        update_data['type'] = type_
    update_data['updated_at'] = datetime.utcnow()
    categories_collection.update_one(
        {'name': name, 'user': username},
        {'$set': update_data}
    )
    return jsonify({"message": "Category updated successfully"})

@app.route("/category/<name>", methods=["DELETE"])
@require_auth
def delete_category(user, name):
    username = user.get('Username')
    result = categories_collection.delete_one({
        'name': name,
        'user': username,
        'system': False
    })
    if result.deleted_count == 0:
        return jsonify({"error": "Category not found or cannot be deleted (system categories are protected)"}), 404
    return jsonify({"message": "Category deleted successfully"})

@app.route("/category/stats", methods=["GET"])
@require_auth
def category_stats(user):
    username = user.get('Username')
    pipeline = [
        {'$match': {'$or': [{'user': username}, {'system': True}]}},
        {'$group': {'_id': '$type', 'count': {'$sum': 1}}}
    ]
    stats = list(categories_collection.aggregate(pipeline))
    formatted_stats = {'income_categories': 0, 'expense_categories': 0, 'total_categories': 0}
    for stat in stats:
        if stat['_id'] == 'income':
            formatted_stats['income_categories'] = stat['count']
        elif stat['_id'] == 'expense':
            formatted_stats['expense_categories'] = stat['count']
        formatted_stats['total_categories'] += stat['count']
    return jsonify({"stats": formatted_stats})

# ADMIN ENDPOINTS

@app.route("/admin/categories", methods=["GET"])
@require_admin
def admin_all_categories(user):
    categories = list(categories_collection.find({}))
    for cat in categories:
        cat['_id'] = str(cat['_id'])
        if 'created_at' in cat:
            cat['created_at'] = cat['created_at'].isoformat()
        if 'updated_at' in cat:
            cat['updated_at'] = cat['updated_at'].isoformat()
    return jsonify({"categories": categories})

@app.route("/admin/categories/stats", methods=["GET"])
@require_admin
def admin_category_stats(user):
    total_categories = categories_collection.count_documents({})
    system_categories = categories_collection.count_documents({'system': True})
    user_categories = categories_collection.count_documents({'system': False})
    type_pipeline = [{'$group': {'_id': '$type', 'count': {'$sum': 1}}}]
    type_stats = list(categories_collection.aggregate(type_pipeline))
    recent_date = datetime.utcnow() - timedelta(days=7)
    recent_categories = categories_collection.count_documents({
        'created_at': {'$gte': recent_date},
        'system': False
    })
    return jsonify({
        "total_categories": total_categories,
        "system_categories": system_categories,
        "user_categories": user_categories,
        "recent_categories_7d": recent_categories,
        "categories_by_type": type_stats
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
