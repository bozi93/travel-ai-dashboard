import json, re

with open('data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

enrichments = {
    'Voyagier': {
        'founded': '2023-01-01',
        'location': 'Philadelphia, USA',
        'stage': 'Pre-seed',
        'totalFunding': 'N/A',
        'product': 'AI-powered luxury travel planning platform',
        'website': '',
        'description': 'Voyagier is an AI-powered luxury travel planning platform that recently emerged from stealth and is gearing up for a seed round.',
        'investors': 'N/A',
    },
    'WeTravel': {
        'founded': '2014-01-01',
        'location': 'Ghent, Belgium',
        'stage': 'Series C',
        'totalFunding': '$92M+',
        'product': 'Multi-day travel operations platform with AI features',
        'website': 'https://www.wetravel.com',
        'description': 'WeTravel is a Dutch startup that provides a payment and booking platform for multi-day travel operators, recently raised $92M to scale with AI-driven features.',
        'investors': 'N/A',
        'fundingRounds': [
            {
                'date': '2025-09-25',
                'round': 'Series C',
                'amount': '$92M',
                'investors': 'N/A',
                'source': 'https://news.google.com/rss/articles/CBMisAFBVV95cUxPdzFDQThINGx6T0ZNMVIwYWtycnlZaWN1WHE3VEE0ci1ESC16NUEwOXAwWThtZ2JzTHBwaFV5MzU3Rm1OamE3UTNKazZEWHhBcXlGOUlrQktlb2NTV0tEX0JEc2NEbVY2YS03UEV0NW1yODVXeUFDMkdlX0c1TUFtakdmZGJsVndfZE5BRDVpLWdMZ19JWTdvZDBoU2dTYlJZWXltbXZQVFVsQjlIOVlpbg?oc=5'
            }
        ]
    },
    'LIAD': {
        'founded': '2024-01-01',
        'location': 'Seoul, South Korea',
        'stage': 'Seed Bridge',
        'totalFunding': 'N/A',
        'product': 'AI-powered travel planning and booking platform',
        'website': '',
        'description': 'LIAD Corporation is a Korean travel AI startup that raised a seed bridge round from Silicon Valley-based Sazze Partners, developing AI-powered travel solutions.',
        'investors': 'Sazze Partners',
        'fundingRounds': [
            {
                'date': '2026-03-19',
                'round': 'Seed Bridge',
                'amount': 'N/A',
                'investors': 'Sazze Partners',
                'source': 'https://news.google.com/rss/articles/CBMiU0FVX3lxTE9yeWp1Nm52c2RKazhQOHk5VW9LLTJxUWhMdTJvbGlCQUQ1VkxVa3ktb2hSeG84Qi01ZlpzVng5ZF9BSXRtUnVOWGVLOXBXTzNQek5n?oc=5'
            }
        ]
    },
    'Passprt': {
        'founded': '2024-01-01',
        'location': 'India',
        'stage': 'Pre-seed',
        'totalFunding': '$500K',
        'product': 'AI-powered travel platform for trip planning',
        'website': '',
        'description': 'Passprt Trips is an India-based startup that raised $500K to build an AI-powered travel platform focused on intelligent trip planning and recommendations.',
        'investors': 'N/A',
        'fundingRounds': [
            {
                'date': '2025-07-30',
                'round': 'Pre-seed',
                'amount': '$500K',
                'investors': 'N/A',
                'source': 'https://news.google.com/rss/articles/CBMi4gFBVV95cUxOVTBvUFBnV1lHdW5ya3ZwR2gtWEIxTi1RbnVhNENNQXAzNktTNU94eXlOanJUMV9TV0xUSnc0ajliN2VkTm1sLTd1bk8zWUs1MjIwb0RuZFJCM3R4MGtnVDZVeWVEZjJMZUVaVjRyUGpCNGJtRUVVMW91NnNBTDcwelhWR05tbFR5WHVDZGx3S0RKTVFvQ2dCNzBXSGQ5eWo4Q0hTT0Z0RlUyUWxobTRHMkUwWFI5R1l4alBDeVRoYktNakZOVUJ2VHJKaGRvR05KWFlUZVF0d3pMb1NiQ0RfWWl30gHnAUFVX3lxTE5Hbmw1V2FDSnJ5LVlLbEtwUWRUM2Uta1Bxck1Dc2ZpcF9GcEtrcVNXeHFucFE1eXJVTk81dllUWWkwck9WaU4zdzM5VTE4a09MN0lrS1F3UzNfcGFrcWlJaDhaNEkzZElHVE4zSGI4SXJlV19LQTc0RTJzYzg3bWhJeFFscnhHQ2UwbmxSRHE3UEJaWUJSYXFhbUkzV3BiU3FjZmxYbE02ZXRvQ1RHT0NwNUNVUFl6Mmt5OTNLOElCLWhpekNpYTY5YTIzSF83MlU3d2tzZ3VoZGU5MmlwRDJUenpGMnZpTQ?oc=5'
            }
        ]
    },
    'GeniusTravel': {
        'founded': '2024-01-01',
        'location': 'Amsterdam, Netherlands',
        'stage': 'Seed',
        'totalFunding': '€2M',
        'product': 'AI travel packages and booking app',
        'website': '',
        'description': 'GeniusTravel is a Dutch TravelTech platform that raised €2 million to roll out an AI-driven travel packages app, simplifying trip planning and booking.',
        'investors': 'N/A',
        'fundingRounds': [
            {
                'date': '2025-07-07',
                'round': 'Seed',
                'amount': '€2M',
                'investors': 'N/A',
                'source': 'https://news.google.com/rss/articles/CBMiwwFBVV95cUxNTnV4X0dXXzQyQlJucEo3a3dMT09XQTRFVkRwNUg3U0ZKNDRDc2dkbW9Ya3JWdkhRSDJmY3lFMUVPYVlMS2UxbTB4OXBWSU9YR2E0YTQ5SUF5VTNlOGZPbi1tQlhsZjdIbl9TQWlsa3phUUVQaXZJVG0tOHU0S21HU1RiSWhSSlVxWnBWNDJnNGZqWUMyU0c4b2FBTGdZTFJzcVlZbWU4a0JPTXdtSEtlV0Y0aFItd1dEUTViNTFwTUlHR2s?oc=5'
            }
        ]
    }
}

def dedupe_news(news_list):
    seen = set()
    result = []
    for n in news_list:
        key = (n.get('date',''), n.get('title',''))
        if key not in seen:
            seen.add(key)
            result.append(n)
    return result

for company in data['companies']:
    name = company['name']
    if name in enrichments:
        e = enrichments[name]
        for key, val in e.items():
            company[key] = val
        company['news'] = dedupe_news(company.get('news', []))
        desc = company.get('description', '')
        if desc.startswith('<a href=') or len(desc) < 30:
            company['description'] = e['description']
        company['isNew'] = False
        print(f"Fixed {name}: {len(company['news'])} news, stage={company['stage']}, loc={company['location']}")

with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write('\n')

print('Done.')
