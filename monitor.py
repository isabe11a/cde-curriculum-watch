# monitor.py — CDE RSS-first curriculum / SBE / IQC / ELA-ELD / AI watcher

import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import feedparser
import requests


BASELINE_FILE = Path("baseline.json")
REPORT_FILE = Path("report.txt")

# CDE official RSS feed
RSS_FEEDS = [
    {
        "id": "cde_whats_new",
        "name": "CDE What's New RSS",
        "url": "https://www.cde.ca.gov/rssfeed.asp",
    },
]

CORE_TERMS = [
    # State governance
    "state board of education",
    "sbe",
    "instructional quality commission",
    "iqc",
    "state board members",

    # ELA / ELD / curriculum adoption
    "english language arts",
    "ela",
    "eld",
    "ela/eld",
    "instructional materials",
    "curriculum",
    "framework",
    "follow-up adoption",
    "adoption",
    "publisher",
    "publishers",
    "reviewer",
    "reviewers",

    # Science of Reading / literacy
    "science of reading",
    "structured literacy",
    "evidence-based literacy",
    "research-based literacy",
    "foundational skills",
    "phonics",
    "phonemic awareness",
    "phonological awareness",
    "decodable",
    "decodable texts",
    "reading",
    "literacy",
    "dyslexia",
    "screening for risk of reading difficulties",
    "reading difficulties",

    # AI / screen use / ed tech
    "artificial intelligence",
    "generative ai",
    "ai in education",
    "chatgpt",
    "large language model",
    "llm",
    "machine learning",
    "technology",
    "digital learning",
    "screen",
    "screen time",
    "device",
    "devices",
    "edtech",
    "educational technology",
    "computer-based",
    "computer based",
    "personalized learning",
    "adaptive learning",

    # Vendors/programs: ELA core and literacy
    "arc core",
    "arc core fusion",
    "amplify",
    "amplify ela",
    "bookworms",
    "ckla",
    "core knowledge",
    "core knowledge language arts",
    "core knowledge/amplify",
    "el education",
    "fishtank",
    "fishtank ela",
    "louisiana guidebooks",
    "novel middle school ela",
    "reading reconsidered",
    "wit & wisdom",

    # Other ELA/core programs worth watching
    "open court",
    "wonders",
    "benchmark",
    "hmh",
    "houghton mifflin harcourt",
    "into reading",
    "expeditionary learning",
    "great minds",
    "american reading company",
    "myview",
    "savvas",
    "pearson",
    "mcgraw hill",
    "study sync",
    "studysync",
    "collaborative classroom",
    "center for the collaborative classroom",
    "being a reader",
    "sipps",
    "reading horizons",
    "95 percent group",
    "95 phonics",
    "really great reading",
    "logic of english",

    # Vendors/programs: edtech / AI / assessment / intervention
    "lexia",
    "amira",
    "iready",
    "i-ready",
    "curriculum associates",
    "renaissance",
    "star reading",
    "nwea",
    "map growth",
    "newsela",
    "khan academy",
    "khanmigo",
    "magicschool",
    "schoolai",
    "brisk teaching",
    "quill",
    "dreambox",

    # Organizations: literacy / anti-screen / evidence
    "edreports",
    "reading league",
    "the reading league",
    "decoding dyslexia",
    "california reading coalition",
    "schools beyond screens",
    "distraction free schools",
    "fairplay",
    "wait until 8th",
    "children and screens",

    # Organizations: edtech / AI / interoperability / procurement
    "cite",
    "california it in education",
    "cetpa",
    "iste",
    "cosn",
    "asugsv",
    "edsafe ai alliance",
    "ai education project",
    "teachai",
    "code.org",
    "innovateedu",
    "project unicorn",
    "digital promise",
    "1edtech",
    "ims global",
    "meta",
    "google",
    "microsoft",
    "openai",
    "anthropic",
    "mobilizing economic transformation",
    "leading the future",
    "encode",
    "californians for responsible artificial intelligence",

    # California education policy orgs
    "california state pta",
    "california teachers association",
    "cta",
    "california school boards association",
    "csba",
    "association of california school administrators",
    "acsa",
    "california county superintendents",
    "ccsesa",
    "edvoice",
    "calmatters",
    "edsource",
]

