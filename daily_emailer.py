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
RECIPIENT_EMAILS_LINKEDIN = [email.strip() for email in os.getenv('RECIPIENT_EMAIL_LINKEDIN', '').split(',') if email.strip()]
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
        from_date = to_date - timedelta(days=7) # Fetch news from the past week
        from_param = from_date.strftime('%Y-%m-%d')
        to_param = to_date.strftime('%Y-%m-%d')

        # Refined search query for AI news specifically related to Australia
        query = '("Australian AI" OR "AI in Australia" OR ("artificial intelligence" AND Australia))'
        print(f"Querying News API with: '{query}', from: {from_param}, to: {to_param}")

        all_articles = newsapi.get_everything(q=query,
                                              from_param=from_param,
                                              to=to_param,
                                              language='en',
                                              sort_by='relevancy',
                                              page_size=20) # Fetch more results for better filtering

        filtered_articles = []
        if all_articles['status'] == 'ok':
            print(f"News API returned {all_articles['totalResults']} raw articles.")
            for article in all_articles['articles']:
                title = article.get('title', '')
                description = article.get('description', '') or '' # Ensure description is string
                url = article.get('url', '')
                source_name = article.get('source', {}).get('name', '')
                content = article.get('content', '') or '' # Get content field, ensure string

                # Check for Australian relevance in title, description, source, or URL
                is_relevant = False
                if re.search(r'\b(Australia|Australian)\b', title, re.IGNORECASE):
                    is_relevant = True
                elif description and re.search(r'\b(Australia|Australian)\b', description, re.IGNORECASE):
                     is_relevant = True
                elif re.search(r'\b(Australia|Australian)\b', source_name, re.IGNORECASE):
                     is_relevant = True
                elif '.au' in url:
                     is_relevant = True

                if is_relevant:
                    filtered_articles.append({
                        'title': title,
                        # Store both description and content
                        'summary': description if description else 'No description available.',
                        'content': content,
                        'url': url
                    })
                    print(f"Added (Relevant): {title}")
                else:
                     print(f"Skipped (Not relevant): {title} | Source: {source_name}") # Log skipped articles

                # Stop if we have enough relevant articles
                if len(filtered_articles) >= 3:
                    break
        else:
            print(f"Error fetching from News API: {all_articles.get('message', 'Unknown error')}")
            return []

        print(f"Total relevant Australian articles found and filtered: {len(filtered_articles)}")
        # Return up to 3 relevant articles (already ensured by the break condition)
        return filtered_articles

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


