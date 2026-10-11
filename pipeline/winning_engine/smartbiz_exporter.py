"""
SmartBiz by Amazon Bulk Product Listing Exporter (v10 Template)
===============================================================
Generates 100% upload-ready CSV UTF-8 files strictly adhering to:
- `smartbiz_bulk_upload_template_v10.xlsx` (`important_instructions`, `bulk_upload_template`, `DataSheet`)
- Exact 52 column headers (`A1:AZ1`) without modification.
- Zero cross-category Product Category collision across Business Categories.
- Automatic Shopify `.webp?v=...` -> `.jpg` image sanitization across up to 6 gallery images.
- Strict MRP > Selling Price numeric validation and character limit enforcement.
"""

import csv
import html
import io
import re
from typing import Dict, List, Optional, Tuple

from .radar_controller import get_winners

# Exact 52 column headers from `smartbiz_bulk_upload_template_v10.xlsx` -> `bulk_upload_template` Row 1 (A1:AZ1)
EXACT_SMARTBIZ_HEADERS: List[str] = [
    "SKU ID (Not to be Edited)",
    "Variant ID (Not to be Edited)",
    "Variant Feature 1 ID ( Not to be edited)",
    "Variant Feature 2 ID ( Not to be edited)",
    "Variant Feature 3 ID ( Not to be edited)",
    "Custom SKU (Optional) Maximum 40 characters",
    "Product Name (Mandatory) Maximum 200 characters",
    "MRP (Mandatory) Number only",
    "Selling Price (Optional) Number only Should be less than MRP",
    "Business Category (Mandatory) Select from Dropdown",
    "Product Category (Mandatory)",
    "Product Description (Optional) Maximum 2000 characters",
    "Variant Relationship (Optional)",
    "Variant Feature 1 (Optional)",
    "Variant Value 1 (Optional)",
    "Variant Feature 2 (Optional)",
    "Variant Value 2 (Optional)",
    "Variant Feature 3 (Optional)",
    "Variant Value 3 (Optional)",
    "Color Code (Optional) Maximum 7 characters",
    "Best Seller (Optional)",
    "HSN Code (Optional)",
    "Product Image1 (Optional)",
    "Product Image2 (Optional)",
    "Product Image3 (Optional)",
    "Product Image4 (Optional)",
    "Product Image5 (Optional)",
    "Product Image6 (Optional)",
    "Size Guide (Optional)",
    "SEOMeta Title (Optional)",
    "SEOMeta Description (Optional)",
    "SEOMeta ImageUrl (Optional)",
    "Custom Attribute Key 1 (Optional)",
    "Custom Attribute Value 1 (Optional)",
    "Custom Attribute Key 2 (Optional)",
    "Custom Attribute Value 2 (Optional)",
    "Custom Attribute Key 3 (Optional)",
    "Custom Attribute Value 3 (Optional)",
    "Custom Attribute Key 4 (Optional)",
    "Custom Attribute Value 4 (Optional)",
    "Custom Attribute Key 5 (Optional)",
    "Custom Attribute Value 5 (Optional)",
    "Custom Attribute Key 6 (Optional)",
    "Custom Attribute Value 6 (Optional)",
    "Custom Attribute Key 7 (Optional)",
    "Custom Attribute Value 7 (Optional)",
    "Custom Attribute Key 8 (Optional)",
    "Custom Attribute Value 8 (Optional)",
    "Custom Attribute Key 9 (Optional)",
    "Custom Attribute Value 9 (Optional)",
    "Custom Attribute Key 10 (Optional)",
    "Custom Attribute Value 10 (Optional)",
]

# Official 21 Business Categories from `DataSheet` Row 2
OFFICIAL_BUSINESS_CATEGORIES = {
    "CLOTHING",
    "FOOTWEAR",
    "WATCHES",
    "JEWELRY",
    "LUGGAGE_AND_BAGS",
    "BEAUTY_AND_PERSONAL_CARE",
    "HOME_AND_KITCHEN",
    "FOOD_AND_GROCERY",
    "HOME_CARE",
    "BOOKS_AND_STATIONARY",
    "BABY",
    "TOYS_AND_GAMES",
    "ELECTRONICS",
    "APPLIANCES",
    "SPORTS_AND_FITNESS",
    "FURNITURE",
    "HEALTH_SUPPLIEMENTS",
    "LAWN_AND_GARDEN",
    "PET_PRODUCTS",
    "MULTIPURPOSE",
    "GENERAL",
}

