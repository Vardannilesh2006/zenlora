import re
import urllib.request
import json
import random
from typing import List, Dict, Any, Optional

# Strictly Excluded from Festive (High RTO Wearable / Artificial Jewelry / Fragile Glass / Breakables)
EXCLUDED_JEWELRY = [
    "earring", "earrings", "necklace", "jhumka", "jhumki", "bracelet", "bracelets",
    "bangle", "bangles", "ring", "rings", "toe ring", "anklet", "jewel", "jewellery",
    "jewelry", "choker", "pendant", "chain", "mangalsutra", "kundan", "cuff",
    "poochi", "stud combo", "assorted gold", "hasali", "temple jewellery",
    "kada", "payal", "har", "mala", "bichiya", "ear ring", "neck piece",
    "crystal ball", "glass jar", "glass jars", "ceramic", "terracotta", "clay", "porcelain",
    "wall art"
]

def is_jewelry_item(title: str, tags: str = "", description: str = "") -> bool:
    combined = f"{title} {tags} {description}".lower()
    title_lower = title.lower()
    return any(re.search(r'\b' + re.escape(j) + r'\b', combined) or (j in title_lower) for j in EXCLUDED_JEWELRY)

# Target Niche Categories & Keywords
NICHE_RULES = {
    "Home Decor": [
        "decor", "vase", "lamp", "candle", "diffuser", "frame", "clock",
        "painting", "ambient", "sunset lamp", "statue", "planter", "pot", "rug", "cushion",
        "aesthetic", "table lamp", "wall decor", "curtain", "humidifier", "tapestry", "led bulb",
        "showpiece", "mirror", "artificial flower"
    ],
    "Kitchen": [
        "kitchen", "chopper", "dispenser", "cleaner", "scrub", "wiper", "mop", "organizer",
        "rack", "tray", "peeler", "knife", "sink", "caddy", "bottle", "container", "oil sprayer",
        "slicer", "drainer", "cutlery", "silicone", "mat", "sponge", "foldable rack", "cookware", "grater",
        "lunch box", "scale", "juicer", "blender", "measuring", "spatula", "scissor", "ice tray"
    ],
    "Gadgets": [
        "smart", "usb", "rechargeable", "sensor", "digital", "gadget", "motion",
        "wireless", "electric", "charger", "fan", "mini cleaner", "power bank",
        "automatic", "alarm", "stand", "holder", "massager", "bluetooth", "earbuds",
        "vacuum", "tripod", "selfie", "speaker", "lighter", "multitool", "keychain tool"
    ],
    "Festive": [
        "water sensor led diya", "flameless decorative diya", "rangoli stencil", "kapoor dani",
        "camphor diffuser", "led string light", "shubh labh", "flower 5-step decorative diya",
        "decorative pooja thali", "pooja thali", "kalash pooja chowki", "adiyogi shiva backflow",
        "3d lord ganesha acrylic", "3d ganesha acrylic", "3d ganesha led", "acrylic swastik",
        "100-inch", "microfiber fan duster", "5 in 1 electric cleaning brush",
        "floor cleaning brush with water scraper", "rotating floor cleaning brush",
        "drain cleaner tool", "4 compartment dry fruit box", "5 compartment petal shape",
        "revolving dry fruit box", "compact travel grooming kit", "diwali", "festive", "diya",
        "toran", "pooja", "puja", "rangoli", "kalash", "incense", "dhoop"
    ],
    "Gifts": [
        "gift set", "hamper", "couple gift", "custom gift", "luxury gift", "scented candle",
        "anniversary", "birthday gift", "gift box", "gifting", "customized", "pen set",
        "wallet combo", "diary", "mug", "photo frame", "keychain gift", "surprise"
    ]
}

def classify_niche(title: str, tags: str = "", description: str = "") -> str:
    combined = f"{title} {tags} {description}".lower()
    title_lower = title.lower()

    # Absolute Exclusion: Zero Jewelry or Fragile Glass Crystal Balls in Festive
    is_banned_festive = is_jewelry_item(title, tags, description)

    scores = {}
    for niche, keywords in NICHE_RULES.items():
        if niche == "Festive" and is_banned_festive:
            scores[niche] = -9999
            continue
        score = 0
        for kw in keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            matches = len(re.findall(pattern, combined))
            if matches > 0:
                if re.search(r'\b' + re.escape(kw) + r'\b', title_lower):
                    score += matches * 6  # Strong title match priority
                else:
                    score += matches
        scores[niche] = score

    best_niche = max(scores, key=scores.get)
    if scores[best_niche] > 0:
        return best_niche
    
    # Secondary heuristic fallback
    if any(k in title_lower for k in ["lamp", "decor", "vase", "frame", "ambient", "light", "clock"]):
        return "Home Decor"
    if any(k in title_lower for k in ["kitchen", "chopper", "bottle", "organizer", "rack", "cutter", "peeler", "cook"]):
        return "Kitchen"
    if not is_banned_festive and any(k in title_lower for k in ["diwali", "diya", "festive", "fairy", "puja", "mandir", "rangoli", "kalash", "thali"]):
        return "Festive"
    if any(k in title_lower for k in ["gift", "hamper", "combo", "box", "set"]):
        return "Gifts"
    return "Gadgets"

