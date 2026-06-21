# monitor_index.py — weekly CDE index-page checker
#
# This is separate from the RSS watcher.
# It checks a small number of CDE landing/index pages for new or removed links.
# It refuses to save Radware/CAPTCHA pages to the baseline.

import os
import hashlib
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASELINE_FILE = Path("index_baseline.json")
REPORT_FILE = Path("index_report.txt")


INDEX_PAGES = [
    {
        "id": "sbe_meeting_agendas_schedule",
        "name": "SBE Meeting Agendas & Schedule",
        "url": "https://www.cde.ca.gov/be/ag/",
        "category": "SBE",
    },
    {
        "id": "sbe_current_past_agendas",
        "name": "SBE Current & Past Agendas",
        "url": "https://www.cde.ca.gov/be/ag/ag/",
        "category": "SBE",
    },
    {
        "id": "sbe_meeting_minutes",
        "name": "SBE Meeting Minutes",
        "url": "https://www.cde.ca.gov/be/ag/mn/",
        "category": "SBE",
    },
    {
        "id": "sbe_information_memoranda",
        "name": "SBE Information Memoranda",
        "url": "https://www.cde.ca.gov/be/pn/im/",
        "category": "SBE",
    },
    {
        "id": "iqc_landing",
        "name": "Instructional Quality Commission",
        "url": "https://www.cde.ca.gov/be/cc/cd/",
        "category": "IQC",
    },
    {
        "id": "iqc_current_meeting_dates",
        "name": "IQC Current Meeting Dates",
        "url": "https://www.cde.ca.gov/be/cc/cd/iqccurrentmtgdates.asp",
        "category": "IQC",
    },
    {
        "id": "ela_instructional_materials",
        "name": "ELA Instructional Materials",
        "url": "https://www.cde.ca.gov/ci/rl/im/",
        "category": "ELA/ELD",
    },
    {
        "id": "ela_eld_followup_timeline",
        "name": "ELA/ELD Follow-up Adoption Timeline",
        "url": "https://www.cde.ca.gov/be/cc/cd/elaeldfupadopttimeline.asp",
        "category": "ELA/ELD",
    },
    {
        "id": "ela_eld_significant_events",
        "name": "ELA/ELD Follow-up Adoption Significant Events",
        "url": "https://www.cde.ca.gov/ci/rl/im/elaeldfupsigevents.asp",
        "category": "ELA/ELD",
    },
    {
        "id": "ela_eld_participants",
        "name": "2026 ELA/ELD Follow-up Adoption Participants",
        "url": "https://www.cde.ca.gov/ci/rl/im/elaeldparticipants2026.asp",
        "category": "ELA/ELD",
    },
    {
        "id": "cde_ai",
        "name": "CDE Artificial Intelligence",
        "url": "https://www.cde.ca.gov/ci/pl/aiincalifornia.asp",
        "category": "AI",
    },
    {
        "id": "ai_working_group",
        "name": "Public Schools AI Working Group",
        "url": "https://www.cde.ca.gov/ci/pl/aiineducationworkgroup.asp",
        "category": "AI",
    },
    {
        "id": "cde_news_releases",
        "name": "CDE News Releases",
        "url": "https://www.cde.ca.gov/nr/ne/",
        "category": "News",
    },
]


BLOCKED_TEXT_MARKERS = [
    "your activity and behavior on this site made us think that you are a bot",
    "please solve this captcha",
    "radware captcha page",
    "request unblock to the website",
]


NOISE_LINK_TEXT = {
    "home",
    "search",
    "contact us",
    "translate",
    "share this page",
    "back to top",
    "skip to main content",

    # CDE identity / top-level template
    "california department of education",
    "california state board of education",
    "ca board of education",

    # CDE global footer / boilerplate
    "about cde",
    "cde locations",
    "cde mission",
    "cde organization",
    "equal opportunity",
    "jobs at cde",
    "newsroom",
    "stay connected with cde",
    "superintendent's initiatives",
    "a-z index",
    "site map",
    "web policy",
    "accessibility certification",

    # CDE global nav / popular links
    "teaching & learning",
    "teaching & learning home",
    "testing & accountability",
    "testing & accountability home",
    "finance & grants",
    "finance & grants home",
    "data & statistics",
    "data & statistics home",
    "specialized programs",
    "specialized programs home",
    "learning support",
    "learning support home",

    "popular content",
    "popular program areas",
    "resources",
    "site information",
    "more resources",

    "california school dashboard",
    "common core state standards",
    "complaint procedures",
    "content standards",
    "curriculum resources",
    "education funding",
    "english language development standards",
    "financial allocations & apportionments",
    "high school equivalency tests",
    "high school graduation requirements",
    "kindergarten in california",
    "social and emotional learning",
    "standards & frameworks",
    "accountability - school performance",
    "career technical education",
    "charter schools",
    "child nutrition",
    "child development",
    "disaster and emergency management",
    "expanded learning",
    "principal apportionments",
    "safe schools",
    "school facilities",
    "special education",
    "standardized testing",
    "title i",
    "title iii",
    "california school directory",
    "education calendars",
    "education faqs",
    "language access complaint",
    "laws & regulations",
    "multilingual documents",
    "publications",
    "school and district reports",
}


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_blocked_text(text: str) -> bool:
    lower = clean_text(text).lower()
    return any(marker in lower for marker in BLOCKED_TEXT_MARKERS)


