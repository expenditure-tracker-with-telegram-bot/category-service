from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from pymongo import MongoClient
from datetime import datetime
from typing import Optional
import logging
import config

category_app = FastAPI()

try:
    client = MongoClient(config.MONGO_URI)
    db = client.get_default_database()
    categories_collection = db.categories
    audit_collection = db.audit_logs
    logging.info("Category Service: Successfully connected to MongoDB.")
except Exception as e:
    logging.error(f"Category Service: Database connection error: {e}")

def get_user_id(x_user_id: str = Header(...)):
    """Dependency to get user ID from the X-User-ID header."""
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is missing.")
    return x_user_id

def log_category_audit(action: str, user_id: str, category_name: str = None, details: dict = None):
    try:
        audit_collection.insert_one({
            'service': 'category', 'action': action, 'user_id': user_id,
            'category_name': category_name, 'details': details, 'timestamp': datetime.utcnow()
        })
    except Exception as e:
        logging.error(f"Category audit logging failed: {e}")

class CategoryCreate(BaseModel):
    name: str
    type: str

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None

class CategoryResponse(BaseModel):
    _id: str
    name: str
    type: str
    user_id: str
    is_system: bool
    created_at: str

@category_app.post("/category", status_code=201)
async def add_category(category: CategoryCreate, user_id: str = Depends(get_user_id)):
    try:
        if categories_collection.find_one({'name': category.name, 'user_id': user_id}):
            raise HTTPException(status_code=409, detail="Category already exists")

        category_data = category.dict()
        category_data.update({
            'user_id': user_id, # Assign to the user from the header
            'is_system': False,
            'created_at': datetime.utcnow()
        })
        result = categories_collection.insert_one(category_data)
        category_id = str(result.inserted_id)
        log_category_audit('CREATE', user_id, category.name, category_data)
        return {'message': 'Category added successfully', 'category_id': category_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@category_app.get("/category")
async def list_categories(user_id: str = Depends(get_user_id)):
    """Lists categories for the specific user + system categories."""
    categories = list(categories_collection.find({'$or': [{'user_id': user_id}, {'is_system': True}]}))
    for cat in categories:
        cat['_id'] = str(cat['_id'])
        cat['created_at'] = cat['created_at'].isoformat()
    return categories

@category_app.put("/category/{name}")
async def update_category(name: str, category_update: CategoryUpdate, user_id: str = Depends(get_user_id)):
    try:
        query = {'name': name, 'user_id': user_id, 'is_system': False}
        if not categories_collection.find_one(query):
            raise HTTPException(status_code=404, detail="Category not found or not created by user")

        update_fields = category_update.model_dump(exclude_unset=True)
        if not update_fields:
            return {'message': 'No fields to update'}

        update_fields['updated_at'] = datetime.utcnow()
        categories_collection.update_one(query, {'$set': update_fields})
        log_category_audit('UPDATE', user_id, name, update_fields)
        return {'message': 'Category updated successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@category_app.delete("/category/{name}")
async def delete_category(name: str, user_id: str = Depends(get_user_id)):
    try:
        query = {'name': name, 'user_id': user_id, 'is_system': False}
        result = categories_collection.delete_one(query)
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Category not found or not created by user")

        log_category_audit('DELETE', user_id, name)
        return {'message': 'Category deleted successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@category_app.get("/category/stats")
async def category_stats(user_id: str = Depends(get_user_id)):
    try:
        pipeline = [
            {'$match': {'user_id': user_id}},
            {'$group': {'_id': '$type', 'count': {'$sum': 1}}}
        ]
        results = list(categories_collection.aggregate(pipeline))
        return {res['_id']: res['count'] for res in results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@category_app.get("/health")
async def health():
    return {'status': 'Category Service running'}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(category_app, host="0.0.0.0", port=5003)