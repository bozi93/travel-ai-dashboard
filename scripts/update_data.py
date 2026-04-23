#!/usr/bin/env python3
"""
Auto-scraper for travel AI startup news.
Fetches RSS feeds and Reddit, matches news to existing companies,
and discovers new candidates.
"""

import json
import re
import os
import sys
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
import feedparser

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data.json')

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    "https://skift.com/feed/",
    "https://www.phocuswire.com/rss.xml",
    # Google News RSS ( English )
    "https://news.google.com/rss/search?q=AI+travel+startup&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=AI+tourism+planning&hl=en-US&gl=US&ceid=US:en",
]

REDDIT_QUERIES = [
    ("travel", "AI"),
    ("startups", "travel"),
]

# ---------------------------------------------------------------------------
# Keywords for filtering relevant news
# ---------------------------------------------------------------------------
TRAVEL_AI_KEYWORDS = [
    "travel", "tourism", "trip", "hotel", "flight", "itinerary",
    "vacation", "booking", "destination",
]
AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "llm",
    "chatbot", "gpt", "generative ai", "agent",
]
NEW_COMPANY_SIGNALS = [
    "raises", "funding", "seed", "series a", "series b",
    "launches", "debuts", "unveils", "introduces", "new startup",
    "emerges", "coming out of stealth",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_data():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

def today_str():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

def normalize(text):
    return re.sub(r'[^\w\s]', ' ', text.lower())

def is_relevant(title, summary=''):
    text = normalize(title + ' ' + summary)
    has_travel = any(kw in text for kw in TRAVEL_AI_KEYWORDS)
    has_ai = any(kw in text for kw in AI_KEYWORDS)
    return has_travel and has_ai

def looks_like_new_company(title, summary=''):
    text = normalize(title + ' ' + summary)
    return any(sig in text for sig in NEW_COMPANY_SIGNALS)

def extract_domain(url):
    return urlparse(url).netloc.lower()

def news_id(title, date):
    return hashlib.md5(f"{date}:{title}".encode()).hexdigest()[:12]

def is_news_known(company, title):
    """Check if a news title is already known (regardless of date)."""
    for n in company.get('news', []):
        if n.get('title') == title:
            return True
    return False

def is_funding_known(company, date, round_name, amount):
    for f in company.get('fundingRounds', []):
        if f.get('date') == date and f.get('round') == round_name and f.get('amount') == amount:
            return True
    return False

# ---------------------------------------------------------------------------
# Company name matching
# ---------------------------------------------------------------------------
def match_company_name(text, companies):
    """Return company object if text contains a known company name, else None."""
    text_lower = text.lower()
    # Sort by name length descending so longer names match first
    for c in sorted(companies, key=lambda x: -len(x['name'])):
        name = c['name'].lower()
        # Avoid matching common words that happen to be in names
        if len(name) <= 3:
            continue
        if name in text_lower:
            return c
    return None

# ---------------------------------------------------------------------------
# RSS scraping
# ---------------------------------------------------------------------------
def parse_rss_date(date_str):
    """Parse various RSS date formats into YYYY-MM-DD."""
    if not date_str:
        return None
    import email.utils
    from datetime import datetime
    try:
        # RFC 822 format: "Wed, 23 Apr 2026 10:00:00 GMT"
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        pass
    try:
        # ISO 8601 format
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except Exception:
        pass
    # Try common patterns
    m = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if m:
        return m.group(1)
    return None


def fetch_rss(url):
    try:
        # feedparser handles HTTP itself, but we set a timeout
        fp = feedparser.parse(url)
        entries = []
        for e in fp.entries:
            published = e.get('published', '')
            pub_date = parse_rss_date(published)
            entries.append({
                'title': e.get('title', ''),
                'summary': e.get('summary', e.get('description', '')),
                'link': e.get('link', ''),
                'published': pub_date or '',
            })
        return entries
    except Exception as ex:
        print(f"RSS error {url}: {ex}")
        return []

# ---------------------------------------------------------------------------
# Reddit scraping (JSON API, no auth needed for read-only)
# ---------------------------------------------------------------------------
def fetch_reddit(subreddit, query):
    try:
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "sort": "new", "limit": 25, "t": "week"}
        headers = {"User-Agent": "travel-ai-dashboard/1.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"Reddit error {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        entries = []
        for child in data.get('data', {}).get('children', []):
            post = child.get('data', {})
            entries.append({
                'title': post.get('title', ''),
                'summary': post.get('selftext', '')[:500],
                'link': f"https://www.reddit.com{post.get('permalink', '')}",
                'published': '',
            })
        return entries
    except Exception as ex:
        print(f"Reddit error r/{subreddit} q={query}: {ex}")
        return []

# ---------------------------------------------------------------------------
# New company extraction (heuristic)
# ---------------------------------------------------------------------------

# Blocklist: if the ENTIRE title/summary is about these, skip
GOVERNMENT_BLOCKLIST = [
    "tourism board", "ministry of tourism", "department of tourism",
    "bureau of tourism", "tourism authority", "tourism administration",
    "national tourism", "tourism development", "tourism promotion",
    "embassy ", "consulate ", "government announces", "government launches",
]

# Words that should NEVER be extracted as company names
BLOCKED_COMPANY_WORDS = [
    "tourism", "travel", "trip", "trips", "booking", "vacation",
    "holiday", "resort", "hotel", "airline", "airport",
    "ministry", "department", "bureau", "authority", "board",
    "council", "commission", "organization", "association",
]

# Geographic names that should NEVER be company names
GEO_COUNTRY_NAMES = [
    "south africa", "saudi arabia", "thailand", "vietnam", "indonesia",
    "malaysia", "singapore", "philippines", "japan", "korea", "china",
    "india", "brazil", "mexico", "australia", "new zealand", "canada",
    "united states", "united kingdom", "france", "germany", "italy",
    "spain", "portugal", "netherlands", "switzerland", "austria",
    "sweden", "norway", "denmark", "finland", "poland", "turkey",
    "russia", "uae", "qatar", "dubai", "abu dhabi", "egypt",
    "morocco", "kenya", "nigeria", "argentina", "chile", "colombia",
    "peru", "costa rica", "jamaica", "bahamas", "maldives",
    "sri lanka", "nepal", "cambodia", "laos", "myanmar",
    "sonoma county", "california", "texas", "florida", "hawaii",
    "new york", "london", "paris", "rome", "tokyo", "bangkok",
    # Continent names and parts that appear as company names
    "africa", "asia", "europe", "americas", "oceania", "antarctica",
    "south", "north", "east", "west", "central",
    # Country name parts
    "south", "north", "republic", "kingdom", "emirates", "states",
    "arabia", "zealand", "islands",
]

# Short geo adjectives that may appear before "startup/company"
GEO_ADJECTIVES = [
    "dutch", "german", "french", "italian", "spanish", "british",
    "american", "canadian", "australian", "japanese", "korean",
    "chinese", "indian", "brazilian", "mexican", "russian",
    "african", "european", "asian", "latin", "nordic",
    "south african", "saudi", "emirati", "qatari", "turkish",
    "swiss", "swedish", "norwegian", "danish", "finnish",
    "thai", "vietnamese", "indonesian", "malaysian",
    "uae-based", "us-based", "uk-based", "eu-based",
]


def is_government_entity(title):
    """Check if the title is about a government/tourism board entity."""
    text = title.lower()
    for blocked in GOVERNMENT_BLOCKLIST:
        if blocked in text:
            return True
    return False


def is_geo_only_name(name):
    """Check if a name is purely a geographic place (country/city)."""
    name_lower = name.lower().strip()
    # Direct match against country/city list
    if name_lower in GEO_COUNTRY_NAMES:
        return True
    # Common abbreviations
    short_forms = {"tat": True, "sato": True, "pata": True, "unwto": True, "wttc": True}
    if name_lower.strip() in short_forms:
        return True
    # Check against blocked company words
    if name_lower in BLOCKED_COMPANY_WORDS:
        return True
    return False


def is_valid_company_name(name):
    """Check if a name looks like a real company name."""
    if not name or len(name) < 3:
        return False
    name_lower = name.lower().strip()
    # Reject if it's purely a geo name or blocked word
    if name_lower in GEO_COUNTRY_NAMES or name_lower in BLOCKED_COMPANY_WORDS:
        return False
    # Reject common abbreviations
    short_forms = {"tat": True, "sato": True, "pata": True, "unwto": True, "wttc": True}
    if name_lower in short_forms:
        return False
    # Accept names starting with capital letter
    if re.match(r'^[A-Z]', name):
        return True
    return False


def extract_company_name_from_title(title):
    """
    Extract company/product name from a news headline.
    """
    text = title.strip()

    # Early reject: government/tourism board articles
    if is_government_entity(text):
        return None

    # --- Pattern 1: "[Geo] ... startup/company/platform X ..." ---
    # e.g. "Dutch startup WeTravel launches AI platform"
    # e.g. "Dutch TravelTech platform GeniusTravel launches AI booking"
    for geo in GEO_ADJECTIVES:
        pattern = rf'\b{re.escape(geo)}\s+.*?(?:startup|company|firm|platform|app)\s+([A-Z][A-Za-z0-9]+)'
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            company = m.group(1).strip()
            if is_valid_company_name(company):
                return company

    # --- Pattern 2: "X launches/raises/debuts/unveils..." (subject at start) ---
    # e.g. "WeTravel launches AI platform" or "BizTrip AI launches assistant"
    m = re.search(
        r'^([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*)\s+'
        r'(raises|launches|debuts|unveils|introduces|emerges|announces|secures|closes|gets)',
        text
    )
    if m:
        raw_name = m.group(1).strip()
        words = raw_name.split()
        # If multi-word like "BizTrip AI", take the first meaningful word
        # If it's "Passprt Trips", take "Passprt"
        if len(words) >= 2:
            # Check if last word is a generic term
            if words[-1].lower() in ('ai', 'trips', 'trip', 'travel', 'app', 'platform', 'tech'):
                company = words[-2] if len(words) >= 2 else words[-1]
            else:
                company = words[-1]
        else:
            company = words[0] if words else raw_name
        if is_valid_company_name(company):
            return company

    # --- Pattern 3: "...startup/company X..." anywhere in title ---
    # e.g. "AI travel startup WeTravel raises $5M"
    m = re.search(
        r'(?:new\s+)?(?:startup|company|firm)\s+([A-Z][A-Za-z0-9]+)',
        text
    )
    if m:
        company = m.group(1).strip()
        if is_valid_company_name(company):
            return company

    # --- Pattern 4: "X, a [geo] startup, ..." ---
    m = re.search(
        r'([A-Z][A-Za-z0-9]+)\s*,\s*(?:a|an)\s+(?:.*?)\s*(?:startup|company|firm)',
        text
    )
    if m:
        company = m.group(1).strip()
        if is_valid_company_name(company):
            return company

    # --- Pattern 5: "X — a [geo] startup..." ---
    m = re.search(
        r'([A-Z][A-Za-z0-9]+)\s*[—–-]\s*(?:a|an)\s+(?:.*?)\s*(?:startup|company|firm)',
        text
    )
    if m:
        company = m.group(1).strip()
        if is_valid_company_name(company):
            return company

    return None


def infer_location_from_title(title):
    """Infer location from geo adjectives or country mentions in the title."""
    text = title.lower()
    geo_map = {
        'dutch': 'Netherlands',
        'german': 'Germany',
        'french': 'France',
        'italian': 'Italy',
        'spanish': 'Spain',
        'british': 'United Kingdom',
        'american': 'USA',
        'canadian': 'Canada',
        'australian': 'Australia',
        'japanese': 'Japan',
        'korean': 'South Korea',
        'chinese': 'China',
        'indian': 'India',
        'brazilian': 'Brazil',
        'mexican': 'Mexico',
        'russian': 'Russia',
        'african': 'Africa',
        'european': 'Europe',
        'asian': 'Asia',
        'latin': 'Latin America',
        'nordic': 'Nordic',
        'south african': 'South Africa',
        'saudi': 'Saudi Arabia',
        'emirati': 'UAE',
        'qatari': 'Qatar',
        'turkish': 'Turkey',
        'swiss': 'Switzerland',
        'swedish': 'Sweden',
        'norwegian': 'Norway',
        'danish': 'Denmark',
        'finnish': 'Finland',
        'thai': 'Thailand',
        'vietnamese': 'Vietnam',
        'indonesian': 'Indonesia',
        'malaysian': 'Malaysia',
        'uae-based': 'UAE',
        'us-based': 'USA',
        'uk-based': 'United Kingdom',
        'eu-based': 'Europe',
    }
    for adj, country in geo_map.items():
        if adj in text:
            return country
    # Try to find "in City" or "based in City"
    m = re.search(r'(?:based\s+in|in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', title)
    if m:
        city = m.group(1).strip()
        if city.lower() not in GEO_COUNTRY_NAMES and city.lower() not in BLOCKED_COMPANY_WORDS:
            return city
    return 'Unknown'


def infer_website(company_name):
    """Generate a likely website URL from the company name."""
    if not company_name:
        return ''
    clean = re.sub(r'[^\w]', '', company_name).lower()
    if not clean:
        return ''
    # Try common startup domains
    for tld in ['.ai', '.com', '.co', '.io']:
        guess = f'https://www.{clean}{tld}'
        # We return the guess; the dashboard can show it as "unverified"
        return guess
    return ''


def extract_founded_year(title, summary=''):
    """Extract founded year from text like 'Founded in 2023'."""
    text = title + ' ' + summary
    m = re.search(r'[Ff]ounded\s+(?:in\s+)?(\d{4})', text)
    if m:
        return m.group(1) + '-01-01'
    return ''


# ---------------------------------------------------------------------------
# LLM enhancement (optional)
# ---------------------------------------------------------------------------
def llm_judge_new_company(title, summary):
    """Use OpenAI to judge if this news is about a new travel-AI company."""
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return None  # skip if no key
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": (
                        "You are a news analyst. Given a news headline and summary, "
                        "determine if it is about a NEW travel/AI startup or product "
                        "that is NOT already well-known (e.g. not Booking.com, Expedia, "
                        "TripAdvisor, Airbnb, Uber). "
                        "Respond ONLY with a JSON object: "
                        '{"is_new_company": true/false, "company_name": "...", "reason": "..."}'
                    )},
                    {"role": "user", "content": f"Title: {title}\nSummary: {summary}"}
                ],
                "temperature": 0.2,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        # Strip markdown code fences if present
        content = re.sub(r'^```json\s*|\s*```$', '', content, flags=re.MULTILINE).strip()
        return json.loads(content)
    except Exception as ex:
        print(f"LLM error: {ex}")
        return None

