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

# Official DeoDap Category Collections for 100% Category-Authentic Harvesting
NICHE_COLLECTIONS_MAP = {
    "Festive & Lights": [
        "deodap-diwali-decoration",
        "diwali-decor",
        "pooja-essentials",
        "religious-idols-pooja-decor",
        "seasonal-festive-decorations",
        "decorative-and-string-lights",
        "candles",
        "deodap-diwali",
        "gift-sets-boxes",
        "corporate-gifting",
        "diwali-corporate-gifting",
        "festival-gift",
        "birthday-gift",
        "deodap-diwali-gifting",
    ],
    "Home Improvement": [
        "home-decor",
        "decor-ambience",
        "decorative-accessories",
        "specialty-decorative-lighting",
        "vases-items-2",
    ],
    "Home & Kitchen": [
        "kitchen-tools",
        "all-kitchen-accessories",
        "kitchen-appliances-utensils",
        "kitchen-storage-basket-stands",
        "kitchen-organizers",
        "daily-cooking-tools",
        "cookware",
    ],
    "Smart Gadgets": [
        "electronic-gadgets",
        "personal-tech-gadgets",
        "mobile-accessories",
        "computer-accessories",
        "usb-gadgets",
        "electronics",
        "electronics-accessories",
        "computers-electronics",
        "desk-lights",
        "lights",
        "lamps",
        "night-lights",
    ],
    "Health & Beauty Accessories": [
        "personal-care-appliances",
        "skin-care-tools",
        "makeup-accessories",
        "makeup-and-organizers",
        "massager",
        "hair-care-styling",
        "grooming-shaving",
        "health-beauty-personal-care",
        "personal-care-health-appliances",
        "foot-care",
    ],
    "Toys & Games": [
        "toys-games",
        "kids-toys",
    ],
}

# Strictly Excluded Wearable / Artificial Jewelry (Word-boundary matched; never blocks 'rechargeable' or 'string' or 'jewelry box')
EXCLUDED_JEWELRY = [
    "earring", "earrings", "necklace", "jhumka", "jhumki", "bracelet", "bracelets",
    "bangle", "bangles", "finger ring", "toe ring", "anklet", "choker",
    "mangalsutra", "kundan", "stud combo", "stud earring", "hoop earring",
    "assorted gold", "hasali", "temple jewellery", "payal", "bichiya", "ear ring",
    "neck piece", "gold-tone", "silver-tone", "oxidised", "1 gram gold", "gold forming",
    "locket necklace", "stick pendant",
]

