"""אחסון מתמיד: פלייליסט, רשימה שחורה, מדידות גודל וטעם.

**שני בקאנדים, facade אחד.** יש `DATABASE_URL` (ו-psycopg מותקן) — הכל
עובר דרך `db.py`; אין — קבצי JSON, בדיוק כמו קודם. זו לא פשרה אלא דרישה:
הטסטים והפיתוח המקומי לא אמורים לדרוש מסד נתונים, באותה פילוסופיה שכבר
קיימת ב-`resolve_data_dir` (נפילה מסודרת במקום קריסה).

**מי שואל עובר כפרמטר.** לכל פונקציה אישית יש `subject` אופציונלי
(ראו `accounts.Subject`). ההפרדה חלה על משתמש **מחובר** בלבד:

- `subject=None` או אנונימי → המרחב המשותף הישן. בפיתוח מקומי ובטסטים,
  שבהם אין התחברות בכלל, זו בדיוק ההתנהגות שהייתה כאן תמיד.
- משתמש מחובר → מרחב משלו (תיקייה משלו בבקאנד הקבצים, `user_id` בבקאנד
  Postgres).

מה שאינו העדפה אלא **עובדה** — מדידות העוצמה, קאש ה-YouTube והמצעדים
המיובאים — נשאר משותף לכולם בשני הבקאנדים. מדידה מחדש של אותו טראק לכל
משתמש בנפרד הייתה מבזבזת את הנכס היקר ביותר כאן.

הנתיב נבחר בזהירות: אם /data לא קיים או לא ניתן לכתיבה (סביבה מקומית, קונטיינר
ללא volume) נופלים לתיקייה מקומית במקום להפיל את האפליקציה.
"""
import datetime as _dt
import hashlib
import json
import os
import tempfile

import db

ENV_VAR = "TRAILER_SONG_DATA_DIR"

# אזהרות שנצברו בזמן ריצה כדי שה-UI יוכל להציג אותן במקום לקרוס
warnings: list[str] = []


def _is_writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return True
    except Exception:
        return False


def resolve_data_dir() -> str:
    """בוחר תיקיית אחסון: משתנה סביבה -> /data -> .data מקומי -> temp."""
    candidates = []
    if os.environ.get(ENV_VAR):
        candidates.append(os.environ[ENV_VAR])
    candidates.append("/data")
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data"))
    candidates.append(os.path.join(tempfile.gettempdir(), "trailer-song"))

    for candidate in candidates:
        if _is_writable(candidate):
            return candidate

    warnings.append("No writable folder found — data will not be kept between runs.")
    return ""


DATA_DIR = resolve_data_dir()


def _slug(subject) -> str:
    """שם תיקייה יציב למשתמש. גיבוב ולא המייל עצמו — כדי שלא יהיו כתובות
    מייל בשמות קבצים, ושלא ייווצר תו לא חוקי לשם קובץ."""
    return hashlib.sha1(subject.key.encode("utf-8")).hexdigest()[:16]


def _personal(subject) -> bool:
    """האם לפצל לפי משתמש. אנונימי אינו מקבל מרחב משלו: הוא ממילא לא
    יכול לשמור (שמירה דורשת התחברות), ומרחב לכל ביקור היה מייצר זבל."""
    return bool(subject is not None and getattr(subject, "is_logged_in", False))


def _path(name: str, subject=None) -> str:
    if not DATA_DIR:
        return ""
    if _personal(subject):
        folder = os.path.join(DATA_DIR, "users", _slug(subject))
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as exc:
            warnings.append(f"Creating your data folder failed ({exc}).")
            return ""
        return os.path.join(folder, name)
    return os.path.join(DATA_DIR, name)


def _uid(subject):
    """מזהה המשתמש ב-Postgres, או None כשאין הפרדה אישית.

    `db.available()` נבדק כאן ולא רק בקריאה: משתמש מחובר יכול להתקיים גם
    בלי מסד נתונים (בדיקה מקומית עם `[auth]`), ואז ההפרדה נעשית בתיקיות
    ולא בטבלאות.
    """
    if not _personal(subject) or not db.available():
        return None
    return db.user_id(subject.email)


def _load_json(name: str, default, subject=None):
    """טוען, ומחזיר את ברירת המחדל גם כשהתוכן תקין כ-JSON אבל לא מהסוג הנכון.

    JSON פגום כבר טופל; מה שלא טופל היה קובץ *תקין* עם מבנה אחר — רשימה
    במקום מילון — שעבר את `json.load` ונפל רק מאוחר יותר, בתוך הרינדור,
    בכל טעינה ובלי דרך לתקן מתוך הממשק.
    """
    path = _path(name, subject)
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        warnings.append(f"Reading {name} failed ({exc}) — loaded an empty value.")
        return default
    if type(data) is not type(default):
        warnings.append(f"The structure of {name} is not what was expected — loaded an empty value.")
        return default
    return data


