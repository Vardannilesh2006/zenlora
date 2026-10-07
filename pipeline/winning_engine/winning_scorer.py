import os
import sys
from typing import Dict, Any, List

# Add parent directory to path to import classifier_pricing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from classifier_pricing import ClassifierAndPricingEngine
except ImportError:
    ClassifierAndPricingEngine = None

def compute_winning_score(product: Dict[str, Any], meta_signals: Dict[str, Any], trend_signals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes the Zenlora 0-100 Winning Score (ZWI), badges, and actionable bullet reasoning.
    """
    wholesale_price = float(product.get("wholesale_price", 150))
    niche = product.get("niche", "Home Decor")
    title = product.get("title", "")
    title_lower = title.lower()

    # 1. Pricing & Margin Calculation
    if ClassifierAndPricingEngine:
        pricing = ClassifierAndPricingEngine.calculate_pricing(wholesale_price)
    else:
        selling_price = max(499, int(wholesale_price * 3.2))
        landed_cost = wholesale_price + 70
        gross_profit = selling_price - landed_cost
        pricing = {
            "wholesale_price": wholesale_price,
            "selling_price": selling_price,
            "mrp": selling_price + 400,
            "gross_profit": gross_profit,
            "profit_margin_pct": round((gross_profit / selling_price) * 100, 1),
            "discount_pct": 50,
            "badge": "Save 50%"
        }

    gross_profit = pricing["gross_profit"]

    # Margin Score (Max 30)
    if gross_profit >= 500:
        margin_score = 30
    elif gross_profit >= 400:
        margin_score = 26
    elif gross_profit >= 300:
        margin_score = 21
    elif gross_profit >= 200:
        margin_score = 16
    else:
        margin_score = 10

    # 2. Competitor Scale Proof (Max 25)
    active_ads = meta_signals.get("estimated_active_ads", 1)
    if active_ads >= 8:
        scale_score = 25
    elif active_ads >= 4:
        scale_score = 21
    elif active_ads >= 2:
        scale_score = 16
    else:
        scale_score = 12

    # 3. Google Trends Momentum (Max 20)
    trend_val = trend_signals.get("trend_score", 75)
    trend_score_pts = min(20, round((trend_val / 100.0) * 20))

    # 4. COD & RTO Safety Score (Max 15)
    fragile_triggers = ["glass", "ceramic", "mirror", "fragile", "heavy", "porcelain"]
    safe_triggers = ["led", "silicone", "organizer", "dispenser", "abs", "plastic", "cutter", "peeler", "mat", "light", "bottle", "rack"]
    
    is_fragile = any(f in title_lower for f in fragile_triggers)
    is_safe = any(s in title_lower for s in safe_triggers)

    if is_fragile:
        rto_score = 8
        rto_verdict = "Medium Risk (Fragile Material - Pack Well)"
    elif is_safe:
        rto_score = 15
        rto_verdict = "Low RTO Risk (Durable, Lightweight Packaging)"
    else:
        rto_score = 12
        rto_verdict = "Standard COD Safety"

    # 5. Aesthetic & Reel Appeal (Max 10)
    visual_triggers = ["lamp", "light", "rgb", "crystal", "sunset", "glow", "aesthetic", "mini", "portable", "automatic", "360", "wireless", "touch", "sensor"]
    visual_matches = sum(1 for v in visual_triggers if v in title_lower)
    
    aesthetic_score = min(10, 6 + (visual_matches * 2))

    # Total Score Calculation
    total_score = min(99, margin_score + scale_score + trend_score_pts + rto_score + aesthetic_score)

    # Badges
    if total_score >= 88:
        badge_text = "🔥 SUPER WINNER"
        badge_color = "#10B981"  # Emerald
    elif total_score >= 78:
        badge_text = "⚡ SCALING FAST"
        badge_color = "#F59E0B"  # Amber
    elif total_score >= 70:
        badge_text = "💎 HIGH MARGIN GEM"
        badge_color = "#6366F1"  # Indigo
    else:
        badge_text = "🌱 PROMISING TEST"
        badge_color = "#64748B"  # Slate

    # Actionable Bullet Points
    bullets: List[str] = [
        f"💰 ₹{int(gross_profit)} Net Profit: High {pricing['profit_margin_pct']}% markup at ₹{pricing['selling_price']} retail (Cost: ₹{int(wholesale_price)}).",
        f"🎯 Ad Proof: {meta_signals.get('scale_verdict', 'Active')} with ~{active_ads} active competitor ads.",
        f"📈 Trend Demand: {trend_signals.get('trend_status', 'Rising')} in India ({niche} niche).",
        f"🛡️ Return Safety: {rto_verdict}."
    ]

    return {
        "total_score": total_score,
        "badge_text": badge_text,
        "badge_color": badge_color,
        "breakdown": {
            "margin_score": margin_score,
            "scale_score": scale_score,
            "trend_score": trend_score_pts,
            "rto_score": rto_score,
            "aesthetic_score": aesthetic_score
        },
        "pricing": pricing,
        "bullets": bullets,
        "rto_verdict": rto_verdict
    }
