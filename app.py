from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Body, Form
from fastapi.staticfiles import StaticFiles
import os
import psycopg2
import bcrypt
import jwt  # PyJWT
from models import SignupRequest, LoginRequest, CreateUserProfile, UserProfile, CreateComment
import datetime
from config import SECRET_KEY, DATABASE_URL
from util import get_current_user
from uuid import uuid4, UUID
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

UPLOAD_DIR = "uploads/profile_pics"
os.makedirs(UPLOAD_DIR, exist_ok=True)

origins = [
    "http://localhost:3000",  # your React dev server
    "http://127.0.0.1:3000",
    # add production frontend URL here when deployed, e.g.:
    # "https://yourfrontend.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # domains allowed
    allow_credentials=True,
    allow_methods=["*"],            # allow all HTTP methods (POST, GET, etc.)
    allow_headers=["*"],            # allow all headers
)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

@app.get("/")
def read_root():
    return {"Hello": "Funk-27"}


@app.get("/me")
def get_my_profile(current_email: str = Depends(get_current_user)):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT up.*
        FROM users u
        JOIN user_profiles up ON u.id = up.user_id
        WHERE u.email = %s
    """, (current_email,))

    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Profile not found.")

    columns = [desc[0] for desc in cur.description]
    profile_dict = dict(zip(columns, row))
    cur.close()
    conn.close()
    return profile_dict

@app.post("/upload-profile-picture")
async def upload_profile_picture(
    user_id: UUID = Form(...),
    file: UploadFile = File(...)
):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # Get the email for this user_id (cast UUID to str)
        cur.execute("SELECT email FROM users WHERE id = %s", (str(user_id),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        
        email = row[0]

        # Build file path
        file_ext = os.path.splitext(file.filename)[1]
        safe_email = email.replace("@", "_at_").replace(".", "_")
        file_name = f"{safe_email}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, file_name)

        # Save the file
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        # Update user profile with relative path (cast UUID to str again)
        cur.execute(
            "UPDATE user_profiles SET profile_picture = %s WHERE user_id = %s",
            (f"/uploads/profile_pics/{file_name}", str(user_id)),
        )
        conn.commit()

        return {
            "message": "Profile picture updated",
            "url": f"/uploads/profile_pics/{file_name}"
        }

    finally:
        cur.close()
        conn.close()




@app.post("/signup")
def signup(req: SignupRequest):
    hashed = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Insert user and return their UUID
        cur.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id
            """,
            (req.email, hashed)
        )
        user_id = cur.fetchone()[0]

        # Create blank user profile and return it
        cur.execute("""
            INSERT INTO user_profiles (user_id, email)
            VALUES (%s, %s)
            RETURNING user_id, email
        """, (user_id, req.email))
        user_profile = cur.fetchone()

        conn.commit()

        # Build JWT
        payload = {
            "sub": req.email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        return {
            "message": "User and profile created successfully.",
            "user_id": user_id,
            "access_token": token,
            "token_type": "bearer",
            "profile": {
                "user_id": user_profile[0],
                # "email": user_profile[1],
                "first_name": "",
                "last_name": "",
                "email": req.email,
                "profile_picture": "https://t3.ftcdn.net/jpg/11/61/33/44/360_F_1161334476_RF0ScQ0v1KQ5bRyiYIkj0SixXMJUdqly.jpg",
            }
        }

    except psycopg2.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Signup failed: {e}")

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


@app.patch("/update-user-profile")
def update_user_profile(
        profile_data: UserProfile,
        current_email: str = Depends(get_current_user)
):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # Get user_id from email
        cur.execute("SELECT id FROM users WHERE email = %s", (current_email,))
        user_row = cur.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found.")

        user_id = user_row[0]

        # Update the profile
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
            profile_data.first_name,
            profile_data.last_name,
            profile_data.profile_picture,
            profile_data.address_line_1,
            profile_data.address_line_2,
            profile_data.address_line_3,
            profile_data.postcode,
            profile_data.credit_card_encrypted,
            user_id
        ))

        conn.commit()
        return {"message": "User profile updated successfully"}

    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    finally:
        cur.close()
        conn.close()

@app.post("/forgot-password")
def forgot_password(email: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    reset_token = jwt.encode(
        {
            "sub": email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        },
        SECRET_KEY,
        algorithm="HS256"
    )

    # TO-DO In production, send this token by email
    return {"reset_token": reset_token}

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

    cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (hashed, email))
    conn.commit()

    cur.close()
    conn.close()

    return {"message": "Password reset successfully"}

@app.post("/comments")
def create_comment(
    comment: CreateComment,
    current_email: str = Depends(get_current_user)
):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # Get the current user_id
        cur.execute("SELECT id FROM users WHERE email = %s", (current_email,))
        user_row = cur.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        user_id = user_row[0]

        # Insert the comment
        cur.execute("""
            INSERT INTO comments (id, user_id, target_type, target_id, content)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            str(uuid4()),  # manually generate UUID in app
            user_id,
            comment.target_type,
            str(comment.target_id),
            comment.content
        ))

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
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, content, created_at
        FROM comments
        WHERE target_type = %s AND target_id = %s
        ORDER BY created_at ASC
    """, (target_type, str(target_id)))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {"user_id": row[0], "content": row[1], "created_at": row[2].isoformat()}
        for row in rows
    ]
