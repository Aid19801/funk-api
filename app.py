from fastapi import FastAPI, HTTPException
import psycopg2
import bcrypt
import os
from dotenv import load_dotenv
import jwt  # PyJWT
from models import SignupRequest, LoginRequest
import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

app = FastAPI()

def get_conn():
    return psycopg2.connect(DATABASE_URL)

@app.post("/signup")
def signup(req: SignupRequest):
    hashed = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
            (req.email, hashed)
        )
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Email already registered.")
    finally:
        cur.close()
        conn.close()

    return {"message": "User registered successfully."}

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/login")
def login(req: LoginRequest):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT password_hash FROM users WHERE email = %s",
        (req.email,)
    )
    result = cur.fetchone()

    cur.close()
    conn.close()

    if not result:
        raise HTTPException(status_code=400, detail="Invalid email or password.")

    stored_hash = result[0]
    if bcrypt.checkpw(req.password.encode('utf-8'), stored_hash.encode('utf-8')):
        # Generate JWT token valid for 1 hour
        payload = {
            "sub": req.email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        print("token", token)
        return {"access_token": token, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=400, detail="Invalid email or password.")