def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 cde-curriculum-watch/1.0 weekly index checker",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def pages_to_check_today() -> list[dict]:
    """
    Check only one index page per scheduled run to avoid looking like a scraper
    from GitHub Actions.

    Manual runs can check a specific page by setting INDEX_PAGE_ID.
    Example:
      INDEX_PAGE_ID=iqc_landing python monitor_index.py
    """
    requested_id = os.getenv("INDEX_PAGE_ID", "").strip()

    if requested_id:
        selected = [page for page in INDEX_PAGES if page["id"] == requested_id]
        if not selected:
            raise RuntimeError(f"Unknown INDEX_PAGE_ID: {requested_id}")
        return selected

    # Rotate one page per day based on UTC day number.
    day_number = datetime.now(timezone.utc).toordinal()
    index = day_number % len(INDEX_PAGES)
    return [INDEX_PAGES[index]]


def normalize_page(html: str, base_url: str) -> dict:
    if is_blocked_text(html):
        raise RuntimeError("Blocked/CAPTCHA response received; not saving this page.")

    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # Remove obvious CDE template/nav/footer regions before extracting links.
    # This is the important part: otherwise we capture hundreds of global nav links.
    template_selectors = [
        "header",
        "footer",
        "nav",
        "[role='navigation']",
        ".navbar",
        ".mega-menu",
        ".megamenu",
        ".breadcrumb",
        ".breadcrumbs",
        "#breadcrumb",
        "#breadcrumbs",
        "#footer",
        "#header",
        "#navigation",
        "#nav",
        "#skip-to-content",
        ".skip-link",
        ".skip",
        ".social-media",
        ".social",
    ]

    for selector in template_selectors:
        for tag in soup.select(selector):
            tag.decompose()

    # Prefer the true content area.
    main = (
        soup.find(id="content")
        or soup.find(id="maincontent")
        or soup.find("main")
        or soup.body
        or soup
    )

    text = clean_text(main.get_text(" ", strip=True))

    if is_blocked_text(title) or is_blocked_text(text):
        raise RuntimeError("Blocked/CAPTCHA page detected after parsing; not saving this page.")

    links = []

    for a in main.find_all("a", href=True):
        link_text = clean_text(a.get_text(" ", strip=True))
        href = urljoin(base_url, a["href"]).strip()

        if not link_text:
            continue

        lower_text = link_text.lower()

        if lower_text in NOISE_LINK_TEXT:
            continue

        if href.startswith("mailto:") or href.lower().startswith("javascript:"):
            continue

        # Skip same-page footnotes / anchors like #Footnote1.
        if "#" in href:
            href_without_anchor, anchor = href.split("#", 1)
            if href_without_anchor == base_url or href_without_anchor.rstrip("/") == base_url.rstrip("/"):
                continue

        # Skip self-links.
        if href.rstrip("/") == base_url.rstrip("/"):
            continue

        links.append({
            "text": link_text,
            "href": href,
        })

    # Deduplicate links while preserving order.
    seen = set()
    deduped_links = []
    for link in links:
        key = (link["text"], link["href"])
        if key not in seen:
            deduped_links.append(link)
            seen.add(key)

    return {
        "title": clean_text(title),
        "text": text,
        "links": deduped_links,
    }


def hash_links(links: list[dict]) -> str:
    raw = json.dumps(links, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_baseline() -> dict:
    if BASELINE_FILE.exists():
        try:
            return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"pages": {}, "last_updated": None}

    return {"pages": {}, "last_updated": None}


def save_baseline(data: dict) -> None:
    BASELINE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def link_diff(old_links: list[dict], new_links: list[dict]) -> dict:
    old_set = {(x.get("text", ""), x.get("href", "")) for x in old_links}
    new_set = {(x.get("text", ""), x.get("href", "")) for x in new_links}

    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)

    return {
        "added": [{"text": text, "href": href} for text, href in added],
        "removed": [{"text": text, "href": href} for text, href in removed],
    }


