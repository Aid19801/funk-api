import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

db_name = os.getenv("DB_NAME")
db_user = os.getenv("DB_USER")
db_pw = os.getenv("DB_PASSWORD")

postgres_db = f"postgresql://{db_user}:{db_pw}@localhost:5432/{db_name}"

engine = create_engine(postgres_db)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()