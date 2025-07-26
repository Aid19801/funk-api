from fastapi import FastAPI, HTTPException
import psycopg2
import bcrypt
import os
from dotenv import load_dotenv
import jwt  # PyJWT
from models import SignupRequest, LoginRequest, CreateUserProfile
import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

app = FastAPI()

def get_conn():
    return psycopg2.connect(DATABASE_URL)

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/signup")
def signup(req: SignupRequest):
    hashed = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Insert user and return their UUID
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
            (req.email, hashed)
        )
        user_id = cur.fetchone()[0]

        # Create blank user profile
        cur.execute("""
            INSERT INTO user_profiles (user_id, email)
            VALUES (%s, %s)
        """, (user_id, req.email))

        conn.commit()
        return {"message": "User and profile created successfully.", "user_id": user_id}

    except psycopg2.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Signup failed: " + str(e))

    finally:
        cur.close()
        conn.close()

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
        payload = {
            "sub": req.email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        return {"access_token": token, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=400, detail="Invalid email or password.")

@app.post("/create-user-profile")
def create_user_profile(data: CreateUserProfile):
    profile = data.user_profile

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE user_profiles SET
                first_name = %s,
                last_name = %s,
                profile_picture = %s,
                address_line_1 = %s,
                address_line_2 = %s,
                address_line_3 = %s,
                postcode = %s,
                credit_card_encrypted = %s
            WHERE user_id = %s
        """, (
            profile.first_name,
            profile.last_name,
            profile.profile_picture,
            profile.address_line_1,
            profile.address_line_2,
            profile.address_line_3,
            profile.postcode,
            profile.credit_card_encrypted,
            profile.user_id
        ))
        conn.commit()
        return {"message": "User profile updated successfully"}

    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Profile update failed: " + str(e))

    finally:
        cur.close()
        conn.close()
