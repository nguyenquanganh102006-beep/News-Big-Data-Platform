import os
from dotenv import load_dotenv

load_dotenv()

# env
PRODUCTION_ENV = (os.getenv("PRODUCTION_ENV").lower() == "true")
DEBUG = (os.getenv("DEBUG").lower() == "true")

# Folder structure
PWD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ../../../News-Big-Data-Platform
DATA_DIR = os.path.join(PWD, "data")
DATA_BRONZE_DIR = os.path.join(DATA_DIR, "bronze")
DATA_SILVER_DIR = os.path.join(DATA_DIR, "silver")

# general constants
DEFAULT_STRING = "???"
