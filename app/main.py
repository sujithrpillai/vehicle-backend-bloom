"""Main Application"""
import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pybloom_live import BloomFilter
from pymongo import MongoClient
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Vehicle(BaseModel):
    """Model for vehicle data."""
    vehicle_to_check: str

# MongoDB configuration
mongo_host = os.getenv("MONGO_HOST", "mongo")
mongo_port = int(os.getenv("MONGO_PORT", "27017"))
mongo_db = os.getenv("MONGO_DB", "vehicle_db")
mongo_collection = os.getenv("MONGO_COLLECTION", "vehicles")
mongo_user = os.getenv("MONGO_USER", "admin")
mongo_password = os.getenv("MONGO_PASSWORD", "admin")

# Initialize MongoDB client
mongo_client = MongoClient(
    host=mongo_host,
    port=mongo_port,
    username=mongo_user,
    password=mongo_password
)
db = mongo_client[mongo_db]
collection = db[mongo_collection]

def lifespan(app: FastAPI):
    """Lifespan event handler to load the bloom filter on startup."""
    logger.info("Loading Bloom filter on startup...")
    # Create Bloom fiter
    bloom = BloomFilter(capacity=1000, error_rate=0.1)
    # Load vehicles from MongoDB into the Bloom filter
    for vehicle in collection.find():
        vehicle_to_add = vehicle['vehicle_number'].encode('utf-8')
        bloom.add(vehicle_to_add)
    logger.info("Bloom filter loaded with vehicles from MongoDB.")
    # disconnect MongoDB client
    mongo_client.close()
    # Store the bloom filter in the app state
    app.state.bloom = bloom
    yield
    logger.info("Bloom filter loaded successfully.")

# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8050",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow all origins for CORS
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint"])
@app.middleware("http")
async def count_requests(request: Request, call_next):
    """Middleware to count HTTP requests."""
    response = await call_next(request)
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path).inc()
    return response

@app.post("/api/check_vehicle/")
def check_vehicle(vehicle: Vehicle):
    """Check if a vehicle is in the Bloom filter."""
    vehicle_to_check = vehicle.vehicle_to_check.encode('utf-8')
    if vehicle_to_check in app.state.bloom:
        return {"vehicle_to_check": vehicle.vehicle_to_check, "status": "yes"}
    else:
        return {"vehicle_to_check": vehicle.vehicle_to_check, "status": "no"}

@app.get("/api/vehicles/")
def get_vehicles():
    """Get all vehicles from the MongoDB."""
    vehicles = []
    for vehicle in collection.find():
        vehicles.append(vehicle['vehicle_number'])
    return {"vehicles": vehicles}

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "message": "Vehicle API is running!"}

@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
