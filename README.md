# Daily AI LinkedIn Post Generator

Automatically generates engaging LinkedIn posts about the latest AI news from tldr.tech, with a focus on responsible AI development and certification.

## Features

- Fetches daily AI news from tldr.tech
- Generates three focused LinkedIn posts using Google's Gemini AI:
  - AI Security & Safety
  - AI in Healthcare
  - AI in Workplace Transformation
- Connects each topic to responsible AI certification
- Sends daily emails at 6am AEST
- Runs automatically via GitHub Actions

## Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd DailyAIEmail
```

2. Install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
- Copy `.env.example` to `.env` for local testing
- Add your actual values to `.env`
- Never commit the `.env` file (it's in .gitignore)

4. GitHub Actions Setup:
- Push the code to a GitHub repository
- Go to repository Settings > Secrets and Variables > Actions
- Add the following repository secrets:
  - `GEMINI_API_KEY`: Your Google Gemini API key
  - `SENDER_EMAIL`: Your Gmail address
  - `SENDER_PASSWORD`: Your Gmail app password
  - `RECIPIENT_EMAIL`: Recipient's email address

The GitHub Action will run automatically at 6am AEST (8pm UTC) every day.

## Local Development

To test locally:
```bash
python daily_emailer.py
```

## Environment Variables

- `GEMINI_API_KEY`: Google Gemini API key for AI content generation
- `SENDER_EMAIL`: Gmail address to send from
- `SENDER_PASSWORD`: Gmail app password (not your regular password)
- `RECIPIENT_EMAIL`: Email address to receive the posts

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

MIT License - feel free to use this code for your own projects! 