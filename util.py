import os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from db import SECRET_KEY, get_db

auth_scheme = HTTPBearer()

SUPERUSER_ID = os.getenv("SUPERUSER_ID")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token.")
        with get_db() as (conn, cur):
            cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="User not found.")
        return {
            "id": user[0],
            "email": user[1],
            "is_superuser": str(user[0]) == SUPERUSER_ID,
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def require_superuser(current_user: dict = Depends(get_current_user)):
    if not current_user["is_superuser"]:
        raise HTTPException(status_code=403, detail="Superuser access required.")
    return current_user
