import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

INPUT_FILE = Path("data/extracted.csv")
PAGES_DIR = Path("data/raw/pages")
QUALIFIED_FILE = Path("data/qualified_leads.csv")
EXCLUDED_FILE = Path("data/excluded_leads.csv")
EXCEL_FILE = Path("data/leads.xlsx")

CURRENT_YEAR = datetime.now().year

THIRD_PARTY_SITES = ["sulekha.com", "indiabusinessguide.in", "tendersontime.com", "indiatimes.com",
                     "cvent.com", "bebee.com", "ensun.io", "medium.com"]
MAX_PHONES_ON_PAGE = 10

BUSINESS_TYPE_FIT = {
    "Corporate Gifting": 20,
    "Promotional Merchandise": 20,
    "Wholesaler/Distributor": 18,
    "Bag/Luggage Retailer": 18,
    "Travel Operator": 14,
    "E-commerce Brand": 12,
    "Hotel": 10,
    "Other": 4,
}

BAG_WORDS = ["bag", "backpack", "luggage", "trolley", "duffle", "tote", "suitcase", "laptop sleeve"]

INTENT_SIGNALS = [
    ("bulk / wholesale buying", 10, ["bulk order", "in bulk", "wholesale", "trade rate", "minimum order", "moq"]),
    ("quote / quotation requests", 8, ["request a quote", "get a quote", "request quote", "quotation", "rfq"]),
    ("corporate / B2B orders", 6, ["corporate order", "corporate gift", "b2b", "welcome kit", "employee gift"]),
    ("sourcing / procurement", 6, ["tender", "procurement", "vendor registration", "become a supplier",
                                   "looking for supplier"]),
]

SIZE_CLAIM = re.compile(r"\d+\+?\s*(clients|customers|brands|companies|branches|stores|outlets|hotels"
                        r"|properties|cities|employees|tours|travellers|years)\b")


def page_text(domain):
    scraped = json.loads((PAGES_DIR / f"{domain}.json").read_text())
    text = scraped["page"]["markdown"]
    if scraped["contact_page"]:
        text += "\n" + scraped["contact_page"]["markdown"]
    return text.lower()


def exclusion_reason(lead):
    if lead["scrape_error"]:
        return "Website could not be scraped"
    if lead["llm_error"]:
        return "AI extraction failed"
    if lead["lead_type"] == "competitor":
        return "Competitor: makes its own bags or is a bag brand"
    if lead["lead_type"] == "directory_or_blog":
        return "Directory, marketplace or blog, not a single business"
    if lead["lead_type"] == "outside_india":
        return "Business is not based in India"
    if any(lead["domain"].endswith(site) for site in THIRD_PARTY_SITES):
        return "Third-party listing site, contact details may not be the business's own"
    if int(lead["phone_count_on_page"] or 0) > MAX_PHONES_ON_PAGE:
        return "Page lists many businesses' numbers (store locator or directory)"
    if not lead["company_name"]:
        return "Company name missing"
    if not lead["emails"] and not lead["phones"]:
        return "No phone number or email found"
    return None


def score_fit(lead, text):
    points = BUSINESS_TYPE_FIT.get(lead["business_type"], 4)
    reason = f"{lead['business_type']} ({points}/20)"
    if any(word in text for word in BAG_WORDS):
        points += 5
        reason += ", mentions bags/luggage on site (+5)"
    return points, reason


def score_intent(text):
    points = 0
    found = []
    for name, value, phrases in INTENT_SIGNALS:
        for phrase in phrases:
            if phrase in text:
                points += value
                found.append(f"{name}: '{phrase}'")
                break
    return points, "; ".join(found) or "no buying signals found"


def score_scale(lead, text):
    points = 0
    reasons = []
    if lead["scale_quote"]:
        points += 5
        reasons.append("size statement on site")
    claim = SIZE_CLAIM.search(text)
    if claim:
        points += 5
        reasons.append(f"'{claim.group(0)}'")
    if "pan india" in text or "across india" in text or "branches" in text:
        points += 5
        reasons.append("serves multiple cities/branches")
    return points, "ASSUMPTION from site claims: " + (", ".join(reasons) or "no size information")


