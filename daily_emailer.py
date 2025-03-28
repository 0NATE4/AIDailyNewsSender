import os
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

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

def get_tldr_articles():
    try:
        # Get today's date in the required format
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
                    
                    articles.append({
                        'title': title,
                        'summary': summary_text
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

def generate_linkedin_post(article):
    try:
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
{article['title']}
{article['summary']}"""

        print(f"Generating post for article: {article['title']}")
        response = model.generate_content(prompt)
        print("Post generated successfully")
        return response.text
    except Exception as e:
        print(f"Error generating LinkedIn post: {str(e)}")
        raise

def send_email(linkedin_post):
    try:
        print(f"Preparing to send email to {', '.join(RECIPIENT_EMAILS)}")
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = ', '.join(RECIPIENT_EMAILS)  # Join all emails with commas
        msg['Subject'] = f"Your Daily LinkedIn AI Posts - {datetime.now().strftime('%Y-%m-%d')}"
        
        body = f"""
        Here are your AI-generated LinkedIn posts for today:
        
        {linkedin_post}
        
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
        # Get today's articles
        articles = get_tldr_articles()
        
        if not articles:
            print("No articles found for today.")
            return
        
        print(f"Found {len(articles)} articles")
        
        # Generate LinkedIn posts
        print("Generating LinkedIn posts...")
        post1 = generate_linkedin_post(articles[0])
        post2 = generate_linkedin_post(articles[1])
        post3 = generate_linkedin_post(articles[2])
        
        # Combine all posts with separators
        combined_posts = f"{post1}\n\n-------------------\n\n{post2}\n\n-------------------\n\n{post3}"
        
        # Send emails
        print("Sending email...")
        send_email(combined_posts)
        print("Process completed successfully!")
        
    except Exception as e:
        print(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main() 