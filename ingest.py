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
            if text and len(text) > 200:
                return title, text
    except Exception:
        pass

    # Fallback: requests + BeautifulSoup
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else _title_from_url(url)

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    article = soup.find("article") or soup.find("main") or soup.find("body")
    paragraphs = article.find_all("p") if article else soup.find_all("p")
    text = "\n\n".join(p.get_text(separator=" ", strip=True) for p in paragraphs if p.get_text(strip=True))

    if not text:
        raise ValueError(f"Could not extract text from {url}")

    return title, text


def _is_x_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().lstrip("www.")
    return host in ("x.com", "twitter.com")


def _fetch_x_article(url: str) -> tuple[str, str]:
    from playwright.sync_api import sync_playwright

    if not X_SESSION_FILE.exists():
        print("No X session found. Run: narrate auth-x", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(X_SESSION_FILE))
        page = ctx.new_page()

        print("  Loading X article in headless browser...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Check if we ended up on a login page
        if "login" in page.url or "i/flow/login" in page.url:
            browser.close()
            print("X session has expired. Re-run auth_x_helper.py on your laptop and SCP x_session.json over.", file=sys.stderr)
            sys.exit(1)

        # Wait for article body to render — X articles lazy-load content
        try:
            page.wait_for_selector("article, [data-testid='article'], main", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

        # Scroll through the page to trigger lazy loading of article paragraphs
        page.evaluate("""async () => {
            await new Promise(resolve => {
                let total = 0;
                const step = 800;
                const delay = 300;
                const timer = setInterval(() => {
                    window.scrollBy(0, step);
                    total += step;
                    if (total >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, delay);
            });
        }""")
        page.wait_for_timeout(2000)

        # Extract article title
        title = ""
        for selector in ["h1", "[data-testid='articleTitle']", "article h2", "main h2"]:
            el = page.query_selector(selector)
            if el:
                title = el.inner_text().strip()
                if title:
                    break
        title = title or _title_from_url(url)

        # Extract body: remove sidebar/nav then take full body text
        content = page.evaluate("""() => {
            // Remove sidebar, nav, and engagement widgets
            const noise = document.querySelectorAll(
                '[data-testid="sidebarColumn"], nav, [role="navigation"], ' +
                '[aria-label="Home timeline"], [data-testid="TopNavBar"]'
            );
            noise.forEach(el => el.remove());
            return document.body.innerText;
        }""")

        browser.close()

    if not content or len(content) < 100:
        raise ValueError("Could not extract article content from X. The article may be paywalled or the session may be expired.")

    return title, content


def auth_x():
    """Open a visible browser for the user to log into X, then save the session."""
    from playwright.sync_api import sync_playwright

    print("Opening browser — log into X, then close the browser window when done.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://x.com/login")
        input("Press Enter here once you've logged in and the feed has loaded... ")
        ctx.storage_state(path=str(X_SESSION_FILE))
        browser.close()
    print(f"Session saved to {X_SESSION_FILE}")


def _extract_title_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.get_text(strip=True) if soup.title else ""


def _title_from_url(url: str) -> str:
    path = url.rstrip("/").split("/")[-1]
    return re.sub(r"[-_]", " ", path).title() or "Untitled"
