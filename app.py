import jwt
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from config import db, PORT, JWT_SECRET

app = FastAPI(title="Category Service")

categories_collection = db.categories

# System categories that are available to all users
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

# Initialize system categories
for cat in SYSTEM_CATEGORIES:
    if not categories_collection.find_one({'name': cat['name'], 'system': True}):
        cat['created_at'] = datetime.utcnow()
        categories_collection.insert_one(cat)

# Pydantic models
class CategoryCreate(BaseModel):
    name: str
    type: str  # 'income' or 'expense'

    class Config:
        schema_extra = {
            "example": {
                "name": "Groceries",
                "type": "expense"
            }
        }

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None

# Authentication functions
def verify_jwt_token(token: str):
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(request: Request):
    """Get current user from headers (for gateway forwarded requests)"""
    # First try to get from gateway headers
    user = request.headers.get('X-User') or request.headers.get('x-user')
    role = request.headers.get('X-Role') or request.headers.get('x-role')

    if user and role:
        return {'Username': user, 'Role': role}

    # If no gateway headers, try to extract from Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        return verify_jwt_token(token)

    raise HTTPException(status_code=401, detail="Authentication required")

def require_admin(request: Request):
    """Require admin role"""
    user = get_current_user(request)
    if user.get('Role') != 'Admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

@app.get("/health")
def health():
    return {"status": "Category Service running", "port": PORT}

@app.post("/category")
def create_category(category: CategoryCreate, request: Request):
    """Create a new category for the authenticated user"""
    user = get_current_user(request)
    username = user.get('Username')

    if not username:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Validate category type
    if category.type not in ['income', 'expense']:
        raise HTTPException(status_code=400, detail="Category type must be 'income' or 'expense'")

    # Check if category already exists for this user or as system category
    existing = categories_collection.find_one({
        'name': category.name,
        '$or': [{'user': username}, {'system': True}]
    })

    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")

    # Create new category
    category_data = {
        'name': category.name,
        'type': category.type,
        'user': username,
        'system': False,
        'created_at': datetime.utcnow()
    }

    result = categories_collection.insert_one(category_data)

    return {
        "message": "Category created successfully",
        "id": str(result.inserted_id),
        "category": {
            "name": category.name,
            "type": category.type,
            "system": False
        }
    }

@app.get("/category")
def list_categories(request: Request):
    """List all categories available to the authenticated user"""
    user = get_current_user(request)
    username = user.get('Username')

    if not username:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Get both user categories and system categories
    categories = list(categories_collection.find({
        '$or': [{'user': username}, {'system': True}]
    }))

    # Format response
    for cat in categories:
        cat['_id'] = str(cat['_id'])
        if 'created_at' in cat:
            cat['created_at'] = cat['created_at'].isoformat()

    # Sort by system categories first, then alphabetically
    categories.sort(key=lambda x: (not x.get('system', False), x['name']))

    return {"categories": categories}

@app.put("/category/{name}")
def update_category(name: str, category: CategoryUpdate, request: Request):
    """Update a user's category (system categories cannot be updated)"""
    user = get_current_user(request)
    username = user.get('Username')

    if not username:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Find the category (must be user's category, not system)
    existing = categories_collection.find_one({
        'name': name,
        'user': username,
        'system': False
    })

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Category not found or cannot be modified (system categories are read-only)"
        )

    # Validate new category type if provided
    if category.type and category.type not in ['income', 'expense']:
        raise HTTPException(status_code=400, detail="Category type must be 'income' or 'expense'")

    update_data = {}
    if category.name:
        # Check if new name conflicts with existing categories
        name_conflict = categories_collection.find_one({
            'name': category.name,
            '$or': [{'user': username}, {'system': True}],
            '_id': {'$ne': existing['_id']}
        })
        if name_conflict:
            raise HTTPException(status_code=409, detail="Category name already exists")
        update_data['name'] = category.name

    if category.type:
        update_data['type'] = category.type

    update_data['updated_at'] = datetime.utcnow()

    categories_collection.update_one(
        {'name': name, 'user': username},
        {'$set': update_data}
    )

    return {"message": "Category updated successfully"}

@app.delete("/category/{name}")
def delete_category(name: str, request: Request):
    """Delete a user's category (system categories cannot be deleted)"""
    user = get_current_user(request)
    username = user.get('Username')

    if not username:
        raise HTTPException(status_code=401, detail="User not authenticated")

    result = categories_collection.delete_one({
        'name': name,
        'user': username,
        'system': False
    })

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Category not found or cannot be deleted (system categories are protected)"
        )

    return {"message": "Category deleted successfully"}

@app.get("/category/stats")
def category_stats(request: Request):
    """Get category statistics for the authenticated user"""
    user = get_current_user(request)
    username = user.get('Username')

    if not username:
        raise HTTPException(status_code=401, detail="User not authenticated")

    pipeline = [
        {'$match': {'$or': [{'user': username}, {'system': True}]}},
        {'$group': {'_id': '$type', 'count': {'$sum': 1}}}
    ]

    stats = list(categories_collection.aggregate(pipeline))

    # Format stats
    formatted_stats = {
        'income_categories': 0,
        'expense_categories': 0,
        'total_categories': 0
    }

    for stat in stats:
        if stat['_id'] == 'income':
            formatted_stats['income_categories'] = stat['count']
        elif stat['_id'] == 'expense':
            formatted_stats['expense_categories'] = stat['count']
        formatted_stats['total_categories'] += stat['count']

    return {"stats": formatted_stats}

# Admin endpoints
@app.get("/admin/categories")
def admin_all_categories(request: Request):
    """Get all categories (admin only)"""
    require_admin(request)

    categories = list(categories_collection.find({}))

    for cat in categories:
        cat['_id'] = str(cat['_id'])
        if 'created_at' in cat:
            cat['created_at'] = cat['created_at'].isoformat()
        if 'updated_at' in cat:
            cat['updated_at'] = cat['updated_at'].isoformat()

    return {"categories": categories}

@app.get("/admin/categories/stats")
def admin_category_stats(request: Request):
    """Get detailed category statistics (admin only)"""
    require_admin(request)

    total_categories = categories_collection.count_documents({})
    system_categories = categories_collection.count_documents({'system': True})
    user_categories = categories_collection.count_documents({'system': False})

    # Categories by type
    type_pipeline = [
        {'$group': {'_id': '$type', 'count': {'$sum': 1}}}
    ]
    type_stats = list(categories_collection.aggregate(type_pipeline))

    # Recent categories (last 7 days)
    from datetime import timedelta
    recent_date = datetime.utcnow() - timedelta(days=7)
    recent_categories = categories_collection.count_documents({
        'created_at': {'$gte': recent_date},
        'system': False
    })

    return {
        "total_categories": total_categories,
        "system_categories": system_categories,
        "user_categories": user_categories,
        "recent_categories_7d": recent_categories,
        "categories_by_type": type_stats
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
