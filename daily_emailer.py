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
    yesterday = datetime.now() - timedelta(days=1)
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

def generate_linkedin_post(articles):
    posts = []
    prompts = [
        """
        Create a focused LinkedIn post about AI security and safety, using this news story as the foundation.
        Key points:
        1. Start with an attention-grabbing hook about AI security
        2. Deep dive into the specific security concerns and their implications
        3. Connect to Responsble.ai's mission of promoting ethical AI certification
        4. Explain how certification and standards can help address these security challenges
        5. End with a thought-provoking question about AI safety
        6. Include 2 relevant hashtags and 1 strategic emoji
        Keep it natural and conversational, around 150 words.
        
        Article to discuss:
        """,
        """
        Create a focused LinkedIn post about AI in healthcare, using this news story as the foundation.
        Key points:
        1. Start with an engaging hook about AI transforming healthcare
        2. Analyze the specific innovations and their potential impact
        3. Address the importance of responsible AI deployment in healthcare
        4. Connect to how Responsble.ai's certification ensures ethical AI use in critical sectors
        5. End with a question about the future of AI in healthcare
        6. Include 2 relevant hashtags and 1 strategic emoji
        Keep it natural and conversational, around 150 words.
        
        Article to discuss:
        """,
        """
        Create a focused LinkedIn post about AI in productivity and workplace tools, using this news story as the foundation.
        Key points:
        1. Start with a compelling hook about workplace transformation
        2. Analyze how AI is reshaping traditional tools and workflows
        3. Address both opportunities and challenges of AI integration
        4. Connect to Responsble.ai's role in ensuring responsible AI deployment in enterprise
        5. End with a question about the future of work
        6. Include 2 relevant hashtags and 1 strategic emoji
        Keep it natural and conversational, around 150 words.
        
        Article to discuss:
        """
    ]
    
    # Generate three separate posts
    for i, article in enumerate(articles[:3]):
        prompt = prompts[i] + f"\n\n{article['title']}\nSummary: {article['summary']}"
        
        # Generate content using Gemini
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        posts.append(response.text)
    
    # Combine all posts with separators
    combined_posts = "\n\n-------------------\n\n".join(posts)
    return combined_posts

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
        # Get articles
        articles = get_tldr_articles()
        if not articles:
            print("No articles found for today")
            return
        
        # Generate LinkedIn posts
        linkedin_posts = generate_linkedin_post(articles)
        
        # Send emails
        send_email(linkedin_posts)
        
    except Exception as e:
        print(f"Error in main execution: {str(e)}")

if __name__ == "__main__":
    main() 