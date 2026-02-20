import os
import datetime
from contextlib import asynccontextmanager
from uuid import uuid4

import bcrypt
import jwt
import psycopg2
import smtplib
from email.message import EmailMessage
import cloudinary
import cloudinary.uploader

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from models import (
    SignupRequest, LoginRequest, UserProfile,
    CreateComment, ForgotPasswordRequest, ResetPasswordRequest,
    ContactRequest, PollVoteRequest,
)
from db import SECRET_KEY, get_db
from util import get_current_user, require_superuser
from feed import build_feed_page, refresh_comments_cache, FEED_MAX_PAGES
from get_youtube import fetch_all_youtube, youtube_cache
from get_bluesky import fetch_all_bluesky
from get_pinecast import get_podcast

TITAN_PW = os.getenv("TITAN_PW")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://funk-27.co.uk")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    fetch_all_youtube()
    fetch_all_bluesky()
    refresh_comments_cache()
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_all_youtube, "interval", hours=1)
    scheduler.add_job(fetch_all_bluesky, "interval", hours=1)
    scheduler.add_job(refresh_comments_cache, "interval", minutes=5)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

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
def get_feed(page: int = Query(1, ge=1, le=FEED_MAX_PAGES)):
    return build_feed_page(page)


PAGE_SIZE = 50
MAX_PAGES = 4


@app.get("/youtube")
def get_youtube(page: int = Query(1, ge=1, le=MAX_PAGES)):
    items = youtube_cache["items"]
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    total_pages = min(MAX_PAGES, -(-len(items) // PAGE_SIZE))  # ceil division, capped at 4
    return {
        "items": items[start:end],
        "page": page,
        "total_pages": total_pages,
    }


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

    try:
        result = cloudinary.uploader.upload(
            file.file,
            public_id=str(current_user["id"]),
            folder="profile_pics",
            format="jpg",
            overwrite=True,
            transformation=[{"width": 400, "height": 400, "crop": "fill", "gravity": "face"}],
        )
        url = result["secure_url"]
    except Exception:
        raise HTTPException(status_code=500, detail="Image upload failed.")

    with get_db() as (conn, cur):
        cur.execute(
            "UPDATE user_profiles SET profile_picture = %s WHERE user_id = %s",
            (url, current_user["id"]),
        )
        conn.commit()
        return {
            "message": "Profile picture updated",
            "url": url,
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
            SELECT user_id, first_name, last_name, email, profile_picture, created_at, verified
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
            "verified": row[6],
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


@app.post("/contact")
def contact(req: ContactRequest):
    msg = EmailMessage()
    msg["Subject"] = f"Funk-27 contact from {req.email}"
    msg["From"] = "aid@funk-27.co.uk"
    msg["To"] = "aid@funk-27.co.uk"
    msg["Reply-To"] = req.email
    msg.set_content(f"From: {req.email}\n\n{req.message}")

    try:
        with smtplib.SMTP_SSL("smtp.titan.email", 465) as server:
            server.login("aid@funk-27.co.uk", TITAN_PW)
            server.send_message(msg)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to send message.")

    return {"message": "Message sent."}


@app.get("/podcast")
def list_podcast_eps():
    return get_podcast()


# ---------- POLL ----------

def _poll_response(poll_id, question, yes_votes, no_votes, user_vote):
    total = yes_votes + no_votes
    return {
        "poll_id": str(poll_id),
        "question": question,
        "yes_votes": yes_votes,
        "no_votes": no_votes,
        "total": total,
        "yes_percent": round(yes_votes / total * 100) if total > 0 else 0,
        "no_percent": round(no_votes / total * 100) if total > 0 else 0,
        "user_vote": user_vote,
    }


@app.get("/poll")
def get_poll(request: Request):
    user_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("sub")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass

    with get_db() as (conn, cur):
        cur.execute(
            "SELECT id, question, yes_votes, no_votes FROM polls ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No poll found.")

        poll_id, question, yes_votes, no_votes = row

        user_vote = None
        if user_id:
            cur.execute(
                "SELECT vote FROM poll_votes WHERE poll_id = %s AND user_id = %s",
                (poll_id, user_id),
            )
            vote_row = cur.fetchone()
            if vote_row:
                user_vote = vote_row[0]

        return _poll_response(poll_id, question, yes_votes, no_votes, user_vote)


@app.post("/poll/vote")
def cast_poll_vote(req: PollVoteRequest, current_user: dict = Depends(get_current_user)):
    if req.vote not in ("yes", "no"):
        raise HTTPException(status_code=400, detail="Vote must be 'yes' or 'no'.")

    with get_db() as (conn, cur):
        cur.execute("SELECT id FROM polls ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No active poll.")

        poll_id = row[0]

        try:
            cur.execute(
                "INSERT INTO poll_votes (poll_id, user_id, vote) VALUES (%s, %s, %s)",
                (poll_id, current_user["id"], req.vote),
            )
            if req.vote == "yes":
                cur.execute("UPDATE polls SET yes_votes = yes_votes + 1 WHERE id = %s", (poll_id,))
            else:
                cur.execute("UPDATE polls SET no_votes = no_votes + 1 WHERE id = %s", (poll_id,))
            conn.commit()
        except psycopg2.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=409, detail="You have already voted in this poll.")

        cur.execute("SELECT question, yes_votes, no_votes FROM polls WHERE id = %s", (poll_id,))
        question, yes_votes, no_votes = cur.fetchone()
        return _poll_response(poll_id, question, yes_votes, no_votes, req.vote)


# ---------- ADMIN ----------

@app.patch("/admin/verify-user/{user_id}")
def verify_user(user_id: str, current_user: dict = Depends(require_superuser)):
    with get_db() as (conn, cur):
        cur.execute(
            "UPDATE user_profiles SET verified = TRUE WHERE user_id = %s RETURNING user_id",
            (user_id,),
        )
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="User not found.")
        conn.commit()
        return {"message": f"User {user_id} verified."}
