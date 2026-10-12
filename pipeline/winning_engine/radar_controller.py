import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR.parent.parent
sys.path.insert(0, str(CURRENT_DIR.parent))

from config import WINNING_DB_FILE, DATABASE_FILE, DATA_DIR, BASE_DIR as CONFIG_BASE_DIR
from classifier_pricing import ClassifierAndPricingEngine
from deodap_extractor import DeoDapExtractor

from winning_engine.data_models import now_iso, load_settings, get_product_manual_entry
from winning_engine.deodap_harvester import harvest_deodap_bestsellers
from winning_engine.meta_ad_spy import analyze_meta_ad_signals
from winning_engine.trend_checker import get_google_trends_analysis
from winning_engine.social_spy import analyze_social_velocity
from winning_engine.gemini_analyzer import analyze_with_gemini
from winning_engine.winning_scorer import compute_winning_score
from winning_engine.competitor_pricing import get_competitor_price_intelligence
from ugc_engine import UGCEngine


def _build_pipeline_steps_status(
    item: Dict[str, Any],
    trend_signals: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    meta_signals: Dict[str, Any],
    social_signals: Dict[str, Any],
    score_data: Dict[str, Any]
) -> List[Dict[str, str]]:
    """
    Research Pipeline Steps 1–8 status indicator (done / manual_needed / unavailable).
    """
    mkt = competitor_intel.get("marketplaces", {})
    any_mkt_done = any(
        mkt.get(k, {}).get("status") == "done"
        for k in ("amazon", "flipkart", "meesho")
    )
    sample_st = score_data.get("sample_tracking", {}).get("status", "shortlisted")
    has_test = score_data.get("test_results") is not None

    return [
        {
            "step": 1,
            "name": "Supplier Ingest (DeoDap)",
            "status": "done" if item.get("wholesale_price") else "unavailable",
            "method": item.get("method", "api"),
            "detail": f"₹{item.get('wholesale_price')} | Stock: {item.get('in_stock')}"
        },
        {
            "step": 2,
            "name": "Demand Check (Trends / Suggest / YT)",
            "status": trend_signals.get("pipeline_status", "manual_needed"),
            "method": "api",
            "detail": trend_signals.get("trend_label", "Data not available")
        },
        {
            "step": 3,
            "name": "Marketplace Check (Amazon / FK / Meesho)",
            "status": "done" if any_mkt_done else "manual_needed",
            "method": "scrape / manual_entry",
            "detail": competitor_intel.get("market_comparison_verdict", "Data not available")
        },
        {
            "step": 4,
            "name": "Ads Validation (Meta Ad Library)",
            "status": meta_signals.get("status", "manual_needed"),
            "method": "manual_entry",
            "detail": meta_signals.get("scale_verdict", "Ads not checked yet")
        },
        {
            "step": 5,
            "name": "Instagram Validation",
            "status": social_signals.get("status", "manual_needed"),
            "method": social_signals.get("method", "manual_entry"),
            "detail": social_signals.get("est_reels_views") or "Instagram not checked yet"
        },
        {
            "step": 6,
            "name": "Competitor / Price Comparison",
            "status": "done" if any_mkt_done else "manual_needed",
            "method": "scrape / manual_entry",
            "detail": f"Avg Market: {'₹' + str(int(competitor_intel['avg_market_price'])) if competitor_intel.get('avg_market_price') else 'Data not available'}"
        },
        {
            "step": 7,
            "name": "Sample Tracking",
            "status": "done" if sample_st != "shortlisted" else "manual_needed",
            "method": "manual_entry",
            "detail": f"Stage: {sample_st.replace('_', ' ').title()}"
        },
        {
            "step": 8,
            "name": "Store Test Results",
            "status": "done" if has_test else "manual_needed",
            "method": "manual_entry",
            "detail": f"Net Profit: ₹{score_data['test_results']['real_net_profit_total']}" if has_test else "No live test data entered yet"
        }
    ]


