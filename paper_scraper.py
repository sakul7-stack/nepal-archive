import os
import requests
import urllib3
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sqlite3
from paper_config import NEWSPAPERS
import time
import pytz
from pdf2image import convert_from_path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

urllib3.disable_warnings()

PAPER_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PAPER_PDF_DIR   = os.path.join(PAPER_BASE_DIR, "paper_archive", "pdfs")
PAPER_THUMB_DIR = os.path.join(PAPER_BASE_DIR, "paper_archive", "thumbnails")
PAPER_DB_PATH   = os.path.join(PAPER_BASE_DIR, "paper_archive", "database.db")

os.makedirs(PAPER_PDF_DIR,   exist_ok=True)
os.makedirs(PAPER_THUMB_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(PAPER_DB_PATH)
    c    = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS newspapers (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            key      TEXT UNIQUE NOT NULL,
            name     TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'np'
        );

        CREATE TABLE IF NOT EXISTS issues (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            newspaper_id  INTEGER NOT NULL REFERENCES newspapers(id),
            issue_date    TEXT    NOT NULL,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(newspaper_id, issue_date)
        );

        CREATE TABLE IF NOT EXISTS files (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id       INTEGER NOT NULL REFERENCES issues(id),
            pdf_path       TEXT    NOT NULL,
            thumbnail_path TEXT
        );
    """)
    conn.commit()
    conn.close()


def upsert_newspaper(conn, key, name, language):
    c = conn.cursor()
    c.execute("""
        INSERT INTO newspapers (key, name, language)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET name=excluded.name, language=excluded.language
    """, (key, name, language))
    conn.commit()
    c.execute("SELECT id FROM newspapers WHERE key = ?", (key,))
    return c.fetchone()[0]


def upsert_issue(conn, newspaper_id, issue_date):
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO issues (newspaper_id, issue_date)
        VALUES (?, ?)
    """, (newspaper_id, issue_date))
    conn.commit()
    c.execute("SELECT id FROM issues WHERE newspaper_id = ? AND issue_date = ?",
              (newspaper_id, issue_date))
    return c.fetchone()[0]


def upsert_file(conn, issue_id, pdf_path, thumbnail_path):
    c = conn.cursor()
    c.execute("DELETE FROM files WHERE issue_id = ?", (issue_id,))
    c.execute("""
        INSERT INTO files (issue_id, pdf_path, thumbnail_path)
        VALUES (?, ?, ?)
    """, (issue_id, pdf_path, thumbnail_path))
    conn.commit()


def save_paper(conn, key, name, language, issue_date, pdf_path, thumbnail_path):
    newspaper_id = upsert_newspaper(conn, key, name, language)
    issue_id     = upsert_issue(conn, newspaper_id, issue_date)
    upsert_file(conn, issue_id, pdf_path, thumbnail_path)
    print(f"[DB] Saved {name} for {issue_date}")


def download_pdf(input_url, date, newspaper):
    direct_pdf_url = input_url.strip()

    if '?file=' in direct_pdf_url:
        try:
            file_path      = direct_pdf_url.split('?file=')[1]
            direct_pdf_url = "https://epaper.gorkhapatraonline.com" + file_path
            print(f"Extracted direct URL for {newspaper}: {direct_pdf_url}")
        except Exception:
            print(f"Failed to extract ?file= for {newspaper}")
            return None, None
    else:
        print(f"Using direct PDF URL for {newspaper}: {direct_pdf_url}")

    headers = {
        'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Connection':      'keep-alive',
        'Referer':         'https://epaper.ekantipur.com/'
    }

    cookies = {}
    if newspaper in ["kantipur", "kathmandupost"]:
        cookies = {

        }
    elif newspaper == "nagarik":
        cookies = {

        }

    try:
        response = requests.get(direct_pdf_url, headers=headers, cookies=cookies,
                                verify=False, timeout=60, stream=True)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type:
            print(f"Non-PDF response for {newspaper} (Content-Type: {content_type})")
            return None, None
    except Exception as e:
        print(f"Failed to download PDF for {newspaper}: {e}")
        return None, None

    pdf_path = os.path.join(PAPER_PDF_DIR, f"{date}_{newspaper}.pdf")
    try:
        with open(pdf_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        print(f"Downloaded PDF: {pdf_path}")
    except Exception as e:
        print(f"Failed to save PDF for {newspaper}: {e}")
        return None, None

    thumb_path = _make_thumbnail(pdf_path, date, newspaper)
    return pdf_path, thumb_path


def _make_thumbnail(pdf_path, date, newspaper):
    thumb_path = os.path.join(PAPER_THUMB_DIR, f"{date}_{newspaper}.jpg")
    poppler_path = os.path.join(
        PAPER_BASE_DIR, "Release-25.12.0-0",
        "poppler-25.12.0", "Library", "bin"
    )
    try:
        images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=1,
                                   poppler_path=poppler_path)
        if images:
            img = images[0]
            img.thumbnail((400, 600))
            img.save(thumb_path, "JPEG", quality=85)
            print(f"Thumbnail created: {thumb_path}")
            return thumb_path
    except Exception as e:
        print(f"Thumbnail generation failed for {newspaper}: {e}")
    return None


