fimport os
import time
import json
import requests

NEWS_API_KEY       = os.getenv("NEWS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL_ID", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")

# ============================================================
# CONFIGURATION — add your keys here or use env variables
# ============================================================
NEWS_API_KEY       = os.getenv("NEWS_API_KEY", "cf31c1b5840740eda902f42b0ab0927c")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL_ID", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")

CHECK_INTERVAL_MINUTES = 15   # how often to check for new news
MAX_ARTICLES_PER_RUN   = 3    # max posts per check (avoid spamming)
POSTED_IDS_FILE        = "posted_articles.json"  # tracks what's been posted

# ============================================================
# HELPERS
# ============================================================

def load_posted_ids():
    """Load the set of already-posted article URLs from disk."""
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_posted_ids(ids: set):
    """Save posted article URLs to disk so we don't repost after restart."""
    with open(POSTED_IDS_FILE, "w") as f:
        json.dump(list(ids), f)


def fetch_crypto_news():
    """Fetch latest crypto & finance headlines from NewsAPI."""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "crypto OR bitcoin OR ethereum OR finance OR stocks",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": NEWS_API_KEY,
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("articles", [])


def rewrite_with_groq(title: str, description: str, source: str, url: str) -> str:
    """Send article to Groq and get a casual, conversational Telegram post back."""
    prompt = f"""You write posts for a crypto & finance Telegram channel.
Your tone is casual, conversational, and friendly — like texting a mate about something interesting you just read.
Use 1-2 relevant emojis. Keep it under 200 words. End with the article link.

Article title: {title}
Summary: {description}
Source: {source}
Link: {url}

Write the Telegram post now. No preamble, just the post itself."""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def post_to_telegram(message: str):
    """Send a message to the Telegram channel."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


# ============================================================
# MAIN LOOP
# ============================================================

def run():
    print("Crypto News Bot started!")
    print(f"Checking for news every {CHECK_INTERVAL_MINUTES} minutes...\n")

    posted_ids = load_posted_ids()

    while True:
        try:
            print(f"[{time.strftime('%H:%M:%S')}] Fetching latest crypto news...")
            articles = fetch_crypto_news()
            new_count = 0

            for article in articles:
                if new_count >= MAX_ARTICLES_PER_RUN:
                    break

                url = article.get("url", "")
                title = article.get("title", "")
                description = article.get("description", "") or ""
                source = article.get("source", {}).get("name", "Unknown")

                # Skip if already posted or missing key info
                if not url or not title or url in posted_ids:
                    continue

                # Skip removed articles
                if "[Removed]" in title:
                    continue

                print(f"  New article: {title[:60]}...")

                # Rewrite with Groq
                post_text = rewrite_with_groq(title, description, source, url)

                # Post to Telegram
                post_to_telegram(post_text)
                print(f"  Posted to Telegram!")

                # Mark as posted
                posted_ids.add(url)
                save_posted_ids(posted_ids)
                new_count += 1

                # Small delay between posts to avoid Telegram rate limits
                time.sleep(3)

            if new_count == 0:
                print("  No new articles found.")
            else:
                print(f"  Posted {new_count} new article(s).")

        except requests.exceptions.RequestException as e:
            print(f"  Network error: {e}")
        except Exception as e:
            print(f"  Unexpected error: {e}")

        print(f"  Sleeping for {CHECK_INTERVAL_MINUTES} minutes...\n")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    run()
