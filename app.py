import streamlit as st
from scanner import fetch_web_covers, verify_single_track, clean_artist_name

st.set_page_config(page_title="סורק קאברים - IFPI Israel", page_icon="🎵", layout="wide")

st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div[data-testid="stColumn"] { text-align: right; }
    </style>
""", unsafe_allow_html=True)

# אתחול זיכרון לבדיקות ולרשימה שחורה
if 'statuses' not in st.session_state:
    st.session_state['statuses'] = {} # track_id -> {"approved": bool, "publisher": str}
if 'blacklist' not in st.session_state:
    st.session_state['blacklist'] = set()

# ניהול רשימה שחורה בסיידבר
with st.sidebar:
    st.markdown("### 🚫 אמנים ברשימה השחורה")
    st.write(f"סה\"כ נחסמו: **{len(st.session_state['blacklist'])}**")
    
    if st.session_state['blacklist']:
        st.write(list(st.session_state['blacklist']))
        if st.button("🗑️ נקה רשימה שחורה"):
            st.session_state['blacklist'] = set()
            st.rerun()

st.title("🎵 סורק קאברים מהיר (IFPI Israel)")
st.write("הכנס חיפוש לקבלת תוצאות מיידיות. הקשב לאודיו, סרוק שירים בפדרציה או חסום אמנים שאינם רלוונטיים בלחיצה אחת.")

# פילטרים
with st.expander("🎛️ פילטרים לחיפוש (סגנון, קצב, אורך)", expanded=False):
    col1, col2, col3 = st.columns(3)
    with col1:
        style_filter = st.selectbox("סגנון / ז'אנר:", ["הכל", "Epic Orchestral", "Rock Hybrid", "Dark Electronic", "Dramatic Piano"])
    with col2:
        tempo_filter = st.selectbox("קצב / טמפו:", ["הכל", "Fast Action", "Slow Build-up"])
    with col3:
        length_filter = st.selectbox("אורך השיר:", ["הכל", "קצר (< 3 דק')", "בינוני (3-4 דק')", "ארוך (> 4 דק')"])

filters = {
    "style": style_filter,
    "tempo": tempo_filter,
    "length": length_filter
}

query = st.text_input("מילת חיפוש / אמן / שיר מקור:", placeholder="למשל: victory, 2WEI, Hans Zimmer")

if st.button("🔎 חפש שירים מיידית", type="primary"):
    if query.strip():
        with st.spinner("שולף שירים מאינטרנט..."):
            raw_results = fetch_web_covers(query, limit=40, filters=filters)
            # סינון מיידי של אמנים ברשימה השחורה
            st.session_state['candidates'] = [
                item for item in raw_results
                if clean_artist_name(item.get("artistName", "")).lower() not in st.session_state['blacklist']
            ]

# הצגת השירים מיידית
if 'candidates' in st.session_state and st.session_state['candidates']:
    st.subheader(f"נמצאו {len(st.session_state['candidates'])} קאברים:")
    
    selected_to_batch = []

    for idx, item in enumerate(st.session_state['candidates']):
        track_id = item.get("trackId", idx)
        artist = item.get("artistName", "")
        track = item.get("trackName", "")
        clean_art = clean_artist_name(artist).lower()
        duration_min = round(item.get("trackTimeMillis", 0) / 60000, 1)
        
        status_info = st.session_state['statuses'].get(track_id)

        col_check, col_title, col_audio, col_status, col_btn_check, col_btn_block = st.columns([0.5, 3, 3, 2, 1.5, 1.2])
        
        with col_check:
            is_selected = st.checkbox("", key=f"chk_{track_id}")
            if is_selected:
                selected_to_batch.append(item)

        with col_title:
            st.markdown(f"**{artist}** - {track}")
            st.caption(f"אורך: {duration_min} דק'")

        with col_audio:
            if item.get("previewUrl"):
                st.audio(item.get("previewUrl"))

        with col_status:
            if status_info is None:
                st.info("⚪ טרם נבדק")
            elif status_info["approved"]:
                st.success(f"🟢 מיוצג ({status_info['publisher']})")
            else:
                st.error("🔴 לא מיוצג בפדרציה")

        with col_btn_check:
            if st.button("🔍 בדוק בפדרציה", key=f"btn_check_{track_id}"):
                with st.spinner("בודק..."):
                    is_approved, pub = verify_single_track(item)
                    st.session_state['statuses'][track_id] = {"approved": is_approved, "publisher": pub}
                    st.rerun()

        with col_btn_block:
            if st.button("🚫 חסום אמן", key=f"btn_block_{track_id}"):
                st.session_state['blacklist'].add(clean_art)
                # הסרת כל השירים של האמן הזה מהתוצאות הנוכחיות
                st.session_state['candidates'] = [
                    c for c in st.session_state['candidates']
                    if clean_artist_name(c.get("artistName", "")).lower() not in st.session_state['blacklist']
                ]
                st.toast(f"האמן '{artist}' הועבר לרשימה השחורה", icon="🚫")
                st.rerun()

        st.divider()

    # אפשרות בדיקה מרוכזת למסומנים בלבד
    if selected_to_batch:
        if st.button(f"🔍 בדוק בפדרציה את {len(selected_to_batch)} השירים המסומנים", type="secondary"):
            progress_bar = st.progress(0)
            for i, track_item in enumerate(selected_to_batch):
                t_id = track_item.get("trackId", i)
                is_approved, pub = verify_single_track(track_item)
                st.session_state['statuses'][t_id] = {"approved": is_approved, "publisher": pub}
                progress_bar.progress((i + 1) / len(selected_to_batch))
            st.rerun()
