import os
import re
import json
import time
import random
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from config import BASE_DIR, DATA_DIR, CONTINUITY_PROMPT
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    CONTINUITY_PROMPT = (
        "Continue the video seamlessly from the last scene of the previous clip. "
        "Keep the same characters, appearance, clothing, environment, camera style, lighting, "
        "and overall visual consistency. The new scene must naturally begin exactly where the previous scene ended."
    )

# Live store syncer (primary source — always fresh)
try:
    from live_store_syncer import fetch_live_products, get_live_stats
    HAS_LIVE_SYNCER = True
except ImportError:
    HAS_LIVE_SYNCER = False
    fetch_live_products = None
    get_live_stats = None

# ── Static fallback paths (used only when store is unreachable) ──
EXCEL_CATALOG_NAME = "zenlora_catalog_642_products_FIXED_READY_TO_UPLOAD.xlsx"
EXCEL_PATH = BASE_DIR / EXCEL_CATALOG_NAME
RUNTIME_CATALOG_JSON = DATA_DIR / "catalog_642.json"
REPO_CATALOG_JSON = BASE_DIR / "data" / "catalog_642.json"

RUNTIME_LEDGER_FILE = DATA_DIR / "reels_done_ledger.json"
REPO_LEDGER_FILE = BASE_DIR / "data" / "reels_done_ledger.json"

_CATALOG_MEM_CACHE: Dict[str, Any] = {"mtime": 0.0, "products": None, "by_sku": {}}
_LEDGER_MEM_CACHE: Dict[str, Any] = {"mtime": 0.0, "data": None}