def _format_deodap_item(p: Dict[str, Any], current_page: int, idx: int) -> Optional[Dict[str, Any]]:
    handle = p.get("handle")
    if not handle:
        return None
    variants = p.get("variants", [])
    if not variants:
        return None
    variant = variants[0]
    try:
        wholesale_cost = float(variant.get("price", 0))
    except (ValueError, TypeError):
        return None

    if wholesale_cost < 35.0 or wholesale_cost > 245.0:
        return None

    title = p.get("title", "").strip()
    tags = p.get("tags", "")
    if isinstance(tags, list):
        tags = ", ".join(str(tag).strip() for tag in tags if str(tag).strip())
    elif tags is None:
        tags = ""
    elif not isinstance(tags, str):
        tags = str(tags)
    body_html = p.get("body_html", "") or ""
    niche = classify_niche(title, tags, body_html)

    images = [img.get("src") for img in p.get("images", []) if img.get("src")]
    primary_image = images[0] if images else ""
    grams = variant.get("grams", 350) or 350

    buffer_cost = wholesale_cost + 60.0
    raw_selling = buffer_cost * 3.0
    if raw_selling < 249:
        selling_price = 249
    elif raw_selling < 349:
        selling_price = 299
    elif raw_selling < 449:
        selling_price = 399
    elif raw_selling < 549:
        selling_price = 499
    elif raw_selling < 649:
        selling_price = 599
    elif raw_selling < 749:
        selling_price = 699
    else:
        selling_price = 799

    gross_profit = round(selling_price - wholesale_cost - 60.0, 1)
    margin_pct = round((gross_profit / selling_price) * 100, 1) if selling_price > 0 else 0

    return {
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
        "bestseller_rank": (current_page - 1) * 250 + idx + 1,
        "sku": variant.get("sku", "") or handle,
        "description": body_html[:350] if body_html else ""
    }

def harvest_deodap_bestsellers(limit_per_niche: int = 20, min_price: float = 35.0, max_price: float = 245.0, randomize: bool = True) -> List[Dict[str, Any]]:
    """
    Harvests top bestsellers from DeoDap across 5 niches (Home Decor, Kitchen, Gadgets, Festive, Gifts).
    Enforces the 10-Point Dropshipping Checklist:
    - Wholesale cost <= ₹245 so Selling Price stays strictly within ₹199–₹799 impulse range.
    - Zero fragile glass / crystal balls / jewelry in Festive.
    """
    from pathlib import Path
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    raw_candidates: List[Dict[str, Any]] = []
    seen_handles = set()

    # 1. Load from bundled verified DeoDap bestsellers pool first
    cache_file = Path(__file__).resolve().parent.parent.parent / "data" / "deodap_bestsellers_pool.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_pool = json.load(f)
            if randomize:
                random.shuffle(cached_pool)
            for idx, item in enumerate(cached_pool):
                handle = item.get("handle")
                cost = float(item.get("wholesale_cost") or item.get("wholesale_price") or 100.0)
                if handle and handle not in seen_handles and 35.0 <= cost <= 245.0:
                    seen_handles.add(handle)
                    if item.get("niche") == "Festive" and not is_jewelry_item(item.get("title", ""), item.get("tags", ""), item.get("description", "")):
                        item["niche"] = "Festive"
                    else:
                        item["niche"] = classify_niche(
                            item.get("title", ""),
                            item.get("tags", ""),
                            item.get("description", "")
                        )
                    raw_candidates.append(item)
        except Exception as e:
            print(f"[DeoDap Harvester] Error loading cache pool: {e}")

    # 2. Optional live DeoDap supplement
    start_page = random.randint(1, 3) if randomize else 1
    url = f"https://deodap.in/collections/all/products.json?limit=250&page={start_page}&sort_by=best-selling"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as response:
            data = json.loads(response.read().decode('utf-8'))
            live_prods = data.get("products", [])
            for idx, p in enumerate(live_prods):
                formatted = _format_deodap_item(p, start_page, idx)
                if formatted and formatted["handle"] not in seen_handles:
                    seen_handles.add(formatted["handle"])
                    raw_candidates.append(formatted)
    except Exception as e:
        print(f"[DeoDap Harvester] Quick live fetch bypassed ({e}), using bundled cache.")

    # 3. Categorize candidates by niche
    niches = ["Home Decor", "Kitchen", "Gadgets", "Festive", "Gifts"]
    by_niche: Dict[str, List[Dict[str, Any]]] = {n: [] for n in niches}

    for item in raw_candidates:
        n = item["niche"]
        if n in by_niche:
            by_niche[n].append(item)
        else:
            by_niche["Gadgets"].append(item)

    # 4. Select exactly limit_per_niche items per niche with rotation
    selected_items: List[Dict[str, Any]] = []
    for n in niches:
        pool = by_niche[n]
        if randomize:
            random.shuffle(pool)
        
        # Take up to limit_per_niche
        chosen = pool[:limit_per_niche]
        
        # If pool was somehow short, borrow high-converting items from largest pool (never jewelry for Festive)
        if len(chosen) < limit_per_niche:
            deficit = limit_per_niche - len(chosen)
            if n == "Festive":
                fallback_pool = [
                    x for x in raw_candidates
                    if x not in chosen and x not in selected_items
                    and not is_jewelry_item(x.get("title", ""), x.get("tags", ""), x.get("description", ""))
                    and any(k in x.get("title", "").lower() for k in ["lamp", "light", "candle", "statue", "idol", "fountain", "diffuser", "frame", "decor"])
                ]
            else:
                fallback_pool = [x for x in raw_candidates if x not in chosen and x not in selected_items]
            if fallback_pool:
                for fb in fallback_pool[:deficit]:
                    fb_copy = dict(fb)
                    fb_copy["niche"] = n  # Map to requested niche
                    chosen.append(fb_copy)

        selected_items.extend(chosen)

    return selected_items
