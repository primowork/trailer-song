"""ממשק Streamlit: גילוי קאברים אפיים לטריילרים, עם בדיקת רפרטואר הפדרציה."""
import csv
import datetime as _dt
import io
import time

import streamlit as st
import streamlit.components.v1 as components

import audio
import covers as covers_module
import youtube as youtube_module
import federation
import storage
import search as search_module
from search import (ALL, LENGTH_LONG, LENGTH_MEDIUM, LENGTH_SHORT, STYLES,
                    clean_artist_name, search_covers, track_key)

PAGE_SIZE = 20

# פילטר "חדשות": התווית וסף השנה שהיא מייצגת. 0 = בלי סינון.
RECENCY_OPTIONS = {
    "הכל": 0,
    "השנה האחרונה": _dt.date.today().year,
    "השנתיים האחרונות": _dt.date.today().year - 1,
    "5 השנים האחרונות": _dt.date.today().year - 4,
}

st.set_page_config(page_title="סורק קאברים - IFPI Israel", page_icon="🎵", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] { direction: rtl; }
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stColumn"] { text-align: right; }
    [data-testid="stSidebar"] { direction: rtl; text-align: right; }
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
        "candidates": [],
        "seen_keys": set(),
        "visible_count": PAGE_SIZE,
        "last_query": "",
        "debug_mode": False,
        "covers_source": "",
        "work_candidates": [],
        "impact": {},
        "evidence": {},
        "original": None,
        "federation_blocked": False,
        "all_inputs": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()


def is_blacklisted(artist: str) -> bool:
    return clean_artist_name(artist).lower() in st.session_state["blacklist"]


def apply_blacklist(tracks: list[dict]) -> list[dict]:
    return [t for t in tracks if not is_blacklisted(t.get("artist", ""))]


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


# ---------- סרגל צד ----------

with st.sidebar:
    st.markdown("### 🚫 אמנים ברשימה השחורה")
    blacklist = sorted(st.session_state["blacklist"])
    st.write(f"סה\"כ נחסמו: **{len(blacklist)}**")

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
    if not audio.librosa_available():
        st.caption("ניתוח אודיו כבוי (librosa לא מותקנת)")

    if st.button("🧹 נקה קאש בדיקות"):
        st.session_state["cache"] = {}
        storage.save_cache({})
        st.toast("הקאש נוקה", icon="🧹")

    for warning in storage.warnings:
        st.warning(warning)


# ---------- הצגת שיר בודד ----------

