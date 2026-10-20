import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from firecrawl import Firecrawl

from utils import get_domain, log_credits

load_dotenv()

CACHE_DIR = Path("data/raw/search")
OUTPUT_FILE = Path("data/discovered.csv")
RESULTS_PER_QUERY = 10

QUERIES = [
    ("Corporate Gifting", "corporate gifting company India bulk orders bags"),
    ("Corporate Gifting", "corporate gifts supplier Mumbai customised backpacks"),
    ("Promotional Merchandise", "promotional merchandise company India branded bags"),
    ("Promotional Merchandise", "branded merchandise supplier Bengaluru employee welcome kit"),
    ("Travel Operator", "tour operator India group tours corporate travel"),
    ("Travel Operator", "MICE travel company Delhi corporate events"),
    ("Hotel", "hotel group India multiple properties corporate events"),
    ("Hotel", "resort chain India banquet and conference"),
    ("Bag/Luggage Retailer", "luggage store India multi brand showroom"),
    ("Bag/Luggage Retailer", "bags and luggage shop Pune contact"),
    ("Wholesaler/Distributor", "bags wholesaler India contact number"),
    ("Wholesaler/Distributor", "luggage distributor India dealership enquiry"),
    ("E-commerce Brand", "D2C bags brand India online store"),
    ("E-commerce Brand", "travel accessories brand India online"),
    ("Buying Signal", "looking for bag supplier India bulk quotation"),
    ("Buying Signal", "tender supply of backpacks 2026 India"),
    ("Corporate Gifting", "corporate gifting company Hyderabad bulk orders"),
    ("Corporate Gifting", "corporate gifts supplier Chennai"),
    ("Corporate Gifting", "corporate gifting company Pune"),
    ("Corporate Gifting", "corporate gifts company Kolkata"),
    ("Corporate Gifting", "corporate gifting Ahmedabad customised"),
    ("Promotional Merchandise", "customised promotional products supplier Delhi"),
    ("Promotional Merchandise", "employee onboarding kit company India"),
    ("Bag/Luggage Retailer", "authorised dealer VIP Safari American Tourister luggage store"),
    ("Bag/Luggage Retailer", "luggage shop Chennai multi brand"),
    ("Wholesaler/Distributor", "school bags wholesale dealer India"),
    ("Travel Operator", "corporate travel management company India offices"),
    ("Travel Operator", "pilgrimage tour operator India group tours"),
    ("Hotel", "boutique hotel chain India properties"),
]

EXCLUDED_DOMAINS = [
    "indiamart.com", "justdial.com", "tradeindia.com", "amazon.in", "amazon.com",
    "flipkart.com", "myntra.com", "linkedin.com", "facebook.com", "instagram.com",
    "youtube.com", "wikipedia.org", "quora.com", "reddit.com", "x.com", "twitter.com",
    "pinterest.com",
]


def search(fc, query):
    cache_file = CACHE_DIR / (re.sub(r"[^a-z0-9]+", "_", query.lower()) + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    response = fc.search(
        query,
        limit=RESULTS_PER_QUERY,
        location="India",
        exclude_domains=EXCLUDED_DOMAINS,
    )
    results = [
        {"url": r.url, "title": r.title, "description": r.description}
        for r in (response.web or [])
    ]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(results, indent=2))
    return results


def main():
    fc = Firecrawl(api_key=os.getenv("FIRECRAWL_API_KEY"))
    log_credits(fc, "before discover")

    leads = {}
    total_results = 0
    for category, query in QUERIES:
        results = search(fc, query)
        total_results += len(results)
        print(f"{len(results):>3} results  {query}")
        for r in results:
            domain = get_domain(r["url"])
            if domain in leads or any(domain.endswith(d) for d in EXCLUDED_DOMAINS):
                continue
            leads[domain] = {
                "domain": domain,
                "url": r["url"],
                "title": r["title"],
                "description": r["description"],
                "category_hint": category,
                "query": query,
                "discovered_at": datetime.now().date().isoformat(),
            }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "domain", "url", "title", "description", "category_hint", "query", "discovered_at",
        ])
        writer.writeheader()
        writer.writerows(leads.values())

    print(f"\n{total_results} search results -> {len(leads)} unique domains saved to {OUTPUT_FILE}")
    log_credits(fc, "after discover")


if __name__ == "__main__":
    main()
