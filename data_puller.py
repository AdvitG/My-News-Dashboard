"""
Financial Data and News API Aggregator
Fetches real-time data from various APIs for the dashboard
"""

import requests
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Optional
import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__)
CORS(app)

# API Configuration
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')  # Get from newsapi.org

# Cache to avoid hitting API limits
cache = {}
CACHE_DURATION = 120  # seconds

def is_cache_valid(key: str) -> bool:
    """Check if cached data is still valid"""
    if key not in cache:
        return False
    cached_time, _ = cache[key]
    return (datetime.now() - cached_time).total_seconds() < CACHE_DURATION

def get_cached(key: str):
    """Get cached data if valid"""
    if is_cache_valid(key):
        return cache[key][1]
    return None

def set_cache(key: str, data):
    """Set cache with current timestamp"""
    cache[key] = (datetime.now(), data)

# ============= MARKET DATA APIs =============

def fetch_yahoo_finance(symbol: str) -> Optional[Dict]:
    """Fetch stock/commodity data using yfinance"""
    cached = get_cached(f'yahoo_{symbol}')
    if cached:
        return cached

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info

        current_price = info.last_price
        previous_close = info.previous_close

        if not current_price or not previous_close:
            print(f"No price data returned for {symbol}")
            return None

        change = current_price - previous_close
        change_percent = (change / previous_close) * 100 if previous_close else 0

        market_data = {
            'symbol': symbol,
            'value': round(current_price, 2),
            'change': round(change, 2),
            'percent': round(change_percent, 2),
            'timestamp': datetime.now().isoformat()
        }

        set_cache(f'yahoo_{symbol}', market_data)
        return market_data
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")

    return None

def compute_gold_inr() -> Optional[Dict]:
    """Compute Gold price in INR per 10g"""
    data = fetch_yahoo_finance('GC=F')
    if data:
        usd_inr = fetch_yahoo_finance('USDINR=X')
        if usd_inr:
            exchange_rate = usd_inr['value']
            # 1 troy ounce = 31.1035 grams
            inr_per_10g = (data['value'] * exchange_rate * 10) / 31.1035
            change_inr = (data['change'] * exchange_rate * 10) / 31.1035
            return {
                'symbol': 'GOLD',
                'value': round(inr_per_10g, 0),
                'change': round(change_inr, 0),
                'percent': data['percent'],
                'timestamp': datetime.now().isoformat()
            }
    return None

def compute_silver_inr() -> Optional[Dict]:
    """Compute Silver price in INR per kg"""
    data = fetch_yahoo_finance('SI=F')
    if data:
        usd_inr = fetch_yahoo_finance('USDINR=X')
        if usd_inr:
            exchange_rate = usd_inr['value']
            # 1 troy ounce = 31.1035 grams, 1 kg = 1000g
            inr_per_kg = (data['value'] * exchange_rate * 1000) / 31.1035
            change_inr = (data['change'] * exchange_rate * 1000) / 31.1035
            return {
                'symbol': 'SILVER',
                'value': round(inr_per_kg, 0),
                'change': round(change_inr, 0),
                'percent': data['percent'],
                'timestamp': datetime.now().isoformat()
            }
    return None

@app.route('/api/market/sensex')
def get_sensex():
    """Get BSE Sensex data"""
    data = fetch_yahoo_finance('^BSESN')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/nifty')
def get_nifty():
    """Get Nifty 50 data"""
    data = fetch_yahoo_finance('^NSEI')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/dow')
def get_dow():
    """Get Dow Jones data"""
    data = fetch_yahoo_finance('^DJI')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/forex')
def get_forex():
    """Get USD/INR exchange rate"""
    data = fetch_yahoo_finance('USDINR=X')
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/gold')
def get_gold():
    """Get Gold price (converted to INR per 10g)"""
    data = compute_gold_inr()
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/silver')
def get_silver():
    """Get Silver price (converted to INR per kg)"""
    data = compute_silver_inr()
    return jsonify(data or {'error': 'Unable to fetch data'})

@app.route('/api/market/all')
def get_all_markets():
    """Get all market data in one call"""
    return jsonify({
        'sensex': fetch_yahoo_finance('^BSESN'),
        'nifty': fetch_yahoo_finance('^NSEI'),
        'dow': fetch_yahoo_finance('^DJI'),
        'forex': fetch_yahoo_finance('USDINR=X'),
        'gold': compute_gold_inr(),
        'silver': compute_silver_inr(),
        'timestamp': datetime.now().isoformat()
    })

# ============= FII/DII DATA =============

