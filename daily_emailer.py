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

def get_australian_ai_news():
    """Fetches relevant Australian AI news from the past 7 days using News API."""
    try:
        print("Fetching Australian AI news using News API...")
        if not NEWS_API_KEY:
            print("Error: NEWS_API_KEY not found in environment variables.")
            return []

        newsapi = NewsApiClient(api_key=NEWS_API_KEY)

        # Calculate dates for the past 7 days based on US/Eastern Time
        et_tz = pytz.timezone('US/Eastern')
        et_now = datetime.now(et_tz)
        to_date = et_now
        from_date = to_date - timedelta(days=7)
        from_param = from_date.strftime('%Y-%m-%d')
        to_param = to_date.strftime('%Y-%m-%d')

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
            print(f"Querying News API with: '{query}'")
            try:
                response = newsapi.get_everything(
                    q=query,
                                              from_param=from_param,
                                              to=to_param,
                                              language='en',
                                              sort_by='relevancy',
                    page_size=30  # Increased page size for more candidates
                )
                
                if response['status'] == 'ok':
                    all_articles.extend(response['articles'])
                    print(f"Found {len(response['articles'])} articles for query: {query}")
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

        print(f"Total unique articles found: {len(unique_articles)}")

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

            # Check for AI relevance
            is_ai_related = any(
                keyword in title or 
                keyword in description or 
                keyword in content
                for keyword in ai_keywords
            )

            # Additional context check to ensure the article is actually about AI
            def has_strong_ai_context(text):
                # Count occurrences of AI-related terms
                ai_term_count = sum(text.count(keyword) for keyword in ai_keywords)
                # Check if AI terms appear in the first 100 characters (likely more important)
                ai_in_beginning = any(keyword in text[:100] for keyword in ai_keywords)
                return ai_term_count >= 2 or ai_in_beginning

            has_context = has_strong_ai_context(title + ' ' + description + ' ' + content)

            if is_australian and is_ai_related and has_context:
                filtered_articles.append({
                    'title': article.get('title', ''),
                        'summary': description if description else 'No description available.',
                        'content': content,
                    'url': article.get('url', '')
                    })
                print(f"Added (Relevant): {article.get('title', '')}")
                print(f"Source: {source_name}")
                print(f"AI keywords found in: {'title' if is_ai_related else ''} {'description' if any(k in description for k in ai_keywords) else ''}")
            else:
                print(f"Skipped: {article.get('title', '')}")
                print(f"Reason: {'Not Australian' if not is_australian else ''} {'Not AI-related' if not is_ai_related else ''} {'Weak AI context' if not has_context else ''}")

        print(f"Total relevant articles found: {len(filtered_articles)}")
        
        # Sort by relevance (prioritize articles with AI in title)
        filtered_articles.sort(key=lambda x: sum(k in x['title'].lower() for k in ai_keywords), reverse=True)
        
        # Return up to 3 most relevant articles
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

        # --- Helper function to format articles into HTML bullet points ---
        def format_articles_html(articles_list):
            if not articles_list:
                return "<p>No updates found.</p>"
            html_output = ""
            for article in articles_list:
                escaped_summary = html.escape(str(article.get('summary', '')).strip())
                # Remove the introductory line and clean up bullet points
                summary_lines = escaped_summary.split('\n')
                # Filter out the introductory lines and empty lines
                bullet_lines = [line.strip() for line in summary_lines 
                               if line.strip() 
                               and not line.startswith('Here are') 
                               and not line.startswith('Anthropic')]
                # Convert to HTML list items, removing any bullet characters
                list_items = "".join(f"<li>{line.strip('-* ')}</li>" 
                                    for line in bullet_lines)

                html_output += f"""
                    <div class="article">
                    <h4>{html.escape(article.get('title', 'No Title'))}</h4>
                    <ul>{list_items}</ul>
                        <p class="read-more"><a href="{html.escape(article.get('url', '#'))}" target="_blank">Read more →</a></p>
                    </div>
                """
            return html_output

        global_html = format_articles_html(global_articles_data)
        australian_html = format_articles_html(australian_articles_data)

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
            text-align: left;  /* Ensure article content is left-aligned */
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
            text-align: left;  /* Ensure bullet points are left-aligned */
        }}
        li {{
            margin-bottom: 8px;
            line-height: 1.5;
            text-align: left;  /* Ensure list items are left-aligned */
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
            <h2>Daily AI News Summary</h2>
            <p class="date">{et_now.strftime('%B %d, %Y')} (ET)</p>
        </div>

    <h2>Global AI Updates</h2>
    <div class="article-section">
        {global_html}
    </div>

    <h2>Australian AI Updates</h2>
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


def is_weekend_et():
    """Check if current US/Eastern time is a weekend."""
    et_tz = pytz.timezone('US/Eastern')
    et_now = datetime.now(et_tz)
    # 5 = Saturday, 6 = Sunday
    return et_now.weekday() in [5, 6]


def main():
    """Main function to fetch news, generate content, and send emails."""
    try:
        print("Starting main process...")
        
        # Check if it's weekend in ET
        if is_weekend_et():
            print("Weekend detected in ET timezone. Skipping news updates.")
            return

        # Lists to hold generated content (removed LinkedIn-related lists)
        global_bullet_points = []
        aus_bullet_points = []

        # Get global articles
        print("\nFetching global articles...")
        global_articles = get_tldr_articles()

        if not global_articles:
            print("No global articles found for today.")
        else:
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
        australian_articles = get_australian_ai_news()

        if not australian_articles:
            print("No Australian articles found.")
        else:
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
             if global_bullet_points or aus_bullet_points:
                 print("\nSending bullet points email...")
                 try:
                     send_bullet_points_email(global_bullet_points, aus_bullet_points)
                 except Exception as e:
                     print(f"Failed to send bullet points email: {e}")
             else:
                 print("\nNo bullet point content generated to send.")
        else:
             print("\nSkipping bullet points email: No recipients configured (RECIPIENT_EMAIL_BULLETS).")

        print("\nProcess completed successfully!")

    except Exception as e:
        print(f"Error in main: {str(e)}")
        raise


if __name__ == "__main__":
    main()