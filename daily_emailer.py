import os
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from dotenv import load_dotenv
from newsapi import NewsApiClient
import re
from urllib.parse import urlparse, urlunparse # Added for URL cleaning
import pytz # Added pytz import
import html # Added for escaping HTML in email
import json
from pathlib import Path
from email.utils import formataddr
import time

# Load environment variables
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')  # Create model once

# Email configuration
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
# Split recipient emails by comma for different formats
# Filter out empty strings that might result from trailing commas
RECIPIENT_EMAILS_BULLETS = [email.strip() for email in os.getenv('RECIPIENT_EMAIL_BULLETS', '').split(',') if email.strip()]
NEWS_API_KEY = os.getenv('NEWS_API_KEY') # Added News API Key loading

def save_sent_articles(cache):
    """Save sent articles to cache file."""
    cache_file = Path('sent_articles_cache.json')
    try:
        with open(cache_file, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"Error saving cache: {e}")

def is_weekend_et():
    """Check if current US/Eastern time is a weekend."""
    et_tz = pytz.timezone('US/Eastern')
    et_now = datetime.now(et_tz)
    # 5 = Saturday, 6 = Sunday
    return et_now.weekday() in [5, 6]

def get_date_range_et():
    """Get appropriate date range based on current day in ET."""
    et_tz = pytz.timezone('US/Eastern')
    et_now = datetime.now(et_tz)
    weekday = et_now.weekday()  # 0 = Monday, 1 = Tuesday, etc.
    
    to_date = et_now
    if weekday == 0:  # If Monday
        # Look back 72 hours to cover the weekend
        from_date = et_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=3)
        print("Monday detected - fetching news from the past 72 hours")
    else:
        # Regular 24-hour window
        from_date = et_now.replace(hour=0, minute=0, second=0, microsecond=0)
        print("Regular day - fetching news from the past 24 hours")
    
    return from_date, to_date

def get_australian_date_range():
    """Get weekly date range for Australian news (last 7 days)."""
    et_tz = pytz.timezone('US/Eastern')
    et_now = datetime.now(et_tz)
    
    to_date = et_now
    from_date = et_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
    print("Fetching Australian news from the past 7 days")
    
    return from_date, to_date