NICHE_CODE_MAP = {
    "Festive": "FEST",
    "Kitchen": "KITC",
    "Home Decor": "DECO",
    "Gadgets": "GADG",
    "Gifts": "GIFT",
}


def sanitize_smartbiz_image_url(url: Optional[str]) -> str:
    """
    SmartBiz requires direct image links ending in .jpg, .jpeg, or .png.
    DeoDap/Shopify CDN links often end in .webp?v=171... which can fail SmartBiz validation.
    This function strips query parameters and converts Shopify .webp extensions to .jpg.
    """
    if not url or not isinstance(url, str):
        return ""
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return ""
    # Strip query string (?v=...) and fragment
    cleaned = cleaned.split("?")[0].split("#")[0]
    # Convert .webp to .jpg (Shopify CDN natively serves .jpg when extension is changed)
    if cleaned.lower().endswith(".webp"):
        cleaned = cleaned[:-5] + ".jpg"
    elif not cleaned.lower().endswith((".jpg", ".jpeg", ".png")):
        # If no standard extension is present on a Shopify URL, append .jpg
        if "cdn.shopify.com" in cleaned.lower():
            cleaned = cleaned + ".jpg"
    return cleaned


def extract_product_images(product: Dict) -> List[str]:
    """
    Extracts up to 6 unique, sanitized .jpg/.png image URLs for Product Image1..6.
    """
    candidates: List[str] = []
    primary = product.get("primary_image") or product.get("image_url") or ""
    if primary:
        candidates.append(primary)

    raw_images = product.get("images") or []
    if isinstance(raw_images, list):
        for img in raw_images:
            if isinstance(img, str):
                candidates.append(img)
            elif isinstance(img, dict) and img.get("src"):
                candidates.append(img["src"])

    seen = set()
    sanitized_list: List[str] = []
    for raw_url in candidates:
        clean_url = sanitize_smartbiz_image_url(raw_url)
        if clean_url and clean_url not in seen:
            seen.add(clean_url)
            sanitized_list.append(clean_url)
            if len(sanitized_list) >= 6:
                break

    # Pad to 6 elements with empty strings
    while len(sanitized_list) < 6:
        sanitized_list.append("")
    return sanitized_list


def map_smartbiz_categories(product: Dict) -> Tuple[str, str]:
    """
    Maps a Zenlora product to its official SmartBiz (Business Category, Product Category) pair
    from `DataSheet`.
    Strictly enforces `important_instructions` Row 17:
    "Please remember not to create product categories with the same name in different business categories."
    Every Business Category below uses mutually exclusive Product Category names.
    """
    niche = str(product.get("niche") or product.get("primary_category") or "Home Decor").strip()
    title_lower = str(product.get("title") or "").lower()
    mood_lower = str(product.get("festival_mood") or "").lower()
    combined = f"{title_lower} {mood_lower}"

    if niche == "Festive":
        # Check if cleaning utility
        if any(
            kw in combined
            for kw in (
                "brush",
                "mop",
                "scrub",
                "wiper",
                "microfiber",
                "cleaner",
                "cleaning",
                "duster",
                "sponge",
                "lint",
                "broom",
            )
        ):
            return ("HOME_CARE", "Mops, Brushes & Scrubs")
        # Check if Pooja / traditional festive item
        if any(
            kw in combined
            for kw in (
                "pooja",
                "puja",
                "diya",
                "kalash",
                "thali",
                "agarbatti",
                "dhoop",
                "incense",
                "camphor",
                "kapoor",
                "shankh",
                "bell",
                "toran",
                "rangoli",
                "shubh",
                "labh",
                "swastik",
                "om ",
                "jyot",
                "batti",
                "kumkum",
                "haldi",
                "chandan",
            )
        ):
            return ("HOME_CARE", "Pooja essentials")
        # Otherwise Festive LED / String Lights / Decor Lighting
        return ("HOME_AND_KITCHEN", "Lighting")

    if niche == "Kitchen":
        if any(
            kw in combined
            for kw in ("rack", "organizer", "storage", "shelf", "holder", "container", "jar", "basket", "hook")
        ):
            return ("HOME_AND_KITCHEN", "Home storage and Organization")
        return ("HOME_AND_KITCHEN", "Kitchen & Dining")

    if niche == "Home Decor":
        if any(kw in combined for kw in ("light", "lamp", "led", "lantern", "neon", "bulb", "string")):
            return ("HOME_AND_KITCHEN", "Lighting")
        if any(kw in combined for kw in ("rack", "organizer", "storage", "shelf", "hook", "hanger")):
            return ("HOME_AND_KITCHEN", "Home storage and Organization")
        return ("HOME_AND_KITCHEN", "Home Decor")

    if niche == "Gadgets":
        return ("ELECTRONICS", "Other Electronics")

    if niche == "Gifts":
        return ("MULTIPURPOSE", "General")

    return ("HOME_AND_KITCHEN", "Home Decor")


