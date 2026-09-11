"""חלוקת התוצאות לקטגוריות: לאיזה *סוג* גרסה כל קאבר שייך.

רשימה שטוחה של שישים קאברים לאותו שיר היא רשימה שצריך לקרוא עד הסוף.
החלוקה כאן עונה על השאלה שבאמת נשאלת מול תוצאות של חיפוש קאברים —
"תראה לי את גרסאות הרוק", "יש בכלל אקפלה?" — בלי לחפש מחדש.

**קטגוריה אחת לכל קאבר**, לפי `ORDER`. גרסה שמופיעה בכמה מקומות גורמת
לסכום הקטגוריות להיות גדול ממספר התוצאות, וזה קורא כמו כפילות.

## על מה כל קטגוריה נשענת, ומה זה אומר על הכיסוי

- **כותרת/אלבום** (אקפלה, אינסטרומנטלי, טריילר): עובד לשתי החנויות, כי
  הטקסט תמיד מגיע. תופס רק את מי ש*מצהיר* על עצמו.
- **ז'אנר** (קלאסי, רוק, טראנס): מגיע מ-iTunes בלבד —
  `search.py` מחזיר `"genre": ""` לכל תוצאה מ-Deezer. לכן לכל
  קטגוריה כזו יש גם סימני כותרת, אחרת חצי מהתוצאות היו נופלות בשקט
  לקטגוריית השארית.
- **מדידה** (עדין, רגוע): מגיעה מהדפדפן שניות אחרי שהתוצאות כבר על המסך, ולכן
  שורה יכולה לעבור מ"כל השאר" ל"רגוע" תוך כדי. ראו את ההערה ב-`group`.
"""
from __future__ import annotations

import re

import audio
import search as search_module
import tags

ALL = "All"

ACAPPELLA = "A cappella"
TRAILER = "Trailer / epic"
INSTRUMENTAL = "Instrumental"
CLASSICAL = "Classical"
ROCK = "Rock"
TRANCE = "Trance / electronic"
INTIMATE = "Intimate"
CALM = "Calm"
OTHER = "Everything else"

# סדר העדיפויות **וגם** סדר התצוגה. קאבר נכנס לראשונה שמתאימה לו, ולכן
# שינוי סדר כאן משנה את החלוקה — זו הידית היחידה שצריך לגעת בה.
#
# אקפלה ראשונה כי היא הנדירה והמוצהרת ביותר: גרסה שכתוב עליה שהיא
# אקפלה היא קודם כל אקפלה. אחריה טריילר, כי זה מה שהאפליקציה הזו
# מחפשת מלכתחילה.
ORDER = (ACAPPELLA, TRAILER, INSTRUMENTAL, CLASSICAL, ROCK, TRANCE, INTIMATE,
         CALM, OTHER)

_TITLE_MARKERS = {
    ACAPPELLA: ("a cappella", "acappella", "a-cappella", "vocals only",
                "vocal only", "voice only"),
    INSTRUMENTAL: ("instrumental", "karaoke", "backing track", "no vocals",
                   "playback", "minus one"),
    CLASSICAL: ("orchestra", "orchestral", "symphony", "symphonic", "philharmonic",
                "string quartet", "strings", "cello", "violin", "piano solo",
                "solo piano", "chamber", "opera"),
    ROCK: ("rock", "metal", "punk", "grunge", "guitar", "hardcore", "riff"),
    TRANCE: ("trance", "remix", "edm", "dubstep", "house mix", "club mix",
             "techno", "electro", "dance mix", "bootleg"),
}

_GENRE_MARKERS = {
    CLASSICAL: ("classical", "opera", "chamber"),
    ROCK: ("rock", "metal", "punk", "grunge"),
    TRANCE: ("dance", "electronic", "electronica", "house", "techno", "trance", "edm"),
    INSTRUMENTAL: ("instrumental",),
}


def _haystack(track: dict) -> str:
    return f"{track.get('track', '')} {track.get('album', '')}".lower()


def _hits(text: str, markers: "tuple[str, ...]") -> bool:
    """גבול מילה **משני הצדדים**, ולא `in`.

    `search.has_epic_title` מעגן רק את ההתחלה (`\bepic`), וזה מספיק שם כי
    הסמנים שלו ארוכים וייחודיים. כאן זה לא הספיק ונמדד: `\brock` תופס את
    **Rocket Man**, כי "Rocket" מתחיל בגבול מילה. העיגון בסוף הוא מה שמפריד
    בין "Rock Cover" לבין "Rocket Man" — ולכן שתי הצורות קיימות בקוד הזה
    בכוונה, ולא מתוך חוסר עקביות.
    """
    return any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in markers)


