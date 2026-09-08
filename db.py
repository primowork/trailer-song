"""בקאנד Postgres. נטען רק כש-`DATABASE_URL` מוגדר.

`storage.py` נשאר ה-facade היחיד; הקובץ הזה הוא מימוש אחד משניים שלו.
בלי `DATABASE_URL` שום דבר כאן לא רץ — וזו דרישה ולא פשרה: הטסטים
והפיתוח המקומי לא אמורים לדרוש מסד נתונים.

חלוקת הבעלות שמשתקפת בסכימה: **מה שהוא העדפה — אישי; מה שהוא עובדה —
משותף.** מדידת עוצמה של טראק, תשובת YouTube ומצעד בילבורד הם אותו דבר
לכל המשתמשים, ומדידה מחדש שלהם לכל משתמש הייתה הורסת בדיוק את הנכס
היקר ביותר שיש כאן.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import threading

DATABASE_URL_ENV = "DATABASE_URL"

_lock = threading.Lock()
_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          bigserial PRIMARY KEY,
    email       text UNIQUE NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- אישי
CREATE TABLE IF NOT EXISTS favorites (
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_key   text NOT NULL,
    payload     jsonb NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, track_key)
);
CREATE TABLE IF NOT EXISTS rejections (
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_key   text NOT NULL,
    payload     jsonb NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, track_key)
);
CREATE TABLE IF NOT EXISTS blacklist (
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artist      text NOT NULL,
    PRIMARY KEY (user_id, artist)
);

-- משותף
CREATE TABLE IF NOT EXISTS measurements (
    cache_key   text PRIMARY KEY,
    features    jsonb NOT NULL,
    measured_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS evidence (
    cache_key   text PRIMARY KEY,
    payload     jsonb NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS charts (
    slug        text PRIMARY KEY,
    payload     jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

-- מכסה. המפתח הוא ה-subject המלא ("user:<email>" או "anon:<uuid>"),
-- ולא user_id, כי אנונימי חייב מכסה גם בלי שורה ב-users.
CREATE TABLE IF NOT EXISTS quota (
    subject     text PRIMARY KEY,
    tokens      real NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
"""


def url() -> str:
    return os.environ.get(DATABASE_URL_ENV, "").strip()


def available() -> bool:
    """האם לעבוד מול Postgres. גם הכתובת וגם הדרייבר חייבים להיות שם."""
    if not url():
        return False
    try:
        import psycopg  # noqa: F401
    except Exception:
        return False
    return True


def connect():
    import psycopg
    return psycopg.connect(url())


def _ensure_schema(conn):
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()
        _ready = True


def _cursor(conn):
    _ensure_schema(conn)
    return conn.cursor()


def user_id(email: str) -> int:
    """מזהה המשתמש לפי מייל, ויוצר אותו בפעם הראשונה.

    `ON CONFLICT ... DO UPDATE` ולא `DO NOTHING`, כי `DO NOTHING` לא
    מחזיר שורה בהתנגשות ואז ההתחברות השנייה של אותו משתמש הייתה נופלת.
    """
    with connect() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                "INSERT INTO users (email) VALUES (%s) "
                "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email "
                "RETURNING id", (email,))
            row = cur.fetchone()
        conn.commit()
    return int(row[0])


# ---------- אישי ----------

def _load_pairs(table: str, uid: int) -> dict:
    with connect() as conn:
        with _cursor(conn) as cur:
            cur.execute(f"SELECT track_key, payload FROM {table} WHERE user_id = %s",
                        (uid,))
            return {key: payload for key, payload in cur.fetchall()}


def _save_pairs(table: str, uid: int, items: dict) -> bool:
    """מחליף את כל התוכן של המשתמש בטבלה בעסקה אחת.

    ה-API של `storage` שומר תמיד את המילון **כולו**, ולכן החלפה מלאה
    היא התרגום הנאמן — לא מיזוג, שהיה משאיר לנצח פריטים שנמחקו.
    """
    with connect() as conn:
        with _cursor(conn) as cur:
            keys = list(items)
            if keys:
                cur.execute(f"DELETE FROM {table} WHERE user_id = %s "
                            "AND track_key <> ALL(%s)", (uid, keys))
            else:
                cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (uid,))
            for key, payload in items.items():
                cur.execute(
                    f"INSERT INTO {table} (user_id, track_key, payload) "
                    "VALUES (%s, %s, %s) ON CONFLICT (user_id, track_key) "
                    "DO UPDATE SET payload = EXCLUDED.payload",
                    (uid, key, json.dumps(payload, ensure_ascii=False)))
        conn.commit()
    return True


