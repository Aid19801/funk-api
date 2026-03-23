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

import stripe

from models import (
    SignupRequest, LoginRequest, UserProfile,
    CreateComment, ForgotPasswordRequest, ResetPasswordRequest,
    ContactRequest, PollVoteRequest, LicenceValidateRequest,
)
from db import SECRET_KEY, get_db
from util import get_current_user, require_superuser, SUPERUSER_ID
from feed import build_feed_page, refresh_comments_cache, FEED_MAX_PAGES
from get_youtube import fetch_all_youtube, youtube_cache, fetch_video_details, fetch_single_video
from get_bluesky import fetch_all_bluesky
from get_pinecast import get_podcast

TITAN_PW = os.getenv("TITAN_PW")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://funk-27.co.uk")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

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


@app.get("/youtube/{video_id}/details")
def get_youtube_video_details(video_id: str):
    return fetch_video_details(video_id)


@app.get("/youtube/{video_id}")
def get_single_youtube_video(video_id: str):
    video = fetch_single_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


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
        profile = dict(zip(columns, row))
        profile["is_superuser"] = str(current_user["id"]) == SUPERUSER_ID
        return profile


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
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
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
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
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


# ---------- SEARCH ----------

@app.get("/search")
def search(q: str = Query(..., min_length=1)):
    q_lower = q.lower()
    results = []

    # Podcast episodes (fetched live from Pinecast RSS)
    try:
        for ep in get_podcast():
            title = ep.get("title", "") or ""
            summary = ep.get("summary", "") or ""
            if q_lower in title.lower() or q_lower in summary.lower():
                guid = ep.get("id", "")
                idx = guid.find("/guid/")
                if idx != -1:
                    uuid = guid[idx + 6:]
                    img = None
                    image = ep.get("image")
                    if image:
                        img = image.get("href") if isinstance(image, dict) else getattr(image, "href", None)
                    results.append({
                        "type": "podcast",
                        "title": title,
                        "description": summary[:200],
                        "image": img,
                        "slug": f"/posts/podcast/{uuid}",
                        "published_at": ep.get("published"),
                    })
    except Exception:
        pass

    # YouTube videos (from in-memory cache)
    for video in youtube_cache.get("items", []):
        title = video.get("title", "") or ""
        text = video.get("text", "") or ""
        if q_lower in title.lower() or q_lower in text.lower():
            results.append({
                "type": "youtube",
                "title": title,
                "description": text[:200],
                "image": video.get("image"),
                "slug": f"/posts/youtube/{video['id']}",
                "published_at": video.get("published_at"),
            })

    # Comments + Users (single DB connection)
    with get_db() as (conn, cur):
        cur.execute(
            """
            SELECT content, created_at, author_name, author_profile_picture, target_id
            FROM comments
            WHERE content ILIKE %s OR author_name ILIKE %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (f"%{q}%", f"%{q}%"),
        )
        for row in cur.fetchall():
            results.append({
                "type": "comment",
                "title": row[2] or "Anonymous",
                "description": row[0][:200] if row[0] else "",
                "image": row[3],
                "slug": row[4],
                "published_at": row[1].isoformat() if row[1] else None,
            })

        cur.execute(
            """
            SELECT user_id, first_name, last_name, profile_picture
            FROM user_profiles
            WHERE first_name ILIKE %s OR last_name ILIKE %s
            LIMIT 10
            """,
            (f"%{q}%", f"%{q}%"),
        )
        for row in cur.fetchall():
            name = " ".join(filter(None, [row[1] or "", row[2] or ""])).strip() or "Unknown"
            results.append({
                "type": "user",
                "title": name,
                "description": "",
                "image": row[3],
                "slug": f"/user/{row[0]}",
                "published_at": None,
            })

    return {
        "results": results[:10],
        "query": q,
        "total": len(results),
    }


# ---------- POLL ----------

def _poll_response(poll_id, question, options, user_vote):
    total = sum(o["votes"] for o in options)
    for o in options:
        o["percent"] = round(o["votes"] / total * 100) if total > 0 else 0
    return {
        "poll_id": str(poll_id),
        "question": question,
        "options": options,
        "total": total,
        "user_vote": user_vote,
    }


def _fetch_options(cur, poll_id):
    cur.execute(
        "SELECT id, label, vote_count FROM poll_options WHERE poll_id = %s ORDER BY display_order",
        (poll_id,),
    )
    return [{"id": str(r[0]), "label": r[1], "votes": r[2]} for r in cur.fetchall()]


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
            "SELECT id, question FROM polls ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No poll found.")

        poll_id, question = row
        options = _fetch_options(cur, poll_id)

        user_vote = None
        if user_id:
            cur.execute(
                """SELECT po.label FROM poll_votes pv
                   JOIN poll_options po ON po.id = pv.option_id
                   WHERE pv.poll_id = %s AND pv.user_id = %s""",
                (poll_id, user_id),
            )
            vote_row = cur.fetchone()
            if vote_row:
                user_vote = vote_row[0]

        return _poll_response(poll_id, question, options, user_vote)


@app.post("/poll/vote")
def cast_poll_vote(req: PollVoteRequest, current_user: dict = Depends(get_current_user)):
    with get_db() as (conn, cur):
        cur.execute("SELECT id, question FROM polls ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No active poll.")

        poll_id, question = row

        cur.execute(
            "SELECT id, label FROM poll_options WHERE id = %s AND poll_id = %s",
            (req.option_id, poll_id),
        )
        option_row = cur.fetchone()
        if not option_row:
            raise HTTPException(status_code=400, detail="Invalid option for this poll.")

        option_id, option_label = option_row

        try:
            cur.execute(
                "INSERT INTO poll_votes (poll_id, user_id, option_id) VALUES (%s, %s, %s)",
                (poll_id, current_user["id"], option_id),
            )
            cur.execute(
                "UPDATE poll_options SET vote_count = vote_count + 1 WHERE id = %s",
                (option_id,),
            )
            conn.commit()
        except psycopg2.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=409, detail="You have already voted in this poll.")

        options = _fetch_options(cur, poll_id)
        return _poll_response(poll_id, question, options, option_label)


# ---------- VIDEO BASTARD LICENCES ----------

def _generate_licence_key() -> str:
    import secrets
    groups = [secrets.token_hex(2).upper() for _ in range(4)]
    return "-".join(groups)


def _send_licence_email(to_email: str, licence_key: str):
    msg = EmailMessage()
    msg["Subject"] = "Your Video Bastard licence key"
    msg["From"] = "aid@funk-27.co.uk"
    msg["To"] = to_email
    msg.set_content(
        f"Thanks for subscribing to Video Bastard!\n\n"
        f"Your licence key is:\n\n  {licence_key}\n\n"
        f"Open the app, click 'Activate', and paste this key.\n\n"
        f"Download: https://github.com/Aid19801/video-bastard/releases\n"
    )
    with smtplib.SMTP_SSL("smtp.titan.email", 465) as server:
        server.login("aid@funk-27.co.uk", TITAN_PW)
        server.send_message(msg)


def _resolve_email_from_stripe(obj: dict) -> tuple[str | None, str | None, str | None]:
    """Return (email, customer_id, subscription_id) from a Stripe event object."""
    customer_email = (
        obj.get("customer_email")
        or (obj.get("customer_details") or {}).get("email")
    )
    customer_id = obj.get("customer")
    subscription_id = obj.get("subscription") or obj.get("id")

    # customer.subscription.created has no email — fetch from Stripe
    if not customer_email and customer_id:
        try:
            customer = stripe.Customer.retrieve(customer_id)
            customer_email = customer.get("email")
        except Exception:
            pass

    return customer_email, customer_id, subscription_id


def _issue_or_resend_licence(customer_email: str, customer_id: str | None, subscription_id: str | None):
    with get_db() as (conn, cur):
        cur.execute(
            "SELECT key FROM licences WHERE email = %s AND active = TRUE LIMIT 1",
            (customer_email,),
        )
        existing = cur.fetchone()

        if existing:
            # Key already exists — another event already handled this purchase
            return

        licence_key = _generate_licence_key()
        cur.execute(
            """
            INSERT INTO licences (key, stripe_customer_id, stripe_subscription_id, email, active)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (key) DO NOTHING
            """,
            (licence_key, customer_id, subscription_id, customer_email),
        )
        conn.commit()

    try:
        _send_licence_email(customer_email, licence_key)
    except Exception:
        pass  # Don't fail the webhook if email bounces


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type in (
        "checkout.session.completed",
        "invoice.payment_succeeded",
        "customer.subscription.created",
    ):
        customer_email, customer_id, subscription_id = _resolve_email_from_stripe(obj)
        if customer_email:
            _issue_or_resend_licence(customer_email, customer_id, subscription_id)

    elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        subscription_id = obj.get("id") or obj.get("subscription")
        if subscription_id:
            with get_db() as (conn, cur):
                cur.execute(
                    "UPDATE licences SET active = FALSE WHERE stripe_subscription_id = %s",
                    (subscription_id,),
                )
                conn.commit()

    return {"status": "ok"}


@app.post("/licence/validate")
def validate_licence(req: LicenceValidateRequest):
    with get_db() as (conn, cur):
        cur.execute(
            "SELECT active FROM licences WHERE key = %s",
            (req.licence_key,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Licence key not found")
    if not row[0]:
        raise HTTPException(status_code=403, detail="Licence key is inactive")

    return {"valid": True}


# ---------- TRANSCRIBE ----------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

@app.post("/transcribe")
async def transcribe_audio(request: Request):
    import base64, tempfile, httpx

    body = await request.json()
    licence_key = body.get("licence_key")
    audio_base64 = body.get("audioBase64")

    if not licence_key or not audio_base64:
        raise HTTPException(status_code=400, detail="licence_key and audioBase64 required")

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Transcription not configured")

    # Validate licence
    with get_db() as (conn, cur):
        cur.execute("SELECT active FROM licences WHERE key = %s", (licence_key,))
        row = cur.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=403, detail="Invalid or inactive licence key")

    # Write audio to temp file and send to OpenAI Whisper
    audio_bytes = base64.b64decode(audio_base64)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            with open(tmp_path, "rb") as f:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": ("audio.mp3", f, "audio/mpeg")},
                    data={
                        "model": "whisper-1",
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "word",
                    },
                )
        if not response.is_success:
            raise HTTPException(status_code=502, detail=f"Whisper error: {response.text}")
        result = response.json()
        return result.get("words", [])
    finally:
        import os as _os
        _os.unlink(tmp_path)


# ---------- ADMIN ----------

@app.post("/admin/generate-licence")
def admin_generate_licence(email: str, current_user: dict = Depends(require_superuser)):
    with get_db() as (conn, cur):
        # Check for existing licence
        cur.execute(
            "SELECT key FROM licences WHERE email = %s AND active = TRUE LIMIT 1",
            (email,),
        )
        existing = cur.fetchone()
        if existing:
            return {"message": "Licence already exists", "key": existing[0], "email": email}

        # Create user account if not exists
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user_row = cur.fetchone()
        if not user_row:
            dummy_pw = bcrypt.hashpw(uuid4().hex.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (email, dummy_pw),
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO user_profiles (user_id, email) VALUES (%s, %s)",
                (user_id, email),
            )

        licence_key = _generate_licence_key()
        cur.execute(
            """
            INSERT INTO licences (key, email, active)
            VALUES (%s, %s, TRUE)
            """,
            (licence_key, email),
        )
        conn.commit()

    try:
        _send_licence_email(email, licence_key)
    except Exception:
        pass

    return {"message": "Licence generated", "key": licence_key, "email": email}


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
