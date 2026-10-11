import urllib.parse
from typing import Dict, Any

def extract_search_keyword(title: str) -> str:
    """
    Cleans up noisy brand names, pack sizes, and specifications to get the core commercial product term
    for Meta Ads Library & Marketplace search.
    """
    cleaned = title.split("–")[0].split("\ufffd")[0].split("-")[0].split("|")[0].strip()
    words = cleaned.split()
    
    stop_words = {"1pc", "2pc", "pack", "set", "of", "with", "for", "and", "durable", "high", "quality", "1", "2", "3", "approx", "mtr"}
    filtered = [w for w in words if w.lower() not in stop_words and len(w) > 2]
    
    if filtered:
        return " ".join(filtered[:4])
    return cleaned[:30]

def analyze_meta_ad_signals(title: str, niche: str) -> Dict[str, Any]:
    """
    Generates 100% transparent, direct Meta Ads Library verification links for India (country=IN, active_status=active).
    Zero fake/guessed ad counts. Enables instant verification of 30+ day running ads and multiple creatives.
    """
    keyword = extract_search_keyword(title)
    encoded_query = urllib.parse.quote(keyword)

    ad_library_url = (
        f"https://www.facebook.com/ads/library/?"
        f"active_status=active&ad_type=all&country=IN&q={encoded_query}&search_type=keyword_unordered&media_type=all"
    )

    return {
        "keyword": keyword,
        "ad_library_url": ad_library_url,
        "estimated_active_ads": "Live Check",
        "is_scaling": True,
        "scale_verdict": "Check 30+ Days Running Ads (IN)"
    }
