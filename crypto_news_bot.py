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
STATE_FILE = "bot_state.json"

# Removed broken feeds
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

WEEKLY_POLLS = [
    ("Where is BTC heading this week?", ["📈 Higher", "📉 Lower", "➡️ Sideways"]),
    ("Are you bullish or bearish on crypto right now?", ["🟢 Bullish", "🔴 Bearish", "🤷 Neutral"]),
    ("Which asset will perform best this month?", ["₿ Bitcoin", "💛 Gold", "📊 Stocks"]),
    ("Will BTC hit a new all time high this year?", ["✅ Yes", "❌ No", "🤔 Maybe"]),
    ("How are you positioned right now?", ["🟢 Mostly long", "🔴 Mostly short", "💵 In cash"]),
    ("Best time to buy Bitcoin?", ["🔥 Right now", "📉 Wait for dip", "🚫 Not buying"]),
]

# Cache prices to avoid hitting CoinGecko too often
price_cache = {"data": None, "last_fetch": 0}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_btc_post": 0,
        "last_morning_brief": 0,
        "last_evening_wrap": 0,
        "last_weekly_recap": 0,
        "last_poll": 0,
        "last_correlation": 0,
        "last_btc_price": 0,
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


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


def fetch_market_prices():
    # Only call CoinGecko every 10 minutes to avoid rate limits
    now = time.time()
    if price_cache["data"] and now - price_cache["last_fetch"] < 600:
        return price_cache["data"]
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "bitcoin,ethereum,solana",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=15,
        )
        r.raise_for_status()
        price_cache["data"] = r.json()
        price_cache["last_fetch"] = now
        return price_cache["data"]
    except Exception as e:
        print("  Price fetch error: " + str(e))
        return price_cache["data"]  # Return cached data if available


def fetch_bitcoin_chart():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": "7"}
    r = requests.get(url, params=params, timeout=15)
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


def arrow(change):
    return "🟢" if change >= 0 else "🔴"


def fmt_change(change):
    return "{:+.2f}".format(change) + "%"


def post_morning_brief(crypto):
    btc = crypto.get("bitcoin", {})
    eth = crypto.get("ethereum", {})
    sol = crypto.get("solana", {})
    btc_price = btc.get("usd", 0)
    btc_change = btc.get("usd_24h_change", 0)
    eth_price = eth.get("usd", 0)
    eth_change = eth.get("usd_24h_change", 0)
    sol_price = sol.get("usd", 0)
    sol_change = sol.get("usd_24h_change", 0)
    sentiment = "bullish" if btc_change > 1 else "bearish" if btc_change < -1 else "mixed"
    watch = "Key level to watch: $" + "{:,.0f}".format(round(btc_price / 1000) * 1000)
    message = (
        "🌅 *GOOD MORNING — DAILY MARKET BRIEF*\n\n"
        + arrow(btc_change) + " *BTC:* $" + "{:,.0f}".format(btc_price) + " (" + fmt_change(btc_change) + ")\n"
        + arrow(eth_change) + " *ETH:* $" + "{:,.0f}".format(eth_price) + " (" + fmt_change(eth_change) + ")\n"
        + arrow(sol_change) + " *SOL:* $" + "{:,.0f}".format(sol_price) + " (" + fmt_change(sol_change) + ")\n\n"
        + "📊 *Sentiment:* Market looking " + sentiment + " to start the day\n"
        + "⚠️ *Watch:* " + watch + " — reaction here sets the tone\n\n"
        + "_Stay sharp. More updates throughout the day._"
    )
    post_to_telegram(message)
    print("  Posted morning brief!")


