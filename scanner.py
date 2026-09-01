import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from thefuzz import fuzz

def clean_track_title(title: str) -> str:
    """מנקה לחלוטין תוספות, סוגריים וגרסאות לקבלת שם היצירה המקורית"""
    cleaned = re.sub(r'\(.*?\)|\[.*?\]', '', title)
    keywords = ['trailer', 'cover', 'epic', 'version', 'remix', 'cinematic', 'feat', 'ft', 'edit', 'theme', 'from']
    for kw in keywords:
        cleaned = re.sub(rf'\b{kw}\b.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def clean_artist_name(artist: str) -> str:
    """מנקה שמות אמנים מתוספות Feat"""
    cleaned = re.sub(r'\(.*?\)|\[.*?\]', '', artist)
    cleaned = re.sub(r'\b(feat|ft)\b.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def fetch_web_covers(query: str, limit: int = 30, filters: dict = None):
    """שליפת מועמדים מ-iTunes API"""
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

def parse_ifpi_table(html_content: str, target_artist: str) -> tuple[bool, str]:
    """מפענח את טבלת התוצאות של הפדרציה לפי עמודות מדויקות"""
    soup = BeautifulSoup(html_content, "html.parser")
    
    if "לא נמצאו תוצאות" in soup.get_text():
        return False, ""

    clean_target = clean_artist_name(target_artist).lower()
    
    rows = soup.find_all("tr")
    for row in rows:
        cols = [td.get_text().strip() for td in row.find_all("td")]
        
        # מבנה עמודות בפדרציה: [0] מבצע | [1] הקלטה | [2] הערות | [3] אלבום | [4] מיוצג ע"י
        if len(cols) >= 5:
            row_artist = cols[0].lower()
            publisher = cols[4]
            
            # בדיקה האם עמודת המייצג אינה ריקה
            if publisher and publisher != "-" and len(publisher) > 1:
                # Fuzzy matching בין שם האמן בטבלה לשם האמן המבוקש
                if clean_target in row_artist or fuzz.partial_ratio(clean_target, row_artist) > 75:
                    return True, publisher
                    
    return False, ""

def verify_selected_tracks(selected_tracks: list, progress_callback=None):
    """סריקת דפדפן ממוקדת עם בדיקה דו-שלבית והמתנת DOM אקטיבית"""
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
                progress_callback(idx + 1, total, f"בודק בפדרציה: {clean_artist} - {clean_song}")

            is_approved = False
            publisher_found = ""

            try:
                # שלב א': חיפוש לפי שם היצירה בלבד
                page.goto("https://www.federation.co.il/Index.asp?CategoryID=94", wait_until="domcontentloaded", timeout=15000)
                page.fill('input[name="artName"]', '')
                page.fill('input[name="trkName"]', clean_song)
                page.click('input[type="submit"], button[type="submit"]')
                
                # המתנה לרכיב התוצאות ב-DOM
                page.wait_for_selector('text="תוצאות חיפוש עבור:"', timeout=8000)
                is_approved, publisher_found = parse_ifpi_table(page.content(), raw_artist)

                # שלב ב': גיבוי - חיפוש משולב (אם החיפוש לפי שיר לא החזיר התאמה)
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
