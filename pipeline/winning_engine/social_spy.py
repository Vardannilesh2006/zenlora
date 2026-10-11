import urllib.parse
from typing import Dict, Any

def detect_festival_mood(keyword: str, niche: str) -> str:
    """Classifies product into the 4 active Festival Buying Moods (Oct–Nov)."""
    kw_low = keyword.lower()
    if any(k in kw_low for k in ["brush", "mop", "duster", "clean", "scrub", "wiper", "drain", "groove", "sponge"]):
        return "🧹 Diwali Cleaning (Peak Demand)"
    if any(k in kw_low for k in ["thali", "kalash", "chowki", "brass", "copper", "steel bottle", "dhanteras"]):
        return "🪙 Dhanteras & Puja Special"
    if any(k in kw_low for k in ["dry fruit", "grooming", "manicure", "trimmer", "gift", "hamper", "combo"]):
        return "🎁 Diwali & Bhai Dooj Gifting"
    if any(k in kw_low for k in ["diya", "rangoli", "string light", "kapoor", "camphor", "toran", "shubh labh", "ganesha", "shiva", "adiyogi", "lamp", "candle"]):
        return "🪔 Diwali Decor & Lights"
    if niche == "Kitchen":
        return "🧹 Diwali Cleaning & Kitchen"
    return f"✨ {niche} Utility"

def analyze_social_velocity(keyword: str, niche: str) -> Dict[str, Any]:
    """
    Provides real Instagram Reels search & hashtag verification links (Step 5 & 6 of Hunting Process)
    and identifies the exact Festival Buying Mood. Zero fake/hashed view or like counts.
    """
    kw_low = keyword.lower()
    mood_label = detect_festival_mood(keyword, niche)

    if "cleaning" in mood_label.lower():
        hashtags = ["#diwalicleaning", "#cleaninghacks", "#homecleaning"]
    elif "dhanteras" in mood_label.lower():
        hashtags = ["#dhanteras", "#poojathali", "#diwalipooja"]
    elif "gifting" in mood_label.lower():
        hashtags = ["#diwaligifts", "#bhaidoojgifts", "#giftideasindia"]
    elif "decor" in mood_label.lower() or niche == "Festive":
        hashtags = ["#diwalidecor", "#waterleddiya", "#rangolistencil"]
    else:
        niche_hashtags = {
            "Home Decor": ["#homedecorindia", "#aestheticdecor", "#amazonfinds"],
            "Kitchen": ["#kitchenhacks", "#kitchengadgets", "#usefulkitchenproducts"],
            "Gadgets": ["#smartgadgets", "#coolgadgets", "#techfinds"],
            "Gifts": ["#giftideas", "#uniquegifts", "#aestheticgifts"]
        }
        hashtags = niche_hashtags.get(niche, ["#amazonfinds", "#trendingnow"])

    instagram_reels_url = f"https://www.instagram.com/explore/tags/{urllib.parse.quote(hashtags[0].replace('#', ''))}/"

    return {
        "primary_hashtag": hashtags[0],
        "hashtags": hashtags,
        "est_reels_views": mood_label,
        "est_reels_likes": "Check Comments/Saves",
        "days_scaling": 0,
        "scale_label": mood_label,
        "is_winning_ad": True,
        "instagram_url": instagram_reels_url,
        "tiktok_tag_url": f"https://www.google.com/search?q=site:instagram.com/reel+{urllib.parse.quote(keyword)}"
    }