# Global Junk & Non-Dropshipping Blocklist (Blocks food, raw agarbatti refills, hardware tools, stationery, consumables, cables)
GLOBAL_JUNK_KEYWORDS = [
    # Food / Perishables / Snacks / Chocolates
    "makhana", "chocolate", "choco", "soya", "dates", "nutty", "butterscotch",
    "blueberry", "almond", "cashew", "biscuit", "cookie", "snack", "namkeen",
    "pickle", "sweet", "candy", "toffee", "coffee powder", "edible", "fox nuts",
    "roasted crunchy", "protein roasted", "mouth freshener", "mukhwas",
    # Raw Consumable Agarbatti / Dhoop Stick Refill Packs (Durable burners/diffusers allowed)
    "agarbatti", "incense sticks", "dhoop sticks", "dhoop batti", "bela ke phool",
    "blue pearl", "chandan dhoop", "chandan herbal", "rose dhoop", "camphor tablet",
    "kapoor tablet", "hawan samagri", "gangajal", "cotton wicks", "ruyi batti",
    "kumkum", "roli", "chawal", "haldi kumkum",
    # Wearable Fashion / Artificial Jewelry / Apparel
    "earring", "earrings", "necklace", "jhumka", "jhumki", "bracelet", "bracelets",
    "bangle", "bangles", "toe ring", "anklet",
    "choker", "mangalsutra", "kundan", "stud combo", "stud earring",
    "hoop earring", "payal", "bichiya", "ear ring", "neck piece", "gold-tone",
    "silver-tone", "oxidised", "1 gram gold", "gold forming", "ankle length",
    "waist belt", "buckleless", "slipper", "sandal", "t-shirt", "kurti", "saree",
    "sunglass", "safety goggles", "goggles", "swimming goggles", "hair claw", "hair clip",
    "hair band", "scrunchie", "tiara", "brooch", "saree pin",
    # Industrial / Hardware / Plumbing / Raw Gardening Tools / Locks
    "spring clamp", "polishing wheel", "buffing wheel", "abrasive", "rotary tool",
    "drill bit", "screwdriver", "allen key", "wrench", "plier", "spanner",
    "utility knife", "replacement blade", "snap-off", "bib cock", "water tap",
    "plumbing", "teflon tape", "mounting tape", "foam tape", "bopp tape",
    "sealing tape", "cable protector", "cord cover", "wire hider", "padlock",
    "combination lock", "helmet cable lock", "helmet lock", "bicycle lock",
    "double hoe", "gardening hand tool", "garden trowel", "pruning shear",
    "impact sprinkler", "snow scraper", "safety hammer", "window breaker",
    "watering can", "solder", "multimeter", "glue stick", "hot melt glue",
    # School Stationery / Sports Balls / Party Banners
    "bendy ruler", "flexible ruler", "30cm", "eraser", "sharpener",
    "document file", "file folder", "expanding plastic",
    "stapler", "stationery kit", "stationery set", "school supplies", "pencil pouch",
    "geometry box", "compass box", "marker", "highlighter", "whiteboard",
    "table tennis", "ping pong",
    "feliz a", "new year", "happy birthday banner", "balloon", "party foil",
    "gift envelope", "shagun envelope", "money envelope", "carry bag", "packing bag",
    # Raw Liquid Cosmetics / Commodity Cables / Bags
    "hair oil", "olive hair", "argan", "bleach cream", "glycerine", "handmade soap",
    "bath bar", "tissue paper", "nipple cover", "detox foot", "kinoki", "color powder",
    "micro usb", "type c to lightning",
    "charging cable", "charging cord", "data cable", "wall adapter",
    "charging adapter", "fast charger", "usb splitter",
    "ac dust cover", "hanging shoe organizer", "laptop briefcase", "travel waist bag",
]

