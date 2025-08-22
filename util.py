from fastapi import Depends, Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt  # PyJWT
from db import SECRET_KEY
from db import get_conn

auth_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token.")
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        print("found user? ", user)
        cur.close()
        conn.close()

        if not user:
            raise HTTPException(status_code=401, detail="User not found.")
        return {"id": user[0], "email": user[1]}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")