def get_australian_ai_news():
    """Fetches relevant Australian AI news using News API."""
    try:
        print("Fetching Australian AI news using News API...")
        if not NEWS_API_KEY:
            print("Error: NEWS_API_KEY not found in environment variables.")
            return []

        newsapi = NewsApiClient(api_key=NEWS_API_KEY)

        # Get weekly date range for Australian news
        from_date, to_date = get_australian_date_range()
        from_param = from_date.strftime('%Y-%m-%d')
        to_param = to_date.strftime('%Y-%m-%d')

        print(f"Searching for news from {from_param} to {to_param}")

        # AI-related keywords for relevance checking (broadened)
        ai_keywords = [
            'artificial intelligence', 'ai ', 'machine learning', 'deep learning',
            'neural network', 'chatbot', 'language model', 'llm', 'ml ',
            'computer vision', 'nlp ', 'natural language processing',
            'ai-powered', 'ai powered', 'ai-based', 'ai based',
            'automation', 'robotics', 'algorithm'
        ]

        # Combined search query to reduce API calls
        combined_query = '''
            ("artificial intelligence" OR "AI" OR "machine learning" OR "deep learning" OR 
            "neural network" OR "chatbot" OR "language model" OR "LLM" OR 
            "AI startup" OR "AI policy" OR "AI regulation")
            AND 
            (Australia OR Australian OR Sydney OR Melbourne OR Brisbane OR Perth OR Adelaide)
        '''

        print(f"Querying News API with combined query for date range {from_param} to {to_param}")
        try:
            response = newsapi.get_everything(
                q=combined_query,
                from_param=from_param,
                to=to_param,
                language='en',
                sort_by='publishedAt',
                page_size=100  # Increased to get more results in one call
            )
            
            if response['status'] == 'ok':
                # Filter articles by publishedAt date within our date range
                valid_articles = [
                    article for article in response['articles']
                    if article.get('publishedAt') and 
                    from_date.date() <= datetime.strptime(article['publishedAt'][:10], '%Y-%m-%d').date() <= to_date.date()
                ]
                print(f"Found {len(valid_articles)} articles within date range")
            else:
                print(f"Error in query: {response.get('message', 'Unknown error')}")
                return []
        
        except Exception as e:
            print(f"Error processing query: {str(e)}")
            return []

        # Deduplicate articles based on URL
        seen_urls = set()
        unique_articles = []
        for article in valid_articles:
            url = article.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)

        print(f"Total unique articles found for the period: {len(unique_articles)}")

        # Whitelist of trusted Australian news domains
        australian_sources = [
            'abc.net.au', 'smh.com.au', 'theage.com.au', 'itnews.com.au',
            'afr.com', 'news.com.au', 'drive.com.au', 'sbs.com.au', 'theguardian.com.au'
        ]
        aus_terms = ['australia', 'australian', 'sydney', 'melbourne', 'brisbane', 'perth', 'adelaide']
        def is_australian(article):
            url = article.get('url', '').lower()
            source_name = article.get('source', {}).get('name', '').lower()
            title = article.get('title', '').lower()
            description = article.get('description', '').lower() if article.get('description') else ''
            content = article.get('content', '').lower() if article.get('content') else ''
            domain = urlparse(url).netloc
            # .au domain or whitelisted source
            if domain.endswith('.au') or any(src in domain for src in australian_sources):
                return True
            # Australia/cities in title/desc/content/source
            if any(term in title for term in aus_terms) or \
               any(term in description for term in aus_terms) or \
               any(term in content for term in aus_terms) or \
               any(term in source_name for term in aus_terms):
                return True
            return False

        # Enhanced relevance checking
        filtered_articles = []
        for article in unique_articles:
            title = article.get('title', '').lower()
            description = article.get('description', '').lower() if article.get('description') else ''
            content = article.get('content', '').lower() if article.get('content') else ''
            source_name = article.get('source', {}).get('name', '').lower()
            url = article.get('url', '').lower()

            # Use improved Australian relevance
            is_aus = is_australian(article)

            # Check for AI relevance (more strict)
            ai_relevance_score = sum(
                2 if keyword in title else  # Higher weight for title matches
                1 if keyword in description or keyword in content else
                0
                for keyword in ai_keywords
            )

            # Additional context check
            def has_strong_ai_context(text):
                ai_term_count = sum(text.count(keyword) for keyword in ai_keywords)
                ai_in_beginning = any(keyword in text[:100] for keyword in ai_keywords)
                ai_focus_phrases = [
                    'artificial intelligence', 'machine learning', 'deep learning',
                    'ai technology', 'ai development', 'ai research'
                ]
                has_focus_phrase = any(phrase in text for phrase in ai_focus_phrases)
                return (ai_term_count >= 2 and (ai_in_beginning or has_focus_phrase))

            has_context = has_strong_ai_context(title + ' ' + description + ' ' + content)

            if is_aus and ai_relevance_score >= 2 and has_context:
                filtered_articles.append({
                    'title': article.get('title', ''),
                    'summary': description if description else 'No description available.',
                    'content': content,
                    'url': article.get('url', ''),
                    'publishedAt': article.get('publishedAt', ''),
                    'relevance_score': ai_relevance_score
                })
                print(f"Added (Relevant): {article.get('title', '')}")
                print(f"Source: {source_name}")
                print(f"AI relevance score: {ai_relevance_score}")
                print(f"Published at: {article.get('publishedAt', '')}")
            else:
                print(f"Skipped: {article.get('title', '')}")
                print(f"Reason: {'Not Australian' if not is_aus else ''} "
                      f"{'Low AI relevance' if ai_relevance_score < 2 else ''} "
                      f"{'Weak AI context' if not has_context else ''}")

        print(f"Total relevant articles found for the period: {len(filtered_articles)}")
        
        # Sort by publication date (most recent first) and then relevance score
        filtered_articles.sort(key=lambda x: (
            datetime.strptime(x.get('publishedAt', '2000-01-01'), '%Y-%m-%dT%H:%M:%SZ'),
            x['relevance_score']
        ), reverse=True)
        
        return filtered_articles

    except Exception as e:
        print(f"Error in get_australian_ai_news: {str(e)}")
        return []


