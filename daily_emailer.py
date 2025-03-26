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

# Email configuration
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')

def get_tldr_articles():
    # Get yesterday's date in the required format
    yesterday = datetime.now()
    date_str = yesterday.strftime("%Y-%m-%d")
    
    url = f"https://tldr.tech/ai/{date_str}"
    print(f"Fetching articles from: {url}")
    
    response = requests.get(url)
    print(f"Response status code: {response.status_code}")
    
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
    
    print(f"Total articles found: {len(articles)}")
    return articles

def generate_linkedin_post(article):
    prompt = f"""Write a professional, natural-sounding LinkedIn post based on the following article.

Guidelines:
1. Begin with an engaging hook that captures the core theme of the article.
2. Summarise the main point or breakthrough, highlighting its relevance or potential impact.
3. Briefly reflect on why this development matters in the context of ethical, safe, or transparent AI.
4. Tie it back to Responsible.ai's mission of supporting responsible, standards-based AI certification — only if relevant.
5. End with a thoughtful question that invites discussion.
6. Keep it around 150 words.
7. Use 2 relevant hashtags and 1 well-placed emoji.

Tone: Authentic, clear, and conversational — like a seasoned Australian copywriter writing for a professional but curious audience. No "-"

Article:
{article['title']}
{article['summary']}"""

    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(prompt)
    return response.text

def generate_linkedin_post_2(article):
    prompt = f"""Write a professional, natural-sounding LinkedIn post based on the following article.

Guidelines:
1. Begin with an engaging hook that captures the core theme of the article.
2. Summarise the main point or breakthrough, highlighting its relevance or potential impact.
3. Briefly reflect on why this development matters in the context of ethical, safe, or transparent AI.
4. Tie it back to Responsible.ai's mission of supporting responsible, standards-based AI certification — only if relevant.
5. End with a thoughtful question that invites discussion.
6. Keep it around 150 words.
7. Use 2 relevant hashtags and 1 well-placed emoji.

Tone: Authentic, clear, and conversational — like a seasoned Australian copywriter writing for a professional but curious audience. No "-"

Article:
{article['title']}
{article['summary']}"""

    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(prompt)
    return response.text

def generate_linkedin_post_3(article):
    prompt = f"""Write a professional, natural-sounding LinkedIn post based on the following article.

Guidelines:
1. Begin with an engaging hook that captures the core theme of the article.
2. Summarise the main point or breakthrough, highlighting its relevance or potential impact.
3. Briefly reflect on why this development matters in the context of ethical, safe, or transparent AI.
4. Tie it back to Responsible.ai's mission of supporting responsible, standards-based AI certification — only if relevant.
5. End with a thoughtful question that invites discussion.
6. Keep it around 150 words.
7. Use 2 relevant hashtags and 1 well-placed emoji.

Tone: Authentic, clear, and conversational — like a seasoned Australian copywriter writing for a professional but curious audience. No "-"

Article:
{article['title']}
{article['summary']}"""

    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(prompt)
    return response.text

def send_email(linkedin_post):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = f"Your Daily LinkedIn AI Posts - {datetime.now().strftime('%Y-%m-%d')}"
    
    body = f"""
    Here are your AI-generated LinkedIn posts for today:
    
    {linkedin_post}
    
    Feel free to edit and customize before posting! You can choose to post these separately throughout the day or combine elements into a single post.
    """
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {str(e)}")

def main():
    try:
        # Get today's articles
        articles = get_tldr_articles()
        
        if not articles:
            print("No articles found for today.")
            return
        
        # Generate LinkedIn posts
        post1 = generate_linkedin_post(articles[0])
        post2 = generate_linkedin_post_2(articles[1])
        post3 = generate_linkedin_post_3(articles[2])
        
        # Combine all posts with separators
        combined_posts = f"{post1}\n\n-------------------\n\n{post2}\n\n-------------------\n\n{post3}"
        
        # Send emails
        send_email(combined_posts)
        
    except Exception as e:
        print(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main() 