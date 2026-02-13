import os
import datetime
from contextlib import asynccontextmanager
from uuid import uuid4

import bcrypt
import jwt
import psycopg2
import smtplib
from email.message import EmailMessage

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from models import (
    SignupRequest, LoginRequest, UserProfile,
    CreateComment, ForgotPasswordRequest, ResetPasswordRequest,
)
from db import SECRET_KEY, get_db
from util import get_current_user
from feed import fetch_feed, latest_feed
from get_pinecast import get_podcast

TITAN_PW = os.getenv("TITAN_PW")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://funk-27.co.uk")

UPLOAD_DIR = "uploads/profile_pics"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    fetch_feed()
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_feed, "interval", hours=3)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://funk-27.co.uk",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/feed")
def get_feed():
    return latest_feed


@app.get("/")
def read_root():
    return {"Hello": "Funk-27"}


# ---------- AUTH'D PROFILE ----------

@app.get("/me")
def get_my_profile(current_user: dict = Depends(get_current_user)):
    with get_db() as (conn, cur):
        cur.execute(
            """
            SELECT up.*
            FROM users u
            JOIN user_profiles up ON u.id = up.user_id
            WHERE u.id = %s
            """,
            (current_user["id"],),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found.")

        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))


# ---------- UPLOAD PROFILE PICTURE (AUTH ONLY) ----------

@app.post("/upload-profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Only .jpg, .jpeg, .png allowed.")

    file_name = f"{current_user['id']}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    with get_db() as (conn, cur):
        cur.execute(
            "UPDATE user_profiles SET profile_picture = %s WHERE user_id = %s",
            (f"/uploads/profile_pics/{file_name}", current_user["id"]),
        )
        conn.commit()
        return {
            "message": "Profile picture updated",
            "url": f"/uploads/profile_pics/{file_name}",
        }


# ---------- SIGNUP / LOGIN ----------

@app.post("/signup")
def signup(req: SignupRequest):
    hashed = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    with get_db() as (conn, cur):
        try:
            cur.execute(
                """
                INSERT INTO users (email, password_hash)
                VALUES (%s, %s)
                RETURNING id
                """,
                (req.email, hashed),
            )
            user_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO user_profiles (user_id, email)
                VALUES (%s, %s)
                RETURNING user_id, email
                """,
                (user_id, req.email),
            )
            user_profile = cur.fetchone()
            conn.commit()

            payload = {
                "sub": str(user_id),
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

            return {
                "message": "User and profile created successfully.",
                "user_id": str(user_id),
                "access_token": token,
                "token_type": "bearer",
                "profile": {
                    "user_id": str(user_profile[0]),
                    "first_name": "",
                    "last_name": "",
                    "email": req.email,
                    "profile_picture": "",
                },
            }
        except psycopg2.IntegrityError as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"Signup failed: {e}")


@app.post("/login")
def login(req: LoginRequest):
    with get_db() as (conn, cur):
        cur.execute(
            "SELECT id, password_hash FROM users WHERE email = %s",
            (req.email,),
        )
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        user_id, stored_hash = result[0], result[1]
        if not bcrypt.checkpw(req.password.encode("utf-8"), stored_hash.encode("utf-8")):
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        payload = {
            "sub": str(user_id),
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        return {"access_token": token, "token_type": "bearer"}


# ---------- PROFILE ----------

@app.get("/user/{user_id}")
def get_user(user_id: str):
    with get_db() as (conn, cur):
        cur.execute(
            """
            SELECT user_id, first_name, last_name, email, profile_picture, created_at
            FROM user_profiles
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user_id": row[0],
            "first_name": row[1],
            "profile_picture": row[4],
            "created_at": row[5],
        }


@app.patch("/update-user-profile")
def update_user_profile(
    profile_data: UserProfile,
    current_user: dict = Depends(get_current_user),
):
    with get_db() as (conn, cur):
        try:
            cur.execute(
                """
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
                """,
                (
                    profile_data.first_name,
                    profile_data.last_name,
                    profile_data.profile_picture,
                    profile_data.address_line_1,
                    profile_data.address_line_2,
                    profile_data.address_line_3,
                    profile_data.postcode,
                    profile_data.credit_card_encrypted,
                    current_user["id"],
                ),
            )
            conn.commit()
            return {"message": "User profile updated successfully"}
        except psycopg2.Error as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {e}")