def get_tldr_articles():
    """Fetches and scrapes TLDR AI articles from the past week (Monday-Friday only)."""
    try:
        # Get date range in US/Eastern Time
        et_tz = pytz.timezone('US/Eastern')
        et_now = datetime.now(et_tz)
        
        # Calculate the date range (past 7 days)
        end_date = et_now
        start_date = et_now - timedelta(days=7)
        
        print(f"Fetching TLDR articles from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        all_articles = []
        current_date = start_date
        
        # Iterate through each day in the range
        while current_date <= end_date:
            # Skip weekends (5 = Saturday, 6 = Sunday)
            if current_date.weekday() >= 5:
                print(f"Skipping weekend day: {current_date.strftime('%Y-%m-%d')}")
                current_date += timedelta(days=1)
                continue
                
            date_str = current_date.strftime("%Y-%m-%d")
            url = f"https://tldr.tech/ai/{date_str}"
            print(f"\nFetching articles from: {url}")

            # Add a common browser User-Agent header
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers)
            print(f"Response status code: {response.status_code}")

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                sections = soup.find_all('h3')
                print(f"Found {len(sections)} sections for {date_str}")

                # Find the Headlines & Launches section
                headlines_section = None
                for section in sections:
                    if section.text.strip() == "Headlines & Launches":
                        headlines_section = section
                        break

                if headlines_section:
                    print(f"Found Headlines & Launches section for {date_str}")
                    # Get all h3 elements after Headlines & Launches until the next section
                    current = headlines_section.find_next('h3')
                    articles_for_day = 0
                    
                    while current and current.text.strip() != "Research & Innovation":
                        title_text = current.text.strip()
                        if '(' in title_text and ')' in title_text:
                            # Split into title and reading time
                            parts = title_text.rsplit('(', 1)
                            title = parts[0].strip()
                            
                            # Find the anchor tag containing or related to the headline
                            anchor_tag = current.find_parent('a')
                            if not anchor_tag:
                                print(f"Warning: No anchor tag found for article: {title}")
                                current = current.find_next('h3')
                                continue
                                
                            # Find the div.newsletter-html that is the immediate next sibling
                            summary_div = anchor_tag.find_next_sibling('div', class_='newsletter-html')
                            if not summary_div:
                                print(f"Warning: No summary div found for article: {title}")
                                current = current.find_next('h3')
                                continue
                                
                            summary_text = summary_div.text.strip()
                            if not summary_text:
                                print(f"Warning: Empty summary for article: {title}")
                                current = current.find_next('h3')
                                continue
                            
                            # Get the URL and clean it
                            raw_url = anchor_tag['href']
                            if not raw_url:
                                print(f"Warning: No URL found for article: {title}")
                                current = current.find_next('h3')
                                continue
                                
                            parsed_url = urlparse(raw_url)
                            url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, '', ''))

                            all_articles.append({
                                'title': title,
                                'summary': summary_text,
                                'url': url,
                                'date': date_str,
                                'day': current_date.strftime('%A')  # Add day name for better organization
                            })
                            articles_for_day += 1
                            print(f"Added article {articles_for_day} for {date_str}: {title}")
                            
                            # Safety check - TLDR typically has 3 articles per day
                            if articles_for_day >= 3:
                                print(f"Reached 3 articles for {date_str}, moving to next day")
                                break
                                
                        current = current.find_next('h3')
                    
                    print(f"Total articles found for {date_str}: {articles_for_day}")
                else:
                    print(f"Warning: Could not find Headlines & Launches section for {date_str}")
            else:
                print(f"Warning: Could not fetch TLDR for {date_str} (Status code: {response.status_code})")

            # Move to next day
            current_date += timedelta(days=1)

        print(f"\nTotal articles found across all weekdays: {len(all_articles)}")
        print("Articles by day:")
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            day_articles = [a for a in all_articles if a['day'] == day]
            print(f"{day}: {len(day_articles)} articles")
            
        return all_articles
    except Exception as e:
        print(f"Error in get_tldr_articles: {str(e)}")
        raise


