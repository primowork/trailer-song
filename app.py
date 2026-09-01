import streamlit as st
from scanner import scan_and_verify_ifpi

st.set_page_config(page_title="סורק זכויות קאברים (IFPI Israel)", page_icon="🎵", layout="wide")

st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🎵 סורק זכויות קאברים מול הפדרציה (IFPI Israel)")
st.write("הכנס נושא או סגנון (למשל: victory, action, dark) והמערכת תאתר קאברים באינטרנט ותאמת אותם בלייב מול מאגר הפדרציה.")

query = st.text_input("מילת חיפוש / סגנון:", placeholder="למשל: victory cover")

if st.button("התחל סריקה", type="primary"):
    if not query.strip():
        st.warning("אנא הכנס מילת חיפוש.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total, msg):
            progress_bar.progress(current / total)
            status_text.text(f"[{current}/{total}] {msg}")

        with st.spinner("מפעיל דפדפן בסביבת הענן..."):
            results = scan_and_verify_ifpi(query, progress_callback=update_progress)

        status_text.empty()
        progress_bar.empty()

        approved_list = [r for r in results if r["approved"]]
        rejected_list = [r for r in results if not r["approved"]]

        st.subheader(f"🟢 שירים מאושרים בפדרציה ({len(approved_list)})")
        if approved_list:
            for item in approved_list:
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{item['artist']}** - {item['song']}")
                    with col2:
                        if item['preview']:
                            st.audio(item['preview'])
                st.divider()
        else:
            st.info("לא נמצאו שירים מאושרים בחיפוש זה.")

        if rejected_list:
            with st.expander(f"🔴 שירים שנבדקו ולא נמצאו מיוצגים ({len(rejected_list)})"):
                for item in rejected_list:
                    st.write(f"• {item['artist']} - {item['song']}")
