import re
import urllib.parse
import httpx
from playwright.sync_api import sync_playwright

def clean_text(text: str) -> str:
    """ניקוי תוספות משם השיר והאמן לטובת חיפוש נקי בפדרציה"""
    text = re.sub(r'\(.*?\)|\[.*?\]', '', text)
    keywords = ['trailer', 'cover', 'epic', 'version', 'remix', 'cinematic', 'feat', 'ft', 'edit']
    for kw in keywords:
        text = re.sub(rf'\b{kw}\b', '', text, flags=re.IGNORECASE)
    return text.strip()

def fetch_web_covers(query: str, limit: int = 10):
    """שליפת מועמדים אמיתיים מ-iTunes API ללא צורך במפתחות API"""
    search_term = f"{query} trailer cover"
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(search_term)}&media=music&entity=song&limit={limit}"
    
    try:
        response = httpx.get(url, timeout=10.0)
        data = response.json()
        return data.get("results", [])
    except Exception:
        return []

def scan_and_verify_ifpi(query: str, progress_callback=None):
    """סריקה אוטומטית בדפדפן Playwright מול אתר הפדרציה"""
    raw_tracks = fetch_web_covers(query)
    if not raw_tracks:
        return []

    verified_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()

        total = len(raw_tracks)
        for idx, track in enumerate(raw_tracks):
            artist = track.get("artistName", "")
            song = track.get("trackName", "")
            preview_url = track.get("previewUrl", "")

            clean_artist_str = clean_text(artist)
            clean_song_str = clean_text(song)

            if progress_callback:
                progress_callback(idx + 1, total, f"בודק: {artist} - {song}")

            is_approved = False
            try:
                page.goto("https://www.federation.co.il/Index.asp?CategoryID=94", wait_until="networkidle", timeout=15000)
                page.fill('input[name="artName"]', clean_artist_str)
                page.fill('input[name="trkName"]', clean_song_str)
                page.click('input[type="submit"], button[type="submit"]')
                page.wait_for_timeout(2000)

                content = page.content()
                if "מיוצג" in content and "לא נמצאו תוצאות" not in content:
                    is_approved = True
            except Exception:
                is_approved = False

            verified_results.append({
                "artist": artist,
                "song": song,
                "preview": preview_url,
                "approved": is_approved
            })

        browser.close()

    return verified_results