def _clean_text(text: str) -> str:
    """Removes HTML tags and normalizes whitespace."""
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", str(text))
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def build_smartbiz_custom_sku(product: Dict, index: int) -> str:
    """
    Builds a unique Custom SKU <= 40 characters.
    Uses cleaned supplier SKU if available, prefixed with ZEN-, or generates a deterministic SKU.
    """
    niche = str(product.get("niche") or "Home Decor")
    niche_code = NICHE_CODE_MAP.get(niche, "ZENL")
    raw_sku = str(product.get("sku") or "").strip()
    handle = str(product.get("handle") or f"item-{index}").strip()

    if raw_sku and raw_sku.lower() not in ("none", "null", "n/a"):
        clean_sku = re.sub(r"[^A-Za-z0-9\-_]", "", raw_sku).upper()
        candidate = f"ZEN-{clean_sku}"
    else:
        slug_part = re.sub(r"[^A-Za-z0-9]", "", handle).upper()[:18]
        candidate = f"ZEN-{niche_code}-{index:03d}-{slug_part}"

    return candidate[:40]


def build_smartbiz_product_name(product: Dict) -> str:
    """
    Returns mandatory Product Name strictly <= 200 characters.
    """
    raw_title = str(product.get("zenlora_title") or product.get("title") or "Zenlora Utility Product").strip()
    clean_title = _clean_text(raw_title)
    if not clean_title:
        clean_title = "Zenlora Home & Kitchen Utility Product"
    return clean_title[:200]


