from pymongo import MongoClient
from init_env import config

_client = MongoClient(config.MONGO_URI)
_db = _client[config.DB_NAME]

observations = _db[config.OBSERVATIONS_COLLECTION]
users = _db["users"]
rubric_questions = _db["rubric_questions"]
submissions = _db["submissions"]
sites = _db["sites"]
user_sites = _db["user_sites"]
feedback = _db["feedback"]