def generate_bullet_points(article, is_australian=False):
    """Generates 5 bullet points summarizing an article."""
    try:
        # Construct the prompt for generating 5 key bullet points
        guidelines = """
Guidelines:
1. Summarize the provided article into exactly 5 key bullet points.
2. Focus on the most important facts and takeaways for a general consumer audience.
3. Each bullet point should be concise and easy to understand.
4. Do not include introductory or concluding sentences, just the bullet points.
5. Start each bullet point with a standard bullet character (e.g., '-', '*')."""

        if is_australian:
            guidelines += "\n6. Ensure the Australian context is clear if relevant to the key points."
            prompt_prefix = "Australian News: "
            # Prioritize using 'content' if available and substantially longer
            content_text = article.get('content', '') or ''
            description_text = article.get('summary', '') or '' # 'summary' key holds description
            if content_text and len(content_text) > len(description_text) + 20:
                 summary_to_use = content_text
                 source_used = 'content'
            else:
                 summary_to_use = description_text
                 source_used = 'summary/description'
        else:
            prompt_prefix = "Global News: "
            # For global news, use the scraped summary
            summary_to_use = article.get('summary', '')
            source_used = 'summary/description'

        prompt = f"""Generate 5 key bullet points summarizing the following article for a consumer audience.
{guidelines}

Article:
{prompt_prefix}{article['title']}
{summary_to_use}
"""
        print(f"Generating bullet points for article: {article['title']} (Using {source_used})")
        response = model.generate_content(prompt)
        print("Bullet points generated successfully")
        # Return the raw text (bullet points) and the URL
        return response.text, article['url']
    except Exception as e:
        print(f"Error generating bullet points: {str(e)}")
        raise


def format_global_articles_by_day(articles_list):
    """Format global articles grouped by weekday for HTML email."""
    if not articles_list:
        return "<div class='no-updates'><p style='color: #666; font-style: italic;'>No global AI updates available for this week.</p></div>"
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    html_output = ""
    for day in days:
        day_articles = [a for a in articles_list if a.get('day') == day]
        if not day_articles:
            continue
        html_output += f"<h3 style='color:#5D3FD3;margin-top:30px;margin-bottom:10px;'>{day}</h3>"
        for article in day_articles:
            escaped_summary = html.escape(str(article.get('summary', '')).strip())
            summary_lines = escaped_summary.split('\n')
            bullet_lines = []
            for line in summary_lines:
                line = line.strip()
                if line and not line.startswith('Here are') and not line.startswith('Anthropic'):
                    line = re.sub(r'<[^>]*>', '', line)
                    line = re.sub(r'style="[^"]*"', '', line)
                    bullet_lines.append(line)
            list_items = "".join(
                f'<li style="color: #333;">{line.strip("-* ")}</li>'
                for line in bullet_lines
            )
            html_output += f"""
                <div class='article'>
                    <h4>{html.escape(article.get('title', 'No Title'))}</h4>
                    <ul style='color: #333;'>{list_items}</ul>
                    <p class='read-more'><a href='{html.escape(article.get('url', '#'))}' target='_blank'>Read more →</a></p>
                </div>
            """
    return html_output or "<div class='no-updates'><p style='color: #666; font-style: italic;'>No global AI updates available for this week.</p></div>"

