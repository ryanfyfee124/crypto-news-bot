import os
import time
import json
import random
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8704241956:AAErQGx47GDGS8qF5fwWESMwr8dTzc5JKJ8"
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

MAX_ARTICLES_PER_RUN = 1
POSTED_IDS_FILE = "posted_articles.json"

RSS_FEEDS = [
    ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk"),
    ("https://cointelegraph.com/rss", "CoinTelegraph"),
    ("https://decrypt.co/feed", "Decrypt"),
    ("https://feeds.bloomberg.com/markets/news.rss", "Bloomberg"),
    ("https://oilprice.com/rss/main", "OilPrice"),
    ("https://feeds.foxnews.com/foxnews/politics", "Fox News Politics"),
    ("https://feeds.foxnews.com/foxnews/latest", "Fox News"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "NY Times Politics"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml", "NY Times Economy"),
    ("https://www.theblock.co/rss.xml", "The Block"),
    ("https://www.reuters.com/finance/rss", "Reuters Finance"),
    ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
]

KEYWORDS = [
    "bitcoin", "crypto", "blockchain", "ethereum", "blackrock", "etf",
    "gold", "silver", "oil", "platinum", "palladium", "commodity",
    "trump", "donald trump", "trump tariff", "trump crypto", "trump bitcoin",
    "trump executive order", "trump administration", "white house crypto",
    "trump market", "trump stocks", "trump economy", "trump fed",
    "federal reserve", "fed", "interest rate", "powell",
    "sec", "regulation", "crypto law", "digital asset",
    "stock market", "nasdaq", "s&p", "dow jones", "wall street",
    "tesla", "microstrategy", "coinbase", "binance",
    "china crypto", "russia crypto", "el salvador", "bitcoin reserve",
    "crypto ban", "crypto legal", "central bank", "cbdc",
    "tariff", "trade war", "sanctions", "inflation", "recession",
    "strategic reserve", "crypto reserve", "bitcoin act",
]

# Free crypto related images to attach to some posts
POST_IMAGES = [
    "https://images.unsplash.com/photo-1518546305927-5a555bb7020d?w=800",
    "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800",
    "https://images.unsplash.com/photo-1605792657660-596af9009e82?w=800",
    "https://images.unsplash.com/photo-1622630998477-20aa696ecb05?w=800",
    "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?w=800",
    "https://images.unsplash.com/photo-1640340434855-6084b1f4901c?w=800",
    "https://images.unsplash.com/photo-1621761191319-c6fb62004040?w=800",
    "https://images.unsplash.com/photo-1634704784915-aacf363b021f?w=800",
]


def load_posted_ids():
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_posted_ids(ids):
    with open(POSTED_IDS_FILE, "w") as f:
        json.dump(list(ids), f)


def is_relevant(title, description):
    text = (title + " " + description).lower()
    return any(keyword in text for keyword in KEYWORDS)


def fetch_all_news():
    articles = []
    for feed_url, source_name in RSS_FEEDS:
        try:
            response = requests.get(feed_url, timeout=10)
            root = ET.fromstring(response.content)
            for item in root.findall(".//item")[:10]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                description = item.findtext("description", "") or title
                if title and link and is_relevant(title, description):
                    articles.append({
                        "title": title,
                        "description": description[:300],
                        "url": link,
                        "source": {"name": source_name},
                    })
        except Exception as e:
            print("  Feed error (" + source_name + "): " + str(e))
    return articles


def rewrite_with_groq(title, description, source):
    # Randomly pick a writing style to vary posts
    styles = [
        "casual and punchy like a friend texting breaking news",
        "direct and confident like a trader who knows whats going on",
        "slightly dramatic but factual like a news anchor",
        "sharp and analytical like a market analyst",
    ]
    style = random.choice(styles)

    prompt = (
        "You write posts for a professional crypto & finance Telegram channel.\n"
        "Your writing style for this post: " + style + "\n\n"
        "Study these real examples and copy the format:\n\n"
        "Example 1: ELON MUSK CALLS 95% CRYPTO PROJECTS SCAMS\n"
        "Musk says some assets have merit but most are scams. "
        "This comes as Tesla continues to hold billions in Bitcoin.\n\n"
        "Example 2: JUST IN: US Treasury seizes $450 million in Iranian cryptocurrency.\n\n"
        "Example 3: BULLISH: Senator Lummis confirms crypto legislation will be marked up in May. "
        "This could be the regulatory clarity markets have been waiting for.\n\n"
        "Example 4: Trump pauses tariffs for 90 days. "
        "Bitcoin jumps 4% as markets react to the news — risk-on is back.\n\n"
        "Example 5: Fed holds rates steady. *Powell* signals no cuts coming soon. "
        "Crypto dips slightly on the news.\n\n"
        "Rules:\n"
        "- Start breaking news with JUST IN:\n"
        "- Start very bullish news with BULLISH:\n"
        "- Use ALL CAPS only for the biggest headlines\n"
        "- Use country flag emojis when mentioning specific countries\n"
        "- Only use hashtags in about 1 in 5 posts\n"
        "- 1-3 sentences max\n"
        "- No links ever\n"
        "- No speech marks or quotation marks\n"
        "- Use *bold* for key figures or numbers occasionally\n"
        "- When relevant mention the market impact — did crypto go up or down\n"
        "- Sound like a real person, not a robot\n\n"
        "Article title: " + title + "\n"
        "Summary: " + description + "\n"
        "Source: " + source + "\n\n"
        "Write the Telegram post now. No preamble, just the post itself."
    )
    headers = {
        "Authorization": "Bearer " + GROQ_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.85,
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def post_to_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def post_with_image(message, image_url):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "photo": image_url,
        "caption": message,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def run():
    print("COINDEX Bot started!")
    print("Posting at random human-like intervals...\n")

    posted_ids = load_posted_ids()
    post_count = 0

    while True:
        try:
            print("[" + time.strftime("%H:%M:%S") + "] Fetching latest news...")
            articles = fetch_all_news()
            new_count = 0

            for article in articles:
                if new_count >= MAX_ARTICLES_PER_RUN:
                    break

                url = article.get("url", "")
                title = article.get("title", "")
                description = article.get("description", "") or ""
                source = article.get("source", {}).get("name", "Unknown")

                if not url or not title or url in posted_ids:
                    continue

                if "[Removed]" in title:
                    continue

                print("  New article: " + title[:60] + "...")

                post_text = rewrite_with_groq(title, description, source)

                # Attach an image to roughly 1 in 3 posts
                if post_count % 3 == 0:
                    image_url = random.choice(POST_IMAGES)
                    try:
                        post_with_image(post_text, image_url)
                        print("  Posted to Telegram with image!")
                    except Exception:
                        post_to_telegram(post_text)
                        print("  Posted to Telegram (image failed, text only)!")
                else:
                    post_to_telegram(post_text)
                    print("  Posted to Telegram!")

                posted_ids.add(url)
                save_posted_ids(posted_ids)
                new_count += 1
                post_count += 1
                time.sleep(3)

            if new_count == 0:
                print("  No new articles found.")
            else:
                print("  Posted " + str(new_count) + " new article(s).")

        except requests.exceptions.RequestException as e:
            print("  Network error: " + str(e))
        except Exception as e:
            print("  Unexpected error: " + str(e))

        # Human-like random intervals — sometimes quick, sometimes slower
        sleep_minutes = random.choice([8, 10, 12, 15, 18, 20, 25, 11, 14, 17])
        print("  Sleeping for " + str(sleep_minutes) + " minutes...\n")
        time.sleep(sleep_minutes * 60)


if __name__ == "__main__":
    run()
