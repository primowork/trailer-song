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
# כמה קריטריון פישר (הפרדה בין אהובים לדחויים) מגביר את משקל המימד
FISHER_STRENGTH = 3.0
# כמה קרבה למרכז הדחויים גורעת מההתאמה
REJECT_PENALTY = 0.7
# מספר הדחיות שבו הן שוקלות כמו הרקע כקבוצת ייחוס קטגוריאלית
REJECT_REFERENCE_HALF = 5.0
# כמה לייקים צריכים לשאת תכונה כדי שהיא תוצג כ"הטעם שלך". תכונה מדוגמה
# בודדת עשויה לקבל lift גבוה ועדיין להיות מקרית
MIN_SUPPORT = 2.0
# תוספת ישירה לטראק שהאמן שלו כבר שמור בפלייליסט, גם אם זה קאבר לשיר אחר
KNOWN_ARTIST_BOOST = 0.25

# המימדים אינם קבועים: מדידה שנשמרה לפני שמדדי הגוון נוספו מתארת ארבעה
# מימדים, ומדידה חדשה תשעה. הפרופיל נבנה על מה שקיים בפועל בכל הדוגמאות,
# וההשוואה רצה על החיתוך — כך שמדידות ישנות נשארות שימושיות במקום להיזרק.
DIMENSIONS = tuple(audio.WEIGHTS) + tuple(audio.TIMBRE_RANGES)

