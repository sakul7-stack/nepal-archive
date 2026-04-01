from flask import Flask, render_template, request, send_from_directory
import sqlite3
from datetime import datetime, timedelta
import os
from collections import defaultdict
import re
from markupsafe import escape
from werkzeug.utils import secure_filename

app = Flask(__name__)


app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PORTAL_DB_PATH   = os.path.join(BASE_DIR, "portal_archive", "database.db")
PORTAL_THUMB_DIR = os.path.join(BASE_DIR, "portal_archive", "thumbnails")

PAPER_PDF_DIR   = os.path.join(BASE_DIR, "paper_archive", "pdfs")
PAPER_THUMB_DIR = os.path.join(BASE_DIR, "paper_archive", "thumbnails")
PAPER_DB_PATH   = os.path.join(BASE_DIR, "paper_archive", "database.db")

SOCIAL_THUMB_DIR = os.path.join(BASE_DIR, "social_archive", "thumbnails")
SOCIAL_DB_PATH   = os.path.join(BASE_DIR, "social_archive", "social_archive.db")



def validate_date(date_str):
    if re.match(r'^\d{4}-\d{2}-\d{2}$', str(date_str)):
        return date_str
    return None

def sanitize_search(text):
    text = (text or "").strip()
    if len(text) > 100:
        return ""
    return re.sub(r'[^\w\s\-.,]', '', text)

def validate_choice(value, allowed):
    return value if value in allowed else ""