# ---------------------------------------------------------------------------
# Main update logic
# ---------------------------------------------------------------------------
def main():
    data = load_data()
    companies = data.get('companies', [])
    existing_names = {c['name'].lower() for c in companies}
    today = today_str()
    new_entries = []      # news added to existing companies
    candidates = []       # potential new companies

    # Gather all raw entries
    all_entries = []
    for url in RSS_FEEDS:
        all_entries.extend(fetch_rss(url))
    for sub, q in REDDIT_QUERIES:
        all_entries.extend(fetch_reddit(sub, q))

    print(f"Fetched {len(all_entries)} raw entries.")

    for entry in all_entries:
        title = entry.get('title', '')
        summary = entry.get('summary', '')
        link = entry.get('link', '')

        if not is_relevant(title, summary):
            continue

        matched = match_company_name(title + ' ' + summary, companies)

        if matched:
            # Add news to existing company
            if not is_news_known(matched, title):
                # Use the actual published date if available, otherwise fall back to today
                news_date = entry.get('published') or today
                matched.setdefault('news', []).insert(0, {
                    "date": news_date,
                    "title": title,
                    "type": "product",
                    "source": link,
                })
                matched['lastUpdated'] = today
                # Bump metrics news count slightly
                metrics = matched.get('metrics', {})
                metrics['newsCount'] = metrics.get('newsCount', 0) + 1
                new_entries.append((matched['name'], title))
        else:
            # No known company matched — could be new
            if looks_like_new_company(title, summary):
                # Try LLM if available
                llm_result = llm_judge_new_company(title, summary)
                if llm_result and not llm_result.get('is_new_company'):
                    continue

                company_name = None
                if llm_result:
                    company_name = llm_result.get('company_name')
                if not company_name:
                    company_name = extract_company_name_from_title(title)

                # Skip government/tourism board entities and pure geo names
                if company_name and (is_government_entity(company_name) or is_geo_only_name(company_name)):
                    print(f"  [SKIP] Filtered out: {company_name}")
                    continue

                if company_name and company_name.lower() not in existing_names:
                    # Check we haven't already queued this candidate today
                    if not any(c['name'] == company_name for c in candidates):
                        news_date = entry.get('published') or today
                        # Clean product field: just the company/product name, not full headline
                        product_field = company_name
                        # Clean description: remove source suffix like " - Technical.ly"
                        clean_summary = re.sub(r'\s*[-–—]\s*\w+(\.\w+)+$', '', summary).strip()
                        # Extract a meaningful product description from the title
                        product_desc = re.sub(
                            r'^(?:' + '|'.join(GEO_ADJECTIVES) + r')\s+.*?\s+(?:startup|company|firm|platform|app)\s+',
                            '', title, flags=re.IGNORECASE
                        )
                        product_desc = re.sub(
                            r'\s+(raises|launches|debuts|unveils|introduces|emerges|announces|secures|closes|gets)\s+.*$',
                            '', product_desc
                        ).strip()
                        if len(product_desc) < 10 or product_desc.lower() == company_name.lower():
                            product_desc = f"AI-powered travel technology by {company_name}"

                        location = infer_location_from_title(title)
                        website = infer_website(company_name)
                        founded = extract_founded_year(title, summary)
                        if not founded:
                            founded = f"{datetime.now().year}-01-01"

                        candidates.append({
                            "id": f"auto-{news_id(company_name, news_date)}",
                            "name": company_name,
                            "type": "startup",
                            "location": location,
                            "stage": "Unknown",
                            "totalFunding": "N/A",
                            "product": product_desc,
                            "investors": "N/A",
                            "metrics": {"newsCount": 1, "newsRecency": news_date, "socialMentions": 5, "trafficGrowth": "待观察"},
                            "news": [{
                                "date": news_date,
                                "title": title,
                                "type": "product",
                                "source": link,
                            }],
                            "website": website,
                            "description": clean_summary[:200] if clean_summary and not clean_summary.startswith('<') else product_desc,
                            "isNew": True,
                            "lastUpdated": today,
                            "_autoDiscovered": True,
                            "founded": founded,
                        })

    # Append candidates
    if candidates:
        companies.extend(candidates)
        print(f"Discovered {len(candidates)} new candidate(s):")
        for c in candidates:
            print(f"  - {c['name']}: {c['news'][0]['title']}")

    # Update metadata
    data['lastUpdated'] = today
    if 'version' not in data:
        data['version'] = today
    else:
        # bump version date
        data['version'] = today

    save_data(data)

    print(f"Added {len(new_entries)} news to existing companies.")
    if new_entries:
        for name, title in new_entries[:10]:
            print(f"  + {name}: {title[:60]}...")

if __name__ == '__main__':
    main()