def enrich_winner_record(item: Dict[str, Any], catalog_pool: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Computes full transparent scoring, provenance, and pipeline status for a single catalog item."""
    handle = item.get("handle", "")
    title = item.get("title", "")
    niche = item.get("niche", "Home Decor")
    wholesale_price = float(item.get("wholesale_price") or item.get("wholesale_cost") or 0.0)

    meta_signals = analyze_meta_ad_signals(title, niche, handle=handle)
    trend_signals = get_google_trends_analysis(meta_signals["keyword"], niche, fetch_live=False)
    social_signals = analyze_social_velocity(meta_signals["keyword"], niche, handle=handle)

    gemini_signals = item.get("gemini")
    if not gemini_signals or not gemini_signals.get("gemini_powered"):
        gemini_signals = analyze_with_gemini(
            product_title=title,
            niche=niche,
            wholesale_price=wholesale_price,
            selling_price=int(item.get("selling_price") or 299),
            description=item.get("description", ""),
            handle=handle,
            fetch_live=False
        )

    score_data = compute_winning_score(
        product=item,
        meta_signals=meta_signals,
        trend_signals=trend_signals,
        social_signals=social_signals,
        gemini_signals=gemini_signals,
        catalog_pool=catalog_pool
    )

    zen_title = (
        ClassifierAndPricingEngine.generate_zenlora_title(title)
        if ClassifierAndPricingEngine
        else f"Zenlora™ {meta_signals['keyword'].title()}"
    )

    competitor_intel = get_competitor_price_intelligence(
        title=title,
        wholesale_price=wholesale_price,
        niche=niche,
        handle=handle,
        fetch_live=False
    )

    ugc_prompts = {}
    if item.get("storyboard_image_prompt"):
        ugc_prompts = {
            k: item[k]
            for k in ("storyboard_image_prompt", "scene_1_video_prompt", "scene_2_video_prompt", "scene_3_video_prompt", "voiceover_script")
            if k in item
        }

    pipeline_steps = _build_pipeline_steps_status(
        item, trend_signals, competitor_intel, meta_signals, social_signals, score_data
    )

    fetched_at = item.get("fetched_at") or now_iso()

    primary_img = item.get("image_url") or item.get("primary_image") or ""
    raw_imgs = item.get("images") or ([primary_img] if primary_img else [])

    return {
        "id": item.get("id"),
        "variant_id": item.get("variant_id"),
        "sku": item.get("sku"),
        "barcode": item.get("barcode"),
        "compare_at_price": item.get("compare_at_price"),
        "handle": handle,
        "title": title,
        "zenlora_title": zen_title,
        "niche": niche,
        "source": item.get("source", "DeoDap Shopify API"),
        "source_url": item.get("source_url") or item.get("deodap_url", ""),
        "fetched_at": fetched_at,
        "method": item.get("method", "api"),
        "in_stock": item.get("in_stock", True),
        "weight_grams": item.get("weight_grams"),
        "dimensions": item.get("dimensions"),
        "delivery_min_days": item.get("delivery_min_days"),
        "delivery_max_days": item.get("delivery_max_days"),
        "wholesale_price": wholesale_price,
        "selling_price": score_data["pricing"]["selling_price"],
        "mrp": score_data["pricing"]["mrp"],
        "gross_profit": score_data["pricing"]["gross_profit"],
        "profit_margin_pct": score_data["pricing"]["profit_margin_pct"],
        "discount_pct": score_data["pricing"]["discount_pct"],
        "winning_score": score_data["total_score"],
        "earned_points": score_data["earned_points"],
        "scored_weight_sum": score_data["scored_weight_sum"],
        "verified_score_pct": score_data["verified_score_pct"],
        "formula_explanation": score_data["formula_explanation"],
        "confidence": score_data["confidence"],
        "confidence_color": score_data["confidence_color"],
        "is_stale": score_data["is_stale"],
        "data_coverage": score_data["data_coverage"],
        "is_hard_failed": score_data["is_hard_failed"],
        "hard_fail_reasons": score_data["hard_fail_reasons"],
        "passed_criteria_count": score_data["passed_criteria_count"],
        "checklist": score_data["checklist"],
        "festival_mood": score_data["festival_mood"],
        "festival_cutoffs": score_data["festival_cutoffs"],
        "delivery_days_source": score_data["delivery_days_source"],
        "sample_tracking": score_data["sample_tracking"],
        "test_results": score_data["test_results"],
        "pipeline_steps": pipeline_steps,
        "badge_text": score_data["badge_text"],
        "badge_color": score_data["badge_color"],
        "bestseller_rank": item.get("bestseller_rank", 1),
        "meta_ads": meta_signals,
        "trends": trend_signals,
        "social": social_signals,
        "gemini": gemini_signals,
        "score_breakdown": score_data["breakdown"],
        "bullets": score_data["bullets"],
        "rto_verdict": score_data["rto_verdict"],
        "image_url": primary_img,
        "images": raw_imgs[:6],
        "deodap_url": item.get("deodap_url") or f"https://www.deodap.in/products/{handle}",
        "description": item.get("description", ""),
        "scanned_at": fetched_at,
        "competitor_pricing": competitor_intel,
        "suggested_price": competitor_intel.get("suggested_price", score_data["pricing"]["selling_price"]),
        "strategy_insight": competitor_intel.get("strategy_insight", ""),
        **ugc_prompts
    }


def scan_and_update_winners(
    limit_per_niche: int = 30,
    randomize: bool = True,
    batch_cursor: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Pulls fresh live DeoDap products across all 5 niches, evaluates all 10 criteria
    with transparent provenance metadata, filters out any hard-failed items, and persists the shortlist pool.
    """
    pool_limit = max(limit_per_niche, 30)
    print(f"[*] Starting Zenlora Winning Radar live scan (pool_limit={pool_limit}, rotate={randomize}, batch={batch_cursor})...")
    harvested_items = harvest_deodap_bestsellers(
        limit_per_niche=pool_limit,
        randomize=randomize,
        batch_cursor=batch_cursor
    )

    winners = [enrich_winner_record(item, catalog_pool=harvested_items) for item in harvested_items]
    winners = [w for w in winners if not w.get("is_hard_failed", False)]
    if not randomize:
        winners.sort(key=lambda x: (x.get("winning_score", 0), x.get("verified_score_pct", 0)), reverse=True)

    # Persist to both runtime WINNING_DB_FILE and repo winning_products.json
    repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"
    for target in (WINNING_DB_FILE, repo_file):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(winners, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Warning saving {target}: {e}")

    print(f"[+] Scan completed! {len(winners)} verified high-confidence products saved.")
    return winners


def get_winners(
    niche: Optional[str] = None,
    include_hard_failed: bool = False,
    refresh_dynamic: bool = True,
    batch_cursor: int = 0,
    per_niche_display: int = 12
) -> List[Dict[str, Any]]:
    """
    Loads winning products from storage, dynamically applying any updated manual entries
    or user settings, and rotates the displayed slice per niche when batch_cursor > 0.
    """
    winners = []
    repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"

    candidates = []
    if WINNING_DB_FILE.exists():
        candidates.append(WINNING_DB_FILE)
    if repo_file.exists() and repo_file != WINNING_DB_FILE:
        candidates.append(repo_file)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for src_file in candidates:
        try:
            with open(src_file, "r", encoding="utf-8") as f:
                winners = json.load(f)
            if winners:
                break
        except Exception:
            continue

    if refresh_dynamic and winners:
        winners = [enrich_winner_record(w, catalog_pool=winners) for w in winners]

    if not include_hard_failed:
        winners = [w for w in winners if not w.get("is_hard_failed", False)]

    # Group by niche to apply batch_cursor rotation and per_niche_display slicing
    if per_niche_display and per_niche_display > 0:
        niches_order = ["Home Decor", "Kitchen", "Gadgets", "Festive", "Gifts"]
        by_niche: Dict[str, List[Dict[str, Any]]] = {n: [] for n in niches_order}
        for w in winners:
            wn = w.get("niche", "Gadgets")
            if wn in by_niche:
                by_niche[wn].append(w)
            else:
                by_niche.setdefault(wn, []).append(w)

        sliced_all: List[Dict[str, Any]] = []
        b_idx = max(0, int(batch_cursor or 0))

        for n_name, n_items in by_niche.items():
            if not n_items:
                continue
            # Sort base niche pool deterministically by (not hard_failed, score, handle)
            n_items_sorted = sorted(
                n_items,
                key=lambda x: (not x.get("is_hard_failed", False), x.get("winning_score", 0), x.get("handle", "")),
                reverse=True
            )
            if b_idx > 0 and len(n_items_sorted) > 1:
                shift = (b_idx * 6) % len(n_items_sorted)
                rotated_niche = n_items_sorted[shift:] + n_items_sorted[:shift]
            else:
                rotated_niche = n_items_sorted
            sliced_all.extend(rotated_niche[:per_niche_display])

        # Interleave niches for 'All' tab when batch_cursor > 0 so top row immediately changes across all categories
        if not niche or str(niche).strip().lower() == "all":
            if b_idx == 0:
                sliced_all.sort(key=lambda x: (not x.get("is_hard_failed", False), x.get("winning_score", 0)), reverse=True)
            else:
                interleaved: List[Dict[str, Any]] = []
                niche_buckets = [
                    [x for x in sliced_all if x.get("niche") == n_key]
                    for n_key in niches_order
                ]
                # Rotate bucket order by batch_cursor too
                b_shift = b_idx % len(niche_buckets)
                niche_buckets = niche_buckets[b_shift:] + niche_buckets[:b_shift]
                for i in range(per_niche_display):
                    for bucket in niche_buckets:
                        if i < len(bucket):
                            interleaved.append(bucket[i])
                sliced_all = interleaved
            return sliced_all

        target_niche = str(niche).strip().lower()
        return [w for w in sliced_all if str(w.get("niche", "")).strip().lower() == target_niche]

    if niche and str(niche).strip().lower() != "all":
        target_niche = str(niche).strip().lower()
        return [w for w in winners if str(w.get("niche", "")).strip().lower() == target_niche]
    return winners


def import_to_studio(handle: str) -> Dict[str, Any]:
    """Imports a discovered winning product directly into the Zenlora Studio database."""
    normalized_handle = DeoDapExtractor.clean_handle(handle)
    all_winners = get_winners(include_hard_failed=True, refresh_dynamic=False, per_niche_display=0)
    target = next(
        (
            w for w in all_winners
            if str(w.get("handle") or "").lower() == normalized_handle.lower()
        ),
        None,
    )
    if not target:
        raise ValueError(f"Product handle '{handle}' not found in winning radar.")

    from pipeline_controller import ZenloraPipeline
    deodap_url = target.get("deodap_url") or f"https://www.deodap.in/products/{normalized_handle}"
    return ZenloraPipeline.process_url(deodap_url)
