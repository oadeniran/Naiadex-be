import os
from dotenv import load_dotenv
import requests
import json

# Load environment variables from .env file
load_dotenv()

class EnvConfig:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME = os.getenv("DB_NAME", "naiadex")
    OBSERVATIONS_COLLECTION = os.getenv("OBSERVATIONS_COLLECTION", "observations")

config = EnvConfig()

JSON_URL = os.getenv("JSON_URL")
GOOGLE_APP_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "creds.json")

# Download Google vertex Json
# in init_env.py, replace the download block
if JSON_URL:
    response = requests.get(JSON_URL)
    if response.status_code == 200:
        cred_dir = os.path.dirname(GOOGLE_APP_CREDENTIALS)
        if cred_dir:
            os.makedirs(cred_dir, exist_ok=True)
        with open(GOOGLE_APP_CREDENTIALS, "w") as file:
            json.dump(response.json(), file)