def calculate_smartbiz_prices(product: Dict) -> Tuple[int, int]:
    """
    Returns (mrp, selling_price) as positive integers satisfying SmartBiz validation:
    AND(I2<=H2, ISNUMBER(I2), I2>=0) and AND(ISNUMBER(H2), H2>0, H2<=999999.99)
    where H = MRP and I = Selling Price.
    """
    raw_sp = product.get("selling_price") or 399
    try:
        selling_price = int(round(float(raw_sp)))
    except (ValueError, TypeError):
        selling_price = 399

    if selling_price <= 0:
        selling_price = 399

    raw_mrp = product.get("compare_at_price") or product.get("mrp") or 0
    try:
        mrp = int(round(float(raw_mrp)))
    except (ValueError, TypeError):
        mrp = 0

    # Ensure MRP is strictly greater than Selling Price with attractive Indian retail pricing (ending in 99)
    if mrp <= selling_price:
        computed = max(selling_price + 200, int(round(selling_price * 1.75)))
        mrp = (computed // 100) * 100 + 99
        if mrp <= selling_price:
            mrp = selling_price + 200

    return (mrp, selling_price)


def build_smartbiz_html_description(product: Dict) -> str:
    """
    Generates a clean, high-conversion HTML product description strictly <= 2000 characters.
    Combines real supplier specifications with structured HTML bullet points.
    """
    title = html.escape(build_smartbiz_product_name(product))
    niche = html.escape(str(product.get("niche") or "Home & Kitchen"))
    festival_mood = str(product.get("festival_mood") or "").strip()
    raw_desc = _clean_text(str(product.get("description") or product.get("body_html") or ""))

    bullets = []
    if raw_desc:
        # Split sentences for clean readability
        sentences = [s.strip() for s in re.split(r"[.!?•\n]+", raw_desc) if len(s.strip()) > 12]
        for s in sentences[:5]:
            bullets.append(html.escape(s[:180]))

    if not bullets:
        bullets = [
            f"Premium quality {title} designed for everyday Indian households.",
            "Compact, durable, and easy-to-use utility design with zero installation hassle.",
            "Ideal for daily convenience, home organization, and festive gifting.",
        ]

    weight_g = product.get("weight_grams")
    if weight_g:
        bullets.append(f"Lightweight & Sturdy Build: Approx. {int(float(weight_g))}g transit-safe construction.")

    if festival_mood and festival_mood.lower() not in ("none", "general", "all"):
        bullets.append(f"Special Utility & Occasion: {html.escape(festival_mood)}.")

    bullets.append("Quality Checked & Dispatched across India with secure transit packaging.")

    li_html = "".join(f"<li>{b}</li>" for b in bullets)
    html_desc = (
        f"<p><strong>{title}</strong> — Curated by Zenlora for {niche}.</p>"
        f"<ul>{li_html}</ul>"
        f"<p><b>Fast Pan-India Delivery:</b> Dispatched within 24–48 hours with 4–8 business days delivery.</p>"
    )

    if len(html_desc) > 2000:
        html_desc = html_desc[:1993] + "</p>"
    return html_desc


def build_seo_metadata(product: Dict, primary_image_url: str) -> Tuple[str, str, str]:
    """
    Generates (SEOMeta Title <= 60 chars, SEOMeta Description <= 160 chars, SEOMeta ImageUrl).
    """
    name = build_smartbiz_product_name(product)
    mrp, sp = calculate_smartbiz_prices(product)
    niche = str(product.get("niche") or "Home Utility")

    # SEOMeta Title (strictly <= 60 chars)
    suffix = " | Zenlora India"
    if len(name) + len(suffix) <= 60:
        seo_title = f"{name}{suffix}"
    else:
        seo_title = name[:60].strip()

    # SEOMeta Description (strictly <= 160 chars)
    raw_desc = _clean_text(str(product.get("description") or ""))
    base_snippet = raw_desc[:75].strip() if raw_desc else f"Shop {name[:55]} online at Zenlora."
    seo_desc = f"Buy {name[:48]} at Rs.{sp} (MRP Rs.{mrp}). {base_snippet} Free Pan-India Delivery."
    seo_desc = re.sub(r"\s+", " ", seo_desc).strip()[:160]

    return (seo_title[:60], seo_desc[:160], primary_image_url)


def product_to_smartbiz_row(product: Dict, index: int = 1) -> List[str]:
    """
    Converts a single Zenlora product dictionary into an exact 52-column row
    matching `smartbiz_bulk_upload_template_v10.xlsx` (`bulk_upload_template` A..AZ).
    """
    custom_sku = build_smartbiz_custom_sku(product, index)
    product_name = build_smartbiz_product_name(product)
    mrp, selling_price = calculate_smartbiz_prices(product)
    business_cat, product_cat = map_smartbiz_categories(product)
    html_description = build_smartbiz_html_description(product)

    score = float(product.get("winning_score") or 0)
    best_seller = "Yes" if score >= 60.0 else ""

    raw_hsn = str(product.get("hsn_code") or "").strip()
    hsn_code = re.sub(r"[^0-9]", "", raw_hsn)[:8] if raw_hsn else ""

    images = extract_product_images(product)
    seo_title, seo_desc, seo_img = build_seo_metadata(product, images[0])

    niche_label = str(product.get("niche") or "Home & Kitchen")
    festival_mood = str(product.get("festival_mood") or "").strip()
    collection_val = f"{niche_label} ({festival_mood})" if festival_mood else niche_label

    row = [
        "",                     # 1. A: SKU ID (Not to be Edited)
        "",                     # 2. B: Variant ID (Not to be Edited)
        "",                     # 3. C: Variant Feature 1 ID ( Not to be edited)
        "",                     # 4. D: Variant Feature 2 ID ( Not to be edited)
        "",                     # 5. E: Variant Feature 3 ID ( Not to be edited)
        custom_sku[:40],        # 6. F: Custom SKU (Optional) Maximum 40 characters
        product_name[:200],     # 7. G: Product Name (Mandatory) Maximum 200 characters
        str(mrp),               # 8. H: MRP (Mandatory) Number only
        str(selling_price),     # 9. I: Selling Price (Optional) Number only Should be less than MRP
        business_cat,           # 10. J: Business Category (Mandatory) Select from Dropdown
        product_cat[:100],      # 11. K: Product Category (Mandatory)
        html_description[:2000],# 12. L: Product Description (Optional) Maximum 2000 characters
        "",                     # 13. M: Variant Relationship (Optional) -> Blank = Standalone Product
        "",                     # 14. N: Variant Feature 1 (Optional)
        "",                     # 15. O: Variant Value 1 (Optional)
        "",                     # 16. P: Variant Feature 2 (Optional)
        "",                     # 17. Q: Variant Value 2 (Optional)
        "",                     # 18. R: Variant Feature 3 (Optional)
        "",                     # 19. S: Variant Value 3 (Optional)
        "",                     # 20. T: Color Code (Optional) Maximum 7 characters
        best_seller,            # 21. U: Best Seller (Optional)
        hsn_code,               # 22. V: HSN Code (Optional)
        images[0],              # 23. W: Product Image1 (Optional)
        images[1],              # 24. X: Product Image2 (Optional)
        images[2],              # 25. Y: Product Image3 (Optional)
        images[3],              # 26. Z: Product Image4 (Optional)
        images[4],              # 27. AA: Product Image5 (Optional)
        images[5],              # 28. AB: Product Image6 (Optional)
        "",                     # 29. AC: Size Guide (Optional)
        seo_title[:60],         # 30. AD: SEOMeta Title (Optional)
        seo_desc[:160],         # 31. AE: SEOMeta Description (Optional)
        seo_img,                # 32. AF: SEOMeta ImageUrl (Optional)
        "Country of Origin",    # 33. AG: Custom Attribute Key 1 (Optional)
        "India",                # 34. AH: Custom Attribute Value 1 (Optional)
        "Delivery Timeline",    # 35. AI: Custom Attribute Key 2 (Optional)
        "4-8 Business Days (Free Pan-India Shipping)",  # 36. AJ: Custom Attribute Value 2 (Optional)
        "Return & Replacement", # 37. AK: Custom Attribute Key 3 (Optional)
        "Easy Replacement for Damaged or Defective Transit Items",  # 38. AL: Custom Attribute Value 3 (Optional)
        "Collection & Utility", # 39. AM: Custom Attribute Key 4 (Optional)
        collection_val[:1000],  # 40. AN: Custom Attribute Value 4 (Optional)
        "",                     # 41. AO: Custom Attribute Key 5 (Optional)
        "",                     # 42. AP: Custom Attribute Value 5 (Optional)
        "",                     # 43. AQ: Custom Attribute Key 6 (Optional)
        "",                     # 44. AR: Custom Attribute Value 6 (Optional)
        "",                     # 45. AS: Custom Attribute Key 7 (Optional)
        "",                     # 46. AT: Custom Attribute Value 7 (Optional)
        "",                     # 47. AU: Custom Attribute Key 8 (Optional)
        "",                     # 48. AV: Custom Attribute Value 8 (Optional)
        "",                     # 49. AW: Custom Attribute Key 9 (Optional)
        "",                     # 50. AX: Custom Attribute Value 9 (Optional)
        "",                     # 51. AY: Custom Attribute Key 10 (Optional)
        "",                     # 52. AZ: Custom Attribute Value 10 (Optional)
    ]
    assert len(row) == 52, f"Expected 52 columns, got {len(row)}"
    return row


def select_current_page_products(
    niche: str = "All",
    batch_cursor: int = 0,
    limit: int = 20,
    include_hard_failed: bool = False,
) -> List[Dict]:
    """
    Mode A (Current Page / Category Batch):
    - When viewing a specific category tab (e.g. Festive, Kitchen, Home Decor, Gadgets, Gifts),
      selects up to `limit` (default 20) products from that category rotated by `batch_cursor`.
    - When viewing 'All', selects the top `limit` (default 20) products from the current rotated page.
    """
    if niche and niche != "All":
        items = get_winners(
            niche=niche,
            include_hard_failed=include_hard_failed,
            refresh_dynamic=True,
            batch_cursor=batch_cursor,
            per_niche_display=limit,
        )
        return items[:limit]

    # For "All", get the rotated page across all niches and take top `limit` (20) items
    items = get_winners(
        niche="All",
        include_hard_failed=include_hard_failed,
        refresh_dynamic=True,
        batch_cursor=batch_cursor,
        per_niche_display=12,
    )
    items_sorted = sorted(items, key=lambda x: float(x.get("winning_score") or 0), reverse=True)
    return items_sorted[:limit]


def select_smart_mix_products(
    total_count: int = 55,
    batch_cursor: int = 0,
) -> List[Dict]:
    """
    Mode B (Smart 50-60 Mix Across All 5 Categories):
    Selects a balanced mix of `total_count` (default 55 = 11 per category across all 5 categories:
    Festive, Kitchen, Home Decor, Gadgets, Gifts), excluding hard-failed items.
    """
    categories = ["Festive", "Kitchen", "Home Decor", "Gadgets", "Gifts"]
    per_cat = max(1, total_count // len(categories))  # 11 per category for total_count=55

    mixed: List[Dict] = []
    seen_handles = set()

    for cat in categories:
        cat_items = get_winners(
            niche=cat,
            include_hard_failed=False,
            refresh_dynamic=True,
            batch_cursor=batch_cursor,
            per_niche_display=per_cat + 5,
        )
        added = 0
        for item in cat_items:
            h = item.get("handle")
            if h and h not in seen_handles and not item.get("is_hard_failed", False):
                seen_handles.add(h)
                mixed.append(item)
                added += 1
                if added >= per_cat:
                    break

    # If any category had fewer than `per_cat` non-hard-failed items, top up from remaining pool
    if len(mixed) < total_count:
        all_pool = get_winners(
            niche="All",
            include_hard_failed=False,
            refresh_dynamic=True,
            batch_cursor=batch_cursor,
            per_niche_display=0,
        )
        for item in all_pool:
            h = item.get("handle")
            if h and h not in seen_handles and not item.get("is_hard_failed", False):
                seen_handles.add(h)
                mixed.append(item)
                if len(mixed) >= total_count:
                    break

    return mixed[:total_count]


def generate_smartbiz_csv_bytes(products: List[Dict]) -> bytes:
    """
    Generates a CSV UTF-8 (Comma delimited) (*.csv) byte stream with the exact 52 column headers
    from `smartbiz_bulk_upload_template_v10.xlsx`.
    Ensures every Custom SKU in the batch is 100% unique.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(EXACT_SMARTBIZ_HEADERS)

    used_skus = set()
    for idx, prod in enumerate(products, start=1):
        row = product_to_smartbiz_row(prod, index=idx)
        sku = row[5]
        if sku in used_skus:
            suffix = f"-{idx}"
            sku = f"{sku[:40 - len(suffix)]}{suffix}"
            row[5] = sku
        used_skus.add(sku)
        writer.writerow(row)

    # Encode as UTF-8 with BOM (standard Excel "CSV UTF-8 (Comma delimited) (*.csv)" encoding)
    return output.getvalue().encode("utf-8-sig")
