"""
Financial Data and News API Aggregator
Fetches real-time data from various APIs for the dashboard
"""

import requests
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')

cache = {}
CACHE_DURATION = 300  # 5 minutes — gives fresher data while staying within NewsAPI limits

def is_cache_valid(key: str) -> bool:
    if key not in cache:
        return False
    cached_time, _ = cache[key]
    return (datetime.now() - cached_time).total_seconds() < CACHE_DURATION

def get_cached(key: str):
    if is_cache_valid(key):
        return cache[key][1]
    return None

def set_cache(key: str, data):
    cache[key] = (datetime.now(), data)

# ============= MARKET DATA (Stooq) =============
# Stooq is a free financial data provider that works from cloud servers.
# No API key required. Returns CSV data for stocks, indices, forex, commodities.
# Symbols: ^bsesn (Sensex), ^nsei (Nifty), ^dji (Dow), usdinr (USD/INR),
#          xauusd (Gold/USD), xagusd (Silver/USD)

def fetch_stooq(symbol: str) -> Optional[Dict]:
    """Fetch market data from Stooq (free, no API key, cloud-friendly)"""
    cached = get_cached(f'stooq_{symbol}')
    if cached:
        return cached

    try:
        # Limit to last 7 days — avoids getting the entire multi-decade history
        # which causes row[0] to be from the 1890s for symbols like ^dji or usdinr
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        url = f'https://stooq.com/q/d/l/?s={symbol}&d1={start_date}&d2={end_date}&i=d'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"Stooq {symbol}: HTTP {response.status_code}")
            return None

        text = response.text.strip()
        if not text or 'No data' in text:
            print(f"Stooq {symbol}: empty or no data response")
            return None

        rows = list(csv.DictReader(io.StringIO(text)))

        if len(rows) < 1:
            print(f"Stooq {symbol}: no rows in CSV")
            return None

        # Sort by Date descending — Stooq return order varies by symbol
        try:
            rows.sort(key=lambda r: r.get('Date', ''), reverse=True)
        except Exception:
            pass

        current_price = float(rows[0].get('Close', 0) or 0)
        if not current_price:
            print(f"Stooq {symbol}: zero/null close price")
            return None

        prev_close = float(rows[1].get('Close', current_price) or current_price) if len(rows) >= 2 else current_price
        change = current_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        data = {
            'symbol': symbol,
            'value': round(current_price, 2),
            'change': round(change, 2),
            'percent': round(change_pct, 2),
            'timestamp': datetime.now().isoformat()
        }

        set_cache(f'stooq_{symbol}', data)
        print(f"Stooq {symbol}: {current_price} (change: {change:+.2f})")
        return data

    except Exception as e:
        print(f"Error fetching {symbol} from Stooq: {e}")
        return None

def compute_gold_inr() -> Optional[Dict]:
    """Gold price in INR per 10g"""
    gold_usd = fetch_stooq('xauusd')   # Gold spot price in USD/troy oz
    usd_inr = fetch_stooq('usdinr')    # USD/INR exchange rate
    if gold_usd and usd_inr:
        rate = usd_inr['value']
        # 1 troy oz = 31.1035g → price per 10g
        inr_per_10g = (gold_usd['value'] * rate * 10) / 31.1035
        change_inr = (gold_usd['change'] * rate * 10) / 31.1035
        return {
            'symbol': 'GOLD',
            'value': round(inr_per_10g, 0),
            'change': round(change_inr, 0),
            'percent': round(gold_usd['percent'], 2),
            'timestamp': datetime.now().isoformat()
        }
    return None

def compute_silver_inr() -> Optional[Dict]:
    """Silver price in INR per kg"""
    silver_usd = fetch_stooq('xagusd')  # Silver spot price in USD/troy oz
    usd_inr = fetch_stooq('usdinr')
    if silver_usd and usd_inr:
        rate = usd_inr['value']
        # 1 troy oz = 31.1035g, 1 kg = 1000g
        inr_per_kg = (silver_usd['value'] * rate * 1000) / 31.1035
        change_inr = (silver_usd['change'] * rate * 1000) / 31.1035
        return {
            'symbol': 'SILVER',
            'value': round(inr_per_kg, 0),
            'change': round(change_inr, 0),
            'percent': round(silver_usd['percent'], 2),
            'timestamp': datetime.now().isoformat()
        }
    return None