def get_db(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/papers/pdf/<path:filename>')
def serve_paper_pdf(filename):
    return send_from_directory(PAPER_PDF_DIR, secure_filename(filename))

@app.route('/papers/thumbnails/<path:filename>')
def serve_paper_thumbnail(filename):
    return send_from_directory(PAPER_THUMB_DIR, secure_filename(filename))

@app.route('/portals/thumbnails/<path:filename>')
def serve_portal_thumbnail(filename):
    return send_from_directory(PORTAL_THUMB_DIR, secure_filename(filename))

@app.route('/socials/thumbnails/<path:filename>')
def serve_social_thumbnail(filename):
    return send_from_directory(SOCIAL_THUMB_DIR, secure_filename(filename))


@app.route('/')
def homepage():
    today = datetime.now().strftime('%Y-%m-%d')
    current_year = datetime.now().year

    try:
        requested_year = int(request.args.get('year', current_year))
        if requested_year < 2000 or requested_year > current_year + 1:
            requested_year = current_year
    except:
        requested_year = current_year

    archive_info = defaultdict(dict)

    try:
        conn = get_db(SOCIAL_DB_PATH)
        rows = conn.execute(
            "SELECT DISTINCT archive_date FROM archive_dates WHERE archive_date LIKE ?",
            (f"{requested_year}%",)
        ).fetchall()
        for r in rows:
            archive_info[r[0]]['social'] = True
        conn.close()
    except:
        pass


    try:
        conn = get_db(PORTAL_DB_PATH)
        rows = conn.execute(
            "SELECT DISTINCT DATE(scrape_datetime) FROM headline_snapshots WHERE DATE(scrape_datetime) LIKE ?",
            (f"{requested_year}%",)
        ).fetchall()
        for r in rows:
            archive_info[r[0]]['portal'] = True
        conn.close()
    except:
        pass

    try:
        conn = get_db(PAPER_DB_PATH)
        rows = conn.execute(
            "SELECT DISTINCT issue_date FROM issues WHERE issue_date LIKE ?",
            (f"{requested_year}%",)
        ).fetchall()
        for r in rows:
            archive_info[r[0]]['paper'] = True
        conn.close()
    except:
        pass

    return render_template(
        'homepage.html',
        today=today,
        selected_year=requested_year,
        current_year=current_year,
        archive_data=archive_info
    )



@app.route('/socials')
def socials():
    conn = get_db(SOCIAL_DB_PATH)
    c = conn.cursor()

    date_str = validate_date(request.args.get('date', ''))
    if not date_str:
        row=c.execute('SELECT MAX(archive_date) as max_date FROM archive_dates').fetchone()
        date_str=row['max_date']
              

    platform_rows = c.execute(
        "SELECT platform_id, platform_name FROM platforms"
    ).fetchall()

    platforms_map = {str(r['platform_id']): r['platform_name'] for r in platform_rows}

    platform_filter = validate_choice(request.args.get('platform', ''), platforms_map)

    query = """
        SELECT p.platform_id, p.platform_name, ad.archive_date,
               sp.post_id, sp.title, sp.link, sp.created_at, mf.file_path
        FROM social_posts sp
        JOIN platforms p ON p.platform_id = sp.platform_id
        JOIN archive_dates ad ON ad.archive_date_id = sp.archive_date_id
        LEFT JOIN media_files mf ON mf.post_id = sp.post_id
        WHERE ad.archive_date = ?
    """
    params = [date_str]

    if platform_filter:
        query += " AND sp.platform_id = ?"
        params.append(platform_filter)

    query += " ORDER BY sp.created_at DESC"

    rows = []
    try:
        c.execute(query, params)
        rows = [
            {
                **dict(r),
                "title": escape(r["title"]),
                "thumb_filename": os.path.basename(r["file_path"]) if r["file_path"] else None
            }
            for r in c.fetchall()
        ]
    except Exception as e:
        print("Social error:", e)

    conn.close()

    return render_template(
        'social_homepage.html',
        rows=rows,
        platforms=platforms_map,
        selected_date=date_str,
        selected_platform=platform_filter,
        today=datetime.now().strftime("%Y-%m-%d"),
    )

@app.route('/papers')
def papers():
    conn = get_db(PAPER_DB_PATH)
    c = conn.cursor()

    date_str = validate_date(request.args.get('date', ''))

    if not date_str:
        row = c.execute("SELECT MAX(issue_date) as max_date FROM issues").fetchone()
        date_str = row["max_date"]

    newspaper_rows = c.execute(
        "SELECT key, name, language FROM newspapers"
    ).fetchall()

    newspapers_map = {r['key']: r['name'] for r in newspaper_rows}

    lang_filter = validate_choice(request.args.get('lang', ''), ['np', 'en'])
    paper_key   = validate_choice(request.args.get('paper', ''), newspapers_map)

    query = """
        SELECT n.key, n.name, n.language, i.issue_date,
               f.pdf_path, f.thumbnail_path
        FROM newspapers n
        JOIN issues i ON i.newspaper_id = n.id
        JOIN files f ON f.issue_id = i.id
        WHERE i.issue_date = ?
    """
    params = [date_str]

    if lang_filter:
        query += " AND n.language = ?"
        params.append(lang_filter)

    if paper_key:
        query += " AND n.key = ?"
        params.append(paper_key)

    rows = []
    try:
        c.execute(query, params)
        rows = [
            {
                **dict(r),
                "thumb_filename": os.path.basename(r["thumbnail_path"]) if r["thumbnail_path"] else None,
                "pdf_filename": os.path.basename(r["pdf_path"])
            }
            for r in c.fetchall()
        ]
    except Exception as e:
        print("Paper error:", e)

    conn.close()

    return render_template(
        'paper_homepage.html',
        rows=rows,
        newspapers=newspapers_map,
        selected_date=date_str,
        selected_lang=lang_filter,
        selected_paper=paper_key,
        today=datetime.now().strftime("%Y-%m-%d"),
    )


@app.route('/portals')
def portals():
    conn = get_db(PORTAL_DB_PATH)
    c = conn.cursor()

    search = sanitize_search(request.args.get('q', ''))
    date_str = validate_date(request.args.get('date', ''))

    if not date_str:
        row = c.execute("SELECT MAX(DATE(scrape_datetime)) as max_date FROM headline_snapshots").fetchone()
        date_str = row["max_date"]

    portal_rows = c.execute(
        "SELECT portal_key, portal_name FROM portals WHERE is_active = 1"
    ).fetchall()

    portals_map = {r['portal_key']: r['portal_name'] for r in portal_rows}

    portal_key  = validate_choice(request.args.get('portal', ''), portals_map)
    lang_filter = validate_choice(request.args.get('lang', ''), ['np', 'en'])

    query = """
        SELECT hs.snapshot_id, hs.scrape_datetime, hs.thumbnail_filename,
               p.portal_key, p.portal_name, p.language,
               a.article_id, a.article_url, a.title,
               a.summary_en, a.summary_np,
	       a.keywords_en, a.keywords_np
        FROM headline_snapshots hs
        JOIN portals p ON p.portal_key = hs.portal_key
        JOIN articles a ON a.article_id = hs.article_id
        WHERE DATE(hs.scrape_datetime) = ?
    """
    params = [date_str]

    if portal_key:
        query += " AND hs.portal_key = ?"
        params.append(portal_key)

    if lang_filter:
        query += " AND p.language = ?"
        params.append(lang_filter)

    if search:
        like = f"%{search}%"
        query += " AND (a.title LIKE ? OR a.summary_en LIKE ? OR a.summary_np LIKE ?)"
        params.extend([like, like, like])

    query += " ORDER BY hs.scrape_datetime DESC"

    rows = []
    try:
        c.execute(query, params)
        rows = [
            {
                **dict(r),
                "title": escape(r["title"]),
                "summary_en": escape(r["summary_en"]) if r["summary_en"] else "",
                "summary_np": escape(r["summary_np"]) if r["summary_np"] else "",
                "keywords_en": escape(r["keywords_en"]) if r["keywords_en"] else "",
                "keywords_np": escape(r["keywords_np"]) if r["keywords_np"] else ""
            }
            for r in c.fetchall()
        ]
    except Exception as e:
        print("Portal error:", e)

    conn.close()

    return render_template(
        'portal_homepage.html',
        rows=rows,
        portals=portals_map,
        selected_date=date_str,
        selected_portal=portal_key,
        selected_lang=lang_filter,
        search_query=search,
        today=datetime.now().strftime("%Y-%m-%d"),
    )

"""
Add this route to your existing app.py
Also add 'search' to your nav links in all templates.
"""
@app.route('/search')
def search():
    from math import ceil
    import unicodedata


    raw_q     = request.args.get('q', '').strip()
    q         = sanitize_search(raw_q)
    date_from = validate_date(request.args.get('from', ''))
    date_to   = validate_date(request.args.get('to',   ''))

    raw_sources     = request.args.getlist('source')
    allowed_sources = {'papers', 'portals', 'socials'}
    sources = [s for s in raw_sources if s in allowed_sources] or list(allowed_sources)

    try:    page_papers  = max(1, int(request.args.get('pp', 1)))
    except: page_papers  = 1
    try:    page_portals = max(1, int(request.args.get('po', 1)))
    except: page_portals = 1
    try:    page_socials = max(1, int(request.args.get('ps', 1)))
    except: page_socials = 1

    PER_PAGE = 12

    paper_results  = []
    portal_results = []
    social_results = []

    searched = bool(q or date_from or date_to)

    if searched:

        def date_clause(col):
            parts, vals = [], []
            if date_from:
                parts.append(f"{col} >= ?")
                vals.append(date_from)
            if date_to:
                parts.append(f"{col} <= ?")
                vals.append(date_to)
            return (" AND " + " AND ".join(parts)) if parts else "", vals

        like = f"%{q}%" if q else None


        if 'papers' in sources:
            try:
                conn = get_db(PAPER_DB_PATH)
                dc, dv = date_clause("i.issue_date")
                qc = " AND (n.name LIKE ?)" if like else ""
                qv = [like] if like else []
                sql = f"""
                    SELECT
                        n.name           AS title,
                        n.language       AS language,
                        n.name           AS source_name,
                        i.issue_date     AS result_date,
                        f.thumbnail_path AS thumb_path,
                        f.pdf_path       AS pdf_path
                    FROM newspapers n
                    JOIN issues i ON i.newspaper_id = n.id
                    JOIN files   f ON f.issue_id    = i.id
                    WHERE 1=1 {dc} {qc}
                    ORDER BY i.issue_date DESC
                """
                rows = conn.execute(sql, dv + qv).fetchall()
                for r in rows:
                    d = dict(r)
                    d['thumb_filename'] = os.path.basename(d['thumb_path']) if d.get('thumb_path') else None
                    d['pdf_filename']   = os.path.basename(d['pdf_path'])   if d.get('pdf_path')   else None
                    d['title']          = str(escape(d.get('title') or ''))
                    paper_results.append(d)
                conn.close()
            except Exception as e:
                print("Search papers error:", e)

        if 'portals' in sources:
            try:
                conn = get_db(PORTAL_DB_PATH)
                dc, dv = date_clause("DATE(hs.scrape_datetime)")
                qc = " AND (a.title LIKE ? OR a.summary_en LIKE ? OR a.summary_np LIKE ?)" if like else ""
                qv = [like, like, like] if like else []
                sql = f"""
                    SELECT
                        a.title                  AS title,
                        a.summary_en             AS summary_en,
                        a.summary_np             AS summary_np,
                        a.article_url            AS url,
                        p.language               AS language,
                        p.portal_name            AS source_name,
                        DATE(hs.scrape_datetime) AS result_date,
                        hs.scrape_datetime       AS scrape_datetime,
                        hs.thumbnail_filename    AS thumb_filename
                    FROM headline_snapshots hs
                    JOIN portals  p ON p.portal_key = hs.portal_key
                    JOIN articles a ON a.article_id = hs.article_id
                    WHERE p.is_active = 1 {dc} {qc}
                    ORDER BY hs.scrape_datetime DESC
                """
                rows = conn.execute(sql, dv + qv).fetchall()
                for r in rows:
                    d = dict(r)
                    d['title']      = str(escape(d.get('title')      or ''))
                    d['summary_en'] = str(escape(d.get('summary_en') or ''))
                    d['summary_np'] = str(escape(d.get('summary_np') or ''))
                    portal_results.append(d)
                conn.close()
            except Exception as e:
                print("Search portals error:", e)

        if 'socials' in sources:
            try:
                conn = get_db(SOCIAL_DB_PATH)
                dc, dv = date_clause("ad.archive_date")
                qc = " AND (sp.title LIKE ?)" if like else ""
                qv = [like] if like else []
                sql = f"""
                    SELECT
                        sp.title             AS title,
                        sp.link              AS url,
                        p.platform_name      AS source_name,
                        ad.archive_date      AS result_date,
                        mf.file_path         AS thumb_path
                    FROM social_posts sp
                    JOIN platforms     p  ON p.platform_id        = sp.platform_id
                    JOIN archive_dates ad ON ad.archive_date_id   = sp.archive_date_id
                    LEFT JOIN media_files mf ON mf.post_id        = sp.post_id
                    WHERE 1=1 {dc} {qc}
                    ORDER BY ad.archive_date DESC, sp.created_at DESC
                """
                rows = conn.execute(sql, dv + qv).fetchall()
                for r in rows:
                    d = dict(r)
                    d['thumb_filename'] = os.path.basename(d['thumb_path']) if d.get('thumb_path') else None
                    d['title']          = str(escape(d.get('title') or ''))
                    social_results.append(d)
                conn.close()
            except Exception as e:
                print("Search socials error:", e)

    def paginate(items, page, per_page):
        total       = len(items)
        total_pages = ceil(total / per_page) if total else 1
        page        = min(max(1, page), total_pages)
        offset      = (page - 1) * per_page
        return items[offset:offset + per_page], total, total_pages, page

    paper_page,  paper_total,  paper_pages,  page_papers  = paginate(paper_results,  page_papers,  PER_PAGE)
    portal_page, portal_total, portal_pages, page_portals = paginate(portal_results, page_portals, PER_PAGE)
    social_page, social_total, social_pages, page_socials = paginate(social_results, page_socials, PER_PAGE)

    has_nepali = False
    if raw_q:
        try:
            has_nepali = any(
                '\u0900' <= c <= '\u097F' for c in raw_q
            )
        except Exception:
            has_nepali = False

    return render_template(
        'search.html',
        paper_results  = paper_page,
        paper_total    = paper_total,
        paper_pages    = paper_pages,
        page_papers    = page_papers,
        portal_results = portal_page,
        portal_total   = portal_total,
        portal_pages   = portal_pages,
        page_portals   = page_portals,
        social_results = social_page,
        social_total   = social_total,
        social_pages   = social_pages,
        page_socials   = page_socials,
        searched       = searched,
        search_query   = raw_q,
        date_from      = date_from or '',
        date_to        = date_to   or '',
        selected_sources = sources,
        has_nepali     = has_nepali,
        today          = datetime.now().strftime('%Y-%m-%d'),
    )

@app.errorhandler(Exception)
def handle_error(e):
    print("Error:", e)
    return "Internal Server Error", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=False)
