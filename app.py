from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Body, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import psycopg2
import bcrypt
import jwt  # PyJWT
import datetime
from uuid import uuid4, UUID

from models import SignupRequest, LoginRequest, CreateUserProfile, UserProfile, CreateComment
from db import SECRET_KEY, get_conn
from util import get_current_user  # <-- MUST now decode JWT and return user_id (UUID as str)

app = FastAPI()

# Static files for uploaded images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
UPLOAD_DIR = "uploads/profile_pics"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # "https://yourfrontend.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# def get_conn():
#     return psycopg2.connect(DATABASE_URL)

@app.get("/")
def read_root():
    return {"Hello": "Funk-27"}

# ---------- AUTH’D PROFILE ----------

@app.get("/me")
def get_my_profile(current_user: str = Depends(get_current_user)):
    """
    Returns the current user's profile using user_id from JWT.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
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
    finally:
        cur.close()
        conn.close()

# ---------- UPLOAD PROFILE PICTURE (AUTH ONLY) ----------

@app.post("/upload-profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    print(11111)
    """
    Accepts an image file and saves it as the user's profile picture.
    Uses user_id from JWT; no user_id form field needed.
    """
    # Basic content-type/extension check (JPEG/PNG only)
    file_ext = os.path.splitext(file.filename)[1].lower()
    print(2222)
    if file_ext not in [".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Only .jpg, .jpeg, .png allowed.")

    # Use user_id to name the file (stable, no PII leakage)
    print(3333)
    file_name = f"{current_user['id']}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    # Save file
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Persist relative path in DB
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE user_profiles SET profile_picture = %s WHERE user_id = %s",
            (f"/uploads/profile_pics/{file_name}", current_user["id"]),
        )
        conn.commit()
        return {
            "message": "Profile picture updated",
            "url": f"/uploads/profile_pics/{file_name}",
        }
    finally:
        cur.close()
        conn.close()

# ---------- SIGNUP / LOGIN ----------

@app.post("/signup")
def signup(req: SignupRequest):
    hashed = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = get_conn()
    cur = conn.cursor()
    try:
        # Create user
        cur.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id
            """,
            (req.email, hashed),
        )
        user_id = cur.fetchone()[0]

        # Create blank profile
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

        # JWT now carries user_id
        payload = {
            "sub": str(user_id),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
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
                "profile_picture": "https://t3.ftcdn.net/jpg/11/61/33/44/360_F_1161334476_RF0ScQ0v1KQ5bRyiYIkj0SixXMJUdqly.jpg",
            },
        }
    except psycopg2.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Signup failed: {e}")
    finally:
        cur.close()
        conn.close()

@app.post("/login")
def login(req: LoginRequest):
    """
    Logs in with email/password, returns JWT whose sub=user_id.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
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
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        return {"access_token": token, "token_type": "bearer"}
    finally:
        cur.close()
        conn.close()

# ---------- PROFILE UPDATE (AUTH ONLY) ----------

@app.post("/create-user-profile")
def create_user_profile(data: CreateUserProfile):
    profile = data.user_profile
    conn = get_conn()
    cur = conn.cursor()
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
                profile.first_name,
                profile.last_name,
                profile.profile_picture,
                profile.address_line_1,
                profile.address_line_2,
                profile.address_line_3,
                profile.postcode,
                profile.credit_card_encrypted,
                str(profile.user_id),
            ),
        )
        conn.commit()
        return {"message": "User profile updated successfully"}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Profile update failed: " + str(e))
    finally:
        cur.close()
        conn.close()
@app.get("/user/{user_id}")
def get_user(user_id: str):
    print("used_id ========>> ", user_id)
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT user_id, first_name, last_name, email, profile_picture, created_at
            FROM user_profiles
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        print("row========== >> ", row)
        if not row:
                raise HTTPException(status_code=404, detail="User not found")

        user = {
            "user_id": row[0],
            "first_name": row[1],
            "profile_picture": row[4],
            "created_at": row[5],
        }
        print("returning this ========== >> ", user)
        return user

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        cur.close()
        conn.close()


@app.patch("/update-user-profile")
def update_user_profile(
    profile_data: UserProfile,
    current_user: str = Depends(get_current_user),
):
    conn = get_conn()
    cur = conn.cursor()
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
                (current_user["id"],),
            ),
        )
        conn.commit()
        return {"message": "User profile updated successfully"}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        cur.close()
        conn.close()

# ---------- PASSWORD RESET (EMAIL-BASED TOKEN) ----------

@app.post("/forgot-password")
def forgot_password(email: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Email not found")

        reset_token = jwt.encode(
            {
                "sub": email,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30),
            },
            SECRET_KEY,
            algorithm="HS256",
        )
        # In production, email this token
        return {"reset_token": reset_token}
    finally:
        cur.close()
        conn.close()

@app.post("/reset-password")
def reset_password(token: str = Body(...), new_password: str = Body(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")

    hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (hashed, email))
        conn.commit()
        return {"message": "Password reset successfully"}
    finally:
        cur.close()
        conn.close()

# ---------- COMMENTS ----------

@app.post("/comments")
def create_comment(
    comment: CreateComment,
    current_user: str = Depends(get_current_user),
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO comments (id, user_id, target_type, target_id, content)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                str(uuid4()),
                (current_user["id"],),
                comment.target_type,
                str(comment.target_id),
                comment.content,
            ),
        )
        conn.commit()
        return {"message": "Comment posted"}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Comment failed: " + str(e))
    finally:
        cur.close()
        conn.close()

@app.get("/comments/{target_type}/{target_id}")
def list_comments(target_type: str, target_id: UUID):
    print("========= NO: list_comments firing =======")
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT user_id, content, created_at
            FROM comments
            WHERE target_type = %s AND target_id = %s
            ORDER BY created_at ASC
            """,
            (target_type, str(target_id)),
        )
        rows = cur.fetchall()
        
        return [
            {"user_id": row[0], "content": row[1], "created_at": row[2].isoformat()}
            for row in rows
        ]
    finally:
        cur.close()
        conn.close()

@app.get("/comments/me")
def list_my_comments(current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, content, created_at
            FROM comments
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (current_user["id"],),  # <-- use the UUID string
        )
        rows = cur.fetchall()
        comments = [
            {"id": row[0], "content": row[1], "created_at": row[2].isoformat()}
            for row in rows
        ]
        return {"comments": comments}
    finally:
        cur.close()
        conn.close()

@app.get("/recent_activity/{user_id}")
def list_user_comments(user_id: str):
    print("====== is this even firing tho? ===========")
    conn = get_conn()
    cur = conn.cursor()
    print(2222222)
    try:
        cur.execute(
            """
            SELECT id, content, created_at
            FROM comments
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (user_id,),
        )

        rows = cur.fetchall()

        print("sending this back ====>> ", rows)
        comments = [
            {"id": row[0], "content": row[1], "created_at": row[2].isoformat()}
            for row in rows
        ]
        return {"comments": comments}
    finally:
        cur.close()
        conn.close()