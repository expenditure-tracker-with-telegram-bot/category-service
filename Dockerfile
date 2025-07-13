# category-service/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Assuming you have a requirements.txt file in this directory
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The port your application will run on
EXPOSE 5003

# The correct command to run a FastAPI app with Gunicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:5003", "app:app"]