def format_articles_html(articles_list, section_type=""):
    """Format articles into HTML with improved error handling and messaging."""
    if not articles_list:
        message = ""
        et_tz = pytz.timezone('US/Eastern')
        et_now = datetime.now(et_tz)
        weekday = et_now.weekday()
        
        if is_weekend_et():
            if section_type == "Global":
                message = "No global AI updates available on weekends."
            else:
                message = "No Australian AI updates available on weekends."
        elif section_type == "Australian" and weekday == 0:
            message = "No Australian AI news found for the weekend period."
        elif section_type == "Australian":
            message = "No Australian AI news found for today."
        elif section_type == "Global":
            message = "No global AI updates available for today."
        else:
            message = "No updates found."
            
        return f"""
            <div class="no-updates">
                <p style="color: #666; font-style: italic;">{message}</p>
            </div>
        """

    html_output = ""
    for article in articles_list:
        escaped_summary = html.escape(str(article.get('summary', '')).strip())
        summary_lines = escaped_summary.split('\n')
        
        # Filter and clean bullet points, ensuring consistent color
        bullet_lines = []
        for line in summary_lines:
            line = line.strip()
            if line and not line.startswith('Here are') and not line.startswith('Anthropic'):
                # Remove any existing HTML color styling
                line = re.sub(r'<[^>]*>', '', line)  # Remove any HTML tags
                line = re.sub(r'style="[^"]*"', '', line)  # Remove any style attributes
                bullet_lines.append(line)

        # Convert to HTML list items with consistent styling
        list_items = "".join(
            f'<li style="color: #333;">{line.strip("-* ")}</li>'
            for line in bullet_lines
        )

        html_output += f"""
            <div class="article">
                <h4>{html.escape(article.get('title', 'No Title'))}</h4>
                <ul style="color: #333;">{list_items}</ul>
                <p class="read-more"><a href="{html.escape(article.get('url', '#'))}" target="_blank">Read more →</a></p>
            </div>
        """
    return html_output