# Strict Title-Only Positive Rules for Each of the 6 Categories
NICHE_RULES = {
    "Festive & Lights": [
        "diya", "tealight", "tea light", "pooja thali", "puja thali", "aarti thali",
        "kalash", "pooja chowki", "bajot", "toran", "bandhanwar", "shubh labh",
        "swastik", "lakshmi footprint", "laxmi charan", "rangoli", "kapoor dani",
        "camphor diffuser", "electric diffuser", "backflow", "incense burner",
        "incense holder", "dhoop dani", "loban", "ganesh", "ganesha", "lakshmi",
        "laxmi", "adiyogi", "shiva", "krishna", "bal gopal", "jhula", "hanuman",
        "ram mandir", "mandir", "temple", "fairy light", "string light",
        "curtain light", "rice light", "jhalar", "festive light", "diwali",
        "urli", "deepak", "samai", "pooja bell", "shankh", "dry fruit box",
        "pooja", "puja", "festive", "lotus lamp", "lotus light", "akhand",
        "flameless", "star light", "bottle cork light",
    ],
    "Home Improvement": [
        "night lamp", "table lamp", "desk lamp", "crystal lamp", "crystal ball",
        "crystal globe", "crystal astronaut", "crystal adiyogi", "3d lamp",
        "illusion night light", "illusion lamp", "sunset lamp", "moon lamp",
        "rose lamp", "tulip lamp", "projector lamp", "ambient light", "wall lamp",
        "wall light", "neon light", "neon sign", "vase", "flower pot", "planter",
        "artificial plant", "artificial flower", "bonsai", "wall clock",
        "alarm clock", "photo frame", "wall decor", "showpiece", "statue",
        "figurine", "sculpture", "dream catcher", "wind chime", "sand timer",
        "hourglass", "candle holder", "aroma diffuser", "air humidifier",
        "mist humidifier", "humidifier", "floor mat", "bath mat", "round rug",
        "rug", "carpet", "cushion", "wall hook", "adhesive hook", "coat hook",
        "floating shelf", "wall shelf", "home decor", "night light", "led lamp",
        "study lamp", "touch lamp", "astronaut", "galaxy projector", "feng shui",
        "evil eye", "wall hanging", "macrame",
    ],
    "Home & Kitchen": [
        "kitchen", "chopper", "vegetable cutter", "clever cutter", "slicer",
        "peeler", "grater", "crusher", "masher", "garlic", "oil dispenser",
        "oil sprayer", "oil bottle", "spice rack", "spice box", "masala box",
        "dish rack", "sink", "faucet", "tap extender", "soap pump",
        "soap dispenser", "sponge holder", "cutting board", "chopping board",
        "spatula", "cooking", "ladle", "whisk", "egg beater", "milk frother",
        "frother", "egg tray", "egg boiler", "ice cube", "ice tray",
        "water bottle", "insulated bottle", "thermos", "flask", "tumbler",
        "sipper", "lunch box", "tiffin", "food storage", "fridge", "refrigerator",
        "storage jar", "storage container", "grain dispenser", "cereal dispenser",
        "strainer", "colander", "juicer", "lemon squeezer", "dough", "roti",
        "baking", "air fryer", "coaster", "serving tray", "fruit basket",
        "cutlery", "utensil", "bottle cleaning brush", "mortar", "pestle",
        "pizza cutter", "knife sharpener", "bowl", "plate", "dinner", "cookware",
        "pan", "pot", "kettle", "tea strainer", "sprout maker",
    ],
    "Smart Gadgets": [
        "portable fan", "mini fan", "neck fan", "cooling fan", "desk fan",
        "lint remover", "fabric shaver", "mini vacuum", "car vacuum", "vacuum cleaner",
        "electric cleaning brush", "spin scrubber", "portable blender", "bag sealer",
        "heat sealer", "vacuum sealer", "kitchen scale", "weighing scale",
        "luggage scale", "mosquito killer", "mosquito lamp", "bug zapper", "mosquito",
        "motion sensor", "cabinet light", "reading light", "book light",
        "selfie stick", "tripod", "ring light", "wireless mic", "microphone",
        "bluetooth speaker", "mini speaker", "speaker", "earbuds", "headphone",
        "cleaning pen", "airpod", "screen cleaner", "phone holder", "mobile stand",
        "laptop stand", "car phone", "car mount", "bicycle light", "bike light",
        "headlamp", "cob", "flashlight", "mini torch", "torch", "plasma lighter",
        "arc lighter", "electric lighter", "gas lighter", "massager", "neck massager",
        "foot massager", "face massager", "3d roller", "water dispenser pump",
        "automatic dispenser", "mini iron", "garment steamer", "ultrasonic",
        "writing tablet", "lcd", "mini printer", "thermal printer", "key finder",
        "smart tracker", "hair straightener", "curler", "trimmer", "shaver",
        "hair dryer", "night sensor", "emergency light", "solar light", "solar lamp",
        "solar wall", "voice recording", "tire inflator", "air pump", "wireless mouse",
        "gaming mouse", "keyboard", "laptop cooling", "cooling pad", "webcam",
        "usb hub", "otg", "card reader", "digital clock", "led clock", "rechargeable",
        "smart gadget", "bluetooth", "power bank", "car charger", "fm transmitter",
        "endoscope", "magnifying", "stylus", "mouse pad", "wrist support",
    ],
    "Gifts": [
        "gift set", "gift box", "gift boxes", "hamper", "corporate gift",
        "gold foil rose", "24k gold", "eternal rose", "golden rose", "rose bear",
        "teddy bear", "couple", "anniversary", "birthday", "valentine", "diary",
        "notebook", "pen set", "pen holder", "desk organizer", "executive",
        "wallet combo", "wallet set", "wallet", "keychain", "key chain",
        "perfume", "fragrance", "scented candle", "aroma gift", "coffee mug",
        "ceramic mug", "insulated mug", "office mug", "cat mug", "glass coffee mug",
        "cup set", "ceramic cups", "tea set", "vacuum flask set", "thermos flask",
        "jewelry box", "jewellery box", "jewelry organizer", "jewellery organizer",
        "organizer box", "music box", "snow globe", "keepsake", "return gift",
        "dry fruit box", "gift combo", "men's gift", "women's gift", "gift",
        "cruiser ship", "sand art", "baby buddha", "dashboard idol", "idol throne",
        "pocket mirror", "coin pouch", "handbag",
    ],
    "Health & Beauty Accessories": [
        "gua sha", "facial roller", "jade roller", "ice roller", "face roller",
        "face massager", "3d roller", "body massager", "neck massager",
        "foot massager", "scalp massager", "cellulite roller", "acupressure",
        "manicure", "pedicure", "nail care", "nail kit", "nail cutter", "nail clipper",
        "makeup brush", "makeup sponge", "beauty blender", "makeup organizer",
        "cosmetic organizer", "cosmetic bag", "vanity", "compact mirror", "led mirror",
        "hair brush", "detangling brush", "self-cleaning hair", "hair comb",
        "hair straightener", "hair curler", "hair styler", "hair dryer", "blow dryer",
        "nose trimmer", "ear trimmer", "hair trimmer", "beard trimmer", "beard apron",
        "threading", "epilator", "flawless", "eyebrow trimmer", "derma roller",
        "blackhead", "pore cleaner", "skin tag", "facial steamer", "nano mist",
        "hot water bag", "heating pad", "gel eye mask", "eye mask", "sleeping mask",
        "heel protector", "heel socks", "heel cup", "foot scrubber", "pumice",
        "bath brush", "shower brush", "back scrubber", "body scrubber", "bath sponge",
        "loofah", "water flosser", "electric toothbrush", "ear swab", "ear cleaner",
        "knee support", "posture corrector", "wrist support", "ankle support",
        "pill box", "medicine box", "shaving", "grooming",
    ],
    "Toys & Games": [
        "toy", "toys", "game", "games", "puzzle", "board game", "fidget",
        "magic cube", "speed cube", "rubik", "rubix", "building blocks", "block toy",
        "rc car", "remote control car", "remote car", "diecast", "die-cast",
        "racing car", "stunt car", "drone", "helicopter", "robot", "action figure",
        "doll", "barbie", "plush", "stuffed toy", "drawing tablet", "lcd writing",
        "water gun", "bubble gun", "bubble blower", "bubble machine", "slime",
        "clay set", "kinetic sand", "train set", "track set", "dart", "dartboard",
        "chess", "ludo", "carrom", "snake and ladder", "uno", "card game",
        "educational toy", "learning toy", "stem toy", "musical toy", "drum set",
        "xylophone", "piano toy", "walkie talkie", "glow track", "finger toy",
        "pop it", "push pop", "spinner", "yo-yo", "yoyo", "spinning top",
        "flying spinner", "magic slate", "magnetic tiles", "diy craft", "craft kit",
        "dough", "mind game", "shape sorter", "spinning bead", "puzzle card",
        "craft puzzle", "clay", "magnetic puzzle",
    ],
}


