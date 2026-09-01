"""ממשק Streamlit: גילוי קאברים אפיים לטריילרים, עם בדיקת רפרטואר הפדרציה."""
import csv
import io
import time

import streamlit as st

import audio
import covers as covers_module
import federation
import storage
from search import (ALL, LENGTH_LONG, LENGTH_MEDIUM, LENGTH_SHORT,
                    clean_artist_name, search_covers, track_key)

PAGE_SIZE = 20

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
        signals = track.get("trailer_signals") or []
        badge = " 🎬" if signals else ""
        st.markdown(f"**{track['artist']}**{badge} - {track['track']}")
        if signals:
            st.caption("סימני טריילר: " + " · ".join(signals))
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

    if col_btn_check.button("🔍 בדוק", key=f"btn_check_{uid}"):
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


# ---------- מסכים ----------

st.title("🎵 סורק קאברים לטריילרים")

tab_covers, tab_search = st.tabs(["🎬 מצא קאברים לשיר", "🔎 חיפוש חופשי"])

with tab_covers:
    st.write(
        "מזין שיר מקורי ומקבל את כל גרסאות הכיסוי המוכרות שלו ממאגר קאברים יחסי "
        "(SecondHandSongs, ובנפילה לאחור MusicBrainz), ולא מניחוש טקסטואלי בכותרות."
    )

    col_title, col_artist = st.columns(2)
    cover_title = col_title.text_input("שם השיר המקורי:", placeholder="למשל: Zombie")
    cover_artist = col_artist.text_input(
        "אמן מקורי (לא חובה):", placeholder="Eurythmics",
        help="ממלא תפקיד מכריע בשמות עמומים: 'Sweet Dreams' הוא גם סטנדרט קאנטרי מ-1955.")
    epic_only = st.checkbox(
        "העדף גרסאות עם סימן טריילר", value=False,
        help="מקדם למעלה גרסאות עם סימן טריילר (בית הפקה, אמן קאברים מוכר, "
             "שיבוץ בפסקול, ז'אנר). לא מסתיר גרסאות אחרות.",
    )

    if st.button("🔎 אילו שירים בשם הזה?"):
        if not cover_title.strip():
            st.warning("הכנס שם שיר")
        else:
            with st.spinner("מחפש יצירות..."):
                st.session_state["work_candidates"] = covers_module.musicbrainz_work_candidates(
                    cover_title, cover_artist)
            if not st.session_state["work_candidates"]:
                st.info("לא נמצאו יצירות בשם הזה. אפשר לחפש ישירות בכפתור למטה.")

    chosen_work = ""
    candidates = st.session_state.get("work_candidates") or []
    if candidates:
        # "Sweet Dreams" הוא גם סטנדרט קאנטרי מ-1955 וגם Eurythmics 1983.
        # בלי בחירה מפורשת המערכת לקחה את הראשון והחזירה עשרים גרסאות קאנטרי.
        labels = {
            f"{c['title']}" + (f" — {c['disambiguation']}" if c["disambiguation"] else "")
            + (f" ({c['writers']})" if c["writers"] else ""): c["id"]
            for c in candidates
        }
        picked = st.radio("איזו יצירה התכוונת?", list(labels), index=0)
        chosen_work = labels[picked]

    if st.button("🎬 מצא קאברים", type="primary"):
        if not cover_title.strip():
            st.warning("הכנס שם שיר")
        else:
            with st.spinner("שולף גרסאות מהמאגר..."):
                results, source_used = covers_module.find_covers(
                    cover_title, cover_artist, epic_only=False, work_id=chosen_work)
                results = apply_blacklist(results)
            if epic_only:
                # העדפה ולא סינון: גרסה בלי סימן עדיין מוצגת, רק נמוך יותר
                results.sort(key=lambda t: (bool(t.get("trailer_signals")), t.get("score", 0)),
                             reverse=True)
            st.session_state["candidates"] = results
            st.session_state["covers_source"] = source_used
            st.session_state["visible_count"] = PAGE_SIZE
            st.session_state["last_query"] = cover_title
            if not results:
                st.info(
                    "לא נמצאו גרסאות. ייתכן שהיצירה לא במאגר, או ששני המקורות "
                    "לא היו זמינים. נסה את לשונית החיפוש החופשי."
                )

    if st.session_state["covers_source"]:
        st.caption(f"מקור הנתונים: {st.session_state['covers_source']}")

