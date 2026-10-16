import os
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

EXCEL_CATALOG_NAME = "zenlora_catalog_642_products_FIXED_READY_TO_UPLOAD.xlsx"
EXCEL_PATH = BASE_DIR / EXCEL_CATALOG_NAME
RUNTIME_CATALOG_JSON = DATA_DIR / "catalog_642.json"
REPO_CATALOG_JSON = BASE_DIR / "data" / "catalog_642.json"

RUNTIME_LEDGER_FILE = DATA_DIR / "reels_done_ledger.json"
REPO_LEDGER_FILE = BASE_DIR / "data" / "reels_done_ledger.json"

_CATALOG_MEM_CACHE: Dict[str, Any] = {"mtime": 0.0, "products": None, "by_sku": {}}
_LEDGER_MEM_CACHE: Dict[str, Any] = {"mtime": 0.0, "data": None}


def _get_excel_mtime() -> float:
    if EXCEL_PATH.exists():
        try:
            return EXCEL_PATH.stat().st_mtime
        except Exception:
            return 0.0
    return 0.0


def _build_json_from_excel() -> List[Dict[str, Any]]:
    """Parse Excel catalog into structured JSON."""
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

            # Derive clean URL slug / handle
            handle = sku.lower().replace(" ", "-").replace("_", "-")

            products.append({
                "id": f"zen_{idx+1}",
                "sku": sku,
                "handle": handle,
                "title": title,
                "mrp": mrp,
                "selling_price": selling_price,
                "category": category,
                "description": desc,
                "image_url": image_url,
                "images": images,
                "discount_pct": disc_pct,
                "seo_title": str(row.get("SEOMeta Title (Optional)") or "") if pd.notna(row.get("SEOMeta Title (Optional)")) else "",
                "seo_description": str(row.get("SEOMeta Description (Optional)") or "") if pd.notna(row.get("SEOMeta Description (Optional)")) else "",
                "store_url": f"https://zenlora.store/search?q={sku}",
            })
        
        # Save to runtime and repo JSON for lightning-fast loads
        for target in (RUNTIME_CATALOG_JSON, REPO_CATALOG_JSON):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(products, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        return products
    except Exception as e:
        print(f"[reels_catalog_engine] Error parsing Excel: {e}")
        return []


def load_catalog(force_reload: bool = False) -> List[Dict[str, Any]]:
    """Loads all catalog products with auto-sync from Excel or fast JSON cache."""
    excel_mtime = _get_excel_mtime()
    
    # Check if in-memory cache is valid
    if (
        not force_reload
        and _CATALOG_MEM_CACHE["products"] is not None
        and _CATALOG_MEM_CACHE["mtime"] >= excel_mtime
    ):
        return _CATALOG_MEM_CACHE["products"]

    # Determine whether we need to parse Excel
    needs_excel_parse = False
    json_path_to_use = None
    for p in (RUNTIME_CATALOG_JSON, REPO_CATALOG_JSON):
        if p.exists():
            json_path_to_use = p
            break

    if EXCEL_PATH.exists():
        if json_path_to_use is None:
            needs_excel_parse = True
        else:
            try:
                if excel_mtime > json_path_to_use.stat().st_mtime:
                    needs_excel_parse = True
            except Exception:
                needs_excel_parse = True

    products = []
    if needs_excel_parse:
        products = _build_json_from_excel()

    if not products and json_path_to_use and json_path_to_use.exists():
        try:
            with open(json_path_to_use, "r", encoding="utf-8") as f:
                products = json.load(f)
        except Exception:
            products = []

    # Final fallback to products_db.json if nothing else found
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
                            "seo_title": p.get("seo_title", ""),
                            "seo_description": p.get("seo_description", ""),
                            "store_url": f"https://zenlora.store/search?q={p.get('sku', '')}",
                        })
            except Exception:
                pass

    by_sku = {p["sku"]: p for p in products if p.get("sku")}
    _CATALOG_MEM_CACHE["mtime"] = max(excel_mtime, time.time())
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

