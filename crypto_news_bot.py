import os
import time
import json
import requests
import xml.etree.ElementTree as ET

TELEGRAM_BOT_TOKEN = "8704241956:AAErQGx47GDGS8qF5fwWESMwr8dTzc5JKJ8"
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

CHECK_INTERVAL_MINUTES = 5
MAX_ARTICLES_PER_RUN = 3
POSTED_IDS_FILE = "posted_articles.json"


def load_posted_ids():
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_posted_ids(ids):
    with open(POSTED_IDS_FILE, "w") as f:
        json.dump(list(ids), f)


def fetch_crypto_news():
    feeds = [
        ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk"),
        ("https://cointelegraph.com/rss", "CoinTelegraph"),
        ("https://decrypt.co/feed", "Decrypt"),
    ]
    articles = []
    for feed_url, source_name in feeds:
        try:
            response = requests.get(feed_url, timeout=10)
            root = ET.fromstring(response.content)
            for item in root.findall(".//item")[:5]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                description = item.findtext("description", "") or title
                if title and link:
                    articles.append({
                        "title": title,
                        "description": description[:200],
                        "url": link,
                        "source": {"name": source_name},
                    })
        except Exception as e:
            print("  Feed error: " + str(e))
    return articles


def fetch_crypto_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin,ethereum,solana,dogecoin,ripple,cardano",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    lines = ["📊 Crypto Prices Update"]
    names = {
        "bitcoin": "Bitcoin BTC",
        "ethereum": "Ethereum ETH",
        "solana": "Solana SOL",
        "dogecoin": "Dogecoin DOGE",
        "ripple": "XRP",
        "cardano": "Cardano ADA",
    }
    for coin, label in names.items():
        price = data[coin]["usd"]
        change = data[coin]["usd_24h_change"]
        arrow = "🟢" if change >= 0 else "🔴"
        lines.append(arrow + " " + label + ": $" + "{:,.2f}".format(price) + " (" + "{:+.2f}".format(change) + "%)")
    return "\n".join(lines)


def rewrite_with_groq(title, description, source, url):
    prompt = (
        "You write posts for a crypto & finance Telegram channel.\n"
        "Your tone is very casual, short and punchy - like a friend texting you hot news.\n"
        "Max 3-4 sentences. Use 1-2 emojis. No formal language. Do not include any links.\n\n"
        "Article title: " + title + "\n"
        "Summary: " + description + "\n"
        "Source: " + source + "\n"
        "Link: " + url + "\n\n"
        "Write the Telegram post now. No preamble, just the post itself."
    )

    headers = {
        "Authorization": "Bearer " + GROQ_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.7,
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


def post_to_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "text": message,
        "disable_web_page_preview": False,
    }
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def run():
    print("Crypto News Bot started!")
    print("Checking for news every " + str(CHECK_INTERVAL_MINUTES) + " minutes...\n")

    posted_ids = load_posted_ids()
    last_price_post = 0

    while True:
        try:
            # Post price update every hour
            if time.time() - last_price_post > 3600:
                try:
                    prices = fetch_crypto_prices()
                    post_to_telegram(prices)
                    print("  Posted price update!")
                    last_price_post = time.time()
                except Exception as e:
                    print("  Price fetch error: " + str(e))

            print("[" + time.strftime("%H:%M:%S") + "] Fetching latest crypto news...")
            articles = fetch_crypto_news()
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

                post_text = rewrite_with_groq(title, description, source, url)
                post_to_telegram(post_text)
                print("  Posted to Telegram!")

                posted_ids.add(url)
                save_posted_ids(posted_ids)
                new_count += 1
                time.sleep(3)

            if new_count == 0:
                print("  No new articles found.")
            else:
                print("  Posted " + str(new_count) + " new article(s).")

        except requests.exceptions.RequestException as e:
            print("  Network error: " + str(e))
        except Exception as e:
            print("  Unexpected error: " + str(e))

        print("  Sleeping for " + str(CHECK_INTERVAL_MINUTES) + " minutes...\n")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    run()
