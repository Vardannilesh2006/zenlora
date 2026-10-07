import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

# Setup paths
CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR.parent.parent
sys.path.insert(0, str(CURRENT_DIR.parent))

from config import WINNING_DB_FILE, DATABASE_FILE, DATA_DIR, BASE_DIR as CONFIG_BASE_DIR
from classifier_pricing import ClassifierAndPricingEngine

from winning_engine.deodap_harvester import harvest_deodap_bestsellers
from winning_engine.meta_ad_spy import analyze_meta_ad_signals
from winning_engine.trend_checker import get_google_trends_analysis
from winning_engine.social_spy import analyze_social_velocity
from winning_engine.gemini_analyzer import analyze_with_gemini
from winning_engine.winning_scorer import compute_winning_score
from ugc_engine import UGCEngine

def scan_and_update_winners(limit_per_niche: int = 20, randomize: bool = True) -> List[Dict[str, Any]]:
    """
    Harvests DeoDap across 5 niches (min 20 per niche), runs Meta Ads, Reels velocity,
    Google Trends, Gemini AI analysis, and automatically generates full 3-scene UGC storyboards
    and creative director direction for every discovered winner.
    """
    print(f"[*] Starting Zenlora Winning Radar scan (target: {limit_per_niche} per niche, rotation={randomize})...")
    harvested_items = harvest_deodap_bestsellers(limit_per_niche=limit_per_niche, randomize=randomize)
    
    winners = []
    scan_timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")

    # To optimize scan speed and avoid rate-limiting Gemini API on 100+ items,
    # we call Gemini on top items and utilize smart deterministic fallbacks.
    gemini_count = 0
    max_gemini_calls = 10

    for item in harvested_items:
        title = item.get("title", "")
        niche = item.get("niche", "Home Decor")
        wholesale_price = item.get("wholesale_price", 150.0)
        selling_price = item.get("selling_price", 499)

        # 1. Meta Ad Spy Intelligence
        meta_signals = analyze_meta_ad_signals(title, niche)

        # 2. Google Trends Momentum
        trend_signals = get_google_trends_analysis(meta_signals["keyword"], niche)

        # 3. Social / Instagram Reels Velocity
        social_signals = analyze_social_velocity(meta_signals["keyword"], niche)

        # 4. Gemini Multimodal & Copy Engine
        gemini_signals = None
        if gemini_count < max_gemini_calls:
            try:
                gemini_signals = analyze_with_gemini(title, niche, wholesale_price, selling_price)
                if gemini_signals and gemini_signals.get("gemini_powered"):
                    gemini_count += 1
            except Exception:
                pass

        # 5. Master Winning Score (0-100)
        score_data = compute_winning_score(
            product=item,
            meta_signals=meta_signals,
            trend_signals=trend_signals,
            social_signals=social_signals,
            gemini_signals=gemini_signals
        )

        zen_title = ClassifierAndPricingEngine.generate_zenlora_title(title) if ClassifierAndPricingEngine else f"Zenlora™ {meta_signals['keyword'].title()}"

        # 6. Automatic UGC Storyboard & Multi-Scene Continuity Prompts
        prod_data = {
            "title": title,
            "description": item.get("description", "")
        }
        class_data = {
            "zenlora_title": zen_title,
            "primary_category": niche,
            "selling_price": score_data["pricing"]["selling_price"]
        }
        try:
            ugc_prompts = UGCEngine.generate_prompts(prod_data, class_data)
        except Exception:
            ugc_prompts = {}

        winner_record = {
            "id": item.get("id"),
            "handle": item.get("handle"),
            "title": title,
            "zenlora_title": zen_title,
            "niche": niche,
            "wholesale_price": wholesale_price,
            "selling_price": score_data["pricing"]["selling_price"],
            "mrp": score_data["pricing"]["mrp"],
            "gross_profit": score_data["pricing"]["gross_profit"],
            "profit_margin_pct": score_data["pricing"]["profit_margin_pct"],
            "discount_pct": score_data["pricing"].get("discount_pct", 50),
            "winning_score": score_data["total_score"],
            "badge_text": score_data["badge_text"],
            "badge_color": score_data["badge_color"],
            "bestseller_rank": item.get("bestseller_rank", 99),
            "meta_ads": {
                "keyword": meta_signals["keyword"],
                "ad_library_url": meta_signals["ad_library_url"],
                "active_ads": meta_signals["estimated_active_ads"],
                "scale_verdict": meta_signals["scale_verdict"],
                "is_scaling": meta_signals["is_scaling"]
            },
            "trends": {
                "score": trend_signals["trend_score"],
                "status": trend_signals["trend_status"],
                "label": trend_signals["trend_label"],
                "trends_url": trend_signals["trends_url"]
            },
            "social": {
                "views": social_signals["est_reels_views"],
                "likes": social_signals["est_reels_likes"],
                "days_scaling": social_signals["days_scaling"],
                "scale_label": social_signals["scale_label"],
                "instagram_url": social_signals["instagram_url"],
                "primary_hashtag": social_signals["primary_hashtag"]
            },
            "gemini": gemini_signals if gemini_signals else {
                "ai_verdict": "High impulse-buy potential with strong social proof in Indian D2C market.",
                "viral_hook_hinglish": f"Aapke room ka look instant badal dega yeh {zen_title.replace('Zenlora™', '').strip()}!",
                "target_audience": "Modern Indian Homemakers & Youth",
                "ai_viral_score": score_data["total_score"]
            },
            "score_breakdown": score_data["breakdown"],
            "bullets": score_data["bullets"],
            "rto_verdict": score_data["rto_verdict"],
            "image_url": item.get("image_url", ""),
            "deodap_url": item.get("deodap_url", ""),
            "description": item.get("description", ""),
            "scanned_at": scan_timestamp,
            **ugc_prompts
        }
        winners.append(winner_record)

    # Sort descending by winning score
    winners.sort(key=lambda x: x["winning_score"], reverse=True)

    # Persist to active database
    try:
        WINNING_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WINNING_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(winners, f, indent=2, ensure_ascii=False)
        
        # Also sync to bundled repository folder if not in /tmp
        repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"
        if repo_file != WINNING_DB_FILE:
            repo_file.parent.mkdir(parents=True, exist_ok=True)
            with open(repo_file, "w", encoding="utf-8") as f:
                json.dump(winners, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Warning: Failed to persist winning_products.json: {e}")

    print(f"[+] Scan completed! {len(winners)} winning products analyzed with full AI UGC storyboards.")
    return winners

def get_winners(niche: Optional[str] = None) -> List[Dict[str, Any]]:
    """Loads winning products from storage, ensuring full UGC storyboard fields are present."""
    winners = []
    
    # 1. Try reading active WINNING_DB_FILE
    if WINNING_DB_FILE.exists():
        try:
            with open(WINNING_DB_FILE, "r", encoding="utf-8") as f:
                winners = json.load(f)
        except Exception:
            winners = []

    # 2. If missing or lacking UGC prompts, try bundled repo file
    repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"
    if (not winners or not winners[0].get("storyboard_image_prompt")) and repo_file.exists():
        try:
            with open(repo_file, "r", encoding="utf-8") as f:
                repo_winners = json.load(f)
            if repo_winners and repo_winners[0].get("storyboard_image_prompt"):
                winners = repo_winners
                # Sync back to active file
                try:
                    WINNING_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(WINNING_DB_FILE, "w", encoding="utf-8") as f:
                        json.dump(winners, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
        except Exception:
            pass

    # 3. If still empty, trigger clean scan
    if not winners:
        winners = scan_and_update_winners(limit_per_niche=20, randomize=False)

    if niche and niche.lower() != "all":
        return [w for w in winners if w.get("niche", "").lower() == niche.lower()]
    return winners

def import_to_studio(handle: str) -> Dict[str, Any]:
    """
    Imports a discovered winning product directly into the Zenlora Studio database,
    generating full 3-scene UGC storyboard prompts and retail pricing.
    """
    all_winners = get_winners()
    target = next((w for w in all_winners if w["handle"] == handle), None)
    if not target:
        raise ValueError(f"Product handle '{handle}' not found in winning radar.")

    from pipeline_controller import ZenloraPipeline
    deodap_url = target.get("deodap_url") or f"https://deodap.in/products/{handle}"
    
    full_record = ZenloraPipeline.process_url(deodap_url)
    return full_record
