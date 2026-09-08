"""זהות המשתמש ומכסת החיפושים.

שני דברים יושבים כאן ולא ב-`storage.py`, כי הם *מי שואל* ולא *מה נשמר*:
מי המשתמש הנוכחי, וכמה חיפושים נשארו לו.

**הזהות עוברת כפרמטר, לעולם לא כמשתנה מודול.** Streamlit מריץ כל session
בת'רד משלו על אותו תהליך; משתנה גלובלי "המשתמש הנוכחי" היה נדרס בין
משתמשים במקביליות, כלומר משתמש אחד היה רואה את הפלייליסט של אחר. לכן
`current_subject()` מחשב מחדש מתוך הקשר ה-session בכל קריאה, ו-`app.py`
מעביר את התוצאה הלאה במפורש.
"""
from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass

import streamlit as st

# שם העוגייה שנושאת את הזהות האנונימית. נכתבת ב-JS מתוך `app.py` ונקראת
# כאן דרך `st.context.cookies`.
ANON_COOKIE = "ts_anon"

# המפתח ב-session_state שמחזיק זהות אנונימית זמנית. נחוץ כי
# `st.context.cookies` משקף את **הבקשה הראשונית** של ה-session: בביקור
# הראשון העוגייה עוד לא קיימת, ובלי נפילה לזיכרון ה-session היה נוצר
# מזהה חדש בכל ריצה מחדש — כלומר מכסה אינסופית בלחיצת כפתור.
ANON_STATE_KEY = "_anon_id"

# דלי אסימונים, לא מונה יומי. "10 ניסיונות שמתמלאים אחד ליום" ו"10 ליום"
# הן אותה מכונה עם קצב מילוי אחר, ולכן שינוי מדיניות הוא שינוי קבוע אחד
# ולא כתיבה מחדש.
QUOTA_CAPACITY = 10.0
QUOTA_REFILL_PER_DAY = 1.0


@dataclass(frozen=True)
class Subject:
    """מי מבצע את הפעולה. `key` הוא המפתח שכל אחסון per-user מפתח לפיו."""

    kind: str          # "user" או "anon"
    key: str           # "user:<email>" או "anon:<uuid>"
    email: str | None = None

    @property
    def is_logged_in(self) -> bool:
        return self.kind == "user"


def _logged_in_email() -> str | None:
    """המייל של המשתמש המחובר, או None.

    ה-try/except אינו הגנה תיאורטית: בלי בלוק `[auth]` ב-secrets,
    `st.user.is_logged_in` **זורק** `AttributeError` (נבדק). בלעדיו כל
    הרצה מקומית וכל טסט היו נשברים מעצם קיום ההתחברות.
    """
    try:
        if not st.user.is_logged_in:
            return None
        email = st.user.email
    except Exception:
        return None
    return email.strip().lower() if isinstance(email, str) and email.strip() else None


def login_available() -> bool:
    """האם התחברות מוגדרת בכלל בסביבה הזו.

    בלי בלוק `[auth]` ב-secrets אין למי להתחבר, ולכן אין טעם לחסום שמירה
    מאחורי כפתור שלא יעשה כלום. זה גם מה ששומר על הפיתוח המקומי ועל
    הטסטים: שם אין auth, וההתנהגות נשארת בדיוק כפי שהייתה — משתמש יחיד
    שיכול לשמור.
    """
    try:
        st.user.is_logged_in
        return True
    except Exception:
        return False


def _anonymous_id() -> str:
    cached = st.session_state.get(ANON_STATE_KEY)
    if cached:
        return cached
    value = ""
    try:
        value = (st.context.cookies or {}).get(ANON_COOKIE) or ""
    except Exception:
        value = ""
    if not value:
        value = uuid.uuid4().hex
    st.session_state[ANON_STATE_KEY] = value
    return value


def current_subject() -> Subject:
    """מחשב את הזהות הנוכחית מתוך הקשר ה-session."""
    email = _logged_in_email()
    if email:
        return Subject("user", f"user:{email}", email)
    return Subject("anon", f"anon:{_anonymous_id()}", None)


def refill(tokens: float, updated_at, now=None,
           capacity: float = QUOTA_CAPACITY,
           per_day: float = QUOTA_REFILL_PER_DAY) -> float:
    """מילוי עצל של הדלי: אין job מתוזמן, רק חשבון בזמן הקריאה.

    פונקציה טהורה בכוונה — היא הלב של המדיניות, וכך אפשר לבדוק אותה בלי
    מסד נתונים ובלי לזייף שעון גלובלי.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if updated_at is None:
        return min(capacity, max(0.0, tokens))
    elapsed = (now - updated_at).total_seconds() / 86400.0
    if elapsed < 0:  # שעון שקפץ אחורה לא אמור לזכות אף אחד
        elapsed = 0.0
    return min(capacity, max(0.0, tokens) + elapsed * per_day)


def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def remaining(subject: Subject) -> float:
    """כמה חיפושים נשארו כרגע, אחרי מילוי עצל."""
    import storage
    tokens, when = storage.load_quota(subject.key)
    if tokens is None:
        return QUOTA_CAPACITY
    return refill(tokens, when, _now())


def spend(subject: Subject, cost: float = 1.0) -> bool:
    """מוריד אסימון אם יש. מחזיר False כשנגמרה המכסה — בלי לכתוב.

    אין כתיבה במסלול הדחייה בכוונה: כתיבה הייתה מקדמת את `updated_at`
    בכל ניסיון חסום, ומאפסת בכל פעם את מד הזמן שממנו מגיע המילוי — כלומר
    משתמש שממשיך ללחוץ לא היה מתמלא לעולם.
    """
    import storage
    now = _now()
    tokens, when = storage.load_quota(subject.key)
    current = QUOTA_CAPACITY if tokens is None else refill(tokens, when, now)
    if current < cost:
        return False
    storage.save_quota(subject.key, current - cost, now)
    return True


def cookie_anon_key() -> str | None:
    """הזהות האנונימית שנשארה בעוגייה, בפורמט של `Subject.key`."""
    try:
        value = (st.context.cookies or {}).get(ANON_COOKIE) or ""
    except Exception:
        value = ""
    return f"anon:{value}" if value else None


def merge_anonymous_quota(subject: Subject) -> None:
    """נקרא פעם אחת אחרי התחברות. ראו `absorb_anonymous` להסבר."""
    absorb_anonymous(subject, cookie_anon_key() or "")


def absorb_anonymous(subject: Subject, anon_key: str) -> None:
    """התחברות אינה מתנה של מכסה חדשה.

    בלי זה, מי שניצל את עשרת החיפושים האנונימיים היה מקבל דלי מלא בשנייה
    שהתחבר — כלומר ההתחברות עצמה הופכת לעקיפת המכסה. לוקחים את המינימום
    בין שני הדליים, פעם אחת, ברגע המעבר.
    """
    import storage
    if not subject.is_logged_in or not anon_key or anon_key == subject.key:
        return
    anon_tokens, anon_when = storage.load_quota(anon_key)
    if anon_tokens is None:
        return
    now = _now()
    anon_left = refill(anon_tokens, anon_when, now)
    mine, mine_when = storage.load_quota(subject.key)
    mine_left = QUOTA_CAPACITY if mine is None else refill(mine, mine_when, now)
    storage.save_quota(subject.key, min(anon_left, mine_left), now)
