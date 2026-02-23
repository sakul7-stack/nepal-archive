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