def generate_linkedin_post(article, is_australian=False):
    """Generates a LinkedIn post based on an article."""
    try:
        # Construct the prompt for LinkedIn post (from daily_emailer.py)
        guidelines = """
Guidelines:
1. Begin with an engaging hook that captures the core theme of the article.
2. Summarise the main point or breakthrough, highlighting its relevance or potential impact.
3. Briefly reflect on why this development matters in the context of ethical, safe, or transparent AI.
4. Tie it back to "responsble.ai" (notice that its responsble, NOT responsible), and its mission of supporting responsible, standards-based AI certification."""

        if is_australian:
            guidelines += "\n5. Explicitly mention the Australian context of this news (e.g., using 'Australia', 'Australian', 'Aussie')."
            guidelines += "\n6. End with a thoughtful question that invites discussion."
            guidelines += "\n7. Keep it around 200 words."
            guidelines += "\n8. Use 2 relevant hashtags and 1 well-placed emoji."
            prompt_prefix = "Australian AI Update: "
            # Prioritize using 'content' if available and substantially longer
            content_text = article.get('content', '') or ''
            description_text = article.get('summary', '') or '' # 'summary' key holds description
            if content_text and len(content_text) > len(description_text) + 20:
                 summary_to_use = content_text
                 source_used = 'content' # Keep track for potential debugging
            else:
                 summary_to_use = description_text
                 source_used = 'summary/description' # Keep track for potential debugging
        else:
            guidelines += "\n5. End with a thoughtful question that invites discussion."
            guidelines += "\n6. Keep it around 200 words."
            guidelines += "\n7. Use 2 relevant hashtags and 1 well-placed emoji."
            prompt_prefix = "" # No prefix for global posts
            # For global news, use the scraped summary
            summary_to_use = article.get('summary', '')
            source_used = 'summary/description' # Indicate source for consistency

        # LinkedIn prompt structure (from daily_emailer.py)
        prompt = f"""Write a professional, natural-sounding LinkedIn post based on the following article.
{guidelines}

Tone: Authentic, clear, and conversational — like a seasoned Australian copywriter writing for a professional but curious audience. No "-"

Article:
{prompt_prefix}{article['title']}
{summary_to_use}
"""
        print(f"Generating LinkedIn post for article: {article['title']} (Using {source_used})")
        response = model.generate_content(prompt)
        print("Post generated successfully")
        # Return formatted post string
        return f"{response.text}\n\nRead more: {article['url']}"
    except Exception as e:
        print(f"Error generating LinkedIn post: {str(e)}")
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
        }}
        .header {{
            text-align: center;
            padding: 20px 0;
            border-bottom: 2px solid #eee;
        }}
        .logo {{
            max-width: 200px;
            height: auto;
            margin-bottom: 20px;
        }}
        h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #5D3FD3;
            padding-bottom: 8px;
            margin-top: 30px;
            font-size: 1.6em;
        }}
        .article {{
            background-color: #fff;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 5px;
            border-left: 4px solid #5D3FD3;
        }}
        h4 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 1.2em;
        }}
        ul {{
            margin: 15px 0;
            padding-left: 25px;
        }}
        li {{
            margin-bottom: 8px;
            line-height: 1.5;
        }}
        .read-more {{
            margin-top: 15px;
        }}
        .read-more a {{
            color: #5D3FD3;
            text-decoration: none;
            font-weight: 500;
        }}
        .read-more a:hover {{
            text-decoration: underline;
            color: #4B0082;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
            border-top: 1px solid #eee;
            margin-top: 30px;
        }}
        .header-link {{
            display: block;
            text-decoration: none;
            margin-bottom: 10px;
        }}
        .header-link:hover img {{
            opacity: 0.9;
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
            <h2 style="margin-top: 0;">Daily AI News Summary</h2>
            <p style="color: #666;">{et_now.strftime('%B %d, %Y')} (ET)</p>
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
            <p>Generated summaries based on recent AI news.</p>
            <div class="footer-links">
                <a href="https://www.responsibleaiaustralia.com.au/" target="_blank">Visit Responsble.ai</a>
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


def send_linkedin_email(global_posts_list, australian_posts_list):
    """Sends the LinkedIn posts as a plain text email."""
    # Use the specific recipient list for LinkedIn posts
    if not RECIPIENT_EMAILS_LINKEDIN or not any(RECIPIENT_EMAILS_LINKEDIN):
        print("Error: No recipient emails configured for LinkedIn posts (RECIPIENT_EMAIL_LINKEDIN).")
        return # Or raise an error

    try:
        # Combine posts with separators
        global_combined = "\n\n-------------------\n\n".join(global_posts_list)
        australian_combined = "\n\n-------------------\n\n".join(australian_posts_list) # Corrected variable name

        print(f"Preparing LinkedIn posts email via BCC to {len(RECIPIENT_EMAILS_LINKEDIN)} recipients.")
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL # For BCC
        et_tz = pytz.timezone('US/Eastern')
        # Use current ET date for subject as posts relate to 'today' in ET perspective
        et_now = datetime.now(et_tz)
        msg['Subject'] = f"Your Daily LinkedIn AI Posts - Global & Australian Updates - {et_now.strftime('%Y-%m-%d')} (ET)"

        body = f"""
Here are your AI-generated LinkedIn posts for today:

GLOBAL AI UPDATES:
{global_combined if global_combined else "No global posts generated."}

==========================================

AUSTRALIAN AI UPDATES:
{australian_combined if australian_combined else "No Australian posts generated."}

Feel free to edit and customize before posting! You can choose to post these separately throughout the day or combine elements into a single post.
"""
        msg.attach(MIMEText(body, 'plain')) # Plain text email

        print("Connecting to SMTP server for LinkedIn posts email...")
        server = smtplib.SMTP_SSL('mail.inventico.io', 465)
        print("Logging in...")
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        print("Sending LinkedIn posts email...")
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS_LINKEDIN, msg.as_string())
        print("Closing connection...")
        server.quit()
        print("LinkedIn posts email sent successfully!")
    except Exception as e:
        print(f"Error sending LinkedIn posts email: {str(e)}")
        raise


def main():
    """Main function to fetch news, generate content, and send emails."""
    try:
        print("Starting main process...")

        # Lists to hold generated content
        global_linkedin_posts = []
        global_bullet_points = []
        aus_linkedin_posts = []
        aus_bullet_points = []

        # Get global articles
        print("\nFetching global articles...")
        global_articles = get_tldr_articles()

        if not global_articles:
            print("No global articles found for today.")
        else:
            print("\nGenerating global content (LinkedIn posts and bullet points)...") # Updated print
            num_global_articles = min(len(global_articles), 3)
            for i in range(num_global_articles):
                article = global_articles[i]
                # Generate LinkedIn post
                try:
                    linkedin_post = generate_linkedin_post(article, is_australian=False)
                    global_linkedin_posts.append(linkedin_post) # Store the formatted string
                except Exception as e:
                    print(f"Failed to generate LinkedIn post for global article '{article.get('title', 'N/A')}': {e}")
                # Generate bullet points
                try:
                    bullets, url = generate_bullet_points(article, is_australian=False)
                    global_bullet_points.append({'summary': bullets, 'url': url, 'title': article['title']}) # Store dict for HTML email
                except Exception as e:
                    print(f"Failed to generate bullet points for global article '{article.get('title', 'N/A')}': {e}")


        # Get Australian articles
        print("\nFetching Australian articles...")
        australian_articles = get_australian_ai_news()

        if not australian_articles:
            print("No Australian articles found.")
        else:
            print("\nGenerating Australian content (LinkedIn posts and bullet points)...") # Updated print
            num_aus_articles = min(len(australian_articles), 3)
            for i in range(num_aus_articles):
                article = australian_articles[i]
                 # Generate LinkedIn post
                try:
                    linkedin_post = generate_linkedin_post(article, is_australian=True)
                    aus_linkedin_posts.append(linkedin_post) # Store the formatted string
                except Exception as e:
                    print(f"Failed to generate LinkedIn post for Australian article '{article.get('title', 'N/A')}': {e}")
               # Generate bullet points
                try:
                    bullets, url = generate_bullet_points(article, is_australian=True)
                    aus_bullet_points.append({'summary': bullets, 'url': url, 'title': article['title']}) # Store dict for HTML email
                except Exception as e:
                    print(f"Failed to generate bullet points for Australian article '{article.get('title', 'N/A')}': {e}")


        # --- Email Sending Section ---
        # Send bullet points email (HTML)
        if RECIPIENT_EMAILS_BULLETS: # Check if list is configured
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

        # Send LinkedIn posts email (Plain Text)
        if RECIPIENT_EMAILS_LINKEDIN: # Check if list is configured
            if global_linkedin_posts or aus_linkedin_posts:
                 print("\nSending LinkedIn posts email...")
                 try:
                     send_linkedin_email(global_linkedin_posts, aus_linkedin_posts)
                 except Exception as e:
                     print(f"Failed to send LinkedIn posts email: {e}")
            else:
                 print("\nNo LinkedIn post content generated to send.")
        else:
             print("\nSkipping LinkedIn posts email: No recipients configured (RECIPIENT_EMAIL_LINKEDIN).")


        print("\nProcess completed successfully!")

    except Exception as e:
        print(f"Error in main: {str(e)}")
        raise


if __name__ == "__main__":
    main()