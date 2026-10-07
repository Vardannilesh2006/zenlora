import urllib.parse
from typing import Dict, Any

def analyze_social_velocity(keyword: str, niche: str) -> Dict[str, Any]:
    """
    Simulates TikTok-Api & Instagram Reels social velocity tracking.
    Extracts viral hashtag presence (#amazonfinds, #trendinggadgets),
    computes estimated reel view velocity, and provides live search links.
    """
    encoded_kw = urllib.parse.quote(keyword)
    
    # Target hashtags based on niche
    niche_hashtags = {
        "Home Decor": ["#homedecorindia", "#aestheticdecor", "#amazonfinds"],
        "Kitchen": ["#kitchenhacks", "#kitchengadgets", "#usefulkitchenproducts"],
        "Gadgets": ["#smartgadgets", "#coolgadgets", "#techfinds"],
        "Festive": ["#diwalidecor", "#festivelights", "#poojadecor"],
        "Gifts": ["#giftideas", "#uniquegifts", "#aestheticgifts"]
    }
    
    hashtags = niche_hashtags.get(niche, ["#amazonfinds", "#trendingnow"])
    
    # Instagram Reels Search URL
    instagram_reels_url = f"https://www.instagram.com/explore/tags/{urllib.parse.quote(hashtags[0].replace('#', ''))}/"
    
    # Calculate deterministic estimated viral engagement
    keyword_hash = hash(keyword)
    views_million = round(1.2 + ((keyword_hash % 45) / 10.0), 1)
    likes_k = int(views_million * 42)
    
    # Saturation vs Scalability verdict (KalilFagundes inspiration)
    days_scaling = 12 + (keyword_hash % 18)
    if days_scaling >= 18:
        scale_label = f"🔥 Proven Winner ({days_scaling}d on Meta & Reels)"
        is_winning_ad = True
    else:
        scale_label = f"⚡ Fast Escalating ({days_scaling}d campaign active)"
        is_winning_ad = False

    return {
        "primary_hashtag": hashtags[0],
        "hashtags": hashtags,
        "est_reels_views": f"{views_million}M",
        "est_reels_likes": f"{likes_k}K",
        "days_scaling": days_scaling,
        "scale_label": scale_label,
        "is_winning_ad": is_winning_ad,
        "instagram_url": instagram_reels_url,
        "tiktok_tag_url": f"https://www.tiktok.com/tag/{hashtags[0].replace('#', '')}"
    }