def is_jewelry_item(title: str, tags: str = "", description: str = "") -> bool:
    title_lower = (title or "").lower()
    if any(box_term in title_lower for box_term in ("jewelry box", "jewellery box", "jewelry organizer", "jewellery organizer", "gift box", "storage box")):
        return False
    return any(re.search(r"\b" + re.escape(j) + r"\b", title_lower) for j in EXCLUDED_JEWELRY)



def is_junk_or_mismatched_product(title: str, tags: str = "", description: str = "") -> bool:
    """Returns True if the product title matches any banned junk, food, stationery, hardware, or jewelry keyword."""
    tl = (title or "").lower()
    if not tl:
        return True
    if is_jewelry_item(title):
        return True
    return any(j in tl for j in GLOBAL_JUNK_KEYWORDS)


def get_concept_stem(title: str) -> str:
    """
    Computes a normalized product concept signature so the same product concept
    (e.g., 3D Crystal Ball Lamp, Water Sensor Diya, Coffee Mug) is capped at max 2 per category.
    """
    tl = re.sub(r"[^a-z0-9\s]", " ", (title or "").lower())
    if "crystal" in tl and ("ball" in tl or "globe" in tl or "lamp" in tl or "night" in tl):
        return "3d_crystal_lamp"
    if "water" in tl and "sensor" in tl and "diya" in tl:
        return "water_sensor_diya"
    if "tealight" in tl or "tea light" in tl:
        return "led_tealight_candle"
    if "kapoor" in tl or "camphor" in tl:
        return "kapoor_dani_diffuser"
    if "backflow" in tl:
        return "backflow_incense_burner"
    if "shubh" in tl and "labh" in tl:
        return "shubh_labh_decor"
    if "toran" in tl or "bandhanwar" in tl:
        return "festive_toran_hanging"
    if ("pooja" in tl or "puja" in tl or "aarti" in tl) and "thali" in tl:
        return "pooja_thali_set"
    if "coffee" in tl and "mug" in tl:
        return "coffee_mug_gift"
    if "gold" in tl and "rose" in tl:
        return "gold_foil_rose_gift"
    if "oil" in tl and ("dispenser" in tl or "sprayer" in tl or "bottle" in tl):
        return "kitchen_oil_dispenser"
    if "ice" in tl and ("tray" in tl or "cube" in tl):
        return "ice_cube_tray"
    if "water" in tl and "bottle" in tl:
        return "water_bottle"
    if "soap" in tl and ("dispenser" in tl or "pump" in tl):
        return "soap_dispenser"
    stop = {
        "with", "for", "and", "the", "set", "pack", "pcs", "piece", "combo",
        "home", "use", "mini", "pro", "new", "best", "multipurpose", "portable",
        "rechargeable", "electric", "usb", "led", "plastic", "wooden", "metal",
        "stainless", "steel", "colorful", "assorted", "premium", "luxury",
    }
    words = [w for w in tl.split() if len(w) > 2 and not w.isdigit() and w not in stop]
    return "_".join(words[:3]) or tl[:20]


