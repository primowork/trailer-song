"""ממשק Streamlit: גילוי קאברים אפיים לטריילרים, עם בדיקת רפרטואר הפדרציה."""
import csv
import os
import datetime as _dt
import io
import random
import time

from urllib.parse import quote_plus

import streamlit as st
import streamlit.components.v1 as components

import artists as artists_module
import audio
import billboard as billboard_module
import classics as classics_module
import covers as covers_module
import youtube as youtube_module
import federation
import preview as preview_module
import storage
import search as search_module
import suggest as suggest_module
import taste
from search import (ALL, LENGTH_LONG, LENGTH_MEDIUM, LENGTH_SHORT, STYLES,
                    clean_artist_name, search_covers, track_key)

PAGE_SIZE = 20
# ברירת המחדל של המיון. השם אומר במפורש שהעדות על טריילר חלק מהדירוג —
# כשהתווית הבטיחה רק "הטעם שלי", לא היה מובן למה גרסה שכתוב עליה
# "Epic Trailer Version" יושבת למטה
SORT_BEST = "הכי מתאים (טעם + סימני טריילר)"

# שלושת מצבי החיפוש. "קאברים לשיר" ממזג שני מקורות (מאגר יחסי + חיפוש בחנויות)
# תחת בחירה אחת — הם עונים בפועל על אותה שאלה. "קאברים לאמן" ו"חיפוש חופשי"
# הם כוונות שונות באמת (קלט שונה; חיפוש רחב מכוון-פילטרים) ונשארים מצבים נפרדים.
# מתחת לזה התג "מתאים לטעם שלך" הוא רעש: עם מעט לייקים כל הטראקים מקבלים
# ציון נמוך דומה, ותג על כולם אינו אומר דבר
TASTE_BADGE_THRESHOLD = 0.35

MODE_SONG = "קאברים לשיר"
MODE_ARTIST = "קאברים לאמן"
MODE_FREE = "חיפוש חופשי + פילטרים"
SEARCH_MODES = [MODE_SONG, MODE_ARTIST, MODE_FREE]

# פילטר "חדשות": התווית וסף השנה שהיא מייצגת. 0 = בלי סינון.
RECENCY_OPTIONS = {
    "הכל": 0,
    "השנה האחרונה": _dt.date.today().year,
    "השנתיים האחרונות": _dt.date.today().year - 1,
    "5 השנים האחרונות": _dt.date.today().year - 4,
}

st.set_page_config(page_title="סורק קאברים - IFPI Israel", page_icon="🎵", layout="wide")

# ה-RTL מוחל על אזור התוכן ועל הסרגל בנפרד, ולא על `stAppViewContainer`
# שעוטף את שניהם. זה לא עניין של סגנון: בטלפון Streamlit מסתיר את הסרגל
# בעזרת `translateX` שלילי, וכיווניות הפוכה על השורש הפכה את ההזזה — הסרגל
# נשאר על המסך, נמעך לרוחב של כ-50px, וחפף לתוכן הראשי. זה מה שהפך את
# האפליקציה לבלתי שמישה בטלפון.
#
# `max-width` על אזור התוכן הוא התיקון לצד השני: ב-`layout="wide"` הטופס
# נמתח על פני 1400px ומפזר את העין. הרוחב הרחב עדיין משרת את הרשתות
# (אינדקס המצעדים) שבאמת צריכות אותו.
st.markdown(
    """
    <style>
    /* הגופנים נטענים כאן ולא ב-config.toml: ה-theme מקבל שם משפחה, לא כתובת.
       Heebo לכותרות (יש לה משקל 800 שנושא היררכיה), Assistant לגוף. */
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800&family=Assistant:wght@400;600&display=swap');

    /* על מסך רחב הכיווניות חלה על השורש, כדי שהסרגל יישב מימין כמו שמצופה
       בעברית. בטלפון היא נשארת מחוץ לשורש — ראו ההסבר מעל. */
    @media (min-width: 768px) {
        [data-testid="stAppViewContainer"] { direction: rtl; }
    }
    [data-testid="stMain"] { direction: rtl; }
    [data-testid="stMain"] p,
    [data-testid="stMain"] h1,
    [data-testid="stMain"] h2,
    [data-testid="stMain"] h3,
    [data-testid="stColumn"] { text-align: right; }
    [data-testid="stSidebar"] { direction: rtl; text-align: right; }

    [data-testid="stMainBlockContainer"] {
        max-width: 1180px;
        padding-top: 2.5rem;
    }

    /* מספרים בטבלה אחת: ציון 87 ו-ציון 9 חייבים להתחיל באותו מקום, אחרת
       העין קופצת בין השורות */
    [data-testid="stMain"] { font-variant-numeric: tabular-nums; }

    /* כרטיס תוצאה: מרווח פנימי הדוק יותר מברירת המחדל, כדי שיותר תוצאות
       ייכנסו למסך — זו הייתה התלונה המרכזית על הצפיפות */
    [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }
    [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] > div > div {
        padding: 0.15rem 0;
    }
    /* טקסט משני אמיתי ולא אפור-על-אפור: היררכיה במקום שש שורות זהות */
    [data-testid="stMain"] [data-testid="stCaptionContainer"] p {
        color: #8A91A3;
        font-size: 0.79rem;
        line-height: 1.45;
    }
    /* הצבע עצמו מגיע מ-`linkColor` ב-theme (חל על כל הרכיבים); כאן רק
       המעבר, שהוא מה שמסמן שהטקסט לחיץ בלי אקסנט על כל שורה */
    [data-testid="stMain"] a:hover {
        color: #FFB020 !important; text-decoration: underline;
    }

    /* נגן מותאם. נגן ה-<audio controls> של הדפדפן יושב ב-shadow DOM שלא
       ניתן לעיצוב, ולכן הוא הגיע בפלטה של הדפדפן ולא של האפליקציה — פס אפור
       שהיה הרכיב הרועש ביותר בכרטיס. כאן ה-<audio> נשאר אבל מוסתר, והפקדים
       שלנו. אלמנט אודיו אמיתי הוא מה שמשמר "רק נגן אחד בכל רגע". */
    .ts-player { display: flex; align-items: center; gap: 10px; max-width: 340px; }
    .ts-player audio { display: none; }
    /* המשולש והמקפים מצוירים ב-CSS ולא ב-SVG: Streamlit מסנן <svg> מתוך
       st.html, ואייקון מוטמע פשוט לא מגיע לדף (נבדק בדפדפן) */
    .ts-play {
        width: 32px; height: 32px; flex: none; border: none; cursor: pointer;
        border-radius: 50%; background: #FFB020;
        display: flex; align-items: center; justify-content: center; padding: 0;
    }
    .ts-play:hover { background: #FFC65C; }
    .ts-play::before {
        content: ""; width: 0; height: 0; border-style: solid;
        border-width: 6px 0 6px 10px;
        border-color: transparent transparent transparent #0B0D12;
        margin-inline-start: 2px;
    }
    .ts-play.is-playing::before {
        width: 9px; height: 11px; border: none; margin: 0;
        background: linear-gradient(90deg, #0B0D12 0 3px, transparent 3px 6px,
                                    #0B0D12 6px 9px);
    }
    .ts-bar {
        flex-grow: 1; height: 12px; cursor: pointer; position: relative;
        display: flex; align-items: center;
    }
    .ts-bar::before {
        content: ""; position: absolute; inset-inline: 0; height: 3px;
        border-radius: 2px; background: #262B38;
    }
    .ts-fill {
        position: relative; height: 3px; border-radius: 2px;
        background: #6C7488; width: 0%;
    }
    .ts-time { flex: none; font-size: 0.72rem; color: #8A91A3; }

    /* ---- סרגל עליון ושורת החיפוש ---- */
    .st-key-appbar { gap: 0.6rem; margin-bottom: 0.9rem; }
    .st-key-appbar h4 { margin: 0; padding: 0; font-size: 1.12rem; }
    /* סמל: ריבוע ענבר עם חור כהה — תקליט, לא ריבוע מלא */
    .ts-mark {
        width: 26px; height: 26px; border-radius: 7px; background: #FFB020;
        position: relative; flex: none;
    }
    .ts-mark::after {
        content: ""; position: absolute; inset: 9px;
        border-radius: 50%; background: #0B0D12;
    }

    /* שני האקספנדרים בשורה אחת: שני פסים ברוחב מלא זה אחר זה נראו כמו שני
       כרטיסים ריקים מעל התוצאות */
    .st-key-panels { gap: 0.5rem; }
    /* המסגרת שייכת למכולה, והשדות שקופים בתוכה — כך שלושת הפקדים נקראים
       כרכיב אחד ולא כשלושה טפסים נפרדים */
    .st-key-searchbar {
        border: 1px solid #2C3342; border-radius: 12px;
        background: #14171F; padding: 5px; gap: 5px;
    }
    .st-key-searchbar [data-baseweb="input"],
    .st-key-searchbar [data-baseweb="base-input"] {
        border: none !important; background: transparent !important;
    }
    .st-key-searchbar [data-testid="stTextInputRootElement"] {
        border: none; background: transparent;
    }
    .st-key-searchbar [data-testid="stElementContainer"]:first-child { flex-grow: 1; }
    /* בטלפון שדה האמן תופס שורה משלו ולא נחתך באמצע מילה */
    @media (max-width: 640px) {
        .st-key-searchbar [data-testid="stElementContainer"]:nth-child(2) {
            flex-basis: 100%;
        }
    }

    /* עטיפה חסרה: גרדיאנט וגליף במקום ריבוע אפור שטוח שמושך את העין */
    .ts-art-blank {
        border-radius: 8px; border: 1px solid #262B38;
        background: linear-gradient(135deg, #232936, #14171F);
        display: flex; align-items: center; justify-content: center;
        color: #3C4457;
    }
    @media (max-width: 640px) {
        [data-testid="stMainBlockContainer"] {
            padding: 1.25rem 0.9rem 3rem;
        }
        /* כותרת של 2.5rem גולשת לשלוש שורות במסך של 390px */
        [data-testid="stMain"] h1 { font-size: 1.7rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)



def _audio_behaviour():
    """מפעיל את הנגנים המותאמים, ומשאיר רק אחד מנגן בכל רגע.

    שתי סיבות ל-delegation על ה-document ולא ל-binding לכל נגן: הכרטיסים
    נבנים מחדש בכל rerun (וב-Streamlit כל לחיצה היא rerun), וה-iframe הזה
    אינו מורכב מחדש כשה-srcdoc זהה — כלומר סקריפט שרץ פעם אחת בכניסה לא
    ימצא אף נגן שנוצר אחריו. זה בדיוק הכשל שנמדד קודם בשומר הגלילה.
    """
    renderer = getattr(st, "iframe", None) or components.html
    renderer(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (doc.__audioBehaviourBound) return;
            doc.__audioBehaviourBound = true;

            const clock = function (seconds) {
                if (!isFinite(seconds)) return "0:00";
                const m = Math.floor(seconds / 60);
                const s = Math.floor(seconds % 60);
                return m + ":" + (s < 10 ? "0" : "") + s;
            };
            const paint = function (audio) {
                const box = audio.closest(".ts-player");
                if (!box) return;
                const fill = box.querySelector(".ts-fill");
                const time = box.querySelector(".ts-time");
                const button = box.querySelector(".ts-play");
                const ratio = audio.duration ? audio.currentTime / audio.duration : 0;
                if (fill) fill.style.width = (ratio * 100).toFixed(1) + "%";
                if (time) time.textContent = clock(audio.currentTime) + " / " + clock(audio.duration);
                if (button) button.classList.toggle("is-playing", !audio.paused);
            };

            doc.addEventListener("click", function (event) {
                const button = event.target.closest(".ts-play");
                if (button) {
                    const audio = button.closest(".ts-player").querySelector("audio");
                    if (audio) { audio.paused ? audio.play() : audio.pause(); }
                    return;
                }
                // דילוג: המיקום נגזר מהיחס ברוחב הפס, ולכן עובד גם ב-RTL
                const bar = event.target.closest(".ts-bar");
                if (bar) {
                    const audio = bar.closest(".ts-player").querySelector("audio");
                    const box = bar.getBoundingClientRect();
                    if (audio && audio.duration) {
                        audio.currentTime = ((event.clientX - box.left) / box.width) * audio.duration;
                    }
                }
            }, true);

            ["timeupdate", "loadedmetadata", "pause", "ended"].forEach(function (name) {
                doc.addEventListener(name, function (event) {
                    if (event.target instanceof window.parent.HTMLMediaElement) paint(event.target);
                }, true);
            });

            doc.addEventListener("play", function (event) {
                const started = event.target;
                if (!(started instanceof window.parent.HTMLMediaElement)) return;
                paint(started);
                doc.querySelectorAll("audio, video").forEach(function (other) {
                    if (other !== started && !other.paused) other.pause();
                });
            }, true);
        })();
        </script>
        """,
        # st.iframe דורש גובה חיובי, בניגוד ל-components.html שקיבל 0
        height=1,
    )


