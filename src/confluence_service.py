from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MAX_PAGES_PER_PR = 5

# Matches Confluence page URLs (view by pageId or space/title paths)
_CONFLUENCE_URL_RE = re.compile(
    r"https?://[^\s/]+/wiki/(?:spaces/[^/\s]+/pages/\d+[^\s]*"
    r"|pages/viewpage\.action\?pageId=\d+"
    r"|display/[^/\s]+/[^\s]+)",
    re.IGNORECASE,
)

# Extracts page ID from Confluence URLs
_PAGE_ID_RE = re.compile(r"pageId=(\d+)|/pages/(\d+)")


@dataclass
class ConfluencePage:
    page_id: str
    title: str
    content: str  # plain text, HTML stripped


class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-text converter using stdlib html.parser."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


class ConfluenceService:
    """Fetches Confluence pages linked to a Jira ticket.

    Gracefully disabled when credentials are absent — all methods return
    empty results without raising exceptions.
    """

    def __init__(self, base_url: str = "", token: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._enabled = bool(base_url and token)
        if not self._enabled:
            logger.debug("ConfluenceService: credentials absent — fetching disabled")

    def is_available(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pages_for_ticket(
        self,
        ticket_key: str,
        description: str = "",
    ) -> list[ConfluencePage]:
        """Return Confluence pages linked to a Jira ticket.

        Discovery order:
        1. Jira remoteLinks API (structured links)
        2. URL extraction from ticket description (fallback)

        At most MAX_PAGES_PER_PR pages are fetched.
        """
        if not self._enabled:
            return []

        page_ids: list[str] = []

        # Primary: Jira remoteLinks
        jira_base = self._base_url.replace("/wiki", "")
        try:
            resp = requests.get(
                f"{jira_base}/rest/api/3/issue/{ticket_key}/remotelink",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                for link in resp.json():
                    url = (link.get("object") or {}).get("url", "")
                    pid = self._extract_page_id(url)
                    if pid and pid not in page_ids:
                        page_ids.append(pid)
        except Exception as exc:
            logger.warning("ConfluenceService: remoteLinks fetch failed for %s: %s", ticket_key, exc)

        # Fallback: URLs embedded in description text
        if not page_ids and description:
            for url in _CONFLUENCE_URL_RE.findall(description):
                pid = self._extract_page_id(url)
                if pid and pid not in page_ids:
                    page_ids.append(pid)

        if len(page_ids) > MAX_PAGES_PER_PR:
            logger.debug(
                "ConfluenceService: %d pages found for %s, limiting to %d",
                len(page_ids), ticket_key, MAX_PAGES_PER_PR,
            )
            page_ids = page_ids[:MAX_PAGES_PER_PR]

        pages: list[ConfluencePage] = []
        for pid in page_ids:
            page = self.get_page_content(pid)
            if page:
                pages.append(page)
        return pages

    def get_page_content(self, page_id: str) -> Optional[ConfluencePage]:
        """Fetch and return a Confluence page as plain text, or None on failure."""
        if not self._enabled:
            return None
        try:
            resp = requests.get(
                f"{self._base_url}/rest/api/content/{page_id}",
                params={"expand": "body.storage"},
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code in (403, 404):
                logger.warning(
                    "ConfluenceService: page %s returned %d — skipping",
                    page_id, resp.status_code,
                )
                return None
            resp.raise_for_status()
            data = resp.json()
            title = data.get("title", f"Page {page_id}")
            html = (data.get("body") or {}).get("storage", {}).get("value", "")
            return ConfluencePage(page_id=page_id, title=title, content=_strip_html(html))
        except Exception as exc:
            logger.warning("ConfluenceService: failed to fetch page %s: %s", page_id, exc)
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    def _extract_page_id(self, url: str) -> Optional[str]:
        m = _PAGE_ID_RE.search(url)
        if m:
            return m.group(1) or m.group(2)
        return None


# ---------------------------------------------------------------------------
# Context assembly (task 4.1)
# ---------------------------------------------------------------------------

def build_confluence_context(pages: list[ConfluencePage], budget: int = 6000) -> str:
    """Concatenate page content within a character budget, truncating as needed.

    Pages are consumed in priority order (first = highest priority).
    Each page that exceeds the remaining budget is cut and tagged [truncated].
    Returns empty string when pages is empty.
    """
    if not pages:
        return ""

    parts: list[str] = []
    remaining = budget

    for page in pages:
        if remaining <= 0:
            break
        content = page.content
        if len(content) > remaining:
            content = content[:remaining] + " [truncated]"
        parts.append(f"### {page.title}\n{content}")
        remaining -= len(content)

    return "\n\n".join(parts)
