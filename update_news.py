#!/usr/bin/env python3
"""Update the site with relevant headlines and source links only."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "news.json"
TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
MAX_ITEMS = 5

# Perfil y Clarín publican feeds RSS de Política/Economía. Solo se guardan
# titulares, fechas y enlaces originales.
RSS_FEEDS = (
    {
        "source": "Perfil",
        "url": "https://www.perfil.com/feed/politica",
        "domains": ("perfil.com",),
    },
    {
        "source": "Perfil",
        "url": "https://www.perfil.com/feed/economia",
        "domains": ("perfil.com",),
    },
    {
        "source": "Clarín",
        "url": "https://www.clarin.com/rss/politica/",
        "domains": ("clarin.com",),
    },
)

# Estos medios riojanos no anuncian un RSS utilizable. Se consultan sus páginas
# públicas de portada una vez al día y solo se extraen titulares y enlaces.
HTML_SOURCES = (
    {
        "source": "Nueva Rioja",
        "url": "https://nuevarioja.com.ar/",
        "domains": ("nuevarioja.com.ar",),
        "kind": "nueva-rioja",
    },
    {
        "source": "El Independiente",
        "url": "https://www.elindependiente.com.ar/",
        "domains": ("elindependiente.com.ar",),
        "kind": "independiente",
    },
)

KEYWORDS = ("lacunza", "macri", "la rioja", "riojano", "riojana")
PRO_PATTERN = re.compile(r"\bPRO\b", re.IGNORECASE)
HEADINGS = {"h1", "h2", "h3", "h4"}
LOCAL_SOURCES = {"Nueva Rioja", "El Independiente"}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def text_of(parent: ET.Element, name: str) -> str:
    element = parent.find(name)
    if element is None or element.text is None:
        return ""
    return clean_text(element.text)


def parse_date(raw: str) -> tuple[str, datetime | None]:
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), dt
    except (TypeError, ValueError, OverflowError):
        return "", None


def is_allowed_link(link: str, domains: tuple[str, ...]) -> bool:
    try:
        host = (urlparse(link).hostname or "").lower()
    except ValueError:
        return False
    return link.startswith("https://") and any(
        host == domain or host.endswith("." + domain) for domain in domains
    )


def matches_topic(title: str, source: str) -> bool:
    folded = title.casefold()
    party_or_people = bool(PRO_PATTERN.search(title)) or any(
        word in folded for word in ("lacunza", "macri")
    )
    if party_or_people:
        return True

    # En los medios locales, evita traer noticias sin relación solo porque
    # mencionan La Rioja.
    if source in LOCAL_SOURCES:
        return False

    return any(word in folded for word in ("la rioja", "riojano", "riojana"))


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PROLaRiojaNews/1.0 (headlines and source links)"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read(8_000_000)


def rss_items(feed: dict) -> list[dict]:
    root = ET.fromstring(fetch(feed["url"]))
    channel = root.find("channel")
    if channel is None:
        raise ValueError("el RSS no tiene un canal reconocible")

    result = []
    for entry in channel.findall("item"):
        title = text_of(entry, "title")
        link = text_of(entry, "link")
        if not title or not link or not is_allowed_link(link, feed["domains"]):
            continue
        if not matches_topic(title, feed["source"]):
            continue

        published_iso, published_dt = parse_date(text_of(entry, "pubDate"))
        result.append({
            "title": title,
            "url": link,
            "source": feed["source"],
            "publishedAt": published_iso,
            "publishedLabel": (
                published_dt.astimezone(TIMEZONE).strftime("%d/%m/%Y")
                if published_dt else ""
            ),
            "_sort": published_dt.timestamp() if published_dt else 0.0,
        })
    return result


class ArticleLinkParser(HTMLParser):
    """Collect headline text from article links without storing article bodies."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self.current_href: str | None = None
        self.fallback: list[str] = []
        self.heading: list[str] = []
        self.heading_depth = 0
        self.has_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and self.current_href is None:
            href = attrs_dict.get("href")
            if href:
                self.current_href = urljoin(self.base_url, href.strip())
                self.fallback = []
                self.heading = []
                self.heading_depth = 0
                self.has_heading = False
            return

        if self.current_href is None:
            return

        if tag in HEADINGS:
            if not self.has_heading:
                self.heading = []
                self.has_heading = True
            self.heading_depth += 1
        elif tag == "img":
            alt = attrs_dict.get("alt") or ""
            if alt:
                target = self.heading if self.heading_depth else self.fallback
                target.append(alt)
        elif tag in {"br", "p", "div"}:
            target = self.heading if self.heading_depth else self.fallback
            target.append(" ")

    def handle_data(self, data: str) -> None:
        if self.current_href is None:
            return
        target = self.heading if self.heading_depth else self.fallback
        target.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current_href is None:
            return

        if tag in HEADINGS and self.heading_depth:
            self.heading_depth -= 1
        elif tag == "a":
            parts = self.heading if self.has_heading else self.fallback
            title = clean_text(" ".join(parts))
            if title:
                self.links.append((self.current_href, title))

            self.current_href = None
            self.fallback = []
            self.heading = []
            self.heading_depth = 0
            self.has_heading = False


