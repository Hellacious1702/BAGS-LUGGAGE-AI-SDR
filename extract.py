import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from utils import find_emails, find_phones

load_dotenv()

INPUT_FILE = Path("data/discovered.csv")
PAGES_DIR = Path("data/raw/pages")
LLM_CACHE_DIR = Path("data/raw/llm")
OUTPUT_FILE = Path("data/extracted.csv")

MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
MAX_PAGE_CHARS = 12000
CURRENT_YEAR = datetime.now().year

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_NIM_API_KEY"))

PROMPT = """You help a bags and luggage manufacturer in India find businesses that could BUY bags from them
(for corporate gifts, employee kits, travel kits, hotel use, or to resell).

Read the website text below and return ONLY a JSON object with these keys:
- "company_name": the business name, or "" if unclear
- "contact_person": a named person (owner, founder, sales contact) ONLY if written on the page, else ""
- "location": city/state in India if written on the page, else ""
- "business_type": one of "Corporate Gifting", "Promotional Merchandise", "Travel Operator", "Hotel",
  "Bag/Luggage Retailer", "Wholesaler/Distributor", "E-commerce Brand", "Other"
- "lead_type": one of
    "buyer" - a business that could buy bags from us. This INCLUDES gifting companies, merchandise
              suppliers, retailers, wholesalers and distributors that resell or brand bags made by others,
    "competitor" - it manufactures bags itself (has its own factory) or is a bag/luggage brand,
    "directory_or_blog" - an article, list, directory or marketplace, not a single business,
    "outside_india" - the business is not based in India
- "likely_bag_need": one short sentence guessing what bags they might buy and why (this is an assumption)
- "intent_quote": an EXACT sentence copied from the text that shows buying intent or bulk demand
  (bulk orders, request a quote, corporate orders, supplier enquiries), else ""
- "scale_quote": an EXACT sentence copied from the text that shows business size
  (number of clients, branches, employees, years, tours per year), else ""

Never invent details. If something is not in the text, use "".

Website text:
{text}"""


def normalize(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def appears_in(snippet, text):
    return bool(snippet) and normalize(snippet) in normalize(text)


def latest_year(text):
    years = []
    for line in text.splitlines():
        if "©" in line or "copyright" in line.lower():
            continue
        years += [int(y) for y in re.findall(r"\b(20[12]\d)\b", line) if int(y) <= CURRENT_YEAR]
    return max(years) if years else ""


def parse_json(reply):
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        return None


def ask_llm(domain, text):
    cache_file = LLM_CACHE_DIR / f"{domain}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT.format(text=text[:MAX_PAGE_CHARS])}],
            temperature=0,
            max_tokens=1000,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    except Exception as e:
        print(f"  LLM call failed for {domain}: {str(e)[:100]}")
        return None
    result = parse_json(response.choices[0].message.content or "")
    if result is None:
        return None

    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result, indent=2))
    return result


def extract_lead(lead):
    page_file = PAGES_DIR / f"{lead['domain']}.json"
    scraped = json.loads(page_file.read_text())
    page, contact_page = scraped["page"], scraped["contact_page"] or {}

    row = {
        "domain": lead["domain"],
        "source_url": lead["url"],
        "contact_page_url": contact_page.get("url", ""),
        "search_title": lead["title"],
        "category_hint": lead["category_hint"],
        "search_query": lead["query"],
        "collected_on": lead["discovered_at"],
        "scrape_error": page["error"] or "",
    }
    if page["error"]:
        return row

    text = page["markdown"] + "\n" + (contact_page.get("markdown") or "")
    emails = find_emails(text)
    own_emails = [e for e in emails if e.endswith(lead["domain"])]
    emails = own_emails + [e for e in emails if e not in own_emails]
    phones = find_phones(text)
    row["emails"] = "; ".join(emails[:3])
    row["phones"] = "; ".join(phones[:3])
    row["phone_count_on_page"] = len(phones)
    row["latest_year"] = latest_year(text)

    llm = ask_llm(lead["domain"], text)
    if llm is None:
        row["llm_error"] = "LLM call failed or reply was not valid JSON"
        return row

    for key in ["company_name", "location", "business_type", "lead_type", "likely_bag_need"]:
        row[key] = llm.get(key, "")

    unverified = []
    for key in ["contact_person", "intent_quote", "scale_quote"]:
        value = llm.get(key, "")
        if value and not appears_in(value, text):
            unverified.append(key)
            value = ""
        row[key] = value
    row["unverified_ai_fields"] = ", ".join(unverified)
    return row


def main():
    with open(INPUT_FILE, newline="") as f:
        leads = list(csv.DictReader(f))

    rows = []
    for i, lead in enumerate(leads, start=1):
        row = extract_lead(lead)
        rows.append(row)
        print(f"[{i}/{len(leads)}] {lead['domain']}: {row.get('lead_type') or row.get('scrape_error') or row.get('llm_error')}")

    columns = [
        "domain", "company_name", "emails", "phones", "phone_count_on_page", "contact_person", "location",
        "business_type", "lead_type", "likely_bag_need", "intent_quote", "scale_quote",
        "latest_year", "source_url", "contact_page_url", "search_title", "category_hint",
        "search_query", "collected_on", "unverified_ai_fields", "scrape_error", "llm_error",
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