def _is_trailer(track: dict) -> bool:
    """עדות טריילר מהכותרת, מהאלבום ומהאמן — **בלי הז'אנר**.

    `search.trailer_indicators` סופר גם `is_soundtrack`, ו-`EPIC_GENRES`
    כולל "classical" ו-"instrumental". שימוש בו כאן היה בולע את שתי
    הקטגוריות האלה לתוך "טריילר" ומשאיר אותן ריקות לנצח — כלומר החלוקה
    הייתה נראית עובדת ובעצם מסתירה בדיוק את מה שביקשו לראות.
    """
    return (search_module.has_epic_title(track)
            or search_module.has_production_album(track)
            or search_module.is_trailer_artist(track))


def _too_busy(features: "dict | None") -> bool:
    """קצבי מדיי כדי להיחשב רגוע או עדין, לפי `tags.py` ולא לפי סף חדש."""
    found = tags.tags_for(features)
    return tags.ACTION in found or tags.RELENTLESS in found


def _is_intimate(features: "dict | None") -> bool:
    """עדין = **שקט**, לפי אותו מספר שהמד בשורה כבר מצייר.

    הגרסה הקודמת דרשה את התגית INTIMATE של `tags.py`, שהיא צירוף של שלושה
    תנאים בו-זמנית (`loudness <= 0.146` וגם `onset_rate <= 1.75/s` וגם
    `low_end <= 1.68`). כמעט שום קאבר לא קיים את שלושתם, ולכן הכפתור לא
    הופיע אף פעם — נמדד, לא שוער.

    חמור מזה: הקטגוריה הייתה **חלוקה על המד שכבר מוצג בשורה**. שורה שהמד
    שלה מראה 28 נקראת שקטה לכל מי שמסתכל, ובכל זאת נפלה ל"כל השאר".
    `MID_VERSION_THRESHOLD` הוא בדיוק הסף שמתחתיו המד כבר מאפיר את המספר,
    והתיעוד שלו ב-`audio.py` אומר "ומתחת לזה היא באמת רגועה" — ולכן
    הקטגוריה מסכימה עכשיו עם המסך, בתנאי יחיד.
    """
    if not audio.measured(features) or _too_busy(features):
        return False
    return audio.bigness(features) < audio.MID_VERSION_THRESHOLD


def _is_calm(features: "dict | None") -> bool:
    """רגוע = **איטי**: קצב נמוך בלבד, בלי צירוף.

    זו תכונה מוזיקלית אחרת משקט, וזה בדיוק ההבדל בין "רגוע" ל"עדין":
    בלדה מלאה בכלים יכולה להיות איטית ובכל זאת גדולה, וגרסה שקטה יכולה
    להיות מהירה. לכן שתי קטגוריות ולא אחת, ולכן שני תנאים נפרדים.

    הסף הוא אותו `hits <= 0.35` שכבר משמש ב-`tags.py` ל-SLOW_BURN
    ול-INTIMATE — על הערכים המנורמלים, כדי ששינוי טווח ב-`audio.py` יזיז
    גם את זה.
    """
    values = audio.normalized(features)
    if not values or _too_busy(features):
        return False
    return values.get("onset_rate", 1.0) <= 0.35


# ---------- תיקוני משתמשים ----------
#
# כל מה שלמעלה נגזר מהכותרת, מהז'אנר ומהמדידה, ולכן הוא טועה בדיוק איפה
# שהמקורות האלה משקרים: אלבום בשם "Kane (Original Motion Picture
# Soundtrack)" נקרא "טריילר" גם כשמדובר בשיר פופ רגיל בפסקול. מי שרואה
# את השורה יודע את זה מיד, והכפתור "Wrong category?" הוא הדרך להגיד את זה.
#
# התיקון **משותף לכל המשתמשים**, כמו דיווחי ההתאמה: לאיזו קטגוריה שייכת
# גרסה היא עובדה עליה, לא העדפה של מי שדיווח.

# כמה תיקונים מסכימים צריך כדי להכליל מטראק בודד. אלבום הוא הפקה אחת
# ולכן שניים מספיקים; אמן הוא גוף עבודה שלם ולכן הרף גבוה יותר.
ALBUM_AGREEMENT = 2
ARTIST_AGREEMENT = 3


def correction_keys(track: dict) -> "tuple[str, str, str]":
    """(מפתח טראק, מפתח אלבום, מפתח אמן) — שלוש הרמות שתיקון יכול לחול בהן.

    מפתח האלבום נושא גם את האמן: "Greatest Hits" הוא שם של מאות אלבומים
    שונים, ותיקון על אחד מהם היה מחיל את עצמו על כולם.
    """
    artist = search_module.normalize_artist(track.get("artist", ""))
    album = " ".join((track.get("album") or "").lower().split())
    return (search_module.track_key(track.get("artist", ""), track.get("track", "")),
            f"{artist}|{album}" if artist and album else "",
            artist)


