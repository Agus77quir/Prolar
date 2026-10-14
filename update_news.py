#!/usr/bin/env python3
"""Update the site's news list from Perfil's official Politics RSS channel.
Only headlines, publication dates and links are displayed, as allowed by Perfil's RSS terms.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent

OUTPUT = ROOT / "data" / "news.json"
FEED_URLS = (
    "https://www.perfil.com/feed/politica",
    "https://www.perfil.com/feed/economia",
    "https://www.lanacion.com.ar/politica",
    "https://www.lanacion.com.ar/economia",
)
KEYWORDS = ("lacunza", "pro", "la rioja", "riojano", "riojana")
MAX_ITEMS = 12


def text_of(parent: ET.Element, name: str) -> str:
    element = parent.find(name)
    if element is None or element.text is None:
        return ""
    return re.sub(r"\s+", " ", element.text).strip()


def parse_date(raw: str) -> tuple[str, datetime]:
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), dt
    except (TypeError, ValueError, OverflowError):
        return "", datetime.min.replace(tzinfo=timezone.utc)


def main() -> int:
    entries = []
    for feed_url in FEED_URLS:
        request = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "FundacionPensarLaRiojaNews/1.0 (RSS reader)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = response.read(4_000_000)
            root = ET.fromstring(payload)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            print(f"No se pudo leer {feed_url}; se conserva el último archivo publicado: {exc}", file=sys.stderr)
            return 1
        channel = root.find("channel")
        if channel is None:
            print(f"El RSS no tiene un canal reconocible ({feed_url}); no se reemplaza el archivo publicado.", file=sys.stderr)
            return 1
        entries.extend(channel.findall("item"))

    items = []
    seen = set()
    for entry in entries:
        title = text_of(entry, "title")
        link = text_of(entry, "link")
        if not title or not link:
            continue
        if not (
            any(word in title.casefold() for word in KEYWORDS)
            or re.search(r"\bPRO\b", title, re.IGNORECASE)
        ):
            continue
            
        if not re.match(r"^https://(?:[a-z0-9-]+\.)*perfil\.com/", link, re.I):
            continue
        if link in seen:
            continue
        seen.add(link)
        published_raw = text_of(entry, "pubDate")
        published_iso, published_dt = parse_date(published_raw)
        items.append({
            "title": title,
            "url": link,
            "source": "Perfil",
            "publishedAt": published_iso,
            "publishedLabel": published_dt.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%d/%m/%Y") if published_iso else "",
        })

    items.sort(key=lambda item: item["publishedAt"], reverse=True)
    now = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    result = {
        "updatedAt": now.isoformat(timespec="seconds"),
        "updatedLabel": now.strftime("%d/%m/%Y %H:%M"),
        "source": "Perfil — canales RSS de Política y Economía",
        "items": items[:MAX_ITEMS],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Actualizado: {len(result['items'])} noticias relevantes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
