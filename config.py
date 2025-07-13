# category-service/config.py
from dotenv import load_dotenv
import os
import certifi
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv('MONGODB_URI')
DB_NAME = os.getenv('DB_NAME', 'expTracker')
PORT = int(os.getenv('PORT', 5003))

_mongo_client = None
db = None

try:
    _mongo_client = MongoClient(
        MONGODB_URI,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=5000
    )
    db = _mongo_client[DB_NAME]
    _mongo_client.admin.command('ping')
    print("Category Service: MongoDB connection successful.")
except Exception as e:
    print(f"Category Service: FATAL - Could not connect to MongoDB. Error: {e}")