def fetch_fii_dii_data() -> Dict:
    """
    Fetch FII/DII data from NSE India.
    NSE requires a valid browser session (cookies) before serving the API.
    Returns None values if unavailable — frontend shows N/A.
    """
    cached = get_cached('fii_dii')
    if cached:
        return cached

    try:
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        api_headers = {
            **headers,
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.nseindia.com/market-data/fii-dii-activity',
            'X-Requested-With': 'XMLHttpRequest',
        }

        # Two warmup requests to establish session cookies (NSE requires this)
        session.get('https://www.nseindia.com', headers=headers, timeout=15)
        session.get('https://www.nseindia.com/market-data/fii-dii-activity', headers=headers, timeout=10)

        response = session.get(
            'https://www.nseindia.com/api/fiidiiTradeReact',
            headers=api_headers,
            timeout=10
        )

        print(f"NSE FII/DII status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            result = {
                'fii_net': None,
                'dii_net': None,
                'fii_mtd': None,
                'dii_mtd': None,
                'date': datetime.now().strftime('%Y-%m-%d')
            }

            if isinstance(data, list) and len(data) > 0:
                latest = data[0]
                fii_block = latest.get('fii', latest)
                dii_block = latest.get('dii', latest)
                result['fii_net'] = fii_block.get('netValue', fii_block.get('NET', None))
                result['dii_net'] = dii_block.get('netValue', dii_block.get('NET', None))
                # MTD: sum the available rows
                if len(data) > 1:
                    try:
                        result['fii_mtd'] = round(sum(
                            float(r.get('fii', r).get('netValue', 0) or 0) for r in data
                        ), 2)
                        result['dii_mtd'] = round(sum(
                            float(r.get('dii', r).get('netValue', 0) or 0) for r in data
                        ), 2)
                    except Exception:
                        pass

            set_cache('fii_dii', result)
            return result

        print(f"NSE API blocked (status {response.status_code}) — FII/DII unavailable from cloud")

    except Exception as e:
        print(f"Error fetching FII/DII data: {e}")

    return {
        'fii_net': None,
        'dii_net': None,
        'fii_mtd': None,
        'dii_mtd': None,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'error': 'Data unavailable - NSE API restricted from cloud servers'
    }

@app.route('/api/fii-dii')
def get_fii_dii():
    """Get FII/DII investment data"""
    data = fetch_fii_dii_data()
    return jsonify(data)

# ============= NEWS DATA =============

def fetch_news_by_category(query: str, category: str, page_size: int = 5) -> List[Dict]:
    """Fetch news from NewsAPI"""
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
                articles.append({
                    'category': category,
                    'title': article.get('title', ''),
                    'summary': article.get('description') or article.get('content', '')[:150] + '...',
                    'source': article.get('source', {}).get('name', 'Unknown'),
                    'time': get_relative_time(article.get('publishedAt')),
                    'url': article.get('url', '#'),
                    'imageUrl': article.get('urlToImage'),
                    'publishedAt': article.get('publishedAt')
                })

            set_cache(f'news_{category}', articles)
            return articles
        else:
            print(f"NewsAPI error for {category}: {data.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"Error fetching news for {category}: {e}")

    return []

def get_relative_time(date_string: str) -> str:
    """Convert ISO date to relative time"""
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
    """Get news for a specific category"""
    queries = {
        'india': 'India',
        'gurgaon': 'Gurgaon OR Gurugram',
        'tech': 'technology OR AI OR artificial intelligence',
        'business': 'business OR finance OR economy',
        'science': 'science OR research OR space',
        'politics': 'politics OR government OR election'
    }

    query = queries.get(category, category)
    articles = fetch_news_by_category(query, category)
    return jsonify(articles)

@app.route('/api/news/all')
def get_all_news():
    """Get news from all categories"""
    categories = ['india', 'gurgaon', 'tech', 'business', 'science', 'politics']
    all_articles = []

    for category in categories:
        articles = fetch_news_by_category(
            {
                'india': 'India',
                'gurgaon': 'Gurgaon OR Gurugram',
                'tech': 'technology OR AI',
                'business': 'business OR finance',
                'science': 'science OR research',
                'politics': 'politics OR government'
            }[category],
            category,
            page_size=3
        )
        all_articles.extend(articles)

    return jsonify(all_articles)

@app.route('/api/news/custom/<topic>')
def get_custom_news(topic: str):
    """Get news for a custom topic"""
    articles = fetch_news_by_category(topic, f'custom_{topic}', page_size=5)
    return jsonify(articles)

# ============= UTILITY ENDPOINTS =============

@app.route('/')
def index():
    """Root route - confirms server is running"""
    return jsonify({
        'status': 'running',
        'message': 'Dashboard API is live!',
        'endpoints': '/api/health  |  /api/market/all  |  /api/news/all  |  /api/fii-dii'
    })

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'apis': {
            'news': bool(NEWS_API_KEY),
            'yahoo_finance': True,
            'open_meteo': True
        }
    })

@app.route('/api/config')
def get_config():
    """Get API configuration status"""
    return jsonify({
        'news_api_configured': bool(NEWS_API_KEY),
        'message': 'Set NEWS_API_KEY environment variable for news data'
    })

# ============= MAIN =============

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))

    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║         Financial Data & News API Server                  ║
    ╚════════════════════════════════════════════════════════════╝

    Server starting on http://0.0.0.0:{}

    API Endpoints:
    - GET /api/market/all       - All market data
    - GET /api/market/sensex    - BSE Sensex
    - GET /api/market/nifty     - Nifty 50
    - GET /api/market/dow       - Dow Jones
    - GET /api/market/forex     - USD/INR
    - GET /api/market/gold      - Gold prices
    - GET /api/market/silver    - Silver prices
    - GET /api/fii-dii          - FII/DII data
    - GET /api/news/all         - All news
    - GET /api/news/<category>  - News by category
    - GET /api/health           - Health check

    Environment Variables:
    - NEWS_API_KEY              - Get from newsapi.org (FREE)
    - PORT                      - Server port (default: 5000)

    """.format(port))

    is_production = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('DYNO')
    app.run(debug=not is_production, host='0.0.0.0', port=port)