def load_favorites(uid: int) -> dict:
    return _load_pairs("favorites", uid)


def save_favorites(uid: int, items: dict) -> bool:
    return _save_pairs("favorites", uid, items)


def load_rejections(uid: int) -> dict:
    return _load_pairs("rejections", uid)


def save_rejections(uid: int, items: dict) -> bool:
    return _save_pairs("rejections", uid, items)


def load_blacklist(uid: int) -> set:
    with connect() as conn:
        with _cursor(conn) as cur:
            cur.execute("SELECT artist FROM blacklist WHERE user_id = %s", (uid,))
            return {row[0] for row in cur.fetchall()}


def save_blacklist(uid: int, artists) -> bool:
    artists = sorted(set(artists))
    with connect() as conn:
        with _cursor(conn) as cur:
            if artists:
                cur.execute("DELETE FROM blacklist WHERE user_id = %s "
                            "AND artist <> ALL(%s)", (uid, artists))
            else:
                cur.execute("DELETE FROM blacklist WHERE user_id = %s", (uid,))
            for artist in artists:
                cur.execute("INSERT INTO blacklist (user_id, artist) VALUES (%s, %s) "
                            "ON CONFLICT DO NOTHING", (uid, artist))
        conn.commit()
    return True


# ---------- משותף ----------

def _load_shared(table: str, key_col: str, value_col: str) -> dict:
    with connect() as conn:
        with _cursor(conn) as cur:
            cur.execute(f"SELECT {key_col}, {value_col} FROM {table}")
            return {key: value for key, value in cur.fetchall()}


def _save_shared(table: str, key_col: str, value_col: str, items: dict) -> bool:
    """משותף = **מיזוג**, לא החלפה.

    זה ההבדל המכוון מול הטבלאות האישיות: שני משתמשים מודדים במקביל, וכל
    אחד שולח את הקאש שלו. החלפה מלאה כאן הייתה גורמת לאחרון למחוק את
    המדידות של הראשון.
    """
    if not items:
        return True
    with connect() as conn:
        with _cursor(conn) as cur:
            for key, value in items.items():
                cur.execute(
                    f"INSERT INTO {table} ({key_col}, {value_col}) VALUES (%s, %s) "
                    f"ON CONFLICT ({key_col}) DO UPDATE SET {value_col} = EXCLUDED.{value_col}",
                    (key, json.dumps(value, ensure_ascii=False)))
        conn.commit()
    return True


def load_bigness() -> dict:
    return _load_shared("measurements", "cache_key", "features")


def save_bigness(items: dict) -> bool:
    return _save_shared("measurements", "cache_key", "features", items)


def load_evidence() -> dict:
    return _load_shared("evidence", "cache_key", "payload")


def save_evidence(items: dict) -> bool:
    return _save_shared("evidence", "cache_key", "payload", items)


def load_charts() -> dict:
    return _load_shared("charts", "slug", "payload")


def save_charts(items: dict) -> bool:
    """מצעדים כן מוחלפים במלואם — למסך ההגדרות יש כפתור *הסרה*, ומיזוג
    היה הופך אותו לכפתור שלא עושה כלום."""
    with connect() as conn:
        with _cursor(conn) as cur:
            slugs = list(items)
            if slugs:
                cur.execute("DELETE FROM charts WHERE slug <> ALL(%s)", (slugs,))
            else:
                cur.execute("DELETE FROM charts")
            for slug, payload in items.items():
                cur.execute(
                    "INSERT INTO charts (slug, payload) VALUES (%s, %s) "
                    "ON CONFLICT (slug) DO UPDATE SET payload = EXCLUDED.payload",
                    (slug, json.dumps(payload, ensure_ascii=False)))
        conn.commit()
    return True


# ---------- מכסה ----------

def load_quota(subject: str):
    """מחזיר (tokens, updated_at) או (None, None) אם אין עדיין שורה."""
    with connect() as conn:
        with _cursor(conn) as cur:
            cur.execute("SELECT tokens, updated_at FROM quota WHERE subject = %s",
                        (subject,))
            row = cur.fetchone()
    if not row:
        return None, None
    return float(row[0]), row[1]


def save_quota(subject: str, tokens: float, when=None) -> bool:
    when = when or _dt.datetime.now(_dt.timezone.utc)
    with connect() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                "INSERT INTO quota (subject, tokens, updated_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (subject) DO UPDATE SET tokens = EXCLUDED.tokens, "
                "updated_at = EXCLUDED.updated_at", (subject, float(tokens), when))
        conn.commit()
    return True
