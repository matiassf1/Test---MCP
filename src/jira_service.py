from __future__ import annotations

import re
from typing import Optional

from src.config import settings
from src.models import JiraIssue

# Jira ticket pattern, e.g. PAY-212, PROJ-1234
_TICKET_PATTERN = re.compile(r"\b([A-Z]+-\d+)\b")


def _normalize_description(desc: object, max_len: int = 2000) -> Optional[str]:
    """Strip HTML and truncate description for use in docs/prompts. Shared by fetch_issue and fetch_epic_issues."""
    if desc is None:
        return None
    if isinstance(desc, str):
        out = re.sub(r"<[^>]+>", " ", desc)
        out = re.sub(r"\s+", " ", out).strip()
        return out[:max_len] if out else None
    if isinstance(desc, dict):
        raw = desc.get("plain") or desc.get("content") or str(desc)
        s = raw if isinstance(raw, str) else " ".join(str(x) for x in (raw if isinstance(raw, list) else [raw]))
        return s[:max_len] if s else None
    return str(desc)[:max_len]


# ---------------------------------------------------------------------------
# Pure extraction helpers (no network, no credentials required)
# ---------------------------------------------------------------------------

def extract_ticket_from_text(text: str) -> Optional[str]:
    """Return the first Jira ticket key found in any text string, or None."""
    if not text:
        return None
    match = _TICKET_PATTERN.search(text)
    return match.group(1) if match else None


def extract_ticket_from_title(title: str) -> Optional[str]:
    """Backwards-compatible alias kept for callers that import this directly."""
    return extract_ticket_from_text(title)


def extract_ticket(
    title: str = "",
    branch: str = "",
    description: str = "",
) -> Optional[str]:
    """Search for a Jira ticket key across PR title, branch name, and description.

    Sources are checked in priority order: title → branch → description.
    Returns the first match found, or None.
    """
    for source in (title, branch, description):
        ticket = extract_ticket_from_text(source)
        if ticket:
            return ticket
    return None


# ---------------------------------------------------------------------------
# Jira client — gracefully absent when credentials are not configured
# ---------------------------------------------------------------------------

