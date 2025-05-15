from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import User
from app.schemas import UserIn
from app.auth import hash_password, verify_password

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter_by(email=email).first()

def create_user(db: Session, user_in: UserIn):
    is_exists = get_user_by_email(db, user_in.email)
    if is_exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = hash_password(user_in.password)

    db_user = User(email=user_in.email, hashed_password=hashed_pw)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def login_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

def get_users(db: Session):
    return db.query(User).all()

def delete_user_by_id(db: Session, user_id: int):
    user = db.query(User).filter_by(id=user_id).first()
    if user:
        db.delete(user)
        db.commit()
    return user