def classify_niche(
    title: str,
    tags: str = "",
    description: str = "",
    preferred_niche: Optional[str] = None,
) -> Optional[str]:
    """
    Strictly classifies a product into one of the 5 core categories based on its TITLE.
    Returns None if the product matches the Global Junk Blocklist or does not genuinely match any category.
    """
    title_lower = (title or "").lower()
    if is_junk_or_mismatched_product(title_lower):
        return None

    scores: Dict[str, int] = {n: 0 for n in NICHE_RULES}
    for niche, keywords in NICHE_RULES.items():
        for kw in keywords:
            if kw in title_lower:
                # Multi-word exact phrases get higher specificity weight
                scores[niche] += len(kw.split()) * 4

    # Map aliases for preferred_niche
    alias_map = {
        "Festive": "Festive & Lights", "Kitchen": "Home & Kitchen", "Kitchen & Dining": "Home & Kitchen",
        "Gadgets": "Smart Gadgets", "Health & Beauty": "Health & Beauty Accessories", "Home Decor": "Home Improvement",
        "Gifts": "Festive & Lights", "Gifts & Hampers": "Festive & Lights", "Toys": "Toys & Games",
    }
    pref = alias_map.get(preferred_niche, preferred_niche)
    if pref and pref in scores and scores[pref] > 0:
        return pref

    best_niche = max(scores, key=scores.get)
    if scores[best_niche] > 0:
        return best_niche
    return None


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


