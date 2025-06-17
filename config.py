import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# JWT Secret Key - loaded from environment variable for security
SECRET_KEY = os.getenv('SECRET_KEY')

# MongoDB URI - loaded from environment variable
MONGO_URI = os.getenv('MONGO_URI')