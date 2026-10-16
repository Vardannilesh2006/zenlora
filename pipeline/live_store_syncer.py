"""
Zenlora Live Store Syncer
=========================
Fetches ALL live products directly from zenlora.store by crawling
the SmartBiz __NEXT_DATA__ JSON embedded in each page.
- Works for Vercel (no pandas/openpyxl needed)
- Products update automatically when you add/delete on your store
- Smart LRU cache: 15-minute TTL to avoid hammering the store
- Falls back to local catalog_642.json if store is unreachable
"""
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import requests
    import bs4
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ─────────────── Paths ───────────────
try:
    from config import BASE_DIR, DATA_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"

LIVE_CACHE_FILE = DATA_DIR / "live_store_cache.json"

STORE_URL = "https://www.zenlora.store"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
CACHE_TTL_SECONDS = 900  # 15 minutes

_MEM: Dict[str, Any] = {"ts": 0.0, "products": None}


# ─────────────── Category classifier ───────────────
_CAT_RULES = [
    (["pooja", "diwali", "kalash", "matki", "tealight", "diya", "diya", "puja", "kalawa",
      "marigold", "festive", "festival", "rangoli", "toran", "mandir", "idol", "bhog",
      "aarti", "lamp", "deepak", "led candle", "flameless", "fairy light"], "Festive & Lights"),
    (["kitchen", "chopper", "cutter", "peeler", "grater", "tray", "dispenser", "spray",
      "oil", "spice", "cutting board", "rolling pin", "roti", "chakla", "atta", "knive",
      "knife", "fork", "spoon", "ladle", "spatula", "masher", "masala", "box", "jar", "container"], "Home & Kitchen"),
    (["gadget", "smart", "charger", "wireless", "bluetooth", "speaker", "usb", "clock",
      "digital", "sensor", "robot", "vacuum", "projector", "led strip", "rgb", "socket"], "Smart Gadgets"),
    (["hair", "brush", "comb", "shampoo", "serum", "face", "skin", "cream", "mask",
      "beauty", "makeup", "lipstick", "kajal", "nail", "lotion", "moisturizer",
      "eyebrow", "lash", "beard", "trimmer", "shaver"], "Health & Beauty Accessories"),
    (["toy", "game", "puzzle", "doll", "car", "lego", "board game", "kids", "children",
      "baby", "infant", "soft toy", "teddy"], "Toys & Games"),
    (["under 199", "under199", "budget", "combo", "set of", "pack of"], "Under 199 Collection"),
    (["curtain", "bedsheet", "pillow", "cushion", "mattress", "sofa", "chair", "table",
      "shelf", "rack", "hook", "hanger", "organizer", "drawer", "wardrobe", "mirror",
      "vase", "planter", "decor", "diffuser", "aroma", "candle", "wick", "incense",
      "paint", "brush", "roller", "tape", "screw", "drill", "tool", "hammer",
      "bulb", "tube light", "switch", "wire", "cable"], "Home Improvement"),
]

def _classify_category(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    for keywords, cat in _CAT_RULES:
        if any(k in text for k in keywords):
            return cat
    return "Home & Kitchen"


# ─────────────── Parser ───────────────
def _parse_item(item: Dict, source_tag: str = "") -> Optional[Dict]:
    """Convert a single SmartBiz store item dict to our standard format."""
    sku = item.get("itemSku") or item.get("sku", "")
    details = item.get("itemDetails", {})
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}

    name = details.get("name") or item.get("name", "")
    if not name or not sku:
        return None

    try:
        selling_price = int(float(details.get("sellingPrice") or item.get("sellingPrice") or 0))
    except Exception:
        selling_price = 0

    try:
        mrp = int(float(details.get("mrp") or item.get("mrp") or selling_price * 1.5))
    except Exception:
        mrp = selling_price

    desc = details.get("description") or ""
    clean_desc = re.sub(r"<[^>]+>", "", desc).strip()

    img_url = (
        details.get("imageUrl")
        or details.get("image_url")
        or (details.get("secondaryImageUrl", [None])[0] if details.get("secondaryImageUrl") else "")
        or ""
    )

    all_images = []
    if details.get("imageUrl"):
        all_images.append(details.get("imageUrl"))
    if details.get("secondaryImageUrl") and isinstance(details.get("secondaryImageUrl"), list):
        for sec in details.get("secondaryImageUrl"):
            if sec and sec not in all_images:
                all_images.append(sec)
    if img_url and img_url not in all_images:
        all_images.append(img_url)

    disc_pct = 0
    if mrp > selling_price > 0:
        disc_pct = round((mrp - selling_price) / mrp * 100)

    cat = _classify_category(name, clean_desc)
    handle = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]

    return {
        "sku": sku,
        "handle": handle,
        "title": name,
        "mrp": mrp,
        "selling_price": selling_price,
        "category": cat,
        "description": clean_desc[:500],
        "image_url": img_url,
        "images": all_images,
        "discount_pct": disc_pct,
        "last_updated": details.get("lastUpdatedTime", 0),
        "in_stock": (details.get("buyingOptions", {})
                    .get("singlePurchase", {})
                    .get("availability", {})
                    .get("inStock", True)),
        "store_url": f"{STORE_URL}/product/{sku}",
        "source": source_tag,
        "live_verified": True,
    }


