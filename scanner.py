import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from thefuzz import fuzz

def clean_artist_name(artist: str) -> str:
    cleaned = re.sub(r'\(.*?\)|\[.*?\]', '', artist)
    cleaned = re.sub(r'\b(feat|ft)\b.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def clean_track_title(title: str) -> str:
    cleaned = re.sub(r'\(.*?\)|\[.*?\]', '', title)
    keywords = ['trailer', 'cover', 'epic', 'version', 'remix', 'cinematic', 'feat', 'ft', 'edit', 'theme', 'from']
    for kw in keywords:
        cleaned = re.sub(rf'\b{kw}\b.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def fetch_web_covers(query: str, limit: int = 40, filters: dict = None):
    search_query = query
    if filters:
        if filters.get("style") and filters["style"] != "הכל":
            search_query += f" {filters['style']}"
        if filters.get("tempo") and filters["tempo"] != "הכל":
            search_query += f" {filters['tempo']}"

    search_term = f"{search_query} trailer cover"
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(search_term)}&media=music&entity=song&limit=50"
    
    try:
        response = httpx.get(url, timeout=5.0)
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
    """קורא את הטבלה כולה ללא תלות במספר העמודה כדי למנוע פספוסים"""
    soup = BeautifulSoup(html_content, "html.parser")
    if "לא נמצאו תוצאות" in soup.get_text():
        return False, ""

    clean_target = clean_artist_name(target_artist).lower()
    rows = soup.find_all("tr")
    
    for row in rows:
        cols = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
        row_text = " ".join(cols).lower()
        
        # זיהוי חכם: האם שם האמן מופיע בשורה
        if clean_target in row_text or fuzz.partial_ratio(clean_target, row_text) > 80:
            
            # חיפוש חברת תקליטים בכל העמודות
            publishers = ["יוניברסל", "וורנר", "סוני", "nmc", "הליקון", "bmg", "universal", "sony", "warner"]
            for col in cols:
                col_lower = col.lower()
                if any(p in col_lower for p in publishers):
                    return True, col
            
            # גיבוי: שליפת התוכן מעמודה 4 אם לא נמצאה מילת מפתח מדויקת
            if len(cols) >= 5 and len(cols[4]) > 1 and cols[4] != "-":
                return True, cols[4]
                    
    return False, ""

def verify_single_track(track: dict) -> tuple[bool, str]:
    raw_artist = track.get("artistName", "")
    raw_song = track.get("trackName", "")

    clean_song = clean_track_title(raw_song)
    clean_artist = clean_artist_name(raw_artist)

    is_approved = False
    publisher_found = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()

        try:
            # אסטרטגיה 1 (המתוקנת): חיפוש אמן + שיר יחד כדי למנוע נפילה לעמודים מוסתרים
            page.goto("https://www.federation.co.il/Index.asp?CategoryID=94", wait_until="domcontentloaded", timeout=15000)
            page.fill('input[name="artName"]', clean_artist)
            page.fill('input[name="trkName"]', clean_song)
            
            # במקום page.click שקורס, משתמשים ב-Enter עם השהייה קשיחה לאתרים איטיים
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)
            
            is_approved, publisher_found = parse_ifpi_table(page.content(), raw_artist)

            # אסטרטגיה 2: חיפוש גיבוי לפי שיר בלבד (למקרה של כתיב אמן שגוי לחלוטין)
            if not is_approved:
                page.goto("https://www.federation.co.il/Index.asp?CategoryID=94", wait_until="domcontentloaded", timeout=15000)
                page.fill('input[name="artName"]', '')
                page.fill('input[name="trkName"]', clean_song)
                
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)
                
                is_approved, publisher_found = parse_ifpi_table(page.content(), raw_artist)

        except Exception as e:
            is_approved = False

        browser.close()

    return is_approved, publisher_found
