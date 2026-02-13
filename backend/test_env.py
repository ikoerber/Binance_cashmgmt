"""
Test Environment Variables

Prüft ob .env korrekt geladen wird
"""
from dotenv import load_dotenv
import os

# Load .env
load_dotenv()

print("🔍 Checking Environment Variables...")
print("=" * 50)

# Check Binance Keys
api_key = os.getenv("BINANCE_API_KEY", "")
api_secret = os.getenv("BINANCE_API_SECRET", "")
testnet = os.getenv("BINANCE_TESTNET", "true")

print(f"BINANCE_API_KEY:    {'✅ Set' if api_key else '❌ Not set'}")
if api_key:
    print(f"                    {api_key[:10]}...{api_key[-4:]}")

print(f"BINANCE_API_SECRET: {'✅ Set' if api_secret else '❌ Not set'}")
if api_secret:
    print(f"                    {api_secret[:10]}...{api_secret[-4:]}")

print(f"BINANCE_TESTNET:    {testnet}")

print("=" * 50)

if api_key and api_secret:
    print("✅ Binance API credentials configured!")
    print("\n🧪 Testing Binance connection...")

    try:
        from binance.client import Client
        client = Client(api_key, api_secret, testnet=(testnet.lower() == 'true'))

        # Test API call
        account = client.get_account()
        print(f"✅ Connection successful!")
        print(f"   Account Type: {account.get('accountType', 'N/A')}")
        print(f"   Can Trade: {account.get('canTrade', False)}")

        # Show balances
        print("\n💰 Balances:")
        balances = [b for b in account['balances'] if float(b['free']) > 0 or float(b['locked']) > 0]
        for balance in balances[:5]:  # Show first 5
            asset = balance['asset']
            free = balance['free']
            locked = balance['locked']
            print(f"   {asset}: {free} (free), {locked} (locked)")

    except Exception as e:
        print(f"❌ Connection failed: {e}")
else:
    print("❌ Binance API credentials NOT configured!")
    print("\n📝 To fix:")
    print("1. Edit backend/.env")
    print("2. Add your Binance API keys:")
    print("   BINANCE_API_KEY=your_key")
    print("   BINANCE_API_SECRET=your_secret")
    print("   BINANCE_TESTNET=true  # or false for production")
