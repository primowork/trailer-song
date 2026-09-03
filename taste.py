"""למידת הטעם של המשתמש מהגרסאות שסימן ב-❤️.

הבעיה: הדירוג הכללי (`relevance + epic_bonus`) לא יודע דבר על המשתמש
הספציפי, ולכן הגרסה שהוא הכי אוהב נוחתת במקום שביעי. כאן נלמד מה מייחד
את מה שהוא כן אהב, ומוסיפים בונוס לטראקים דומים.

**למה מודל קטן ולא מודל גדול.** מספר הדוגמאות כאן הוא 5–30. רגרסיה עם
עשרות פרמטרים על מדגם כזה משננת רעש. שלושת הדברים שכן מייצרים דיוק על
מדגם קטן, וזה מה שמיושם:

1. **ניגוד מול הרקע.** אם 80% מהתוצאות ממילא מתויגות Soundtrack, לייק על
   Soundtrack אינו מלמד כלום; לייק על ז'אנר שהוא 3% מהתוצאות הוא אות חזק.
   הלמידה מודדת יחס מול השכיחות בפול שהוצג בפועל, לא ספירה גולמית.
2. **גילוי אילו מימדים חשובים.** אם הלייקים עקביים בבס אבל מפוזרים בקצב,
   הבס הוא שמגדיר את הטעם. זה נופל ישירות מסטיית התקן לכל מימד — מודל
   גאוסיאני עם קווריאנס אלכסוני, שבו משקל המימד הוא 1/σ².
3. **ריכוך מול פריור.** σ וגם עוצמת ההשפעה מרוככים לפי מספר הדוגמאות, כך
   שלייק בודד מזיז מעט ו-20 לייקים שולטים. בלי זה לחיצה אחת נועלת את
   המשתמש על סגנון.

הקובץ טהור: בלי Streamlit, בלי רשת, בלי קריאות דיסק — ולכן נבדק במלואו.
"""
import math
import time

import audio
from search import normalize_artist, trailer_indicators

# --- כיול. הערכים הם הערכה מושכלת ומיועדים לכיול מחדש על לייקים אמיתיים ---

# פיזור אופייני של טראק אקראי במרחב המנורמל 0..1, ששימש כפריור ל-σ
SPREAD_PRIOR = 0.28
# משקל הפריור מול הנצפה: σ = (n·σ_נצפה + k·σ_פריור) / (n + k)
SPREAD_SHRINK = 4.0
# רמפת הביטחון: n/(n+K). לייק אחד ≈0.17, חמישה 0.5, עשרים 0.8
CONFIDENCE_HALF = 5.0
# החלקה אדיטיבית ליחס הסבירות הקטגוריאלי
SMOOTHING = 0.15
# חסם על lift של תכונה בודדת, כדי שערך יחיד לא ישתלט על הפרופיל
MAX_LIFT = 1.6
# הבונוס המרבי שהטעם יכול להוסיף לציון (להשוואה: MAX_EPIC_BONUS=30)
MAX_TASTE_BONUS = 40
AUDIO_WEIGHT = 0.6
CATEGORICAL_WEIGHT = 0.4
# ציון האודיו של טראק שטרם נמדד. לא 0 — "לא נמדד" אינו "לא מתאים", ואחרת
# כל מה שהמדידה בדפדפן טרם הגיעה אליו נקבר מתחת למדודים
NEUTRAL = 0.5
# לייק ישן שוקל פחות, כדי שהטעם יוכל לזוז עם הזמן. חצי-חיים בימים.
RECENCY_HALFLIFE_DAYS = 120.0

DIMENSIONS = tuple(audio.WEIGHTS)

# תווית לכל קצה של כל מימד, ל-describe
_DIMENSION_LABELS = {
    "loudness": ("עוצמה גבוהה", "עוצמה נמוכה"),
    "low_end": ("בס חזק", "בס מינימלי"),
    "onset_rate": ("קצב מהיר", "קצב איטי"),
    "dynamic_span": ("קשת דינמית רחבה", "דינמיקה שטוחה"),
}
_TRAIT_LABELS = {"genre": "ז'אנר", "artist": "אמן", "source": "מקור",
                 "mark": "סימן", "decade": "שנות"}


