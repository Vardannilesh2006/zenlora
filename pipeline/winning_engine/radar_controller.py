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
from winning_engine.deodap_harvester import (
    harvest_deodap_bestsellers,
    classify_niche,
    is_junk_or_mismatched_product,
    get_concept_stem,
)
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
    raw_niche = item.get("niche", "Home Decor")
    verified_niche = classify_niche(title, preferred_niche=raw_niche)
    niche = verified_niche or raw_niche
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

    item_with_niche = {**item, "niche": niche}
    score_data = compute_winning_score(
        product=item_with_niche,
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
        item_with_niche, trend_signals, competitor_intel, meta_signals, social_signals, score_data
    )

    fetched_at = item.get("fetched_at") or now_iso()

    primary_img = item.get("image_url") or item.get("primary_image") or ""
    raw_imgs = item.get("images") or ([primary_img] if primary_img else [])

    from winning_engine.smartbiz_exporter import get_product_smartbiz_preset_summary
    smartbiz_preset = get_product_smartbiz_preset_summary({
        **item_with_niche,
        "wholesale_price": wholesale_price,
        "selling_price": score_data["pricing"]["selling_price"],
        "images": raw_imgs[:6],
        "image_url": primary_img,
    })

    is_hard_failed = score_data["is_hard_failed"]
    hard_fail_reasons = list(score_data["hard_fail_reasons"])
    if verified_niche is None or is_junk_or_mismatched_product(title):
        is_hard_failed = True
        hard_fail_reasons.append("Category Mismatch / Off-Niche Product")

    return {
        "id": item.get("id"),
        "variant_id": item.get("variant_id"),
        "sku": item.get("sku"),
        "barcode": item.get("barcode"),
        "compare_at_price": score_data["pricing"]["mrp"],
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
        "smartbiz_preset": smartbiz_preset,
        "winning_score": score_data["total_score"],
        "earned_points": score_data["earned_points"],
        "scored_weight_sum": score_data["scored_weight_sum"],
        "verified_score_pct": score_data["verified_score_pct"],
        "formula_explanation": score_data["formula_explanation"],
        "confidence": score_data["confidence"],
        "confidence_color": score_data["confidence_color"],
        "is_stale": score_data["is_stale"],
        "data_coverage": score_data["data_coverage"],
        "is_hard_failed": is_hard_failed,
        "hard_fail_reasons": hard_fail_reasons,
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
        "images": raw_imgs,
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
    batch_cursor: Optional[int] = None,
    extra_excluded_keys: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Pulls fresh live DeoDap products across all 5 niches, enforces the 4-Key Zero-Repeat
    Export Vault (server ledger + browser localStorage keys), evaluates all 10 criteria
    with transparent provenance metadata, filters out hard-failed or off-niche items, and merges
    newly scanned unexported winners with the existing unexported pool.
    """
    from winning_engine.export_ledger import (
        build_exclusion_sets,
        extract_product_fingerprints,
        is_product_already_exported,
        record_exported_products,
    )

    if extra_excluded_keys:
        record_exported_products([], source_label="browser_scan_sync", extra_client_keys=extra_excluded_keys)

    excl_sets = build_exclusion_sets(extra_excluded_keys)

    # Load existing unexported pool so scanning expands/rotates the pool instead of shrinking it
    repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"
    existing_pool: List[Dict[str, Any]] = []
    for src_file in (WINNING_DB_FILE, repo_file):
        if src_file.exists():
            try:
                with open(src_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list) and len(loaded) > len(existing_pool):
                    existing_pool = loaded
            except Exception:
                continue

    pool_limit = max(limit_per_niche, 30)
    print(f"[*] Starting Zenlora Winning Radar live scan (pool_limit={pool_limit}, rotate={randomize}, batch={batch_cursor})...")
    harvested_items = harvest_deodap_bestsellers(
        limit_per_niche=pool_limit,
        randomize=randomize,
        batch_cursor=batch_cursor,
        extra_excluded_keys=extra_excluded_keys,
    )

    newly_scanned = [enrich_winner_record(item, catalog_pool=harvested_items) for item in harvested_items]
    newly_scanned = [
        w for w in newly_scanned
        if not w.get("is_hard_failed", False)
        and w.get("confidence") != "Low"
        and not is_product_already_exported(w, excl_sets)
    ]
    if not randomize:
        newly_scanned.sort(key=lambda x: (x.get("confidence") == "High", x.get("winning_score", 0), x.get("verified_score_pct", 0)), reverse=True)

    # Merge newly_scanned at the front + existing items, deduplicating by all 4 keys
    seen_skus = set(excl_sets[0])
    seen_handles = set(excl_sets[1])
    seen_vids = set(excl_sets[2])
    seen_tfps = set(excl_sets[3])
    merged_winners: List[Dict[str, Any]] = []

    master_skus = set()
    master_handles = set()
    master_vids = set()
    master_tfps = set()
    master_pool: List[Dict[str, Any]] = []

    for candidate in newly_scanned + existing_pool:
        if candidate.get("is_hard_failed", False):
            continue
        verified_niche = classify_niche(candidate.get("title", ""), preferred_niche=candidate.get("niche"))
        if not verified_niche:
            continue
        candidate["niche"] = verified_niche
        if candidate.get("confidence") == "Low":
            continue
        fp = extract_product_fingerprints(candidate)

        if not is_product_already_exported(candidate, (master_skus, master_handles, master_vids, master_tfps)):
            if fp["sku"]:
                master_skus.add(fp["sku"])
            if fp["handle"]:
                master_handles.add(fp["handle"])
            if fp["variant_id"]:
                master_vids.add(fp["variant_id"])
            if fp["title_fp"]:
                master_tfps.add(fp["title_fp"])
            master_pool.append(candidate)

        if is_product_already_exported(candidate, (seen_skus, seen_handles, seen_vids, seen_tfps)):
            continue
        if fp["sku"]:
            seen_skus.add(fp["sku"])
        if fp["handle"]:
            seen_handles.add(fp["handle"])
        if fp["variant_id"]:
            seen_vids.add(fp["variant_id"])
        if fp["title_fp"]:
            seen_tfps.add(fp["title_fp"])
        merged_winners.append(candidate)

    # Persist full master pool to both runtime WINNING_DB_FILE and repo winning_products.json so categories never shrink
    for target in (WINNING_DB_FILE, repo_file):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(master_pool, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Warning saving {target}: {e}")

    print(
        f"[+] Scan completed! {len(newly_scanned)} fresh batch items + "
        f"{len(merged_winners)} total verified unexported products in pool."
    )
    return merged_winners


def auto_refill_unexported_winners(
    existing_winners: List[Dict[str, Any]],
    exclusion_sets,
    min_needed_total: int = 130,
) -> List[Dict[str, Any]]:
    """
    If the number of unexported winners falls below `min_needed_total`, automatically crawls
    the next unseen pages of DeoDap's live Shopify catalog, enriches & scores the new items,
    persists them to storage, and returns the expanded pool.
    """
    from winning_engine.deodap_harvester import harvest_fresh_unexported_deodap_items
    from winning_engine.export_ledger import (
        extract_product_fingerprints,
        load_export_ledger,
        save_export_ledger,
    )

    ledger = load_export_ledger()
    start_pg = int(ledger.get("last_harvested_deodap_page") or 3) + 1

    # Combine existing pool fingerprints into exclusion sets so we don't re-harvest items already in winning_products.json
    skus, handles, variant_ids, title_fps = (
        set(exclusion_sets[0]),
        set(exclusion_sets[1]),
        set(exclusion_sets[2]),
        set(exclusion_sets[3]),
    )
    for w in existing_winners:
        fp = extract_product_fingerprints(w)
        if fp["sku"]:
            skus.add(fp["sku"])
        if fp["handle"]:
            handles.add(fp["handle"])
        if fp["variant_id"]:
            variant_ids.add(fp["variant_id"])
        if fp["title_fp"]:
            title_fps.add(fp["title_fp"])

    raw_new_items, next_pg = harvest_fresh_unexported_deodap_items(
        start_page=start_pg,
        max_pages=2,
        exclusion_sets=(skus, handles, variant_ids, title_fps),
    )

    ledger["last_harvested_deodap_page"] = next_pg - 1
    save_export_ledger(ledger)

    if not raw_new_items:
        return existing_winners

    combined_pool = existing_winners + raw_new_items
    newly_enriched: List[Dict[str, Any]] = []
    for item in raw_new_items:
        enriched = enrich_winner_record(item, catalog_pool=combined_pool)
        if not enriched.get("is_hard_failed", False) and enriched.get("confidence") != "Low":
            newly_enriched.append(enriched)

    if newly_enriched:
        updated_all = existing_winners + newly_enriched
        repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"
        for target in (WINNING_DB_FILE, repo_file):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(updated_all, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        return updated_all

    return existing_winners


_ENRICHED_WINNERS_CACHE: Dict[str, Any] = {
    "sig": None,
    "raw_items": [],
    "enriched_items": [],
}


def normalize_niche_param(niche: Optional[str]) -> str:
    """Normalizes category query parameters (including partial/unencoded '&' URLs) to canonical niche names."""
    if not niche:
        return "All"
    raw = str(niche).strip()
    low = raw.lower()
    if low in ("all", ""):
        return "All"
    if low in (
        "under 199",
        "under 199 collection",
        "under 199-299",
        "under_199",
        "under_199_collection",
        "under_199-299",
        "under 199_299",
        "under_50",
        "under 50",
        "under50",
        "199-299",
        "199_299",
        "199 to 299",
    ):
        return "Under 199 Collection"
    if low in (
        "health",
        "health & beauty",
        "health and beauty",
        "health & beauty accessories",
        "health and beauty accessories",
        "beauty",
        "beauty accessories",
    ) or low.startswith("health"):
        return "Health & Beauty"
    if low in ("festive", "festive & lights", "festive and lights") or low.startswith("festive"):
        return "Festive"
    if low in ("gifts", "gifts & hampers", "gifts and hampers") or low.startswith("gift"):
        return "Gifts"
    if low in ("gadgets", "smart gadgets"):
        return "Gadgets"
    if low in ("home decor", "home_decor"):
        return "Home Decor"
    if low in ("kitchen", "kitchen & dining", "kitchen and dining"):
        return "Kitchen"
    return raw


def matches_niche(item_niche: str, query_niche: str) -> bool:
    """Robust bidirectional matcher for canonical Zenlora / SmartBiz niche categories."""
    item_n = str(item_niche or "").strip().lower()
    q_n = str(query_niche or "").strip().lower()
    if not q_n or q_n == "all":
        return True
    if item_n == q_n:
        return True
    if q_n in ("health & beauty", "health & beauty accessories", "health and beauty", "beauty", "health"):
        return item_n in ("health & beauty", "health & beauty accessories", "health and beauty", "beauty", "health")
    if q_n in ("festive", "festive & lights", "festive and lights"):
        return item_n in ("festive", "festive & lights", "festive and lights")
    if q_n in ("gadgets", "smart gadgets"):
        return item_n in ("gadgets", "smart gadgets")
    if q_n in ("kitchen", "kitchen & dining"):
        return item_n in ("kitchen", "kitchen & dining")
    if q_n in ("gifts", "gifts & hampers"):
        return item_n in ("gifts", "gifts & hampers")
    if q_n in ("home decor", "home_decor"):
        return item_n in ("home decor", "home_decor")
    if q_n in ("under 199 collection", "under 199", "under 199-299", "199-299", "under_50"):
        return item_n in ("under 199 collection", "under 199", "under 199-299", "199-299", "under_50")
    return False


def get_winners(
    niche: Optional[str] = None,
    include_hard_failed: bool = False,
    refresh_dynamic: bool = True,
    batch_cursor: int = 0,
    per_niche_display: int = 24,
    exclude_exported: bool = True,
    extra_excluded_keys: Optional[List[str]] = None,
    auto_refill: bool = False,
) -> List[Dict[str, Any]]:
    """
    Loads winning products from storage, filters out any product already in the 4-Key Zero-Repeat Export Vault
    when `exclude_exported=True`, enforces strict category purity + High/Medium confidence,
    and rotates the displayed slice per niche when batch_cursor > 0.
    """
    from winning_engine.export_ledger import (
        build_exclusion_sets,
        extract_product_fingerprints,
        is_product_already_exported,
    )

    niche = normalize_niche_param(niche)
    repo_file = CONFIG_BASE_DIR / "data" / "winning_products.json"

    candidates = []
    if WINNING_DB_FILE.exists():
        candidates.append(WINNING_DB_FILE)
    if repo_file.exists() and repo_file != WINNING_DB_FILE:
        candidates.append(repo_file)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    file_sig_parts = []
    for p in candidates:
        try:
            st = p.stat()
            file_sig_parts.append((str(p), st.st_mtime_ns, st.st_size))
        except Exception:
            pass
    settings_sig = json.dumps(load_settings(), sort_keys=True)
    cache_sig = (tuple(file_sig_parts), settings_sig)

    if _ENRICHED_WINNERS_CACHE.get("sig") == cache_sig and _ENRICHED_WINNERS_CACHE.get("raw_items"):
        if refresh_dynamic and _ENRICHED_WINNERS_CACHE.get("enriched_items"):
            winners = [dict(w) for w in _ENRICHED_WINNERS_CACHE["enriched_items"]]
        else:
            winners = [dict(w) for w in _ENRICHED_WINNERS_CACHE["raw_items"]]
    else:
        merged_by_handle: List[Dict[str, Any]] = []
        seen_loaded_handles = set()
        for src_file in candidates:
            try:
                with open(src_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    for item in loaded:
                        h = str(item.get("handle") or "").strip().lower()
                        if h and h not in seen_loaded_handles:
                            seen_loaded_handles.add(h)
                            merged_by_handle.append(item)
            except Exception:
                continue

        winners = merged_by_handle
        _ENRICHED_WINNERS_CACHE["sig"] = cache_sig
        _ENRICHED_WINNERS_CACHE["raw_items"] = [dict(w) for w in winners]
        if refresh_dynamic and winners:
            enriched = [enrich_winner_record(w, catalog_pool=winners) for w in winners]
            _ENRICHED_WINNERS_CACHE["enriched_items"] = [dict(w) for w in enriched]
            winners = enriched
        else:
            _ENRICHED_WINNERS_CACHE["enriched_items"] = []

    if refresh_dynamic and winners and not _ENRICHED_WINNERS_CACHE.get("enriched_items"):
        winners = [enrich_winner_record(w, catalog_pool=winners) for w in winners]
        _ENRICHED_WINNERS_CACHE["enriched_items"] = [dict(w) for w in winners]

    if not include_hard_failed:
        winners = [
            w for w in winners
            if not w.get("is_hard_failed", False)
            and w.get("confidence") != "Low"
            and classify_niche(w.get("title", ""), preferred_niche=w.get("niche")) is not None
        ]

    all_valid_winners = list(winners)

    if exclude_exported:
        excl_sets = build_exclusion_sets(extra_excluded_keys)
        unexported = [w for w in winners if not is_product_already_exported(w, excl_sets)]

        # Auto-refill from deeper DeoDap pages if unexported pool is running low
        target_min = max(per_niche_display * 5 if per_niche_display else 60, 65)
        if auto_refill and len(unexported) < target_min:
            winners = auto_refill_unexported_winners(winners, excl_sets, min_needed_total=target_min)
            all_valid_winners = list(winners)
            unexported = [w for w in winners if not is_product_already_exported(w, excl_sets)]

        # Also deduplicate by 4-key fingerprint within the active candidate list so two SKUs with identical titles never appear together
        deduped: List[Dict[str, Any]] = []
        seen_skus = set()
        seen_handles = set()
        seen_title_fps = set()
        for w in unexported:
            fp = extract_product_fingerprints(w)
            if fp["sku"] and fp["sku"] in seen_skus:
                continue
            if fp["handle"] and fp["handle"] in seen_handles:
                continue
            if fp["title_fp"] and len(fp["title_fp"]) >= 5 and fp["title_fp"] in seen_title_fps:
                continue
            if fp["sku"]:
                seen_skus.add(fp["sku"])
            if fp["handle"]:
                seen_handles.add(fp["handle"])
            if fp["title_fp"]:
                seen_title_fps.add(fp["title_fp"])
            deduped.append(w)
        winners = deduped

    # Dedicated "Under 199 Collection" Page logic (DeoDap cost <= 50, selling price 179..185)
    if niche == "Under 199 Collection":
        def _is_under_199(item_obj: Dict[str, Any]) -> bool:
            cost = float(item_obj.get("wholesale_price") or 0.0)
            return 0 < cost <= 50.0

        pool_under = [w for w in winners if _is_under_199(w)]
        if per_niche_display and len(pool_under) < per_niche_display:
            existing_h = {str(x.get("handle") or "").lower() for x in pool_under}
            for fb in all_valid_winners:
                if _is_under_199(fb) and str(fb.get("handle") or "").lower() not in existing_h:
                    pool_under.append(fb)
                    existing_h.add(str(fb.get("handle") or "").lower())
                    if len(pool_under) >= per_niche_display * 2:
                        break

        pool_sorted = sorted(
            pool_under,
            key=lambda x: (
                not x.get("is_hard_failed", False),
                x.get("confidence") == "High",
                x.get("winning_score", 0),
                x.get("verified_score_pct", 0),
                x.get("handle", ""),
            ),
            reverse=True,
        )
        if not per_niche_display or per_niche_display <= 0:
            return pool_sorted

        b_idx = max(0, int(batch_cursor or 0))
        if b_idx > 0 and len(pool_sorted) > 1:
            shift = (b_idx * 6) % len(pool_sorted)
            rotated = pool_sorted[shift:] + pool_sorted[:shift]
        else:
            rotated = pool_sorted

        diverse_under: List[Dict[str, Any]] = []
        stem_counts_under: Dict[str, int] = {}
        overflow_under: List[Dict[str, Any]] = []
        for item in rotated:
            stem = get_concept_stem(item.get("title", ""))
            if stem_counts_under.get(stem, 0) < 2:
                stem_counts_under[stem] = stem_counts_under.get(stem, 0) + 1
                diverse_under.append(item)
            else:
                overflow_under.append(item)
            if len(diverse_under) >= per_niche_display:
                break
        if len(diverse_under) < per_niche_display:
            diverse_under.extend(overflow_under[: per_niche_display - len(diverse_under)])

        result_under = []
        for item in diverse_under[:per_niche_display]:
            item_copy = dict(item)
            preset = dict(item_copy.get("smartbiz_preset") or {})
            preset["product_category"] = "Under 199 Collection"
            item_copy["smartbiz_preset"] = preset
            result_under.append(item_copy)
        return result_under

    # Group by niche to apply batch_cursor rotation and per_niche_display slicing
    if per_niche_display and per_niche_display > 0:
        niches_order = ["Home Decor", "Kitchen", "Gadgets", "Festive", "Gifts", "Health & Beauty Accessories"]
        by_niche: Dict[str, List[Dict[str, Any]]] = {n: [] for n in niches_order}
        for w in winners:
            wn = w.get("niche", "Gadgets")
            matched = False
            for target_n in niches_order:
                if matches_niche(wn, target_n):
                    by_niche[target_n].append(w)
                    matched = True
                    break
            if not matched:
                by_niche.setdefault(wn, []).append(w)

        # Guarantee every category (including Festive & Lights) always has at least per_niche_display (24) items
        for n_name in niches_order:
            if len(by_niche.get(n_name, [])) < per_niche_display:
                existing_n_handles = {str(x.get("handle") or "").lower() for x in by_niche.get(n_name, [])}
                existing_n_skus = {str(x.get("sku") or "").lower() for x in by_niche.get(n_name, []) if x.get("sku")}
                fallback_pool = [
                    w for w in all_valid_winners
                    if matches_niche(w.get("niche", ""), n_name)
                    and str(w.get("handle") or "").lower() not in existing_n_handles
                    and (not w.get("sku") or str(w.get("sku") or "").lower() not in existing_n_skus)
                ]
                for fb_item in fallback_pool:
                    by_niche.setdefault(n_name, []).append(fb_item)
                    existing_n_handles.add(str(fb_item.get("handle") or "").lower())
                    if fb_item.get("sku"):
                        existing_n_skus.add(str(fb_item.get("sku") or "").lower())
                    if len(by_niche[n_name]) >= per_niche_display * 2:
                        break

        sliced_all: List[Dict[str, Any]] = []
        b_idx = max(0, int(batch_cursor or 0))

        for n_name, n_items in by_niche.items():
            if not n_items:
                continue
            # Sort base niche pool deterministically by (High confidence, not hard_failed, score, handle)
            n_items_sorted = sorted(
                n_items,
                key=lambda x: (
                    not x.get("is_hard_failed", False),
                    x.get("confidence") == "High",
                    x.get("winning_score", 0),
                    x.get("verified_score_pct", 0),
                    x.get("handle", ""),
                ),
                reverse=True
            )
            if b_idx > 0 and len(n_items_sorted) > 1:
                shift = (b_idx * 6) % len(n_items_sorted)
                rotated_niche = n_items_sorted[shift:] + n_items_sorted[:shift]
            else:
                rotated_niche = n_items_sorted

            # Enforce concept-stem diversity within the displayed slice (max 2 per concept stem first pass)
            diverse_slice: List[Dict[str, Any]] = []
            stem_counts: Dict[str, int] = {}
            overflow_slice: List[Dict[str, Any]] = []
            for item in rotated_niche:
                stem = get_concept_stem(item.get("title", ""))
                if stem_counts.get(stem, 0) < 2:
                    stem_counts[stem] = stem_counts.get(stem, 0) + 1
                    diverse_slice.append(item)
                else:
                    overflow_slice.append(item)
                if len(diverse_slice) >= per_niche_display:
                    break
            if len(diverse_slice) < per_niche_display:
                diverse_slice.extend(overflow_slice[: per_niche_display - len(diverse_slice)])

            sliced_all.extend(diverse_slice[:per_niche_display])

        # Interleave niches for 'All' tab when batch_cursor > 0 so top row immediately changes across all categories
        if not niche or str(niche).strip().lower() == "all":
            if b_idx == 0:
                sliced_all.sort(
                    key=lambda x: (
                        not x.get("is_hard_failed", False),
                        x.get("confidence") == "High",
                        x.get("winning_score", 0),
                    ),
                    reverse=True,
                )
            else:
                interleaved: List[Dict[str, Any]] = []
                niche_buckets = [
                    [x for x in sliced_all if matches_niche(x.get("niche", ""), n_key)]
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
        return [w for w in sliced_all if matches_niche(w.get("niche", ""), target_niche)]

    if niche and str(niche).strip().lower() != "all":
        target_niche = str(niche).strip().lower()
        return [w for w in winners if matches_niche(w.get("niche", ""), target_niche)]
    return winners


def import_to_studio(handle: str) -> Dict[str, Any]:
    """Imports a discovered winning product directly into the Zenlora Studio database."""
    normalized_handle = DeoDapExtractor.clean_handle(handle)
    all_winners = get_winners(include_hard_failed=True, refresh_dynamic=False, per_niche_display=0, exclude_exported=False)
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