PROCESS_TERMS = [
    "adopt",
    "adoption",
    "follow-up adoption",
    "publisher",
    "publishers",
    "reviewer",
    "reviewers",
    "public comment",
    "significant event",
    "significant events",
    "agenda",
    "meeting agenda",
    "minutes",
    "meeting minutes",
    "information memoranda",
    "memoranda",
    "memorandum",
    "report of findings",
    "webcast",
    "meeting materials",
    "item number",
    "attachment",
    "memo",
]

BLOCKED_TEXT_MARKERS = [
    "your activity and behavior on this site made us think that you are a bot",
    "please solve this captcha",
    "radware captcha page",
    "request unblock to the website",
]


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


def fetch_feed(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 cde-curriculum-watch/1.0 RSS reader",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def contains_term(haystack: str, term: str) -> bool:
    haystack = haystack.lower()
    term = term.lower().strip()

    # For acronyms / short terms, require word boundaries.
    if len(term) <= 4 or term in {"sbe", "iqc", "ela", "eld", "ai", "llm", "cta"}:
        return re.search(rf"\b{re.escape(term)}\b", haystack) is not None

    return term in haystack

def term_hits_for_entry(entry: dict) -> tuple[list[str], bool]:
    haystack = " ".join([
        entry.get("title", ""),
        entry.get("summary", ""),
        entry.get("link", ""),
    ])
    haystack = f" {haystack.lower()} "

    core_hits = []
    process_hits = []

    for term in CORE_TERMS:
        if contains_term(haystack, term):
            core_hits.append(term)

    for term in PROCESS_TERMS:
        if contains_term(haystack, term):
            process_hits.append(term)

    core_hits = sorted(set(core_hits))
    process_hits = sorted(set(process_hits))

    # Alert logic:
    # - Any core topic is relevant by itself.
    # - Process-only items are not relevant unless they also hit a core topic.
    #   This avoids false positives like nutrition public comment.
    is_relevant = bool(core_hits)

    all_hits = sorted(set(core_hits + process_hits))
    return all_hits, is_relevant


def entry_id(entry) -> str:
    # Prefer stable RSS guid/id. Fall back to link, then title.
    return (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
        or entry.get("title")
        or ""
    )


def parse_rss_feed(feed_config: dict) -> list[dict]:
    raw = fetch_feed(feed_config["url"])

    if is_blocked_text(raw):
        raise RuntimeError("Blocked/CAPTCHA response received from CDE RSS feed; not saving baseline.")

    parsed = feedparser.parse(raw)

    if parsed.bozo:
        raise RuntimeError(f"Could not parse RSS feed: {parsed.bozo_exception}")

    entries = []

    for entry in parsed.entries:
        item = {
            "feed_id": feed_config["id"],
            "feed_name": feed_config["name"],
            "id": clean_text(entry_id(entry)),
            "title": clean_text(entry.get("title", "")),
            "link": clean_text(entry.get("link", "")),
            "summary": clean_text(entry.get("summary", "")),
            "published": clean_text(entry.get("published", "")),
            "updated": clean_text(entry.get("updated", "")),
        }

        if not item["id"]:
            continue

        item["term_hits"], item["is_relevant"] = term_hits_for_entry(item)

        entries.append(item)

    # Stable ordering
    entries.sort(key=lambda x: (x.get("published", ""), x.get("title", ""), x.get("link", "")), reverse=True)
    return entries


def load_baseline() -> dict:
    if BASELINE_FILE.exists():
        try:
            return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"feeds": {}, "last_updated": None}

    return {"feeds": {}, "last_updated": None}