def _make_thumbnail_from_path(pdf_path, dest_path):
    poppler_path = os.path.join(
        PAPER_BASE_DIR, "Release-25.12.0-0",
        "poppler-25.12.0", "Library", "bin"
    )
    try:
        images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=1,
                                   poppler_path=poppler_path)
        if images:
            img = images[0]
            img.thumbnail((400, 600))
            img.save(dest_path, "JPEG", quality=85)
            print(f"Thumbnail created: {dest_path}")
            return dest_path
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
    return None


def scrape_today():
    tz        = pytz.timezone('Asia/Kathmandu')
    today     = datetime.now(tz)
    today_str = today.strftime("%Y-%m-%d")

    print(f"Scraping for {today_str}...")

    init_db()
    conn = sqlite3.connect(PAPER_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = None

    try:
        for key, info in NEWSPAPERS.items():
            try:
                pdf_url      = None
                name         = info["name"]
                language     = info.get("language", "np")
                save_date_str = today_str

                if info.get("use_yesterday"):
                    save_date     = today - timedelta(days=1)
                    save_date_str = save_date.strftime("%Y-%m-%d")

                if key in ["kantipur", "kathmandupost"]:
                    y, m, d = today.strftime("%Y"), today.strftime("%m"), today.strftime("%d")
                    pdf_url = info["download_url_pattern"].format(y=y, m=m, d=d)
                    print(f"Direct download URL for {name}: {pdf_url}")

                elif key == "nagarik":
                    base_date  = tz.localize(datetime.strptime(info["base_date"], "%Y-%m-%d"))
                    days_offset = (today - base_date).days
                    epaper_id  = info["base_id"] + days_offset
                    pdf_url    = info["epaper_base_url"] + str(epaper_id)
                    print(f"Calculated Nagarik epaper ID: {epaper_id} → {pdf_url}")

                elif key == "abhiyandaily":
                    download_temp_dir = os.path.join(PAPER_BASE_DIR, "temp_downloads")
                    os.makedirs(download_temp_dir, exist_ok=True)
                    for old_file in os.listdir(download_temp_dir):
                        old_path = os.path.join(download_temp_dir, old_file)
                        if os.path.isfile(old_path):
                            os.remove(old_path)

                    chrome_opts_ab = Options()
                    chrome_opts_ab.add_argument("--no-sandbox")
                    chrome_opts_ab.add_argument("--disable-dev-shm-usage")
                    chrome_opts_ab.add_argument("--disable-gpu")
                    prefs = {
                        "download.default_directory":      download_temp_dir,
                        "download.prompt_for_download":    False,
                        "download.directory_upgrade":      True,
                        "safebrowsing.enabled":            True,
                        "plugins.always_open_pdf_externally": True,
                    }
                    chrome_opts_ab.add_experimental_option("prefs", prefs)
                    driver_ab = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                        options=chrome_opts_ab
                    )
                    try:
                        driver_ab.get(info["epaper_url"])
                        time.sleep(15)
                        driver_ab.execute_script(f"""
                            let btn = document.querySelector('{info["download_js_selector"]}');
                            if (btn) btn.click();
                        """)
                        print("Triggered Arthik Abhiyan download")

                        timeout    = 60
                        start_time = time.time()
                        downloaded_file = None
                        while time.time() - start_time < timeout:
                            files     = os.listdir(download_temp_dir)
                            pdf_files = [f for f in files if f.endswith(".pdf")]
                            if pdf_files:
                                downloaded_file = pdf_files[0]
                                break
                            time.sleep(2)

                        if downloaded_file:
                            src_path  = os.path.join(download_temp_dir, downloaded_file)
                            dest_path = os.path.join(PAPER_PDF_DIR, f"{save_date_str}_abhiyandaily.pdf")
                            if os.path.exists(dest_path):
                                os.remove(dest_path)
                            os.rename(src_path, dest_path)
                            print(f"Saved Arthik Abhiyan PDF: {dest_path}")

                            thumb_dest = os.path.join(PAPER_THUMB_DIR, f"{save_date_str}_abhiyandaily.jpg")
                            thumb_path = _make_thumbnail_from_path(dest_path, thumb_dest)
                            save_paper(conn, key, name, language, save_date_str, dest_path, thumb_path)
                        else:
                            print("Arthik Abhiyan: Download timed out")
                    except Exception as e:
                        print(f"Error with Arthik Abhiyan: {e}")
                    finally:
                        driver_ab.quit()
                    continue  # already saved — skip generic handling below

                elif key == "karobardaily":
                    if driver is None:
                        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                    driver.get(info["main_url"])
                    time.sleep(5)
                    try:
                        driver.find_element(By.CSS_SELECTOR, info["today_paper_selector"]).click()
                        time.sleep(10)
                        driver.find_element(By.CSS_SELECTOR, info["download_button_selector"]).click()
                        time.sleep(10)
                        driver.switch_to.window(driver.window_handles[-1])
                        pdf_url = driver.current_url
                        print(f"Karobar Daily PDF URL: {pdf_url}")
                    except Exception as e:
                        print(f"Selenium error for Karobar Daily: {e}")

                elif key == "souryadaily":
                    if driver is None:
                        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                    driver.get(info["main_url"])
                    time.sleep(5)
                    try:
                        driver.find_element(By.CSS_SELECTOR, info["today_paper_selector"]).click()
                        time.sleep(5)
                        driver.switch_to.window(driver.window_handles[-1])
                        pdfs = re.findall(info["pdf_pattern"], driver.page_source)
                        if pdfs:
                            pdf_url = pdfs[0]
                            print(f"Sourya Daily PDF: {pdf_url}")
                    except Exception as e:
                        print(f"Selenium error for Sourya Daily: {e}")

                elif key == "nayapatrika":
                    page_url = info["date_url_pattern"].format(
                        y=today.strftime("%Y"), m=today.strftime("%m"), d=today.strftime("%d"))
                    cookies_local = {'PHPSESSID': '25dc5220dbcc5c59ac596a8b3b2ebab9', 'STACKSCALING': 'web99j'}
                    headers_local = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0'}
                    r = requests.get(page_url, headers=headers_local, cookies=cookies_local, verify=False, timeout=30)
                    if r.status_code == 200:
                        soup     = BeautifulSoup(r.text, 'lxml')
                        link_tag = soup.select_one(info["pdf_selector"])
                        if link_tag and link_tag.get('href'):
                            pdf_url = link_tag['href']
                            if not pdf_url.startswith('http'):
                                pdf_url = "https://epaper.nayapatrikadaily.com/" + pdf_url.lstrip('/')

                elif key == "himalayatimes":
                    if driver is None:
                        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                    driver.get(info["epaper_url"])
                    time.sleep(10)
                    try:
                        driver.find_element(By.CSS_SELECTOR, info["more_button_selector"]).click()
                        time.sleep(10)
                        pdf_link = driver.find_element(By.CSS_SELECTOR, info["download_link_selector"])
                        pdf_url  = pdf_link.get_attribute("href")
                    except Exception as e:
                        print(f"Selenium error for Himalaya Times: {e}")

                elif key == "annapurnapost":
                    if driver is None:
                        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                    driver.get(info["epaper_url"])
                    time.sleep(10)
                    try:
                        for a_tag in driver.find_elements(By.CSS_SELECTOR, info["download_links_selector"]):
                            href = a_tag.get_attribute("href")
                            if href:
                                pdf_url = href
                                print(f"Annapurna Post download gateway: {pdf_url}")
                                break
                    except Exception as e:
                        print(f"Selenium error for Annapurna Post: {e}")

                elif key == "rajdhani":
                    if driver is None:
                        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                    driver.get(info["epaper_url"])
                    time.sleep(10)
                    try:
                        driver.find_element(By.CSS_SELECTOR, info["more_button_selector"]).click()
                        time.sleep(10)
                        dl_btn  = driver.find_element(By.CSS_SELECTOR, info["download_button_selector"])
                        pdf_url = dl_btn.get_attribute("href")
                        print(f"Rajdhani Daily PDF: {pdf_url}")
                    except Exception as e:
                        print(f"Selenium error for Rajdhani Daily: {e}")

                elif key == "apandainik":
                    if driver is None:
                        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                    driver.get(info["epaper_url"])
                    time.sleep(10)
                    try:
                        thumb = driver.find_element(By.CSS_SELECTOR, info["thumbnail_selector"])
                        driver.execute_script("arguments[0].scrollIntoView(true);", thumb)
                        time.sleep(1)
                        thumb.click()
                        time.sleep(10)
                        dl_btn  = driver.find_element(By.CSS_SELECTOR, info["download_button_selector"])
                        pdf_url = dl_btn.get_attribute("href")
                        print(f"Apan Dainik PDF ({save_date_str}): {pdf_url}")
                    except Exception as e:
                        print(f"Selenium error for Apan Dainik: {e}")

                elif key == "samacharpata":
                    chrome_opts_vis = Options()
                    chrome_opts_vis.add_argument("--no-sandbox")
                    chrome_opts_vis.add_argument("--disable-dev-shm-usage")
                    chrome_opts_vis.add_argument("--disable-gpu")
                    chrome_opts_vis.add_argument("--window-size=1920,1080")
                    chrome_opts_vis.set_capability("goog:loggingPrefs", {"performance": "ALL"})
                    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_opts_vis)
                    try:
                        drv.get(info["epaper_url"])
                        time.sleep(5)
                        btn = drv.find_element(By.CSS_SELECTOR, "a > div.box-shadow.epaper-img")
                        drv.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        btn.click()
                        time.sleep(10)
                        pdf_links  = set()
                        start_time = time.time()
                        while time.time() - start_time < 25:
                            for entry in drv.get_log("performance"):
                                try:
                                    msg  = json.loads(entry["message"])["message"]
                                    if msg.get("method") == "Network.responseReceived":
                                        resp = msg["params"]["response"]
                                        url  = resp.get("url", "")
                                        if resp.get("status") == 206 and url.lower().endswith(".pdf"):
                                            pdf_links.add(url)
                                except Exception:
                                    pass
                            time.sleep(1)
                        if pdf_links:
                            pdf_url = list(pdf_links)[0]
                            print(f"Samachar Patra PDF: {pdf_url}")
                    except Exception as e:
                        print(f"Selenium error for Samachar Patra: {e}")
                    finally:
                        drv.quit()

                else:
                    r = requests.get(info["list_url"], verify=False, timeout=30)
                    if r.status_code == 200:
                        soup     = BeautifulSoup(r.text, 'lxml')
                        link_tag = soup.select_one(info["selector"])
                        if link_tag and link_tag.get('href'):
                            pdf_url = link_tag['href']

                if not pdf_url:
                    print(f"No PDF URL found for {name}")
                    continue

                print(f"{name} PDF URL: {pdf_url}")
                pdf_path, thumb_path = download_pdf(pdf_url, save_date_str, key)
                if pdf_path:
                    save_paper(conn, key, name, language, save_date_str, pdf_path, thumb_path)

            except Exception as e:
                print(f"Error scraping {info.get('name', key)}: {e}")

    finally:
        if driver:
            driver.quit()
        conn.close()


if __name__ == "__main__":
    scrape_today()