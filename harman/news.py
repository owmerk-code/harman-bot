"""RSS haber okuyucu (Cointelegraph, Decrypt, The Block, Fed, SEC). Yalnız başlık ve zaman alınır."""
from __future__ import annotations

import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

FEEDS = [("Cointelegraph", "https://cointelegraph.com/rss"), ("Decrypt", "https://decrypt.co/feed"),
         ("The Block", "https://www.theblock.co/rss.xml"),
         ("Fed", "https://www.federalreserve.gov/feeds/press_all.xml"),
         ("SEC", "https://www.sec.gov/news/pressreleases.rss")]
MAX_BYTES = 3_000_000


def _time(value: str) -> datetime:
    text = (value or "").strip()
    for parse in (lambda t: datetime.fromisoformat(t.replace("Z", "+00:00")), parsedate_to_datetime):
        try:
            parsed = parse(text)
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
    return datetime.now(timezone.utc)


def parse_feed(name: str, data: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(data)
    out = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
            continue
        fields: dict[str, str] = {}
        for child in node.iter():
            local = child.tag.rsplit("}", 1)[-1].lower()
            if child.text and local not in fields:
                fields[local] = child.text.strip()
        title = fields.get("title", "")
        if not title:
            continue
        when = _time(fields.get("pubdate") or fields.get("published") or fields.get("updated") or fields.get("date", ""))
        ident = fields.get("guid") or fields.get("id") or hashlib.sha256(title.encode()).hexdigest()
        out.append({"id": ident[:300], "ms": int(when.timestamp() * 1000), "t": f"[{name}] {title[:300]}"})
    return out[:100]


def fetch(name: str, url: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": "harman-bot/1",
                                               "Accept": "application/rss+xml, application/atom+xml, text/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("haber cevabi cok buyuk")
    return parse_feed(name, data)
