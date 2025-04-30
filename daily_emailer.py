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

def load_sent_articles():
    """Load previously sent articles from cache file."""
    cache_file = Path('sent_articles_cache.json')
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
                # Remove entries older than 30 days
                now = datetime.now()
                cache = {
                    url: date for url, date in cache.items()
                    if datetime.strptime(date, '%Y-%m-%d') > (now - timedelta(days=30))
                }
                return cache
        except Exception as e:
            print(f"Error loading cache: {e}")
    return {}

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

def get_australian_ai_news():
    """Fetches relevant Australian AI news using News API."""
    try:
        print("Fetching Australian AI news using News API...")
        if not NEWS_API_KEY:
            print("Error: NEWS_API_KEY not found in environment variables.")
            return []

        newsapi = NewsApiClient(api_key=NEWS_API_KEY)

        # Get appropriate date range
        from_date, to_date = get_date_range_et()
        from_param = from_date.strftime('%Y-%m-%d')
        to_param = to_date.strftime('%Y-%m-%d')

        print(f"Searching for news from {from_param} to {to_param}")

        # Broader search queries to cast a wider net
        queries = [
            '("artificial intelligence" OR "AI") AND (Australia OR Australian)',
            'machine learning AND (Australia OR Australian)',
            '(chatbot OR "language model" OR LLM) AND (Australia OR Australian)',
            '("deep learning" OR "neural network") AND (Australia OR Australian)',
            'AI startup AND (Australia OR Australian)',
            '(AI policy OR "AI regulation") AND (Australia OR Australian)'
        ]

        # AI-related keywords for relevance checking
        ai_keywords = [
            'artificial intelligence', 'ai ', 'machine learning', 'deep learning',
            'neural network', 'chatbot', 'language model', 'llm', 'ml ', 
            'computer vision', 'nlp ', 'natural language processing',
            'ai-powered', 'ai powered', 'ai-based', 'ai based',
            'automation', 'robotics', 'algorithm'
        ]

        all_articles = []
        for query in queries:
            print(f"Querying News API with: '{query}' for date range {from_param} to {to_param}")
            try:
                response = newsapi.get_everything(
                    q=query,
                                              from_param=from_param,
                                              to=to_param,
                                              language='en',
                    sort_by='publishedAt',
                    page_size=30
                )
                
                if response['status'] == 'ok':
                    # Filter articles by publishedAt date within our date range
                    valid_articles = [
                        article for article in response['articles']
                        if article.get('publishedAt') and 
                        from_date.date() <= datetime.strptime(article['publishedAt'][:10], '%Y-%m-%d').date() <= to_date.date()
                    ]
                    all_articles.extend(valid_articles)
                    print(f"Found {len(valid_articles)} articles within date range from query: {query}")
                else:
                    print(f"Error in query '{query}': {response.get('message', 'Unknown error')}")
            
            except Exception as e:
                print(f"Error processing query '{query}': {str(e)}")
                continue

        # Deduplicate articles based on URL
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            url = article.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)

        print(f"Total unique articles found for the period: {len(unique_articles)}")

        # Enhanced relevance checking
        filtered_articles = []
        for article in unique_articles:
            title = article.get('title', '').lower()
            description = article.get('description', '').lower() if article.get('description') else ''
            content = article.get('content', '').lower() if article.get('content') else ''
            source_name = article.get('source', {}).get('name', '').lower()
            url = article.get('url', '').lower()

            # Check for Australian relevance
            is_australian = any([
                re.search(r'\b(australia|australian)\b', title),
                re.search(r'\b(australia|australian)\b', description),
                re.search(r'\b(australia|australian)\b', source_name),
                '.au' in url
            ])

            # Check for AI relevance (more strict)
            ai_relevance_score = sum(
                2 if keyword in title else  # Higher weight for title matches
                1 if keyword in description or keyword in content else
                0
                for keyword in ai_keywords
            )

            # Additional context check
            def has_strong_ai_context(text):
                # Count occurrences of AI-related terms
                ai_term_count = sum(text.count(keyword) for keyword in ai_keywords)
                # Check if AI terms appear in the first 100 characters
                ai_in_beginning = any(keyword in text[:100] for keyword in ai_keywords)
                # Check for specific phrases that indicate AI focus
                ai_focus_phrases = [
                    'artificial intelligence', 'machine learning', 'deep learning',
                    'ai technology', 'ai development', 'ai research'
                ]
                has_focus_phrase = any(phrase in text for phrase in ai_focus_phrases)
                return (ai_term_count >= 2 and (ai_in_beginning or has_focus_phrase))

            has_context = has_strong_ai_context(title + ' ' + description + ' ' + content)

            if is_australian and ai_relevance_score >= 2 and has_context:
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
                print(f"Reason: {'Not Australian' if not is_australian else ''} "
                      f"{'Low AI relevance' if ai_relevance_score < 2 else ''} "
                      f"{'Weak AI context' if not has_context else ''}")

        print(f"Total relevant articles found for the period: {len(filtered_articles)}")
        
        # Sort by publication date (most recent first) and then relevance score
        filtered_articles.sort(key=lambda x: (
            datetime.strptime(x.get('publishedAt', '2000-01-01'), '%Y-%m-%dT%H:%M:%SZ'),
            x['relevance_score']
        ), reverse=True)
        
        # Return up to 3 most recent, relevant articles
        return filtered_articles[:3]

    except Exception as e:
        print(f"Error in get_australian_ai_news: {str(e)}")
        return []


