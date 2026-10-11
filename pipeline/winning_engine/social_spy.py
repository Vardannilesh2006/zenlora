"""
Instagram Validation & Festival Category Mapping Module (Research Pipeline Step 5):
1. Uses official Instagram Graph API hashtag search ONLY if INSTAGRAM_ACCESS_TOKEN
   and INSTAGRAM_USER_ID are provided in .env.
2. Otherwise provides a manual entry form (reel_link, views, saves_shares,
   price_link_comments_count, date_checked) with method='manual_entry'.
3. Never invents engagement numbers, views, or likes.
"""
import os
import urllib.parse
from typing import Dict, Any, Optional
import requests

from winning_engine.data_models import (
    get_product_manual_entry,
    is_timestamp_stale,
    load_settings,
    now_iso,
    REPO_DATA_DIR,
)


def _get_ig_credentials():
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    uid = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    if token and uid:
        return token, uid
    env_file = REPO_DATA_DIR.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("INSTAGRAM_ACCESS_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                    elif line.startswith("INSTAGRAM_USER_ID="):
                        uid = line.split("=", 1)[1].strip()
        except Exception:
            pass
    return token, uid


def detect_festival_mood(keyword: str, niche: str) -> str:
    """Matches product against user's editable Festival -> Keyword Seed Map (labelled rule_based)."""
    settings = load_settings()
    seed_map = settings.get("festival_keyword_seeds", {})
    kw_low = keyword.lower()

    for fest_cat, seeds in seed_map.items():
        if fest_cat.startswith("_") or not isinstance(seeds, list):
            continue
        if any(s.lower() in kw_low for s in seeds):
            return fest_cat

    if any(k in kw_low for k in ["brush", "mop", "duster", "clean", "scrub", "wiper", "drain"]):
        return "Diwali Cleaning"
    if any(k in kw_low for k in ["thali", "kalash", "chowki", "brass", "copper"]):
        return "Dhanteras"
    if any(k in kw_low for k in ["dry fruit", "grooming", "manicure", "gift", "hamper"]):
        return "Diwali Gifting"
    if any(k in kw_low for k in ["diya", "rangoli", "light", "kapoor", "toran", "shubh labh", "ganesha", "shiva", "lamp", "candle"]):
        return "Diwali Decor"
    return f"{niche}"


def analyze_social_velocity(keyword: str, niche: str, handle: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns official Instagram Graph API data (if credentials exist) or user's manual entry.
    Never invents views, likes, or comment counts.
    """
    mood_label = detect_festival_mood(keyword, niche)
    clean_tag = "".join(ch for ch in keyword.lower() if ch.isalnum())[:24] or "diwalidecor"
    hashtags = [f"#{clean_tag}", "#diwalidecor", "#indianhome"]
    instagram_url = f"https://www.instagram.com/explore/tags/{urllib.parse.quote(clean_tag)}/"

    settings = load_settings()
    stale_days = int(settings.get("general", {}).get("stale_days_limit", 7))

    # 1. Check if user has entered manual Instagram validation for this product
    manual_all = get_product_manual_entry(handle) if handle else {}
    manual_ig = manual_all.get("instagram")

    if manual_ig and (manual_ig.get("views") is not None or manual_ig.get("reel_link")):
        fetched_at = manual_ig.get("fetched_at") or manual_ig.get("date_checked")
        stale = is_timestamp_stale(fetched_at, stale_days)
        views = manual_ig.get("views")
        saves_shares = manual_ig.get("saves_shares")
        comments_count = manual_ig.get("price_link_comments_count")
        reel_link = manual_ig.get("reel_link") or instagram_url

        return {
            "primary_hashtag": hashtags[0],
            "hashtags": hashtags,
            "festival_category_seed": mood_label,
            "status": "done",
            "reel_link": reel_link,
            "views": views,
            "saves_shares": saves_shares,
            "price_link_comments_count": comments_count,
            "date_checked": manual_ig.get("date_checked") or fetched_at,
            "est_reels_views": f"{views} Views (Manual)" if views is not None else "Reel Linked",
            "est_reels_likes": f"{comments_count} 'Price/Link?' Comments" if comments_count is not None else "Checked",
            "scale_label": mood_label,
            "is_winning_ad": bool(comments_count and int(comments_count) >= 5),
            "instagram_url": reel_link,
            "source": "Instagram Manual Entry",
            "source_url": reel_link,
            "fetched_at": fetched_at,
            "method": "manual_entry",
            "is_stale": stale,
            "null_reason": None
        }

    # 2. Check Official Instagram Graph API if credentials supplied
    ig_token, ig_uid = _get_ig_credentials()
    if ig_token and ig_uid:
        api_url = f"https://graph.facebook.com/v19.0/ig_hashtag_search?user_id={ig_uid}&q={urllib.parse.quote(clean_tag)}&access_token={ig_token}"
        try:
            r = requests.get(api_url, timeout=5.0)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    ts = now_iso()
                    return {
                        "primary_hashtag": hashtags[0],
                        "hashtags": hashtags,
                        "festival_category_seed": mood_label,
                        "status": "done",
                        "reel_link": instagram_url,
                        "views": None,
                        "saves_shares": None,
                        "price_link_comments_count": None,
                        "date_checked": ts,
                        "est_reels_views": f"Hashtag ID: {data[0].get('id')}",
                        "est_reels_likes": "Graph API Verified",
                        "scale_label": mood_label,
                        "is_winning_ad": None,
                        "instagram_url": instagram_url,
                        "source": "Instagram Graph API",
                        "source_url": instagram_url,
                        "fetched_at": ts,
                        "method": "api",
                        "is_stale": False,
                        "null_reason": None
                    }
        except Exception:
            pass

    # 3. Honest Null State until user fills Manual Entry form
    return {
        "primary_hashtag": hashtags[0],
        "hashtags": hashtags,
        "festival_category_seed": mood_label,
        "status": "manual_needed",
        "reel_link": None,
        "views": None,
        "saves_shares": None,
        "price_link_comments_count": None,
        "date_checked": None,
        "est_reels_views": None,
        "est_reels_likes": None,
        "scale_label": mood_label,
        "is_winning_ad": None,
        "instagram_url": instagram_url,
        "source": "Instagram (Manual Entry / Graph API)",
        "source_url": instagram_url,
        "fetched_at": None,
        "method": "manual_entry",
        "is_stale": False,
        "null_reason": "Data not available: Instagram Graph API credentials not set & manual entry not filled yet"
    }