@app.route('/api/market/sensex')
def get_sensex():
    data = fetch_stooq('^bsesn')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/nifty')
def get_nifty():
    data = fetch_stooq('^nsei')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/dow')
def get_dow():
    data = fetch_stooq('^dji')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/forex')
def get_forex():
    data = fetch_stooq('usdinr')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/gold')
def get_gold():
    data = compute_gold_inr()
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/silver')
def get_silver():
    data = compute_silver_inr()
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/all')
def get_all_markets():
    return jsonify({
        'sensex': fetch_stooq('^bsesn'),
        'nifty': fetch_stooq('^nsei'),
        'dow': fetch_stooq('^dji'),
        'forex': fetch_stooq('usdinr'),
        'gold': compute_gold_inr(),
        'silver': compute_silver_inr(),
        'timestamp': datetime.now().isoformat()
    })

# ============= FII/DII DATA =============
# NSE India returns HTTP 200 but with empty body from cloud server IPs
# (confirmed in Railway logs). This is their IP-level blocking mechanism.
# No workaround exists without a paid data provider.
# Returns None values so the frontend displays N/A.

def fetch_fii_dii_data() -> Dict:
    cached = get_cached('fii_dii')
    if cached:
        return cached

    try:
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        }
        api_headers = {
            **headers,
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.nseindia.com/market-data/fii-dii-activity',
            'X-Requested-With': 'XMLHttpRequest',
        }

        session.get('https://www.nseindia.com', headers=headers, timeout=15)
        session.get('https://www.nseindia.com/market-data/fii-dii-activity', headers=headers, timeout=10)

        response = session.get(
            'https://www.nseindia.com/api/fiidiiTradeReact',
            headers=api_headers,
            timeout=10
        )

        print(f"NSE FII/DII status: {response.status_code}, body_len: {len(response.text)}")

        # NSE returns 200 with empty body when blocking cloud IPs
        if response.status_code == 200 and response.text.strip():
            data = response.json()
            print(f"NSE FII/DII data keys: {list(data[0].keys()) if isinstance(data, list) and data else type(data)}")

            result = {
                'fii_net': None, 'dii_net': None,
                'fii_mtd': None, 'dii_mtd': None,
                'date': datetime.now().strftime('%Y-%m-%d')
            }

            if isinstance(data, list) and len(data) > 0:
                latest = data[0]
                # Try common NSE response structures
                fii_block = latest.get('fii', {})
                dii_block = latest.get('dii', {})

                if isinstance(fii_block, dict):
                    result['fii_net'] = fii_block.get('netValue') or fii_block.get('NET')
                    result['dii_net'] = (dii_block.get('netValue') or dii_block.get('NET')) if isinstance(dii_block, dict) else None
                else:
                    # Flat structure fallback
                    result['fii_net'] = latest.get('fiiNet') or latest.get('fii_net')
                    result['dii_net'] = latest.get('diiNet') or latest.get('dii_net')

                # Only compute MTD if we successfully got today's net — avoids summing
                # 0-defaults when NSE key structure doesn't match, which produces ₹0 Cr
                if len(data) > 1 and result['fii_net'] is not None:
                    try:
                        result['fii_mtd'] = round(sum(
                            float(r.get('fii', {}).get('netValue', 0) or 0) for r in data
                        ), 2)
                        result['dii_mtd'] = round(sum(
                            float(r.get('dii', {}).get('netValue', 0) or 0) for r in data
                        ), 2)
                    except Exception:
                        pass

            set_cache('fii_dii', result)
            return result

        print(f"NSE returned empty body — cloud IP blocked")

    except Exception as e:
        print(f"Error fetching FII/DII: {e}")

    return {
        'fii_net': None, 'dii_net': None,
        'fii_mtd': None, 'dii_mtd': None,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'error': 'NSE blocks cloud server IPs — data unavailable'
    }

@app.route('/api/fii-dii')
def get_fii_dii():
    return jsonify(fetch_fii_dii_data())

# ============= NEWS DATA =============

