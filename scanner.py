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

def fetch_web_covers(query: str, limit: int = 30, filters: dict = None):
    """שליפת מועמדים מ-iTunes API עם סינון לפי קצב, אורך וסגנון"""
    search_query = query
    if filters:
        if filters.get("style") and filters["style"] != "הכל":
            search_query += f" {filters['style']}"
        if filters.get("tempo") and filters["tempo"] != "הכל":
            search_query += f" {filters['tempo']}"

    search_term = f"{search_query} trailer cover"
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(search_term)}&media=music&entity=song&limit=50"
    
    try:
        response = httpx.get(url, timeout=10.0)
        data = response.json()
        results = data.get("results", [])
    except Exception:
        return []

    filtered = []
    for track in results:
        duration_sec = track.get("trackTimeMillis", 0) / 1000

        # פילטר אורך השיר
        if filters and filters.get("length") == "קצר (< 3 דק')" and duration_sec > 180:
            continue
        if filters and filters.get("length") == "ארוך (> 4 דק')" and duration_sec < 240:
            continue
        if filters and filters.get("length") == "בינוני (3-4 דק')" and not (180 <= duration_sec <= 240):
            continue

        filtered.append(track)
        if len(filtered) >= limit:
            break

    return filtered

def verify_selected_tracks(selected_tracks: list, progress_callback=None):
    """מריץ דפדפן Playwright אך ורק על השירים שהמשתמש סימן ב-V"""
    verified_results = []
    total = len(selected_tracks)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()

        for idx, track in enumerate(selected_tracks):
            artist = track.get("artistName", "")
            song = track.get("trackName", "")

            clean_artist_str = clean_text(artist)
            clean_song_str = clean_text(song)

            if progress_callback:
                progress_callback(idx + 1, total, f"בודק בפדרציה: {artist} - {song}")

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
                "preview": track.get("previewUrl", ""),
                "approved": is_approved
            })

        browser.close()

    return verified_results