FEMALE_CREATOR_DESCRIPTION = (
    "A charismatic, expressive Indian woman in her mid-20s, wearing an elegant neutral modern pastel kurta, "
    "with natural hair and warm expressive facial reactions. Genuine relatable Indian D2C creator persona."
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
    - Act 1 Video Prompt (0-8s: Hook & First Demo)
    - Act 2 Video Prompt (8-16s: Continuity Injection + Makeover + Auto-DM CTA)
    - 16s Timed Voiceover Script (Hinglish + English)
    - Viral On-Screen Hooks
    - High-Converting Instagram/Shorts Caption
    - High-Intent Auto-DM Trigger Keyword
    - Trending Hashtags & Algorithmic Search Keywords
    """
    title = product.get("title", "Zenlora Luxury Product").replace("Zenlora™", "").strip()
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
        env = "modern Indian Japandi modular kitchen with clean white quartz countertop and warm recessed under-cabinet lighting"
    elif "festive" in category.lower() or "light" in title_lower:
        env = "warm festive Indian living room decorated with fresh marigold flowers, soft brass accents, and glowing fairy lights"
    elif "smart" in category.lower() or "gadget" in title_lower:
        env = "minimalist aesthetic dark oak study desk setup with ambient warm backlighting and clean cordless vibe"
    else:
        env = "aesthetic cozy Japandi room corner with textured beige linen, warm floor lamp glow, and soft natural indoor lighting"

    # 1. 6-Panel Storyboard Grid Prompt
    if is_female_creator:
        storyboard_prompt = (
            f"A photorealistic, highly detailed 6-panel AI Video Storyboard Grid (2 rows by 3 columns, vertical 9:16 format) "
            f"for an Indian D2C viral reel featuring '{title}'. "
            f"Consistent Creator: {FEMALE_CREATOR_DESCRIPTION} Environment: {env}. "
            f"Panel 1 [Hook 0-3s]: Creator looking frustrated or shocked at a common daily problem in the room, holding her phone showing an overpriced competitor product ₹{mrp}. "
            f"Panel 2 [Price Shock 3-5s]: Creator excitedly unboxing a sleek brown package, pulling out the pristine '{title}', on-screen graphic badge 'ZENLORA ₹{selling_price}'. "
            f"Panel 3 [Tactile Demo 5-8s]: Close-up of creator's hands actively demonstrating how '{title}' works with instant satisfying utility or light activation. "
            f"Panel 4 [Anchor Frame 8-11s]: Cinematic macro close-up of '{title}' in pristine aesthetic action, warm golden bokeh highlights, premium finish. "
            f"Panel 5 [Room Makeover 11-14s]: Full wide shot of the room completely transformed, creator smiling in sheer delight at the aesthetic upgrade. "
            f"Panel 6 [Auto-DM CTA 14-16s]: Creator smiling at camera, holding the product, pointing down with a clean graphic sticker: 'COMMENT \"{clean_kw}\" FOR SECRET ₹50 OFF LINK 🎁'. "
            f"Hyper-realistic 8k, cinematic color grading, identical character and product across all 6 panels, clean comic grid border lines."
        )
    else:
        storyboard_prompt = (
            f"A photorealistic, highly detailed 6-panel AI Video Storyboard Grid (2 rows by 3 columns, vertical 9:16 format) "
            f"for an aesthetic ASMR D2C viral reel featuring '{title}'. "
            f"Style: {ASMR_HANDS_DESCRIPTION} Environment: {env}. "
            f"Panel 1 [Hook 0-3s]: Macro shot of the cluttered or dark space with high-contrast moody lighting and an aesthetic question sticker. "
            f"Panel 2 [Unboxing 3-5s]: Sleek minimal packaging being opened by clean hands, peeling protective film in a satisfying ASMR motion. "
            f"Panel 3 [First Demo 5-8s]: First tactile touch - hands activating or using '{title}', crisp macro texture and immediate visual feedback. "
            f"Panel 4 [Anchor Frame 8-11s]: Ultra-crisp hero shot of '{title}' standing gracefully in the center, warm ambient glow illuminating the surrounding decor. "
            f"Panel 5 [Aesthetic Transformation 11-14s]: Slow smooth camera pan across the fully upgraded space, looking like a ₹50,000 Pinterest room makeover. "
            f"Panel 6 [Auto-DM CTA 14-16s]: Clean minimal end card showing '{title}' with on-screen graphic pill: 'Comment \"{clean_kw}\" for the direct link + ₹50 OFF coupon'. "
            f"Hyper-realistic 8k, cinematic 35mm lens, soft bokeh, warm Japandi aesthetic, identical product across all 6 panels."
        )

    # 2. Act 1 Video Prompt (0–8s: Hook & Unboxing)
    if is_female_creator:
        act_1_prompt = (
            f"[ACT 1: 0 to 8 Seconds | Hook & Unboxing] "
            f"Cinematic vertical 9:16 video. In a {env}, {FEMALE_CREATOR_DESCRIPTION} "
            f"starts with an expressive 2-second hook looking straight at the camera with genuine curiosity/frustration, "
            f"then quickly transitions to unboxing '{title}'. Her hands smoothly lift the product, showing its sleek build. "
            f"At second 5 to 7, she demonstrates the primary satisfying feature or clicks it on. "
            f"The scene stabilizes and smoothly settles into an ultra-sharp steady ANCHOR FRAME at second 8, "
            f"focusing cleanly on '{title}' operating in warm ambient light. Smooth handheld camera motion, 24fps, photorealistic 4k."
        )
    else:
        act_1_prompt = (
            f"[ACT 1: 0 to 8 Seconds | ASMR Hook & Tactile Demo] "
            f"Cinematic vertical 9:16 video. In a {env}, {ASMR_HANDS_DESCRIPTION} "
            f"starts with a slow macro push-in on an ordinary space, then hands enter the frame holding the sleek '{title}'. "
            f"Crisp tactile unboxing and immediate activation at second 4 to 6. "
            f"The camera pulls into a steady, perfectly focused ANCHOR FRAME at second 8, "
            f"capturing the product glowing or working with soft dust motes in warm amber lighting. Smooth dolly-in, 24fps, photorealistic 4k."
        )

    # 3. Act 2 Video Prompt (8–16s: Continuity + Makeover + CTA)
    if is_female_creator:
        act_2_prompt = (
            f"{CONTINUITY_PROMPT} "
            f"[ACT 2: 8 to 16 Seconds | Transformation & CTA] "
            f"Starting exactly from the steady anchor frame of '{title}' in the {env}, "
            f"the camera smoothly pulls back to reveal the complete breathtaking room transformation. "
            f"The Indian female creator steps into the warm golden lighting with an excited, satisfied smile. "
            f"At second 12 to 14, she holds the product up near camera level, smiles directly into the lens, "
            f"and gestures pointing downwards with a welcoming smile. A clean graphical on-screen sticker appears reading: "
            f"'Comment \"{clean_kw}\" to get the link in your DM!'. Cinematic slow-motion, soft bokeh background, 24fps, photorealistic 4k."
        )
    else:
        act_2_prompt = (
            f"{CONTINUITY_PROMPT} "
            f"[ACT 2: 8 to 16 Seconds | ASMR Transformation & CTA] "
            f"Starting exactly from the steady anchor frame of '{title}' in the {env}, "
            f"the camera glides in a smooth cinematic orbit around the product, showing the full room elevated into luxury Pinterest aesthetic. "
            f"Warm golden hour rays or cozy ambient LED glow fill the room. "
            f"At second 13 to 16, the video gently slows down on an elegant close-up with clean graphic text overlay: "
            f"'Comment \"{clean_kw}\" for instant link & ₹50 discount'. Smooth gimbal pan, 24fps, photorealistic 4k."
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
        "store_url": product.get("store_url", f"https://zenlora.store/search?q={sku}"),
        "image_url": product.get("image_url", "")
    }
