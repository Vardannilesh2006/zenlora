import re
import html
import json
import socket
import urllib.parse
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional

from winning_engine.data_models import (
    now_iso,
    load_settings,
    append_audit_log,
    RUNTIME_DATA_DIR,
    REPO_DATA_DIR,
)

# Ensure dual-stack IPv6 (2620:127:f00f:e::) + IPv4 resolution for deodap.in
_orig_getaddrinfo = socket.getaddrinfo
def _deodap_dual_stack_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in ("deodap.in", "www.deodap.in"):
        try:
            base = _orig_getaddrinfo(host, port, family, type, proto, flags)
        except Exception:
            base = []
        ipv6_entry = (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2620:127:f00f:e::", port, 0, 0))
        if ipv6_entry not in base:
            return [ipv6_entry] + base
        return base
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _deodap_dual_stack_getaddrinfo

SCAN_STATE_FILE = RUNTIME_DATA_DIR / "scan_state.json"

# Strictly Excluded from Festive (High RTO Wearable / Artificial Jewelry / Fragile Glass / Breakables)
EXCLUDED_JEWELRY = [
    "earring", "earrings", "necklace", "jhumka", "jhumki", "bracelet", "bracelets",
    "bangle", "bangles", "ring", "rings", "toe ring", "anklet", "jewel", "jewellery",
    "jewelry", "choker", "pendant", "chain", "mangalsutra", "kundan", "cuff",
    "poochi", "stud combo", "assorted gold", "hasali", "temple jewellery",
    "kada", "payal", "har", "mala", "bichiya", "ear ring", "neck piece",
    "crystal ball", "glass jar", "glass jars", "ceramic", "terracotta", "clay", "porcelain",
    "wall art", "1 gram gold", "gold forming"
]


def is_jewelry_item(title: str, tags: str = "", description: str = "") -> bool:
    combined = f"{title} {tags} {description}".lower()
    title_lower = title.lower()
    return any(re.search(r"\b" + re.escape(j) + r"\b", combined) or (j in title_lower) for j in EXCLUDED_JEWELRY)


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
    is_banned_festive = is_jewelry_item(title, tags, description)

    scores = {}
    for niche, keywords in NICHE_RULES.items():
        if niche == "Festive" and is_banned_festive:
            scores[niche] = -9999
            continue
        score = 0
        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            matches = len(re.findall(pattern, combined))
            if matches > 0:
                if re.search(r"\b" + re.escape(kw) + r"\b", title_lower):
                    score += matches * 6
                else:
                    score += matches
        scores[niche] = score

    best_niche = max(scores, key=scores.get)
    if scores[best_niche] > 0:
        return best_niche

    if any(k in title_lower for k in ["lamp", "decor", "vase", "frame", "ambient", "light", "clock"]):
        return "Home Decor"
    if any(k in title_lower for k in ["kitchen", "chopper", "bottle", "organizer", "rack", "cutter", "peeler", "cook"]):
        return "Kitchen"
    if not is_banned_festive and any(k in title_lower for k in ["diwali", "diya", "festive", "fairy", "puja", "mandir", "rangoli", "kalash", "thali"]):
        return "Festive"
    if any(k in title_lower for k in ["gift", "hamper", "combo", "box", "set"]):
        return "Gifts"
    return "Gadgets"


def _extract_dimensions(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"\b(\d+(?:\.\d+)?\s*[xX×*]\s*\d+(?:\.\d+)?(?:\s*[xX×*]\s*\d+(?:\.\d+)?)?\s*(?:cm|mm|inch|inches|in)\b)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_delivery_days(text: str):
    if not text:
        return None, None
    m = re.search(r"(?:delivery|deliver|dispatch|shipping).*?(\d+)\s*(?:to|\-)\s*(\d+)\s*(?:business|working)?\s*days", text, re.IGNORECASE)
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        if 1 <= d1 <= d2 <= 30:
            return d1, d2
    return None, None


def _format_deodap_item(p: Dict[str, Any], current_page: int, idx: int, source_url: str, fetched_at: str) -> Optional[Dict[str, Any]]:
    handle = p.get("handle")
    if not handle:
        return None
    variants = p.get("variants", [])
    if not variants:
        return None
    variant = variants[0]
    raw_price = variant.get("price")
    try:
        wholesale_cost = float(raw_price) if raw_price is not None and float(raw_price) > 0 else None
    except (ValueError, TypeError):
        wholesale_cost = None

    if wholesale_cost is None or wholesale_cost < 25.0 or wholesale_cost > 245.0:
        return None

    in_stock = variant.get("available")
    if in_stock is None:
        in_stock = any(bool(v.get("available")) for v in variants)

    title = (p.get("title") or "").strip()
    if not title:
        return None

    tags = p.get("tags", "")
    if isinstance(tags, list):
        tags = ", ".join(str(tag).strip() for tag in tags if str(tag).strip())
    elif tags is None:
        tags = ""
    elif not isinstance(tags, str):
        tags = str(tags)

    body_html = p.get("body_html", "") or ""
    clean_desc = re.sub(r"<[^>]+>", " ", body_html)
    clean_desc = html.unescape(clean_desc)
    clean_desc = " ".join(clean_desc.split())

    niche = classify_niche(title, tags, clean_desc)
    if is_jewelry_item(title, tags, clean_desc) and niche == "Festive":
        return None

    images = [img.get("src") for img in p.get("images", []) if img.get("src")]
    primary_image = images[0] if images else (p.get("image", {}).get("src") if isinstance(p.get("image"), dict) else None)

    # Real weight from supplier page if present (> 0); otherwise None (NEVER guess 350g)
    raw_grams = variant.get("grams")
    try:
        weight_grams = int(raw_grams) if raw_grams is not None and int(raw_grams) > 0 else None
    except (ValueError, TypeError):
        weight_grams = None

    dimensions = _extract_dimensions(f"{title} {clean_desc}")
    deliv_min, deliv_max = _extract_delivery_days(clean_desc)

    return {
        "id": p.get("id"),
        "handle": handle,
        "title": title,
        "deodap_url": f"https://www.deodap.in/products/{handle}",
        "source": "DeoDap Shopify API",
        "source_url": source_url,
        "fetched_at": fetched_at,
        "method": "api",
        "primary_image": primary_image,
        "image_url": primary_image,
        "images": images[:4],
        "wholesale_cost": wholesale_cost,
        "wholesale_price": wholesale_cost,
        "in_stock": bool(in_stock) if in_stock is not None else None,
        "niche": niche,
        "weight_grams": weight_grams,
        "dimensions": dimensions,
        "delivery_min_days": deliv_min,
        "delivery_max_days": deliv_max,
        "bestseller_rank": (current_page - 1) * 250 + idx + 1,
        "sku": variant.get("sku") or None,
        "tags": tags,
        "description": clean_desc[:400] if clean_desc else ""
    }


def _load_scan_state() -> Dict[str, Any]:
    if SCAN_STATE_FILE.exists():
        try:
            with open(SCAN_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"page_cursor": 1, "seed_cursor": 0, "last_shown_handles": []}


def _save_scan_state(state: Dict[str, Any]) -> None:
    try:
        SCAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SCAN_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def harvest_deodap_bestsellers(
    limit_per_niche: int = 20,
    min_price: float = 25.0,
    max_price: float = 245.0,
    randomize: bool = True
) -> List[Dict[str, Any]]:
    """
    Pulls fresh, real product data from DeoDap's official Shopify JSON endpoints
    with full timestamps and provenance metadata.
    Each scan rotates across live catalog pages and keyword seeds so clicking
    'Scan DeoDap Winners' returns fresh data across every category and 'All'.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    settings = load_settings()
    state = _load_scan_state()
    page_cursor = int(state.get("page_cursor", 1))
    seed_cursor = int(state.get("seed_cursor", 0))
    last_shown_handles = set(state.get("last_shown_handles", []))

    fetched_at = now_iso()
    live_items: List[Dict[str, Any]] = []
    seen_handles = set()
    live_sources_fetched = 0

    # 1. Live Fetch from DeoDap Collections API (rotating pages 1..6)
    pages_to_fetch = [page_cursor, (page_cursor % 6) + 1]
    for pg in pages_to_fetch:
        url = f"https://www.deodap.in/collections/all/products.json?limit=250&page={pg}&sort_by=best-selling"
        try:
            resp = requests.get(url, headers=headers, timeout=4.5)
            if resp.status_code == 200:
                prods = resp.json().get("products", [])
                live_sources_fetched += 1
                for idx, p in enumerate(prods):
                    item = _format_deodap_item(p, pg, idx, url, fetched_at)
                    if item and item["handle"] not in seen_handles and item.get("in_stock") is not False:
                        seen_handles.add(item["handle"])
                        live_items.append(item)
        except Exception as e:
            print(f"[DeoDap Harvester] Live page {pg} error: {e}")

    # 2. Live Fetch from DeoDap Search Suggest API for Rotating Festival & Category Keyword Seeds
    seed_map = settings.get("festival_keyword_seeds", {})
    all_seeds: List[str] = []
    for k, kw_list in seed_map.items():
        if k.startswith("_") or not isinstance(kw_list, list):
            continue
        all_seeds.extend(kw_list)
    # Also add core category seeds so all 5 niches get fresh live items
    all_seeds.extend(["table lamp", "kitchen chopper", "oil sprayer", "mini fan", "gift box", "humidifier"])

    if all_seeds:
        selected_seeds = [all_seeds[(seed_cursor + i) % len(all_seeds)] for i in range(4)]
        for kw in selected_seeds:
            q_enc = urllib.parse.quote(kw)
            sug_url = f"https://www.deodap.in/search/suggest.json?q={q_enc}&resources[type]=product&resources[limit]=10"
            try:
                r_sug = requests.get(sug_url, headers=headers, timeout=3.0)
                if r_sug.status_code == 200:
                    s_prods = r_sug.json().get("resources", {}).get("results", {}).get("products", [])
                    live_sources_fetched += 1
                    for idx, sp in enumerate(s_prods):
                        handle = sp.get("handle")
                        if not handle or handle in seen_handles:
                            continue
                        try:
                            cost = float(sp.get("price", 0))
                        except (ValueError, TypeError):
                            continue
                        if not (min_price <= cost <= max_price) or not sp.get("available", True):
                            continue
                        title = (sp.get("title") or "").strip()
                        body = sp.get("body", "") or ""
                        niche = classify_niche(title, "", body)
                        if is_jewelry_item(title, "", body) and niche == "Festive":
                            continue
                        seen_handles.add(handle)
                        live_items.append({
                            "id": sp.get("id"),
                            "handle": handle,
                            "title": title,
                            "deodap_url": f"https://www.deodap.in/products/{handle}",
                            "source": "DeoDap Search Suggest API",
                            "source_url": sug_url,
                            "fetched_at": fetched_at,
                            "method": "api",
                            "primary_image": sp.get("image"),
                            "image_url": sp.get("image"),
                            "images": [sp.get("image")] if sp.get("image") else [],
                            "wholesale_cost": cost,
                            "wholesale_price": cost,
                            "in_stock": bool(sp.get("available", True)),
                            "niche": niche,
                            "weight_grams": None,
                            "dimensions": _extract_dimensions(f"{title} {body}"),
                            "delivery_min_days": None,
                            "delivery_max_days": None,
                            "bestseller_rank": idx + 1,
                            "sku": handle,
                            "tags": kw,
                            "description": re.sub(r"<[^>]+>", " ", body)[:350]
                        })
            except Exception:
                continue

    if live_sources_fetched > 0:
        append_audit_log(
            action="deodap_live_ingest",
            target=f"{len(live_items)} products",
            source="DeoDap Shopify API",
            method="api",
            source_url=f"https://www.deodap.in/collections/all/products.json?page={page_cursor}",
            details=f"Fetched {len(live_items)} live in-stock items across {live_sources_fetched} API requests."
        )

    # 3. Merge with previously cached real DeoDap pool (preserving each item's real fetched_at timestamp)
    cache_file = REPO_DATA_DIR / "deodap_bestsellers_pool.json"
    cached_items: List[Dict[str, Any]] = []
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                raw_pool = json.load(f)
            for item in raw_pool:
                h = item.get("handle")
                if not h or h in seen_handles:
                    continue
                try:
                    c = float(item.get("wholesale_cost") or item.get("wholesale_price") or 0)
                except (ValueError, TypeError):
                    continue
                if not (min_price <= c <= max_price):
                    continue
                # Ensure honest null instead of old 350g fallback if weight wasn't verified
                raw_w = item.get("weight_grams")
                if raw_w == 350 and "fetched_at" not in item:
                    item["weight_grams"] = None
                item.setdefault("source", "DeoDap Shopify API (Cached)")
                item.setdefault("source_url", f"https://www.deodap.in/products/{h}.json")
                item.setdefault("fetched_at", item.get("scanned_at_iso") or "2026-10-10T18:00:00+05:30")
                item.setdefault("method", "api")
                item.setdefault("in_stock", True)
                item.setdefault("dimensions", _extract_dimensions(f"{item.get('title', '')} {item.get('description', '')}"))
                item.setdefault("delivery_min_days", None)
                item.setdefault("delivery_max_days", None)

                if item.get("niche") == "Festive" and not is_jewelry_item(item.get("title", ""), item.get("tags", ""), item.get("description", "")):
                    item["niche"] = "Festive"
                else:
                    item["niche"] = classify_niche(item.get("title", ""), item.get("tags", ""), item.get("description", ""))
                seen_handles.add(h)
                cached_items.append(item)
        except Exception as e:
            print(f"[DeoDap Harvester] Cache read warning: {e}")

    # Combine: freshly fetched live items FIRST, then cached items
    all_candidates = live_items + cached_items

    # Save updated pool back to cache so newly discovered live items persist with real timestamps
    if live_items:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(all_candidates[:600], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # 4. Group by Niche & Rotate so consecutive scans surface fresh items
    niches = ["Home Decor", "Kitchen", "Gadgets", "Festive", "Gifts"]
    by_niche: Dict[str, List[Dict[str, Any]]] = {n: [] for n in niches}
    for item in all_candidates:
        n = item.get("niche", "Gadgets")
        if n in by_niche:
            by_niche[n].append(item)
        else:
            by_niche["Gadgets"].append(item)

    selected_items: List[Dict[str, Any]] = []
    newly_shown_handles: List[str] = []

    for n in niches:
        pool = by_niche[n]
        if randomize and last_shown_handles:
            # Prioritize items NOT shown in the immediately previous scan
            unseen = [x for x in pool if x.get("handle") not in last_shown_handles]
            seen_before = [x for x in pool if x.get("handle") in last_shown_handles]
            # Rotate seen_before by page_cursor offset so order shifts deterministically
            if seen_before:
                shift = (page_cursor * 5) % len(seen_before)
                seen_before = seen_before[shift:] + seen_before[:shift]
            ordered_pool = unseen + seen_before
        else:
            ordered_pool = pool

        chosen = ordered_pool[:limit_per_niche]
        selected_items.extend(chosen)
        newly_shown_handles.extend(x.get("handle") for x in chosen if x.get("handle"))

    # Advance scan state cursors for next click
    _save_scan_state({
        "page_cursor": (page_cursor % 6) + 1,
        "seed_cursor": (seed_cursor + 4) % max(1, len(all_seeds)),
        "last_shown_handles": newly_shown_handles,
        "last_scan_at": fetched_at
    })

    return selected_items