def send_bullet_points_email(global_articles_data, australian_articles_data):
    """Sends the bullet point summaries as an HTML email."""
    if not RECIPIENT_EMAILS_BULLETS or not any(RECIPIENT_EMAILS_BULLETS):
        print("Error: No recipient emails configured for bullet points (RECIPIENT_EMAIL_BULLETS).")
        return

    try:
        print(f"Preparing bullet points email via BCC to {len(RECIPIENT_EMAILS_BULLETS)} recipients.")
        msg = MIMEMultipart()
        msg['From'] = formataddr(("Responsible AI Australia", SENDER_EMAIL))
        msg['To'] = ", ".join(RECIPIENT_EMAILS_BULLETS)
        
        # Get current time in both ET and AET
        et_tz = pytz.timezone('US/Eastern')
        aet_tz = pytz.timezone('Australia/Sydney')
        et_now = datetime.now(et_tz)
        aet_now = datetime.now(aet_tz)
        
        # Use AET for display, but keep ET in subject for reference
        msg['Subject'] = f"Weekly AI News Summary - {et_now.strftime('%Y-%m-%d')} (ET)"
        
        # Format articles with section type for appropriate messaging
        global_html = format_global_articles_by_day(global_articles_data)
        australian_html = format_articles_html(australian_articles_data, "Australian")

        # HTML Body with improved styling and logo
        body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily AI News Summary</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 0;
            color: #333;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #ffffff;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .header {{
            text-align: center;
            padding: 20px 0;
            border-bottom: 2px solid #eee;
            margin: 0 auto;
        }}
        .logo {{
            display: block;
            max-width: 180px;
            height: auto;
            margin: 0 auto 15px;
        }}
        .badges-row {{
            display: inline-block;
            text-align: center;
            margin: 15px auto;
            width: 100%;
        }}
        .badge {{
            display: inline-block;
            width: 80px;
            height: auto;
            margin: 0 15px;
            vertical-align: middle;
            transition: transform 0.2s;
        }}
        .badge.gold {{
            width: 100px;
            margin: 0 20px;
        }}
        .badge:hover {{
            transform: scale(1.1);
        }}
        .footer-badges {{
            text-align: center;
            margin: 20px auto;
            width: 100%;
        }}
        .footer-badge {{
            display: inline-block;
            width: 60px;
            height: auto;
            margin: 0 10px;
            vertical-align: middle;
        }}
        h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #5D3FD3;
            padding-bottom: 8px;
            margin: 20px auto;
            font-size: 1.6em;
            text-align: center;
            max-width: 80%;
        }}
        .date {{
            color: #666;
            text-align: center;
            margin: 15px 0;
        }}
        .article {{
            background-color: #fff;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 5px;
            border-left: 4px solid #5D3FD3;
            color: #333;
        }}
        .article h4 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 1.2em;
            text-align: left;
        }}
        ul {{
            margin: 15px 0;
            padding-left: 25px;
            color: #333;
        }}
        li {{
            margin-bottom: 8px;
            line-height: 1.5;
            color: #333;
        }}
        .read-more {{
            margin-top: 15px;
            text-align: left;
        }}
        .article-section {{
            text-align: left;
        }}
        .footer-links {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
        }}
        .footer-links a {{
            color: #5D3FD3;
            text-decoration: none;
            font-weight: 500;
        }}
        .footer-links a:hover {{
            text-decoration: underline;
            color: #4B0082;
        }}
        .divider {{
            color: #666;
            margin: 0 10px;
        }}
        .no-updates {{
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .header-title {{
            color: #2c3e50;
            font-size: 2em;
            margin: 30px 0 10px 0;
            text-align: center;
        }}
        .header-date {{
            color: #666;
            text-align: center;
            margin: 0 0 40px 0;
            font-size: 1.1em;
        }}
        .section-title {{
            color: #2c3e50;
            font-size: 1.6em;
            margin: 40px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #5D3FD3;
            text-align: center;
            width: 80%;
            margin-left: auto;
            margin-right: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a href="https://www.responsibleaiaustralia.com.au/" class="header-link" target="_blank">
                <img src="cid:logo" alt="Logo" class="logo">
            </a>
            <div class="badges-row">
                <img src="cid:bronzeBadge" alt="Bronze Badge" class="badge">
                <img src="cid:goldBadge" alt="Gold Badge" class="badge gold">
                <img src="cid:silverBadge" alt="Silver Badge" class="badge">
            </div>
            <h1 class="header-title">Daily AI News Summary</h1>
            <p class="header-date">{aet_now.strftime('%B %d, %Y')} (AET)</p>
        </div>

        <h2 class="section-title">Global AI Updates</h2>
        <div class="article-section">
            {global_html}
        </div>

        <h2 class="section-title">Australian AI Updates</h2>
        <div class="article-section">
            {australian_html}
        </div>

        <div class="footer">
            <div class="footer-badges">
                <img src="cid:bronzeBadge" alt="Bronze Badge" class="footer-badge">
                <img src="cid:goldBadge" alt="Gold Badge" class="footer-badge">
                <img src="cid:silverBadge" alt="Silver Badge" class="footer-badge">
            </div>
            <div class="footer-links">
                <a href="https://www.responsibleaiaustralia.com.au/" target="_blank">Visit Responsible AI Australia</a>
                <span class="divider">|</span>
                <a href="https://www.responsibleaiaustralia.com.au/contact" target="_blank">Contact Us</a>
            </div>
        </div>
    </div>
</body>
</html>
"""
        # Add HTML content
        msg_html = MIMEText(body, 'html', 'utf-8')
        msg.attach(msg_html)

        # Add logo image
        with open('assets/image001.png', 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-ID', '<logo>')
            img.add_header('Content-Disposition', 'inline', filename='image001.png')
            msg.attach(img)

        # Add badge images
        badge_files = ['goldBadge', 'silverBadge', 'bronzeBadge']
        for badge in badge_files:
            with open(f'assets/badges/{badge}.png', 'rb') as f:
                img = MIMEImage(f.read())
                img.add_header('Content-ID', f'<{badge}>')
                img.add_header('Content-Disposition', 'inline', filename=f'{badge}.png')
                msg.attach(img)

        print("Connecting to SMTP server for bullet points email...")
        server = smtplib.SMTP_SSL('mail.responsibleaiaustralia.com.au', 465)
        print("Logging in...")
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        print("Sending bullet points email...")
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS_BULLETS, msg.as_string())
        print("Closing connection...")
        server.quit()
        print("Bullet points email sent successfully!")
    except Exception as e:
        print(f"Error sending bullet points email: {str(e)}")
        raise

def should_send_email():
    """Check if we should send the email (only on Mondays, Australia/Sydney time)."""
    aet_tz = pytz.timezone('Australia/Sydney')
    aet_now = datetime.now(aet_tz)
    return aet_now.weekday() == 0  # 0 = Monday

def main():
    """Main function to fetch news, generate content, and send emails."""
    try:
        print("Starting main process...")
        # Only run on Mondays (Australia/Sydney time)
        if not should_send_email():
            print("Not Monday in Australia/Sydney - skipping email generation.")
            return
        
        # Lists to hold generated content
        global_bullet_points = []
        aus_bullet_points = []

        # Get global articles
        print("\nFetching global articles...")
        try:
            global_articles = get_tldr_articles()
        except Exception as e:
            print(f"Error fetching global articles: {e}")
            global_articles = []

        if global_articles:
            print("\nGenerating global content...")
            # Sort articles by date (most recent first)
            global_articles.sort(key=lambda x: x.get('date', ''), reverse=True)
            for article in global_articles:
                try:
                    bullets, url = generate_bullet_points(article, is_australian=False)
                    global_bullet_points.append({'summary': bullets, 'url': url, 'title': article['title'], 'day': article.get('day')})
                    time.sleep(3)
                except Exception as e:
                    print(f"Failed to generate bullet points for global article '{article.get('title', 'N/A')}': {e}")

        # Get Australian articles
        print("\nFetching Australian articles...")
        try:
            australian_articles = get_australian_ai_news()
        except Exception as e:
            print(f"Error fetching Australian articles: {e}")
            australian_articles = []

        if australian_articles:
            print("\nGenerating Australian content...")
            # Sort by relevance score and date
            australian_articles.sort(key=lambda x: (x['relevance_score'], x['publishedAt']), reverse=True)
            # Take top 5 most relevant articles
            num_aus_articles = min(len(australian_articles), 5)
            for i in range(num_aus_articles):
                article = australian_articles[i]
                try:
                    bullets, url = generate_bullet_points(article, is_australian=True)
                    aus_bullet_points.append({'summary': bullets, 'url': url, 'title': article['title']})
                    time.sleep(3)
                except Exception as e:
                    print(f"Failed to generate bullet points for Australian article '{article.get('title', 'N/A')}': {e}")

        # Send bullet points email (HTML)
        if RECIPIENT_EMAILS_BULLETS:
            print("\nSending bullet points email...")
            try:
                send_bullet_points_email(global_bullet_points, aus_bullet_points)
            except Exception as e:
                print(f"Failed to send bullet points email: {e}")
        else:
            print("\nSkipping bullet points email: No recipients configured (RECIPIENT_EMAIL_BULLETS).")

        print("\nProcess completed successfully!")

    except Exception as e:
        print(f"Error in main: {str(e)}")
        raise


if __name__ == "__main__":
    main()