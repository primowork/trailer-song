import asyncio
import urllib.parse
import httpx
from playwright.async_api import async_playwright

# ----------------------------------------------------
# שלב 1: מנוע חיפוש באינטרנט לשליפת קאברים אמיתיים
# ----------------------------------------------------
async def search_covers_on_web(query: str, limit: int = 10):
    search_term = f"{query} trailer cover"
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(search_term)}&media=music&entity=song&limit={limit}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()
        
    candidates = []
    for item in data.get("results", []):
        artist = item.get("artistName", "")
        raw_track = item.get("trackName", "")
        
        # ניקוי סוגריים ותוספות בשם השיר לקבלת חיפוש נקי בפדרציה
        clean_track = raw_track.split("(")[0].split("-")[0].strip()
        
        candidates.append({
            "artist": artist,
            "track": clean_track,
            "full_title": f"{artist} - {raw_track}",
            "preview_url": item.get("previewUrl")
        })
        
    return candidates

# ----------------------------------------------------
# שלב 2: סורק דפדפן אוטומטי מול אתר הפדרציה
# ----------------------------------------------------
async def verify_in_federation(page, artist: str, track: str) -> bool:
    url = "https://www.federation.co.il/Index.asp?CategoryID=94"
    
    try:
        await page.goto(url, wait_until="networkidle")
        
        # הזנת הנתונים לשדות הטופס
        await page.fill('input[name="artName"]', artist)
        await page.fill('input[name="trkName"]', track)
        
        # לחיצה על כפתור החיפוש והמתנה לטעינת התוצאות
        await page.click('input[type="submit"], button[type="submit"]')
        await page.wait_for_timeout(2000) # המתנה לרענון הטבלה
        
        content = await page.content()
        
        # בדיקה אם קיימת שורת ייצוג בטבלה
        if "מיוצג" in content and "לא נמצאו תוצאות" not in content:
            return True
        return False
    except Exception:
        return False

# ----------------------------------------------------
# הצינור המרכזי (Main Pipeline)
# ----------------------------------------------------
async def run_pipeline(search_query: str):
    print(f"🔎 שלב 1: מחפש קאברים באינטרנט עבור: '{search_query}'...")
    candidates = await search_covers_on_web(search_query, limit=15)
    print(f"Found {len(candidates)} candidates. Starting Federation verification...\n")

    approved_results = []

    # הפעלת דפדפן Playwright ברקע
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # שנה ל-False אם ברצונך לראות את הדפדפן עובד
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()

        for idx, item in enumerate(candidates, 1):
            artist = item["artist"]
            track = item["track"]
            
            print(f"[{idx}/{len(candidates)}] בודק בפדרציה: {artist} - {track}...")
            is_approved = await verify_in_federation(page, artist, track)
            
            if is_approved:
                print(f"   🟢 מאושר בפדרציה!")
                item["status"] = "APPROVED"
                approved_results.append(item)
            else:
                print(f"   🔴 לא מיוצג / לא נמצא")

        await browser.close()

    print(f"\n======================================")
    print(f"🎉 סיום! נמצאו {len(approved_results)} שירים מאושרים בפדרציה:")
    print(f"======================================")
    for res in approved_results:
        print(f"• {res['full_title']}")
        if res.get("previewUrl"):
            print(f"  Audio Preview: {res['previewUrl']}")

if __name__ == "__main__":
    # הרצת הצינור עם מילת חיפוש לבחירתך
    asyncio.run(run_pipeline("victory"))
