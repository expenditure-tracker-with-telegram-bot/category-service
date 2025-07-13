from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel

from config import db, PORT

app = FastAPI(title="Category Service")

categories_collection = db.categories


class CategoryCreate(BaseModel):
    name: str
    type: str


def get_current_user(request: Request) -> dict:
    username = request.headers.get('X-User-Username')
    role = request.headers.get('X-User-Role')
    if not username:
        raise HTTPException(status_code=401, detail="User identity not found in request")
    return {"username": username, "role": role}


def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.post("/create")
def create_category(category: CategoryCreate, user: dict = Depends(get_current_user)):
    username = user.get('username')
    if categories_collection.find_one({'name': category.name, 'user': username}):
        raise HTTPException(status_code=409, detail="Category already exists")

    new_category = {
        'name': category.name,
        'type': category.type,
        'user': username,
        'created_at': datetime.utcnow()
    }
    result = categories_collection.insert_one(new_category)
    return {"message": "Category created", "id": str(result.inserted_id)}


@app.get("/list")
def list_categories(user: dict = Depends(get_current_user)):
    username = user.get('username')
    categories = list(categories_collection.find({'user': username}))
    for cat in categories:
        cat['_id'] = str(cat['_id'])
    return {"categories": categories}


@app.get("/admin/all")
def admin_all_categories(user: dict = Depends(require_admin)):
    all_categories = list(categories_collection.find({}))
    for cat in all_categories:
        cat['_id'] = str(cat['_id'])
    return {"categories": all_categories}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(PORT))