def _scrape_page(url: str) -> List[Dict]:
    """Scrape any zenlora.store page and extract all products from __NEXT_DATA__."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        nd = soup.find("script", id="__NEXT_DATA__")
        if not nd:
            return []
        d = json.loads(nd.string)
        props = d.get("props", {}).get("pageProps", {})

        items = []

        # 1. products list (the main list with all 10 items per page)
        for p in props.get("products", []):
            parsed = _parse_item(p, "products_list")
            if parsed:
                items.append(parsed)

        # 2. productSkuDictionary (featured / curated sections)
        for sec, sec_items in props.get("productSkuDictionary", {}).items():
            if isinstance(sec_items, list):
                for p in sec_items:
                    parsed = _parse_item(p, f"sku_dict_{sec}")
                    if parsed:
                        items.append(parsed)

        return items
    except Exception:
        return []


def _scrape_full_catalog() -> List[Dict]:
    """
    Smart multi-page scraper:
    1. Hits homepage (10 products)
    2. Hits /all-products (10 products)
    3. Hits each known collection page (varies)
    4. Deduplicates by SKU
    Returns all unique live products.
    """
    seen_skus: Dict[str, Dict] = {}

    # Pages to scrape (homepage + all-products + each collection ID)
    pages = [
        STORE_URL,
        f"{STORE_URL}/all-products",
    ]

    # First pass: get collection IDs from homepage
    try:
        r = requests.get(STORE_URL, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            soup = bs4.BeautifulSoup(r.text, "html.parser")
            nd = soup.find("script", id="__NEXT_DATA__")
            if nd:
                d = json.loads(nd.string)
                props = d.get("props", {}).get("pageProps", {})
                for col in props.get("allCollections", []):
                    cid = col.get("id")
                    if cid:
                        pages.append(f"{STORE_URL}/collection/{cid}")
    except Exception:
        pass

    # Scrape all pages
    for page_url in pages:
        items = _scrape_page(page_url)
        for item in items:
            sku = item["sku"]
            if sku not in seen_skus:
                seen_skus[sku] = item
            else:
                # Keep the one with more recent lastUpdatedTime
                if item.get("last_updated", 0) > seen_skus[sku].get("last_updated", 0):
                    seen_skus[sku] = item

    products = list(seen_skus.values())

    # Enrich with multi-angle photos from catalog_642.json and products_db.json
    fallback_map = {}
    for fb_name in ("catalog_642.json", "products_db.json"):
        fb_path = DATA_DIR / fb_name
        if fb_path.exists():
            try:
                with open(fb_path, "r", encoding="utf-8") as f:
                    fb_data = json.load(f)
                    for item in fb_data:
                        sku_k = (item.get("sku") or "").lower().strip()
                        title_k = (item.get("title") or item.get("zenlora_title") or "")[:25].lower().strip()
                        imgs = item.get("images") or ([item.get("image_url")] if item.get("image_url") else [])
                        if imgs:
                            if sku_k and sku_k not in fallback_map:
                                fallback_map[sku_k] = imgs
                            if title_k and title_k not in fallback_map:
                                fallback_map[title_k] = imgs
            except Exception:
                pass

    for p in products:
        sku_k = (p.get("sku") or "").lower().strip()
        title_k = (p.get("title") or "")[:25].lower().strip()
        extra_imgs = fallback_map.get(sku_k) or fallback_map.get(title_k) or []
        cur_imgs = list(p.get("images") or [])
        if p.get("image_url") and p["image_url"] not in cur_imgs:
            cur_imgs.insert(0, p["image_url"])
        for im in extra_imgs:
            if im and im not in cur_imgs:
                cur_imgs.append(im)
        p["images"] = cur_imgs or ([p.get("image_url")] if p.get("image_url") else [])

    products.sort(key=lambda x: x.get("last_updated", 0), reverse=True)
    return products


def _save_cache(products: List[Dict]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_at": time.time(), "products": products}
        with open(LIVE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_cache() -> Optional[Dict]:
    try:
        if LIVE_CACHE_FILE.exists():
            with open(LIVE_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


# ─────────────── Public API ───────────────
def fetch_live_products(force_refresh: bool = False) -> List[Dict]:
    """
    Returns live products from zenlora.store.
    - First call scrapes the store (2-4 seconds)
    - Subsequent calls within 15 minutes use in-memory cache (instant)
    - Disk cache survives server restarts
    - Falls back to catalog_642.json if unreachable
    """
    now = time.time()

    # 1. In-memory cache hit
    if not force_refresh and _MEM["products"] and (now - _MEM["ts"]) < CACHE_TTL_SECONDS:
        return _MEM["products"]

    # 2. Disk cache hit (if not expired)
    if not force_refresh:
        cached = _load_cache()
        if cached and (now - cached.get("fetched_at", 0)) < CACHE_TTL_SECONDS:
            products = cached["products"]
            _MEM["ts"] = now
            _MEM["products"] = products
            return products

    # 3. Live scrape
    if HAS_REQUESTS:
        try:
            products = _scrape_full_catalog()
            if products:
                _MEM["ts"] = now
                _MEM["products"] = products
                _save_cache(products)
                return products
        except Exception:
            pass

    # 4. Fallback: stale disk cache
    cached = _load_cache()
    if cached and cached.get("products"):
        products = cached["products"]
        _MEM["ts"] = now
        _MEM["products"] = products
        return products

    # 5. Fallback: catalog_642.json
    fallback = DATA_DIR / "catalog_642.json"
    if fallback.exists():
        try:
            with open(fallback, "r", encoding="utf-8") as f:
                products = json.load(f)
            _MEM["ts"] = now
            _MEM["products"] = products
            return products
        except Exception:
            pass

    return []


def get_live_stats() -> Dict[str, Any]:
    products = fetch_live_products()
    categories: Dict[str, int] = {}
    for p in products:
        cat = p.get("category", "Other")
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total_products": len(products),
        "categories": categories,
        "cache_age_seconds": int(time.time() - _MEM["ts"]) if _MEM["ts"] else None,
        "source": "live_store" if HAS_REQUESTS else "fallback_json",
    }