class JiraClient:
    """Thin wrapper around the ``jira`` library.

    Designed so the underlying HTTP client can later be swapped out for an
    Atlassian MCP integration by replacing only this class, without changing
    any callers.
    """

    def __init__(self, url: str, username: str, api_token: str) -> None:
        self._raw = self._connect(url, username, api_token)

    def is_connected(self) -> bool:
        return self._raw is not None

    def fetch_issue(self, issue_key: str) -> Optional[JiraIssue]:
        """Fetch structured metadata for a Jira issue.

        Returns a ``JiraIssue`` on success, or ``None`` if the client is
        unavailable or the request fails for any reason.
        """
        if not self._raw:
            return None
        try:
            raw = self._raw.issue(issue_key)
            fields = raw.fields
            desc = getattr(fields, "description", None)
            if desc is None:
                pass
            elif isinstance(desc, str):
                desc = self._strip_html(desc)[:4000]  # limit for prompt size
            elif isinstance(desc, dict):
                # Jira Cloud ADF or similar; flatten to string for prompt
                raw = desc.get("plain") or desc.get("content") or str(desc)
                desc = (raw if isinstance(raw, str) else " ".join(str(x) for x in (raw if isinstance(raw, list) else [raw])))[:4000]
            else:
                desc = str(desc)[:4000]
            return JiraIssue(
                key=issue_key,
                summary=getattr(fields, "summary", None),
                description=desc or None,
                issue_type=self._field_name(getattr(fields, "issuetype", None)),
                status=self._field_name(getattr(fields, "status", None)),
                priority=self._field_name(getattr(fields, "priority", None)),
                components=[
                    c.name for c in (getattr(fields, "components", None) or [])
                ],
                labels=list(getattr(fields, "labels", None) or []),
            )
        except Exception:
            return None

    def fetch_epic_context_markdown(self, issue_key: str) -> str:
        """Return markdown for the Epic linked to this issue (parent Epic Link, or issue is Epic).

        Empty string if no epic found or on failure. Uses parent + common Epic Link custom fields.
        """
        if not self._raw:
            return ""
        try:
            issue = self._raw.issue(
                issue_key,
                fields="summary,description,issuetype,parent,customfield_10014,customfield_10008",
            )
            fields = issue.fields
            itype = (getattr(getattr(fields, "issuetype", None), "name", None) or "").lower()

            def _fmt_epic(raw_epic) -> str:
                summ = getattr(raw_epic.fields, "summary", "") or ""
                desc = getattr(raw_epic.fields, "description", None)
                desc = _normalize_description(desc, max_len=4500) or ""
                key = raw_epic.key
                return f"## Jira Epic ({key})\n**{summ}**\n\n{desc}"

            if "epic" in itype:
                return _fmt_epic(issue)

            candidates: list[str] = []
            par = getattr(fields, "parent", None)
            if par and getattr(par, "key", None):
                candidates.append(par.key)
            for cf_name in ("customfield_10014", "customfield_10008"):
                cf = getattr(fields, cf_name, None)
                if cf is None:
                    continue
                k = getattr(cf, "key", None) if not isinstance(cf, str) else None
                if k:
                    candidates.append(k)
                elif isinstance(cf, str) and "-" in cf:
                    candidates.append(cf.strip())

            seen: set[str] = set()
            for ek in candidates:
                if not ek or ek in seen:
                    continue
                seen.add(ek)
                try:
                    epic = self._raw.issue(ek, fields="summary,description,issuetype")
                    ename = (getattr(getattr(epic.fields, "issuetype", None), "name", None) or "").lower()
                    if "epic" in ename:
                        return _fmt_epic(epic)
                except Exception:
                    continue
            return ""
        except Exception:
            return ""

    def _connect(self, url: str, username: str, api_token: str):  # type: ignore[return]
        try:
            from jira import JIRA

            return JIRA(server=url, basic_auth=(username, api_token))
        except Exception:
            return None

    def _field_name(self, field_obj: object) -> Optional[str]:
        """Extract the ``.name`` attribute from a Jira field object, if present."""
        if field_obj is None:
            return None
        return getattr(field_obj, "name", str(field_obj)) or None

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags and normalize whitespace for use in prompts."""
        if not text:
            return ""
        # Remove tags; collapse whitespace
        out = re.sub(r"<[^>]+>", " ", text)
        out = re.sub(r"\s+", " ", out).strip()
        return out


# ---------------------------------------------------------------------------
# Service facade
# ---------------------------------------------------------------------------

class JiraService:
    """High-level Jira service used by the CLI and metrics engine.

    Falls back to regex-only mode when Jira credentials are not configured,
    so the tool works without any Jira setup.
    """

    def __init__(self) -> None:
        self._client: Optional[JiraClient] = None
        if settings.jira_url and settings.jira_username and settings.jira_api_token:
            client = JiraClient(
                url=settings.jira_url,
                username=settings.jira_username,
                api_token=settings.jira_api_token,
            )
            if client.is_connected():
                self._client = client

    def is_available(self) -> bool:
        """True when a live Jira connection is established."""
        return self._client is not None

    def fetch_issue(self, issue_key: str) -> Optional[JiraIssue]:
        """Return structured Jira metadata, or None if unavailable."""
        if not self._client:
            return None
        return self._client.fetch_issue(issue_key)

    def get_ticket_summary(self, ticket_key: str) -> Optional[str]:
        """Backwards-compatible helper — returns the issue summary string."""
        issue = self.fetch_issue(ticket_key)
        return issue.summary if issue else None

    def fetch_epic_context_markdown(self, issue_key: str) -> str:
        """Epic summary+description for prompts (delegates to client)."""
        if not self._client:
            return ""
        return self._client.fetch_epic_context_markdown(issue_key)

    def fetch_epic_issues(self, epic_key: str) -> list[JiraIssue]:
        """Return all child issues (Stories, Tasks, Bugs, etc.) under an Epic.

        Uses JQL: ``"Epic Link" = KEY OR parent = KEY`` to cover both classic
        and next-gen Jira project structures.  Returns an empty list on any
        failure or when Jira is not configured.
        """
        if not self._client or not self._client._raw:
            return []
        try:
            jql = f'"Epic Link" = {epic_key} OR parent = {epic_key}'
            raw_issues = self._client._raw.search_issues(jql, maxResults=200)
            results: list[JiraIssue] = []
            for raw in raw_issues:
                fields = raw.fields
                desc = _normalize_description(getattr(fields, "description", None), max_len=2000)
                results.append(JiraIssue(
                    key=raw.key,
                    summary=getattr(fields, "summary", None),
                    description=desc,
                    issue_type=self._client._field_name(getattr(fields, "issuetype", None)),
                    status=self._client._field_name(getattr(fields, "status", None)),
                    priority=self._client._field_name(getattr(fields, "priority", None)),
                    components=[c.name for c in (getattr(fields, "components", None) or [])],
                    labels=list(getattr(fields, "labels", None) or []),
                ))
            return results
        except Exception:
            return []