def score_recency(lead):
    if not lead["latest_year"]:
        return 0, "no dated content found"
    year = int(lead["latest_year"])
    if year == CURRENT_YEAR:
        points = 15
    elif year == CURRENT_YEAR - 1:
        points = 10
    elif year == CURRENT_YEAR - 2:
        points = 6
    else:
        points = 3
    return points, f"latest year on site: {year}"


def score_contact(lead):
    points = 0
    have = []
    if lead["emails"]:
        points += 5
        have.append("email")
    if lead["phones"]:
        points += 5
        have.append("phone")
    if lead["contact_person"]:
        points += 3
        have.append("named contact")
    if lead["location"]:
        points += 2
        have.append("location")
    return points, "has " + ", ".join(have)


def intent_label(total, intent, fit):
    if total >= 65 and intent >= 16:
        return "High"
    if total >= 45 and fit >= 14:
        return "Medium"
    return "Low"


def missing_data(lead):
    fields = {
        "email": "emails", "phone": "phones", "contact person": "contact_person",
        "location": "location", "intent quote": "intent_quote", "dated evidence": "latest_year",
    }
    missing = [name for name, column in fields.items() if not lead[column]]
    return ", ".join(missing) or "none"


def score_lead(lead):
    text = page_text(lead["domain"])
    fit, fit_why = score_fit(lead, text)
    intent, intent_why = score_intent(text)
    scale, scale_why = score_scale(lead, text)
    recency, recency_why = score_recency(lead)
    contact, contact_why = score_contact(lead)
    total = fit + intent + scale + recency + contact

    lead["score"] = total
    lead["intent_label"] = intent_label(total, intent, fit)
    lead["fit_score"] = fit
    lead["intent_score"] = intent
    lead["scale_score"] = scale
    lead["recency_score"] = recency
    lead["contact_score"] = contact
    lead["intent_evidence"] = intent_why
    lead["missing_data"] = missing_data(lead)
    lead["explanation"] = (
        f"Fit {fit}/25: {fit_why}. Intent {intent}/30: {intent_why}. Scale {scale}/15: {scale_why}. "
        f"Recency {recency}/15: {recency_why}. Contact {contact}/15: {contact_why}."
    )


def main():
    with open(INPUT_FILE, newline="") as f:
        leads = list(csv.DictReader(f))

    qualified = []
    excluded = []
    for lead in leads:
        reason = exclusion_reason(lead)
        if reason:
            lead["exclusion_reason"] = reason
            excluded.append(lead)
        else:
            score_lead(lead)
            qualified.append(lead)

    qualified.sort(key=lambda lead: lead["score"], reverse=True)
    unique = []
    seen_names = set()
    for lead in qualified:
        name = re.sub(r"[^a-z0-9]", "", lead["company_name"].lower())
        if name in seen_names:
            lead["exclusion_reason"] = "Duplicate company name"
            excluded.append(lead)
        else:
            seen_names.add(name)
            unique.append(lead)
    qualified = unique

    qualified_df = pd.DataFrame(qualified)
    excluded_df = pd.DataFrame(excluded)
    qualified_df.to_csv(QUALIFIED_FILE, index=False)
    excluded_df.to_csv(EXCLUDED_FILE, index=False)
    with pd.ExcelWriter(EXCEL_FILE) as writer:
        qualified_df.to_excel(writer, sheet_name="Qualified", index=False)
        excluded_df.to_excel(writer, sheet_name="Excluded", index=False)

    print(f"Discovered: {len(leads)}  Qualified: {len(qualified)}  Excluded: {len(excluded)}")
    print("Intent labels:", dict(Counter(lead["intent_label"] for lead in qualified)))
    print("Exclusion reasons:", dict(Counter(lead["exclusion_reason"] for lead in excluded)))


if __name__ == "__main__":
    main()
