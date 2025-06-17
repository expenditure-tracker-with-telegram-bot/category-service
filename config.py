from dotenv import load_dotenv
import os
import certifi
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv('MONGODB_URI')
DB_NAME = os.getenv('DB_NAME', 'expTracker')
PORT = int(os.getenv('PORT'))

_mongo_client = MongoClient(
    MONGODB_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000
)

db = _mongo_client[DB_NAME]
JWT_SECRET = os.getenv('JWT_SECRET')
