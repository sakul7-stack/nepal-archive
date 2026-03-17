from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import sqlite3
import os
import re
import json
import time
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
from pdf2image import convert_from_path

urllib3.disable_warnings()

PAPER_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PAPER_PDF_DIR   = os.path.join(PAPER_BASE_DIR, "paper_archive", "pdfs")
PAPER_THUMB_DIR = os.path.join(PAPER_BASE_DIR, "paper_archive", "thumbnails")
PAPER_DB_PATH   = os.path.join(PAPER_BASE_DIR, "paper_archive", "database.db")

os.makedirs(PAPER_PDF_DIR,   exist_ok=True)
os.makedirs(PAPER_THUMB_DIR, exist_ok=True)

NEWSPAPERS = {
    "gorkhapatra": {
        "name": "Gorkhapatra",
        "list_url": "https://epaper.gorkhapatraonline.com/single/gorkhapatra",
        "selector": "div.paperdesign a",
        "language": "np"
    },
    "risingnepal": {
        "name": "The Rising Nepal",
        "list_url": "https://epaper.gorkhapatraonline.com/single/risingnepal",
        "selector": "div.paperdesign a",
        "language": "en"
    },
    "nayapatrika": {
        "name": "Naya Patrika",
        "date_url_pattern": "https://epaper.nayapatrikadaily.com/index.php?posted_id={y}-{m}-{d}",
        "pdf_selector": "span.input-group-addon.pdf-icn a",
        "language": "np"
    },
    "abhiyandaily": {
        "name": "Abhiyan Daily",
        "epaper_url": "https://abhiyandaily.com/epaper/",
        "download_js_selector": "a.download__epaper",
        "language": "np"
    },
    "karobardaily": {
        "name": "Karobar Daily",
        "main_url": "https://www.karobardaily.com/news/e-paper/",
        "today_paper_selector": "div.uk-width-5-5\\@s.uk-first-column",
        "download_button_selector": "span.fa-file.flipbook-icon-fa.flipbook-menu-btn.skin-color.fa.flipbook-color-light",
        "language": "np"
    },
    "himalayatimes": {
        "name": "Himalaya Times",
        "epaper_url": "https://ehimalayatimes.com/epaper/",
        "more_button_selector": "div.df-ui-more",
        "download_link_selector": "a.df-ui-download",
        "language": "np"
    },
    "souryadaily": {
        "name": "Sourya Daily",
        "main_url": "https://www.souryaonline.com/paper",
        "today_paper_selector": "div.epaper_item a",
        "pdf_pattern": r'https://www\.souryaonline\.com/wp-content/uploads/.*?\.pdf',
        "language": "np"
    },
    "annapurnapost": {
        "name": "Annapurna Post",
        "epaper_url": "https://annapurnapost.com/epaper/",
        "download_links_selector": "button.view__flipbook.view__download a",
        "language": "np"
    },
    "rajdhani": {
        "name": "Rajdhani Daily",
        "epaper_url": "https://rajdhani.com.np/",
        "more_button_selector": ".df-ui-more",
        "download_button_selector": "a.df-ui-btn.df-ui-download.df-icon-download",
        "language": "np"
    },
    "apandainik": {
        "name": "Apan Dainik",
        "epaper_url": "https://epaper.apandainik.com/all-day-epaper/",
        "thumbnail_selector": ".pcp-post-thumb-wrapper",
        "download_button_selector": "a.pdfp_download.pdfp_download_btn.button",
        "use_yesterday": True,
        "language": "np"
    },
    "samacharpata": {
        "name": "Samachar Patra",
        "epaper_url": "https://epaper.newsofnepal.com/",
        "language": "np"
    },
    "kantipur": {
        "name": "Kantipur",
        "download_url_pattern": "https://epaper.ekantipur.com/kantipur/download/{y}-{m}-{d}",
        "language": "np"
    },
    "kathmandupost": {
        "name": "Kathmandu Post",
        "download_url_pattern": "https://epaper.ekantipur.com/kathmandupost/download/{y}-{m}-{d}",
        "language": "en"
    },
    "nagarik": {
        "name": "Nagarik",
        "epaper_base_url": "https://nagariknews.nagariknetwork.com/epaper/",
        "base_id": 2640,
        "base_date": "2026-01-01",
        "language": "np"
    }
}

