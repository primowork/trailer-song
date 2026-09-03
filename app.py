"""ממשק Streamlit: גילוי קאברים אפיים לטריילרים, עם בדיקת רפרטואר הפדרציה."""
import csv
import os
import datetime as _dt
import io
import time

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

# שלושת מצבי החיפוש. "קאברים לשיר" ממזג שני מקורות (מאגר יחסי + חיפוש בחנויות)
# תחת בחירה אחת — הם עונים בפועל על אותה שאלה. "קאברים לאמן" ו"חיפוש חופשי"
# הם כוונות שונות באמת (קלט שונה; חיפוש רחב מכוון-פילטרים) ונשארים מצבים נפרדים.
# מתחת לזה התג "מתאים לטעם שלך" הוא רעש: עם מעט לייקים כל הטראקים מקבלים
# ציון נמוך דומה, ותג על כולם אינו אומר דבר
TASTE_BADGE_THRESHOLD = 0.35

MODE_SONG = "🎬 קאברים לשיר"
MODE_ARTIST = "🎤 קאברים לאמן"
MODE_FREE = "🔎 חיפוש חופשי + פילטרים"
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



def _only_one_audio_at_a_time():
    """עוצר כל נגן אחר ברגע שמתחילים לנגן אחד.

    Streamlit מרנדר <audio> נייטיבי לכל שיר, וכולם יכולים לנגן במקביל — מה
    שהופך את ההאזנה לחסרת תועלת. הסקריפט רץ בתוך iframe ולכן ניגש למסמך
    האב, ומאזין ב-capture כדי לתפוס גם נגנים שנוספו אחרי הרינדור.
    """
    renderer = getattr(st, "iframe", None) or components.html
    renderer(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (doc.__singleAudioBound) return;
            doc.__singleAudioBound = true;
            doc.addEventListener("play", function (event) {
                const started = event.target;
                if (!(started instanceof window.parent.HTMLMediaElement)) return;
                doc.querySelectorAll("audio, video").forEach(function (other) {
                    if (other !== started && !other.paused) {
                        other.pause();
                    }
                });
            }, true);
        })();
        </script>
        """,
        # st.iframe דורש גובה חיובי, בניגוד ל-components.html שקיבל 0
        height=1,
    )


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


def _snapshot(track: dict) -> dict:
    features = st.session_state["bigness"].get(track["uid"])
    return {
        **{field: track.get(field) for field in FAVORITE_FIELDS},
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


# ---------- סרגל צד ----------

with st.sidebar:
    st.markdown("### ❤️ הפלייליסט שלי")
    favorites = st.session_state["favorites"]
    st.write(f"גרסאות שמורות: **{len(favorites)}**")

    if favorites:
        learned_sidebar = taste_profile()
        summary = taste.describe(learned_sidebar)
        if summary:
            st.caption(summary)

        for key, entry in sorted(favorites.items(),
                                 key=lambda item: item[1].get("added_at", 0),
                                 reverse=True):
            col_name, col_remove = st.columns([4, 1])
            label = f"{entry.get('artist', '')} — {entry.get('track', '')}"
            # לחיצה על גרסה שמורה מחזירה אליה: ממלאת את השדות ומריצה חיפוש
            # לשיר הזה, כדי שאפשר יהיה למצוא אותה ואת מה שדומה לה שוב
            if col_name.button(label[:48], key=f"fav_open_{key}", help=label,
                               use_container_width=True):
                queue_fields(entry.get("track", ""), entry.get("artist", ""),
                             mode=MODE_SONG, auto_run=True)
            if col_remove.button("✕", key=f"unfav_{key}", help="הסר מהפלייליסט"):
                favorites.pop(key)
                storage.save_favorites(favorites)
                st.rerun()
            if entry.get("preview_url"):
                st.audio(entry["preview_url"])

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["אמן", "שיר", "אלבום", "ז'אנר", "שנה", "preview"])
        for entry in favorites.values():
            writer.writerow([entry.get("artist", ""), entry.get("track", ""),
                             entry.get("album", ""), entry.get("genre", ""),
                             entry.get("year", ""), entry.get("preview_url", "")])
        st.download_button("⬇️ ייצא פלייליסט", data=buffer.getvalue().encode("utf-8-sig"),
                           file_name="playlist.csv", mime="text/csv")
    else:
        st.caption("סמן ❤️ ליד גרסה שאהבת. היא תישמר כאן, והדירוג ילמד "
                   "מה מאפיין את מה שאתה אוהב ויעלה גרסאות כאלה לראש.")

    st.divider()
    st.markdown("### ⚙️ הגדרות")
    st.session_state["debug_mode"] = st.checkbox(
        "מצב דיבאג (שמירת HTML מהפדרציה)", value=st.session_state["debug_mode"]
    )
    if st.session_state.get("debug_path"):
        st.caption(f"נשמר: `{st.session_state['debug_path']}`")

    st.caption(f"רפרטואר: `{federation.FEDERATION_URL}`")

    with st.expander("🌉 בדיקה ידנית דרך הדפדפן שלך"):
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

    if st.button("🩺 בדוק חיבור לפדרציה"):
        with st.spinner("בודק..."):
            report = federation.diagnose()
        html = report.pop("html", "")
        st.json(report)
        if html:
            path = storage.save_debug_html(html, "diagnose")
            if path:
                st.caption(f"HTML נשמר: `{path}`")
                st.download_button("⬇️ הורד את ה-HTML", data=html.encode("utf-8"),
                                   file_name="ifpi_search.html", mime="text/html")
        else:
            st.error("השרת לא הצליח להגיע לאתר הפדרציה. "
                     "אם זה עובד מהדפדפן שלך אבל לא מכאן, החסימה היא ברשת של השרת.")
    st.caption(f"תיקיית נתונים: `{storage.DATA_DIR or 'לא זמינה'}`")
    if not youtube_module.available():
        # מידע על פיצ'ר כבוי, לא שלב במסלול — ולכן כאן ולא בין התוצאות
        st.caption("אימות שימוש בטריילר כבוי (הגדר YOUTUBE_API_KEY)")
    with st.expander("📥 ייבוא מצעד בילבורד"):
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
            if st.button("🗑️ נקה דחיות"):
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

        if blacklist and st.button("🗑️ נקה רשימה שחורה"):
            st.session_state["blacklist"] = set()
            storage.save_blacklist(st.session_state["blacklist"])
            st.rerun()

    if st.button("🧹 נקה קאש בדיקות"):
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

def sorted_by(tracks: list, sort_by: str, learned: dict) -> list:
    """הסדר המבוקש, מחושב על הנתונים שיש **ברגע זה**."""
    ranked = list(tracks)
    measurements = st.session_state.get("bigness", {})

    def measured_size(track):
        features = measurements.get(track["uid"])
        # מי שטרם נמדד יורד לתחתית ולא מתחזה ל"קטן"
        return audio.bigness(features) if audio.measured(features) else -1

    if sort_by == "❤️ הטעם שלי":
        # ברירת המחדל, וזה מה שמעלה את הסגנון שהמשתמש אוהב לראש. בלי לייקים
        # `taste_of` מחזיר 0 לכולם, והמיון מתקפל למיון לפי גודל נמדד
        ranked.sort(key=lambda t: (round(taste_of(t, learned), 3), measured_size(t),
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
    if not moving:
        return
    if st.button(f"🔄 סדר מחדש לפי {sort_by} ({moving} שירים יזוזו)",
                 help="הסדר קפוא בזמן עיון כדי שהרשימה לא תזוז תוך כדי האזנה. "
                      "כאן מיישמים את מה שנלמד מאז — מדידות אודיו חדשות ולייקים."):
        st.session_state["display_order"] = fresh
        st.rerun()


# ---------- הצגת שיר בודד ----------

def render_track(track: dict, index: int, learned: dict | None = None):
    uid = track["uid"]
    status = status_of(track)
    duration_min = round(track.get("duration_sec", 0) / 60, 1)

    # כרטיס אחד לכל תוצאה, ולא שורה של שמונה עמודות. Streamlit לא מכווץ
    # עמודות בטלפון אלא **עורם** אותן לרוחב מלא, כך שכל תוצאה הפכה לשמונה
    # בלוקים נפרדים — עשרים תוצאות היו 160 בלוקים, ומכאן "לא עובד בפלאפון".
    # כאן התוכן זורם לרוחב הכרטיס, והפעולות יושבות בשורה אופקית אחת
    # (`horizontal=True`) שנשברת לשורה נוספת במקום להיערם.
    card = st.container(border=True)
    with card:
        col_title, col_side = st.columns([3, 2], vertical_alignment="top")

    with col_title:
        features = st.session_state.get("bigness", {}).get(uid)
        evidence = st.session_state.get("evidence", {}).get(uid) or []
        badge = " 🎬" if evidence else ""
        if audio.is_big_version(features):
            badge += " 🔊"          # נמדדה כגרסה גדולה, לא משנה מה הכותרת אומרת
        indicators = search_module.trailer_indicators(track)
        if indicators and not audio.is_big_version(features):
            badge += " 📣"
        st.markdown(f"**{track['artist']}**{badge} - {track['track']}")
        if indicators:
            # להראות איזה סימן תפס, לא רק שתפס משהו
            st.caption("סימן: " + " · ".join(indicators))
        if audio.measured(features):
            score = audio.bigness(features)
            # שלוש מדרגות ולא שתיים: הסף כויל על מדגם קטן, ו"רגוע" על ציון 45
            # הוא קביעה חזקה מכפי שהנתונים מצדיקים
            if score >= audio.BIG_VERSION_THRESHOLD:
                label = "🔊 גדול"
            elif score >= audio.MID_VERSION_THRESHOLD:
                label = "🎚️ בינוני"
            else:
                label = "🌙 רגוע"
            st.caption(f"{label} {score}/100 · {audio.describe(features)}")
        elif features:
            reason = ("החנות חוסמת מדידה ישירה (CORS) — נמדד דרך השרת"
                      if features.get("error") == "cors_failed"
                      else features.get("error", ""))
            st.caption(f"⚪ טרם נמדד — {reason}")
        elif track.get("preview_url"):
            st.caption("⚪ טרם נמדד")
        if learned and learned.get("count"):
            # למה הטראק הזה עלה: אחרת שינוי הסדר נראה שרירותי
            fit = taste_of(track, learned)
            if fit >= TASTE_BADGE_THRESHOLD:
                st.caption(f"❤️ {round(fit * 100)}% מתאים לטעם שלך")
        for item in evidence[:2]:
            st.caption(f"🎬 [{item['title'][:70]}]({item['url']}) — {item['channel']}")
        if track.get("origin_track"):
            st.caption(f"🎤 קאבר ל: {track['origin_track']}")
        parts = [f"אורך: {duration_min} דק'", f"מקור: {track['source']}", f"ציון: {track.get('score', 0)}"]
        if track.get("catalog_source"):
            # ממצב "קאברים לשיר" הממוזג: מאיזה חצי (מאגר רשמי / חיפוש בחנויות) זה הגיע
            parts.append(f"התגלה דרך: {track['catalog_source']}")
        if track.get("year"):
            parts.append(f"שנה: {track['year']}")
        if track.get("album"):
            parts.append(f"אלבום: {track['album']}")
        st.caption(" · ".join(parts))

    with col_side:
        # תג ולא st.info/success/error: התיבות הצבעוניות תפסו את מרבית גובה
        # הכרטיס ודחקו את מה שבאמת מבדיל בין תוצאות — הכותרת והמדידה
        if status is None:
            st.badge("⚪ טרם נבדק", color="gray")
        elif status["status"] == federation.APPROVED:
            st.badge(f"🟢 ברפרטואר · {status['confidence']}%", color="green")
            st.caption(status["publisher"])
            if status.get("matched_row"):
                with st.popover("שורה מהפדרציה"):
                    st.code(status["matched_row"])
        elif status["status"] == federation.NOT_FOUND:
            st.badge("🔴 לא ברפרטואר", color="red")
        else:
            st.badge("🟠 הבדיקה נכשלה", color="orange")
            st.caption(status.get("error", "")[:150])

        if track.get("preview_url"):
            st.audio(track["preview_url"])
        else:
            st.caption("אין תצוגה מקדימה")

    with card:
        # `horizontal` נשען על flex ולא על רשת עמודות, ולכן הכפתורים נשארים
        # זה לצד זה גם ברוחב של 390px ונשברים לשורה שנייה בעת הצורך
        with st.container(horizontal=True, wrap=True, vertical_alignment="center"):
            selected = st.checkbox("בחר", key=f"chk_{uid}", label_visibility="collapsed",
                                   help="סמן לבדיקה קבוצתית")

            favorited, rejected = is_favorite(track), is_rejected(track)
            if st.button("❤️" if favorited else "🤍", key=f"btn_favorite_{uid}",
                         help="הסר מהפלייליסט" if favorited else
                              "שמור לפלייליסט — והדירוג ילמד מזה מה אתה אוהב"):
                toggle_favorite(track)
                st.rerun()
            # דוגמה שלילית שווה יותר מדוגמה חיובית נוספת: היא נותנת ללמידה כיוון,
            # בעוד שעוד לייק רק מהדק מרכז כובד שכבר ידוע
            if st.button("👎", key=f"btn_reject_{uid}",
                         type="primary" if rejected else "secondary",
                         help="בטל את הסימון" if rejected else
                              "לא זה — הדירוג ילמד להתרחק מסגנון כזה"):
                toggle_rejection(track)
                st.rerun()

            if st.session_state.get("federation_blocked"):
                with st.popover("🔗 בדוק ידנית"):
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
            elif st.button("🔍 בדוק", key=f"btn_check_{uid}"):
                with st.spinner("בודק..."):
                    verify_tracks([track])
                st.rerun()

            # רוחב מפורש: בתוך מכולה אופקית Streamlit מכווץ את ה-popover
            # ומקצץ את התווית ל-"🔁 …"
            with st.popover("🔁 עוד", width=110):
                st.caption(f"עוד כמו **{track['track']}**")
                if st.button("🎼 עוד קאברים לשיר הזה", key=f"more_covers_{uid}",
                             use_container_width=True):
                    st.session_state["similar_of"] = ("covers", track)
                    st.rerun()
                if st.button("🎨 עוד באותו סגנון", key=f"more_style_{uid}",
                             use_container_width=True,
                             help="לפי הז'אנר והאמן של הטראק הזה. המדידה בדפדפן ממיינת "
                                  "את מה שחוזר לפי גודל."):
                    st.session_state["similar_of"] = ("style", track)
                    st.rerun()

            if st.button("🚫 חסום אמן", key=f"btn_block_{uid}"):
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
        f"⬇️ ייצוא {len(rows)} שירים שברפרטואר ל-CSV",
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
        f"⬇️ ייצא מדדים של {len(rows)} טראקים (לכיול)",
        data=buffer.getvalue().encode("utf-8-sig"),
        file_name="bigness_metrics.csv",
        mime="text/csv",
        help="מלא את עמודת label ב'ענק' או 'רגוע' כדי שהמשקלים יכוילו על תיוג "
             "אמיתי ולא על הערכה.",
    )


# ---------- מסך חיפוש מאוחד ----------

_only_one_audio_at_a_time()

st.title("🎵 סורק קאברים לטריילרים")
st.write(
    "שם שיר או אמן, ומצב חיפוש אחד: קאברים לשיר (מהמאגר וגם מהחנויות), "
    "קאברים לכל הקטלוג של אמן, או חיפוש חופשי עם פילטרים."
)

_pending = st.session_state.pop("pending_fields", None)
if _pending:
    _title, _artist, _mode, _auto_run = _pending
    st.session_state["cover_title"], st.session_state["cover_artist"] = _title, _artist
    if _mode:
        st.session_state["search_mode"] = _mode
    if _auto_run:
        st.session_state["auto_run"] = True

col_title, col_artist = st.columns(2)
cover_title = col_title.text_input(
    "שם השיר:", key="cover_title", placeholder="למשל: Bitter Sweet Symphony")
cover_artist = col_artist.text_input(
    "אמן מקורי (לא חובה):", key="cover_artist", placeholder="The Verve",
    help="מכריע בשמות עמומים: 'Sweet Dreams' הוא גם סטנדרט קאנטרי מ-1955 "
         "וגם Eurythmics 1983.")


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

    לחיצה על אמן ב-📇 אינדקס מצעדים לא צריכה להריץ מיד חיפוש קאברים יקר
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


with st.expander("📇 אינדקס מצעדים", expanded=False):
    st.caption("נקודת פתיחה לחיפוש: לחיצה על אמן מריצה 'קאברים לאמן', "
               "ולחיצה על שיר מריצה 'קאברים לשיר' — לשתיהן אותה תוצאה כמו מילוי "
               "השדות למעלה ולחיצה על 🔎 חפש. המיקום במצעד אינו משפיע על דירוג "
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

with st.expander("🎛️ פילטרים", expanded=False):
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


search_mode = st.radio(
    "סוג חיפוש:", SEARCH_MODES, horizontal=True, key="search_mode",
    help=f"{MODE_SONG}: ממזג את מאגר הגרסאות הרשמי (SecondHandSongs/MusicBrainz) "
         "עם חיפוש בחנויות אחרי טראקים 'Epic/Trailer/Cinematic'. "
         f"{MODE_ARTIST}: מזהה את השירים המזוהים ביותר עם האמן ומביא קאברים לכל "
         f"אחד. {MODE_FREE}: חיפוש רחב עם הפילטרים למעלה, בלי להיצמד ליצירה מסוימת.")

chosen_work = ""
if search_mode == MODE_SONG:
    if st.button("🔎 אילו שירים בשם הזה?"):
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
                    st.info("לא נמצאו יצירות בשם הזה. אפשר לחפש ישירות בכפתור 🔎 חפש.")

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
                   "לחיצה מריצה חיפוש קאברים לשיר הזה בלבד. '🔎 חפש' למטה "
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

run_search = st.button("🔎 חפש", type="primary") or st.session_state.pop("auto_run", False)


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
    st.divider()
    # שתי עמודות ולא שלוש: בטלפון Streamlit עורם עמודות לרוחב מלא, ו"סה"כ
    # במאגר" כ-st.metric תפס מסך שלם בשביל מספר אחד. הוא ירד לשורת caption
    # מתחת לכותרת, שם הוא ממילא נקרא יחד עם "מוצגים X מתוך Y".
    col_a, col_b = st.columns([1, 1])
    # תוצאת הרפרטואר היא תג מידע. הסינון לפיה כבוי כברירת מחדל בכוונה: הקאברים
    # האפיים מגיעים לרוב מספריות הפקה שאינן ברפרטואר ההשמעה הישראלי.
    only_approved = col_a.checkbox("הצג רק מה שברפרטואר", value=False)
    sort_by = col_b.selectbox("מיון:", ["❤️ הטעם שלי", "גודל (נמדד)", "ציון",
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

    if youtube_module.available() and st.button("🎬 חפש אישור שימוש בטריילר (למוצגים)"):
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
        if st.button("⬇️ טען עוד 20 תוצאות"):
            st.session_state["visible_count"] += PAGE_SIZE
            st.rerun()

    export_button(candidates, f"covers_{st.session_state['last_query'] or 'search'}")