def _save_json(name: str, payload, subject=None) -> bool:
    """כתיבה אטומית. מחזיר False במקום לזרוק חריגה."""
    path = _path(name, subject)
    if not path:
        return False
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        warnings.append(f"Saving {name} failed ({exc}) — the change will not be kept between runs.")
        return False


# ---------- רשימה שחורה ----------

def load_blacklist(subject=None) -> set:
    uid = _uid(subject)
    if uid is not None:
        return db.load_blacklist(uid)
    data = _load_json("blacklist.json", [], subject)
    return set(data) if isinstance(data, list) else set()


def save_blacklist(blacklist: set, subject=None) -> bool:
    uid = _uid(subject)
    if uid is not None:
        return db.save_blacklist(uid, blacklist)
    return _save_json("blacklist.json", sorted(blacklist), subject)


# ---------- מפתח זהות לשיר, לקאש המדידות ----------

def cache_key(artist: str, track: str) -> str:
    return f"{artist.strip().lower()}|{track.strip().lower()}"


# מדדי הגודל שנמדדו בדפדפן, לפי cache_key. נשמרים כדי שרענון עמוד לא ימדוד שוב.
# **משותפים לכל המשתמשים**: העוצמה של טראק היא תכונה שלו, לא של מי ששמע אותו.
def load_bigness() -> dict:
    if db.available():
        return db.load_bigness()
    return _load_json("bigness.json", {}) or {}


def save_bigness(measurements: dict) -> bool:
    if db.available():
        return db.save_bigness(measurements)
    return _save_json("bigness.json", measurements)


# הגרסאות שהמשתמש סימן ב-❤️. מאגר אחד שמשרת שתי מטרות: הפלייליסט האישי,
# וגם דוגמאות האימון שמהן `taste.py` לומד מה המשתמש אוהב. מפתח לפי
# `search.track_key` (זהות תוכן), כדי שאותו שיר מ-iTunes ומ-Deezer ייספר פעם אחת.
def load_favorites(subject=None) -> dict:
    uid = _uid(subject)
    if uid is not None:
        return db.load_favorites(uid)
    return _load_json("favorites.json", {}, subject) or {}


def save_favorites(favorites: dict, subject=None) -> bool:
    uid = _uid(subject)
    if uid is not None:
        return db.save_favorites(uid, favorites)
    return _save_json("favorites.json", favorites, subject)


# מה שהמשתמש דחה במפורש (👎). מאגר נפרד ולא דגל בתוך favorites, כי הפלייליסט
# הוא רשימת השמעה — דחייה לא אמורה להופיע בו. ללמידה שני המאגרים שקולים:
# דוגמאות שליליות הן שנותנות למודל *כיוון* ולא רק מרכז כובד.
def load_rejections(subject=None) -> dict:
    uid = _uid(subject)
    if uid is not None:
        return db.load_rejections(uid)
    return _load_json("rejections.json", {}, subject) or {}


def save_rejections(rejections: dict, subject=None) -> bool:
    uid = _uid(subject)
    if uid is not None:
        return db.save_rejections(uid, rejections)
    return _save_json("rejections.json", rejections, subject)


# קאש התשובות מ-YouTube. **משותף** — תשובה של YouTube על טראק היא עובדה
# חיצונית, לא העדפה, והמכסה של ה-API (100 חיפושים ליום לכל הפרויקט) הופכת
# שיתוף מגיבוי-נחמד לתנאי הכרחי.
# שם הקובץ נשאר כפי שהיה ב-`youtube.py`, כדי שהקאש שכבר נצבר
# בפרודקשן לא ייזנח בשקט אחרי המעבר ל-API הציבורי.
EVIDENCE_FILE = "youtube_evidence.json"


def load_evidence() -> dict:
    if db.available():
        return db.load_evidence()
    return _load_json(EVIDENCE_FILE, {}) or {}


def save_evidence(evidence: dict) -> bool:
    if db.available():
        return db.save_evidence(evidence)
    return _save_json(EVIDENCE_FILE, evidence)


# כתובות עטיפות אלבום לפי `cache_key`. **משותף**: העטיפה של אלבום היא
# עובדה ציבורית, ובלי שיתוף כל משתמש שפותח את מסך הפתיחה היה מוציא מחדש
# בדיוק את אותן קריאות רשת.
#
# מחרוזת ריקה נשמרת בכוונה ואינה "אין רשומה": היא אומרת "חיפשנו ולא
# נמצאה עטיפה", ובלעדיה אותה שאילתה כושלת הייתה רצה שוב בכל רינדור.
ARTWORK_FILE = "artwork.json"


