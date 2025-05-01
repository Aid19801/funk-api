from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import User, Base

db_name = "users"
db_user = "myapi_user"
db_pw = "&Alpha01"

postgres_db = f"postgresql://{db_user}:{db_pw}@localhost:5432/{db_name}"

engine = create_engine(postgres_db)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# Add a user
new_user = User(email="bigtom@gmail.com", password="<PASSWORD>")
session.add(new_user)
session.commit()
