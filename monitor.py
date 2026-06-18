# monitor.py — CDE curriculum / SBE / IQC / ELA-ELD / AI watcher

import hashlib
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASELINE_FILE = Path("baseline.json")


WATCH_PAGES = [
    {
        "id": "sbe_current_past_agendas",
        "name": "SBE Current & Past Agendas",
        "url": "https://www.cde.ca.gov/be/ag/ag/",
        "category": "SBE",
    },
    {
        "id": "sbe_meeting_schedule",
        "name": "SBE Meeting Schedule",
        "url": "https://www.cde.ca.gov/be/ag/st/index.asp",
        "category": "SBE",
    },
    {
        "id": "iqc_landing",
        "name": "Instructional Quality Commission Landing Page",
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
        "name": "ELA/ELD IM Follow-up Adoption Significant Events",
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
        "id": "ela_eld_faq",
        "name": "ELA/ELD Follow-up Adoption FAQ",
        "url": "https://www.cde.ca.gov/ci/rl/im/elaeldfollowupadoptfaq.asp",
        "category": "ELA/ELD",
    },
    {
        "id": "ela_eld_reviewers",
        "name": "2026 ELA/ELD Instructional Materials Reviewers",
        "url": "https://www.cde.ca.gov/ci/rl/im/imrselaeldcohort2.asp",
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
]


IMPORTANT_TERMS = [
    # Your main issues
    "artificial intelligence",
    " ai ",
    "screen",
    "technology",
    "digital",
    "device",
    "devices",
    "edtech",
    "computer-based",
    "computer based",

    # Reading / SoR / literacy
    "science of reading",
    "structured literacy",
    "foundational skills",
    "phonics",
    "phonemic awareness",
    "decodable",
    "reading",
    "literacy",
    "dyslexia",
    "english language arts",
    "ela/eld",
    "ela",
    "eld",

    # Curriculum adoption process
    "instructional materials",
    "follow-up adoption",
    "adoption",
    "curriculum",
    "framework",
    "publisher",
    "publishers",
    "reviewer",
    "reviewers",
    "public comment",
    "schedule of significant events",
    "instructional quality commission",
    "state board of education",
    "sbe",
    "iqc",

    # Specific programs / vendors you may want to notice
    "core knowledge",
    "ckla",
    "amplify",
    "open court",
    "wonders",
    "benchmark",
    "lexia",
    "amira",
    "iready",
    "i-ready",
    "hmh",
    "curriculum associates",
]


NOISE_PATTERNS = [
    # CDE boilerplate that can create meaningless diffs.
    r"Last Reviewed:.*",
    r"Recently Posted in .*",
    r"Trending in .*",
    r"More Trending Items.*",
    r"Questions:.*",
    r"Share this Page.*",
]


def fetch(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 cde-curriculum-watch/1.0"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

    return text.strip()


def normalize_page(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    # CDE usually uses main/maincontent, but this fallback keeps it robust.
    main = soup.find("main") or soup.find(id="maincontent") or soup.body or soup

    text = clean_text(main.get_text("\n", strip=True))

    links = []
    for a in main.find_all("a", href=True):
        link_text = clean_text(a.get_text(" ", strip=True))
        href = urljoin(base_url, a["href"])

        if not link_text:
            continue
        if href.lower().startswith("javascript:"):
            continue
        if href.startswith("mailto:"):
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
        "title": title,
        "text": text,
        "links": deduped_links,
    }


def page_hash(page_state: dict) -> str:
    # Hash text and links, not timestamps.
    payload = {
        "text": page_state["text"],
        "links": page_state["links"],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_term_hits(text: str) -> list[str]:
    haystack = f" {text.lower()} "
    hits = []

    for term in IMPORTANT_TERMS:
        needle = term.lower()
        if needle in haystack:
            hits.append(term)

    return sorted(set(hits))


def snippets_for_terms(text: str, terms: list[str], max_snippets: int = 8) -> list[str]:
    snippets = []
    lower = text.lower()

    for term in terms:
        term_lower = term.lower().strip()
        if not term_lower:
            continue

        idx = lower.find(term_lower)
        if idx == -1:
            continue

        start = max(0, idx - 120)
        end = min(len(text), idx + len(term) + 180)
        snippet = text[start:end]
        snippet = re.sub(r"\s+", " ", snippet).strip()

        if snippet and snippet not in snippets:
            snippets.append(snippet)

        if len(snippets) >= max_snippets:
            break

    return snippets


def summarize_link_changes(old_links: list[dict], new_links: list[dict]) -> dict:
    old_set = {(x.get("text", ""), x.get("href", "")) for x in old_links}
    new_set = {(x.get("text", ""), x.get("href", "")) for x in new_links}

    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)

    return {
        "added": [{"text": text, "href": href} for text, href in added],
        "removed": [{"text": text, "href": href} for text, href in removed],
    }


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


def check_pages() -> tuple[list[dict], list[dict]]:
    baseline = load_baseline()
    old_pages = baseline.get("pages", {})

    new_pages = {}
    changes = []
    errors = []

    for config in WATCH_PAGES:
        page_id = config["id"]
        print(f"Checking {config['name']}...", flush=True)

        try:
            html = fetch(config["url"])
            normalized = normalize_page(html, config["url"])
            current_hash = page_hash(normalized)
            term_hits = find_term_hits(normalized["text"])

            new_state = {
                "id": page_id,
                "name": config["name"],
                "category": config["category"],
                "url": config["url"],
                "title": normalized["title"],
                "hash": current_hash,
                "term_hits": term_hits,
                "snippets": snippets_for_terms(normalized["text"], term_hits),
                "text": normalized["text"],
                "links": normalized["links"],
                "checked_at": datetime.utcnow().isoformat() + "Z",
            }

            old_state = old_pages.get(page_id)

            if old_state is None:
                # First run: create baseline, but do not alert.
                print(f"  First baseline for {page_id}", flush=True)
            elif old_state.get("hash") != current_hash:
                link_changes = summarize_link_changes(
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
                    "term_hits": term_hits,
                    "snippets": new_state["snippets"],
                    "link_changes": link_changes,
                })

                print(f"  CHANGE detected for {page_id}", flush=True)
            else:
                print(f"  No change for {page_id}", flush=True)

            new_pages[page_id] = new_state

        except Exception as exc:
            errors.append({
                "id": page_id,
                "name": config["name"],
                "url": config["url"],
                "error": str(exc),
            })
            print(f"  ERROR for {page_id}: {exc}", flush=True)

            # Keep old state if one exists, so a temporary CDE/request failure
            # does not erase the baseline.
            if page_id in old_pages:
                new_pages[page_id] = old_pages[page_id]

    save_baseline({
        "pages": new_pages,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    })

    return changes, errors


def format_report(changes: list[dict], errors: list[dict]) -> str:
    now = datetime.utcnow().isoformat() + "Z"

    lines = [
        f"### CDE Curriculum Watch — {now}",
        "",
        "Tracking:",
        "- State Board of Education agendas",
        "- Instructional Quality Commission pages",
        "- 2026 ELA/ELD instructional materials adoption pages",
        "- CDE AI guidance / AI Working Group pages",
        "",
    ]

    if not changes:
        lines.append("**No changes detected.**")
    else:
        lines.append(f"**Changes detected on {len(changes)} page(s).**")
        lines.append("")

        for change in changes:
            lines.append(f"## {change['category']}: {change['name']}")
            lines.append(f"URL: {change['url']}")
            lines.append(f"Previous check: {change.get('old_checked_at')}")
            lines.append(f"Current check: {change.get('new_checked_at')}")
            lines.append("")

            if change.get("term_hits"):
                lines.append("Important term hits:")
                for term in change["term_hits"]:
                    lines.append(f"- {term}")
                lines.append("")

            added_links = change["link_changes"]["added"]
            removed_links = change["link_changes"]["removed"]

            if added_links:
                lines.append("New links:")
                for link in added_links[:25]:
                    lines.append(f"- {link['text']}: {link['href']}")
                if len(added_links) > 25:
                    lines.append(f"- ...and {len(added_links) - 25} more")
                lines.append("")

            if removed_links:
                lines.append("Removed links:")
                for link in removed_links[:15]:
                    lines.append(f"- {link['text']}: {link['href']}")
                if len(removed_links) > 15:
                    lines.append(f"- ...and {len(removed_links) - 15} more")
                lines.append("")

            if change.get("snippets"):
                lines.append("Relevant snippets from current page:")
                for snippet in change["snippets"][:6]:
                    lines.append(f"> {snippet}")
                    lines.append("")

    if errors:
        lines.append("")
        lines.append("## Errors")
        for error in errors:
            lines.append(f"- {error['name']}: {error['error']}")

    return "\n".join(lines)


def main() -> None:
    try:
        changes, errors = check_pages()
        report = format_report(changes, errors)
        print(report, flush=True)

        Path("report.txt").write_text(report, encoding="utf-8")

        # Match your Aquatics behavior:
        # Exit 1 ONLY when actual page changes are detected.
        # Temporary errors do not fail the action, so your baseline is not blown up.
        if changes:
            print("\n[EXIT CODE 1: Changes detected]", flush=True)
            sys.exit(1)

        print("\n[EXIT CODE 0: No changes]", flush=True)
        sys.exit(0)

    except Exception as exc:
        error_report = (
            "### CDE Curriculum Watch — ERROR\n\n"
            + str(exc)
            + "\n\n"
            + traceback.format_exc()
        )
        print(error_report, flush=True)
        Path("report.txt").write_text(error_report, encoding="utf-8")

        # Same as your Aquatics monitor: do not fail on script error.
        # You can change this to sys.exit(1) later if you want errors to alert.
        print("\n[EXIT CODE 0: Error occurred]", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()