def get_tldr_articles():
    """Fetches and scrapes TLDR AI articles from yesterday (US/ET)."""
    try:
        # Get date in US/Eastern Time
        et_tz = pytz.timezone('US/Eastern')
        et_today = datetime.now(et_tz)
        date_str = et_today.strftime("%Y-%m-%d")

        url = f"https://tldr.tech/ai/{date_str}"
        print(f"Fetching articles from: {url}")

        # Add a common browser User-Agent header
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers)
        print(f"Response status code: {response.status_code}")

        if response.status_code != 200:
            print(f"Error: Received status code {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract articles from the Headlines & Launches section
        articles = []
        sections = soup.find_all('h3')
        print(f"Found {len(sections)} sections")

        # Find the Headlines & Launches section
        headlines_section = None
        for section in sections:
            if section.text.strip() == "Headlines & Launches":
                headlines_section = section
                break

        if headlines_section:
            print("Found Headlines & Launches section")
            # Get all h3 elements after Headlines & Launches until the next section
            current = headlines_section.find_next('h3')
            while current and current.text.strip() != "Research & Innovation":
                title_text = current.text.strip()
                if '(' in title_text and ')' in title_text:
                    # Split into title and reading time
                    parts = title_text.rsplit('(', 1)
                    title = parts[0].strip()
                    # Find the anchor tag containing or related to the headline (h3 is inside a)
                    anchor_tag = current.find_parent('a')
                    # Find the div.newsletter-html that is the immediate next sibling of the anchor tag
                    summary_div = anchor_tag.find_next_sibling('div', class_='newsletter-html') if anchor_tag else None
                    summary_text = summary_div.text.strip() if summary_div else '' # Get stripped text for actual use
                    # Get the URL and clean it
                    raw_url = anchor_tag['href'] if anchor_tag else '' # Get URL from the anchor tag
                    if raw_url:
                        parsed_url = urlparse(raw_url)
                        # Reconstruct URL without query parameters or fragment
                        url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, '', ''))
                    else:
                        url = ''

                    articles.append({
                        'title': title,
                        'summary': summary_text,
                        'url': url
                    })
                    print(f"Added article: {title}")
                current = current.find_next('h3')
        else:
            print("Warning: Could not find Headlines & Launches section")

        print(f"Total articles found: {len(articles)}")
        return articles
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


def format_articles_html(articles_list, section_type=""):
    """Format articles into HTML with improved error handling and messaging."""
    if not articles_list:
        message = ""
        et_tz = pytz.timezone('US/Eastern')
        et_now = datetime.now(et_tz)
        weekday = et_now.weekday()
        
        if is_weekend_et():
            message = "No updates available on weekends."
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
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        et_tz = pytz.timezone('US/Eastern')
        et_now = datetime.now(et_tz)
        msg['Subject'] = f"Daily AI News Summary - {et_now.strftime('%Y-%m-%d')} (ET)"

        # Format articles with section type for appropriate messaging
        global_html = format_articles_html(global_articles_data, "Global")
        australian_html = format_articles_html(australian_articles_data, "Australian")

        # Only send email if we have content or it's a regular weekday
        if is_weekend_et():
            print("Weekend detected. Skipping email send.")
            return

        if not global_articles_data and not australian_articles_data:
            print("No articles found for either section. Sending email with 'no updates' messages.")

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
            text-align: center;  /* Center all content by default */
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
            margin: 0 auto 15px;  /* Reduced bottom margin from 25px to 15px */
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
            width: 100px;  /* Larger size for gold badge */
            margin: 0 20px;  /* Slightly more margin for gold badge */
        }}
        .badge:hover {{
            transform: scale(1.1);
        }}
        .footer-badges {{
            text-align: center;
            margin: 20px auto;  /* Adjusted margin */
            width: 100%;
        }}
        .footer-badge {{
            display: inline-block;
            width: 60px;  /* Increased from 45px to 60px */
            height: auto;
            margin: 0 10px;
            vertical-align: middle;
        }}
        h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #5D3FD3;
            padding-bottom: 8px;
            margin: 20px auto;  /* Adjusted margin */
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
            color: #333;  /* Default text color */
        }}
        .article h4 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 1.2em;
            text-align: left;  /* Left-align article titles */
        }}
        ul {{
            margin: 15px 0;
            padding-left: 25px;
            color: #333;  /* Consistent color for lists */
        }}
        li {{
            margin-bottom: 8px;
            line-height: 1.5;
            color: #333;  /* Consistent color for list items */
        }}
        .read-more {{
            margin-top: 15px;
            text-align: left;  /* Left-align read more links */
        }}
        .article-section {{
            text-align: left;  /* Ensure article sections are left-aligned */
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
            text-align: center;  /* Center align the section titles */
            width: 80%;  /* Limit the width so the border isn't full width */
            margin-left: auto;  /* Center the element itself */
            margin-right: auto;  /* Center the element itself */
        }}
        
        /* Remove any other border/line styles that might interfere */
        .container {{
            border: none;
        }}
        
        .header {{
            border-bottom: none;
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
            <p class="header-date">{et_now.strftime('%B %d, %Y')} (ET)</p>
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
        server = smtplib.SMTP_SSL('mail.inventico.io', 465)
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


def main():
    """Main function to fetch news, generate content, and send emails."""
    try:
        print("Starting main process...")
        
        if is_weekend_et():
            print("Weekend detected in ET timezone. Skipping news updates.")
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
            num_global_articles = min(len(global_articles), 3)
            for i in range(num_global_articles):
                article = global_articles[i]
                try:
                    bullets, url = generate_bullet_points(article, is_australian=False)
                    global_bullet_points.append({'summary': bullets, 'url': url, 'title': article['title']})
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
            num_aus_articles = min(len(australian_articles), 3)
            for i in range(num_aus_articles):
                article = australian_articles[i]
                try:
                    bullets, url = generate_bullet_points(article, is_australian=True)
                    aus_bullet_points.append({'summary': bullets, 'url': url, 'title': article['title']})
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