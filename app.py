"""ממשק Streamlit לסורק קאברים מאושרים מול הפדרציה הישראלית."""
import csv
import io
import time

import streamlit as st

import federation
import storage
from search import ALL, LENGTH_LONG, LENGTH_MEDIUM, LENGTH_SHORT, clean_artist_name, search_covers, track_key

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


# ---------- אתחול מצב ----------

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
        **payload,
        "cached_at": time.time(),
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
    """בודק אצווה: קודם מהקאש, והשאר בדפדפן אחד משותף."""
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

    st.caption(f"תיקיית נתונים: `{storage.DATA_DIR or 'לא זמינה'}`")
    if st.button("🧹 נקה קאש בדיקות"):
        st.session_state["cache"] = {}
        storage.save_cache({})
        st.toast("הקאש נוקה", icon="🧹")

    for warning in storage.warnings:
        st.warning(warning)


# ---------- חיפוש ----------

st.title("🎵 סורק קאברים מהיר (IFPI Israel)")
st.write(
    "חיפוש רחב על פני iTunes ו-Deezer עם כמה וריאציות שאילתה, ניפוי כפילויות "
    "ודירוג לפי רלוונטיות לקאברים אפיים. הקשב, בדוק מול הפדרציה, וחסום אמנים לא רלוונטיים."
)

with st.expander("🎛️ פילטרים לחיפוש (סגנון, קצב, אורך)", expanded=False):
    col1, col2, col3 = st.columns(3)
    style_filter = col1.selectbox(
        "סגנון / ז'אנר:", [ALL, "Epic Orchestral", "Rock Hybrid", "Dark Electronic", "Dramatic Piano"]
    )
    tempo_filter = col2.selectbox("קצב / טמפו:", [ALL, "Fast Action", "Slow Build-up"])
    length_filter = col3.selectbox("אורך השיר:", [ALL, LENGTH_SHORT, LENGTH_MEDIUM, LENGTH_LONG])

filters = {"style": style_filter, "tempo": tempo_filter, "length": length_filter}

query = st.text_input("מילת חיפוש / אמן / שיר מקור:", placeholder="למשל: victory, 2WEI, Hans Zimmer")

col_search, col_fresh = st.columns([1, 1])
do_search = col_search.button("🔎 חפש שירים", type="primary")
fresh_only = col_fresh.checkbox(
    "הצג רק תוצאות שלא ראיתי", value=True, help="חיפוש חוזר יביא חומר חדש במקום אותה רשימה"
)

if do_search:
    if not query.strip():
        st.warning("הכנס מילת חיפוש")
    else:
        with st.spinner("סורק את iTunes ו-Deezer..."):
            exclude = st.session_state["seen_keys"] if fresh_only else frozenset()
            results = search_covers(query, filters=filters, exclude_keys=exclude)
            results = apply_blacklist(results)

        st.session_state["candidates"] = results
        st.session_state["visible_count"] = PAGE_SIZE
        st.session_state["last_query"] = query
        for track in results:
            st.session_state["seen_keys"].add(track_key(track["artist"], track["track"]))

        if not results:
            st.info("לא נמצאו תוצאות חדשות. נסה לבטל את הסימון 'הצג רק תוצאות שלא ראיתי'.")


# ---------- תוצאות ----------

candidates = st.session_state["candidates"]

if candidates:
    col_a, col_b, col_c = st.columns([2, 2, 2])
    only_approved = col_a.checkbox("הצג רק מיוצגים", value=False)
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

    action_check_all, action_check_selected = st.columns([1, 1])
    if action_check_all.button("🔍 בדוק את כל התוצאות המוצגות בפדרציה"):
        verify_tracks(display[: st.session_state["visible_count"]])
        st.rerun()

    selected = []
    for track in display[: st.session_state["visible_count"]]:
        uid = track["uid"]
        status = status_of(track)
        duration_min = round(track.get("duration_sec", 0) / 60, 1)

        col_check, col_title, col_audio, col_status, col_btn_check, col_btn_block = st.columns(
            [0.5, 3, 3, 2.2, 1.5, 1.2]
        )

        if col_check.checkbox("בחר", key=f"chk_{uid}", label_visibility="collapsed"):
            selected.append(track)

        with col_title:
            st.markdown(f"**{track['artist']}** - {track['track']}")
            st.caption(
                f"אורך: {duration_min} דק' · מקור: {track['source']} · ציון: {track.get('score', 0)}"
                + (f" · אלבום: {track['album']}" if track.get("album") else "")
            )

        with col_audio:
            if track.get("preview_url"):
                st.audio(track["preview_url"])
            else:
                st.caption("אין תצוגה מקדימה")

        with col_status:
            if status is None:
                st.info("⚪ טרם נבדק")
            elif status["status"] == federation.APPROVED:
                st.success(f"🟢 מיוצג ({status['publisher']}) · ביטחון {status['confidence']}%")
                if status.get("matched_row"):
                    with st.popover("הצג שורה מהפדרציה"):
                        st.code(status["matched_row"])
            elif status["status"] == federation.NOT_FOUND:
                st.error("🔴 לא נמצא בפדרציה")
            else:
                st.warning(f"🟠 לא ידוע — הסריקה נכשלה\n\n{status.get('error', '')[:120]}")

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

    if selected and action_check_selected.button(
        f"🔍 בדוק את {len(selected)} המסומנים", type="secondary"
    ):
        verify_tracks(selected)
        st.rerun()

    if st.session_state["visible_count"] < len(display):
        if st.button("⬇️ טען עוד 20 תוצאות"):
            st.session_state["visible_count"] += PAGE_SIZE
            st.rerun()

    approved_rows = [
        (t, status_of(t))
        for t in candidates
        if (status_of(t) or {}).get("status") == federation.APPROVED
    ]
    if approved_rows:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["אמן", "שיר", "אלבום", "אורך (דק')", "מייצג", "ביטחון", "מקור", "preview"])
        for track, status in approved_rows:
            writer.writerow([
                track["artist"], track["track"], track.get("album", ""),
                round(track.get("duration_sec", 0) / 60, 1),
                status["publisher"], status["confidence"], track["source"],
                track.get("preview_url", ""),
            ])
        st.download_button(
            f"⬇️ ייצוא {len(approved_rows)} שירים מיוצגים ל-CSV",
            data=buffer.getvalue().encode("utf-8-sig"),
            file_name=f"approved_covers_{st.session_state['last_query'] or 'search'}.csv",
            mime="text/csv",
        )
