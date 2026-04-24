#!/usr/bin/env python3
"""
Send email notification via Resend when new companies are discovered.
Reads data.json and sends a summary of new companies to subscribed emails.
"""

import json
import os
import sys
import requests
from datetime import datetime

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data.json')
SUBSCRIBERS_FILE = os.path.join(os.path.dirname(__file__), '..', 'subscribers.json')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
RESEND_API_URL = 'https://api.resend.com/emails'
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'Travel AI Dashboard <onboarding@resend.dev>')

def load_subscribers():
    """Load subscriber emails from subscribers.json."""
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"WARNING: {SUBSCRIBERS_FILE} is not valid JSON: {e}")
            print("Treating as empty subscriber list.")
            return {"subscribers": []}
    return {"subscribers": []}

def get_new_companies():
    """Get companies marked as isNew from data.json."""
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    new_companies = []
    for company in data.get('companies', []):
        if company.get('isNew', False):
            new_companies.append(company)
    
    return new_companies, data.get('lastUpdated', 'Unknown')

def build_email_html(new_companies, update_date):
    """Build HTML email body."""
    companies_html = ""
    for company in new_companies:
        news_items = company.get('news', [])
        latest_news = news_items[0] if news_items else {}
        
        companies_html += f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
            <td style="padding: 16px 12px;">
                <div style="font-size: 16px; font-weight: 600; color: #1f2937; margin-bottom: 4px;">
                    {company['name']}
                </div>
                <div style="font-size: 14px; color: #6b7280; margin-bottom: 8px;">
                    {company.get('stage', 'Unknown')} · {company.get('location', 'Unknown')}
                </div>
                <div style="font-size: 14px; color: #374151; margin-bottom: 8px;">
                    {company.get('description', '')[:200]}
                </div>
                <div style="font-size: 13px; color: #9ca3af;">
                    Latest: {latest_news.get('title', '')[:100]} · {latest_news.get('date', '')}
                </div>
            </td>
        </tr>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f3f4f6;">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
            <tr>
                <td style="padding: 32px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba8 100%);">
                    <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 700;">
                        Travel AI Dashboard - 新公司发现
                    </h1>
                    <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">
                        更新时间: {update_date}
                    </p>
                </td>
            </tr>
            <tr>
                <td style="padding: 24px;">
                    <p style="font-size: 16px; color: #374151; margin: 0 0 16px 0;">
                        本次扫描发现了 <strong style="color: #667eea;">{len(new_companies)}</strong> 家新的旅游AI创业公司:
                    </p>
                    <table width="100%" cellpadding="0" cellspacing="0">
                        {companies_html}
                    </table>
                </td>
            </tr>
            <tr>
                <td style="padding: 24px; background-color: #f9fafb; text-align: center;">
                    <p style="font-size: 14px; color: #6b7280; margin: 0;">
                        查看完整 Dashboard: <a href="https://travel-ai-dashboard.netlify.app/" style="color: #667eea; text-decoration: none;">travel-ai-dashboard.netlify.app</a>
                    </p>
                    <p style="font-size: 12px; color: #9ca3af; margin: 16px 0 0 0;">
                        如需取消订阅，请回复此邮件。
                    </p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

def send_email(to_email, subject, html_body):
    """Send email via Resend API."""
    if not RESEND_API_KEY:
        print("Error: RESEND_API_KEY not set")
        return False
    
    headers = {
        'Authorization': f'Bearer {RESEND_API_KEY}',
        'Content-Type': 'application/json',
    }
    
    payload = {
        'from': FROM_EMAIL,
        'to': [to_email],
        'subject': subject,
        'html': html_body,
    }
    
    try:
        resp = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"Email sent successfully to {to_email}: {result.get('id')}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send email to {to_email}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False

def main():
    if not RESEND_API_KEY:
        print("Skipping email notification: RESEND_API_KEY not configured")
        sys.exit(0)
    
    new_companies, update_date = get_new_companies()
    
    if not new_companies:
        print("No new companies found, skipping email notification")
        sys.exit(0)
    
    print(f"Found {len(new_companies)} new company(ies), sending notifications...")
    
    subscribers = load_subscribers()
    subscriber_list = subscribers.get('subscribers', [])
    
    if not subscriber_list:
        print("No subscribers found, skipping email notification")
        sys.exit(0)
    
    subject = f"Travel AI Dashboard: 发现 {len(new_companies)} 家新公司 ({update_date})"
    html_body = build_email_html(new_companies, update_date)
    
    success_count = 0
    for email in subscriber_list:
        if send_email(email, subject, html_body):
            success_count += 1

    print(f"Email notifications sent: {success_count}/{len(subscriber_list)} succeeded")

    # Clear isNew flag after successful notification
    if success_count > 0:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cleared = 0
        for company in data.get('companies', []):
            if company.get('isNew', False):
                company['isNew'] = False
                cleared += 1
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print(f"Cleared isNew flag for {cleared} company(ies)")

if __name__ == '__main__':
    main()
