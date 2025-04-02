import os
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from newsapi import NewsApiClient 
import re 

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
NEWS_API_KEY = os.getenv('NEWS_API_KEY') # Added News API Key loading

def get_australian_ai_news():
    try:
        print("Fetching Australian AI news using News API...")
        if not NEWS_API_KEY:
            print("Error: NEWS_API_KEY not found in environment variables.")
            return []

        newsapi = NewsApiClient(api_key=NEWS_API_KEY)

        # Calculate dates for the past day
        to_date = datetime.now()
        from_date = to_date - timedelta(days=1) 
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
                description = article.get('description', '')
                url = article.get('url', '')
                source_name = article.get('source', {}).get('name', '')

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
                        'summary': description if description else 'No description available.',
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
    try:
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
        # Construct the prompt with the new guideline for Australian context
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
        else:
            guidelines += "\n5. End with a thoughtful question that invites discussion."
            guidelines += "\n6. Keep it around 200 words."
            guidelines += "\n7. Use 2 relevant hashtags and 1 well-placed emoji."
            prompt_prefix = ""


        prompt = f"""Write a professional, natural-sounding LinkedIn post based on the following article.
{guidelines}

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
        msg['To'] = ', '.join(RECIPIENT_EMAILS)  
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
            # Ensure we don't try to access indices beyond the list length
            num_global_posts = min(len(global_articles), 3)
            global_posts_list = []
            for i in range(num_global_posts):
                 global_posts_list.append(generate_linkedin_post(global_articles[i]))
            global_combined = "\n\n-------------------\n\n".join(global_posts_list)


        # Get Australian articles
        print("\nFetching Australian articles...")
        australian_articles = get_australian_ai_news()

        if not australian_articles:
            print("No Australian articles found.")
        else:
            print("\nGenerating Australian LinkedIn posts...")
            aus_posts = []
            # Ensure we don't try to access indices beyond the list length
            num_aus_posts = min(len(australian_articles), 3) # Use the actual number of filtered articles
            for i in range(num_aus_posts):
                post = generate_linkedin_post(australian_articles[i], is_australian=True)
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
