"""
Financial Data and News API Aggregator
Deployed as a Vercel Python serverless function (WSGI / Flask).
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
CACHE_DURATION = 300  # 5 minutes

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

# ============= MARKET DATA =============
# Stooq: free CSV API. Used for Dow, USD/INR, Gold, Silver.
# Yahoo Finance v8: free JSON API (server-side only).
#   Used for Sensex (^BSESN) and Nifty (^NSEI) — Stooq returns "No data" for Indian indices.
#   Also used as fallback when Stooq rate-limits the serverless IP.

def fetch_yahoo_finance(symbol: str) -> Optional[Dict]:
    """Fetch market data from Yahoo Finance v8 API (no API key needed)"""
    cache_key = f'yf_{symbol}'
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"Yahoo Finance {symbol}: HTTP {response.status_code}")
            return None

        payload = response.json()
        result = payload.get('chart', {}).get('result', [])
        if not result:
            print(f"Yahoo Finance {symbol}: no result in response")
            return None

        meta = result[0].get('meta', {})
        current_price = float(meta.get('regularMarketPrice', 0) or 0)
        prev_close = float(meta.get('chartPreviousClose', current_price) or current_price)

        if not current_price:
            print(f"Yahoo Finance {symbol}: zero price")
            return None

        change = current_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        data = {
            'symbol': symbol,
            'value': round(current_price, 2),
            'change': round(change, 2),
            'percent': round(change_pct, 2),
            'timestamp': datetime.now().isoformat()
        }
        set_cache(cache_key, data)
        print(f"Yahoo Finance {symbol}: {current_price} (change: {change:+.2f})")
        return data

    except Exception as e:
        print(f"Error fetching {symbol} from Yahoo Finance: {e}")
        return None

def fetch_stooq(symbol: str) -> Optional[Dict]:
    """Fetch market data from Stooq (free, no API key)"""
    cached = get_cached(f'stooq_{symbol}')
    if cached:
        return cached

    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        url = f'https://stooq.com/q/d/l/?s={symbol}&d1={start_date}&d2={end_date}&i=d'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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

        # Sort newest-first — Stooq's row order varies by symbol
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

# Yahoo Finance fallback when Stooq rate-limits the serverless IP
_STOOQ_YF_MAP = {
    '^dji':   '^DJI',
    'usdinr': 'USDINR=X',
    'xauusd': 'GC=F',
    'xagusd': 'SI=F',
}

def fetch_market(stooq_symbol: str) -> Optional[Dict]:
    """Try Stooq first; fall back to Yahoo Finance if unavailable."""
    result = fetch_stooq(stooq_symbol)
    if result:
        return result
    yf_symbol = _STOOQ_YF_MAP.get(stooq_symbol)
    if yf_symbol:
        print(f"Stooq unavailable for {stooq_symbol}, trying Yahoo Finance ({yf_symbol})")
        return fetch_yahoo_finance(yf_symbol)
    return None

def compute_gold_inr() -> Optional[Dict]:
    """Gold price in INR per 10g"""
    gold_usd = fetch_market('xauusd')
    usd_inr = fetch_market('usdinr')
    if gold_usd and usd_inr:
        rate = usd_inr['value']
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
    silver_usd = fetch_market('xagusd')
    usd_inr = fetch_market('usdinr')
    if silver_usd and usd_inr:
        rate = usd_inr['value']
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
    data = fetch_yahoo_finance('^BSESN')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/nifty')
def get_nifty():
    data = fetch_yahoo_finance('^NSEI')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/dow')
def get_dow():
    data = fetch_market('^dji')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/forex')
def get_forex():
    data = fetch_market('usdinr')
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
        'sensex': fetch_yahoo_finance('^BSESN'),
        'nifty': fetch_yahoo_finance('^NSEI'),
        'dow': fetch_market('^dji'),
        'forex': fetch_market('usdinr'),
        'gold': compute_gold_inr(),
        'silver': compute_silver_inr(),
        'timestamp': datetime.now().isoformat()
    })

# ============= FII/DII DATA =============
# NSE's web API blocks cloud IPs, but the mobile app endpoint works.
# MTD accumulation is in-memory (resets per serverless invocation on Vercel).

def fetch_fii_dii_data() -> Dict:
    cached = get_cached('fii_dii')
    if cached:
        return cached

    result = {
        'fii_net': None, 'dii_net': None,
        'fii_mtd': None, 'dii_mtd': None,
        'date': datetime.now().strftime('%Y-%m-%d')
    }

    try:
        headers = {
            'User-Agent': 'NSEMobile/1.0 (Android)',
            'Accept': 'application/json',
            'X-Requested-With': 'NSEApp',
        }
        response = requests.get(
            'https://www.nseindia.com/api/fiidiiTradeReact',
            headers=headers,
            timeout=10
        )
        print(f"NSE FII/DII status: {response.status_code}, body_len: {len(response.text)}")

        if response.status_code == 200 and response.text.strip():
            data = response.json()
            if isinstance(data, list):
                for entry in data:
                    category = (entry.get('category') or '').upper()
                    net_str = entry.get('netValue')
                    if net_str is not None:
                        try:
                            net_val = round(float(str(net_str).replace(',', '')), 2)
                            if 'FII' in category or 'FPI' in category:
                                result['fii_net'] = net_val
                            elif 'DII' in category:
                                result['dii_net'] = net_val
                        except (ValueError, TypeError):
                            pass
        else:
            print(f"NSE FII/DII: empty or non-200 response")

    except Exception as e:
        print(f"Error fetching FII/DII: {e}")

    print(f"FII/DII: NET FII={result['fii_net']}, DII={result['dii_net']}")
    set_cache('fii_dii', result)
    return result

@app.route('/api/fii-dii')
def get_fii_dii():
    return jsonify(fetch_fii_dii_data())

# ============= NEWS DATA =============

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
    except Exception:
        return "Recently"

def fetch_news_by_category(query: str, category: str, page_size: int = 4) -> List[Dict]:
    if not NEWS_API_KEY:
        return []

    cached = get_cached(f'news_{category}')
    if cached:
        return cached

    try:
        params = {
            'q': query,
            'language': 'en',
            'sortBy': 'publishedAt',
            'pageSize': page_size,
            'apiKey': NEWS_API_KEY
        }
        response = requests.get('https://newsapi.org/v2/everything', params=params, timeout=10)
        data = response.json()

        if data.get('status') == 'ok':
            articles = []
            for article in data.get('articles', []):
                title = article.get('title', '') or ''
                url_val = article.get('url', '') or ''
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
        all_articles.extend(fetch_news_by_category(query, category, page_size=3))

    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        url = article.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)

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

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'apis': {
            'news': bool(NEWS_API_KEY),
            'market_data': 'yahoo_finance + stooq',
        }
    })
