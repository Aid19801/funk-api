from sqlalchemy.orm import Session
from .models import User
from .schemas import UserIn
from .auth import hash_password

def create_user(db: Session, user_in: UserIn):
    hashed_pw = hash_password(user_in.password)
    db_user = User(email=user_in.email, hashed_password=hashed_pw)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter_by(email=email).first()

def get_users(db: Session):
    return db.query(User).all()

def delete_user_by_id(db: Session, user_id: int):
    user = db.query(User).filter_by(id=user_id).first()
    if user:
        db.delete(user)
        db.commit()
    return user
