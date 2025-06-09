"""Main Application"""
import os
import logging
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pybloom_live import BloomFilter
from pymongo import MongoClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Vehicle(BaseModel):
    """Model for vehicle data."""
    vehicle_to_check: str

# MongoDB configuration
# MongoDB configuration from environment variables
mongo_host = os.getenv("MONGO_HOST", "mongo")
mongo_port = int(os.getenv("MONGO_PORT", 27017))
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
    # If the collection is empty, create it with some sample data
    if collection.count_documents({}) == 0:
        logger.info("MongoDB collection is empty. Adding sample vehicles.")
        vehicles = []
        for i in range(1000):
            vehicle_number =    f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}-" \
                                f"{random.choice('123456789')}{random.choice('123456789')}-" \
                                f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}-" \
                                f"{random.randint(1000, 9999)}"
            vehicles.append({"vehicle_number": vehicle_number})
        collection.insert_many(vehicles)
        logger.info("Sample vehicles added to MongoDB collection.")
    # Load vehicles from MongoDB into the Bloom filter
    for vehicle in collection.find():
        vehicle_to_add = vehicle['vehicle_number'].encode('utf-8')
        bloom.add(vehicle_to_add)
    logger.info("Bloom filter loaded with vehicles from MongoDB.")
    # disconnect MongoDB client
    # mongo_client.close()
    # Store the bloom filter in the app state
    app.state.bloom = bloom
    yield
    logger.info("Bloom filter loaded successfully.")

# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)
origins = [
    "http://localhost",
    "https://localhost:3000",
    "http://localhost:8050",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow all origins for CORS
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)
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
