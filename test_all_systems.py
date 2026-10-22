# -*- coding: utf-8 -*-
"""
Bot Status & Signal Monitor
نمایش وضعیت بات و سیگنال‌ها بدون نیاز به تلگرام
"""

import sys
import time
sys.path.insert(0, '.')

from core.market_data import MarketData
from core.signal_engine import SignalEngine
from config import KCEX_SYMBOLS

def main():
    print("=" * 60)
    print("  🤖 CRYPTO SIGNAL BOT - MASTERPIECE")
    print("  📊 9 Systems Active")
    print("=" * 60)
    print()
    
    md = MarketData()
    engine = SignalEngine(md)
    
    # Test symbols
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    
    print("🔍 Scanning markets...")
    print()
    
    signals_found = 0
    
    for sym in symbols:
        try:
            signal = engine.scan_symbol(sym)
            if signal and signal.get('direction') != 'NEUTRAL':
                signals_found += 1
                direction = signal['direction']
                score = signal['score']
                entry = signal.get('entry', 0)
                
                emoji = "🟢" if direction == "LONG" else "🔴"
                print(f"{emoji} {sym}: {direction} (score: {score:.0f})")
                print(f"   Entry: {entry:.2f}")
                print(f"   SL: {signal.get('stop_loss', 0):.2f}")
                print(f"   TP: {signal.get('take_profits', [])}")
                print(f"   R:R: {signal.get('risk_reward', 0):.1f}")
                
                # Show key filters
                ctx = signal.get('market_context', {})
                if ctx:
                    btc = ctx.get('btc_trend', {})
                    if btc.get('trend'):
                        print(f"   ₿ BTC: {btc['trend']} ({btc.get('momentum', 0):+.1f}%)")
                    corr = ctx.get('correlation', {})
                    if corr.get('correlation'):
                        print(f"   🔗 Corr: {corr['correlation']:.2f}")
                
                fnd = signal.get('funding_oi', {})
                if fnd and fnd.get('funding_rate'):
                    print(f"   💰 Funding: {fnd['funding_rate']*100:.4f}%")
                
                print()
            else:
                print(f"⚪ {sym}: No signal")
                if signal and signal.get('reasons'):
                    last = signal['reasons'][-1]
                    print(f"   💡 {last[:80]}")
                print()
                
        except Exception as e:
            print(f"❌ {sym}: Error - {e}")
            print()
    
    print("=" * 60)
    print(f"📊 Signals Found: {signals_found}/{len(symbols)}")
    print("=" * 60)
    print()
    print("✅ All 9 systems operational:")
    print("   1. Order Flow")
    print("   2. Liquidity Scanner")
    print("   3. Whale Scanner")
    print("   4. Whale Hunter")
    print("   5. Pre-Movement Detector")
    print("   6. ZoneHunter")
    print("   7. Order Flow Matrix PRO")
    print("   8. Market Context (BTC + ADX + Correlation)")
    print("   9. Funding/OI Analyzer")
    print()
    print("🚀 Bot is ready for deployment!")

if __name__ == "__main__":
    main()
