#!/usr/bin/env python3
"""
Sync Netlify Form submissions to subscribers.json.
Reads email submissions from the 'subscribe' form and updates subscribers.json.
"""

import json
import os
import sys

import requests

SUBSCRIBERS_FILE = os.path.join(os.path.dirname(__file__), '..', 'subscribers.json')
NETLIFY_API_TOKEN = os.environ.get('NETLIFY_API_TOKEN')
NETLIFY_SITE_ID = os.environ.get('NETLIFY_SITE_ID')
NETLIFY_API_BASE = 'https://api.netlify.com/api/v1'


def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"subscribers": []}


def save_subscribers(data):
    with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_netlify_headers():
    return {
        'Authorization': f'Bearer {NETLIFY_API_TOKEN}',
        'Content-Type': 'application/json',
    }


def find_subscribe_form():
    """Find the 'subscribe' form for the given site."""
    if not NETLIFY_API_TOKEN:
        print('NETLIFY_API_TOKEN not set, skipping Netlify subscriber sync')
        return None

    site_id = NETLIFY_SITE_ID
    if not site_id:
        # Try to find site by listing all sites and matching name
        try:
            resp = requests.get(
                f'{NETLIFY_API_BASE}/sites',
                headers=get_netlify_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            sites = resp.json()
            for site in sites:
                if 'travel-ai-dashboard' in site.get('name', ''):
                    site_id = site['id']
                    print(f"Found site by name: {site['name']} ({site_id})")
                    break
        except requests.exceptions.RequestException as e:
            print(f'Failed to list Netlify sites: {e}')
            return None

    if not site_id:
        print('NETLIFY_SITE_ID not set and could not auto-detect, skipping sync')
        return None

    try:
        resp = requests.get(
            f'{NETLIFY_API_BASE}/sites/{site_id}/forms',
            headers=get_netlify_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        forms = resp.json()
        for form in forms:
            if form.get('name') == 'subscribe':
                return form
        print("No 'subscribe' form found on Netlify site")
        return None
    except requests.exceptions.RequestException as e:
        print(f'Failed to fetch Netlify forms: {e}')
        return None


def get_form_submissions(form_id):
    """Get all submissions for a given form."""
    submissions = []
    page = 1
    while True:
        try:
            resp = requests.get(
                f'{NETLIFY_API_BASE}/forms/{form_id}/submissions',
                headers=get_netlify_headers(),
                params={'page': page, 'per_page': 100},
                timeout=30,
            )
            resp.raise_for_status()
            page_data = resp.json()
            if not page_data:
                break
            submissions.extend(page_data)
            if len(page_data) < 100:
                break
            page += 1
        except requests.exceptions.RequestException as e:
            print(f'Failed to fetch form submissions: {e}')
            break
    return submissions


def main():
    subscribers_data = load_subscribers()
    existing = set(subscribers_data.get('subscribers', []))
    initial_count = len(existing)

    form = find_subscribe_form()
    if not form:
        print('No Netlify form configured or found. Keeping existing subscribers.')
        sys.exit(0)

    submissions = get_form_submissions(form['id'])
    print(f'Fetched {len(submissions)} form submissions from Netlify')

    added = 0
    for submission in submissions:
        data = submission.get('data', {})
        email = data.get('email', '').strip().lower()
        if email and '@' in email and email not in existing:
            existing.add(email)
            added += 1

    subscribers_data['subscribers'] = sorted(existing)
    save_subscribers(subscribers_data)

    print(f'Subscribers: {initial_count} -> {len(existing)} (added {added})')


if __name__ == '__main__':
    main()
