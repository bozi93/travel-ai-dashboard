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

def is_news_known(company, title, date):
    for n in company.get('news', []):
        if n.get('title') == title and n.get('date') == date:
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

# Blocklist: filter out government entities, tourism boards, and non-startups
GOVERNMENT_BLOCKLIST = [
    "tourism board", "ministry of", "department of", "bureau of",
    "government", "official", "national tourism", "tourism authority",
    "tourism administration", "embassy", "consulate",
]

# Geographic/adjective prefixes to strip before extracting company names
GEO_ADJECTIVES = [
    "dutch", "german", "french", "italian", "spanish", "british",
    "american", "canadian", "australian", "japanese", "korean",
    "chinese", "indian", "brazilian", "mexican", "russian",
    "african", "european", "asian", "latin", "nordic",
    "south african", "saudi", "emirati", "qatari", "turkish",
    "swiss", "swedish", "norwegian", "danish", "finnish",
    "uae-based", "us-based", "uk-based", "eu-based",
    "bay area", "silicon valley",
]

def is_government_entity(name):
    """Check if a name refers to a government/tourism board entity."""
    name_lower = name.lower()
    for blocked in GOVERNMENT_BLOCKLIST:
        if blocked in name_lower:
            return True
    return False

def strip_geo_prefix(text):
    """Remove geographic/adjective prefixes from headlines."""
    text_lower = text.lower()
    for geo in sorted(GEO_ADJECTIVES, key=len, reverse=True):
        # Match "Geo adjective + startup/company/platform/firm + ..."
        pattern = rf'\b{re.escape(geo)}\s+(startup|company|platform|firm|app|business)\s+'
        if re.search(pattern, text_lower):
            # Remove the geo prefix but keep the rest
            text = re.sub(pattern, r'\2 ', text, count=1, flags=re.IGNORECASE)
            break
    return text

def extract_company_name_from_title(title):
    """Try to extract the company/product name from a news headline."""
    text = title.strip()

    # Step 1: Strip geographic prefixes like "Dutch startup", "German company"
    text = strip_geo_prefix(text)

    # Step 2: Check for government/tourism board entities early
    if is_government_entity(text):
        return None

    # Pattern: "X raises...", "X launches...", "X debuts..."
    m = re.search(r'^([A-Z][A-Za-z0-9\s&\']+?)\s+(raises|launches|debuts|unveils|introduces|emerges|announces)',
                  text)
    if m:
        name = m.group(1).strip()
        name = re.sub(r'[\s:]+$', '', name)
        # Filter out government entities
        if len(name) >= 3 and not is_government_entity(name):
            # Take only the last capitalized word if it looks like "Adjective CompanyName"
            # e.g., "Travel Tech WeTravel" -> "WeTravel"
            words = name.split()
            if len(words) > 1:
                # Return the most likely company name (last capitalized word or compound)
                name = words[-1]
            return name

    # Pattern: "startup X ...", "company X ..."
    m = re.search(r'(?:new\s+)?(?:startup|company|app|platform|firm)\s+([A-Z][A-Za-z0-9\s&\']+?)[\s,;:\-]', text)
    if m:
        name = m.group(1).strip()
        name = re.sub(r'[\s:]+$', '', name)
        if len(name) >= 3 and not is_government_entity(name):
            # Extract clean company name
            words = name.split()
            if len(words) > 1:
                name = words[-1]
            return name

    # Pattern: "X, a Y-based startup, ..." or "X — a startup..."
    m = re.search(r'([A-Z][A-Za-z0-9\']+)\s*[,—–-]\s*(?:a|an)\s+(?:new\s+)?(?:y-)?(?:based\s+)?(?:startup|company|app|platform)', text)
    if m:
        name = m.group(1).strip()
        if len(name) >= 3 and not is_government_entity(name):
            return name

    return None

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
            if not is_news_known(matched, title, today):
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

                # Skip government/tourism board entities
                if company_name and is_government_entity(company_name):
                    print(f"  [SKIP] Filtered out government entity: {company_name}")
                    continue

                if company_name and company_name.lower() not in existing_names:
                    # Check we haven't already queued this candidate today
                    if not any(c['name'] == company_name for c in candidates):
                        news_date = entry.get('published') or today
                        # Clean product field: just the company/product name, not full headline
                        product_field = company_name
                        # Clean description: remove source suffix like " - Technical.ly"
                        clean_summary = re.sub(r'\s*[-–—]\s*\w+(\.\w+)+$', '', summary).strip()
                        candidates.append({
                            "id": f"auto-{news_id(company_name, news_date)}",
                            "name": company_name,
                            "type": "startup",
                            "location": "Unknown",
                            "stage": "Unknown",
                            "totalFunding": "N/A",
                            "product": product_field,
                            "investors": "",
                            "metrics": {"newsCount": 1, "newsRecency": news_date, "socialMentions": 0, "trafficGrowth": "N/A"},
                            "news": [{
                                "date": news_date,
                                "title": title,
                                "type": "product",
                                "source": link,
                            }],
                            "website": "",
                            "description": clean_summary[:200] if clean_summary else title,
                            "isNew": True,
                            "lastUpdated": today,
                            "_autoDiscovered": True,
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
