import streamlit as st
from scanner import fetch_web_covers, filter_candidates_by_artist_presence, verify_selected_tracks

st.set_page_config(page_title="סורק קאברים - IFPI Israel", page_icon="🎵", layout="wide")

st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div[data-testid="stColumn"] { text-align: right; }
    </style>
""", unsafe_allow_html=True)

# אתחול רשימה שחורה ולבנה בזיכרון המערכת
if 'blacklist' not in st.session_state:
    st.session_state['blacklist'] = set()
if 'whitelist' not in st.session_state:
    st.session_state['whitelist'] = set()

st.title("🎵 סורק קאברים ממוקד מול הפדרציה (IFPI Israel)")
st.write("המערכת מסננת אוטומטית אמנים שאינם מופיעים בפדרציה ומציגה לך רק קאברים מיוצרים מורשים.")

# פילטרים
with st.expander("🎛️ פילטרים לחיפוש (סגנון, קצב, אורך)", expanded=True):
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

if st.button("1. חפש אופציות (כולל סינון אמנים מוקדם)", type="primary"):
    if query.strip():
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total, msg):
            progress_bar.progress(current / total)
            status_text.text(f"[{current}/{total}] {msg}")

        with st.spinner("שולף ומסנן אמנים לא מיוצגים..."):
            # 1. שליפה מ-iTunes עם סינון רשימה שחורה קיימת
            raw_candidates = fetch_web_covers(query, limit=30, filters=filters, blacklist=st.session_state['blacklist'])
            
            # 2. סינון אמנים מול הפדרציה
            valid_candidates, updated_bl, updated_wl = filter_candidates_by_artist_presence(
                raw_candidates, 
                st.session_state['blacklist'], 
                st.session_state['whitelist'],
                progress_callback=update_progress
            )
            
            st.session_state['blacklist'] = updated_bl
            st.session_state['whitelist'] = updated_wl
            st.session_state['candidates'] = valid_candidates
            st.session_state['results'] = None

        status_text.empty()
        progress_bar.empty()

# הצגת המועמדים המסוננים בלבד
if 'candidates' in st.session_state and st.session_state['candidates']:
    st.subheader(f"נמצאו {len(st.session_state['candidates'])} קאברים מאמנים מוכרים בפדרציה. האזן וסמן לבדיקת שיר ספציפי:")
    
    selected_to_scan = []
    
    for idx, item in enumerate(st.session_state['candidates']):
        col_check, col_title, col_audio, col_similar = st.columns([1, 3, 3, 2])
        
        artist = item.get("artistName", "")
        track = item.get("trackName", "")
        genre = item.get("primaryGenreName", "")
        duration_min = round(item.get("trackTimeMillis", 0) / 60000, 1)
        
        with col_check:
            is_selected = st.checkbox("סרוק שיר", key=f"chk_{idx}")
        with col_title:
            st.markdown(f"**{artist}** - {track}")
            st.caption(f"ז'אנר: {genre} | אורך: {duration_min} דק'")
        with col_audio:
            if item.get("previewUrl"):
                st.audio(item.get("previewUrl"))
        with col_similar:
            if st.button("🔎 מצא עוד כזה", key=f"btn_sim_{idx}"):
                similar_query = f"{artist} {genre}"
                with st.spinner(f"מחפש שירים דומים ל-{artist}..."):
                    raw_sim = fetch_web_covers(similar_query, limit=30, filters=filters, blacklist=st.session_state['blacklist'])
                    valid_sim, updated_bl, updated_wl = filter_candidates_by_artist_presence(
                        raw_sim, st.session_state['blacklist'], st.session_state['whitelist']
                    )
                    st.session_state['blacklist'] = updated_bl
                    st.session_state['whitelist'] = updated_wl
                    st.session_state['candidates'] = valid_sim
                    st.session_state['results'] = None
                    st.rerun()
        
        if is_selected:
            selected_to_scan.append(item)
        st.divider()

    if st.button("2. 🔍 סרוק זכויות בפדרציה לשירים שנבחרו", type="secondary"):
        if not selected_to_scan:
            st.warning("אנא סמן לפחות שיר אחד לבדיקה.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(current, total, msg):
                progress_bar.progress(current / total)
                status_text.text(f"[{current}/{total}] {msg}")

            with st.spinner("מריץ אימות סופית לשירים שנבחרו..."):
                results = verify_selected_tracks(selected_to_scan, progress_callback=update_progress)
                st.session_state['results'] = results

            status_text.empty()
            progress_bar.empty()

# הצגת תוצאות
if 'results' in st.session_state and st.session_state['results']:
    approved = [r for r in st.session_state['results'] if r['approved']]
    rejected = [r for r in st.session_state['results'] if not r['approved']]

    st.success(f"סריקה הושלמה! נמצאו {len(approved)} שירים מאושרים מתוך {len(st.session_state['results'])} שנבדקו.")

    if approved:
        st.subheader("🟢 מאושרים בפדרציה")
        for item in approved:
            st.markdown(f"✅ **{item['artist']}** - {item['song']} *(מיוצג ע\"י: {item['publisher']})*")
            if item.get("preview"):
                st.audio(item["preview"])

    if rejected:
        with st.expander("🔴 לא מיוצגים בפדרציה"):
            for item in rejected:
                st.write(f"❌ {item['artist']} - {item['song']}")

# הצגת סטטיסטיקת רשימה שחורה בסיידבר
st.sidebar.markdown("### 🛡️ נתוני סינון אמנים")
st.sidebar.write(f"אמנים ברשימה השחורה: **{len(st.session_state['blacklist'])}**")
st.sidebar.write(f"אמנים ברשימה הלבנה: **{len(st.session_state['whitelist'])}**")