def is_article_page(source: dict, link: str) -> bool:
    parsed = urlparse(link)
    if not is_allowed_link(link, source["domains"]):
        return False

    if source["kind"] == "nueva-rioja":
        return parsed.path.lower().endswith(".htm")

    if source["kind"] == "independiente":
        return (
            parsed.path.lower().endswith("/pagina.php")
            and bool(parse_qs(parsed.query).get("id"))
        )

    return False


def html_items(source: dict, observed_at: datetime) -> list[dict]:
    payload = fetch(source["url"]).decode("utf-8", errors="replace")
    parser = ArticleLinkParser(source["url"])
    parser.feed(payload)

    result = []
    seen = set()
    for link, title in parser.links:
        if link in seen or not is_article_page(source, link):
            continue
        if not matches_topic(title, source["source"]):
            continue

        seen.add(link)
        result.append({
            "title": title,
            "url": link,
            "source": source["source"],
            "publishedAt": "",
            "publishedLabel": "",
            # Se usa para ordenar, no se muestra como fecha de publicación.
            "_sort": observed_at.timestamp(),
        })

    return result


def main() -> int:
    all_items: list[dict] = []
    successful_sources: list[str] = []
    now = datetime.now(TIMEZONE)

    for feed in RSS_FEEDS:
        try:
            all_items.extend(rss_items(feed))
            if feed["source"] not in successful_sources:
                successful_sources.append(feed["source"])
        except (
            urllib.error.URLError,
            TimeoutError,
            ET.ParseError,
            OSError,
            ValueError,
        ) as exc:
            print(
                f"No se pudo leer el RSS de {feed['source']}; "
                f"continúo con las otras fuentes: {exc}",
                file=sys.stderr,
            )

    for source in HTML_SOURCES:
        try:
            all_items.extend(html_items(source, now))
            if source["source"] not in successful_sources:
                successful_sources.append(source["source"])
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            UnicodeError,
            ValueError,
        ) as exc:
            print(
                f"No se pudo consultar {source['source']}; "
                f"continúo con las otras fuentes: {exc}",
                file=sys.stderr,
            )

    if not successful_sources:
        print(
            "No se pudo consultar ninguna fuente; "
            "se conserva el último archivo publicado.",
            file=sys.stderr,
        )
        return 1

    deduplicated = {}
    for item in all_items:
        deduplicated.setdefault(item["url"], item)

    items = sorted(
        deduplicated.values(),
        key=lambda item: item["_sort"],
        reverse=True,
    )[:MAX_ITEMS]

    for item in items:
        item.pop("_sort", None)

    result = {
        "updatedAt": now.isoformat(timespec="seconds"),
        "updatedLabel": now.strftime("%d/%m/%Y %H:%M"),
        "source": ", ".join(successful_sources) + " — titulares y enlaces",
        "items": items,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Actualizado: {len(items)} titulares; "
        f"fuentes consultadas: {', '.join(successful_sources)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    