def post_evening_wrap(crypto):
    btc = crypto.get("bitcoin", {})
    eth = crypto.get("ethereum", {})
    btc_price = btc.get("usd", 0)
    btc_change = btc.get("usd_24h_change", 0)
    eth_change = eth.get("usd_24h_change", 0)
    if btc_change > 2:
        summary = "Strong day for crypto. Bulls in control."
        outlook = "If momentum holds overnight, expect continuation tomorrow."
    elif btc_change < -2:
        summary = "Rough day across the board. Bears took charge."
        outlook = "Watch for support levels overnight. Key test incoming."
    else:
        summary = "Choppy day with no clear direction."
        outlook = "Market consolidating. Big move could be coming soon."
    message = (
        "🌙 *EVENING MARKET WRAP*\n\n"
        + arrow(btc_change) + " *BTC:* $" + "{:,.0f}".format(btc_price) + " (" + fmt_change(btc_change) + ")\n"
        + arrow(eth_change) + " *ETH 24h:* " + fmt_change(eth_change) + "\n\n"
        + "📝 *Summary:* " + summary + "\n"
        + "🔮 *Outlook:* " + outlook + "\n\n"
        + "_See you tomorrow. Stay safe out there._"
    )
    post_to_telegram(message)
    print("  Posted evening wrap!")


def post_weekly_recap(crypto):
    btc = crypto.get("bitcoin", {})
    btc_price = btc.get("usd", 0)
    btc_change = btc.get("usd_24h_change", 0)
    if btc_change > 0:
        week_tone = "a positive week for crypto"
        emoji = "🟢"
    else:
        week_tone = "a tough week for crypto"
        emoji = "🔴"
    message = (
        "📅 *WEEKLY RECAP — COINDEX*\n\n"
        + emoji + " Bitcoin finishing the week at *$" + "{:,.0f}".format(btc_price) + "*\n\n"
        + "Here is what moved markets this week:\n"
        + "— Macro sentiment and Fed policy dominated headlines\n"
        + "— Trump news continued to impact risk assets\n"
        + "— Gold and oil remained key indicators to watch\n\n"
        + "Overall it was " + week_tone + ".\n\n"
        + "New week ahead. Stay focused, manage your risk.\n\n"
        + "_Follow @Coindex00 for daily updates all week_"
    )
    post_to_telegram(message)
    print("  Posted weekly recap!")


def post_price_alert(btc_price, last_price):
    if last_price == 0 or btc_price == 0:
        return False
    price_change_pct = ((btc_price - last_price) / last_price) * 100
    if abs(price_change_pct) >= 3:
        direction = "surged" if price_change_pct > 0 else "dropped"
        emoji = "🚀" if price_change_pct > 0 else "📉"
        impact = "Bulls gaining momentum — watch for continuation." if price_change_pct > 0 else "Support levels being tested. Watch closely."
        message = (
            emoji + " *PRICE ALERT*\n\n"
            + "Bitcoin has " + direction + " *" + "{:+.1f}".format(price_change_pct) + "%* in the last few hours\n\n"
            + "*Current price:* $" + "{:,.0f}".format(btc_price) + "\n"
            + impact
        )
        post_to_telegram(message)
        print("  Posted price alert!")
        return True
    return False


def post_correlation(crypto):
    btc_change = crypto.get("bitcoin", {}).get("usd_24h_change", 0)
    eth_change = crypto.get("ethereum", {}).get("usd_24h_change", 0)
    if btc_change < -1 and eth_change < -1:
        message = (
            "⚠️ *MARKET INSIGHT*\n\n"
            "Crypto seeing red across the board today. "
            "When BTC and ETH drop together like this, it usually signals macro pressure — "
            "could be dollar strength, risk-off sentiment, or big news incoming.\n\n"
            "Gold worth watching as a safe haven signal right now."
        )
    elif btc_change > 1 and eth_change > 1:
        message = (
            "🔥 *MARKET INSIGHT*\n\n"
            "BTC and ETH both pushing higher today. "
            "Broad crypto strength usually means institutional money is moving in. "
            "Watch for altcoins to follow if momentum continues.\n\n"
            "Risk-on sentiment building across markets."
        )
    elif btc_change > 1 and eth_change < 0:
        message = (
            "📊 *MARKET INSIGHT*\n\n"
            "Bitcoin outperforming Ethereum today — Bitcoin dominance rising. "
            "This often happens when institutions buy BTC but avoid alts. "
            "Could signal caution in the broader crypto market."
        )
    else:
        return
    post_to_telegram(message)
    print("  Posted market correlation insight!")


def post_weekly_poll():
    poll = random.choice(WEEKLY_POLLS)
    question = poll[0]
    options = poll[1]
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPoll"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "question": question,
        "options": options,
        "is_anonymous": True,
    }
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    print("  Posted weekly poll!")


