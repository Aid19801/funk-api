from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from . import schemas, crud, auth
from .database import SessionLocal, engine, Base

Base.metadata.create_all(bind=engine)
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return crud.get_users(db)

@app.post("/user", response_model=schemas.UserOut)
def create(db: Session = Depends(get_db), user: schemas.UserIn = ...):
    return crud.create_user(db, user)

@app.post("/login", response_model=schemas.UserOut)
def login(db: Session = Depends(get_db), credentials: schemas.UserIn = ...):
    user = crud.get_user_by_email(db, credentials.email)
    if not user or not auth.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.post("/signup", response_model=schemas.UserOut)
def signup(user: schemas.UserIn, db: Session = Depends(get_db)):
    return crud.create_user(db, user)

@app.delete("/user/{user_id}", response_model=schemas.UserOut)
def delete(user_id: int, db: Session = Depends(get_db)):
    user = crud.delete_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