def save_baseline(data: dict) -> None:
    BASELINE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def check_feeds() -> tuple[list[dict], list[dict], dict]:
    baseline = load_baseline()
    old_feeds = baseline.get("feeds", {})

    new_feeds = {}
    new_relevant_items = []
    errors = []

    for feed_config in RSS_FEEDS:
        feed_id = feed_config["id"]
        print(f"Checking RSS feed: {feed_config['name']}...", flush=True)

        try:
            entries = parse_rss_feed(feed_config)

            old_entries = old_feeds.get(feed_id, {}).get("entries", [])
            old_ids = {item.get("id") for item in old_entries}

            current_new_items = [
                item for item in entries
                if item.get("id") not in old_ids
            ]

            current_new_relevant = [
                item for item in current_new_items
                if item.get("is_relevant")
            ]

            if old_entries:
                print(f"  New RSS items: {len(current_new_items)}", flush=True)
                print(f"  New relevant RSS items: {len(current_new_relevant)}", flush=True)
            else:
                print("  First baseline for this RSS feed; not alerting on existing items.", flush=True)

            # Only alert if this is not first baseline.
            if old_entries:
                new_relevant_items.extend(current_new_relevant)

            new_feeds[feed_id] = {
                "id": feed_id,
                "name": feed_config["name"],
                "url": feed_config["url"],
                "checked_at": utc_now(),
                "entries": entries,
            }

        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
            errors.append({
                "feed_id": feed_id,
                "feed_name": feed_config["name"],
                "url": feed_config["url"],
                "error": str(exc),
            })

            # Keep old baseline if RSS fails.
            if feed_id in old_feeds:
                new_feeds[feed_id] = old_feeds[feed_id]

    new_baseline = {
        "feeds": new_feeds,
        "last_updated": utc_now(),
    }

    save_baseline(new_baseline)
    return new_relevant_items, errors, new_baseline


def format_report(new_relevant_items: list[dict], errors: list[dict], baseline: dict) -> str:
    lines = [
        f"CDE Curriculum Watch — {utc_now()}",
        "",
        "Watching CDE RSS for:",
        "• SBE / State Board of Education",
        "• IQC / Instructional Quality Commission",
        "• ELA/ELD instructional materials adoption",
        "• Science of Reading / structured literacy",
        "• AI, screen use, technology, and edtech",
        "",
    ]

    if new_relevant_items:
        lines.append(f"## New relevant RSS items: {len(new_relevant_items)}")
        lines.append("")

        for item in new_relevant_items:
            lines.append(f"### {item.get('title', '(untitled)')}")

            if item.get("published"):
                lines.append(f"Published: {item['published']}")

            if item.get("link"):
                lines.append(f"Link: {item['link']}")

            hits = item.get("term_hits", [])
            if hits:
                lines.append(f"Matched: {', '.join(hits)}")

            if item.get("summary"):
                lines.append("")
                lines.append(item["summary"])

            lines.append("")
    else:
        lines.append("No new relevant RSS items detected")
        lines.append("")

    if errors:
        lines.append("## Errors")
        for error in errors:
            lines.append(f"- {error['feed_name']}: {error['error']}")
        lines.append("")

    lines.append("Current relevant feed items")

    for feed_id, feed in baseline.get("feeds", {}).items():
        entries = feed.get("entries", [])
        relevant_entries = [item for item in entries if item.get("is_relevant")]

        lines.append(f"• {feed.get('name')}: {len(entries)} total RSS items, {len(relevant_entries)} currently matching watch terms")

        for item in relevant_entries[:10]:
            title = item.get("title", "(untitled)")
            link = item.get("link", "")
            hits = ", ".join(item.get("term_hits", []))

            lines.append(f"  • {title}")
            if link:
                lines.append(f"    {link}")
            if hits:
                lines.append(f"    Matched: {hits}")

    return "\n".join(lines)

def main() -> None:
    try:
        new_relevant_items, errors, baseline = check_feeds()
        report = format_report(new_relevant_items, errors, baseline)

        REPORT_FILE.write_text(report, encoding="utf-8")
        print(report, flush=True)

        if new_relevant_items:
            print("\n[EXIT CODE 1: New relevant RSS item detected]", flush=True)
            sys.exit(1)

        print("\n[EXIT CODE 0: No relevant RSS changes]", flush=True)
        sys.exit(0)

    except Exception as exc:
        error_report = (
            "### CDE Curriculum Watch — ERROR\n\n"
            + str(exc)
            + "\n\n"
            + traceback.format_exc()
        )
        print(error_report, flush=True)
        REPORT_FILE.write_text(error_report, encoding="utf-8")

        # Do not poison the baseline or create noisy failures.
        print("\n[EXIT CODE 0: Error occurred]", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