with tab_search:
    st.write("חיפוש רחב על פני iTunes ו-Deezer עם וריאציות שאילתה, ניפוי כפילויות ודירוג.")

    with st.expander("🎛️ פילטרים", expanded=False):
        col1, col2, col3 = st.columns(3)
        style_filter = col1.selectbox(
            "סגנון / ז'אנר:", [ALL, "Epic Orchestral", "Rock Hybrid", "Dark Electronic", "Dramatic Piano"])
        tempo_filter = col2.selectbox("קצב / טמפו:", [ALL, "Fast Action", "Slow Build-up"])
        length_filter = col3.selectbox("אורך השיר:", [ALL, LENGTH_SHORT, LENGTH_MEDIUM, LENGTH_LONG])
        st.caption("הקצב נמדד מה-preview בכפתור 'נתח אודיו' שליד כל שיר, לא מנוחש מהכותרת.")

    filters = {"style": style_filter, "tempo": tempo_filter, "length": length_filter}
    query = st.text_input("מילת חיפוש / אמן / שיר מקור:", placeholder="למשל: victory, 2WEI")

    col_search, col_fresh = st.columns([1, 1])
    do_search = col_search.button("🔎 חפש שירים", type="primary")
    fresh_only = col_fresh.checkbox("הצג רק תוצאות שלא ראיתי", value=True)

    if do_search:
        if not query.strip():
            st.warning("הכנס מילת חיפוש")
        else:
            with st.spinner("סורק את iTunes ו-Deezer..."):
                exclude = st.session_state["seen_keys"] if fresh_only else frozenset()
                results = apply_blacklist(search_covers(query, filters=filters, exclude_keys=exclude))
            st.session_state["candidates"] = results
            st.session_state["covers_source"] = ""
            st.session_state["visible_count"] = PAGE_SIZE
            st.session_state["last_query"] = query
            for track in results:
                st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))
            if not results:
                st.info("לא נמצאו תוצאות חדשות. נסה לבטל את הסימון 'הצג רק תוצאות שלא ראיתי'.")


# ---------- תוצאות ----------

candidates = st.session_state["candidates"]

if candidates:
    st.divider()
    col_a, col_b, col_c = st.columns([2, 2, 2])
    # תוצאת הרפרטואר היא תג מידע. הסינון לפיה כבוי כברירת מחדל בכוונה: הקאברים
    # האפיים מגיעים לרוב מספריות הפקה שאינן ברפרטואר ההשמעה הישראלי.
    only_approved = col_a.checkbox("הצג רק מה שברפרטואר", value=False)
    sort_by = col_b.selectbox("מיון:", ["רלוונטיות", "אורך (עולה)", "אורך (יורד)", "אמן"])

    display = list(candidates)
    if only_approved:
        display = [t for t in display if (status_of(t) or {}).get("status") == federation.APPROVED]
    if sort_by == "אורך (עולה)":
        display.sort(key=lambda t: t.get("duration_sec", 0))
    elif sort_by == "אורך (יורד)":
        display.sort(key=lambda t: t.get("duration_sec", 0), reverse=True)
    elif sort_by == "אמן":
        display.sort(key=lambda t: t.get("artist", "").lower())

    col_c.metric("סה\"כ במאגר", len(candidates))
    st.subheader(f"מוצגים {min(st.session_state['visible_count'], len(display))} מתוך {len(display)}")

    action_all, action_selected = st.columns([1, 1])
    visible = display[: st.session_state["visible_count"]]

    if action_all.button("🔍 בדוק את כל התוצאות המוצגות בפדרציה"):
        verify_tracks(visible)
        st.rerun()

    selected = [t for t in (render_track(track, i) for i, track in enumerate(visible)) if t]

    if selected and action_selected.button(f"🔍 בדוק את {len(selected)} המסומנים", type="secondary"):
        verify_tracks(selected)
        st.rerun()

    if st.session_state["visible_count"] < len(display):
        if st.button("⬇️ טען עוד 20 תוצאות"):
            st.session_state["visible_count"] += PAGE_SIZE
            st.rerun()

    export_button(candidates, f"covers_{st.session_state['last_query'] or 'search'}")
