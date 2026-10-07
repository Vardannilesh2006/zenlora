import re
import urllib.request
import json
from typing import List, Dict, Any

# Target Niche Categories & Keywords
NICHE_RULES = {
    "Home Decor": [
        "decor", "vase", "lamp", "candle", "diffuser", "frame", "clock",
        "painting", "ambient", "sunset lamp", "statue", "planter", "pot", "rug", "cushion",
        "aesthetic", "table lamp", "crystal lamp", "moon lamp", "galaxy", "wall decor", "curtain"
    ],
    "Kitchen": [
        "kitchen", "chopper", "dispenser", "cleaner", "scrub", "wiper", "mop", "organizer",
        "rack", "tray", "peeler", "knife", "sink", "caddy", "bottle", "container", "oil sprayer",
        "slicer", "drainer", "cutlery", "silicone", "mat", "sponge", "foldable rack", "cookware", "grater"
    ],
    "Gadgets": [
        "smart", "usb", "rechargeable", "sensor", "digital", "gadget", "motion",
        "wireless", "electric", "charger", "fan", "mini cleaner",
        "automatic", "alarm", "stand", "holder", "massager", "bluetooth"
    ],
    "Festive": [
        "diwali", "festive", "diya", "fairy light", "curtain light", "puja", "pooja",
        "string light", "led diya", "festival", "rangoli", "brass diya", "mandir"
    ],
    "Gifts": [
        "gift set", "hamper", "couple gift", "custom gift", "luxury gift", "scented candle",
        "anniversary", "birthday gift", "gift box", "gifting"
    ]
}

def classify_niche(title: str, tags: str, description: str) -> str:
    combined = f"{title} {tags} {description}".lower()
    
    # Check each niche with word boundaries and phrase matching
    scores = {}
    for niche, keywords in NICHE_RULES.items():
        score = 0
        for kw in keywords:
            # Word boundary
            pattern = r'\b' + re.escape(kw) + r'\b'
            matches = len(re.findall(pattern, combined))
            if matches > 0:
                # Title matches have triple weight
                if re.search(r'\b' + re.escape(kw) + r'\b', title.lower()):
                    score += matches * 3
                else:
                    score += matches
        scores[niche] = score

    best_niche = max(scores, key=scores.get)
    if scores[best_niche] > 0:
        return best_niche
    
    # Secondary heuristic fallback
    title_lower = title.lower()
    if any(k in title_lower for k in ["lamp", "decor", "vase", "frame", "ambient"]):
        return "Home Decor"
    if any(k in title_lower for k in ["kitchen", "chopper", "bottle", "organizer", "rack", "cutter", "peeler"]):
        return "Kitchen"
    if any(k in title_lower for k in ["diwali", "diya", "festive", "fairy", "puja"]):
        return "Festive"
    if any(k in title_lower for k in ["gift", "hamper", "combo", "box"]):
        return "Gifts"
    return "Gadgets"

def harvest_deodap_bestsellers(limit_per_niche: int = 8, min_price: float = 60.0, max_price: float = 400.0) -> List[Dict[str, Any]]:
    """
    Fetches live bestsellers from DeoDap, filters by target niches and healthy wholesale margin.
    Ensures balanced distribution across Home Decor, Kitchen, Gadgets, Festive, and Gifts.
    """
    url = f"https://deodap.in/collections/all/products.json?limit=250&sort_by=best-selling"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    raw_products = []
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode('utf-8'))
            raw_products = data.get("products", [])
    except Exception as e:
        print(f"[DeoDap Harvester] Error fetching: {e}")

    harvested_by_niche: Dict[str, List[Dict[str, Any]]] = {
        "Home Decor": [],
        "Kitchen": [],
        "Gadgets": [],
        "Festive": [],
        "Gifts": []
    }
    seen_handles = set()

    for idx, p in enumerate(raw_products):
        handle = p.get("handle")
        if not handle or handle in seen_handles:
            continue
        seen_handles.add(handle)

        variants = p.get("variants", [])
        if not variants:
            continue
        
        variant = variants[0]
        try:
            wholesale_cost = float(variant.get("price", 0))
        except (ValueError, TypeError):
            continue

        # Skip products outside viable dropshipping cost range
        if wholesale_cost < min_price or wholesale_cost > max_price:
            continue

        # Check stock availability
        is_available = variant.get("available", True)
        if not is_available:
            continue

        title = p.get("title", "").strip()
        tags = p.get("tags", "")
        if isinstance(tags, list):
            tags = ", ".join(tags)
        
        body_html = p.get("body_html", "") or ""
        niche = classify_niche(title, tags, body_html)
        if niche not in harvested_by_niche:
            niche = "Gadgets"

        if len(harvested_by_niche[niche]) >= limit_per_niche:
            continue

        images = [img.get("src") for img in p.get("images", []) if img.get("src")]
        primary_image = images[0] if images else ""

        # Weight in grams
        grams = variant.get("grams", 350) or 350

        # Calculate psychological 3.2x selling price
        buffer_cost = wholesale_cost + 60.0
        raw_selling = buffer_cost * 3.2
        if raw_selling < 249:
            selling_price = 249
        elif raw_selling < 349:
            selling_price = 299
        elif raw_selling < 449:
            selling_price = 399
        elif raw_selling < 549:
            selling_price = 499
        elif raw_selling < 749:
            selling_price = 699
        elif raw_selling < 949:
            selling_price = 899
        else:
            selling_price = round(raw_selling / 50) * 50 - 1

        gross_profit = round(selling_price - wholesale_cost - 60.0, 1)
        margin_pct = round((gross_profit / selling_price) * 100, 1) if selling_price > 0 else 0

        item_dict = {
            "id": p.get("id"),
            "handle": handle,
            "title": title,
            "deodap_url": f"https://deodap.in/products/{handle}",
            "primary_image": primary_image,
            "image_url": primary_image,
            "images": images[:4],
            "wholesale_cost": wholesale_cost,
            "wholesale_price": wholesale_cost,
            "selling_price": selling_price,
            "gross_profit": gross_profit,
            "margin_pct": margin_pct,
            "niche": niche,
            "weight_grams": grams,
            "bestseller_rank": idx + 1,
            "sku": variant.get("sku", "") or handle,
            "description": body_html[:300] if body_html else ""
        }
        harvested_by_niche[niche].append(item_dict)

    # Flatten and return
    result = []
    for niche_list in harvested_by_niche.values():
        result.extend(niche_list)
    return result