def correction_index(records: "list[dict]") -> dict:
    """מה שנלמד מהתיקונים: שלוש רמות, מהמדויק לרחב.

    זה החלק ש"לומד לשאר החיפושים". תיקון בודד חל תמיד על הטראק שתוקן,
    בכל חיפוש ובכל מצעד. הכללה לאלבום או לאמן דורשת כמה תיקונים
    **שכולם מסכימים**: מספיק שני דיווחים סותרים על אותו אלבום כדי שלא
    תהיה שם הכללה בכלל.

    למה הסכמה מלאה ולא רוב: רוב על שלושה דיווחים הוא שניים, כלומר משתמש
    אחד שטועה פעמיים היה משנה קטגוריה לכל הקטלוג של אמן. עדות מעורבת
    פירושה "לא יודעים", והנפילה לאחור היא החוקים שלמעלה — שהם לפחות
    עקביים.

    פונקציה טהורה על הרשומות, ולכן נבדקת בלי מסד נתונים ובלי רשת.
    """
    levels = {"track": {}, "album": {}, "artist": {}}
    votes = {"album": {}, "artist": {}}
    for record in records:
        category = record.get("category")
        if category not in ORDER:
            continue
        if record.get("track_key"):
            levels["track"][record["track_key"]] = category
        for level, field in (("album", "album_key"), ("artist", "artist_key")):
            if record.get(field):
                votes[level].setdefault(record[field], []).append(category)

    for level, threshold in (("album", ALBUM_AGREEMENT), ("artist", ARTIST_AGREEMENT)):
        for key, cast in votes[level].items():
            if len(cast) >= threshold and len(set(cast)) == 1:
                levels[level][key] = cast[0]
    return levels


def corrected(track: dict, corrections: "dict | None") -> "str | None":
    """הקטגוריה שנלמדה לטראק הזה, או None כשאין תיקון שחל עליו."""
    if not corrections:
        return None
    track_k, album_k, artist_k = correction_keys(track)
    for level, key in (("track", track_k), ("album", album_k), ("artist", artist_k)):
        found = corrections.get(level, {}).get(key)
        if found:
            return found
    return None


def bucket_of(track: dict, features: "dict | None" = None,
              corrections: "dict | None" = None) -> str:
    """הקטגוריה היחידה של קאבר אחד.

    תיקון של משתמש גובר על כל החוקים: הוא ראה את השורה, והחוקים כאן
    קוראים מטא-דאטה.
    """
    override = corrected(track, corrections)
    if override:
        return override

    text, genre = _haystack(track), (track.get("genre") or "").lower()

    def declared(name: str) -> bool:
        return (_hits(text, _TITLE_MARKERS.get(name, ()))
                or _hits(genre, _GENRE_MARKERS.get(name, ())))

    for name in ORDER:
        if name == OTHER:
            break
        if name == TRAILER:
            if _is_trailer(track):
                return TRAILER
        elif name == INTIMATE:
            if _is_intimate(features):
                return INTIMATE
        elif name == CALM:
            if _is_calm(features):
                return CALM
        elif declared(name):
            return name
    return OTHER


def group(tracks: list, measurements: "dict | None" = None,
          corrections: "dict | None" = None) -> "list[tuple[str, list]]":
    """(שם קטגוריה, שורות) לפי `ORDER`, בלי קטגוריות ריקות.

    הסדר בתוך כל קטגוריה הוא הסדר שהתקבל — כלומר המיון שכבר הוחל
    ב-`ordered_display` נשמר, והחלוקה לא מסדרת מחדש שום דבר.

    **הקבוצה מחושבת מחדש בכל ריצה, וזה מכוון.** המדידה מגיעה מהדפדפן
    אחרי שהתוצאות כבר על המסך, ולכן שורה יכולה לעבור פעם אחת מ"כל השאר"
    ל"רגוע" כשהמדידה שלה נוחתת. הקטגוריות עצמן לא זזות (הסדר קבוע
    ב-`ORDER`), ולכן זו השלמה של מדף ולא ערבוב מחדש של הרשימה.
    """
    measurements = measurements or {}
    found: dict = {}
    for track in tracks:
        name = bucket_of(track, measurements.get(track.get("uid")), corrections)
        found.setdefault(name, []).append(track)
    return [(name, found[name]) for name in ORDER if found.get(name)]


def counts(tracks: list, measurements: "dict | None" = None,
           corrections: "dict | None" = None) -> dict:
    """כמה קאברים בכל קטגוריה. הבסיס לשורת הכפתורים שמעל התוצאות.

    נספר על **כל** התוצאות ולא על העמוד המוצג, אחרת המספר על הכפתור היה
    אומר "כמה מזה במקרה נטען" במקום "כמה יש".
    """
    measurements = measurements or {}
    tally: dict = {}
    for track in tracks:
        name = bucket_of(track, measurements.get(track.get("uid")), corrections)
        tally[name] = tally.get(name, 0) + 1
    return tally
