import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "options": f"-c search_path={os.getenv('DB_SCHEMA')}",
    "password": os.getenv("DB_PASSWORD")
}