def render_track(track: dict, index: int):
    uid = track["uid"]
    status = status_of(track)
    duration_min = round(track.get("duration_sec", 0) / 60, 1)

    cols = st.columns([0.5, 3, 3, 2.2, 1.5, 1.2])
    col_check, col_title, col_audio, col_status, col_btn_check, col_btn_block = cols

    selected = col_check.checkbox("בחר", key=f"chk_{uid}", label_visibility="collapsed")

    with col_title:
        metrics = st.session_state.get("impact", {}).get(uid)
        evidence = st.session_state.get("evidence", {}).get(uid) or []
        badge = " 🎬" if evidence else ""
        if audio.is_big_version(metrics):
            badge += " 🔊"          # נמדדה כגרסה גדולה, לא משנה מה הכותרת אומרת
        indicators = search_module.trailer_indicators(track)
        if indicators and not audio.is_big_version(metrics):
            badge += " 📣"
        st.markdown(f"**{track['artist']}**{badge} - {track['track']}")
        if indicators:
            # להראות איזה סימן תפס, לא רק שתפס משהו
            st.caption("סימן: " + " · ".join(indicators))
        if metrics and metrics.get("analyzed"):
            st.caption(
                f"💥 impact {metrics['impact']}/100 · "
                f"איטי פי {metrics['tempo_ratio']} · "
                f"שיא {metrics['peak_delta']:+.2f} · "
                f"קשת פי {metrics['buildup_ratio']}"
            )
        elif metrics:
            st.caption(f"לא נותח: {metrics.get('reason', '')}")
        for item in evidence[:2]:
            st.caption(f"🎬 [{item['title'][:70]}]({item['url']}) — {item['channel']}")
        parts = [f"אורך: {duration_min} דק'", f"מקור: {track['source']}", f"ציון: {track.get('score', 0)}"]
        if track.get("year"):
            parts.append(f"שנה: {track['year']}")
        if track.get("album"):
            parts.append(f"אלבום: {track['album']}")
        st.caption(" · ".join(parts))

        features_key = f"feat_{uid}"
        if st.session_state.get(features_key):
            f = st.session_state[features_key]
            if f.error:
                st.caption(f"ניתוח אודיו נכשל: {f.error}")
            else:
                st.caption(f"🥁 {f.bpm} BPM · אנרגיה {f.energy} · build-up ×{f.buildup}")
        elif track.get("preview_url") and audio.librosa_available():
            if st.button("📊 נתח אודיו", key=f"btn_audio_{uid}"):
                with st.spinner("מנתח..."):
                    st.session_state[features_key] = audio.features_for(track)
                st.rerun()

    with col_audio:
        if track.get("preview_url"):
            st.audio(track["preview_url"])
        else:
            st.caption("אין תצוגה מקדימה")

    with col_status:
        if status is None:
            st.info("⚪ טרם נבדק")
        elif status["status"] == federation.APPROVED:
            st.success(f"🟢 ברפרטואר ({status['publisher']}) · ביטחון {status['confidence']}%")
            if status.get("matched_row"):
                with st.popover("הצג שורה מהפדרציה"):
                    st.code(status["matched_row"])
        elif status["status"] == federation.NOT_FOUND:
            st.error("🔴 לא נמצא ברפרטואר")
        else:
            st.warning(f"🟠 לא ידוע — הבדיקה נכשלה\n\n{status.get('error', '')[:150]}")

    if st.session_state.get("federation_blocked"):
        with col_btn_check.popover("🔗 בדוק ידנית"):
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
    elif col_btn_check.button("🔍 בדוק", key=f"btn_check_{uid}"):
        with st.spinner("בודק..."):
            verify_tracks([track])
        st.rerun()

    if col_btn_block.button("🚫 חסום אמן", key=f"btn_block_{uid}"):
        st.session_state["blacklist"].add(clean_artist_name(track["artist"]).lower())
        storage.save_blacklist(st.session_state["blacklist"])
        st.session_state["candidates"] = apply_blacklist(st.session_state["candidates"])
        st.toast(f"האמן '{track['artist']}' הועבר לרשימה השחורה", icon="🚫")
        st.rerun()

    st.divider()
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


# ---------- מסך חיפוש מאוחד ----------

_only_one_audio_at_a_time()

st.title("🎵 סורק קאברים לטריילרים")
st.write(
    "שיר אחד, שלוש דרכים לחפש אותו: כל גרסאות הכיסוי מהמאגר, רק הגרסאות "
    "האפיות מהחנויות, או חיפוש חופשי רחב."
)

col_title, col_artist = st.columns(2)
cover_title = col_title.text_input("שם השיר:", placeholder="למשל: Bitter Sweet Symphony")
cover_artist = col_artist.text_input(
    "אמן מקורי (לא חובה):", placeholder="The Verve",
    help="מכריע בשמות עמומים: 'Sweet Dreams' הוא גם סטנדרט קאנטרי מ-1955 "
         "וגם Eurythmics 1983. גם משמש כבסיס להשוואת עוצמה.")

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
        help="בחיפוש החופשי: מדלג על תוצאות שכבר הוצגו, כדי להביא חומר חדש.")
    st.caption("הקצב נמדד מה-preview בכפתור 'נתח אודיו', לא מנוחש מהכותרת.")

filters = {"style": style_filter, "tempo": tempo_filter, "length": length_filter}