BROWSER_ARGS = [
    "--no-sandbox", "--disable-gpu", "--mute-audio", "--disable-dev-shm-usage",
    "--disable-extensions", "--disable-background-networking",
    "--disable-default-apps", "--no-first-run",
    "--js-flags=--max-old-space-size=256",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Connection": "keep-alive",
}



def init_db():
    conn = sqlite3.connect(PAPER_DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS newspapers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'np'
        );
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            newspaper_id INTEGER NOT NULL REFERENCES newspapers(id),
            issue_date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(newspaper_id, issue_date)
        );
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER NOT NULL REFERENCES issues(id),
            pdf_path TEXT NOT NULL,
            thumbnail_path TEXT
        );
    """)
    conn.commit()
    conn.close()


def save_paper(conn, key, name, language, issue_date, pdf_path, thumbnail_path):
    c = conn.cursor()
    c.execute("""
        INSERT INTO newspapers (key, name, language) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET name=excluded.name, language=excluded.language
    """, (key, name, language))
    conn.commit()
    c.execute("SELECT id FROM newspapers WHERE key=?", (key,))
    newspaper_id = c.fetchone()[0]

    c.execute("INSERT OR IGNORE INTO issues (newspaper_id, issue_date) VALUES (?,?)",
              (newspaper_id, issue_date))
    conn.commit()
    c.execute("SELECT id FROM issues WHERE newspaper_id=? AND issue_date=?",
              (newspaper_id, issue_date))
    issue_id = c.fetchone()[0]

    c.execute("DELETE FROM files WHERE issue_id=?", (issue_id,))
    c.execute("INSERT INTO files (issue_id, pdf_path, thumbnail_path) VALUES (?,?,?)",
              (issue_id, pdf_path, thumbnail_path))
    conn.commit()
    print(f"[DB] Saved {name} for {issue_date}")



def download_pdf(pdf_url, date_str, key):
    pdf_url = pdf_url.strip()

    if "?file=" in pdf_url:
        try:
            file_path = pdf_url.split("?file=")[1]
            pdf_url   = "https://epaper.gorkhapatraonline.com" + file_path
        except Exception:
            pass

    cookies = {}
    if key in ("kantipur", "kathmandupost"):
        cookies = {
        }
    elif key == "nagarik":
        cookies = {
        }

    try:
        r = requests.get(pdf_url, headers=HEADERS, cookies=cookies,
                         verify=False, timeout=60, stream=True)
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "").lower()
        if "pdf" not in ct:
            print(f"  Non-PDF for {key} (Content-Type: {ct})")
            return None, None
    except Exception as e:
        print(f"  Download failed for {key}: {e}")
        return None, None

    pdf_path = os.path.join(PAPER_PDF_DIR, f"{date_str}_{key}.pdf")
    try:
        with open(pdf_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        print(f"  PDF saved: {pdf_path}")
    except Exception as e:
        print(f"  Save failed for {key}: {e}")
        return None, None

    thumb_path = make_thumbnail(pdf_path, date_str, key)
    return pdf_path, thumb_path


def make_thumbnail(pdf_path, date_str, key, dest_path=None):
    if dest_path is None:
        dest_path = os.path.join(PAPER_THUMB_DIR, f"{date_str}_{key}.jpg")
    try:
        images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=1)
        if images:
            img = images[0]
            img.thumbnail((400, 600))
            img.save(dest_path, "JPEG", quality=85)
            print(f"  Thumbnail: {dest_path}")
            return dest_path
    except Exception as e:
        print(f"  Thumbnail failed for {key}: {e}")
    return None


def new_browser(p):
    return p.chromium.launch(headless=True, args=BROWSER_ARGS)


def new_page(browser, block_media=True):
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    )
    if block_media:
        ctx.route("**/*", lambda route, req:
            route.abort() if req.resource_type in ("font", "image", "media")
            else route.continue_())
    return ctx, ctx.new_page()


def get_pdf_url_gorkhapatra_rising(key, info):
    with sync_playwright() as p:
        browser = new_browser(p)
        try:
            ctx, page = new_page(browser)
            page.goto(info["list_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            el = page.query_selector(info["selector"])
            if el:
                href = el.get_attribute("href") or ""
                return href if href.startswith("http") else ""
        except Exception as e:
            print(f"  {key} error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_nayapatrika(info, today):
    url = info["date_url_pattern"].format(
        y=today.strftime("%Y"), m=today.strftime("%m"), d=today.strftime("%d"))
    cookies = {"PHPSESSID": "25dc5220dbcc5c59ac596a8b3b2ebab9", "STACKSCALING": "web99j"}
    try:
        r = requests.get(url, headers=HEADERS, cookies=cookies, verify=False, timeout=30)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            tag  = soup.select_one(info["pdf_selector"])
            if tag and tag.get("href"):
                href = tag["href"]
                return href if href.startswith("http") else "https://epaper.nayapatrikadaily.com/" + href.lstrip("/")
    except Exception as e:
        print(f"  nayapatrika error: {e}")
    return None


def get_pdf_url_abhiyandaily(info):
    """Download PDF via Playwright by triggering the download button."""
    download_temp = os.path.join(PAPER_BASE_DIR, "temp_downloads")
    os.makedirs(download_temp, exist_ok=True)
    for f in os.listdir(download_temp):
        fp = os.path.join(download_temp, f)
        if os.path.isfile(fp):
            os.remove(fp)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        try:
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
            )
            page = ctx.new_page()
            page.goto(info["epaper_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(15)
            with page.expect_download(timeout=60000) as dl_info:
                page.click(info["download_js_selector"])
            dl = dl_info.value
            dest = os.path.join(download_temp, dl.suggested_filename or "abhiyan.pdf")
            dl.save_as(dest)
            print(f"  Abhiyan download: {dest}")
            return dest  # return local path, handled differently
        except Exception as e:
            print(f"  abhiyandaily error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_karobardaily(info):
    with sync_playwright() as p:
        browser = new_browser(p)
        try:
            ctx, page = new_page(browser, block_media=False)
            page.goto(info["main_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            page.click(info["today_paper_selector"])
            time.sleep(10)
            page.click(info["download_button_selector"])
            time.sleep(10)
            pages = ctx.pages
            if len(pages) > 1:
                return pages[-1].url
            return page.url
        except Exception as e:
            print(f"  karobardaily error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_himalayatimes(info):
    with sync_playwright() as p:
        browser = new_browser(p)
        try:
            ctx, page = new_page(browser, block_media=False)
            page.goto(info["epaper_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(10)
            page.click(info["more_button_selector"])
            time.sleep(10)
            el = page.query_selector(info["download_link_selector"])
            return el.get_attribute("href") if el else None
        except Exception as e:
            print(f"  himalayatimes error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_souryadaily(info):
    with sync_playwright() as p:
        browser = new_browser(p)
        try:
            ctx, page = new_page(browser, block_media=False)
            page.goto(info["main_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            page.click(info["today_paper_selector"])
            time.sleep(5)
            new_pages = ctx.pages
            src = new_pages[-1].content() if len(new_pages) > 1 else page.content()
            pdfs = re.findall(info["pdf_pattern"], src)
            return pdfs[0] if pdfs else None
        except Exception as e:
            print(f"  souryadaily error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_annapurnapost(info):
    with sync_playwright() as p:
        browser = new_browser(p)
        try:
            ctx, page = new_page(browser, block_media=False)
            page.goto(info["epaper_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(10)
            el = page.query_selector(info["download_links_selector"])
            return el.get_attribute("href") if el else None
        except Exception as e:
            print(f"  annapurnapost error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_rajdhani(info):
    with sync_playwright() as p:
        browser = new_browser(p)
        try:
            ctx, page = new_page(browser, block_media=False)
            page.goto(info["epaper_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(10)
            page.click(info["more_button_selector"])
            time.sleep(10)
            el = page.query_selector(info["download_button_selector"])
            return el.get_attribute("href") if el else None
        except Exception as e:
            print(f"  rajdhani error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_apandainik(info):
    with sync_playwright() as p:
        browser = new_browser(p)
        try:
            ctx, page = new_page(browser, block_media=False)
            page.goto(info["epaper_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(10)
            thumb = page.query_selector(info["thumbnail_selector"])
            if thumb:
                thumb.scroll_into_view_if_needed()
                time.sleep(1)
                thumb.click()
                time.sleep(10)
            el = page.query_selector(info["download_button_selector"])
            return el.get_attribute("href") if el else None
        except Exception as e:
            print(f"  apandainik error: {e}")
        finally:
            browser.close()
    return None


def get_pdf_url_samacharpata(info):
    """Intercept PDF network requests."""
    pdf_url = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        try:
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})

            def handle_response(response):
                nonlocal pdf_url
                if response.status == 206 and response.url.lower().endswith(".pdf"):
                    pdf_url = response.url

            ctx.on("response", handle_response)
            page = ctx.new_page()
            page.goto(info["epaper_url"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            btn = page.query_selector("a > div.box-shadow.epaper-img")
            if btn:
                btn.scroll_into_view_if_needed()
                time.sleep(1)
                btn.click()
                time.sleep(25)
        except Exception as e:
            print(f"  samacharpata error: {e}")
        finally:
            browser.close()
    return pdf_url



def scrape_today():
    tz        = pytz.timezone("Asia/Kathmandu")
    today     = datetime.now(tz)
    today_str = today.strftime("%Y-%m-%d")
    print(f"Scraping for {today_str}...")

    init_db()
    conn = sqlite3.connect(PAPER_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    for key, info in NEWSPAPERS.items():
        name         = info["name"]
        language     = info.get("language", "np")
        save_date_str = today_str

        if info.get("use_yesterday"):
            save_date_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"\n── {name} ──")
        pdf_url   = None
        pdf_local = None  

        try:
            if key in ("gorkhapatra", "risingnepal"):
                pdf_url = get_pdf_url_gorkhapatra_rising(key, info)

            elif key == "nayapatrika":
                pdf_url = get_pdf_url_nayapatrika(info, today)

            elif key in ("kantipur", "kathmandupost"):
                y, m, d = today.strftime("%Y"), today.strftime("%m"), today.strftime("%d")
                pdf_url = info["download_url_pattern"].format(y=y, m=m, d=d)

            elif key == "nagarik":
                tz_naive   = pytz.timezone("Asia/Kathmandu")
                base_date  = tz_naive.localize(datetime.strptime(info["base_date"], "%Y-%m-%d"))
                days_offset = (today - base_date).days
                epaper_id  = info["base_id"] + days_offset
                pdf_url    = info["epaper_base_url"] + str(epaper_id)

            elif key == "abhiyandaily":
                pdf_local = get_pdf_url_abhiyandaily(info)

            elif key == "karobardaily":
                pdf_url = get_pdf_url_karobardaily(info)

            elif key == "himalayatimes":
                pdf_url = get_pdf_url_himalayatimes(info)

            elif key == "souryadaily":
                pdf_url = get_pdf_url_souryadaily(info)

            elif key == "annapurnapost":
                pdf_url = get_pdf_url_annapurnapost(info)

            elif key == "rajdhani":
                pdf_url = get_pdf_url_rajdhani(info)

            elif key == "apandainik":
                pdf_url = get_pdf_url_apandainik(info)

            elif key == "samacharpata":
                pdf_url = get_pdf_url_samacharpata(info)

            else:

                r = requests.get(info.get("list_url", ""), verify=False, timeout=30)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "lxml")
                    tag  = soup.select_one(info["selector"])
                    if tag and tag.get("href"):
                        pdf_url = tag["href"]

            if pdf_local:
                dest_path  = os.path.join(PAPER_PDF_DIR, f"{save_date_str}_{key}.pdf")
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(pdf_local, dest_path)
                thumb_dest = os.path.join(PAPER_THUMB_DIR, f"{save_date_str}_{key}.jpg")
                thumb_path = make_thumbnail(dest_path, save_date_str, key, thumb_dest)
                save_paper(conn, key, name, language, save_date_str, dest_path, thumb_path)
                continue

            if not pdf_url:
                print(f"  No PDF URL found for {name}")
                continue

            print(f"  URL: {pdf_url}")
            pdf_path, thumb_path = download_pdf(pdf_url, save_date_str, key)
            if pdf_path:
                save_paper(conn, key, name, language, save_date_str, pdf_path, thumb_path)

        except Exception as e:
            print(f"  Error for {name}: {e}")

        time.sleep(3) 

    conn.close()
    print("\nFinished")


if __name__ == "__main__":
    scrape_today()
