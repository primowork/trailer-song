"""אחסון מתמיד: פלייליסט, רשימה שחורה, מדידות גודל וטעם.

הנתיב נבחר בזהירות: אם /data לא קיים או לא ניתן לכתיבה (סביבה מקומית, קונטיינר
ללא volume) נופלים לתיקייה מקומית במקום להפיל את האפליקציה.
"""
import json
import os
import tempfile

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

    warnings.append("לא נמצאה תיקייה הניתנת לכתיבה — הנתונים לא יישמרו בין הרצות.")
    return ""


DATA_DIR = resolve_data_dir()


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, name) if DATA_DIR else ""


def _load_json(name: str, default):
    """טוען, ומחזיר את ברירת המחדל גם כשהתוכן תקין כ-JSON אבל לא מהסוג הנכון.

    JSON פגום כבר טופל; מה שלא טופל היה קובץ *תקין* עם מבנה אחר — רשימה
    במקום מילון — שעבר את `json.load` ונפל רק מאוחר יותר, בתוך הרינדור,
    בכל טעינה ובלי דרך לתקן מתוך הממשק.
    """
    path = _path(name)
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        warnings.append(f"קריאת {name} נכשלה ({exc}) — נטען ערך ריק.")
        return default
    if type(data) is not type(default):
        warnings.append(f"המבנה של {name} אינו כצפוי — נטען ערך ריק.")
        return default
    return data


def _save_json(name: str, payload) -> bool:
    """כתיבה אטומית. מחזיר False במקום לזרוק חריגה."""
    path = _path(name)
    if not path:
        return False
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        warnings.append(f"שמירת {name} נכשלה ({exc}) — השינוי לא יישמר בין הרצות.")
        return False


# ---------- רשימה שחורה ----------

def load_blacklist() -> set:
    data = _load_json("blacklist.json", [])
    return set(data) if isinstance(data, list) else set()


def save_blacklist(blacklist: set) -> bool:
    return _save_json("blacklist.json", sorted(blacklist))


# ---------- מפתח זהות לשיר, לקאש המדידות ----------

def cache_key(artist: str, track: str) -> str:
    return f"{artist.strip().lower()}|{track.strip().lower()}"


# מדדי הגודל שנמדדו בדפדפן, לפי cache_key. נשמרים כדי שרענון עמוד לא ימדוד שוב.
def load_bigness() -> dict:
    return _load_json("bigness.json", {}) or {}


def save_bigness(measurements: dict) -> bool:
    return _save_json("bigness.json", measurements)


# הגרסאות שהמשתמש סימן ב-❤️. מאגר אחד שמשרת שתי מטרות: הפלייליסט האישי,
# וגם דוגמאות האימון שמהן `taste.py` לומד מה המשתמש אוהב. מפתח לפי
# `search.track_key` (זהות תוכן), כדי שאותו שיר מ-iTunes ומ-Deezer ייספר פעם אחת.
def load_favorites() -> dict:
    return _load_json("favorites.json", {}) or {}


def save_favorites(favorites: dict) -> bool:
    return _save_json("favorites.json", favorites)


# מה שהמשתמש דחה במפורש (👎). מאגר נפרד ולא דגל בתוך favorites, כי הפלייליסט
# הוא רשימת השמעה — דחייה לא אמורה להופיע בו. ללמידה שני המאגרים שקולים:
# דוגמאות שליליות הן שנותנות למודל *כיוון* ולא רק מרכז כובד.
def load_rejections() -> dict:
    return _load_json("rejections.json", {}) or {}


def save_rejections(rejections: dict) -> bool:
    return _save_json("rejections.json", rejections)


# מצעדים שיובאו מעמודי בילבורד שמורים. שם הקובץ נגזר משם המצעד, כדי שייבוא
# חוזר של אותו מצעד יעדכן במקום לשכפל.
IMPORTED_CHARTS = "imported_charts.json"


def load_charts() -> dict:
    return _load_json(IMPORTED_CHARTS, {}) or {}


def save_charts(charts: dict) -> bool:
    return _save_json(IMPORTED_CHARTS, charts)