if st.button("🔎 אילו שירים בשם הזה?"):
    if not cover_title.strip():
        st.warning("הכנס שם שיר")
    else:
        with st.spinner("מחפש יצירות..."):
            st.session_state["work_candidates"] = covers_module.musicbrainz_work_candidates(
                cover_title, cover_artist)
        if not st.session_state["work_candidates"]:
            st.info("לא נמצאו יצירות בשם הזה. אפשר לחפש ישירות בכפתורים למטה.")

chosen_work = ""
work_candidates = st.session_state.get("work_candidates") or []
if work_candidates:
    # "Sweet Dreams" הוא גם סטנדרט קאנטרי מ-1955 וגם Eurythmics 1983.
    # בלי בחירה מפורשת נלקחה הראשונה והוחזרו עשרים גרסאות קאנטרי.
    labels = {
        f"{c['title']}" + (f" — {c['disambiguation']}" if c["disambiguation"] else "")
        + (f" ({c['writers']})" if c["writers"] else ""): c["id"]
        for c in work_candidates
    }
    picked = st.radio("איזו יצירה התכוונת?", list(labels), index=0)
    chosen_work = labels[picked]

col_all, col_epic, col_free = st.columns(3)
search_all = col_all.button("🎬 כל הגרסאות", type="primary",
                            help="כל גרסאות הכיסוי של היצירה מהמאגר היחסי.")
search_epic = col_epic.button(
    "🎥 גרסאות טריילר אפיות",
    help="חיפוש בחנויות אחרי טראקים שמציגים את עצמם כ-Epic / Trailer / Cinematic, "
         "או שיושבים על אלבום של סדרה או סרט. זה חיפוש ולא סיווג.")
search_free = col_free.button(
    "🔎 חיפוש חופשי",
    help="חיפוש רחב בחנויות עם הפילטרים למעלה, בלי להיצמד ליצירה מסוימת.")


def _store_results(results, source, original=None):
    st.session_state["candidates"] = results
    st.session_state["covers_source"] = source
    st.session_state["original"] = original
    st.session_state["visible_count"] = PAGE_SIZE
    st.session_state["last_query"] = cover_title or cover_artist


if (search_all or search_epic or search_free) and not (
        cover_title.strip() or cover_artist.strip()):
    st.warning("הכנס שם שיר או אמן")

elif search_epic:
    with st.spinner("מחפש גרסאות אפיות..."):
        results, source_used = covers_module.find_epic_versions(cover_title, cover_artist)
        results = apply_blacklist(results)
    _store_results(results, source_used)
    declared = sum(1 for t in results if t.get("trailer_indicator"))
    if not results:
        st.info("לא נמצאו גרסאות לשיר הזה. נסה 'כל הגרסאות'.")
    else:
        st.caption(
            f"📣 {declared} גרסאות עם סימן טריילר מופיעות ראשונות. השאר נשארות "
            "ברשימה — רמיקס יכול להיות ענק בלי לכתוב זאת. לחץ '💥 מדוד עוצמה "
            "מול המקור' וכל מי שיימדד כגדול יסומן 🔊."
        )

elif search_all:
    with st.spinner("שולף גרסאות מהמאגר..."):
        results, source_used, original = covers_module.find_covers(
            cover_title, cover_artist, work_id=chosen_work)
        results = apply_blacklist(results)
    _store_results(results, source_used, original)
    if not results:
        st.info("לא נמצאו גרסאות. ייתכן שהיצירה לא במאגר. נסה 'חיפוש חופשי'.")

elif search_free:
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
        st.info("לא נמצאו תוצאות. נסה לבטל את 'רק מה שלא ראיתי' או להרחיב פילטרים.")

original = st.session_state.get("original")
if original:
    st.caption(f"גרסת ייחוס להשוואה: **{original['artist']}** — {original['track']}"
               + (f" ({original['year']})" if original.get("year") else ""))
    if not original.get("preview_url"):
        st.warning("לגרסת הייחוס אין preview — אי אפשר למדוד עוצמה מולה. "
                   "מלא 'אמן מקורי' כדי לבחור בסיס השוואה אחר.")

