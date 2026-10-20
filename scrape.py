import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from firecrawl import Firecrawl

from utils import find_emails, find_phones, get_domain, log_credits

load_dotenv()

INPUT_FILE = Path("data/discovered.csv")
CACHE_DIR = Path("data/raw/pages")


def is_rate_limited(error):
    return error is not None and "Rate limit" in error


def scrape_page(fc, url, attempts=3):
    for attempt in range(attempts):
        try:
            doc = fc.scrape(
                url,
                formats=["markdown", "links"],
                only_main_content=False,
                timeout=30000,
            )
            return {"url": url, "markdown": doc.markdown or "", "links": doc.links or [], "error": None}
        except Exception as e:
            error = str(e)[:300]
            if is_rate_limited(error) and attempt < attempts - 1:
                print("  rate limited, waiting 15s...")
                time.sleep(15)
                continue
            return {"url": url, "markdown": "", "links": [], "error": error}


def find_contact_link(links, domain):
    for link in links:
        if "contact" in link.lower() and get_domain(link) == domain:
            return link
    return None


def has_contact_details(text):
    return bool(find_emails(text) or find_phones(text))


def main():
    fc = Firecrawl(api_key=os.getenv("FIRECRAWL_API_KEY"))
    log_credits(fc, "before scrape")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT_FILE, newline="") as f:
        leads = list(csv.DictReader(f))

    for i, lead in enumerate(leads, start=1):
        domain = lead["domain"]
        cache_file = CACHE_DIR / f"{domain}.json"
        if cache_file.exists():
            continue

        page = scrape_page(fc, lead["url"])
        contact_page = None
        if not page["error"] and not has_contact_details(page["markdown"]):
            contact_link = find_contact_link(page["links"], domain)
            if contact_link and contact_link != lead["url"]:
                contact_page = scrape_page(fc, contact_link)

        if is_rate_limited(page["error"]):
            print(f"[{i}/{len(leads)}] {domain}: still rate limited, will retry next run")
            continue

        cache_file.write_text(json.dumps({
            "domain": domain,
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "page": page,
            "contact_page": contact_page,
        }, indent=2))

        status = "ERROR" if page["error"] else ("ok + contact page" if contact_page else "ok")
        print(f"[{i}/{len(leads)}] {domain}: {status}")

    log_credits(fc, "after scrape")


if __name__ == "__main__":
    main()
