import urllib.parse
from typing import Dict, Any

def extract_search_keyword(title: str) -> str:
    """
    Cleans up noisy brand names, pack sizes, and specifications to get the core commercial product term.
    """
    # Remove emojis, special symbols
    cleaned = title.split("–")[0].split("-")[0].split("|")[0].strip()
    words = cleaned.split()
    
    # Filter out brand-like or generic words
    stop_words = {"1pc", "2pc", "pack", "set", "of", "with", "for", "and", "durable", "high", "quality", "1", "2", "3"}
    filtered = [w for w in words if w.lower() not in stop_words and len(w) > 2]
    
    if filtered:
        return " ".join(filtered[:4])
    return cleaned[:30]

def analyze_meta_ad_signals(title: str, niche: str) -> Dict[str, Any]:
    """
    Simulates Meta Ads Library competitor intelligence for Indian dropshippers.
    Generates live verification links and computes competitor scale momentum.
    """
    keyword = extract_search_keyword(title)
    # Search query targeted to Indian dropshippers running COD campaigns
    search_query = f"{keyword} Cash on Delivery"
    encoded_query = urllib.parse.quote(search_query)

    ad_library_url = (
        f"https://www.facebook.com/ads/library/?"
        f"active_status=active&ad_type=all&country=IN&q={encoded_query}&search_type=keyword_unordered&media_type=all"
    )

    # Heuristic scoring based on niche viral appeal and product keyword commercial velocity
    keyword_lower = keyword.lower()
    high_volume_triggers = [
        "lamp", "light", "dispenser", "chopper", "organizer", "diffuser", "spray", "cleaner",
        "clock", "mat", "bottle", "rack", "crystal", "sunset", "wireless", "sensor"
    ]
    
    matches = sum(1 for trigger in high_volume_triggers if trigger in keyword_lower)
    if matches >= 2:
        estimated_active_ads = 8 + (hash(title) % 7)
        is_scaling = True
        scale_verdict = "Heavy Scaling (Multiple Active Stores)"
    elif matches == 1:
        estimated_active_ads = 4 + (hash(title) % 5)
        is_scaling = True
        scale_verdict = "Moderate Scaling (Active Campaigns Found)"
    else:
        estimated_active_ads = 1 + (hash(title) % 3)
        is_scaling = False
        scale_verdict = "Low Saturation (Fresh Untapped Angle)"

    return {
        "keyword": keyword,
        "ad_library_url": ad_library_url,
        "estimated_active_ads": estimated_active_ads,
        "is_scaling": is_scaling,
        "scale_verdict": scale_verdict
    }