if st.session_state["covers_source"]:
    st.caption(f"מקור הנתונים: {st.session_state['covers_source']}")


# ---------- תוצאות ----------

candidates = st.session_state["candidates"]

if candidates:
    st.divider()
    col_a, col_b, col_c = st.columns([2, 2, 2])
    # תוצאת הרפרטואר היא תג מידע. הסינון לפיה כבוי כברירת מחדל בכוונה: הקאברים
    # האפיים מגיעים לרוב מספריות הפקה שאינן ברפרטואר ההשמעה הישראלי.
    only_approved = col_a.checkbox("הצג רק מה שברפרטואר", value=False)
    sort_by = col_b.selectbox("מיון:", ["ציון", "impact (עוצמה מול המקור)", "חדשים קודם",
                                       "אורך (עולה)", "אורך (יורד)", "אמן"])

    display = list(candidates)
    if only_approved:
        display = [t for t in display if (status_of(t) or {}).get("status") == federation.APPROVED]
    if sort_by == "ציון":
        display.sort(key=lambda t: t.get("score", 0), reverse=True)
    elif sort_by == "חדשים קודם":
        display.sort(key=lambda t: search_module.release_year(t), reverse=True)
    elif sort_by == "impact (עוצמה מול המקור)":
        display.sort(key=lambda t: st.session_state.get("impact", {})
                     .get(t["uid"], {}).get("impact", -1), reverse=True)
    elif sort_by == "אורך (עולה)":
        display.sort(key=lambda t: t.get("duration_sec", 0))
    elif sort_by == "אורך (יורד)":
        display.sort(key=lambda t: t.get("duration_sec", 0), reverse=True)
    elif sort_by == "אמן":
        display.sort(key=lambda t: t.get("artist", "").lower())

    col_c.metric("סה\"כ במאגר", len(candidates))

    st.subheader(f"מוצגים {min(st.session_state['visible_count'], len(display))} מתוך {len(display)}")

    action_all, action_selected = st.columns([1, 1])
    visible = display[: st.session_state["visible_count"]]

    if st.session_state.get("federation_blocked"):
        action_all.caption("🌉 האתר חסום מהשרת — כל שיר נבדק ידנית בכפתור 🔗 שלו")
    elif action_all.button("🔍 בדוק את כל התוצאות המוצגות בפדרציה"):
        verify_tracks(visible)
        st.rerun()

    if st.session_state.get("original") and st.button(
            "💥 מדוד עוצמה מול המקור (לכל המוצגים)"):
        original_track = st.session_state["original"]
        progress = st.progress(0.0, text="מנתח...")
        for index, track in enumerate(visible):
            progress.progress(index / max(len(visible), 1),
                              text=f"מנתח {index + 1}/{len(visible)}: {track['artist']}")
            st.session_state["impact"][track["uid"]] = audio.impact_for(
                track, original_track).to_dict()
            if youtube_module.available():
                st.session_state["evidence"][track["uid"]] = (
                    youtube_module.search_trailer_evidence(track["artist"], track["track"]))
        progress.empty()
        st.rerun()

    if not audio.librosa_available():
        st.caption("⚠️ ניתוח העוצמה כבוי — librosa לא מותקנת")
    if not youtube_module.available():
        st.caption("⚠️ אין אישור שימוש בטריילר — הגדר YOUTUBE_API_KEY")

    selected = [t for t in (render_track(track, i) for i, track in enumerate(visible)) if t]

    if selected and action_selected.button(f"🔍 בדוק את {len(selected)} המסומנים", type="secondary"):
        verify_tracks(selected)
        st.rerun()

    if st.session_state["visible_count"] < len(display):
        if st.button("⬇️ טען עוד 20 תוצאות"):
            st.session_state["visible_count"] += PAGE_SIZE
            st.rerun()

    export_button(candidates, f"covers_{st.session_state['last_query'] or 'search'}")