# ---------- PASSWORD RESET (EMAIL-BASED TOKEN) ----------

def send_reset_email(to_email, reset_token):
    sender_email = "aid@funk-27.co.uk"
    reset_url = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    msg = EmailMessage()
    msg["Subject"] = "Reset Your Password"
    msg["From"] = sender_email
    msg["To"] = to_email
    msg.set_content(f"Click here to reset your password: {reset_url}")

    with smtplib.SMTP_SSL("smtp.titan.email", 465) as server:
        server.login(sender_email, TITAN_PW)
        server.send_message(msg)


@app.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    with get_db() as (conn, cur):
        cur.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(%s)", (req.email,))
        user = cur.fetchone()

    # Always return 200 to prevent email enumeration
    if user:
        reset_token = jwt.encode(
            {
                "sub": req.email,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30),
            },
            SECRET_KEY,
            algorithm="HS256",
        )
        send_reset_email(req.email, reset_token)

    return {"message": "If this email exists, a reset link has been sent."}


@app.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    try:
        decoded = jwt.decode(req.reset_token, SECRET_KEY, algorithms=["HS256"])
        email = decoded.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")

    hashed = bcrypt.hashpw(req.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    with get_db() as (conn, cur):
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (hashed, email))
        conn.commit()
        return {"message": "Password reset successfully"}


# ---------- COMMENTS ----------

def _fetch_user_comments(user_id: str):
    with get_db() as (conn, cur):
        cur.execute(
            """
            SELECT id, content, created_at, author_name, author_profile_picture, user_id, target_id
            FROM comments
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (user_id,),
        )
        return [
            {
                "id": row[0],
                "content": row[1],
                "created_at": row[2].isoformat(),
                "author_name": row[3],
                "author_profile_picture": row[4],
                "user_id": row[5],
                "target_id": row[6],
            }
            for row in cur.fetchall()
        ]


@app.post("/comments")
def create_comment(
    comment: CreateComment,
    current_user: dict = Depends(get_current_user),
):
    with get_db() as (conn, cur):
        cur.execute(
            """
            SELECT first_name, profile_picture
            FROM user_profiles
            WHERE user_id = %s
            """,
            (current_user["id"],),
        )
        profile = cur.fetchone()

        if not profile:
            raise HTTPException(status_code=400, detail="User profile not found")

        first_name, profile_picture = profile

        if not first_name or not profile_picture:
            raise HTTPException(
                status_code=400,
                detail="You must set a first name and profile picture before posting comments.",
            )

        target_id = comment.target_id.strip()
        if not target_id.startswith("/"):
            target_id = "/" + target_id

        try:
            cur.execute(
                """
                INSERT INTO comments (
                    id, user_id, target_type, target_id, content,
                    author_name, author_profile_picture
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid4()),
                    current_user["id"],
                    comment.target_type,
                    target_id,
                    comment.content,
                    first_name,
                    profile_picture,
                ),
            )
            conn.commit()
            return {"message": "Comment posted", "target_id": target_id}
        except psycopg2.Error as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"Comment failed: {e.pgerror or str(e)}")


@app.get("/comments/me")
def list_my_comments(current_user: dict = Depends(get_current_user)):
    return {"comments": _fetch_user_comments(current_user["id"])}


@app.get("/comments/{target_type}/{target_id:path}")
def list_comments(target_type: str, target_id: str):
    with get_db() as (conn, cur):
        full_target_id = f"/{target_type}/{target_id}"
        cur.execute(
            """
            SELECT user_id, content, created_at, author_name, author_profile_picture
            FROM comments
            WHERE target_id = %s
            ORDER BY created_at DESC
            """,
            (full_target_id,),
        )
        comments = [
            {
                "user_id": row[0],
                "content": row[1],
                "created_at": row[2].isoformat(),
                "author_name": row[3],
                "author_profile_picture": row[4],
            }
            for row in cur.fetchall()
        ]
        return {"comments": comments}


@app.get("/recent_activity/{user_id}")
def list_user_comments(user_id: str):
    return {"comments": _fetch_user_comments(user_id)}


@app.get("/podcast")
def list_podcast_eps():
    return get_podcast()