def _build_json_from_excel() -> List[Dict[str, Any]]:
    """Fallback: parse Excel catalog when live store is unreachable."""
    if not EXCEL_PATH.exists():
        return []
    try:
        import pandas as pd
        df = pd.read_excel(EXCEL_PATH, sheet_name="bulk_upload_template")
        products = []
        for idx, row in df.iterrows():
            sku = str(row.get("Custom SKU (Optional) Maximum 40 characters") or row.get("SKU ID (Not to be Edited)") or f"SKU_{idx}").strip()
            title = str(row.get("Product Name (Mandatory) Maximum 200 characters") or "").strip()
            if not title or title.lower() == "nan":
                continue
            try:
                mrp = int(float(row.get("MRP (Mandatory) Number only") or 0))
            except Exception:
                mrp = 0
            try:
                selling_price = int(float(row.get("Selling Price (Optional) Number only Should be less than MRP") or 0))
            except Exception:
                selling_price = mrp or 399
            category = str(row.get("Product Category (Mandatory)") or "Home & Kitchen").strip()
            if category.lower() == "nan" or not category:
                category = "Home & Kitchen"
            desc = str(row.get("Product Description (Optional) Maximum 2000 characters") or "").strip()
            if desc.lower() == "nan":
                desc = ""
            images = []
            for i in range(1, 7):
                img = row.get(f"Product Image{i} (Optional)")
                if pd.notna(img) and str(img).startswith("http"):
                    images.append(str(img).strip())
            image_url = images[0] if images else ""
            disc_pct = round(((mrp - selling_price) / mrp) * 100) if mrp > selling_price and mrp > 0 else 0
            handle = sku.lower().replace(" ", "-").replace("_", "-")
            products.append({
                "id": f"zen_{idx+1}", "sku": sku, "handle": handle, "title": title,
                "mrp": mrp, "selling_price": selling_price, "category": category,
                "description": desc, "image_url": image_url, "images": images,
                "discount_pct": disc_pct, "store_url": f"https://www.zenlora.store/product/{sku}",
            })
        for target in (RUNTIME_CATALOG_JSON, REPO_CATALOG_JSON):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(products, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return products
    except Exception as e:
        print(f"[reels_catalog_engine] Excel fallback error: {e}")
        return []


def load_catalog(force_reload: bool = False) -> List[Dict[str, Any]]:
    """
    Load products from zenlora.store live (primary) → catalog_642.json (fallback) → Excel (last resort).
    Products update instantly when you add/delete on your live store.
    """
    # 1. In-memory cache (valid for 15 minutes, same as live_store_syncer TTL)
    now = time.time()
    if (
        not force_reload
        and _CATALOG_MEM_CACHE["products"] is not None
        and (now - _CATALOG_MEM_CACHE["mtime"]) < 900
    ):
        return _CATALOG_MEM_CACHE["products"]

    products = []

    # 2. Live store scrape (primary source — automatic with 15-min cache)
    if HAS_LIVE_SYNCER and fetch_live_products:
        try:
            live = fetch_live_products(force_refresh=force_reload)
            if live:
                products = live
        except Exception:
            products = []

    # 3. catalog_642.json (fast JSON cache)
    if not products:
        for p in (RUNTIME_CATALOG_JSON, REPO_CATALOG_JSON):
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        products = json.load(f)
                    break
                except Exception:
                    pass

    # 4. Excel fallback (Vercel doesn't have pandas by default, so this is local-only)
    if not products:
        products = _build_json_from_excel()

    # 5. products_db.json final fallback
    if not products:
        fallback_db = DATA_DIR / "products_db.json"
        if fallback_db.exists():
            try:
                with open(fallback_db, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for idx, p in enumerate(raw):
                        products.append({
                            "id": f"zen_{idx+1}",
                            "sku": p.get("sku") or p.get("handle") or f"SKU_{idx+1}",
                            "handle": p.get("handle") or f"prod-{idx+1}",
                            "title": p.get("title") or p.get("zenlora_title") or "Zenlora Luxury Product",
                            "mrp": p.get("mrp", 599),
                            "selling_price": p.get("selling_price", 299),
                            "category": p.get("primary_category", "Home & Kitchen"),
                            "description": p.get("description", ""),
                            "image_url": p.get("image_url", ""),
                            "images": p.get("images") or ([p.get("image_url")] if p.get("image_url") else []),
                            "discount_pct": p.get("discount_pct", 50),
                            "store_url": f"https://zenlora.store/search?q={p.get('sku', '')}",
                        })
            except Exception:
                pass

    by_sku = {p["sku"]: p for p in products if p.get("sku")}
    _CATALOG_MEM_CACHE["mtime"] = time.time()
    _CATALOG_MEM_CACHE["products"] = products
    _CATALOG_MEM_CACHE["by_sku"] = by_sku
    return products


def get_product_by_sku(sku: str) -> Optional[Dict[str, Any]]:
    load_catalog()
    return _CATALOG_MEM_CACHE["by_sku"].get(sku)


# -------------------------------------------------------------
# Done Ledger (Tick Mark Anti-Repeat Engine)
# -------------------------------------------------------------

def load_done_ledger() -> Dict[str, Any]:
    """Loads records of reels already made. Product disappears from views once marked done."""
    for path in (RUNTIME_LEDGER_FILE, REPO_LEDGER_FILE):
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        _LEDGER_MEM_CACHE["data"] = data
                        return data
            except Exception:
                pass
    _LEDGER_MEM_CACHE["data"] = {}
    return {}


def save_done_ledger(data: Dict[str, Any]) -> None:
    _LEDGER_MEM_CACHE["data"] = data
    for path in (RUNTIME_LEDGER_FILE, REPO_LEDGER_FILE):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def is_reel_done(sku: str) -> bool:
    ledger = _LEDGER_MEM_CACHE["data"] or load_done_ledger()
    return sku in ledger


def mark_reel_done(sku: str, title: str = "", character_mode: str = "auto") -> Dict[str, Any]:
    ledger = load_done_ledger()
    ledger[sku] = {
        "title": title,
        "character_mode": character_mode,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "done": True
    }
    save_done_ledger(ledger)
    return {"status": "success", "sku": sku, "is_done": True, "stats": get_catalog_stats()}


def unmark_reel_done(sku: str) -> Dict[str, Any]:
    ledger = load_done_ledger()
    if sku in ledger:
        del ledger[sku]
        save_done_ledger(ledger)
    return {"status": "success", "sku": sku, "is_done": False, "stats": get_catalog_stats()}


def get_catalog_stats() -> Dict[str, Any]:
    products = load_catalog()
    ledger = load_done_ledger()
    total = len(products)
    done_count = sum(1 for p in products if p["sku"] in ledger)
    remaining = total - done_count

    categories_stats = {}
    for p in products:
        cat = p.get("category", "Home & Kitchen")
        if cat not in categories_stats:
            categories_stats[cat] = {"total": 0, "done": 0, "remaining": 0}
        categories_stats[cat]["total"] += 1
        if p["sku"] in ledger:
            categories_stats[cat]["done"] += 1
        else:
            categories_stats[cat]["remaining"] += 1

    return {
        "total_products": total,
        "done_reels": done_count,
        "remaining_reels": remaining,
        "categories": categories_stats
    }


def query_reels_products(
    category: str = "All",
    search: str = "",
    page: int = 1,
    limit: int = 20,
    show_done: bool = False,
    shuffle_seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Returns filtered products.
    - If search is empty: excludes done products (unless show_done=True).
    - If search is provided: searches through all products, with 'is_done' tag.
    - Category filter applies.
    - Pagination with 20 items per view.
    """
    products = load_catalog()
    ledger = load_done_ledger()

    search_norm = search.strip().lower()

    filtered = []
    for p in products:
        # Category check
        if category and category != "All" and p.get("category") != category:
            continue

        done = p["sku"] in ledger

        # If user is searching specifically, search across all items
        if search_norm:
            text_match = (
                search_norm in p.get("title", "").lower()
                or search_norm in p.get("sku", "").lower()
                or search_norm in p.get("category", "").lower()
                or search_norm in p.get("description", "").lower()
            )
            if text_match:
                item = dict(p)
                item["is_done"] = done
                filtered.append(item)
        else:
            # Not searching: respect hide done rule
            if not show_done and done:
                continue
            item = dict(p)
            item["is_done"] = done
            filtered.append(item)

    # Optional shuffle/refresh with seed
    if shuffle_seed is not None:
        rng = random.Random(shuffle_seed)
        rng.shuffle(filtered)

    total_filtered = len(filtered)
    total_pages = max(1, (total_filtered + limit - 1) // limit)
    current_page = max(1, min(page, total_pages))

    start_idx = (current_page - 1) * limit
    end_idx = start_idx + limit
    page_items = filtered[start_idx:end_idx]

    # Tag each item with character mode recommendation
    for item in page_items:
        item["recommended_character_mode"] = recommend_character_mode(item["category"], item["title"])

    return {
        "products": page_items,
        "total_count": total_filtered,
        "current_page": current_page,
        "total_pages": total_pages,
        "limit": limit,
        "category": category,
        "stats": get_catalog_stats()
    }


# -------------------------------------------------------------
# 16-Second Dual-Act (8s + 8s) & Storyboard Prompt Generator
# -------------------------------------------------------------

def sanitize_for_ai_prompt(title: str) -> str:
    """
    Cleanses product titles for AI video & image generators (Google VideoFX, Kling, Runway, Luma, Midjourney)
    to prevent false-positive policy violations (weapons, religious figures/deities/idols, blades, sharp tools).
    """
    cleaned = title
    rules = [
        (r"\bom trishul damru decorative idol\b", "Handcrafted Antique Copper Metallic Accent Decor Centerpiece"),
        (r"\btrishul\b", "traditional artistic metallic motif"),
        (r"\bdamru\b", "classic acoustic metallic accent"),
        (r"\bidol\b", "decorative sculpted art centerpiece"),
        (r"\bidols\b", "decorative sculpted art centerpieces"),
        (r"\bstatue\b", "sculptural artistic centerpiece"),
        (r"\bpanchmukhi hanuman\b", "Traditional Handcrafted Figurine Heritage Centerpiece"),
        (r"\bganesh\b", "Traditional Handcrafted Figurine"),
        (r"\bganesha\b", "Traditional Handcrafted Figurine"),
        (r"\blaxmi charan\b", "Traditional Auspicious Festive Floor Art Set"),
        (r"\bpooja\b", "festive decor"),
        (r"\bpuja\b", "festive decor"),
        (r"\btemple\b", "ambient space"),
        (r"\bknife\b", "culinary prep tool"),
        (r"\bknives\b", "culinary prep tools"),
        (r"\bblade\b", "slicing component"),
        (r"\bblades\b", "slicing components"),
        (r"\bcutter\b", "kitchen produce prep tool"),
        (r"\bchopper\b", "multipurpose food processor"),
        (r"\bpeeler\b", "produce prep tool"),
        (r"\bgun\b", "dispenser device"),
        (r"\bweapon\b", "utility tool"),
        (r"\bkill\b", "remove"),
    ]
    for pattern, rep in rules:
        cleaned = re.sub(pattern, rep, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-,&']", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# User's Custom Reference Character is used as Start Frame in VideoFX / Kling / Runway
FEMALE_CREATOR_DESCRIPTION = (
    "The creator from the uploaded reference character start frame. "
    "Clean, expressive, natural gestures, warm D2C host presence matching the reference image."
)

ASMR_HANDS_DESCRIPTION = (
    "Aesthetic tactile close-up ASMR style. Well-manicured hands interacting with the product, crisp macro textures, "
    "tactile sound triggers, soft clicking or pouring, warm cozy Japandi bedroom/kitchen environment, zero faces shown."
)


def recommend_character_mode(category: str, title: str) -> str:
    """Detects whether Female Creator or ASMR Hands-Only fits best."""
    cat_lower = category.lower()
    title_lower = title.lower()

    # Beauty, grooming, unboxing, gifting, baby, personal care, problem solvers -> Female Creator
    creator_triggers = [
        "beauty", "grooming", "hair", "skin", "facial", "face", "massage", "baby", "toy", "game",
        "festive", "gift", "unboxing", "diwali", "puja", "pooja", "hack", "cutter", "peeler", "grater",
        "dispenser", "clean", "scrub", "mop", "brush", "lint", "organizer"
    ]
    if any(k in title_lower or k in cat_lower for k in creator_triggers):
        return "female_creator"

    # Ambient lamps, diffusers, humidifiers, aesthetic desk setups, clocks -> ASMR Hands
    asmr_triggers = [
        "lamp", "led", "ambient", "diffuser", "humidifier", "clock", "charger", "cable",
        "projector", "candle", "cozy", "sunset", "crystal", "smart gadget"
    ]
    if any(k in title_lower or k in cat_lower for k in asmr_triggers):
        return "asmr_hands"

    return "female_creator"


def generate_16s_reel_pack(product: Dict[str, Any], character_mode: str = "auto") -> Dict[str, Any]:
    """
    Generates the complete 16-second dual-act (8s + 8s) production pack:
    - 6-Panel Storyboard Grid Prompt (Midjourney / Ideogram / SDXL / NanoBanana)
    - Act 1 Video Prompt (0-8s: Hook & First Demo, using user's uploaded reference character)
    - Act 2 Video Prompt (8-16s: Continuity Injection + Makeover + Auto-DM CTA)
    - 16s Timed Voiceover Script (Hinglish + English)
    - Viral On-Screen Hooks
    - High-Converting Instagram/Shorts Caption
    - High-Intent Auto-DM Trigger Keyword
    - Trending Hashtags & Algorithmic Search Keywords
    """
    title = product.get("title", "Zenlora Luxury Product").replace("Zenlora™", "").strip()
    safe_title = sanitize_for_ai_prompt(title)
    category = product.get("category", "Home & Kitchen")
    selling_price = product.get("selling_price", 399)
    mrp = product.get("mrp", selling_price * 2 or 799)
    sku = product.get("sku", "")
    desc = product.get("description", "")

    if character_mode == "auto" or not character_mode:
        character_mode = recommend_character_mode(category, title)

    is_female_creator = (character_mode == "female_creator")
    character_desc = FEMALE_CREATOR_DESCRIPTION if is_female_creator else ASMR_HANDS_DESCRIPTION

    # Determine Auto-DM keyword
    clean_kw = "LINK"
    title_lower = title.lower()
    if "lamp" in title_lower or "light" in title_lower:
        clean_kw = "GLOW"
    elif "kitchen" in title_lower or "cut" in title_lower or "tray" in title_lower or "oil" in title_lower:
        clean_kw = "KITCHEN"
    elif "clean" in title_lower or "mop" in title_lower or "brush" in title_lower:
        clean_kw = "CLEAN"
    elif "diwali" in title_lower or "pooja" in title_lower or "kalash" in title_lower or "matki" in title_lower:
        clean_kw = "DIWALI"
    elif "decor" in title_lower or "vase" in title_lower:
        clean_kw = "DECOR"
    elif "smart" in title_lower or "gadget" in title_lower or "clock" in title_lower:
        clean_kw = "SMART"
    elif "beauty" in title_lower or "hair" in title_lower or "skin" in title_lower:
        clean_kw = "BEAUTY"

    # Environment setup
    if "kitchen" in category.lower() or "kitchen" in title_lower:
        env = "modern Japandi modular kitchen with clean white countertop and warm recessed lighting"
    elif "festive" in category.lower() or "light" in title_lower:
        env = "warm festive ambient living room decorated with soft brass accents and warm glowing fairy lights"
    elif "smart" in category.lower() or "gadget" in title_lower:
        env = "minimalist aesthetic dark oak study desk setup with ambient warm backlighting and clean cordless vibe"
    else:
        env = "aesthetic cozy Japandi room corner with textured beige linen, warm floor lamp glow, and soft natural lighting"

    # 1. 6-Panel Storyboard Grid Prompt
    # 1. 6-Panel Storyboard Grid Prompt (Consistent UGC Ad Comic Strip)
    if is_female_creator:
        storyboard_prompt = (
            f"A photorealistic, highly detailed 6-panel AI Video Storyboard Grid (2 rows by 3 columns, vertical 9:16 format) "
            f"for an authentic D2C viral UGC reel featuring '{safe_title}'. "
            f"Consistent Creator: The Indian female creator from your reference start image wearing a cozy neutral outfit. Environment: {env}. "
            f"Panel 1 [Hook 0-3s]: Creator looking directly into the smartphone camera with a curious, relatable reaction, pointing at an empty or dark corner in her room. "
            f"Panel 2 [First Impression 3-5s]: Creator holding '{safe_title}' in her hand up to the camera, smiling with genuine delight at the premium build quality and finish. "
            f"Panel 3 [Feature Demo 5-8s]: Creator's hands gently demonstrating '{safe_title}' on the wooden table, activating its satisfying function or warm ambient light glow. "
            f"Panel 4 [Anchor Frame 8-11s]: Creator proudly holding '{safe_title}' beside her smiling face in sharp focus under soft warm lighting. "
            f"Panel 5 [Room Makeover 11-14s]: Wide shot of the cozy room beautifully elevated by '{safe_title}', creator sitting in the warm aesthetic glow looking thrilled. "
            f"Panel 6 [Auto-DM CTA 14-16s]: Creator smiling warmly at the camera, holding '{safe_title}', pointing down with a clean graphic sticker: 'COMMENT \"{clean_kw}\" FOR SECRET ₹50 OFF LINK 🎁'. "
            f"Hyper-realistic, identical creator face, matching clothing, and exact product design across all 6 panels. Clean comic grid borders."
        )
    else:
        storyboard_prompt = (
            f"A photorealistic, highly detailed 6-panel AI Video Storyboard Grid (2 rows by 3 columns, vertical 9:16 format) "
            f"for an aesthetic ASMR D2C viral reel featuring '{safe_title}'. "
            f"Style: {ASMR_HANDS_DESCRIPTION} Environment: {env}. "
            f"Panel 1 [Hook 0-3s]: Macro shot of the moody room corner with soft natural shadows and an aesthetic question sticker. "
            f"Panel 2 [First Touch 3-5s]: Clean manicured hands gently picking up '{safe_title}' from the table, showcasing its tactile finish. "
            f"Panel 3 [Feature Demo 5-8s]: Hands pressing the switch or operating '{safe_title}', crisp macro texture with instant satisfying light activation. "
            f"Panel 4 [Anchor Frame 8-11s]: Ultra-crisp hero shot of '{safe_title}' standing gracefully in the center, warm ambient glow illuminating the dark wood surface. "
            f"Panel 5 [Room Transformation 11-14s]: Slow smooth camera pan across the fully upgraded space, looking like a ₹50,000 Pinterest room makeover. "
            f"Panel 6 [Auto-DM CTA 14-16s]: Clean minimal end card showing '{safe_title}' with on-screen graphic pill: 'Comment \"{clean_kw}\" for the direct link + ₹50 OFF coupon'. "
            f"Hyper-realistic 8k, soft bokeh, warm Japandi aesthetic, identical product across all 6 panels."
        )

    # 2. Shot-by-Shot Prompts (Preserved for micro-editing)
    if is_female_creator:
        shot_1_prompt = (
            f"Vertical 9:16 iPhone POV shot. Natural handheld camera with subtle organic micro-jitter. "
            f"In a {env}, the Indian female creator looks directly into the lens with an authentic surprised reaction, "
            f"holding '{safe_title}'. Natural ambient room lighting, authentic social media UGC aesthetic, 24fps."
        )
        shot_2_prompt = (
            f"Vertical 9:16 medium close-up. The creator holds '{safe_title}' up to the camera lens, "
            f"smiling enthusiastically and showcasing its smooth finish. Soft natural light, stable product geometry, 24fps."
        )
        shot_3_prompt = (
            f"Vertical 9:16 slow cinematic push-in focusing on '{safe_title}' operating on the tabletop. "
            f"Warm golden ambient light softly illuminates the surrounding room decor, stable product geometry, photorealistic 24fps."
        )
        shot_4_prompt = (
            f"Vertical 9:16 smooth handheld shot. The creator holds up '{safe_title}' near camera level, smiling warmly and pointing downwards for the link. "
            f"Warm cozy ambient glow, authentic UGC aesthetic, 24fps."
        )
        bridge_prompt = (
            f"Seamless continuous camera glide moving fluidly from the creator holding '{safe_title}' "
            f"into the steady, illuminated hero shot of '{safe_title}' on the table. Natural room lighting transition, stable product geometry, 24fps."
        )
    else:
        shot_1_prompt = (
            f"Vertical 9:16 moody atmospheric macro shot of an uninspired dark room corner with '{safe_title}' on the table. "
            f"Slow continuous push-in, soft natural shadow play, realistic phone camera texture, 24fps."
        )
        shot_2_prompt = (
            f"Top-down macro perspective. Well-manicured hands gently touch and turn '{safe_title}'. "
            f"Crisp tactile touch, satisfying ASMR visual triggers, natural window light, stable product geometry, 24fps."
        )
        shot_3_prompt = (
            f"Macro product shot, slow continuous 45-degree orbit around '{safe_title}'. "
            f"Hands activate the product, warm cozy amber illumination softly lights the tabletop, ultra-stable product geometry."
        )
        shot_4_prompt = (
            f"Slow smooth camera pan across the elevated luxury Japandi aesthetic room. "
            f"Warm golden hour lighting, clean graphic pill overlay at bottom, ultra-crisp finish, 24fps."
        )
        bridge_prompt = (
            f"Smooth cinematic glide transitioning from the tactile touch directly into the fully lit aesthetic '{safe_title}' glowing on the table. 24fps."
        )

    storyboard_shots = [
        {
            "shot_number": 1,
            "timing": "0-3s",
            "name": "The Hook & Relatable Reaction",
            "start_frame_source": "Storyboard Panel 1 (or Your Custom Character Photo)",
            "camera_motion": "Handheld iPhone POV, subtle micro-jitter",
            "video_prompt": shot_1_prompt,
        },
        {
            "shot_number": 2,
            "timing": "3-6s",
            "name": "First Touch & Product Reveal",
            "start_frame_source": "Storyboard Panel 2 (Creator holding product)",
            "camera_motion": "Medium close-up push-in",
            "video_prompt": shot_2_prompt,
        },
        {
            "shot_number": 3,
            "timing": "6-11s",
            "name": "Anchor Frame Hero Demo",
            "start_frame_source": "Storyboard Panel 4 (Creator holding glowing product)",
            "camera_motion": "Steady hold on creator & product",
            "video_prompt": shot_3_prompt,
        },
        {
            "shot_number": 4,
            "timing": "11-16s",
            "name": "Room Makeover & Auto-DM CTA",
            "start_frame_source": "Storyboard Panel 5/6 (Creator holding product pointing down)",
            "camera_motion": "Warm smile & downward gesture",
            "video_prompt": shot_4_prompt,
        }
    ]

    start_end_frame_bridge = {
        "start_frame": "Storyboard Panel 1 (or Custom Character Photo)",
        "end_frame": "Storyboard Panel 4 (Product Hero Anchor Photo)",
        "bridge_prompt": bridge_prompt,
    }

    # 3. Dual-Act Video Prompts (Continuous Single-Take UGC Formula: 8s + 8s)
    if is_female_creator:
        act_1_prompt = (
            f"[ACT 1: 0 to 8 Seconds | UGC Hook & Product Showcase] "
            f"Handheld vertical 9:16 smartphone front camera POV, authentic UGC influencer video in a {env}. "
            f"The Indian female creator is holding '{safe_title}' in her hand, smiling enthusiastically at the camera. "
            f"She speaks with animated, natural expressions as if sharing a secret home hack with her best friend. "
            f"At second 4 to 6, she holds '{safe_title}' closer to the phone lens so viewers clearly see its real texture, color, and premium finish. "
            f"The camera has natural subtle handheld micro-movements, authentic room lighting, and zero CGI distortion. "
            f"At second 8, the video settles into a crystal-clear, steady ANCHOR FRAME with the creator holding '{safe_title}' beside her smiling face."
        )
        act_2_prompt = (
            f"{CONTINUITY_PROMPT} "
            f"[ACT 2: 8 to 16 Seconds | Seamless Continuation, Demo & CTA] "
            f"Continuing seamlessly from the 8-second anchor frame without cut. "
            f"Same Indian female creator in the exact same cozy room and identical outfit, holding '{safe_title}' in the exact same position beside her smile. "
            f"Maintaining exact lighting, facial features, and framing from the anchor frame. "
            f"She continues speaking naturally to the camera, tilting '{safe_title}' slightly as warm ambient light reflects softly across her room. "
            f"At second 12 to 14, she smiles warmly and points downwards with her other hand, giving a clear friendly recommendation: 'Comment \"{clean_kw}\" below to get the direct discount link!' "
            f"Natural handheld smartphone motion, perfectly locked character consistency, zero morphing, authentic UGC video ad finish."
        )
    else:
        act_1_prompt = (
            f"[ACT 1: 0 to 8 Seconds | ASMR Hook & Tactile Demo] "
            f"Vertical 9:16 macro top-down perspective on a clean wooden tabletop in a {env}. "
            f"The sleek '{safe_title}' is already resting elegantly on the surface next to aesthetic room decor. "
            f"Well-manicured hands enter the frame, gently gliding fingers over the product's premium matte texture and tapping the switch. "
            f"Warm ambient light softly turns on, casting a cozy glow on the wood. "
            f"Slow smooth camera push-in with crisp tactile sound cues, zero CGI jitter. "
            f"At second 8, settles into a steady, perfectly focused ANCHOR FRAME capturing '{safe_title}' glowing in the center of the frame."
        )
        act_2_prompt = (
            f"{CONTINUITY_PROMPT} "
            f"[ACT 2: 8 to 16 Seconds | ASMR Seamless Continuity & Room Transformation] "
            f"Continuing seamlessly from the 8-second anchor frame without cut. "
            f"Same camera angle and identical tabletop in the {env}, focusing on '{safe_title}' glowing with warm ambient light. "
            f"Maintaining exact lighting, product position, and surface reflections from the anchor frame. "
            f"The camera glides in a slow, ultra-smooth 45-degree cinematic arc around the glowing product, revealing the cozy Japandi room beautifully elevated in the soft background bokeh. "
            f"At second 13 to 16, video gently comes to a rest on a breathtaking hero shot of '{safe_title}'. "
            f"Ultra-stable product geometry, no distortion, authentic tactile ASMR aesthetic."
        )

    # 4. 16-Second Timed Voiceover Script (~35-42 words)
    vo_hinglish = (
        f"Agar aap bhi apne room ko luxury look dena chahte ho bina ₹2,000 kharche, toh look at this! "
        f"Yeh Zenlora ka '{title[:32]}' itna aesthetic hai aur sirf ₹{selling_price} mein mil raha hai. "
        f"Comment karo '{clean_kw}' aur link seedha aapke DM mein aa jayegi!"
    )
    vo_english = (
        f"Stop spending thousands on home aesthetic! This '{title[:32]}' from Zenlora completely elevates your space. "
        f"High quality, super functional, and currently under ₹{selling_price}. "
        f"Comment '{clean_kw}' below and I'll DM you the direct discounted link instantly!"
    )

    # 5. Viral On-Screen Hooks
    hooks = [
        f"POV: You found this ₹{selling_price} hidden gem for your home ✨",
        f"Stop buying basic decor 🚫 You need this in your life!",
        f"Why pay ₹{mrp} when you can get this for ₹{selling_price}? 😭",
        f"The best ₹{selling_price} investment I made for my room this year 🤎"
    ]

    # 6. Viral Instagram / Shorts Caption
    caption = (
        f"The upgrade your space desperately needed ☁️✨\n\n"
        f"Finding aesthetic home essentials under ₹{selling_price} in India is almost impossible, but '{title}' is an absolute game-changer.\n\n"
        f"⚡ Flat ₹50 Instant Discount on all UPI / GPay payments!\n"
        f"🚚 Free Express Shipping across India.\n\n"
        f"👉 Comment \"{clean_kw}\" below and our bot will instantly DM you the secret product link! 💬🔗\n\n"
        f".\n.\n"
        f"#{clean_kw.lower()} #zenlora #homedecorindia #amazonfindsindia #meeshofinds #viralreels #d2cindia #explorepage #aestheticdecor"
    )

    # 7. Trending Hashtags (Tiered)
    hashtags = (
        "#zenlora #homedecorindia #roommakeover #aestheticdecor #amazonfindsindia "
        "#meeshofinds #meeshodecor #viralreels #d2cindia #desigadgets #kitchenhacks "
        "#festivevibes #smartgadgets #exploreindia #reelsindia #trendingsongs #cozyroom"
    )

    # 8. Recommendation Algorithm Keywords (for SEO search on IG & YT)
    rec_keywords = [
        f"{title.lower()} review",
        f"best {category.lower()} under 500",
        "aesthetic room decor india",
        "cheap home decor items",
        "amazon finds india reels",
        "meesho viral products",
        f"{clean_kw.lower()} aesthetic reel",
        "zenlora store discount",
        "cozy room transformation"
    ]

    return {
        "sku": sku,
        "title": title,
        "category": category,
        "selling_price": selling_price,
        "mrp": mrp,
        "character_mode": character_mode,
        "character_description": character_desc,
        "environment": env,
        "duration_seconds": 16,
        "acts": {
            "act_1": {
                "timing": "0-8 Seconds",
                "purpose": "Hook, Pain/Curiosity, Unboxing, First Tactile Demo -> Settle on Anchor Frame",
                "prompt": act_1_prompt,
            },
            "act_2": {
                "timing": "8-16 Seconds",
                "purpose": "Seamless Continuity, Macro Quality, Full Room Transformation, Auto-DM Call To Action",
                "continuity_prompt_injected": CONTINUITY_PROMPT,
                "prompt": act_2_prompt,
            }
        },
        "storyboard_grid_prompt": storyboard_prompt,
        "storyboard_shots": storyboard_shots,
        "start_end_frame_bridge": start_end_frame_bridge,
        "voiceover_script": {
            "hinglish": vo_hinglish,
            "english": vo_english,
            "word_count": len(vo_hinglish.split()),
            "estimated_read_time": "15-16 seconds"
        },
        "hooks": hooks,
        "cta_keyword": clean_kw,
        "caption": caption,
        "hashtags": hashtags,
        "recommendation_keywords": rec_keywords,
        "store_url": (
            product.get("store_url", "").replace("https://zenlora.store", "https://www.zenlora.store")
            if product.get("store_url")
            else f"https://www.zenlora.store/product/{sku}"
        ),
        "image_url": product.get("image_url", ""),
        "images": product.get("images") or ([product.get("image_url")] if product.get("image_url") else []),
        "safe_title": safe_title,
    }