def load_artwork() -> dict:
    if db.available():
        return db.load_artwork()
    return _load_json(ARTWORK_FILE, {}) or {}


def save_artwork(found: dict) -> bool:
    """**מיזוג** של מה שהתחדש, לא החלפה של הקאש כולו.

    בניגוד ל-`save_evidence`, כאן הקורא מעביר רק את המפתחות החדשים: הקאש
    גדל לכל שיר בכל מצעד (אלפי רשומות), וכתיבת כולו בכל רינדור היא אלפי
    INSERT מיותרים. המיזוג בגיבוי הקבצים נעשה כאן כדי ששני הבקאנדים יקבלו
    את אותו קלט בדיוק.
    """
    if not found:
        return True
    if db.available():
        return db.save_artwork(found)
    return _save_json(ARTWORK_FILE, {**(_load_json(ARTWORK_FILE, {}) or {}), **found})


# מצעדים שיובאו מעמודי בילבורד שמורים. שם הקובץ נגזר משם המצעד, כדי שייבוא
# חוזר של אותו מצעד יעדכן במקום לשכפל. **משותף**: מצעד בילבורד הוא נתון ציבורי.
IMPORTED_CHARTS = "imported_charts.json"


def load_charts() -> dict:
    if db.available():
        return db.load_charts()
    return _load_json(IMPORTED_CHARTS, {}) or {}


def save_charts(charts: dict) -> bool:
    if db.available():
        return db.save_charts(charts)
    return _save_json(IMPORTED_CHARTS, charts)


# ---------- דיווחי "זה לא השיר הנכון" ----------
#
# משותף כמו bigness/evidence/charts, לא לפי `subject`: דיווח שגרסה של
# "Closer" אינה קאבר של "Loser" הוא עובדה על הקטלוג, לא טעם של מי שדיווח
# עליה. המפתח הוא זהות השיר המקורי שחיפשו (ראו `app._report_key_for`),
# הערך רשימת מפתחות הטראקים שדווחו כשגויים תחתיו.
MISMATCH_FILE = "mismatch_reports.json"


def load_mismatch_reports() -> dict:
    if db.available():
        return db.load_mismatch_reports()
    data = _load_json(MISMATCH_FILE, {}) or {}
    return {key: set(value) for key, value in data.items() if isinstance(value, list)}


def add_mismatch_report(query_key: str, wrong_track_key: str) -> bool:
    """דיווח אחד, נוסף למה שכבר נשמר — ולא כל המילון, בניגוד ל-`save_*`
    האחרים כאן. שני משתמשים שמדווחים על שירים שונים באותו רגע לא אמורים
    לדרוס זה את הדיווח של זה, וטעינה-שינוי-שמירה על המילון השלם הייתה
    בדיוק התנאי מרוץ הזה."""
    if db.available():
        return db.add_mismatch_report(query_key, wrong_track_key)
    data = _load_json(MISMATCH_FILE, {}) or {}
    reported = set(data.get(query_key, []))
    reported.add(wrong_track_key)
    data[query_key] = sorted(reported)
    return _save_json(MISMATCH_FILE, data)


# ---------- מכסת חיפושים ----------
#
# מפתח לפי ה-subject המלא ("user:<email>" או "anon:<uuid>"), כי לאנונימי
# חייבת להיות מכסה גם בלי חשבון. הערכים: מספר האסימונים והרגע שבו נמדד
# (ISO-8601 בקבצים, timestamptz ב-Postgres).
QUOTA_FILE = "quota.json"


def load_quota(subject_key: str):
    """מחזיר (tokens, updated_at) — או (None, None) כשעוד לא נרשם דבר."""
    if db.available():
        return db.load_quota(subject_key)
    row = (_load_json(QUOTA_FILE, {}) or {}).get(subject_key)
    if not isinstance(row, dict) or "tokens" not in row:
        return None, None
    when = None
    try:
        when = _dt.datetime.fromisoformat(row["updated_at"])
    except Exception:
        when = None
    return float(row["tokens"]), when


def save_quota(subject_key: str, tokens: float, when=None) -> bool:
    when = when or _dt.datetime.now(_dt.timezone.utc)
    if db.available():
        return db.save_quota(subject_key, tokens, when)
    rows = _load_json(QUOTA_FILE, {}) or {}
    rows[subject_key] = {"tokens": float(tokens), "updated_at": when.isoformat()}
    return _save_json(QUOTA_FILE, rows)
