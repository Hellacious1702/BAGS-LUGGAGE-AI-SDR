import csv
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

CREDIT_LOG = Path("data/credit_log.csv")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

MOBILE = r"(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}"
TOLL_FREE = r"1800[\s-]?\d{3}[\s-]?\d{4}"
PHONE_RE = re.compile(rf"(?<!\d)({MOBILE}|{TOLL_FREE})(?!\d)")

NOT_EMAIL_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def get_domain(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def find_emails(text):
    emails = []
    for email in EMAIL_RE.findall(text or ""):
        email = email.lower().rstrip(".")
        if not email.endswith(NOT_EMAIL_ENDINGS) and email not in emails:
            emails.append(email)
    return emails


def find_phones(text):
    phones = []
    seen_digits = set()
    for phone in PHONE_RE.findall(text or ""):
        digits = re.sub(r"\D", "", phone)[-10:]
        if digits not in seen_digits:
            seen_digits.add(digits)
            phones.append(phone.strip())
    return phones


def log_credits(fc, note):
    usage = fc.get_credit_usage()
    CREDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    is_new = not CREDIT_LOG.exists()
    with open(CREDIT_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "note", "remaining_credits"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), note, usage.remaining_credits])
    print(f"Credits remaining ({note}): {usage.remaining_credits}")
