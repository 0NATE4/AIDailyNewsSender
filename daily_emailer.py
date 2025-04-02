import os
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from gnews import GNews

# Load environment variables
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')  # Create model once

# Email configuration
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
# Split recipient emails by comma
RECIPIENT_EMAILS = [email.strip() for email in os.getenv('RECIPIENT_EMAIL', '').split(',')]

# def get_australian_ai_news():
#     try:
#         print("Fetching Australian AI news...")
#         # Initialize GNews with Australian settings
#         google_news = GNews(language='en', country='Australia', period='1d', max_results=3)
        
#         # Search for AI-related news with Australian context
#         articles = google_news.get_news('(Australia OR Australian) (artificial intelligence OR AI OR machine learning)')
        
#         # Format articles
#         formatted_articles = []
#         for article in articles:
#             formatted_articles.append({
#                 'title': article['title'],
#                 'summary': article['description'],
#                 'url': article['url']
#             })
#             print(f"Added Australian article: {article['title']}")
        
#         print(f"Total Australian articles found: {len(formatted_articles)}")
#         return formatted_articles
#     except Exception as e:
#         print(f"Error in get_australian_ai_news: {str(e)}")
#         raise

def get_australian_ai_news():
    try:
        print("Fetching Australian AI news...")
        google_news = GNews(language='en', country='Australia', period='5d', max_results=10)

        # Raw search
        raw_articles = google_news.get_news('(artificial intelligence OR AI OR machine learning) Australia')

        # Filter for trustworthy Australian sources
        aus_domains = ['abc.net.au', 'smh.com.au', 'afr.com', 'innovationaus.com', 'csiro.au', 'theguardian.com']
        filtered_articles = []
        for article in raw_articles:
            if any(domain in article['url'] for domain in aus_domains):
                filtered_articles.append({
                    'title': article['title'],
                    'summary': article['description'],
                    'url': article['url']
                })
                print(f"Added: {article['title']}")
        
        print(f"Total Australian articles found: {len(filtered_articles)}")
        return filtered_articles[:3]  # Return only top 3
    except Exception as e:
        print(f"Error in get_australian_ai_news: {str(e)}")
        return []


def get_tldr_articles():
    try:
        # Get yesterday's date in the required format
        today = datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        
        url = f"https://tldr.tech/ai/{date_str}"
        print(f"Fetching articles from: {url}")
        
        response = requests.get(url)
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
                    # Get the next paragraph for summary
                    summary = current.find_next('p')
                    summary_text = summary.text.strip() if summary else ''
                    # Get the URL from the parent anchor tag if it exists
                    url = current.find_parent('a')['href'] if current.find_parent('a') else ''
                    
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

def generate_linkedin_post(article, is_australian=False):
    try:
        prompt_prefix = "Australian AI Update: " if is_australian else ""
        prompt = f"""Write a professional, natural-sounding LinkedIn post based on the following article.

Guidelines:
1. Begin with an engaging hook that captures the core theme of the article.
2. Summarise the main point or breakthrough, highlighting its relevance or potential impact.
3. Briefly reflect on why this development matters in the context of ethical, safe, or transparent AI.
4. Tie it back to "responsble.ai" (notice that its responsble, NOT responsible), and its mission of supporting responsible, standards-based AI certification.
5. End with a thoughtful question that invites discussion.
6. Keep it around 200 words.
7. Use 2 relevant hashtags and 1 well-placed emoji.

Tone: Authentic, clear, and conversational — like a seasoned Australian copywriter writing for a professional but curious audience. No "-"

Article:
{prompt_prefix}{article['title']}
{article['summary']}"""

        print(f"Generating post for article: {article['title']}")
        response = model.generate_content(prompt)
        print("Post generated successfully")
        return f"{response.text}\n\nRead more: {article['url']}"
    except Exception as e:
        print(f"Error generating LinkedIn post: {str(e)}")
        raise

def send_email(global_posts, australian_posts):
    try:
        print(f"Preparing to send email to {', '.join(RECIPIENT_EMAILS)}")
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = ', '.join(RECIPIENT_EMAILS)  # Join all emails with commas
        msg['Subject'] = f"Your Daily LinkedIn AI Posts - Global & Australian Updates - {datetime.now().strftime('%Y-%m-%d')}"
        
        body = f"""
        Here are your AI-generated LinkedIn posts for today:

        GLOBAL AI UPDATES:
        {global_posts}
        
        ==========================================
        
        AUSTRALIAN AI UPDATES:
        {australian_posts}
        
        Feel free to edit and customize before posting! You can choose to post these separately throughout the day or combine elements into a single post.
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        print("Connecting to SMTP server...")
        # Using Inventico's SMTP server with SSL
        server = smtplib.SMTP_SSL('mail.inventico.io', 465)
        print("Logging in...")
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        print("Sending message...")
        server.send_message(msg)
        print("Closing connection...")
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        raise

def main():
    try:
        print("Starting main process...")

        # Combine all posts with separators
        global_combined = ""
        australian_combined = ""
        
        # Get global articles
        print("\nFetching global articles...")
        global_articles = get_tldr_articles()
        
        if not global_articles:
            print("No global articles found for today.")
        else:
            print("\nGenerating global LinkedIn posts...")
            global_post1 = generate_linkedin_post(global_articles[0])
            global_post2 = generate_linkedin_post(global_articles[1])
            global_post3 = generate_linkedin_post(global_articles[2])
            global_combined = f"{global_post1}\n\n-------------------\n\n{global_post2}\n\n-------------------\n\n{global_post3}"
        
        # Get Australian articles
        print("\nFetching Australian articles...")
        australian_articles = get_australian_ai_news()
        
        if not australian_articles:
            print("No Australian articles found.")
        else:
            print("\nGenerating Australian LinkedIn posts...")
            aus_posts = []
            for article in australian_articles:
                post = generate_linkedin_post(article, is_australian=True)
                aus_posts.append(post)
            australian_combined = "\n\n-------------------\n\n".join(aus_posts)
        
        
        # Send emails
        print("\nSending email...")
        send_email(global_combined, australian_combined)
        print("Process completed successfully!")
        
    except Exception as e:
        print(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main() 