from flask import Flask, render_template, request, send_from_directory
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

PORTAL_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PORTAL_DB_PATH   = os.path.join(PORTAL_BASE_DIR, "portal_archive", "database.db")
PORTAL_THUMB_DIR = os.path.join(PORTAL_BASE_DIR, "portal_archive", "thumbnails")

PAPER_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PAPER_PDF_DIR   = os.path.join(PAPER_BASE_DIR, "paper_archive", "pdfs")
PAPER_THUMB_DIR = os.path.join(PAPER_BASE_DIR, "paper_archive", "thumbnails")
PAPER_DB_PATH   = os.path.join(PAPER_BASE_DIR, "paper_archive", "database.db")

SOCIAL_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
SOCIAL_THUMB_DIR = os.path.join(SOCIAL_BASE_DIR, "social_archive", "thumbnails")
SOCIAL_DB_PATH   = os.path.join(SOCIAL_BASE_DIR, "social_archive", "social_archive.db")

def get_paper_db():
    conn = sqlite3.connect(PAPER_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def get_social_db():
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def get_portal_db():
    conn = sqlite3.connect(PORTAL_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico', mimetype='image/vnd.microsoft.icon'
    )

@app.route('/portals/thumbnails/<path:filename>')
def serve_portal_thumbnail(filename):
    return send_from_directory(PORTAL_THUMB_DIR, filename)

@app.route('/papers/thumbnails/<path:filename>')
def serve_paper_thumbnail(filename):
    return send_from_directory(PAPER_THUMB_DIR, filename)

@app.route('/papers/pdf/<path:filename>')
def serve_paper_pdf(filename):
    return send_from_directory(PAPER_PDF_DIR, filename)

@app.route('/socials/thumbnails/<path:filename>')
def serve_social_thumbnail(filename):
    return send_from_directory(SOCIAL_THUMB_DIR, filename)


@app.route('/')
def homepage():
    return render_template('homepage.html')


@app.route('/socials')
def socials():
    conn = get_social_db()
    c    = conn.cursor()

    date_str        = request.args.get('date',     '').strip()
    platform_filter = request.args.get('platform', '').strip()

    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    platform_rows = c.execute(
        "SELECT platform_id, platform_name FROM platforms ORDER BY platform_name"
    ).fetchall()
    platforms_map = {str(r['platform_id']): r['platform_name'] for r in platform_rows}
    query = """
        SELECT
            p.platform_id,
            p.platform_name,
            ad.archive_date,
            sp.post_id,
            sp.title,
            sp.link,
            sp.created_at,
            mf.file_path
        FROM social_posts sp
        JOIN platforms     p  ON p.platform_id      = sp.platform_id
        JOIN archive_dates ad ON ad.archive_date_id  = sp.archive_date_id
        LEFT JOIN media_files mf ON mf.post_id = sp.post_id
        WHERE ad.archive_date = ?
    """
    params = [date_str]

    if platform_filter and platform_filter in platforms_map:
        query += " AND sp.platform_id = ?"
        params.append(platform_filter)

    query += " ORDER BY sp.created_at DESC"

    try:
        c.execute(query, params)
        rows = [
            dict(r) | {
                'thumb_filename': os.path.basename(r['file_path']) if r['file_path'] else None,
            }
            for r in c.fetchall()
        ]
    except Exception as e:
        rows = []
        print(f"Social query error: {e}")

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
    conn = get_paper_db()
    c    = conn.cursor()

    date_str    = request.args.get('date',  '').strip()
    lang_filter = request.args.get('lang',  '').strip()
    paper_key   = request.args.get('paper', '').strip()

    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    newspaper_rows = c.execute(
        "SELECT key, name, language FROM newspapers ORDER BY name"
    ).fetchall()
    newspapers_map = {r['key']: r['name'] for r in newspaper_rows}
    query = """
        SELECT
            n.key      AS newspaper_key,
            n.name     AS newspaper_name,
            n.language,
            i.issue_date,
            f.pdf_path,
            f.thumbnail_path
        FROM newspapers n
        JOIN issues i ON i.newspaper_id = n.id
        JOIN files  f ON f.issue_id     = i.id
        WHERE i.issue_date = ?
    """
    params = [date_str]

    if lang_filter in ('np', 'en'):
        query += " AND n.language = ?"
        params.append(lang_filter)

    if paper_key and paper_key in newspapers_map:
        query += " AND n.key = ?"
        params.append(paper_key)

    query += " ORDER BY n.name"

    try:
        c.execute(query, params)
        rows = [
            dict(r) | {
                'thumb_filename': os.path.basename(r['thumbnail_path']) if r['thumbnail_path'] else None,
                'pdf_filename':   os.path.basename(r['pdf_path']),
            }
            for r in c.fetchall()
        ]
    except Exception as e:
        rows = []
        print(f"Paper query error: {e}")

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
    conn = get_portal_db()
    c    = conn.cursor()

    search      = request.args.get('q', '').strip()
    portal_key  = request.args.get('portal', '').strip()
    date_str    = request.args.get('date', '').strip()
    lang_filter = request.args.get('lang', '').strip()  

    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    portal_rows = c.execute("""
        SELECT portal_key, portal_name, language
        FROM portals
        WHERE is_active = 1
        ORDER BY portal_name
    """).fetchall()
    portals_map = {r['portal_key']: r['portal_name'] for r in portal_rows}

    query = """
        SELECT
            hs.snapshot_id,
            hs.scrape_datetime,
            hs.thumbnail_filename,
            p.portal_key,
            p.portal_name,
            p.language,
            a.article_id,
            a.article_url,
            a.title,
            a.summary_en,
            a.keywords_en,
            a.summary_np,
            a.keywords_np
        FROM headline_snapshots hs
        JOIN portals  p ON p.portal_key = hs.portal_key
        JOIN articles a ON a.article_id = hs.article_id
        WHERE DATE(hs.scrape_datetime) = ?
    """
    params = [date_str]

    if portal_key and portal_key in portals_map:
        query += " AND hs.portal_key = ?"
        params.append(portal_key)

    if lang_filter in ('np', 'en'):
        query += " AND p.language = ?"
        params.append(lang_filter)

    if search:
        like = f"%{search}%"
        query += """
            AND (
                a.title       LIKE ? OR
                a.summary_en  LIKE ? OR
                a.keywords_en LIKE ? OR
                a.summary_np  LIKE ? OR
                a.keywords_np LIKE ? OR
                a.article_url LIKE ?
            )
        """
        params.extend([like, like, like, like, like, like])

    query += " ORDER BY hs.scrape_datetime DESC"

    try:
        c.execute(query, params)
        rows = [dict(r) for r in c.fetchall()]
    except Exception as e:
        rows = []
        print(f"Query error: {e}")

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



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')