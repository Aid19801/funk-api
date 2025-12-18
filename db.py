import psycopg2
from config import DATABASE_URL
from dotenv import load_dotenv
import os

load_dotenv()

# DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

def get_conn():
    return psycopg2.connect(DATABASE_URL)