def _format_deodap_item(
    p: Dict[str, Any],
    current_page: int,
    idx: int,
    source_url: str,
    fetched_at: str,
    preferred_niche: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
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

    if wholesale_cost is None or wholesale_cost < 28.0 or wholesale_cost > 245.0:
        return None

    in_stock = variant.get("available")
    if in_stock is None:
        in_stock = any(bool(v.get("available")) for v in variants)
    if not in_stock:
        return None

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

    niche = classify_niche(title, tags, clean_desc, preferred_niche=preferred_niche)
    if not niche:
        return None

    images = [img.get("src") for img in p.get("images", []) if img.get("src")]
    primary_image = images[0] if images else (p.get("image", {}).get("src") if isinstance(p.get("image"), dict) else None)
    if not primary_image:
        return None

    raw_grams = variant.get("grams")
    try:
        weight_grams = int(raw_grams) if raw_grams is not None and int(raw_grams) > 0 else None
    except (ValueError, TypeError):
        weight_grams = None

    dimensions = _extract_dimensions(f"{title} {clean_desc}")
    deliv_min, deliv_max = _extract_delivery_days(clean_desc)

    raw_compare = variant.get("compare_at_price")
    try:
        compare_at_price = float(raw_compare) if raw_compare is not None and float(raw_compare) > 0 else None
    except (ValueError, TypeError):
        compare_at_price = None

    return {
        "id": p.get("id"),
        "variant_id": variant.get("id"),
        "handle": handle,
        "title": title,
        "deodap_url": f"https://www.deodap.in/products/{handle}",
        "source": "DeoDap Shopify API",
        "source_url": source_url,
        "fetched_at": fetched_at,
        "method": "api",
        "primary_image": primary_image,
        "image_url": primary_image,
        "images": images,
        "wholesale_cost": wholesale_cost,
        "wholesale_price": wholesale_cost,
        "compare_at_price": compare_at_price,
        "in_stock": bool(in_stock),
        "niche": niche,
        "concept_stem": get_concept_stem(title),
        "weight_grams": weight_grams,
        "dimensions": dimensions,
        "delivery_min_days": deliv_min,
        "delivery_max_days": deliv_max,
        "bestseller_rank": (current_page - 1) * 250 + idx + 1,
        "sku": variant.get("sku") or None,
        "barcode": variant.get("barcode") or None,
        "tags": tags,
        "description": clean_desc[:800] if clean_desc else ""
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
    limit_per_niche: int = 30,
    min_price: float = 28.0,
    max_price: float = 245.0,
    randomize: bool = True,
    batch_cursor: Optional[int] = None,
    extra_excluded_keys: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Pulls fresh, real category-verified product data from DeoDap's official niche collections
    with full timestamps and provenance metadata.
    Strictly filters out any product in the 4-Key Zero-Repeat Export Vault or Global Junk Blocklist.
    """
    import os
    from collections import Counter
    from winning_engine.export_ledger import (
        build_exclusion_sets,
        extract_product_fingerprints,
        is_product_already_exported,
    )

    is_vercel = bool(os.environ.get("VERCEL"))
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    excl_sets = build_exclusion_sets(extra_excluded_keys)
    seen_skus = set(excl_sets[0])
    seen_handles = set(excl_sets[1])
    seen_vids = set(excl_sets[2])
    seen_tfps = set(excl_sets[3])

    def _can_accept(candidate: Dict[str, Any]) -> bool:
        if not candidate or candidate.get("in_stock") is False:
            return False
        if is_junk_or_mismatched_product(candidate.get("title", "")):
            return False
        if is_product_already_exported(candidate, (seen_skus, seen_handles, seen_vids, seen_tfps)):
            return False
        fp = extract_product_fingerprints(candidate)
        if fp["sku"]:
            seen_skus.add(fp["sku"])
        if fp["handle"]:
            seen_handles.add(fp["handle"])
        if fp["variant_id"]:
            seen_vids.add(fp["variant_id"])
        if fp["title_fp"]:
            seen_tfps.add(fp["title_fp"])
        return True

    state = _load_scan_state()
    if batch_cursor is not None and int(batch_cursor) > 0:
        page_cursor = ((int(batch_cursor) - 1) % 8) + 1
    else:
        page_cursor = int(state.get("page_cursor", 1))
    last_shown_handles = set(state.get("last_shown_handles", []))

    fetched_at = now_iso()
    live_items: List[Dict[str, Any]] = []
    live_sources_fetched = 0

    # 1. Live Fetch from DeoDap's Official Category Collections
    harvest_order = [
        "Festive & Lights",
        "Health & Beauty Accessories",
        "Home & Kitchen",
        "Home Improvement",
        "Smart Gadgets",
        "Toys & Games",
    ]
    for target_niche in harvest_order:
        cols = NICHE_COLLECTIONS_MAP.get(target_niche, [])
        if not cols:
            continue
        col_idx = (page_cursor - 1) % len(cols)
        if is_vercel:
            selected_cols = [cols[col_idx]]
        elif limit_per_niche > 35:
            selected_cols = cols
        else:
            selected_cols = [cols[col_idx], cols[(col_idx + 1) % len(cols)]]

        niche_live_count = 0
        for col_handle in selected_cols:
            if niche_live_count >= limit_per_niche * 2:
                break
            url = f"https://www.deodap.in/collections/{col_handle}/products.json?limit=250&page=1&sort_by=best-selling"
            try:
                resp = requests.get(url, headers=headers, timeout=2.5 if is_vercel else 5.0)
                if resp.status_code == 200:
                    prods = resp.json().get("products", [])
                    live_sources_fetched += 1
                    for idx, p in enumerate(prods):
                        item = _format_deodap_item(p, 1, idx, url, fetched_at, preferred_niche=target_niche)
                        if item and item.get("niche") == target_niche and _can_accept(item):
                            live_items.append(item)
                            niche_live_count += 1
            except Exception as e:
                print(f"[DeoDap Harvester] Collection {col_handle} error: {e}")

    if live_sources_fetched > 0:
        append_audit_log(
            action="deodap_live_ingest",
            target=f"{len(live_items)} products",
            source="DeoDap Category Collections API",
            method="api",
            source_url="https://www.deodap.in/collections.json",
            details=f"Fetched {len(live_items)} pure category-verified items across {live_sources_fetched} collection requests."
        )

    # 2. Merge with previously cached pure DeoDap pool (re-verifying strict category purity)
    cache_file = REPO_DATA_DIR / "deodap_bestsellers_pool.json"
    cached_items: List[Dict[str, Any]] = []
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                raw_pool = json.load(f)
            for item in raw_pool:
                h = item.get("handle")
                if not h:
                    continue
                try:
                    c = float(item.get("wholesale_cost") or item.get("wholesale_price") or 0)
                except (ValueError, TypeError):
                    continue
                if not (min_price <= c <= max_price):
                    continue
                verified_niche = classify_niche(
                    item.get("title", ""),
                    item.get("tags", ""),
                    item.get("description", ""),
                    preferred_niche=item.get("niche"),
                )
                if not verified_niche:
                    continue
                item["niche"] = verified_niche
                item["concept_stem"] = get_concept_stem(item.get("title", ""))
                item.setdefault("source", "DeoDap Shopify API (Cached)")
                item.setdefault("source_url", f"https://www.deodap.in/products/{h}.json")
                item.setdefault("fetched_at", item.get("scanned_at_iso") or "2026-10-10T18:00:00+05:30")
                item.setdefault("method", "api")
                item.setdefault("in_stock", True)
                if _can_accept(item):
                    cached_items.append(item)
        except Exception as e:
            print(f"[DeoDap Harvester] Cache read warning: {e}")

    all_candidates = live_items + cached_items

    if live_items and not is_vercel:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(all_candidates[:1100], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # 3. Group by Niche, enforce Concept-Stem Diversity (max 2 per concept), and Rotate
    niches = ["Home Decor", "Kitchen", "Gadgets", "Festive", "Gifts", "Health & Beauty Accessories"]
    by_niche: Dict[str, List[Dict[str, Any]]] = {n: [] for n in niches}
    for item in all_candidates:
        n = item.get("niche")
        if n in by_niche:
            by_niche[n].append(item)

    selected_items: List[Dict[str, Any]] = []
    newly_shown_handles: List[str] = []

    for n in niches:
        pool = by_niche[n]
        if not pool:
            continue
        if randomize:
            shift = ((page_cursor - 1) * 6) % len(pool)
            rotated = pool[shift:] + pool[:shift]
            unseen = [x for x in rotated if x.get("handle") not in last_shown_handles]
            seen_before = [x for x in rotated if x.get("handle") in last_shown_handles]
            ordered_pool = unseen + seen_before
        else:
            ordered_pool = pool

        # Concept-stem diversity cap (max 2 items of the same concept stem per category slice)
        diverse_chosen: List[Dict[str, Any]] = []
        stem_counts: Counter = Counter()
        for cand in ordered_pool:
            stem = cand.get("concept_stem") or get_concept_stem(cand.get("title", ""))
            if stem_counts[stem] >= 2:
                continue
            stem_counts[stem] += 1
            diverse_chosen.append(cand)
            if len(diverse_chosen) >= limit_per_niche:
                break

        selected_items.extend(diverse_chosen)
        newly_shown_handles.extend(x.get("handle") for x in diverse_chosen if x.get("handle"))

    _save_scan_state({
        "page_cursor": (page_cursor % 8) + 1,
        "seed_cursor": 0,
        "last_shown_handles": newly_shown_handles[:120],
        "last_scan_at": fetched_at
    })

    return selected_items


def harvest_fresh_unexported_deodap_items(
    start_page: int = 1,
    max_pages: int = 2,
    exclusion_sets=None,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Crawls DeoDap's official category collections (`NICHE_COLLECTIONS_MAP`) to auto-refill
    the pool with 100% category-authentic, unexported winning products.
    """
    from winning_engine.export_ledger import (
        build_exclusion_sets,
        extract_product_fingerprints,
        is_product_already_exported,
    )

    excl = exclusion_sets or build_exclusion_sets()
    skus, handles, variant_ids, title_fps = (
        set(excl[0]),
        set(excl[1]),
        set(excl[2]),
        set(excl[3]),
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    fetched_at = now_iso()
    fresh_items: List[Dict[str, Any]] = []
    curr_cursor = max(1, int(start_page or 1))

    for step in range(max_pages):
        col_offset = curr_cursor + step
        for target_niche, cols in NICHE_COLLECTIONS_MAP.items():
            col_handle = cols[(col_offset - 1) % len(cols)]
            pg = ((col_offset - 1) // len(cols)) % 3 + 1
            url = f"https://www.deodap.in/collections/{col_handle}/products.json?limit=250&page={pg}&sort_by=best-selling"
            try:
                resp = requests.get(url, headers=headers, timeout=4.0)
                if resp.status_code != 200:
                    continue
                prods = resp.json().get("products", [])
                for idx, p in enumerate(prods):
                    item = _format_deodap_item(p, pg, idx, url, fetched_at, preferred_niche=target_niche)
                    if not item or not item.get("in_stock") or not item.get("images"):
                        continue
                    if is_product_already_exported(item, (skus, handles, variant_ids, title_fps)):
                        continue
                    fp = extract_product_fingerprints(item)
                    if fp["sku"]:
                        skus.add(fp["sku"])
                    if fp["handle"]:
                        handles.add(fp["handle"])
                    if fp["variant_id"]:
                        variant_ids.add(fp["variant_id"])
                    if fp["title_fp"]:
                        title_fps.add(fp["title_fp"])
                    fresh_items.append(item)
            except Exception as e:
                print(f"[DeoDap Auto-Refill] Collection {col_handle} warning: {e}")

    return fresh_items, curr_cursor + max_pages


