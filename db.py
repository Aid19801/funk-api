import psycopg2
from contextlib import contextmanager
from config import DATABASE_URL, SECRET_KEY


@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        yield conn, cur
    finally:
        cur.close()
        conn.close()