def check_index_pages() -> tuple[list[dict], list[dict], dict]:
    baseline = load_baseline()
    old_pages = baseline.get("pages", {})

    # Start with the existing baseline so the rotating checker accumulates pages
    # over time instead of replacing the baseline with only today's page.
    new_pages = dict(old_pages)

    changes = []
    errors = []

    selected_pages = pages_to_check_today()

    print("Selected index page(s) for this run:", flush=True)
    for page in selected_pages:
        print(f"- {page['id']}: {page['name']}", flush=True)

    for config in selected_pages:
        page_id = config["id"]
        print(f"Checking index page: {config['name']}...", flush=True)

        try:
            html = fetch_page(config["url"])
            normalized = normalize_page(html, config["url"])
            current_hash = hash_links(normalized["links"])

            old_state = old_pages.get(page_id)

            new_state = {
                "id": page_id,
                "name": config["name"],
                "category": config["category"],
                "url": config["url"],
                "title": normalized["title"],
                "hash": current_hash,
                "links": normalized["links"],
                "checked_at": utc_now(),
            }

            if old_state is None:
                print(f"  First baseline for {page_id}; not alerting.", flush=True)
            elif old_state.get("hash") != current_hash:
                diff = link_diff(
                    old_state.get("links", []),
                    new_state.get("links", []),
                )

                changes.append({
                    "id": page_id,
                    "name": config["name"],
                    "category": config["category"],
                    "url": config["url"],
                    "old_checked_at": old_state.get("checked_at"),
                    "new_checked_at": new_state["checked_at"],
                    "added_links": diff["added"],
                    "removed_links": diff["removed"],
                })

                print(f"  CHANGE detected for {page_id}", flush=True)
            else:
                print(f"  No change for {page_id}", flush=True)

            new_pages[page_id] = new_state

        except Exception as exc:
            print(f"  ERROR for {page_id}: {exc}", flush=True)
            errors.append({
                "id": page_id,
                "name": config["name"],
                "url": config["url"],
                "error": str(exc),
            })

            # Keep old page state if possible so a CAPTCHA/error does not poison the baseline.
            if page_id in old_pages:
                new_pages[page_id] = old_pages[page_id]

    new_baseline = {
        "pages": new_pages,
        "last_updated": utc_now(),
    }

    save_baseline(new_baseline)
    return changes, errors, new_baseline


def format_report(changes: list[dict], errors: list[dict], baseline: dict) -> str:
    lines = [
        f"CDE Index Watch — {utc_now()}",
        "",
        "Rotating low-frequency check of selected CDE index pages:",
        "• SBE agendas, minutes, and information memoranda",
        "• IQC pages",
        "• ELA/ELD instructional materials adoption pages",
        "• CDE AI pages",
        "• CDE News Releases index",
        "",
    ]

    if changes:
        lines.append(f"Index page changes detected: {len(changes)}")
        lines.append("")

        for change in changes:
            lines.append(f"### {change['category']}: {change['name']}")
            lines.append(f"Page: {change['url']}")
            lines.append(f"Previous check: {change.get('old_checked_at')}")
            lines.append(f"Current check: {change.get('new_checked_at')}")
            lines.append("")

            added = change.get("added_links", [])
            removed = change.get("removed_links", [])

            if added:
                lines.append("New links")
                for link in added[:25]:
                    lines.append(f"• {link['text']}")
                    lines.append(f"  {link['href']}")
                if len(added) > 25:
                    lines.append(f"- ...and {len(added) - 25} more new links")
                lines.append("")

            if removed:
                lines.append("Removed links:")
                for link in removed[:15]:
                    lines.append(f"- {link['text']}")
                    lines.append(f"  {link['href']}")
                if len(removed) > 15:
                    lines.append(f"- ...and {len(removed) - 15} more removed links")
                lines.append("")
    else:
        lines.append("No new or removed links detected since the last check")
        lines.append("")

    if errors:
        lines.append("Errors")
        lines.append("These were not saved to the baseline.")
        for error in errors:
            lines.append(f"- {error['name']}: {error['error']}")
        lines.append("")

    lines.append("Index pages currently being tracked")
    if not baseline.get("pages"):
        lines.append("• No index pages have been successfully saved yet.")
    else:
        for page_id, page in baseline.get("pages", {}).items():
            lines.append(
                f"• {page.get('category')}: {page.get('name')} "
                f"({len(page.get('links', []))} tracked links)"
            )
            lines.append(f"  {page.get('url')}")

    return "\n".join(lines)

def main() -> None:
    try:
        changes, errors, baseline = check_index_pages()
        report = format_report(changes, errors, baseline)

        REPORT_FILE.write_text(report, encoding="utf-8")
        print(report, flush=True)

        if changes:
            print("\n[EXIT CODE 1: Index page changes detected]", flush=True)
            sys.exit(1)

        print("\n[EXIT CODE 0: No index page changes]", flush=True)
        sys.exit(0)

    except Exception as exc:
        error_report = (
            "### CDE Index Page Watch — ERROR\n\n"
            + str(exc)
            + "\n\n"
            + traceback.format_exc()
        )
        REPORT_FILE.write_text(error_report, encoding="utf-8")
        print(error_report, flush=True)

        # Do not make random errors poison the baseline.
        print("\n[EXIT CODE 0: Error occurred]", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()