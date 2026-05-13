import re
import requests
from bs4 import BeautifulSoup


def fetch_text(url: str) -> tuple[str, str]:
    """Fetch article text from a URL. Returns (title, body_text)."""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            title = _extract_title_from_html(downloaded) or _title_from_url(url)
            if text:
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


def _extract_title_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.get_text(strip=True) if soup.title else ""


def _title_from_url(url: str) -> str:
    path = url.rstrip("/").split("/")[-1]
    return re.sub(r"[-_]", " ", path).title() or "Untitled"
