import re
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from config import X_SESSION_FILE


def fetch_text(url: str) -> tuple[str, str]:
    """Fetch article text from a URL. Returns (title, body_text)."""
    if _is_x_url(url):
        return _fetch_x_article(url)

    # Try trafilatura for static pages
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            title = _extract_title_from_html(downloaded) or _title_from_url(url)
            if text and len(text) > 500:
                return title, text
    except Exception:
        pass

    # Fallback: requests + BeautifulSoup
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else _title_from_url(url)
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.find("body")
        paragraphs = article.find_all("p") if article else soup.find_all("p")
        text = "\n\n".join(p.get_text(separator=" ", strip=True) for p in paragraphs if p.get_text(strip=True))
        if text and len(text) > 500:
            return title, text
    except Exception:
        pass

    # Final fallback: headless browser for JS-rendered pages
    print("  Static fetch returned too little content — trying headless browser...")
    return _fetch_with_browser(url)


def _is_x_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().lstrip("www.")
    return host in ("x.com", "twitter.com")


def _fetch_with_browser(url: str, session_file=None) -> tuple[str, str]:
    """Fetch a URL using headless Chromium. Optionally load a saved session."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs = {"storage_state": str(session_file)} if session_file else {}
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            page.wait_for_selector("article, main, [role='main']", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

        # Scroll to trigger lazy-loaded content
        page.evaluate("""async () => {
            await new Promise(resolve => {
                let total = 0;
                const timer = setInterval(() => {
                    window.scrollBy(0, 800);
                    total += 800;
                    if (total >= document.body.scrollHeight) { clearInterval(timer); resolve(); }
                }, 300);
            });
        }""")
        page.wait_for_timeout(1500)

        title = ""
        for selector in ["h1", "article h2", "main h2"]:
            el = page.query_selector(selector)
            if el:
                title = el.inner_text().strip()
                if title:
                    break
        title = title or page.title() or _title_from_url(url)

        content = page.evaluate("""() => {
            document.querySelectorAll('nav, [role="navigation"], header, footer, aside').forEach(el => el.remove());
            return document.body.innerText;
        }""")

        browser.close()

    if not content or len(content) < 100:
        raise ValueError(f"Headless browser could not extract content from {url}")

    return title, content


def _fetch_x_article(url: str) -> tuple[str, str]:
    if not X_SESSION_FILE.exists():
        print("No X session found. Run auth_x_helper.py on your laptop and SCP x_session.json here.", file=sys.stderr)
        sys.exit(1)

    print("  Loading X article in headless browser...")
    title, content = _fetch_with_browser(url, session_file=X_SESSION_FILE)

    # Detect expired session — X redirects to login
    if "sign in" in content[:200].lower() or "log in" in content[:200].lower():
        print("X session has expired. Re-run auth_x_helper.py on your laptop and SCP x_session.json over.", file=sys.stderr)
        sys.exit(1)

    # Strip X UI chrome from the top (keyboard shortcuts notice, engagement counts)
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if any(x in line for x in ["·", "@", "Follow", "Repost", "Like"]):
            continue
        if len(line.strip()) > 60:
            content = "\n".join(lines[i:])
            break

    return title, content


def check_x_session():
    """Report the expiry status of the saved X session."""
    import json
    from datetime import datetime, timezone

    if not X_SESSION_FILE.exists():
        print("No X session found. Run auth_x_helper.py on your laptop and SCP x_session.json here.")
        return

    data = json.loads(X_SESSION_FILE.read_text())
    cookies = {c["name"]: c for c in data.get("cookies", [])}

    auth = cookies.get("auth_token")
    if not auth:
        print("x_session.json exists but has no auth_token cookie — session is invalid.")
        return

    expires = auth.get("expires", -1)
    if expires == -1 or expires is None:
        print("X session: auth_token is a session cookie (no fixed expiry).")
        return

    exp_dt = datetime.fromtimestamp(expires, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    days_left = (exp_dt - now).days

    if days_left < 0:
        print(f"X session EXPIRED {abs(days_left)} days ago. Re-run auth_x_helper.py on your laptop.")
    elif days_left < 7:
        print(f"X session expires in {days_left} day(s) — refresh soon.")
    else:
        print(f"X session valid for {days_left} more days (expires {exp_dt.strftime('%Y-%m-%d')}).")


def _extract_title_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.get_text(strip=True) if soup.title else ""


def _title_from_url(url: str) -> str:
    path = url.rstrip("/").split("/")[-1]
    return re.sub(r"[-_]", " ", path).title() or "Untitled"