def traits(track: dict, labels: dict | None = None) -> set:
    """התכונות הקטגוריאליות שמהן אפשר ללמוד, כמחרוזות `סוג:ערך`.

    אלה השדות שכבר קיימים על כל טראק בזמן התצוגה — לא נדרשת שום שליפה נוספת.
    הערכים מנורמלים כדי ש-"2WEI" ו-"2Wei" יהיו אותה תכונה; `labels` אוסף
    בדרך את הכתיב המקורי, כדי ש-`describe` יציג "2WEI" ולא "2wei".
    """
    found = set()
    genre = (track.get("genre") or "").strip()
    if genre:
        trait = f"genre:{genre.lower()}"
        found.add(trait)
        if labels is not None:
            labels.setdefault(trait, genre)
    artist = normalize_artist(track.get("artist", ""))
    if artist:
        trait = f"artist:{artist}"
        found.add(trait)
        if labels is not None:
            labels.setdefault(trait, track.get("artist", "").strip())
    catalog = (track.get("catalog_source") or "").strip()
    if catalog:
        found.add(f"source:{catalog}")
    for marker in trailer_indicators(track):
        found.add(f"mark:{marker}")
    year = str(track.get("year") or "")[:4]
    if year.isdigit():
        found.add(f"decade:{int(year) // 10 * 10}")
    return found


def _recency_weight(entry: dict, now: float) -> float:
    """לייק חדש שוקל יותר מלייק בן שנה, בדעיכה מעריכית."""
    added = entry.get("added_at")
    if not added:
        return 1.0
    age_days = max(0.0, (now - float(added)) / 86400.0)
    return 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)


def profile(favorites: list, background: list | None = None,
            now: float | None = None) -> dict:
    """בונה פרופיל טעם מהלייקים, בניגוד לשכיחות ברקע.

    `favorites` — רשומות כפי שנשמרו ב-`storage.load_favorites()` (טראק plus
    `features` plus `added_at`). `background` — פול התוצאות שמוצג בפועל, שממנו
    נלמדת שכיחות הרקע. בלי רקע, המודל מדרדר למונה שכיחות: הוא היה מסיק
    ש"Soundtrack" הוא הטעם של המשתמש רק כי זה מה שהחיפוש מחזיר ממילא.
    """
    now = now or time.time()
    count = len(favorites)
    empty = {"count": 0, "mean": {}, "spread": {}, "dimension_weights": {},
             "lift": {}, "confidence": 0.0}
    if not count:
        return empty

    weights = [_recency_weight(entry, now) for entry in favorites]

    # --- מרכז הכובד של הצליל, ורלוונטיות פר-מימד ---
    vectors, vector_weights = [], []
    for entry, weight in zip(favorites, weights):
        normalized = audio.normalized(entry.get("features"))
        if normalized:
            vectors.append(normalized)
            vector_weights.append(weight)

    mean, spread, dimension_weights = {}, {}, {}
    if vectors:
        total = sum(vector_weights) or 1.0
        for dimension in DIMENSIONS:
            values = [vector[dimension] for vector in vectors]
            mu = sum(v * w for v, w in zip(values, vector_weights)) / total
            variance = sum(w * (v - mu) ** 2
                           for v, w in zip(values, vector_weights)) / total
            observed = math.sqrt(max(0.0, variance))
            # ריכוך: מדגם קטן לא רשאי להכריז "בדיוק 0.31 בס, בלי סטייה"
            n = len(vectors)
            sigma = ((n * observed + SPREAD_SHRINK * SPREAD_PRIOR)
                     / (n + SPREAD_SHRINK))
            mean[dimension] = mu
            spread[dimension] = max(sigma, 0.05)

        # מימד שהמשתמש עקבי בו (σ קטן) מקבל משקל גבוה — זה הלב של
        # "המערכת מבינה *למה* אהבתי", ולא רק "אהבתי"
        raw = {d: 1.0 / (spread[d] ** 2) for d in DIMENSIONS}
        total_raw = sum(raw.values()) or 1.0
        dimension_weights = {d: raw[d] / total_raw for d in DIMENSIONS}

    # --- יחס סבירות קטגוריאלי מול הרקע ---
    liked, labels = {}, {}
    total_weight = sum(weights) or 1.0
    for entry, weight in zip(favorites, weights):
        for trait in traits(entry, labels):
            liked[trait] = liked.get(trait, 0.0) + weight

    pool = background or []
    background_rate = {}
    if pool:
        for track in pool:
            for trait in traits(track):
                background_rate[trait] = background_rate.get(trait, 0.0) + 1.0
        background_rate = {t: c / len(pool) for t, c in background_rate.items()}

    lift = {}
    for trait, weighted_count in liked.items():
        favored = (weighted_count + SMOOTHING) / (total_weight + SMOOTHING)
        # תכונה שלא נראתה ברקע בכלל מקבלת את שכיחות הרצפה, לא אפס —
        # אחרת log מתפוצץ והתכונה הנדירה מקבלת משקל אינסופי
        base = background_rate.get(trait, SMOOTHING)
        value = math.log(favored / max(base, SMOOTHING))
        lift[trait] = max(-MAX_LIFT, min(MAX_LIFT, value))

    return {
        "count": count,
        "mean": mean,
        "spread": spread,
        "dimension_weights": dimension_weights,
        "lift": lift,
        "labels": labels,
        "confidence": count / (count + CONFIDENCE_HALF),
    }


