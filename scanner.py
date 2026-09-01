import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from thefuzz import fuzz

def clean_artist_name(artist: str) -> str:
    """ניקוי שם אמן לקבלת חיפוש נקי בפדרציה"""
    cleaned = re.sub(r'\(.*?\)|\[.*?\]', '', artist)
    cleaned = re.sub(r'\b(feat|ft)\b.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def clean_track_title(title: str) -> str:
    """ניקוי שם שיר"""
    cleaned = re.sub(r'\(.*?\)|\[.*?\]', '', title)
    keywords = ['trailer', 'cover', 'epic', 'version', 'remix', 'cinematic', 'feat', 'ft', 'edit', 'theme', 'from']
    for kw in keywords:
        cleaned = re.sub(rf'\b{kw}\b.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def fetch_web_covers(query: str, limit: int = 30, filters: dict = None, blacklist: set = None):
    """שליפת מועמדים מ-iTunes API עם סינון מוקדם של אמנים ברשימה השחורה"""
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
    blacklist = blacklist or set()

    for track in results:
        artist = clean_artist_name(track.get("artistName", ""))
        
        # דילוג מיידי על אמנים שנמצאים ברשימה השחורה
        if artist.lower() in blacklist:
            continue

        duration_sec = track.get("trackTimeMillis", 0) / 1000

        if filters and filters.get("length"):
            l_filter = filters["length"]
            if l_filter == "קצר (< 3 דק')" and duration_sec > 180:
                continue
            elif l_filter == "ארוך (> 4 דק')" and duration_sec < 240:
                continue
            elif l_filter == "בינוני (3-4 דק')" and not (180 <= duration_sec <= 240):
                continue

        filtered.append(track)
        if len(filtered) >= limit:
            break

    return filtered

def is_artist_represented_in_ifpi(page, raw_artist: str) -> bool:
    """בודק האם לאמן יש נוכחות כלשהי במאגר הפדרציה"""
    clean_artist = clean_artist_name(raw_artist)
    if not clean_artist:
        return False

    try:
        page.goto("https://www.federation.co.il/Index.asp?CategoryID=94", wait_until="domcontentloaded", timeout=12000)
        page.fill('input[name="artName"]', clean_artist)
        page.fill('input[name="trkName"]', '')
        page.click('input[type="submit"], button[type="submit"]')
        page.wait_for_selector('text="תוצאות חיפוש עבור:"', timeout=6000)

        soup = BeautifulSoup(page.content(), "html.parser")
        text = soup.get_text()

        if "לא נמצאו תוצאות" in text:
            return False

        rows = soup.find_all("tr")
        for row in rows:
            cols = [td.get_text().strip() for td in row.find_all("td")]
            if len(cols) >= 5 and cols[4] and cols[4] != "-":
                return True
        return False
    except Exception:
        return False

def filter_candidates_by_artist_presence(candidates: list, blacklist: set, whitelist: set, progress_callback=None):
    """סינון מוקדם של תוצאות לפי קיום האמן במאגר הפדרציה"""
    valid_candidates = []
    unique_artists = list(set([c.get("artistName", "") for c in candidates]))
    
    total = len(unique_artists)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()

        for idx, artist in enumerate(unique_artists):
            clean_art = clean_artist_name(artist).lower()

            if progress_callback:
                progress_callback(idx + 1, total, f"בודק אמן מול הפדרציה: {artist}")

            # בדיקה אם האמן כבר מוכר במטמון
            if clean_art in whitelist:
                continue
            if clean_art in blacklist:
                continue

            # סריקת האמן בפדרציה
            has_presence = is_artist_represented_in_ifpi(page, artist)

            if has_presence:
                whitelist.add(clean_art)
            else:
                blacklist.add(clean_art)

        browser.close()

    # סינון הרשימה והחזרת רק אמנים שאינם ברשימה השחורה
    for track in candidates:
        art = clean_artist_name(track.get("artistName", "")).lower()
        if art not in blacklist:
            valid_candidates.append(track)

    return valid_candidates, blacklist, whitelist

def parse_ifpi_table(html_content: str, target_artist: str) -> tuple[bool, str]:
    """מפענח את טבלת התוצאות של הפדרציה לפי עמודות מדויקות"""
    soup = BeautifulSoup(html_content, "html.parser")
    
    if "לא נמצאו תוצאות" in soup.get_text():
        return False, ""

    clean_target = clean_artist_name(target_artist).lower()
    rows = soup.find_all("tr")
    
    for row in rows:
        cols = [td.get_text().strip() for td in row.find_all("td")]
        if len(cols) >= 5:
            row_artist = cols[0].lower()
            publisher = cols[4]
            if publisher and publisher != "-" and len(publisher) > 1:
                if clean_target in row_artist or fuzz.partial_ratio(clean_target, row_artist) > 75:
                    return True, publisher
                    
    return False, ""

def verify_selected_tracks(selected_tracks: list, progress_callback=None):
    """אימות סופי של השירים שנבחרו בלבד"""
    verified_results = []
    total = len(selected_tracks)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()

        for idx, track in enumerate(selected_tracks):
            raw_artist = track.get("artistName", "")
            raw_song = track.get("trackName", "")

            clean_song = clean_track_title(raw_song)
            clean_artist = clean_artist_name(raw_artist)

            if progress_callback:
                progress_callback(idx + 1, total, f"מאמת זכויות שיר: {clean_artist} - {clean_song}")

            is_approved = False
            publisher_found = ""

            try:
                # 1. חיפוש לפי שם היצירה
                page.goto("https://www.federation.co.il/Index.asp?CategoryID=94", wait_until="domcontentloaded", timeout=15000)
                page.fill('input[name="artName"]', '')
                page.fill('input[name="trkName"]', clean_song)
                page.click('input[type="submit"], button[type="submit"]')
                
                page.wait_for_selector('text="תוצאות חיפוש עבור:"', timeout=8000)
                is_approved, publisher_found = parse_ifpi_table(page.content(), raw_artist)

                # 2. גיבוי - חיפוש משולב
                if not is_approved:
                    page.goto("https://www.federation.co.il/Index.asp?CategoryID=94", wait_until="domcontentloaded", timeout=15000)
                    page.fill('input[name="artName"]', clean_artist)
                    page.fill('input[name="trkName"]', clean_song)
                    page.click('input[type="submit"], button[type="submit"]')
                    
                    page.wait_for_selector('text="תוצאות חיפוש עבור:"', timeout=8000)
                    is_approved, publisher_found = parse_ifpi_table(page.content(), raw_artist)

            except Exception:
                is_approved = False

            verified_results.append({
                "artist": raw_artist,
                "song": raw_song,
                "publisher": publisher_found,
                "preview": track.get("previewUrl", ""),
                "approved": is_approved
            })

        browser.close()

    return verified_results
