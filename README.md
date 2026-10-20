# Bags & Luggage AI SDR

A prototype that finds Indian businesses likely to buy bags and luggage, collects their public contact details, scores each lead from 0 to 100 using evidence from their website, and shows the best leads in a Streamlit dashboard.

**Results:** 224 websites discovered, 90 qualified leads (25 High, 47 Medium, 18 Low intent), 134 excluded with a reason. 290 of 1000 free Firecrawl credits used.

## How it works

The project is 5 scripts that run one after another. Each one saves its output to a file, so a step can be fixed and re-run without repeating the earlier ones.

```
discover.py  ->  scrape.py  ->  extract.py  ->  score.py  ->  app.py
  search          download        read pages       score         dashboard
```

### 1. `discover.py` — find possible buyers
- Runs 29 Firecrawl searches for the buyer types in the brief: corporate gifting, promotional merchandise, travel operators, hotels, bag retailers, wholesalers/distributors, e-commerce brands, plus searches for buying signals (supplier requests, tenders). All searches are limited to India.
- Skips marketplaces, directories and social media (IndiaMART, JustDial, Amazon, LinkedIn, etc.). These list many businesses on one page and mostly block scraping, so contact details found there would not belong to one company.
- Keeps one row per website (by domain), so the same company is not scraped twice.
- Output: `data/discovered.csv`

### 2. `scrape.py` — download each website
- Downloads the page text for every website, keeping the header and footer because that is where phone numbers and emails usually are.
- If the page has no email or phone, it finds the site's "Contact" page and downloads that too. This only happens when needed, to save credits.
- Retries when Firecrawl's free-plan rate limit is hit (wait 15 seconds, up to 3 tries). Failures caused by the rate limit are not saved, so the next run retries them.
- Output: `data/raw/pages/<domain>.json`

### 3. `extract.py` — read each page
- **Emails and phone numbers are found with regex, not AI**, so they cannot be made up. Phone numbers are Indian mobiles (10 digits starting 6–9) and 1800 toll-free numbers. Up to 3 of each are kept, with emails on the company's own domain first.
- **Nemotron** (`nvidia/nemotron-3.5-super-vl-120b-a12b`, via NVIDIA's API) reads the page and returns: company name, contact person, location, business type, lead type (buyer / competitor / directory or blog / outside India), likely bag need, and exact sentences from the page showing buying intent and business size.
- **Every sentence the AI says it copied is checked against the page.** If it is not found, it is removed and listed in `unverified_ai_fields` (this happened for 12 leads).
- The latest year mentioned on the page is found with regex, ignoring copyright lines and future years.
- Output: `data/extracted.csv`

### 4. `score.py` — qualify and score
First, each lead is checked against exclusion rules. The first rule that fails becomes its exclusion reason:

| Rule | Excluded |
|---|---|
| Competitor (makes its own bags or is a bag brand) | 60 |
| Directory, marketplace or blog | 37 |
| No phone number or email (mandatory in the brief) | 13 |
| Third-party listing site | 8 |
| Not based in India | 7 |
| Website could not be scraped | 6 |
| Page lists many businesses' numbers (store locator) | 2 |
| Company name missing | 1 |

Qualified leads are then scored on the 5 factors from the brief. **The AI does not give scores.** Every point comes from a fixed rule, and the reason is written in the `explanation` column.

| Factor | Max | How points are given |
|---|---|---|
| Product/business fit | 25 | Business type: Corporate Gifting 20, Promotional Merchandise 20, Wholesaler/Distributor 18, Bag/Luggage Retailer 18, Travel Operator 14, E-commerce Brand 12, Hotel 10, Other 4. Plus 5 if the site mentions bags or luggage. |
| Buying-intent evidence | 30 | Phrases found on the page: bulk/wholesale buying 10 ("bulk order", "wholesale", "MOQ"), quotation requests 8 ("request a quote", "RFQ"), corporate/B2B orders 6 ("corporate gift", "welcome kit"), sourcing/procurement 6 ("tender", "procurement"). |
| Order size / scale | 15 | Verified size statement 5, a claim like "500+ clients" 5, serves multiple cities or branches 5. **Marked as an assumption**, because it is based on what the business says about itself. |
| Recency of signals | 15 | Latest year on the site: this year 15, last year 10, two years ago 6, older 3, none 0. |
| Contactability | 15 | Email 5, phone 5, named contact person 3, location 2. |

**Intent labels:**
- **High:** score ≥ 65 and intent score ≥ 16 (at least two kinds of buying signal)
- **Medium:** score ≥ 45 and fit score ≥ 14 (good fit, limited evidence)
- **Low:** everything else

Duplicates are removed again by company name, keeping the highest-scoring row.

Output: `data/qualified_leads.csv`, `data/excluded_leads.csv`, `data/leads.xlsx` (two sheets).

### 5. `app.py` — dashboard
- Summary counts: discovered, qualified, High/Medium/Low.
- Lead table sorted by score, with source links.
- Filters: intent label, business category, minimum score, company name search.
- Lead detail view: score breakdown by factor, contact details, evidence, missing data, and the AI's likely bag requirement, marked as an assumption.
- Download the filtered leads as CSV or Excel.
- A separate tab for excluded leads and their reasons.

## Caching and credits

Every Firecrawl search, Firecrawl scrape and AI reply is saved in `data/raw/`. Before calling an API, each script checks for a saved file first, so re-running the pipeline costs no credits. `data/credit_log.csv` records the Firecrawl balance before and after each step.

| Step | Credits |
|---|---|
| Search, round 1 (16 queries) | 32 |
| Setup test | 1 |
| Scrape, round 1 | 154 |
| Search, round 2 (13 queries) | 26 |
| Scrape, round 2 | 100 |
| Returned by Firecrawl afterwards | −23 |
| **Total used** | **290 of 1000** |

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Create a `.env` file with your keys:

```
FIRECRAWL_API_KEY=your_firecrawl_key
NVIDIA_NIM_API_KEY=your_nvidia_key
```

Open the dashboard (no API keys needed, it reads the saved CSV files):

```bash
uv run streamlit run app.py
```

Re-run the full pipeline (uses the saved data in `data/raw/`, so no credits are spent):

```bash
uv run python discover.py
uv run python scrape.py
uv run python extract.py
uv run python score.py
```

`check_setup.py` checks that both API keys work.

## Limitations

- Named contact people are rarely published on Indian business websites (only 6 qualified leads have one).
- The scale score is based on the business's own claims, not verified figures.
- Recency uses the latest year on the page. It shows the site is active, not that a purchase is recent.
- Landline numbers are not collected. Two leads that listed only a landline and no email were excluded.
- Search results for bag retailers and e-commerce brands were almost all bag brands (competitors), so no leads in those categories qualified.