def post_btc_chart():
    prices = fetch_bitcoin_chart()
    chart_url = build_chart_image_url(prices)
    crypto = fetch_market_prices()
    if not crypto:
        return
    btc = crypto.get("bitcoin", {})
    price = btc.get("usd", 0)
    change = btc.get("usd_24h_change", 0)
    trend = "📈" if change >= 0 else "📉"
    message = (
        "₿ *Bitcoin 7-Day Chart* " + trend + "\n\n"
        + arrow(change) + " *Price:* $" + "{:,.2f}".format(price) + "\n"
        + "📊 *24h:* " + fmt_change(change) + "\n\n"
        + "_Updated chart — COINDEX_"
    )
    send_photo_to_telegram(message, chart_url)
    print("  Posted BTC chart!")


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
        "According to Fortune, during his lawsuit against OpenAI, Elon Musk stated that some crypto assets have merit, but most are scams.\n\n"
        "Example 2: JUST IN: US Treasury Secretary Bessent says the US has seized $450 million in Iranian cryptocurrency.\n\n"
        "Example 3: BULLISH: Senator Cynthia Lummis says bitcoin and crypto market structure legislation will be marked up in May.\n\n"
        "Example 4: Trump signs executive order pausing tariffs for 90 days. Markets surge immediately after announcement.\n\n"
        "Example 5: JUST IN: Fed Chair Powell says interest rates will remain unchanged. Bitcoin drops 3% on the news.\n\n"
        "Rules:\n"
        "- Start breaking news with JUST IN:\n"
        "- Start bullish news with BULLISH:\n"
        "- Use ALL CAPS for major headline announcements\n"
        "- Use relevant country flag emojis when mentioning countries\n"
        "- Only use hashtags occasionally when they feel natural, not in every post\n"
        "- Keep it 1-3 sentences max\n"
        "- No links ever\n"
        "- No speech marks or quotation marks\n"
        "- Sometimes use *bold* for key names or numbers\n"
        "- Always mention how news impacts crypto or markets when relevant\n\n"
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


def run():
    print("COINDEX Bot started!")
    print("Full schedule active...\n")

    posted_ids = load_posted_ids()
    state = load_state()

    while True:
        try:
            now = time.time()
            hour = datetime.now().hour
            weekday = datetime.now().weekday()

            # Fetch prices (cached — only hits API every 10 mins)
            crypto = fetch_market_prices()
            btc_price = crypto.get("bitcoin", {}).get("usd", 0) if crypto else 0
            btc_change = crypto.get("bitcoin", {}).get("usd_24h_change", 0) if crypto else 0

            # Morning brief at 8am
            if hour == 8 and now - state["last_morning_brief"] > 43200 and crypto:
                post_morning_brief(crypto)
                state["last_morning_brief"] = now
                save_state(state)
                time.sleep(5)

            # Evening wrap at 8pm
            if hour == 20 and now - state["last_evening_wrap"] > 43200 and crypto:
                post_evening_wrap(crypto)
                state["last_evening_wrap"] = now
                save_state(state)
                time.sleep(5)

            # Weekly recap on Sunday
            if weekday == 6 and now - state["last_weekly_recap"] > 86400 and crypto:
                post_weekly_recap(crypto)
                state["last_weekly_recap"] = now
                save_state(state)
                time.sleep(5)

            # Weekly poll every 3 days
            if now - state["last_poll"] > 259200:
                post_weekly_poll()
                state["last_poll"] = now
                save_state(state)
                time.sleep(5)

            # BTC chart every 12 hours
            if now - state["last_btc_post"] > 43200:
                post_btc_chart()
                state["last_btc_post"] = now
                save_state(state)
                time.sleep(5)

            # Market correlation insight every 6 hours
            if now - state["last_correlation"] > 21600 and crypto:
                post_correlation(crypto)
                state["last_correlation"] = now
                save_state(state)
                time.sleep(5)

            # Price alert if BTC moves 3%+
            if btc_price > 0 and state["last_btc_price"] > 0:
                post_price_alert(btc_price, state["last_btc_price"])

            if btc_price > 0:
                state["last_btc_price"] = btc_price
                save_state(state)

            # Breaking news
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