def fetch_news_by_category(query: str, category: str, page_size: int = 4) -> List[Dict]:
    if not NEWS_API_KEY:
        return []

    cached = get_cached(f'news_{category}')
    if cached:
        return cached

    try:
        url = 'https://newsapi.org/v2/everything'
        params = {
            'q': query,
            'language': 'en',
            'sortBy': 'publishedAt',
            'pageSize': page_size,
            'apiKey': NEWS_API_KEY
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get('status') == 'ok':
            articles = []
            for article in data.get('articles', []):
                title = article.get('title', '') or ''
                url_val = article.get('url', '') or ''
                # Skip removed/deleted articles
                if '[Removed]' in title or not url_val:
                    continue
                articles.append({
                    'category': category,
                    'title': title,
                    'summary': article.get('description') or '',
                    'source': article.get('source', {}).get('name', 'Unknown'),
                    'time': get_relative_time(article.get('publishedAt')),
                    'url': url_val,
                    'publishedAt': article.get('publishedAt')
                })
            set_cache(f'news_{category}', articles)
            return articles
        else:
            print(f"NewsAPI error for {category}: {data.get('message', data.get('status'))}")

    except Exception as e:
        print(f"Error fetching news for {category}: {e}")

    return []

def get_relative_time(date_string: str) -> str:
    try:
        date = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        now = datetime.now(date.tzinfo)
        diff = now - date
        total_seconds = int(diff.total_seconds())
        days = diff.days
        hours = total_seconds // 3600
        minutes = total_seconds // 60

        if days > 0:
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif hours > 0:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    except:
        return "Recently"

@app.route('/api/news/<category>')
def get_news_category(category: str):
    queries = {
        'india': 'India',
        'gurgaon': 'Gurgaon OR Gurugram',
        'tech': 'technology OR AI OR artificial intelligence',
        'business': 'business OR finance OR economy',
        'science': 'science OR research OR space',
        'politics': 'politics OR government OR election'
    }
    articles = fetch_news_by_category(queries.get(category, category), category)
    return jsonify(articles)

@app.route('/api/news/all')
def get_all_news():
    """Return up to 8 deduplicated articles across all categories"""
    category_queries = {
        'india': 'India',
        'gurgaon': 'Gurgaon OR Gurugram',
        'tech': 'technology OR AI',
        'business': 'business OR finance',
        'science': 'science OR research',
        'politics': 'politics OR government'
    }

    all_articles = []
    for category, query in category_queries.items():
        articles = fetch_news_by_category(query, category, page_size=3)
        all_articles.extend(articles)

    # Deduplicate by URL — same article can appear in multiple category searches
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        url = article.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)

    # Sort by publishedAt (newest first) and return 8
    try:
        unique_articles.sort(key=lambda a: a.get('publishedAt', ''), reverse=True)
    except Exception:
        pass

    return jsonify(unique_articles[:8])

@app.route('/api/news/custom/<topic>')
def get_custom_news(topic: str):
    articles = fetch_news_by_category(topic, f'custom_{topic}', page_size=4)
    return jsonify(articles)

# ============= UTILITY ENDPOINTS =============

@app.route('/')
def index():
    return jsonify({
        'status': 'running',
        'message': 'Dashboard API is live!',
        'market_data': 'Powered by Stooq (free, no API key)',
        'endpoints': '/api/health | /api/market/all | /api/news/all | /api/fii-dii'
    })

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'apis': {
            'news': bool(NEWS_API_KEY),
            'market_data': 'stooq',
            'open_meteo': True
        }
    })

@app.route('/api/config')
def get_config():
    return jsonify({
        'news_api_configured': bool(NEWS_API_KEY),
        'market_data_source': 'Stooq (free, no key needed)',
        'message': 'Set NEWS_API_KEY environment variable for news data'
    })

# ============= MAIN =============

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"""
    ╔════════════════════════════════════════════════════════════╗
    ║         Financial Data & News API Server                  ║
    ╚════════════════════════════════════════════════════════════╝
    Starting on http://0.0.0.0:{port}
    Market data: Stooq (free, no API key)
    News:        NewsAPI (requires NEWS_API_KEY env var)
    """)
    is_production = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('DYNO')
    app.run(debug=not is_production, host='0.0.0.0', port=port)
