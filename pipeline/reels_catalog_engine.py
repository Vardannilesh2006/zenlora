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
    if is_female_creator:
        storyboard_prompt = (
            f"A photorealistic, highly detailed 6-panel AI Video Storyboard Grid (2 rows by 3 columns, vertical 9:16 format) "
            f"for an aesthetic D2C viral reel featuring '{safe_title}'. "
            f"Consistent Creator: The female creator from your reference start image. Environment: {env}. "
            f"Panel 1 [Hook 0-3s]: Creator looking frustrated or shocked at a common daily problem in the room, holding her phone showing an overpriced competitor product ₹{mrp}. "
            f"Panel 2 [Price Shock 3-5s]: Creator excitedly unboxing a sleek package, pulling out '{safe_title}', on-screen graphic badge 'ZENLORA ₹{selling_price}'. "
            f"Panel 3 [Tactile Demo 5-8s]: Close-up of creator's hands actively demonstrating '{safe_title}' with instant satisfying utility or warm light glow. "
            f"Panel 4 [Anchor Frame 8-11s]: Cinematic macro close-up of '{safe_title}' in aesthetic action, warm golden bokeh highlights, premium finish. "
            f"Panel 5 [Room Makeover 11-14s]: Full wide shot of the room completely transformed, creator smiling in sheer delight at the aesthetic upgrade. "
            f"Panel 6 [Auto-DM CTA 14-16s]: Creator smiling at camera, holding the product, pointing down with a clean graphic sticker: 'COMMENT \"{clean_kw}\" FOR SECRET ₹50 OFF LINK 🎁'. "
            f"Hyper-realistic 8k, cinematic color grading, identical character and product across all 6 panels, clean comic grid border lines."
        )
    else:
        storyboard_prompt = (
            f"A photorealistic, highly detailed 6-panel AI Video Storyboard Grid (2 rows by 3 columns, vertical 9:16 format) "
            f"for an aesthetic ASMR D2C viral reel featuring '{safe_title}'. "
            f"Style: {ASMR_HANDS_DESCRIPTION} Environment: {env}. "
            f"Panel 1 [Hook 0-3s]: Macro shot of the cluttered or dark space with high-contrast moody lighting and an aesthetic question sticker. "
            f"Panel 2 [Unboxing 3-5s]: Sleek minimal packaging being opened by clean hands, peeling protective film in a satisfying ASMR motion. "
            f"Panel 3 [First Demo 5-8s]: First tactile touch - hands activating or using '{safe_title}', crisp macro texture and immediate visual feedback. "
            f"Panel 4 [Anchor Frame 8-11s]: Ultra-crisp hero shot of '{safe_title}' standing gracefully in the center, warm ambient glow illuminating the surrounding decor. "
            f"Panel 5 [Aesthetic Transformation 11-14s]: Slow smooth camera pan across the fully upgraded space, looking like a ₹50,000 Pinterest room makeover. "
            f"Panel 6 [Auto-DM CTA 14-16s]: Clean minimal end card showing '{safe_title}' with on-screen graphic pill: 'Comment \"{clean_kw}\" for the direct link + ₹50 OFF coupon'. "
            f"Hyper-realistic 8k, cinematic 35mm lens, soft bokeh, warm Japandi aesthetic, identical product across all 6 panels."
        )

    # 2. Shot-by-Shot Storyboard-to-Video Engine (Industry Best Practice for Zero Morphing)
    if is_female_creator:
        shot_1_prompt = (
            f"Vertical 9:16 iPhone POV shot. Natural handheld camera with subtle organic micro-jitter. "
            f"In a {env}, the creator looks directly into the lens with an authentic surprised reaction, "
            f"smiling warmly. Natural ambient room lighting, authentic social media UGC aesthetic, 24fps, zero plastic morphing."
        )
        shot_2_prompt = (
            f"Vertical 9:16 macro perspective on a clean surface. "
            f"Clean hands enter the frame, gently unboxing and presenting the sleek {safe_title}. "
            f"Satisfying tactile ASMR movement, soft natural daylight reflecting off the surface, stable product geometry, 4k 24fps."
        )
        shot_3_prompt = (
            f"Vertical 9:16 slow cinematic push-in focusing on {safe_title} operating on the tabletop. "
            f"Warm golden ambient light softly illuminates the surrounding room decor, subtle dust motes in the air, "
            f"stable locked-on product geometry, zero morphing, photorealistic 24fps."
        )
        shot_4_prompt = (
            f"Vertical 9:16 smooth gimbal pullback revealing the fully transformed aesthetic room. "
            f"The creator holds up {safe_title} near camera level, smiling and pointing downwards for the link. "
            f"Warm cozy ambient glow, authentic UGC aesthetic, 24fps."
        )
        bridge_prompt = (
            f"Seamless continuous camera glide moving fluidly from the creator's unboxing presentation "
            f"into the steady, illuminated hero shot of {safe_title} on the table. "
            f"Natural room lighting transition, stable product geometry, zero distortion, photorealistic 4k 24fps."
        )
    else:
        shot_1_prompt = (
            f"Vertical 9:16 moody atmospheric macro shot of an uninspired dark room corner. "
            f"Slow continuous dolly push-in, soft natural shadow play, realistic phone camera texture, 24fps."
        )
        shot_2_prompt = (
            f"Top-down macro perspective. Well-manicured hands enter frame, gently peeling packaging film and lifting {safe_title}. "
            f"Crisp tactile touch, satisfying ASMR visual triggers, natural window light, stable product geometry, 4k."
        )
        shot_3_prompt = (
            f"Macro product shot, slow continuous 45-degree orbit around {safe_title}. "
            f"Hands gently activate the product, warm cozy amber illumination softly lights the tabletop, "
            f"subtle dust particles, ultra-stable product geometry, no morphing."
        )
        shot_4_prompt = (
            f"Slow smooth camera pan across the elevated luxury Japandi aesthetic room. "
            f"Warm golden hour lighting, clean graphic pill overlay at bottom, ultra-crisp finish, 24fps."
        )
        bridge_prompt = (
            f"Smooth cinematic glide transitioning from the tactile unboxing touch directly into the fully lit aesthetic {safe_title} glowing on the table. "
            f"Natural lighting progression, stable geometry, 4k 24fps."
        )

    storyboard_shots = [
        {
            "shot_number": 1,
            "timing": "0-3s",
            "name": "The Hook & Creator Reaction",
            "start_frame_source": "Storyboard Panel 1 (or Your Custom Character Photo)",
            "camera_motion": "Handheld iPhone POV, subtle micro-jitter",
            "video_prompt": shot_1_prompt,
        },
        {
            "shot_number": 2,
            "timing": "3-6s",
            "name": "Tactile Unboxing & First Touch",
            "start_frame_source": "Storyboard Panel 2/3 (or Product Photo)",
            "camera_motion": "Top-down / 45-degree macro push-in",
            "video_prompt": shot_2_prompt,
        },
        {
            "shot_number": 3,
            "timing": "6-11s",
            "name": "Anchor Frame Hero Demo",
            "start_frame_source": "Storyboard Panel 4 (or Glowing Product Angle)",
            "camera_motion": "Slow smooth cinematic push-in",
            "video_prompt": shot_3_prompt,
        },
        {
            "shot_number": 4,
            "timing": "11-16s",
            "name": "Room Makeover & Auto-DM CTA",
            "start_frame_source": "Storyboard Panel 5/6 (or Creator holding product)",
            "camera_motion": "Smooth pullback & warm smile",
            "video_prompt": shot_4_prompt,
        }
    ]

    start_end_frame_bridge = {
        "start_frame": "Storyboard Panel 1 (or Custom Character Photo)",
        "end_frame": "Storyboard Panel 4 (Product Hero Anchor Photo)",
        "bridge_prompt": bridge_prompt,
    }

    # 3. Dual-Act Video Prompts (Preserved for 2-Clip 8s + 8s Fast Workflow)
    if is_female_creator:
        act_1_prompt = (
            f"[ACT 1: 0 to 8 Seconds | Hook & Unboxing] "
            f"Using the uploaded reference character start frame: "
            f"Natural vertical 9:16 iPhone POV shot in a {env}. The creator starts with an authentic curious hook looking towards camera, "
            f"then smoothly unboxes and presents the '{safe_title}'. "
            f"Her hands demonstrate the product's primary feature or satisfying aesthetic illumination at second 5 to 7. "
            f"The scene stabilizes and smoothly settles into an ultra-sharp steady ANCHOR FRAME at second 8, "
            f"focusing cleanly on '{safe_title}' operating in warm ambient light. Smooth handheld camera motion, 24fps, authentic UGC aesthetic."
        )
        act_2_prompt = (
            f"{CONTINUITY_PROMPT} "
            f"[ACT 2: 8 to 16 Seconds | Transformation & CTA] "
            f"Starting precisely from the steady anchor frame of '{safe_title}' in the {env}: "
            f"The camera smoothly pans back to reveal the complete aesthetic room transformation. "
            f"The creator steps into the warm golden lighting with an excited, satisfied smile. "
            f"At second 12 to 14, the creator holds the product up near camera level and gestures pointing downwards with a welcoming smile for the link. "
            f"Smooth cinematic slow-motion, soft bokeh background, 24fps, photorealistic 4k."
        )
    else:
        act_1_prompt = (
            f"[ACT 1: 0 to 8 Seconds | ASMR Hook & Tactile Demo] "
            f"Using the uploaded reference start frame: "
            f"Cinematic vertical 9:16 macro shot in a {env}. "
            f"Aesthetic hands smoothly unbox and present the sleek '{safe_title}'. "
            f"Crisp tactile product demonstration and ambient activation at second 4 to 6. "
            f"The camera pulls into a steady, perfectly focused ANCHOR FRAME at second 8, "
            f"capturing '{safe_title}' in warm amber lighting. Smooth dolly-in, 24fps, photorealistic 4k, zero faces shown."
        )
        act_2_prompt = (
            f"{CONTINUITY_PROMPT} "
            f"[ACT 2: 8 to 16 Seconds | ASMR Transformation & CTA] "
            f"Starting precisely from the steady anchor frame of '{safe_title}' in the {env}: "
            f"The camera glides in a smooth cinematic orbit around the product, showing the full room elevated into luxury aesthetic decor. "
            f"Warm golden ambient light fills the room. "
            f"At second 13 to 16, the video gently slows down on an elegant close-up of '{safe_title}'. Smooth gimbal pan, 24fps, photorealistic 4k."
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
