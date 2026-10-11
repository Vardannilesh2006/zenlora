"""
Meta Ad Library Validation Module (Research Pipeline Step 4):
The official Meta Ad Library API does not provide commercial ad data for India,
and scraping it violates Meta's terms.
Therefore, this module NEVER fabricates or auto-scrapes ad counts.
It generates a ready-made Ad Library search link (country=IN, keyword) and reads/stores
user-verified manual entries (method='manual_entry').
Shows 'Ads not checked yet' (null) until filled by the user.
"""
import urllib.parse
from typing import Dict, Any, Optional
from winning_engine.data_models import (
    get_product_manual_entry,
    is_timestamp_stale,
    load_settings,
)


def extract_search_keyword(title: str) -> str:
    """Extracts clean 3-4 word commercial product search query from supplier title."""
    cleaned = title.split("–")[0].split("\ufffd")[0].split("-")[0].split("|")[0].strip()
    words = cleaned.split()
    stop_words = {
        "1pc", "2pc", "pack", "set", "of", "with", "for", "and",
        "durable", "high", "quality", "1", "2", "3", "approx", "mtr", "pcs"
    }
    filtered = [w for w in words if w.lower() not in stop_words and len(w) > 2]
    if filtered:
        return " ".join(filtered[:4])
    return cleaned[:30]


def analyze_meta_ad_signals(title: str, niche: str, handle: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns Meta Ad Library search URL and user's manual entry (if recorded).
    Never invents or estimates active ad counts.
    """
    keyword = extract_search_keyword(title)
    encoded_query = urllib.parse.quote(keyword)
    ad_library_url = (
        f"https://www.facebook.com/ads/library/?"
        f"active_status=active&ad_type=all&country=IN&q={encoded_query}&search_type=keyword_unordered&media_type=all"
    )

    settings = load_settings()
    stale_days = int(settings.get("general", {}).get("stale_days_limit", 7))

    manual_all = get_product_manual_entry(handle) if handle else {}
    manual_ads = manual_all.get("meta_ads")

    if manual_ads and manual_ads.get("active_ads_count") is not None:
        fetched_at = manual_ads.get("fetched_at") or manual_ads.get("date_checked")
        stale = is_timestamp_stale(fetched_at, stale_days)
        active_ads = int(manual_ads["active_ads_count"])
        longest_days = int(manual_ads.get("longest_running_days") or 0)
        distinct_creatives = int(manual_ads.get("distinct_creatives_count") or 0)
        advertisers = int(manual_ads.get("advertisers_count") or 0)
        notes = manual_ads.get("notes") or ""

        return {
            "keyword": keyword,
            "ad_library_url": ad_library_url,
            "status": "done",
            "active_ads_count": active_ads,
            "longest_running_days": longest_days,
            "distinct_creatives_count": distinct_creatives,
            "advertisers_count": advertisers,
            "notes": notes,
            "date_checked": manual_ads.get("date_checked") or fetched_at,
            "estimated_active_ads": f"{active_ads} Active Ads ({longest_days}d longest)",
            "is_scaling": longest_days >= 30 or distinct_creatives >= 5,
            "scale_verdict": f"Verified: {active_ads} ads, {longest_days}d longest, {distinct_creatives} creatives",
            "source": "Meta Ad Library (Manual Entry)",
            "source_url": ad_library_url,
            "fetched_at": fetched_at,
            "method": "manual_entry",
            "is_stale": stale,
            "null_reason": None
        }

    # Not checked yet — return null (Rule #3 & Research Pipeline #4)
    return {
        "keyword": keyword,
        "ad_library_url": ad_library_url,
        "status": "manual_needed",
        "active_ads_count": None,
        "longest_running_days": None,
        "distinct_creatives_count": None,
        "advertisers_count": None,
        "notes": None,
        "date_checked": None,
        "estimated_active_ads": None,
        "is_scaling": None,
        "scale_verdict": "Ads not checked yet (Manual entry needed)",
        "source": "Meta Ad Library (India)",
        "source_url": ad_library_url,
        "fetched_at": None,
        "method": "manual_entry",
        "is_stale": False,
        "null_reason": "Ads not checked yet — open Meta Ad Library link and fill Manual Entry form"
    }