def _keep_scroll_position():
    """מחזיר את מקום הגלילה כשהעמוד נבנה מחדש, כדי שלא יקפוץ לראש.

    כל לחיצה ב-Streamlit היא rerun, ולחיצת ❤️ מוסיפה עוד אחד מפורש (בלעדיו
    הלב לא מתחלף עד הפעולה הבאה). בדפדפנים שבהם עוגן הגלילה לא מחזיק, הבנייה
    מחדש של ה-DOM מקפיצה לראש והמשתמש מאבד את מקומו באמצע רשימה ארוכה.

    השומר חייב להיות MutationObserver מתמשך ולא סקריפט שרץ בטעינה: נמדד
    שה-iframe אינו מורכב מחדש ב-rerun (ה-srcdoc זהה), ולכן גרסה שרצה פעם
    אחת בכניסה פשוט לא נורתה כשהיה בה צורך.

    הוא פסיבי בכוונה — משחזר רק את הצירוף "היינו עמוק בעמוד, ואחרי בנייה
    מחדש אנחנו בראשו". גלילה שהמשתמש עשה בעצמו מעדכנת את הזיכרון ולכן אינה
    נגררת אחורה, וחיפוש חדש מאפס אותו דרך סמן הדור שב-DOM.
    """
    renderer = getattr(st, "iframe", None) or components.html
    renderer(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (doc.__scrollKeeperBound) return;
            doc.__scrollKeeperBound = true;

            const target = () => {
                const main = doc.querySelector('[data-testid="stMain"]');
                return (main && main.scrollHeight > main.clientHeight)
                    ? main : doc.scrollingElement;
            };

            let saved = 0, lastBuild = 0, generation = null, pending = null;

            doc.addEventListener("scroll", function () {
                if (pending) return;
                pending = setTimeout(function () {
                    pending = null;
                    const el = target();
                    if (!el) return;
                    // אפס שמגיע מיד אחרי בנייה מחדש הוא הקפיצה עצמה, לא
                    // גלילה של המשתמש — ולכן אינו נכנס לזיכרון
                    if (el.scrollTop >= 40 || Date.now() - lastBuild > 600) {
                        saved = Math.round(el.scrollTop);
                    }
                }, 120);
            }, true);

            new MutationObserver(function () {
                lastBuild = Date.now();
                const marker = doc.querySelector("[data-result-generation]");
                const now = marker ? marker.getAttribute("data-result-generation") : null;
                if (now !== generation) {
                    // רשימה חדשה: אין לאן לחזור, ומקום ברשימה הקודמת חסר משמעות
                    generation = now;
                    saved = 0;
                    return;
                }
                const el = target();
                if (el && saved > 200 && el.scrollTop < 40) {
                    requestAnimationFrame(function () {
                        const back = target();
                        if (back) back.scrollTop = saved;
                    });
                }
            }).observe(doc.body, {childList: true, subtree: true});
        })();
        </script>
        """,
        height=1,
    )


def youtube_music_url(artist: str, track: str) -> str:
    """קישור חיפוש ב-YouTube Music לגרסה הזו.

    חיפוש ולא מזהה טראק: אין לנו מזהה YouTube לגרסאות שמגיעות מ-iTunes או
    מ-Deezer, ולשלוף אותו היה דורש קריאת API לכל שורה. שאילתת "אמן שיר"
    נוחתת על הגרסה הנכונה, ועובדת בלי מפתח ובלי בקשה מהשרת.
    """
    return "https://music.youtube.com/search?q=" + quote_plus(f"{artist} {track}".strip())


def _link_label(text: str) -> str:
    """סוגריים מרובעים בכותרת שוברים תחביר של קישור ב-markdown."""
    return text.replace("[", "\\[").replace("]", "\\]")


def audio_player(url: str):
    """נגן בשפה של האפליקציה. ההתנהגות מגיעה מ-`_audio_behaviour`.

    `st.audio` מרנדר `<audio controls>`, ופקדי הדפדפן יושבים ב-shadow DOM
    שלא ניתן לעצב — ולכן הוא נראה כמו הדפדפן ולא כמו האפליקציה. כאן
    ה-`<audio>` נשאר (וזה מה שמשמר "רק נגן אחד בכל רגע"), רק הפקדים שלנו.
    `preload="none"` כדי שעשרים תוצאות לא ימשכו עשרים קבצים מראש.
    """
    st.html(
        "<div class='ts-player'>"
        "<button class='ts-play' type='button' aria-label='נגן'></button>"
        "<div class='ts-bar'><div class='ts-fill'></div></div>"
        "<span class='ts-time'>0:00</span>"
        f"<audio preload='none' src='{url}'></audio>"
        "</div>")


# ---------- מצב ----------

def _init_state():
    defaults = {
        "statuses": storage.load_statuses(),
        "blacklist": storage.load_blacklist(),
        "cache": storage.load_cache(),
        "favorites": storage.load_favorites(),
        "rejections": storage.load_rejections(),
        "candidates": [],
        "seen_keys": set(),
        "visible_count": PAGE_SIZE,
        # סדר התצוגה קפוא (ראו `ordered_display`): רשימת uid, החתימה שיצרה
        # אותה, ומונה שעולה בכל חיפוש חדש
        "display_order": [],
        "order_signature": None,
        "result_generation": 0,
        # מונה שמפתח האקספנדר של אינדקס המצעדים נגזר ממנו. העלאתו מרנדרת
        # רכיב חדש, שנולד מכווץ — ראו את ההסבר ליד האקספנדר עצמו
        "index_generation": 0,
        "recent_rolls": [],
        "last_query": "",
        "debug_mode": False,
        "covers_source": "",
        "work_candidates": [],
        "bigness": {},
        "evidence": {},
        "original": None,
        "federation_blocked": False,
        "all_inputs": [],
        "suggest_query": "",
        "suggestions": [],
        "artist_preview_query": "",
        "artist_preview_titles": [],
        "cors_retried": set(),
        "federation_probed": False,
        "similar_of": None,
        "pending_fields": None,
        "index_source": "🎻 קלאסיקות",
        "search_mode": MODE_SONG,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()


def is_blacklisted(artist: str) -> bool:
    return clean_artist_name(artist).lower() in st.session_state["blacklist"]


def apply_blacklist(tracks: list[dict]) -> list[dict]:
    return [t for t in tracks if not is_blacklisted(t.get("artist", ""))]


# ---------- ❤️ פלייליסט וטעם נלמד ----------

# שדות שנשמרים בפלייליסט: מספיק כדי להציג את הגרסה מאוחר יותר, ומספיק כדי
# ללמוד ממנה. שמירת הטראק המלא הייתה גוררת גם שדות רגעיים כמו `score`.
FAVORITE_FIELDS = ("artist", "track", "album", "genre", "year", "duration_sec",
                   "preview_url", "artwork", "source", "catalog_source",
                   "trailer_indicator")


def is_favorite(track: dict) -> bool:
    return track_key(track.get("artist", ""), track.get("track", "")) in st.session_state["favorites"]


def is_rejected(track: dict) -> bool:
    return track_key(track.get("artist", ""), track.get("track", "")) in st.session_state["rejections"]


def origin_of(track: dict) -> dict:
    """השיר המקורי שהגרסה הזו מכסה — המפתח שלפיו הפלייליסט מקובץ.

    `origin_track` מסומן ב-`covers.py` בחיפוש לפי אמן וב"עוד קאברים", אבל
    לא בחיפוש רגיל לפי שיר; שם הכותרת עצמה נושאת את התשובה אחרי ניקוי
    תגיות הגרסה (`clean_track_title` הקיימת: "Yellow (Epic Trailer
    Version)" ← "Yellow"). האמן המקורי הוא מה שהמשתמש הקליד בשדה האמן,
    או שאת הקטלוג שלו סרקנו — ולכן `cover_artist`.
    """
    # מה שהמשתמש חיפש קודם לניקוי הכותרת: שתי גרסאות של אותו שיר יכולות
    # להיקרא "Bitter Sweet Symphony" ו-"Bittersweet Symphony", והניקוי לבדו
    # היה מפצל אותן לשתי קבוצות. השאילתה זהה לשתיהן, ולכן היא המפתח הנכון.
    title = (track.get("origin_track")
             or (st.session_state.get("cover_title") or "").strip()
             or search_module.clean_track_title(track.get("track", ""))
             or track.get("track", ""))
    return {"track": title.strip(),
            "artist": (st.session_state.get("cover_artist") or "").strip()}


def origin_key(entry: dict) -> str:
    """מפתח הקיבוץ. לרשומות שנשמרו לפני שהשדה נוסף — נגזר בקריאה.

    זה מה שמייתר סקריפט מיגרציה: פלייליסט קיים מתקבץ נכון בלי לגעת
    ב-`favorites.json` של המשתמש.
    """
    origin = entry.get("origin") or {}
    title = (origin.get("track")
             or search_module.clean_track_title(entry.get("track", ""))
             or entry.get("track", ""))
    return track_key(origin.get("artist", ""), title)


def _snapshot(track: dict) -> dict:
    features = st.session_state["bigness"].get(track["uid"])
    return {
        **{field: track.get(field) for field in FAVORITE_FIELDS},
        # שיר המקור, כדי שהפלייליסט יוכל לשרשר את כל הגרסאות שלו יחד
        "origin": origin_of(track),
        # המדידה נשמרת ברגע התיוג כדי שהלמידה לא תהיה תלויה בכך שהטראק יימדד
        # שוב בעתיד; אם עוד לא נמדד, נלמד ממנו קטגוריאלית בלבד
        "features": features if audio.measured(features) else None,
        "added_at": time.time(),
    }


def toggle_favorite(track: dict):
    """מוסיף או מסיר מהפלייליסט. הפלייליסט הוא גם מאגר האימון החיובי."""
    favorites, rejections = st.session_state["favorites"], st.session_state["rejections"]
    key = track_key(track.get("artist", ""), track.get("track", ""))
    if key in favorites:
        favorites.pop(key)
    else:
        favorites[key] = _snapshot(track)
        # אותו טראק לא יכול להיות גם אהוב וגם דחוי
        if rejections.pop(key, None) is not None:
            storage.save_rejections(rejections)
    storage.save_favorites(favorites)


def toggle_rejection(track: dict):
    """מסמן "לא זה". דוגמאות שליליות הן שנותנות ללמידה כיוון ולא רק מרכז."""
    favorites, rejections = st.session_state["favorites"], st.session_state["rejections"]
    key = track_key(track.get("artist", ""), track.get("track", ""))
    if key in rejections:
        rejections.pop(key)
    else:
        rejections[key] = _snapshot(track)
        if favorites.pop(key, None) is not None:
            storage.save_favorites(favorites)
    storage.save_rejections(rejections)


def taste_profile(background: list[dict] | None = None) -> dict:
    """הפרופיל הנלמד. הרקע הוא פול התוצאות המוצג, ובלעדיו זה מונה שכיחות."""
    return taste.profile(list(st.session_state["favorites"].values()), background,
                         rejections=list(st.session_state["rejections"].values()))


def taste_of(track: dict, learned: dict) -> float:
    return taste.match(track, st.session_state["bigness"].get(track["uid"]), learned)


def status_of(track: dict) -> dict | None:
    return st.session_state["statuses"].get(track["uid"])


def record_status(track: dict, result: federation.VerifyResult):
    payload = result.to_dict()
    st.session_state["statuses"][track["uid"]] = payload
    st.session_state["cache"][storage.cache_key(track["artist"], track["track"])] = {
        **payload, "cached_at": time.time(),
    }
    storage.save_statuses(st.session_state["statuses"])
    storage.save_cache(st.session_state["cache"])


def cached_result(track: dict) -> federation.VerifyResult | None:
    entry = st.session_state["cache"].get(storage.cache_key(track["artist"], track["track"]))
    if not entry:
        return None
    payload = {k: v for k, v in entry.items() if k != "cached_at"}
    try:
        return federation.VerifyResult(**payload)
    except TypeError:
        return None


def verify_tracks(tracks: list[dict]):
    """בדיקת אצווה: קודם מהקאש, השאר בדפדפן אחד משותף עם preflight אחד."""
    pending = []
    for track in tracks:
        cached = cached_result(track)
        if cached and cached.status != federation.UNKNOWN:
            st.session_state["statuses"][track["uid"]] = cached.to_dict()
        else:
            pending.append(track)

    if not pending:
        st.toast("כל התוצאות הוחזרו מהקאש", icon="⚡")
        storage.save_statuses(st.session_state["statuses"])
        return

    progress = st.progress(0.0, text="מתחיל בדיקה...")
    with federation.FederationClient(debug=st.session_state["debug_mode"]) as client:
        # preflight אחד לכל האצווה: אם הטופס לא זוהה, אין טעם לנסות שיר-שיר
        if not client.preflight():
            st.session_state["federation_blocked"] = True
            st.error(f"הבדיקה לא יצאה לדרך: {client.preflight_error}")
            for track in pending:
                record_status(track, federation.VerifyResult(
                    status=federation.UNKNOWN, error=client.preflight_error, strategy="preflight"))
            progress.empty()
            return

        for index, track in enumerate(pending):
            progress.progress(
                index / len(pending),
                text=f"בודק {index + 1}/{len(pending)}: {track['artist']} - {track['track']}",
            )
            record_status(track, client.verify(track))
            if st.session_state["debug_mode"] and client.last_html:
                path = storage.save_debug_html(client.last_html, "last_scan")
                if path:
                    st.session_state["debug_path"] = path
    progress.progress(1.0, text="הסתיים")


def queue_fields(title: str = "", artist: str = "", mode: str | None = None,
                 auto_run: bool = False):
    """קובע את שדות החיפוש (ואופציונלית מצב + הרצה אוטומטית) מכפתור, ומרענן.

    Streamlit אוסר על שינוי session_state של widget אחרי שהוא נוצר, ולכן אי אפשר
    לכתוב לשדה מתוך כפתור שמצויר מתחתיו. הערך נשמר כאן ומוחל בתחילת הריצה הבאה,
    לפני שהשדות/הרדיו נוצרים.
    """
    st.session_state["pending_fields"] = (title, artist, mode, auto_run)
    st.rerun()


def _render_saved_versions(versions: list, favorites: dict):
    """הגרסאות של שיר מקור אחד. אותה שורה כמו קודם, רק תחת כותרת קבוצה."""
    for key, entry in versions:
        label = entry.get("artist", "") or entry.get("track", "")
        row = st.container(horizontal=True, wrap=False, vertical_alignment="center")
        with row:
            # לחיצה על גרסה שמורה מחזירה אליה: ממלאת את השדות ומריצה חיפוש
            # לשיר הזה, כדי שאפשר יהיה למצוא אותה ואת מה שדומה לה שוב
            if st.button(label[:34], key=f"fav_open_{key}",
                         help=f"{entry.get('artist', '')} — {entry.get('track', '')}",
                         width="stretch"):
                queue_fields(entry.get("track", ""), entry.get("artist", ""),
                             mode=MODE_SONG, auto_run=True)
            if entry.get("preview_url"):
                # בתוך אותה שורה ולא מתחתיה: אחרת חמש-עשרה שמורות הן
                # שלושים שורות בסרגל
                with st.popover("", icon=":material/play_arrow:", width=54):
                    audio_player(entry["preview_url"])
            if st.button("", key=f"unfav_{key}", icon=":material/close:",
                         help="הסר מהפלייליסט"):
                favorites.pop(key)
                storage.save_favorites(favorites)
                st.rerun()


# ---------- סרגל צד ----------

with st.sidebar:
    st.markdown("### הפלייליסט שלי")
    favorites = st.session_state["favorites"]
    st.write(f"גרסאות שמורות: **{len(favorites)}**")

    if favorites:
        learned_sidebar = taste_profile()
        summary = taste.describe(learned_sidebar)
        if summary:
            st.caption(summary)

        # מקובץ לפי שיר המקור, ולא רשימה שטוחה: כל הגרסאות של אותו שיר
        # יושבות יחד, וזו גם הדרך שבה חושבים על פלייליסט של קאברים.
        groups: dict[str, list[tuple[str, dict]]] = {}
        for key, entry in favorites.items():
            groups.setdefault(origin_key(entry), []).append((key, entry))

        def newest(items) -> float:
            return max(entry.get("added_at", 0) for _, entry in items)

        for versions in sorted(groups.values(), key=newest, reverse=True):
            versions.sort(key=lambda item: item[1].get("added_at", 0), reverse=True)
            origin = versions[0][1].get("origin") or {}
            song = (origin.get("track")
                    or search_module.clean_track_title(versions[0][1].get("track", ""))
                    or versions[0][1].get("track", ""))
            by = origin.get("artist")
            st.markdown(f"**{song}**" + (f" · {by}" if by else "")
                        + f" &nbsp;:gray[{len(versions)}]")
            _render_saved_versions(versions, favorites)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["שיר מקור", "אמן מקור", "אמן", "שיר", "אלבום",
                         "ז'אנר", "שנה", "preview"])
        # ממוין באותו קיבוץ כמו במסך, אחרת הקובץ מאבד את מה שהסרגל מראה
        for _, entry in sorted(favorites.items(), key=lambda item: (
                origin_key(item[1]), -item[1].get("added_at", 0))):
            origin = entry.get("origin") or {}
            writer.writerow([origin.get("track", ""), origin.get("artist", ""),
                             entry.get("artist", ""), entry.get("track", ""),
                             entry.get("album", ""), entry.get("genre", ""),
                             entry.get("year", ""), entry.get("preview_url", "")])
        st.download_button("ייצא פלייליסט", icon=":material/download:",
                           data=buffer.getvalue().encode("utf-8-sig"),
                           file_name="playlist.csv", mime="text/csv")
    else:
        st.caption("סמן ❤️ ליד גרסה שאהבת. היא תישמר כאן, והדירוג ילמד "
                   "מה מאפיין את מה שאתה אוהב ויעלה גרסאות כאלה לראש.")

    st.divider()
    st.markdown("### הגדרות")
    st.session_state["debug_mode"] = st.checkbox(
        "מצב דיבאג (שמירת HTML מהפדרציה)", value=st.session_state["debug_mode"]
    )
    if st.session_state.get("debug_path"):
        st.caption(f"נשמר: `{st.session_state['debug_path']}`")

    st.caption(f"רפרטואר: `{federation.FEDERATION_URL}`")

    with st.expander("בדיקה ידנית דרך הדפדפן שלך", icon=":material/link:"):
        st.caption(
            "האתר חוסם את השרת אבל נטען בדפדפן שלך. המסלול הזה מנתב דרכו: "
            "פעם אחת מלמדים את שמות השדות, ואז כל שיר נבדק בקליק והדבקה."
        )
        fields = federation.learned_fields()
        if fields["artist_field"] or fields["track_field"]:
            st.success(f"שדות ידועים: אמן=`{fields['artist_field'] or '—'}` · "
                       f"שיר=`{fields['track_field'] or '—'}`")
        else:
            st.warning("שמות השדות עדיין לא נלמדו")

        st.markdown(f"[פתח את דף החיפוש]({federation.FEDERATION_URL}) ← Ctrl+U ← העתק הכל")
        page_html = st.text_area("הדבק כאן את ה-HTML של דף החיפוש:", height=100,
                                 key="learn_html")
        if st.button("למד שמות שדות") and page_html.strip():
            learned = federation.learn_fields_from_html(page_html)
            storage.save_debug_html(page_html, "search_page")
            if learned["artist_field"] or learned["track_field"]:
                st.success(f"זוהו: אמן=`{learned['artist_field'] or '—'}` · "
                           f"שיר=`{learned['track_field'] or '—'}`")
                st.rerun()
            elif learned["all_inputs"]:
                st.session_state["all_inputs"] = learned["all_inputs"]
                st.warning("אף שדה מוכר לא נמצא — בחר ידנית מהרשימה למטה")
            else:
                st.error("לא נמצאו שדות קלט בדף. ודא שהעתקת את כל ה-HTML.")

        options = st.session_state.get("all_inputs") or []
        if options:
            col_a, col_t = st.columns(2)
            picked_artist = col_a.selectbox("שדה האמן:", [""] + options)
            picked_track = col_t.selectbox("שדה השיר:", [""] + options)
            if st.button("שמור שדות") and (picked_artist or picked_track):
                federation.set_fields(picked_artist, picked_track)
                st.session_state["all_inputs"] = []
                st.rerun()

    if st.button("בדוק חיבור לפדרציה", icon=":material/monitor_heart:"):
        with st.spinner("בודק..."):
            report = federation.diagnose()
        html = report.pop("html", "")
        st.json(report)
        if html:
            path = storage.save_debug_html(html, "diagnose")
            if path:
                st.caption(f"HTML נשמר: `{path}`")
                st.download_button("הורד את ה-HTML", icon=":material/download:", data=html.encode("utf-8"),
                                   file_name="ifpi_search.html", mime="text/html")
        else:
            st.error("השרת לא הצליח להגיע לאתר הפדרציה. "
                     "אם זה עובד מהדפדפן שלך אבל לא מכאן, החסימה היא ברשת של השרת.")
    st.caption(f"תיקיית נתונים: `{storage.DATA_DIR or 'לא זמינה'}`")
    if not youtube_module.available():
        # מידע על פיצ'ר כבוי, לא שלב במסלול — ולכן כאן ולא בין התוצאות
        st.caption("אימות שימוש בטריילר כבוי (הגדר YOUTUBE_API_KEY)")
    with st.expander("ייבוא מצעד בילבורד", icon=":material/upload:"):
        st.caption("שמור עמוד מצעד מהדפדפן (Ctrl+S / Cmd+S) והעלה אותו כאן. "
                   "אין ל-billboard.com API ציבורי, והם חוסמים שרתים — לכן הייבוא "
                   "עובר דרך הדפדפן שלך, שבו העמוד כבר נטען.")
        uploaded = st.file_uploader("עמוד מצעד שמור:", type=["html", "htm"],
                                    key="chart_upload")
        if uploaded is not None and st.button("ייבא"):
            chart = billboard_module.parse_chart(
                uploaded.getvalue().decode("utf-8", errors="ignore"))
            if not chart["entries"]:
                st.error("לא זוהו שורות מצעד בעמוד הזה.")
            else:
                slug = billboard_module.chart_slug(chart["title"])
                stored = storage.load_charts()
                stored[slug] = {**chart, "slug": slug}
                if storage.save_charts(stored):
                    st.success(f"יובאו {len(chart['entries'])} שורות מ'{chart['title']}'")
                    st.rerun()
                else:
                    st.error("אין תיקיית נתונים לכתיבה — המצעד לא נשמר.")

        stored = storage.load_charts()
        if stored:
            to_remove = st.selectbox("הסר מצעד:", [""] + [c["title"] for c in stored.values()])
            if to_remove and st.button("הסר"):
                storage.save_charts({slug: chart for slug, chart in stored.items()
                                     if chart["title"] != to_remove})
                st.rerun()

    # הדחיות אינן פלייליסט ולכן אינן מוצגות כרשימה — הן רק מלמדות
    if st.session_state["rejections"]:
        with st.expander(f"👎 סימנת 'לא זה' ({len(st.session_state['rejections'])})"):
            st.caption("הדחיות אינן מוסתרות מהתוצאות — הן רק מלמדות את הדירוג "
                       "להתרחק מהסגנון הזה. להסתרה מלאה יש 🚫 חסום אמן.")
            if st.button("נקה דחיות", icon=":material/delete:"):
                st.session_state["rejections"] = {}
                storage.save_rejections({})
                st.rerun()

    # החסימה עצמה נשארת פעילה; רק התצוגה שלה ירדה מהחזית לטובת הפלייליסט
    with st.expander(f"🚫 רשימה שחורה ({len(st.session_state['blacklist'])})"):
        blacklist = sorted(st.session_state["blacklist"])
        if not blacklist:
            st.caption("אין אמנים חסומים.")
        for artist in blacklist:
            col_name, col_undo = st.columns([3, 1])
            col_name.write(artist)
            if col_undo.button("↩️", key=f"unblock_{artist}", help="בטל חסימה"):
                st.session_state["blacklist"].discard(artist)
                storage.save_blacklist(st.session_state["blacklist"])
                st.rerun()

        if blacklist and st.button("נקה רשימה שחורה", icon=":material/delete:"):
            st.session_state["blacklist"] = set()
            storage.save_blacklist(st.session_state["blacklist"])
            st.rerun()

    if st.button("נקה קאש בדיקות", icon=":material/mop:"):
        st.session_state["cache"] = {}
        storage.save_cache({})
        st.toast("הקאש נוקה", icon="🧹")

    for warning in storage.warnings:
        st.warning(warning)


def probe_federation():
    """בודק פעם אחת לסשן אם השרת בכלל מגיע לאתר הפדרציה.

    בלי זה המשתמש מגלה את החסימה רק אחרי שהוא לוחץ "בדוק את כל התוצאות" ומחכה,
    ומקבל שגיאה אדומה. הבדיקה היא חיבור TCP קצר ולא preflight מלא, כדי שהיא לא
    תעכב את הצגת התוצאות.
    """
    if st.session_state["federation_probed"]:
        return
    st.session_state["federation_probed"] = True
    if not federation.reachable():
        st.session_state["federation_blocked"] = True


# ---------- מדידת גודל בדפדפן ----------

_MEASURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "components", "audio_meter")
_audio_meter = components.declare_component("audio_meter", path=_MEASURE_DIR)
# מופע שני לאותו רכיב: המסלול הישיר והמעקף רצים באותו rerun וצריכים key נפרד
_audio_meter_proxy = components.declare_component("audio_meter_proxy", path=_MEASURE_DIR)

# כמה טראקים לעקוף בכל סבב. ה-data URI הוא מגה-בייטים, וכולם עוברים דרך הדף
CORS_FALLBACK_BATCH = 4


def measure_visible(tracks: list):
    """מודד את כל המוצגים אוטומטית, בדפדפן של המשתמש.

    המדידה חייבת לרוץ בצד הלקוח: פענוח אודיו בשרת דורש תלות כבדה, והשרת הזה
    ממילא חסום לחלק מהחנויות. מה שכבר נמדד נשמר לקאש לפי track_key ולא נמדד שוב.
    """
    cache = storage.load_bigness()
    pending = []
    for track in tracks:
        uid = track["uid"]
        if uid in st.session_state["bigness"]:
            continue
        key = track_key(track["artist"], track["track"])
        if key in cache:
            st.session_state["bigness"][uid] = cache[key]
        elif track.get("preview_url"):
            pending.append({"uid": uid, "url": track["preview_url"]})

    if not pending:
        return

    results = _audio_meter(tracks=pending, key="audio_meter", default=None)
    if not results:
        st.caption("🎚️ מודד את עוצמת הטראקים בדפדפן…")
        return

    _merge_results(results, tracks, cache, overwrite=False)


def _merge_results(results: dict, tracks: list, cache: dict, overwrite: bool):
    """מכניס מדידות ל-session_state ולקאש, ומרענן כדי שהשורות יתעדכנו."""
    by_uid = {t["uid"]: t for t in tracks}
    fresh, cacheable = False, False
    for uid, features in results.items():
        if not overwrite and uid in st.session_state["bigness"]:
            continue
        st.session_state["bigness"][uid] = features
        fresh = True
        track = by_uid.get(uid)
        # שגיאה לא נכנסת לקאש: היא עשויה להיות זמנית, ו"לא נמדד" אינו תוצאה
        if track and not features.get("error"):
            cache[track_key(track["artist"], track["track"])] = features
            cacheable = True
    if cacheable:
        storage.save_bigness(cache)
    if fresh:
        # גם כשהכל נכשל: השורות כבר רונדרו, בלי rerun ה-⚪ לא יופיע עד הקליק הבא
        st.rerun()


def measure_via_server(tracks: list):
    """מעקף לחסימת CORS: השרת מושך את הבייטים, הדפדפן עדיין מפענח ומודד.

    רץ רק על מה שנכשל במסלול הישיר, בקבוצות קטנות — כל preview עובר דרך הדף
    כ-data URI. כל טראק מנוסה פעם אחת בלבד, אחרת סבב שנכשל היה חוזר בלולאה.
    """
    blocked = [t for t in tracks
               if st.session_state["bigness"].get(t["uid"], {}).get("error") == "cors_failed"
               and t["uid"] not in st.session_state["cors_retried"]]
    if not blocked:
        return

    batch = blocked[:CORS_FALLBACK_BATCH]
    payload, failures = [], {}
    with st.spinner("מושך את ה-preview דרך השרת (החנות חוסמת מדידה ישירה)…"):
        for track in batch:
            data_uri, error = preview_module.fetch_data_uri(track.get("preview_url", ""))
            if error:
                failures[track["uid"]] = {"error": error}
            else:
                payload.append({"uid": track["uid"], "url": data_uri})

    cache = storage.load_bigness()
    if failures:
        st.session_state["cors_retried"].update(failures.keys())
        _merge_results(failures, tracks, cache, overwrite=True)
    if not payload:
        return

    results = _audio_meter_proxy(tracks=payload, key="audio_meter_proxy", default=None) or {}
    # הרכיב מחזיק את הערך של הסבב הקודם עד שה-JS שולח חדש. בלי הסינון הזה היינו
    # ממזגים שוב את אותן תוצאות בכל rerun, ועם overwrite זו לולאה אינסופית
    sent = {item["uid"] for item in payload}
    measured_now = {uid: features for uid, features in results.items() if uid in sent}
    if not measured_now:
        st.caption(f"🎚️ מודד {len(payload)} טראקים דרך השרת…")
        return

    st.session_state["cors_retried"].update(measured_now.keys())
    _merge_results(measured_now, tracks, cache, overwrite=True)


# ---------- סדר התצוגה ----------

# משקלי הדירוג הראשי. שלושתם באותה סקאלה 0..1, ולכן הם מתחרים ולא
# מבטלים זה את זה — בניגוד למיון לקסיקוגרפי, שבו המפתח הראשון מכריע לבדו.
# המשקלים כוילו מול שלושה מקרים ולא לפי תחושה:
#   א. בלי שום למידה, גרסה שכתוב עליה "Epic Trailer Version" חייבת לעלות
#      מעל קאבר פופ רועש — גם כשהיא עצמה טרם נמדדה  (0.30 מול 0.10)
#   ב. אחרי שישה ❤️ על סגנון רגוע, גרסה רגועה חייבת לנצח גרסה "אפית"
#      רועשת עם שני סימני טריילר                     (0.41 מול 0.34)
#   ג. אחרי ארבעה 👎 על סגנון, טראק מאותו סגנון יורד (0.46 מול 0.29)
# משקל טעם של 0.40 נכשל ב-(ג), 0.55 נכשל ב-(ב), 0.65 עובר את שלושתם
# במרווח נוח. הפריור על טריילר הוא מה שקובע כשאין עדיין מה ללמוד ממנו:
# `taste_of` מחזיר 0 לכולם עד הלייק הראשון.
RANK_TASTE = 0.65      # מה שהמשתמש לימד בפועל — גובר על הפריור
RANK_TRAILER = 0.25    # עדות מפורשת שזו גרסת טריילר — הסיבה שהאפליקציה קיימת
RANK_SIZE = 0.10       # המדידה בדפדפן. יש גם מיון מפורש "גודל (נמדד)"
# "טרם נמדד" אינו "קטן". הערך הקודם היה -1, ולכן כל טראק שהמדידה לא הגיעה
# אליו (אין preview, חסימת CORS, כישלון) צנח לתחתית — גם כשכתוב עליו
# במפורש "Epic Trailer Version" ויש לו שני סימני טריילר.
NEUTRAL_SIZE = 0.5


def rank_score(track: dict, learned: dict, measurements: dict) -> float:
    """הדירוג הראשי: טעם, עדות טריילר ומדידה — ביחד ולא בזה אחר זה.

    קודם המפתח היה `(taste, measured_size, score)` לקסיקוגרפית. בלי לייקים
    הטעם היה 0 לכולם, ולכן הגודל הנמדד הכריע לבדו ו-`score` — שכולל את
    `epic_bonus` — לא נגע בסדר בפועל. נמדד: טראק בשם "Zombie (Epic Trailer
    Version)", ז'אנר Soundtrack, ציון 130 מול 100, דורג **אחרון** מול קאבר
    פופ רגיל שנמדד רועש. זה ההפך ממה שהאפליקציה אמורה לעשות.
    """
    features = measurements.get(track["uid"])
    size = (audio.bigness(features) / 100.0 if audio.measured(features)
            else NEUTRAL_SIZE)
    return (RANK_TASTE * taste_of(track, learned)
            + RANK_TRAILER * search_module.trailer_strength(track)
            + RANK_SIZE * size)


def sorted_by(tracks: list, sort_by: str, learned: dict) -> list:
    """הסדר המבוקש, מחושב על הנתונים שיש **ברגע זה**."""
    ranked = list(tracks)
    measurements = st.session_state.get("bigness", {})

    def measured_size(track):
        features = measurements.get(track["uid"])
        # במיון המפורש לפי גודל, "טרם נמדד" באמת יורד לתחתית ולא מתחזה למדוד
        return audio.bigness(features) if audio.measured(features) else -1

    if sort_by == SORT_BEST:
        # ברירת המחדל. `score` נשאר רק כשובר שוויון
        ranked.sort(key=lambda t: (round(rank_score(t, learned, measurements), 4),
                                   t.get("score", 0)), reverse=True)
    elif sort_by == "גודל (נמדד)":
        ranked.sort(key=lambda t: (measured_size(t), t.get("score", 0)), reverse=True)
    elif sort_by == "ציון":
        ranked.sort(key=lambda t: t.get("score", 0), reverse=True)
    elif sort_by == "חדשים קודם":
        ranked.sort(key=lambda t: search_module.release_year(t), reverse=True)
    elif sort_by == "אורך (עולה)":
        ranked.sort(key=lambda t: t.get("duration_sec", 0))
    elif sort_by == "אורך (יורד)":
        ranked.sort(key=lambda t: t.get("duration_sec", 0), reverse=True)
    elif sort_by == "אמן":
        ranked.sort(key=lambda t: t.get("artist", "").lower())
    return ranked


def ordered_display(tracks: list, sort_by: str, only_approved: bool, learned: dict) -> list:
    """הסדר נקבע פעם אחת ונשאר — הליבה של תיקון "הכל קופץ".

    מפתח המיון הראשי תלוי במדידות האודיו שממשיכות לזרום מהדפדפן אחרי
    שהתוצאות כבר על המסך, וגם ב-`learned` שמשתנה בכל לחיצת ❤️. כשהוא חושב
    מחדש בכל rerun, נמדד ש-20 מתוך 20 השורות הנראות משנות מיקום ברגע
    שהמדידות חוזרות, ושלחיצת ❤️ אחת דוחפת שלושה שירים אל מעבר ל-20
    המוצגים — כלומר הם "נעלמים". גרוע מכך: ל-`st.audio` אין `key`, ולכן
    זהות הנגן היא מיקומית, ואחרי שינוי סדר הצליל של שיר אחד יושב על
    הכרטיס של שיר אחר (נמדד בדפדפן: הנגן המנגן עבר משורה 1 לשורה 3).

    לכן הסדר נשמר כרשימת uid ומחושב מחדש רק כשמשתנה החתימה — בורר המיון,
    הפילטר, או חיפוש חדש. הדירוג לפי טעם לא בוטל, רק רגע ההחלה שלו הוקפא;
    `resort_button` מחזיר את השליטה למשתמש.
    """
    signature = (sort_by, only_approved, st.session_state["result_generation"])
    if st.session_state["order_signature"] != signature:
        st.session_state["order_signature"] = signature
        st.session_state["display_order"] = [t["uid"] for t in
                                             sorted_by(tracks, sort_by, learned)]
    return apply_order(tracks, st.session_state["display_order"])


def apply_order(tracks: list, order: list) -> list:
    """מסדר לפי רשימת uid שמורה. מה שנעלם יורד, מה שחדש נוסף בסוף.

    "חדש" קורה כשהמשתמש לוחץ "עוד קאברים לשיר הזה" באמצע רשימה קיימת;
    "נעלם" קורה בחסימת אמן. בשני המקרים שאר השורות לא זזות.
    """
    by_uid = {t["uid"]: t for t in tracks}
    kept = [by_uid[uid] for uid in order if uid in by_uid]
    known = set(order)
    return kept + [t for t in tracks if t["uid"] not in known]


def resort_button(display: list, sort_by: str, learned: dict):
    """מיישם את מה שנלמד מאז — ביוזמת המשתמש, ולא באמצע האזנה.

    בלי זה ההקפאה הייתה מסתירה את הלמידה עד החיפוש הבא. הכפתור אומר מראש
    כמה שורות יזוזו, כדי שהתזוזה לא תהיה הפתעה.
    """
    fresh = [t["uid"] for t in sorted_by(display, sort_by, learned)]
    current = [t["uid"] for t in display]
    moving = sum(1 for old, new in zip(current, fresh) if old != new)

    # הכפתור מצויר תמיד, גם כשאין מה לסדר — כפתור שמופיע ונעלם מעל הרשימה
    # דוחף את כל מה שמתחתיו (נמדד: 17px בכל לחיצת ❤️), וזה בדיוק מה שמזיז
    # את המקום שבו המשתמש היה
    label = (f"סדר מחדש לפי {sort_by} ({moving} שירים יזוזו)" if moving
             else "הסדר מעודכן")
    if st.button(label, disabled=not moving, icon=":material/sort:",
                 help="הסדר קפוא בזמן עיון כדי שהרשימה לא תזוז תוך כדי האזנה. "
                      "כאן מיישמים את מה שנלמד מאז — מדידות אודיו חדשות ולייקים."):
        st.session_state["display_order"] = fresh
        st.rerun()


# ---------- הצגת שיר בודד ----------

# מדרגות הציון, וכל אחת עם צבע התג שלה. ענבר שמור ל"גדול" בלבד — אקסנט
# שמופיע על כל שורה מפסיק לסמן משהו.
SCORE_TIERS = (
    (audio.BIG_VERSION_THRESHOLD, "orange", "גדול"),
    (audio.MID_VERSION_THRESHOLD, "gray", "בינוני"),
    (0, "gray", "רגוע"),
)
ARTWORK_SIZE = 56


def _score_badge(features: dict | None):
    """הציון כתג ולא כשורת טקסט אפור. זה הנתון שהאפליקציה קיימת בשבילו."""
    if audio.measured(features):
        score = audio.bigness(features)
        color, _ = next((c, l) for threshold, c, l in SCORE_TIERS if score >= threshold)
        # המספר בלבד: הצבע כבר נושא את המדרגה (ענבר = גדול), ומילה נוספת
        # הרחיבה את התג עד ששורת המטא נשברה לשתי שורות בטלפון
        st.badge(str(score), icon=":material/graphic_eq:", color=color)
    elif (features or {}).get("error") == "cors_failed":
        st.badge("נמדד דרך השרת", icon=":material/hourglass_empty:", color="gray")
    else:
        st.badge("טרם נמדד", icon=":material/hourglass_empty:", color="gray")


def _status_line(status: dict | None) -> str:
    """סטטוס הרפרטואר כטקסט קצר בשורת המטא, לא כתיבה צבעונית בגובה חצי כרטיס."""
    if status is None:
        return ":gray[טרם נבדק]"
    if status["status"] == federation.APPROVED:
        return f":green[ברפרטואר · {status['confidence']}%]"
    if status["status"] == federation.NOT_FOUND:
        return ":red[לא ברפרטואר]"
    return ":orange[הבדיקה נכשלה]"


def _artwork(track: dict):
    """עטיפת האלבום — סימן הזיהוי המהיר ביותר בכלי מוזיקה.

    הכתובת חוזרת מ-iTunes ומ-Deezer מאז ומעולם (`search.py`) ופשוט לא הוצגה.
    `st.image` מעביר את ה-URL לדפדפן כמו שהוא, ולכן הטעינה היא של המשתמש ולא
    של השרת — מה שחשוב כאן, כי השרת חסום מול חלק מהחנויות.
    """
    art = track.get("artwork")
    if art:
        st.image(art, width=ARTWORK_SIZE)
    else:
        # ריבוע ולא כלום: בלעדיו כל השורות מתחתיו מתיישרות אחרת
        st.html(
            f"<div class='ts-art-blank' style='width:{ARTWORK_SIZE}px;"
            f"height:{ARTWORK_SIZE}px;'></div>")


def render_track(track: dict, index: int, learned: dict | None = None):
    uid = track["uid"]
    status = status_of(track)
    features = st.session_state.get("bigness", {}).get(uid)
    evidence = st.session_state.get("evidence", {}).get(uid) or []
    indicators = search_module.trailer_indicators(track)

    # כרטיס אחד לכל תוצאה, ולא שורה של שמונה עמודות. Streamlit לא מכווץ
    # עמודות בטלפון אלא **עורם** אותן לרוחב מלא, כך שכל תוצאה הפכה לשמונה
    # בלוקים נפרדים — עשרים תוצאות היו 160 בלוקים, ומכאן "לא עובד בפלאפון".
    card = st.container(border=True)
    with card:
        # מכולה אופקית ולא עמודות: Streamlit עורם עמודות לרוחב מלא במסך צר,
        # ואז העטיפה, הטקסט והציון היו הופכים לשלוש שורות נפרדות בטלפון.
        # flex שומר אותם זה לצד זה בשני הרוחבים, בדיוק כמו בעיצוב.
        head = st.container(horizontal=True, wrap=False, vertical_alignment="top", gap="medium")
        with head:
            col_art = st.container(width=ARTWORK_SIZE)
            col_main = st.container(width="stretch")
            col_score = st.container(width="content")

    with col_art:
        _artwork(track)

    with col_main:
        # האמן ראשון ובולט: בחיפוש קאברים לשיר אחד, מה שמבדיל בין התוצאות
        # הוא מי ביצע — לא שם השיר, שחוזר על עצמו בכל השורות.
        # שם השיר הוא קישור ל-YouTube Music: התצוגה המקדימה היא 30 שניות,
        # וזה המסלול לשמוע את הגרסה המלאה. Streamlit מוסיף target="_blank"
        # ו-rel="noopener" לקישורי markdown, ולכן האפליקציה לא ננטשת.
        st.markdown(
            f"**{track['artist']}** &nbsp;"
            f"[{_link_label(track['track'])}]"
            f"({youtube_music_url(track['artist'], track['track'])})")

        meta = [part for part in (
            track.get("genre"),
            str(track.get("year") or "") or None,
            f"{int(track.get('duration_sec', 0) // 60)}:{int(track.get('duration_sec', 0) % 60):02d}"
            if track.get("duration_sec") else None,
        ) if part]
        st.caption(" · ".join(meta + [_status_line(status)]))

        if indicators:
            # הסיבה לדירוג, גלויה: `trailer_strength` נספר בדיוק מהרשימה הזו
            st.markdown(" ".join(f":orange-badge[{sign}]" for sign in indicators))

        for item in evidence[:2]:
            st.caption(f":material/movie: [{item['title'][:70]}]({item['url']}) — {item['channel']}")
        if track.get("origin_track"):
            st.caption(f"קאבר ל: {track['origin_track']}")

    with col_score:
        _score_badge(features)
        if learned and learned.get("count"):
            # למה הטראק הזה עלה: אחרת שינוי הסדר נראה שרירותי
            fit = taste_of(track, learned)
            if fit >= TASTE_BADGE_THRESHOLD:
                st.caption(f"{round(fit * 100)}% לטעם שלך")

    with card:
        if track.get("preview_url"):
            audio_player(track["preview_url"])

        # `horizontal` נשען על flex ולא על רשת עמודות, ולכן הכפתורים נשארים
        # זה לצד זה גם ברוחב של 390px ונשברים לשורה שנייה בעת הצורך
        with st.container(horizontal=True, wrap=True, vertical_alignment="center"):
            selected = st.checkbox("בחר", key=f"chk_{uid}", label_visibility="collapsed",
                                   help="סמן לבדיקה קבוצתית")

            favorited, rejected = is_favorite(track), is_rejected(track)
            if st.button("", key=f"btn_favorite_{uid}",
                         icon=":material/favorite:" if favorited else ":material/favorite_border:",
                         type="primary" if favorited else "secondary",
                         help="הסר מהפלייליסט" if favorited else
                              "שמור לפלייליסט — והדירוג ילמד מזה מה אתה אוהב"):
                toggle_favorite(track)
                st.rerun()
            # דוגמה שלילית שווה יותר מדוגמה חיובית נוספת: היא נותנת ללמידה כיוון,
            # בעוד שעוד לייק רק מהדק מרכז כובד שכבר ידוע
            if st.button("", key=f"btn_reject_{uid}", icon=":material/thumb_down:",
                         type="primary" if rejected else "secondary",
                         help="בטל את הסימון" if rejected else
                              "לא זה — הדירוג ילמד להתרחק מסגנון כזה"):
                toggle_rejection(track)
                st.rerun()

            if not st.session_state.get("federation_blocked"):
                if st.button("בדוק", key=f"btn_check_{uid}", icon=":material/search:"):
                    with st.spinner("בודק..."):
                        verify_tracks([track])
                    st.rerun()

            # תפריט אחד לכל מה שנדיר: קודם כל פעולה תפסה כפתור משלה בכל שורה,
            # ושש שורות טקסט אפור נאבקו על אותה תשומת לב
            with st.popover("", icon=":material/more_horiz:", width=54):
                st.caption(f"עוד כמו **{track['track']}**")
                if st.button("עוד קאברים לשיר הזה", key=f"more_covers_{uid}",
                             icon=":material/library_music:", use_container_width=True):
                    st.session_state["similar_of"] = ("covers", track)
                    st.rerun()
                if st.button("עוד באותו סגנון", key=f"more_style_{uid}",
                             icon=":material/palette:", use_container_width=True,
                             help="לפי הז'אנר והאמן של הטראק הזה. המדידה בדפדפן ממיינת "
                                  "את מה שחוזר לפי גודל."):
                    st.session_state["similar_of"] = ("style", track)
                    st.rerun()

                st.divider()
                details = [f"מקור: {track['source']}", f"ציון רלוונטיות: {track.get('score', 0)}"]
                if track.get("catalog_source"):
                    details.append(f"התגלה דרך: {track['catalog_source']}")
                if track.get("album"):
                    details.append(f"אלבום: {track['album']}")
                st.caption(" · ".join(details))
                if audio.measured(features):
                    st.caption(audio.describe(features))
                if status and status.get("matched_row"):
                    st.caption("השורה מהפדרציה:")
                    st.code(status["matched_row"])

                if st.session_state.get("federation_blocked"):
                    st.divider()
                    url = federation.build_search_url(track["artist"], track["track"])
                    st.markdown(f"[פתח חיפוש בפדרציה]({url})")
                    st.caption("אם הטופס לא מולא מראש, העתק:")
                    st.code(f"{clean_artist_name(track['artist'])}\n{track['track']}")
                    pasted = st.text_area("הדבק את ה-HTML של עמוד התוצאות:", height=100,
                                          key=f"paste_{uid}")
                    if st.button("קבע סטטוס", key=f"apply_{uid}") and pasted.strip():
                        record_status(track, federation.verify_from_html(
                            pasted, track["artist"], track["track"]))
                        storage.save_debug_html(pasted, "results_page")
                        st.rerun()

                st.divider()
                if st.button("חסום אמן", key=f"btn_block_{uid}",
                             icon=":material/block:", use_container_width=True):
                    st.session_state["blacklist"].add(clean_artist_name(track["artist"]).lower())
                    storage.save_blacklist(st.session_state["blacklist"])
                    st.session_state["candidates"] = apply_blacklist(st.session_state["candidates"])
                    st.toast(f"האמן '{track['artist']}' הועבר לרשימה השחורה", icon="🚫")
                    st.rerun()

    return track if selected else None


def export_button(tracks: list[dict], label_prefix: str):
    rows = [(t, status_of(t)) for t in tracks
            if (status_of(t) or {}).get("status") == federation.APPROVED]
    if not rows:
        return
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["אמן", "שיר", "אלבום", "אורך (דק')", "מייצג", "ביטחון", "מקור", "preview"])
    for track, status in rows:
        writer.writerow([
            track["artist"], track["track"], track.get("album", ""),
            round(track.get("duration_sec", 0) / 60, 1),
            status["publisher"], status["confidence"], track["source"],
            track.get("preview_url", ""),
        ])
    st.download_button(
        f"ייצוא {len(rows)} שירים שברפרטואר ל-CSV", icon=":material/download:",
        data=buffer.getvalue().encode("utf-8-sig"),
        file_name=f"{label_prefix}.csv",
        mime="text/csv",
    )


def metrics_export(tracks: list[dict]):
    """ייצוא המדדים הגולמיים של המוצגים, לכיול המשקלים על נתונים אמיתיים.

    המשקלים ב-`audio.WEIGHTS` הם הערכה. כדי לכייל אותם צריך תיוג אנושי — אילו
    מהטראקים האלה באמת "ענקיים" — מול המספרים שנמדדו. העמודה `label` נשארת ריקה
    בכוונה: היא מיועדת למילוי ידני.
    """
    measurements = st.session_state.get("bigness", {})
    rows = [(track, measurements.get(track["uid"])) for track in tracks]
    rows = [(track, features) for track, features in rows if audio.measured(features)]
    if not rows:
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["artist", "track", "bigness", "loudness", "low_end",
                     "onset_rate", "dynamic_span", "label"])
    for track, features in rows:
        writer.writerow([
            track["artist"], track["track"], audio.bigness(features),
            features.get("loudness", ""), features.get("low_end", ""),
            features.get("onset_rate", ""), features.get("dynamic_span", ""), "",
        ])
    st.download_button(
        f"ייצא מדדים של {len(rows)} טראקים (לכיול)", icon=":material/download:",
        data=buffer.getvalue().encode("utf-8-sig"),
        file_name="bigness_metrics.csv",
        mime="text/csv",
        help="מלא את עמודת label ב'ענק' או 'רגוע' כדי שהמשקלים יכוילו על תיוג "
             "אמיתי ולא על הערכה.",
    )


# ---------- מסך חיפוש מאוחד ----------

_audio_behaviour()
_keep_scroll_position()

# סרגל עליון ולא כותרת ראשית: כותרת של 2.5rem ופסקת הסבר דחפו את התוצאות
# — מה שהמשתמש בא בשבילו — הרחק מתחת לקפל. ההסבר עבר ל-help של שדה החיפוש.
with st.container(key="appbar", horizontal=True, vertical_alignment="center"):
    st.html("<div class='ts-mark'></div>")
    st.markdown("#### סורק קאברים לטריילרים")
    st.container(width="stretch")
    st.markdown(f":gray[{len(st.session_state['favorites'])} שמורות]")

_pending = st.session_state.pop("pending_fields", None)
if _pending:
    _title, _artist, _mode, _auto_run = _pending
    st.session_state["cover_title"], st.session_state["cover_artist"] = _title, _artist
    if _mode:
        st.session_state["search_mode"] = _mode
    if _auto_run:
        st.session_state["auto_run"] = True

# שדה חיפוש אחד ולא שלוש עמודות עם תווית מעל כל אחת: המסגרת היא של
# המכולה (`.st-key-searchbar` ב-CSS), והשדות שקופים בתוכה — כך זה נקרא
# כרכיב אחד במקום שלושה טפסים נפרדים
# `wrap=True`: בדסקטופ הכל נכנס לשורה אחת ממילא, ובטלפון שדה האמן יורד
# לשורה שנייה במקום להידחס עד שהטקסט נחתך
searchbar = st.container(key="searchbar", horizontal=True, wrap=True,
                         vertical_alignment="center")
with searchbar:
    cover_title = st.text_input(
        "שם השיר", key="cover_title", placeholder="שם השיר",
        label_visibility="collapsed",
        help="שם שיר או אמן, ומצב חיפוש אחד: קאברים לשיר (מהמאגר וגם "
             "מהחנויות), קאברים לכל הקטלוג של אמן, או חיפוש חופשי עם פילטרים.")
    cover_artist = st.text_input(
        "אמן מקורי", key="cover_artist", placeholder="אמן מקורי (לא חובה)",
        label_visibility="collapsed",
        help="מכריע בשמות עמומים: 'Sweet Dreams' הוא גם סטנדרט קאנטרי מ-1955 "
             "וגם Eurythmics 1983.")

RECENT_ROLLS = 5


def roll_famous_song():
    """מגריל שיר מוכר ומריץ עליו חיפוש, כמו לחיצה על שיר במצעדים.

    הבריכה היא `classics.famous_pool()` — ראשי כל עשור מנתוני המצעד ועוד
    רשימות הפופ והרוק. פופולריות במצעד היא הקירוב ל"סביר שיש לו קאבר";
    בדיקה אמיתית הייתה קריאת רשת לכל מועמד, והיא הופכת לחיצה מיידית
    להמתנה.
    """
    pool = classics_module.famous_pool()
    recent = st.session_state["recent_rolls"]
    # בלי זה שתי הגרלות רצופות מחזירות לפעמים את אותו שיר, וזה נראה תקול
    fresh = [entry for entry in pool
             if (entry["artist"], entry["track"]) not in recent] or list(pool)
    choice = random.choice(fresh)

    st.session_state["recent_rolls"] = (
        recent + [(choice["artist"], choice["track"])])[-RECENT_ROLLS:]
    st.toast(f"🎲 {choice['track']} — {choice['artist']}")
    queue_fields(choice["track"], choice["artist"], mode=MODE_SONG, auto_run=True)


# עם תווית ולא אמוג'י בלבד: בטלפון העמודות נערמות, וכפתור ברוחב מלא
# שכתוב עליו רק "🎲" אינו מסביר את עצמו
with searchbar:
    if st.button("", key="btn_dice", icon=":material/casino:",
                 help="מגריל שיר מוכר מהמצעדים ומחפש לו גרסאות טריילר. "
                      "ככל שהשיר מוכר יותר, כך גדל הסיכוי שמישהו כבר עשה לו קאבר."):
        roll_famous_song()


def suggestion_row(query: str):
    """השלמת שם השיר ותיקון שגיאת כתיב, מול שמות אמיתיים מהקטלוג.

    שם חלקי או משובש מחזיר מעט מאוד תוצאות, והמשתמש לא יודע אם השיר לא קיים או
    שהוא פשוט טעה. ההצעות כאן הן שירים שקיימים במאגר שבו נחפש בפועל, ולכן לחיצה
    עליהן מבטיחה שאילתה שתחזיר משהו.
    """
    query = (query or "").strip()
    if len(query) < suggest_module.MIN_QUERY_LEN:
        return
    # ההצעות נשמרות לפי הטקסט: בלי זה כל rerun (סימון checkbox, מדידה) פונה שוב
    # ל-iTunes על אותו שם בדיוק
    if st.session_state["suggest_query"] != query:
        st.session_state["suggest_query"] = query
        with st.spinner("מחפש שמות דומים..."):
            st.session_state["suggestions"] = suggest_module.suggest(query)

    items = st.session_state["suggestions"]
    if not items:
        return

    correction = suggest_module.did_you_mean(query, items)
    if correction:
        st.warning(f"נראה שהתכוונת ל: **{correction['label']}**")
    else:
        st.caption("השלמות מהקטלוג:")

    columns = st.columns(4)
    for index, item in enumerate(items[:4]):
        if columns[index].button(f"🎵 {item['label'][:38]}", key=f"sug_{index}",
                                 help=item["label"], use_container_width=True):
            st.session_state["suggest_query"] = ""
            queue_fields(item["track"], item["artist"])


suggestion_row(cover_title)

ARTIST_PREVIEW_COUNT = 20


def _artist_preview_titles(artist: str) -> list[str]:
    """עד 20 השירים המזוהים ביותר עם האמן, זול (קריאת iTunes אחת) ומקוצ'ר.

    לחיצה על אמן באינדקס המצעדים לא צריכה להריץ מיד חיפוש קאברים יקר
    (עד 8 חיפושים מקבילים) לפני שהמשתמש בכלל ראה אילו שירים נבחרו לו.
    הקאש לפי שם מנורמל מונע קריאת iTunes חוזרת בכל rerun (checkbox, מדידת
    אודיו וכו׳).
    """
    key = search_module.normalize_artist(artist)
    if st.session_state["artist_preview_query"] != key:
        st.session_state["artist_preview_query"] = key
        search_module.reset_errors()
        with st.spinner(f"מזהה שירים של {artist}..."):
            st.session_state["artist_preview_titles"] = covers_module.artist_top_titles(
                artist, limit=ARTIST_PREVIEW_COUNT)
    return st.session_state["artist_preview_titles"]


def _entry_grid(entries: list[dict], key_prefix: str):
    """רשת כפתורים משותפת לאמנים ולשירים, מכל אחד משלושת מקורות האינדקס.

    לחיצה על אמן ממלאת את שדה האמן וקובעת מצב "קאברים לאמן" — תצוגה מקדימה
    זולה של שירי האמן מוצגת לפני שחיפוש הקאברים היקר רץ (ראו
    `_artist_preview_titles`). לחיצה על שיר ממלאת שיר+אמן, קובעת מצב
    "קאברים לשיר" ומריצה אוטומטית. שלושת המקורות (קלאסיקות סטטיות, רשימת
    בילבורד, מצעד מיובא) שונים בנתונים אבל זהים בהתנהגות — לכן רכיב רינדור
    אחד במקום שלושה כמעט-זהים.
    """
    is_song = any(entry["kind"] == "song" for entry in entries)
    per_row = 2 if is_song else 4
    for row_start in range(0, len(entries), per_row):
        columns = st.columns(per_row)
        for offset, (column, entry) in enumerate(
                zip(columns, entries[row_start:row_start + per_row])):
            rank = entry.get("rank")
            # המפתח נגזר מהמיקום ברשימה ולא מהשם: שני שירים שונים בשם
            # "Rockstar" באותה שורה מייצרים מפתח כפול ומפילים את העמוד.
            key = f"{key_prefix}_{row_start + offset}"
            if entry["kind"] == "artist":
                name = entry["artist"]
                label = f"{rank}. {name}" if rank else name
                clicked = column.button(label, key=key, use_container_width=True)
            else:
                full_label = (f"{rank}. " if rank else "") + f"{entry['track']} — {entry['artist']}"
                clicked = column.button(full_label[:60], key=key, help=full_label,
                                        use_container_width=True)
            if clicked:
                # האינדקס ארוך (עד 120 שירים), והצעד הבא של המשתמש — תוצאות
                # או תצוגת השירים המקדימה — מרונדר מחוץ לו. הוא נסגר מעצמו
                st.session_state["index_generation"] += 1
                if entry["kind"] == "artist":
                    # לא auto_run: קודם מוצגת תצוגה מקדימה זולה של שירי האמן
                    # (ראו את המקטע אחרי רדיו "סוג חיפוש") — חיפוש הקאברים
                    # המלא יקר ולא צריך לרוץ לפני שהמשתמש בחר מה לחפש בפועל
                    queue_fields(artist=entry["artist"], mode=MODE_ARTIST)
                else:
                    queue_fields(entry["track"], entry["artist"], mode=MODE_SONG, auto_run=True)


def _classics_entries(category: str) -> list[dict]:
    """קלאסיקות לפי ז'אנר או עשור, 1950–2020 — רשימה סטטית, לא מצעד חי.

    מצעד Deezer חי הציג טרנדים עדכניים שהמשתמש לרוב לא מזהה. הרשימות כאן
    קבועות בקוד: הז'אנרים אצורים ב-`classics.py`, והעשורים מגיעים מנתוני
    Billboard Hot 100 ההיסטוריים דרך `chart_data` (ראו `tools/build_charts.py`).
    """
    source = classics_module.CATEGORIES.get(category, ())
    return [{"kind": "song", "artist": entry["artist"], "track": entry["track"],
            "rank": index + 1} for index, entry in enumerate(source)]


def _goat_entries(filter_text: str) -> list[dict]:
    ranks = {name: index + 1 for index, name in enumerate(artists_module.GREATEST_ARTISTS)}
    return [{"kind": "artist", "artist": name, "rank": ranks.get(name)}
            for name in artists_module.search_artists(filter_text)]


def _imported_entries(chart: dict) -> list[dict]:
    if chart["kind"] == billboard_module.ARTISTS:
        return [{"kind": "artist", "artist": e["artist"], "rank": e.get("rank")}
                for e in chart["entries"]]
    return [{"kind": "song", "artist": e["artist"], "track": e["track"], "rank": e.get("rank")}
            for e in chart["entries"]]


# המפתח נגזר ממונה, ולא סתם קבוע. ל-`st.expander` אין מצב פתוח/סגור
# ב-`session_state` — גם אחרי שהמשתמש פותח אותו ידנית הערך נשאר None,
# וכתיבה אליו אינה משפיעה. Streamlit מחיל את `expanded` רק כשהערך
# **משתנה**, ולכן העברת False כשהוא כבר False לא סוגרת כלום. נמדד
# בדפדפן: אחרי פתיחה ידנית הרכיב נשאר פתוח. מפתח חדש מרנדר רכיב חדש,
# והוא נולד מכווץ — זה מה שעובד בפועל.
# שניהם בשורה אחת: שני פסים ברוחב מלא זה מתחת לזה נראו כמו שני כרטיסים
# ריקים בין שורת החיפוש לתוצאות
panel_index, panel_filters = st.columns(2)

with panel_index, st.expander("אינדקס מצעדים", icon=":material/leaderboard:",
                              expanded=False,
                              key=f"chart_index_{st.session_state['index_generation']}"):
    st.caption("נקודת פתיחה לחיפוש: לחיצה על אמן מריצה 'קאברים לאמן', "
               "ולחיצה על שיר מריצה 'קאברים לשיר' — לשתיהן אותה תוצאה כמו מילוי "
               "השדות למעלה ולחיצה על חפש. המיקום במצעד אינו משפיע על דירוג "
               "התוצאות — שם קובע מה שנמדד מהאודיו.")

    imported = storage.load_charts()
    sources = ["🎻 קלאסיקות", f"בילבורד: האמנים הגדולים ({len(artists_module.GREATEST_ARTISTS)})"]
    sources += [f"מיובא: {chart['title']}" for chart in imported.values()]
    source = st.radio("מקור:", sources, horizontal=True, key="index_source")

    entries, key_prefix = [], ""
    if source.startswith("🎻 קלאסיקות"):
        # selectbox ולא radio: שלוש-עשרה קטגוריות בשורה אחת אינן קריאות
        category = st.selectbox("קטגוריה:", list(classics_module.CATEGORIES),
                                key="classics_category")
        entries = _classics_entries(category)
        key_prefix = "classic"
        st.caption(f"{len(entries)} שירים · העשורים מדורגים לפי ביצועים בפועל "
                   "במצעד Billboard Hot 100 ההיסטורי, והז'אנרים לפי רשימות אצורות. "
                   "בכל קטגוריה לכל היותר שני שירים לאמן, כדי שאותו אמן לא יחזור.")

    elif source.startswith("בילבורד"):
        artist_filter = st.text_input("סנן ברשימה:", key="artist_filter", placeholder="beatles")
        entries = _goat_entries(artist_filter)
        key_prefix = "goat"
        if not entries:
            st.caption("אין אמן בשם הזה ברשימה. אפשר להקליד ידנית בשדה האמן.")

    else:
        chart = next((c for c in imported.values() if source.endswith(c["title"])), None)
        if not chart:
            st.caption("המצעד לא נמצא. ייבא אותו מחדש מסרגל הצד.")
        else:
            entries = _imported_entries(chart)
            key_prefix = f"imp_{chart['slug']}"

    if entries:
        _entry_grid(entries, key_prefix)

with panel_filters, st.expander("פילטרים", icon=":material/tune:", expanded=False):
    col1, col2, col3 = st.columns(3)
    style_filter = col1.selectbox("סגנון / ז'אנר:", [ALL, *STYLES])
    tempo_filter = col2.selectbox("קצב / טמפו:", [ALL, "Fast Action", "Slow Build-up"])
    length_filter = col3.selectbox("אורך השיר:", [ALL, LENGTH_SHORT, LENGTH_MEDIUM, LENGTH_LONG])

    col4, col5, col6 = st.columns(3)
    recency = col4.selectbox("חדשות:", list(RECENCY_OPTIONS))
    prefer_new = col5.checkbox(
        "תעדף חדש עם ציון גבוה", value=True,
        help="בונוס טריות שיורד מ-25 לאפס על פני חמש שנים.")
    fresh_only = col6.checkbox(
        "רק מה שלא ראיתי", value=False,
        help="מדלג על תוצאות שכבר הוצגו בסבב הזה, כדי להביא חומר חדש.")

    if st.session_state.get("search_mode") == MODE_SONG:
        st.caption("סגנון וקצב משפיעים רק על החלק שמגיע מחיפוש בחנויות. המאגר "
                   "הרשמי (SecondHandSongs/MusicBrainz) לא תומך בסינון כזה — "
                   "הגרסאות משם יופיעו תמיד.")

filters = {"style": style_filter, "tempo": tempo_filter, "length": length_filter}

def _lookup_failed() -> str:
    """הודעה כשהחיפוש נכשל, במקום להציג 'לא נמצאו תוצאות'.

    חנות שהחזירה 429/503 נראתה בדיוק כמו חיפוש שלא מצא כלום, ולכן הלחיצה
    השנייה "עבדה". עכשיו יש ניסיונות חוזרים, ומה שנכשל בכל זאת נאמר במפורש.
    """
    errors = search_module.last_errors()
    if not errors:
        return ""
    unique = list(dict.fromkeys(errors))
    return "החיפוש לא הושלם: " + " · ".join(unique[:3])


# צ'יפים ולא רדיו: שורת בחירה קומפקטית במקום שלושה עיגולים עם תוויות
# הצ'יפים והכפתור המשני שלהם באותה שורה: כפתור בודד שצף מתחתיהם נראה
# כמו שריד ולא כמו חלק מהבקרה
mode_row = st.container(key="moderow", horizontal=True, wrap=True,
                        vertical_alignment="center")
with mode_row:
    search_mode = st.pills(
        "סוג חיפוש", SEARCH_MODES, key="search_mode", label_visibility="collapsed",
        help=f"{MODE_SONG}: ממזג את מאגר הגרסאות הרשמי "
             "(SecondHandSongs/MusicBrainz) עם חיפוש בחנויות אחרי טראקים "
             f"'Epic/Trailer/Cinematic'. {MODE_ARTIST}: מזהה את השירים "
             "המזוהים ביותר עם האמן ומביא קאברים לכל "
             f"אחד. {MODE_FREE}: חיפוש רחב עם הפילטרים למעלה, בלי להיצמד "
             "ליצירה מסוימת.")

chosen_work = ""
if search_mode == MODE_SONG:
    with mode_row:
        _which = st.button("אילו שירים בשם הזה?", icon=":material/search:")
    if _which:
        if not cover_title.strip():
            st.warning("הכנס שם שיר")
        else:
            search_module.reset_errors()
            with st.spinner("מחפש יצירות..."):
                st.session_state["work_candidates"] = covers_module.musicbrainz_work_candidates(
                    cover_title, cover_artist)
            if not st.session_state["work_candidates"]:
                failure = _lookup_failed()
                if failure:
                    st.error(failure + " — נסה שוב")
                else:
                    st.info("לא נמצאו יצירות בשם הזה. אפשר לחפש ישירות בכפתור חפש.")

    work_candidates = st.session_state.get("work_candidates") or []
    if work_candidates:
        # "Sweet Dreams" הוא גם סטנדרט קאנטרי מ-1955 וגם Eurythmics 1983.
        # בלי בחירה מפורשת נלקחה הראשונה והוחזרו עשרים גרסאות קאנטרי.
        hint = covers_module.famous_recording(cover_title)
        if hint:
            # הבורר מציג מלחינים, ומשתמש שמחפש "Umbrella" מזהה את השיר לפי המבצע.
            # בלי השורה הזאת נראה שהיצירה הנכונה חסרה, בעוד שהיא ראשונה ברשימה.
            st.caption(f"🎧 השיר המוכר בשם הזה: **{hint['artist']}** — {hint['track']}"
                       + (f" ({hint['year']})" if hint.get("year") else ""))
        labels = {
            f"{c['title']}" + (f" — {c['disambiguation']}" if c["disambiguation"] else "")
            + (f" · מלחינים: {c['writers']}" if c["writers"] else ""): c["id"]
            for c in work_candidates
        }
        picked = st.radio("איזו יצירה התכוונת?", list(labels), index=0)
        chosen_work = labels[picked]

elif search_mode == MODE_ARTIST and cover_artist.strip():
    titles = _artist_preview_titles(cover_artist)
    if titles:
        st.caption(f"🎵 {len(titles)} השירים המזוהים ביותר עם {cover_artist} — "
                   "לחיצה מריצה חיפוש קאברים לשיר הזה בלבד. 'חפש' למטה "
                   "סורק את כל השירים המובילים בבת אחת.")
        _entry_grid([{"kind": "song", "artist": cover_artist, "track": title,
                      "rank": index + 1} for index, title in enumerate(titles)],
                    "artist_preview")
    else:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.caption("לא נמצאו שירים מזוהים עם האמן הזה. אפשר עדיין ללחוץ "
                       "'🔎 חפש' לחיפוש קאברים ישיר.")

with searchbar:
    _clicked_search = st.button("חפש", type="primary", icon=":material/search:")
run_search = _clicked_search or st.session_state.pop("auto_run", False)


def _run_similar():
    """מבצע בקשת "עוד כמו זה" שנרשמה משורה, ומחליף את התוצאות המוצגות."""
    request = st.session_state.get("similar_of")
    if not request:
        return
    st.session_state["similar_of"] = None
    kind, track = request
    search_module.reset_errors()

    with st.spinner("מחפש עוד כמו זה..."):
        if kind == "covers":
            results, source = covers_module.more_covers_of(track)
            # אותו ניקוי שהחיפוש עצמו עשה, אחרת התווית אומרת "Yellow (Epic)"
            origin = track.get("origin_track") or search_module.clean_track_title(
                track["track"]) or track["track"]
            label = f"עוד קאברים ל: {origin}"
        else:
            results, source = covers_module.more_like_style(track)
            label = f"באותו סגנון כמו: {track['artist']} — {track['track']}"
        results = apply_blacklist(results)

    st.session_state["candidates"] = results
    st.session_state["covers_source"] = f"{source} · {label}" if source else label
    st.session_state["original"] = None
    st.session_state["visible_count"] = PAGE_SIZE
    st.session_state["result_generation"] += 1
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info("לא נמצא חומר דומה.")


def _store_results(results, source, original=None):
    st.session_state["candidates"] = results
    st.session_state["covers_source"] = source
    st.session_state["original"] = original
    st.session_state["visible_count"] = PAGE_SIZE
    st.session_state["result_generation"] += 1
    st.session_state["last_query"] = cover_title or cover_artist


_run_similar()

if run_search:
    search_module.reset_errors()

if run_search and search_mode == MODE_ARTIST and not cover_artist.strip():
    st.warning("החיפוש הזה הוא לפי אמן — מלא את שדה האמן")

elif run_search and search_mode != MODE_ARTIST and not (
        cover_title.strip() or cover_artist.strip()):
    st.warning("הכנס שם שיר או אמן")

elif run_search and search_mode == MODE_ARTIST:
    with st.spinner("מזהה את השירים של האמן ומחפש להם קאברים..."):
        results, source_used, titles = covers_module.find_artist_covers(
            cover_artist, filters=filters, prefer_new=prefer_new,
            min_year=RECENCY_OPTIONS[recency])
        results = apply_blacklist(results)
    _store_results(results, source_used)
    for track in results:
        st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info("לא נמצאו קאברים לאמן הזה. בדוק את איות השם, או נסה שיר ספציפי.")
    else:
        st.caption("🎤 נסרקו השירים: " + " · ".join(titles))

elif run_search and search_mode == MODE_SONG:
    with st.spinner("מחפש במאגר הגרסאות הרשמי ובחנויות..."):
        results, source_used, original = covers_module.find_all_covers(
            cover_title, cover_artist, filters=filters, prefer_new=prefer_new,
            min_year=RECENCY_OPTIONS[recency], work_id=chosen_work)
        results = apply_blacklist(results)
    _store_results(results, source_used, original)
    for track in results:
        st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))
    declared = sum(1 for t in results if t.get("trailer_indicator"))
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info("לא נמצאו קאברים לשיר הזה. נסה 'חיפוש חופשי'.")
    else:
        st.caption(
            f"📣 {declared} גרסאות עם סימן טריילר. השאר נשארות ברשימה — רמיקס "
            "יכול להיות ענק בלי לכתוב זאת. כל המוצגים נמדדים אוטומטית בדפדפן, "
            "ומי שנמדד כגדול מסומן 🔊."
        )

elif run_search:  # MODE_FREE
    with st.spinner("סורק את iTunes ו-Deezer..."):
        exclude = st.session_state["seen_keys"] if fresh_only else frozenset()
        results = apply_blacklist(search_covers(
            cover_title or cover_artist, filters=filters, exclude_keys=exclude,
            origin_artist=cover_artist, prefer_new=prefer_new,
            min_year=RECENCY_OPTIONS[recency]))
    _store_results(results, "חיפוש בחנויות")
    for track in results:
        st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))
    if not results:
        failure = _lookup_failed()
        if failure:
            st.error(failure)
        else:
            st.info("לא נמצאו תוצאות. נסה לבטל את 'רק מה שלא ראיתי' או להרחיב פילטרים.")

original = st.session_state.get("original")
if original:
    st.caption(f"גרסת ייחוס להשוואה: **{original['artist']}** — {original['track']}"
               + (f" ({original['year']})" if original.get("year") else ""))

if st.session_state["covers_source"]:
    st.caption(f"מקור הנתונים: {st.session_state['covers_source']}")


# ---------- תוצאות ----------

candidates = st.session_state["candidates"]

if candidates:
    # סמן הדור עבור שומר הגלילה: כל עוד הוא לא השתנה, מקום הגלילה שווה
    # שחזור. חיפוש חדש מחליף אותו, והשומר מוותר על המקום הישן.
    st.markdown(
        f"<span data-result-generation='{st.session_state['result_generation']}' hidden></span>",
        unsafe_allow_html=True)
    st.divider()
    # שתי עמודות ולא שלוש: בטלפון Streamlit עורם עמודות לרוחב מלא, ו"סה"כ
    # במאגר" כ-st.metric תפס מסך שלם בשביל מספר אחד. הוא ירד לשורת caption
    # מתחת לכותרת, שם הוא ממילא נקרא יחד עם "מוצגים X מתוך Y".
    col_a, col_b = st.columns([1, 1])
    # תוצאת הרפרטואר היא תג מידע. הסינון לפיה כבוי כברירת מחדל בכוונה: הקאברים
    # האפיים מגיעים לרוב מספריות הפקה שאינן ברפרטואר ההשמעה הישראלי.
    only_approved = col_a.checkbox("הצג רק מה שברפרטואר", value=False)
    sort_by = col_b.selectbox("מיון:", [SORT_BEST, "גודל (נמדד)", "ציון",
                                       "חדשים קודם", "אורך (עולה)", "אורך (יורד)",
                                       "אמן"])

    display = list(candidates)
    if only_approved:
        display = [t for t in display if (status_of(t) or {}).get("status") == federation.APPROVED]

    # הפרופיל נבנה מול פול התוצאות המוצג — כך "אהבתי Soundtrack" נמדד מול
    # כמה Soundtrack יש כאן ממילא, ולא כספירה גולמית
    learned = taste_profile(display)

    display = ordered_display(display, sort_by, only_approved, learned)
    resort_button(display, sort_by, learned)

    st.subheader(f"מוצגים {min(st.session_state['visible_count'], len(display))} מתוך {len(display)}")
    st.caption(f"סה\"כ במאגר: {len(candidates)}")

    action_all, action_selected = st.columns([1, 1])
    visible = display[: st.session_state["visible_count"]]

    probe_federation()

    if st.session_state.get("federation_blocked"):
        action_all.caption("🌉 האתר חסום מהשרת — כל שיר נבדק ידנית בכפתור 🔗 שלו")
    elif action_all.button("🔍 בדוק את כל התוצאות המוצגות בפדרציה"):
        verify_tracks(visible)
        st.rerun()

    measure_visible(visible)
    measure_via_server(visible)

    if youtube_module.available() and st.button("חפש אישור שימוש בטריילר (למוצגים)", icon=":material/movie:"):
        progress = st.progress(0.0, text="מחפש...")
        for index, track in enumerate(visible):
            progress.progress(index / max(len(visible), 1),
                              text=f"{index + 1}/{len(visible)}: {track['artist']}")
            st.session_state["evidence"][track["uid"]] = (
                youtube_module.search_trailer_evidence(track["artist"], track["track"]))
        progress.empty()
        st.rerun()

    metrics_export(visible)

    selected = [t for t in (render_track(track, i, learned)
                           for i, track in enumerate(visible)) if t]

    if selected and action_selected.button(f"🔍 בדוק את {len(selected)} המסומנים", type="secondary"):
        verify_tracks(selected)
        st.rerun()

    if st.session_state["visible_count"] < len(display):
        if st.button("טען עוד 20 תוצאות", icon=":material/expand_more:"):
            st.session_state["visible_count"] += PAGE_SIZE
            st.rerun()

    export_button(candidates, f"covers_{st.session_state['last_query'] or 'search'}")