def match(track: dict, features: dict | None, learned: dict) -> float:
    """כמה הטראק תואם לטעם שנלמד, 0..1 (כולל רמפת הביטחון)."""
    if not learned or not learned.get("count"):
        return 0.0

    mean = learned.get("mean") or {}
    normalized = audio.normalized(features)
    if normalized and mean:
        spread = learned["spread"]
        dimension_weights = learned["dimension_weights"]
        distance = sum(dimension_weights[d] * (normalized[d] - mean[d]) ** 2
                       / (2 * spread[d] ** 2) for d in DIMENSIONS)
        audio_match = math.exp(-distance)
    else:
        audio_match = NEUTRAL

    lift = learned.get("lift") or {}
    track_traits = traits(track)
    if track_traits and lift:
        mean_lift = sum(lift.get(t, 0.0) for t in track_traits) / len(track_traits)
        # tanh ממפה סביב 0.5: תכונות ניטרליות אינן מזיזות, חיוביות מעלות
        categorical_match = 0.5 + 0.5 * math.tanh(mean_lift * 2)
    else:
        categorical_match = NEUTRAL

    combined = AUDIO_WEIGHT * audio_match + CATEGORICAL_WEIGHT * categorical_match
    return learned["confidence"] * combined


def bonus(track: dict, features: dict | None, learned: dict) -> int:
    """הבונוס לציון הדירוג. חסום, כדי שהטעם ישפיע ולא ישתלט."""
    return int(round(MAX_TASTE_BONUS * match(track, features, learned)))


def describe(learned: dict) -> str:
    """מה בדיוק נלמד, בשפה אנושית.

    בלי זה זו קופסה שחורה: המשתמש רואה שהסדר השתנה ואינו יכול לדעת אם
    המערכת הבינה אותו נכון, ולכן גם לא יכול לתקן אותה.
    """
    if not learned or not learned.get("count"):
        return ""

    parts = []
    dimension_weights = learned.get("dimension_weights") or {}
    if dimension_weights:
        average = sum(dimension_weights.values()) / len(dimension_weights)
        for dimension, weight in sorted(dimension_weights.items(),
                                        key=lambda item: item[1], reverse=True):
            mu = learned["mean"][dimension]
            # רק מימד שגם חשוב (משקל מעל הממוצע) וגם מוכרע (לא באמצע)
            if weight <= average or 0.35 < mu < 0.65:
                continue
            high, low = _DIMENSION_LABELS[dimension]
            parts.append(high if mu >= 0.65 else low)

    display = learned.get("labels") or {}
    for trait, value in sorted((learned.get("lift") or {}).items(),
                               key=lambda item: item[1], reverse=True)[:3]:
        if value <= 0.2:
            continue
        kind, _, name = trait.partition(":")
        label = _TRAIT_LABELS.get(kind, kind)
        parts.append(f"{label} {display.get(trait, name)}".strip())

    if not parts:
        return f"לומד מ-{learned['count']} לייקים — עדיין אין דפוס מובהק"
    return f"לומד מ-{learned['count']} לייקים: " + " · ".join(parts[:5])
