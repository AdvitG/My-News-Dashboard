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

# ============= MARKET DATA =============
# Stooq: free CSV API, works from cloud. Used for Dow, USD/INR, Gold, Silver.
# Yahoo Finance v8: free JSON API, works from cloud (server-side only, no CORS key needed).
#   Used for Sensex (^BSESN) and Nifty (^NSEI) — Stooq returns "No data" for Indian indices.

def fetch_yahoo_finance(symbol: str) -> Optional[Dict]:
    """Fetch market data from Yahoo Finance v8 API (server-side only, no API key needed)"""
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

# Yahoo Finance fallback symbols for when Stooq rate-limits Railway's IP
_STOOQ_YF_MAP = {
    '^dji':   '^DJI',
    'usdinr': 'USDINR=X',
    'xauusd': 'GC=F',
    'xagusd': 'SI=F',
}

def fetch_market(stooq_symbol: str) -> Optional[Dict]:
    """Try Stooq first; fall back to Yahoo Finance if Stooq is unavailable."""
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
    gold_usd = fetch_market('xauusd')   # Gold spot price in USD/troy oz
    usd_inr = fetch_market('usdinr')    # USD/INR exchange rate
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
    silver_usd = fetch_market('xagusd')  # Silver spot price in USD/troy oz
    usd_inr = fetch_market('usdinr')
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
# NSE's web API blocks cloud server IPs, but the mobile app endpoint works.
# The mobile API only returns the most recent trading day's data per call.
# MTD is accumulated in-memory (resets on server restart but rebuilds each day).

_fii_history: Dict[str, Dict] = {}  # keyed by "YYYY-MM-DD", e.g. {"2026-03-03": {"fii": -1234, "dii": 5678}}

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
        # NSE mobile app endpoint — bypasses the IP block that affects the web API
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
            print(f"NSE FII/DII data: {data}")

            if isinstance(data, list):
                fii_net = None
                dii_net = None
                data_date_key = datetime.now().strftime('%Y-%m-%d')

                for entry in data:
                    category = (entry.get('category') or '').upper()
                    net_str = entry.get('netValue')
                    # Parse the date from API response e.g. "27-Feb-2026"
                    raw_date = entry.get('date', '')
                    if raw_date:
                        try:
                            data_date_key = datetime.strptime(raw_date, '%d-%b-%Y').strftime('%Y-%m-%d')
                        except Exception:
                            pass
                    if net_str is not None:
                        try:
                            net_val = round(float(str(net_str).replace(',', '')), 2)
                            if 'FII' in category or 'FPI' in category:
                                fii_net = net_val
                            elif 'DII' in category:
                                dii_net = net_val
                        except (ValueError, TypeError):
                            pass

                result['fii_net'] = fii_net
                result['dii_net'] = dii_net

                # Store in history for MTD accumulation
                if fii_net is not None or dii_net is not None:
                    _fii_history[data_date_key] = {
                        'fii': fii_net if fii_net is not None else 0,
                        'dii': dii_net if dii_net is not None else 0,
                    }

                # MTD = sum of all days in the current calendar month from history
                current_month = datetime.now().strftime('%Y-%m')
                month_data = [v for k, v in _fii_history.items() if k.startswith(current_month)]
                if month_data:
                    result['fii_mtd'] = round(sum(v['fii'] for v in month_data), 2)
                    result['dii_mtd'] = round(sum(v['dii'] for v in month_data), 2)

        else:
            print(f"NSE FII/DII: empty or non-200 response")

    except Exception as e:
        print(f"Error fetching FII/DII: {e}")

    print(f"FII/DII: NET FII={result['fii_net']}, DII={result['dii_net']}, MTD FII={result['fii_mtd']}, DII={result['dii_mtd']}")
    set_cache('fii_dii', result)
    return result

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
