"""
Financial Data and News API Aggregator
Fetches real-time data from various APIs for the dashboard
"""

import requests
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
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', 'demo')
NSE_BASE_URL = 'https://www.nseindia.com/api'

# Cache to avoid hitting API limits
cache = {}
CACHE_DURATION = 120  # seconds

def is_cache_valid(key: str) -> bool:
    """Check if cached data is still valid"""
    if key not in cache:
        return False
    cached_time, _ = cache[key]
    return (datetime.now() - cached_time).seconds < CACHE_DURATION

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
    """Fetch stock/commodity data from Yahoo Finance"""
    cached = get_cached(f'yahoo_{symbol}')
    if cached:
        return cached

    try:
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d'
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get('chart', {}).get('result'):
            result = data['chart']['result'][0]
            quote = result['meta']

            current_price = quote.get('regularMarketPrice', 0)
            previous_close = quote.get('chartPreviousClose', current_price)
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
    data = fetch_yahoo_finance('GC=F')
    if data:
        # Convert USD per troy ounce to INR per 10g
        usd_inr = fetch_yahoo_finance('USDINR=X')
        if usd_inr:
            exchange_rate = usd_inr['value']
            # 1 troy ounce = 31.1035 grams
            inr_per_10g = (data['value'] * exchange_rate * 10) / 31.1035
            change_inr = (data['change'] * exchange_rate * 10) / 31.1035

            return jsonify({
                'symbol': 'GOLD',
                'value': round(inr_per_10g, 0),
                'change': round(change_inr, 0),
                'percent': data['percent'],
                'timestamp': datetime.now().isoformat()
            })
    return jsonify({'error': 'Unable to fetch data'})

@app.route('/api/market/silver')
def get_silver():
    """Get Silver price (converted to INR per kg)"""
    data = fetch_yahoo_finance('SI=F')
    if data:
        # Convert USD per troy ounce to INR per kg
        usd_inr = fetch_yahoo_finance('USDINR=X')
        if usd_inr:
            exchange_rate = usd_inr['value']
            # 1 troy ounce = 31.1035 grams, 1 kg = 1000g
            inr_per_kg = (data['value'] * exchange_rate * 1000) / 31.1035
            change_inr = (data['change'] * exchange_rate * 1000) / 31.1035

            return jsonify({
                'symbol': 'SILVER',
                'value': round(inr_per_kg, 0),
                'change': round(change_inr, 0),
                'percent': data['percent'],
                'timestamp': datetime.now().isoformat()
            })
    return jsonify({'error': 'Unable to fetch data'})

@app.route('/api/market/all')
def get_all_markets():
    """Get all market data in one call"""
    return jsonify({
        'sensex': fetch_yahoo_finance('^BSESN'),
        'nifty': fetch_yahoo_finance('^NSEI'),
        'dow': fetch_yahoo_finance('^DJI'),
        'forex': fetch_yahoo_finance('USDINR=X'),
        'gold': get_gold().get_json(),
        'silver': get_silver().get_json(),
        'timestamp': datetime.now().isoformat()
    })

# ============= FII/DII DATA =============

def fetch_fii_dii_data() -> Dict:
    """
    Fetch FII/DII data from NSE India
    Note: NSE requires specific headers and may block automated requests
    Alternative: Use moneycontrol.com or investing.com scraping
    """
    cached = get_cached('fii_dii')
    if cached:
        return cached

    try:
        # Using a free alternative API - you may need to implement web scraping
        # or use a paid service for reliable FII/DII data

        # For demonstration, using NSE India API (requires proper headers)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/'
        }

        # FII/DII data endpoint
        url = 'https://www.nseindia.com/api/fiidiiTradeReact'

        # Create session to handle cookies
        session = requests.Session()
        # First request to set cookies
        session.get('https://www.nseindia.com', headers=headers, timeout=10)

        # Now fetch FII/DII data
        response = session.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()

            # Parse the response (structure may vary)
            fii_dii_data = {
                'fii_net': 0,
                'dii_net': 0,
                'fii_mtd': 0,
                'dii_mtd': 0,
                'date': datetime.now().strftime('%Y-%m-%d')
            }

            # Extract data from response
            if isinstance(data, list) and len(data) > 0:
                latest = data[0]
                fii_dii_data['fii_net'] = latest.get('fii', {}).get('netValue', 0)
                fii_dii_data['dii_net'] = latest.get('dii', {}).get('netValue', 0)

            set_cache('fii_dii', fii_dii_data)
            return fii_dii_data

    except Exception as e:
        print(f"Error fetching FII/DII data: {e}")

    # Return placeholder data if API fails
    return {
        'fii_net': 0,
        'dii_net': 0,
        'fii_mtd': 0,
        'dii_mtd': 0,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'error': 'Data unavailable - API access restricted'
    }

def fetch_moneycontrol_fii_dii() -> Dict:
    """
    Alternative: Fetch FII/DII from Moneycontrol
    Uses web scraping as they don't have a public API
    """
    try:
        from bs4 import BeautifulSoup

        url = 'https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/index.php'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Parse the table data (implementation depends on site structure)
        # This is a placeholder - you'll need to inspect the HTML structure

        return {
            'fii_net': 0,
            'dii_net': 0,
            'fii_mtd': 0,
            'dii_mtd': 0,
            'note': 'Requires BeautifulSoup4 implementation'
        }
    except ImportError:
        return {'error': 'BeautifulSoup4 not installed'}
    except Exception as e:
        return {'error': str(e)}

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
    except Exception as e:
        print(f"Error fetching news for {category}: {e}")

    return []

def get_relative_time(date_string: str) -> str:
    """Convert ISO date to relative time"""
    try:
        date = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        now = datetime.now(date.tzinfo)
        diff = now - date

        minutes = diff.seconds // 60
        hours = diff.seconds // 3600
        days = diff.days

        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            return f"{days} day{'s' if days != 1 else ''} ago"
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

# ============= WEATHER DATA =============

@app.route('/api/weather')
def get_weather():
    """Get weather data (already handled by frontend, but available if needed)"""
    # This is optional since frontend uses Open-Meteo directly
    return jsonify({'message': 'Use Open-Meteo API directly from frontend'})

# ============= UTILITY ENDPOINTS =============

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
        'alpha_vantage_configured': bool(ALPHA_VANTAGE_KEY and ALPHA_VANTAGE_KEY != 'demo'),
        'message': 'Set NEWS_API_KEY environment variable for news data'
    })

# ============= MAIN =============

if __name__ == '__main__':
    # Get port from environment variable (Railway/Heroku) or default to 5000
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
    - GET /api/config           - Configuration status

    Environment Variables:
    - NEWS_API_KEY              - Get from newsapi.org (FREE)
    - ALPHA_VANTAGE_KEY         - Get from alphavantage.co (optional)
    - PORT                      - Server port (default: 5000)

    """.format(port))

    # Use debug=False in production (Railway/Heroku)
    is_production = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('DYNO')
    app.run(debug=not is_production, host='0.0.0.0', port=port)
