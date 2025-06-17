# category_service/app.py
from fastapi import FastAPI, HTTPException, Request, Depends
from pymongo import MongoClient
from pydantic import BaseModel
import os
from datetime import datetime
from typing import Optional

app = FastAPI(title="Category Service")

# Configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb+srv://RattanakVicboth:Dambo123@rattanakvicboth.7whe9xy.mongodb.net/ProjDB?retryWrites=true&w=majority&appName=RattanakVicboth')
PORT = int(os.getenv('PORT', 5003))

# Database connection
client = MongoClient(MONGODB_URI)
db = client.get_database()
categories_collection = db.categories

# Initialize system categories
SYSTEM_CATEGORIES = [
    {'name': 'Food', 'type': 'expense', 'system': True},
    {'name': 'Transport', 'type': 'expense', 'system': True},
    {'name': 'Entertainment', 'type': 'expense', 'system': True},
    {'name': 'Salary', 'type': 'income', 'system': True},
    {'name': 'Business', 'type': 'income', 'system': True}
]

# Initialize system categories if not exists
for cat in SYSTEM_CATEGORIES:
    if not categories_collection.find_one({'name': cat['name'], 'system': True}):
        categories_collection.insert_one(cat)

# Pydantic models
class CategoryCreate(BaseModel):
    name: str
    type: str  # 'income' or 'expense'

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None

def get_user_from_headers(request: Request):
    return request.headers.get('x-user', '')

def get_role_from_headers(request: Request):
    return request.headers.get('x-role', '')

@app.get("/health")
def health():
    return {"status": "Category Service running", "port": PORT}

@app.post("/category")
def create_category(category: CategoryCreate, request: Request):
    try:
        user = get_user_from_headers(request)
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Check if category already exists for this user
        existing = categories_collection.find_one({
            'name': category.name,
            '$or': [{'user': user}, {'system': True}]
        })

        if existing:
            raise HTTPException(status_code=409, detail="Category already exists")

        category_data = {
            'name': category.name,
            'type': category.type,
            'user': user,
            'system': False,
            'created_at': datetime.utcnow()
        }

        result = categories_collection.insert_one(category_data)

        return {
            "message": "Category created",
            "id": str(result.inserted_id)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/category")
def list_categories(request: Request):
    try:
        user = get_user_from_headers(request)
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Get both system and user categories
        categories = list(categories_collection.find({
            '$or': [
                {'user': user},
                {'system': True}
            ]
        }))

        # Convert ObjectId to string
        for cat in categories:
            cat['_id'] = str(cat['_id'])
            if 'created_at' in cat:
                cat['created_at'] = cat['created_at'].isoformat()

        return {"categories": categories}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/category/{name}")
def update_category(name: str, category: CategoryUpdate, request: Request):
    try:
        user = get_user_from_headers(request)
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Check if category exists and belongs to user (not system)
        existing = categories_collection.find_one({
            'name': name,
            'user': user,
            'system': False
        })

        if not existing:
            raise HTTPException(status_code=404, detail="Category not found or cannot be modified")

        update_data = {}
        if category.name:
            update_data['name'] = category.name
        if category.type:
            update_data['type'] = category.type

        update_data['updated_at'] = datetime.utcnow()

        categories_collection.update_one(
            {'name': name, 'user': user},
            {'$set': update_data}
        )

        return {"message": "Category updated"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/category/{name}")
def delete_category(name: str, request: Request):
    try:
        user = get_user_from_headers(request)
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")

        result = categories_collection.delete_one({
            'name': name,
            'user': user,
            'system': False
        })

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Category not found or cannot be deleted")

        return {"message": "Category deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/category/stats")
def category_stats(request: Request):
    try:
        user = get_user_from_headers(request)
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")

        pipeline = [
            {
                '$match': {
                    '$or': [
                        {'user': user},
                        {'system': True}
                    ]
                }
            },
            {
                '$group': {
                    '_id': '$type',
                    'count': {'$sum': 1}
                }
            }
        ]

        stats = list(categories_collection.aggregate(pipeline))

        return {"stats": stats}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Admin endpoints
@app.get("/admin/categories")
def admin_all_categories(request: Request):
    try:
        role = get_role_from_headers(request)
        if role != 'Admin':
            raise HTTPException(status_code=403, detail="Admin access required")

        categories = list(categories_collection.find({}))

        for cat in categories:
            cat['_id'] = str(cat['_id'])
            if 'created_at' in cat:
                cat['created_at'] = cat['created_at'].isoformat()

        return {"categories": categories}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)