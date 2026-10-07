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
from ugc_engine import UGCEngine

from winning_engine.deodap_harvester import harvest_deodap_bestsellers
from winning_engine.meta_ad_spy import analyze_meta_ad_signals
from winning_engine.trend_checker import get_google_trends_analysis
from winning_engine.winning_scorer import compute_winning_score

def scan_and_update_winners(limit_per_niche: int = 8) -> List[Dict[str, Any]]:
    """
    Harvests DeoDap across 5 niches, runs Meta Ads & Google Trends intelligence,
    scores every product, and persists to winning_products.json.
    """
    print(f"[*] Starting Zenlora Winning Radar scan (limit: {limit_per_niche} per niche)...")
    harvested_items = harvest_deodap_bestsellers(limit_per_niche=limit_per_niche)
    
    winners = []
    scan_timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")

    for item in harvested_items:
        title = item.get("title", "")
        niche = item.get("niche", "Home Decor")
        wholesale_price = item.get("wholesale_price", 150.0)

        # 1. Meta Ad Spy Intelligence
        meta_signals = analyze_meta_ad_signals(title, niche)

        # 2. Google Trends Momentum
        trend_signals = get_google_trends_analysis(meta_signals["keyword"], niche)

        # 3. Master Score & Reasoning
        score_data = compute_winning_score(item, meta_signals, trend_signals)

        zen_title = ClassifierAndPricingEngine.generate_zenlora_title(title) if ClassifierAndPricingEngine else f"Zenlora™ {meta_signals['keyword'].title()}"

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
            "score_breakdown": score_data["breakdown"],
            "bullets": score_data["bullets"],
            "rto_verdict": score_data["rto_verdict"],
            "image_url": item.get("image_url", ""),
            "deodap_url": item.get("deodap_url", ""),
            "description": item.get("description", ""),
            "scanned_at": scan_timestamp
        }
        winners.append(winner_record)

    # Sort descending by winning score
    winners.sort(key=lambda x: x["winning_score"], reverse=True)

    # Save to active database
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

    print(f"[+] Scan completed! {len(winners)} winning products analyzed.")
    return winners

def get_winners(niche: Optional[str] = None) -> List[Dict[str, Any]]:
    """Loads winning products from storage, triggering a scan if missing."""
    winners = []
    if WINNING_DB_FILE.exists():
        try:
            with open(WINNING_DB_FILE, "r", encoding="utf-8") as f:
                winners = json.load(f)
        except Exception:
            winners = []

    # Fallback to repo data
    if not winners:
        repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"
        if repo_file.exists():
            try:
                with open(repo_file, "r", encoding="utf-8") as f:
                    winners = json.load(f)
            except Exception:
                winners = []

    # If still empty, scan immediately
    if not winners:
        winners = scan_and_update_winners(limit_per_niche=6)

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