# תווית לכל קצה של כל מימד, ל-describe
_DIMENSION_LABELS = {
    "loudness": ("עוצמה גבוהה", "עוצמה נמוכה"),
    "low_end": ("בס חזק", "בס מינימלי"),
    "onset_rate": ("קצב מהיר", "קצב איטי"),
    "dynamic_span": ("קשת דינמית רחבה", "דינמיקה שטוחה"),
    "centroid": ("צליל בהיר", "צליל אפל"),
    "flatness": ("מרקם רועש ומעוות", "מרקם טונאלי ונקי"),
    "air": ("אוויר וברק בגבהים", "גבהים מרוסנים"),
    "presence": ("חוד ונוכחות באמצע-גבוה", "אמצע-גבוה רך"),
    "flux": ("ספקטרום נע — פרקושן קצבי", "ספקטרום יציב — מתמשך ולגאטו"),
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


def _moments(entries: list, weights: list) -> tuple:
    """מרכז ופיזור מרוכך לכל מימד אודיו, לקבוצת דוגמאות אחת.

    מוחזר גם מספר הדוגמאות שהיו מדודות בפועל — פיזור שחושב על שתי דוגמאות
    אינו אותו דבר כמו פיזור שחושב על עשרים, וההחלטות למטה תלויות בזה.
    """
    vectors, vector_weights = [], []
    for entry, weight in zip(entries, weights):
        normalized = audio.normalized(entry.get("features"))
        if normalized:
            vectors.append(normalized)
            vector_weights.append(weight)
    if not vectors:
        return {}, {}, 0

    # רק מימדים שקיימים בכל הדוגמאות: ממוצע שחושב על תת-קבוצה אחרת בכל מימד
    # אינו מרכז של אותו ענן נקודות
    shared = [d for d in DIMENSIONS if all(d in vector for vector in vectors)]
    total = sum(vector_weights) or 1.0
    mean, spread = {}, {}
    for dimension in shared:
        values = [vector[dimension] for vector in vectors]
        mu = sum(v * w for v, w in zip(values, vector_weights)) / total
        variance = sum(w * (v - mu) ** 2
                       for v, w in zip(values, vector_weights)) / total
        # ריכוך: מדגם קטן לא רשאי להכריז "בדיוק 0.31 בס, בלי סטייה"
        sigma = ((len(vectors) * math.sqrt(max(0.0, variance))
                  + SPREAD_SHRINK * SPREAD_PRIOR) / (len(vectors) + SPREAD_SHRINK))
        mean[dimension] = mu
        spread[dimension] = max(sigma, 0.05)
    return mean, spread, len(vectors)


def _rates(entries: list, weights: list, labels: dict | None = None) -> tuple:
    """שכיחות משוקללת של כל תכונה קטגוריאלית בקבוצה."""
    counts = {}
    for entry, weight in zip(entries, weights):
        for trait in traits(entry, labels):
            counts[trait] = counts.get(trait, 0.0) + weight
    total = sum(weights) or 1.0
    return {trait: count / total for trait, count in counts.items()}, total


def profile(favorites: list, background: list | None = None,
            rejections: list | None = None, now: float | None = None) -> dict:
    """בונה פרופיל טעם מהלייקים, בניגוד לדחיות ולשכיחות ברקע.

    `favorites` / `rejections` — רשומות כפי שנשמרו ב-`storage` (טראק plus
    `features` plus `added_at`). `background` — פול התוצאות שמוצג בפועל.

    שני מקורות ניגוד, ולא במקרה. **הרקע** עונה על "מה נפוץ ממילא": בלעדיו
    המודל היה מסיק ש-Soundtrack הוא הטעם של המשתמש רק כי זה מה שהחיפוש
    מחזיר. **הדחיות** עונות על שאלה חזקה יותר: "מה מפריד בין מה שאהבתי לבין
    מה שדחיתי". דוגמאות חיוביות לבדן נותנות מרכז כובד; דוגמאות שליליות
    נותנות *כיוון*, וזה מה שמפריד טעם מ"עוד מאותו דבר".
    """
    now = now or time.time()
    count = len(favorites)
    if not count:
        return {"count": 0, "mean": {}, "spread": {}, "dimension_weights": {},
                "lift": {}, "labels": {}, "reject_mean": {}, "reject_spread": {},
                "reject_count": 0, "confidence": 0.0}

    rejections = rejections or []
    weights = [_recency_weight(entry, now) for entry in favorites]
    reject_weights = [_recency_weight(entry, now) for entry in rejections]

    # --- מרכז הכובד של הצליל, ורלוונטיות פר-מימד ---
    mean, spread, measured_count = _moments(favorites, weights)
    reject_mean, reject_spread, reject_measured = _moments(rejections, reject_weights)

    dimension_weights = {}
    if mean:
        # בסיס: מימד שהמשתמש עקבי בו (σ קטן) מגדיר את הטעם יותר ממימד מפוזר
        raw = {d: 1.0 / (spread[d] ** 2) for d in mean}
        for dimension in mean:
            if dimension not in reject_mean:
                continue
            # בנוכחות דחיות, מה שבאמת חשוב הוא מה ש*מפריד* בין השתיים.
            # קריטריון פישר: מרחק בין המרכזים ביחס לפיזור המשותף. מימד שבו
            # האהובים והדחויים יושבים באותו מקום אינו מלמד כלום, גם אם
            # המשתמש עקבי בו לחלוטין.
            gap = (mean[dimension] - reject_mean[dimension]) ** 2
            pooled = spread[dimension] ** 2 + reject_spread[dimension] ** 2
            raw[dimension] *= 1.0 + FISHER_STRENGTH * gap / pooled
        total_raw = sum(raw.values()) or 1.0
        dimension_weights = {d: value / total_raw for d, value in raw.items()}

    # --- יחס סבירות קטגוריאלי, מול הרקע ומול הדחיות ---
    # הכתיב המקורי נאסף משתי הקבוצות: `describe` מציג גם את מה שנאהב וגם את
    # מה שנדחה, ותכונה שהופיעה רק בדחיות זקוקה לשם קריא בדיוק כמו האחרות
    labels = {}
    liked_rate, total_weight = _rates(favorites, weights, labels)
    rejected_rate, _ = _rates(rejections, reject_weights, labels)

    pool = background or []
    background_rate = {}
    if pool:
        for track in pool:
            for trait in traits(track):
                background_rate[trait] = background_rate.get(trait, 0.0) + 1.0
        background_rate = {t: c / len(pool) for t, c in background_rate.items()}

    # ככל שיש יותר דחיות, הן משמשות יותר כקבוצת הייחוס במקום הרקע הכללי:
    # הן דגימה קשה יותר — מאותו פול, אבל של מה שהמשתמש דחה בפועל
    reject_pull = len(rejections) / (len(rejections) + REJECT_REFERENCE_HALF)

    lift = {}
    for trait in set(liked_rate) | set(rejected_rate):
        favored = liked_rate.get(trait, 0.0) + SMOOTHING
        # תכונה שלא נראתה בקבוצת הייחוס מקבלת את שכיחות הרצפה ולא אפס,
        # אחרת log מתפוצץ והתכונה הנדירה מקבלת משקל אינסופי
        base_background = max(background_rate.get(trait, SMOOTHING), SMOOTHING)
        base_rejected = max(rejected_rate.get(trait, 0.0) + SMOOTHING, SMOOTHING)
        base = ((1 - reject_pull) * base_background + reject_pull * base_rejected)
        lift[trait] = max(-MAX_LIFT, min(MAX_LIFT, math.log(favored / base)))

    return {
        "count": count,
        "mean": mean,
        "spread": spread,
        "dimension_weights": dimension_weights,
        "lift": lift,
        # כמה מהלייקים באמת נשאו כל תכונה. `describe` משתמש בזה כדי לא להכריז
        # על אמן שהופיע פעם אחת כעל "הטעם שלך" — lift גבוה על מדגם של אחד
        # הוא רעש, גם כשהחישוב עצמו נכון
        "support": {trait: rate * total_weight for trait, rate in liked_rate.items()},
        "reject_support": {trait: rate * (sum(reject_weights) or 1.0)
                          for trait, rate in rejected_rate.items()},
        "labels": labels,
        "reject_mean": reject_mean,
        "reject_spread": reject_spread,
        "reject_count": len(rejections),
        # הביטחון גדל גם מדחיות: כל תיוג הוא דוגמה, לאיזה כיוון שלא יהיה
        "confidence": (count + len(rejections)) / (count + len(rejections) + CONFIDENCE_HALF),
    }


def _similarity(normalized: dict, mean: dict, spread: dict,
                dimension_weights: dict) -> float:
    """דמיון גאוסיאני על החיתוך בין מימדי הטראק למימדי הפרופיל.

    המשקלים מנורמלים מחדש על החיתוך, אחרת טראק שנמדד לפני שמדדי הגוון נוספו
    היה מקבל מרחק קטן מלאכותית (סכום על פחות מימדים) ומדורג גבוה מדי.
    """
    shared = [d for d in mean if d in normalized]
    total = sum(dimension_weights.get(d, 0.0) for d in shared)
    if not shared or total <= 0:
        return NEUTRAL
    distance = sum((dimension_weights.get(d, 0.0) / total)
                   * (normalized[d] - mean[d]) ** 2 / (2 * spread[d] ** 2)
                   for d in shared)
    return math.exp(-distance)


def match(track: dict, features: dict | None, learned: dict) -> float:
    """כמה הטראק תואם לטעם שנלמד, 0..1 (כולל רמפת הביטחון)."""
    if not learned or not learned.get("count"):
        return 0.0

    mean = learned.get("mean") or {}
    normalized = audio.normalized(features)
    if normalized and mean:
        dimension_weights = learned["dimension_weights"]
        audio_match = _similarity(normalized, mean, learned["spread"],
                                  dimension_weights)
        reject_mean = learned.get("reject_mean") or {}
        if reject_mean:
            # קרבה לדחויים גורעת: טראק שיושב בדיוק בין השניים אינו "חצי
            # מתאים", הוא חשוד. זה מה שהופך מרכז כובד לכיוון
            away = _similarity(normalized, reject_mean, learned["reject_spread"],
                               dimension_weights)
            audio_match = max(0.0, audio_match - REJECT_PENALTY * away)
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

    # אמן ששמור בפלייליסט הוא אות ישיר וחזק, גם כשהקאבר הוא לשיר אחר לגמרי:
    # "אהבתי משהו של האמן הזה" הוא בדיוק סוג ההיכרות שהמשתמש רוצה שיעלה. דרך
    # ה-lift הממוצע לבד האות הזה נבלע — הוא מתחלק במספר התכונות של הטראק
    # הבונוס נלקח מהמרווח שנותר ולא נוסף וחתוך: כשהציון כבר קרוב ל-1 תוספת
    # קבועה נבלעת בתקרה ולא משנה דבר, וזה בדיוק המצב שבו האמן השמור אמור
    # להכריע בין שתי תוצאות טובות
    artist = f"artist:{normalize_artist(track.get('artist', ''))}"
    if (learned.get("support") or {}).get(artist):
        combined += KNOWN_ARTIST_BOOST * (1.0 - combined)

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
    # מימד ראוי לאזכור כשהוא גם משמעותי בפרופיל וגם מוכרע (לא יושב באמצע).
    # דירוג לפי המכפלה, ולא סינון לפי "מעל הממוצע": כשהמשתמש עקבי בכל
    # המימדים כולם שווים, אף אחד אינו מעל הממוצע, ולא היה נאמר דבר
    ranked = sorted(((weight * abs(learned["mean"][dimension] - 0.5), dimension)
                     for dimension, weight in dimension_weights.items()),
                    reverse=True)
    for _, dimension in ranked[:2]:
        mu = learned["mean"][dimension]
        if 0.35 < mu < 0.65:
            continue
        high, low = _DIMENSION_LABELS[dimension]
        parts.append(high if mu >= 0.65 else low)

    display = learned.get("labels") or {}
    support = learned.get("support") or {}
    for trait, value in sorted((learned.get("lift") or {}).items(),
                               key=lambda item: item[1], reverse=True):
        # תכונה שנשענת על דוגמה אחת אינה "הטעם שלך", גם אם ה-lift שלה גבוה
        if value <= 0.2 or support.get(trait, 0) < MIN_SUPPORT:
            continue
        kind, _, name = trait.partition(":")
        label = _TRAIT_LABELS.get(kind, kind)
        parts.append(f"{label} {display.get(trait, name)}".strip())
        if len(parts) >= 5:
            break

    source = f"{learned['count']} לייקים"
    if learned.get("reject_count"):
        source += f" ו-{learned['reject_count']} דחיות"

    reject_support = learned.get("reject_support") or {}
    avoided = [f"{_TRAIT_LABELS.get(t.partition(':')[0], '')} "
               f"{display.get(t, t.partition(':')[2])}".strip()
               for t, value in sorted((learned.get("lift") or {}).items(),
                                      key=lambda item: item[1])
               if value <= -0.4 and reject_support.get(t, 0) >= MIN_SUPPORT][:2]

    if not parts and not avoided:
        return f"לומד מ-{source} — עדיין אין דפוס מובהק"
    text = f"לומד מ-{source}: " + " · ".join(parts[:5])
    if avoided:
        text += " · נמנע מ: " + " · ".join(avoided)
    return text
