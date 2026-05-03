import os
import time
import json
import random
import requests
import xml.etree.ElementTree as ET

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
    return r.json()["bitcoin"]


def fetch_bitcoin_chart():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": "7"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    prices = r.json()["prices"]
    return [round(p[1]) for p in prices]


def build_chart_image_url(prices):
    price_str = ",".join([str(p) for p in prices])
    labels = ",".join(["" for _ in prices])
    config = (
        '{"type":"line","data":{"labels":[' + labels + '],'
        '"datasets":[{"data":[' + price_str + '],'
        '"borderColor":"#F7931A",'
        '"backgroundColor":"rgba(247,147,26,0.1)",'
        '"borderWidth":2,'
        '"pointRadius":0,'
        '"fill":true}]},'
        '"options":{'
        '"plugins":{"legend":{"display":false}},'
        '"scales":{'
        '"x":{"display":false},'
        '"y":{"ticks":{"color":"#aaaaaa"},'
        '"grid":{"color":"rgba(255,255,255,0.05)"}}}}}'
    )
    return (
        "https://quickchart.io/chart?c="
        + requests.utils.quote(config)
        + "&width=700&height=350&backgroundColor=%23131722"
    )


def build_bitcoin_update():
    data = fetch_bitcoin_data()
    prices = fetch_bitcoin_chart()
    chart_url = build_chart_image_url(prices)
    price = data["usd"]
    change = data["usd_24h_change"]
    volume = data["usd_24h_vol"]
    market_cap = data["usd_market_cap"]
    arrow = "🟢" if change >= 0 else "🔴"
    trend = "📈" if change >= 0 else "📉"
    message = (
        "₿ *Bitcoin Price Update* " + trend + "\n\n"
        + arrow + " *Price:* $" + "{:,.2f}".format(price) + "\n"
        + "📊 *24h Change:* " + "{:+.2f}".format(change) + "%\n"
        + "💰 *Volume:* $" + "{:,.0f}".format(volume) + "\n"
        + "🏦 *Market Cap:* $" + "{:,.0f}".format(market_cap) + "\n\n"
        + "_7 day price chart_"
    )
    return message, chart_url


def send_photo_to_telegram(message, photo_url):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "photo": photo_url,
        "caption": message,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def rewrite_with_groq(title, description, source):
    prompt = (
        "You write posts for a professional crypto & finance Telegram news channel with 60,000+ subscribers.\n"
        "Study these real post examples and copy the exact style:\n\n"
        "Example 1: ELON MUSK CALLS 95% CRYPTO PROJECTS SCAMS\n"
        "Musk: Some Crypto Assets Have Merit, but Most of Them Are Scams\n"
        "According to Fortune, during his lawsuit against OpenAI, Elon Musk stated that some crypto assets have merit, but most are scams. #regulation\n\n"
        "Example 2: JUST IN: US Treasury Secretary Bessent says the US has seized $450 million in Iranian cryptocurrency.\n\n"
        "Example 3: BULLISH: Senator Cynthia Lummis says bitcoin and crypto market structure legislation will be marked up in May.\n\n"
        "Example 4: ONLY #BTC #ETH #SOL #XRP #USDT ARE LEGITIMATE ASSETS\n\n"
        "Rules:\n"
        "- Start breaking news with JUST IN: or ALL CAPS headline\n"
        "- Start bullish news with BULLISH: or use rocket emoji\n"
        "- Use relevant country flag emojis when mentioning countries\n"
        "- Only use hashtags occasionally when they feel natural, not in every post\n"
        "- Keep it 1-3 sentences max\n"
        "- No links ever\n"
        "- No speech marks or quotation marks\n"
        "- Sometimes use *bold* for key names or numbers\n"
        "- Mix ALL CAPS headlines with normal sentence case\n\n"
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
    print("Posting at random intervals...\n")

    posted_ids = load_posted_ids()
    last_btc_post = 0

    while True:
        try:
            # Post Bitcoin price chart every 12 hours
            if time.time() - last_btc_post > 43200:
                try:
                    message, chart_url = build_bitcoin_update()
                    send_photo_to_telegram(message, chart_url)
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

        sleep_minutes = random.randint(7, 25)
        print("  Sleeping for " + str(sleep_minutes) + " minutes...\n")
        time.sleep(sleep_minutes * 60)


if __name__ == "__main__":
    run()
