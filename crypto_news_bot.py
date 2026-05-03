import os
import time
import json
import requests
import xml.etree.ElementTree as ET

TELEGRAM_BOT_TOKEN = "8704241956:AAErQGx47GDGS8qF5fwWESMwr8dTzc5JKJ8"
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

CHECK_INTERVAL_MINUTES = 10
MAX_ARTICLES_PER_RUN = 1
POSTED_IDS_FILE = "posted_articles.json"

RSS_FEEDS = [
    ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk"),
    ("https://cointelegraph.com/rss", "CoinTelegraph"),
    ("https://decrypt.co/feed", "Decrypt"),
    ("https://feeds.bloomberg.com/markets/news.rss", "Bloomberg"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC Markets"),
    ("https://www.cnbc.com/id/15839135/device/rss/rss.html", "CNBC Finance"),
    ("https://www.kitco.com/rss/news.xml", "Kitco"),
    ("https://oilprice.com/rss/main", "OilPrice"),
    ("https://feeds.foxnews.com/foxnews/politics", "Fox News Politics"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "NY Times Politics"),
    ("https://www.theblock.co/rss.xml", "The Block"),
    ("https://bitcoinmagazine.com/.rss/full/", "Bitcoin Magazine"),
    ("https://www.reuters.com/finance/rss", "Reuters Finance"),
    ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
]

KEYWORDS = [
    "bitcoin", "crypto", "blockchain", "ethereum", "blackrock", "etf",
    "gold", "silver", "oil", "platinum", "palladium", "commodity",
    "trump", "federal reserve", "fed", "interest rate",
    "sec", "regulation", "crypto law", "digital asset",
    "stock market", "nasdaq", "s&p", "dow jones", "wall street",
    "tesla", "microstrategy", "coinbase", "binance",
    "china crypto", "russia crypto", "el salvador", "bitcoin reserve",
    "crypto ban", "crypto legal", "central bank", "cbdc",
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


def fetch_bitcoin_data():
    price_url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
    }
    r = requests.get(price_url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()["bitcoin"]
    return data


def build_bitcoin_update():
    data = fetch_bitcoin_data()
    price = data["usd"]
    change = data["usd_24h_change"]
    volume = data["usd_24h_vol"]
    market_cap = data["usd_market_cap"]
    arrow = "🟢" if change >= 0 else "🔴"
    trend = "📈" if change >= 0 else "📉"
    # Use CoinGecko's 7 day sparkline chart image
    chart_url = "https://www.coingecko.com/coins/bitcoin/sparkline.svg"
    message = (
        "₿ *Bitcoin Price Update* " + trend + "\n\n"
        + arrow + " *Price:* $" + "{:,.2f}".format(price) + "\n"
        + "📊 *24h Change:* " + "{:+.2f}".format(change) + "%\n"
        + "💰 *Volume:* $" + "{:,.0f}".format(volume) + "\n"
        + "🏦 *Market Cap:* $" + "{:,.0f}".format(market_cap) + "\n\n"
        + "_7 day price chart_"
    )
    return message, chart_url


def send_bitcoin_chart_to_telegram(message, chart_url):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "photo": chart_url,
        "caption": message,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def rewrite_with_groq(title, description, source):
    prompt = (
        "You write posts for a crypto, finance & markets Telegram channel.\n"
        "Your tone is very casual, short and punchy - like a friend texting you hot news.\n"
        "Max 3-4 sentences. No exclamation marks. No speech marks or quotation marks ever. No formal language. Do not include any links.\n"
        "Only use emojis in about half of posts - not every post. When you do use them, make them relevant and specific.\n"
        "Occasionally capitalise important words for emphasis e.g. MASSIVE, HUGE, BREAKING, ALL TIME HIGH.\n"
        "Sometimes make key words or phrases bold using *word* markdown formatting. Not in every post.\n\n"
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
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def run():
    print("Crypto & Finance News Bot started!")
    print("Posting news every " + str(CHECK_INTERVAL_MINUTES) + " minutes...\n")

    posted_ids = load_posted_ids()
    last_btc_post = 0

    while True:
        try:
            # Post Bitcoin price chart every 12 hours
            if time.time() - last_btc_post > 43200:
                try:
                    message, chart_url = build_bitcoin_update()
                    send_bitcoin_chart_to_telegram(message, chart_url)
                    print("  Posted Bitcoin price chart!")
                    last_btc_post = time.time()
                except Exception as e:
                    print("  Bitcoin price error: " + str(e))

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
