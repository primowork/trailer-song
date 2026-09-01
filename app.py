import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from playwright.sync_api import sync_playwright
import re
import pandas as pd
import time
import urllib.parse
import subprocess

st.set_page_config(page_title="Federation Cover Checker", page_icon="🎵", layout="wide")

# --- התקנה אוטומטית של Chromium בסביבת הענן (Streamlit Cloud) ---
@st.cache_resource
def init_browser_environment():
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"שגיאה בהתקנת מנוע Chromium: {e}")

init_browser_environment()

st.title("🎵 סורק זכויות קאברים מול הפדרציה (IFPI Israel)")

# --- ניהול מפתחות Spotify (Secrets או תמיכה ב-Sidebar) ---
client_id_default = st.secrets.get("SPOTIFY_CLIENT_ID", "") if "SPOTIFY_CLIENT_ID" in st.secrets else ""
client_secret_default = st.secrets.get("SPOTIFY_CLIENT_SECRET", "") if "SPOTIFY_CLIENT_SECRET" in st.secrets else ""

with st.sidebar:
    st.header("הגדרות Spotify API")
    client_id = st.text_input("Spotify Client ID", value=client_id_default, type="password")
    client_secret = st.text_input("Spotify Client Secret", value=client_secret_default, type="password")

# --- פונקציות עזר ונורמליזציה ---
def clean_title(title: str) -> str:
    """מנקה תגיות תיאוריות משם השיר לקבלת שם טהור לחיפוש"""
    pattern = r'[\(\[\{].*?(cover|trailer|epic|cinematic|remix|version|edit|extended|rework|reimagined).*?[\)\]\}]'
    clean = re.sub(pattern, '', title, flags=re.IGNORECASE)
    clean = re.sub(r'\s+(feat\.|ft\.).*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s*-\s*$', '', clean)
    return clean.strip()

def get_spotify_tracks(playlist_url: str, sp: spotipy.Spotify) -> list:
    """שולף את רשימת השירים מ-Spotify עם מזהי ISRC ושמות נקיים"""
    playlist_id = playlist_url.split("/")[-1].split("?")[0]
    results = sp.playlist_items(playlist_id)
    tracks = []
    
    for item in results.get('items', []):
        track = item.get('track')
        if not track:
            continue
        tracks.append({
            'name': track['name'],
            'clean_name': clean_title(track['name']),
            'artist': track['artists'][0]['name'],
            'isrc': track['external_ids'].get('isrc', ''),
            'spotify_url': track['external_urls']['spotify']
        })
    return tracks

def extract_publisher(page, track: dict):
    """מחלץ את שם החברה המייצגת מטבלת התוצאות"""
    try:
        publisher_elements = page.locator("div:has-text('מיוצג בפדרציה ע\"י') + div, .publisher-cell")
        if publisher_elements.count() > 0:
            pub_text = publisher_elements.first.inner_text().strip()
            if pub_text:
                track['publisher'] = pub_text
    except Exception:
        pass

def check_federation(page, track: dict) -> dict:
    """סורק את מאגר הפדרציה (ifpi.co.il) באמצעות שאילתות GET ישירות"""
    base_url = "https://ifpi.co.il/search.asp"
    track['publisher'] = ''
    
    try:
        # 1. חיפוש לפי ISRC
        if track.get('isrc'):
            isrc_clean = track['isrc'].strip()
            search_url = f"{base_url}?searchBy=&page=&artist=&song={urllib.parse.quote(isrc_clean)}&album="
            page.goto(search_url, timeout=12000, wait_until="domcontentloaded")
            content = page.content()
            
            if "מיוצג" in content and "לא נמצאו" not in content:
                track['status'] = 'APPROVED'
                track['match_type'] = 'ISRC'
                extract_publisher(page, track)
                return track

        # 2. חיפוש לפי שם אמן + שם שיר נקי
        artist_enc = urllib.parse.quote(track['artist'])
        song_enc = urllib.parse.quote(track['clean_name'])
        search_url = f"{base_url}?searchBy=&page=&artist={artist_enc}&song={song_enc}&album="
        page.goto(search_url, timeout=12000, wait_until="domcontentloaded")
        content = page.content()
        
        if ("פרטי היצירה" in content or "מיוצג בפדרציה" in content) and "לא נמצאו תוצאות" not in content:
            track['status'] = 'APPROVED'
            track['match_type'] = 'Artist + Song'
            extract_publisher(page, track)
            return track
            
        # 3. גיבוי - חיפוש לפי שם שיר בלבד
        search_url_song = f"{base_url}?searchBy=&page=&artist=&song={song_enc}&album="
        page.goto(search_url_song, timeout=12000, wait_until="domcontentloaded")
        content_song = page.content()
        
        if ("פרטי היצירה" in content_song or "מיוצג בפדרציה" in content_song) and "לא נמצאו תוצאות" not in content_song:
            track['status'] = 'APPROVED'
            track['match_type'] = 'Song Title Only'
            extract_publisher(page, track)
            return track

        track['status'] = 'REJECTED'
        track['match_type'] = 'None'
            
    except Exception as e:
        track['status'] = 'ERROR'
        track['match_type'] = f'Exception: {str(e)[:40]}'
        
    return track

# --- ממשק המשתמש הרציף ---
playlist_url = st.text_input("הדבק לינק לפלייליסט מ-Spotify:")

if st.button("התחל סריקה", type="primary"):
    if not client_id or not client_secret:
        st.error("אנא הזן Client ID ו-Client Secret בסרגל הצד או בקובץ ה-Secrets.")
    elif not playlist_url:
        st.error("אנא הזן לינק לפלייליסט.")
    else:
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret
            ))
            
            with st.spinner("שולף נתונים מ-Spotify..."):
                tracks = get_spotify_tracks(playlist_url, sp)
            
            st.info(f"נמצאו {len(tracks)} שירים. מתחיל סריקה מול IFPI...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            approved_tracks = []

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                for idx, track in enumerate(tracks):
                    status_text.text(f"בודק ({idx+1}/{len(tracks)}): {track['artist']} - {track['clean_name']}")
                    res = check_federation(page, track)
                    
                    if res['status'] == 'APPROVED':
                        approved_tracks.append(res)
                    
                    progress_bar.progress((idx + 1) / len(tracks))
                    time.sleep(0.3)

                browser.close()

            status_text.success("הסריקה הושלמה!")

            if approved_tracks:
                df = pd.DataFrame(approved_tracks)
                st.subheader(f"✓ נמצאו {len(approved_tracks)} שירים מיוצגים בפדרציה:")
                st.dataframe(df[['name', 'artist', 'publisher', 'isrc', 'match_type', 'spotify_url']], use_container_width=True)
                
                csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button("הורד תוצאות (CSV)", csv, "federation_results.csv", "text/csv")
            else:
                st.warning("לא נמצאו שירים מיוצגים בפדרציה בפלייליסט זה.")

        except Exception as e:
            st.error(f"שגיאה בהרצת הליך הסריקה: {str(e)}")
