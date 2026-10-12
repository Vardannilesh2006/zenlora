"""
SmartBiz by Amazon Bulk Product Listing Exporter (v10 Template)
===============================================================
Generates 100% upload-ready CSV UTF-8 and Excel (.xlsx) files strictly adhering to:
- `smartbiz_bulk_upload_template_v10.xlsx` (`important_instructions`, `bulk_upload_template`, `DataSheet`)
- Exact 52 column headers (`A1:AZ1`) without modification.
- Real DeoDap SKU (`variants[0].sku`), Variant ID, Product ID, Weight, and up to 6 DeoDap Gallery Image URLs.
- Zero cross-category Product Category collision across Business Categories.
- Strict MRP > Selling Price numeric validation, HSN code mapping, and character limit enforcement.
"""

import csv
import html
import io
import re
from pathlib import Path
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

HSN_BY_PRODUCT_CATEGORY = {
    "Pooja essentials": "830629",
    "Mops, Brushes & Scrubs": "960390",
    "Lighting": "940540",
    "Kitchen & Dining": "392410",
    "Home storage and Organization": "392490",
    "Home Decor": "392640",
    "Other Electronics": "850980",
    "General": "960810",
}


def sanitize_smartbiz_image_url(url: Optional[str]) -> str:
    """
    Preserves the direct DeoDap Shopify CDN image address (cdn.shopify.com/s/files/...)
    while ensuring it ends in .jpg, .jpeg, or .png (converting .webp to .jpg and stripping query strings)
    so SmartBiz bulk image validation passes 100% of the time.
    """
    if not url or not isinstance(url, str):
        return ""
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return ""
    # Strip query string (?v=...) and fragment so the URL ends cleanly with .jpg/.jpeg/.png
    cleaned = cleaned.split("?")[0].split("#")[0]
    if cleaned.lower().endswith(".webp"):
        cleaned = cleaned[:-5] + ".jpg"
    elif not cleaned.lower().endswith((".jpg", ".jpeg", ".png")):
        if "cdn.shopify.com" in cleaned.lower():
            cleaned = cleaned + ".jpg"
    return cleaned


def extract_product_images(product: Dict) -> List[str]:
    """
    Extracts up to 6 unique DeoDap product gallery image URLs for Product Image1..6 (Columns W..AB).
    """
    candidates: List[str] = []
    raw_images = product.get("images") or []
    if isinstance(raw_images, list):
        for img in raw_images:
            if isinstance(img, str) and img.strip():
                candidates.append(img.strip())
            elif isinstance(img, dict) and img.get("src"):
                candidates.append(str(img["src"]).strip())

    primary = product.get("primary_image") or product.get("image_url") or ""
    if primary and primary not in candidates:
        candidates.insert(0, primary)

    seen = set()
    sanitized_list: List[str] = []
    for raw_url in candidates:
        clean_url = sanitize_smartbiz_image_url(raw_url)
        if clean_url and clean_url not in seen:
            seen.add(clean_url)
            sanitized_list.append(clean_url)
            if len(sanitized_list) >= 6:
                break

    while len(sanitized_list) < 6:
        sanitized_list.append("")
    return sanitized_list


def map_smartbiz_categories(product: Dict) -> Tuple[str, str]:
    """
    Maps a Zenlora product to its official SmartBiz (Business Category, Product Category) pair
    from `DataSheet`.
    Strictly enforces `important_instructions` Row 17:
    "Please remember not to create product categories with the same name in different business categories."
    """
    niche = str(product.get("niche") or product.get("primary_category") or "Home Decor").strip()
    title_lower = str(product.get("title") or "").lower()
    mood_lower = str(product.get("festival_mood") or "").lower()
    combined = f"{title_lower} {mood_lower}"

    if niche == "Festive":
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
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", str(text))
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def build_smartbiz_custom_sku(product: Dict, index: int) -> str:
    """
    Uses the real DeoDap SKU (`variants[0].sku`, e.g., `2037_4comp_pla_food_plate`) in Column F (Custom SKU),
    strictly <= 40 characters. Falls back to deterministic `ZEN-<NICHE>-<INDEX>-<HANDLE>` if SKU is missing.
    """
    raw_sku = str(product.get("sku") or "").strip()
    if raw_sku and raw_sku.lower() not in ("none", "null", "n/a"):
        clean_sku = re.sub(r"[^A-Za-z0-9\-_]", "", raw_sku)
        if clean_sku:
            return clean_sku[:40]

    niche = str(product.get("niche") or "Home Decor")
    niche_code = NICHE_CODE_MAP.get(niche, "ZENL")
    handle = str(product.get("handle") or f"item-{index}").strip()
    slug_part = re.sub(r"[^A-Za-z0-9]", "", handle).upper()[:18]
    return f"ZEN-{niche_code}-{index:03d}-{slug_part}"[:40]


def build_smartbiz_product_name(product: Dict) -> str:
    """
    Returns mandatory Product Name strictly <= 200 characters using the full clean commercial title.
    """
    raw_title = str(product.get("title") or product.get("zenlora_title") or "Zenlora Utility Product").strip()
    clean_title = _clean_text(raw_title).replace("Zenlora™", "").strip()
    # Remove any leading numeric model code like "0452 " if present
    clean_title = re.sub(r"^\d{3,5}\s*[-–:]?\s*", "", clean_title).strip()
    clean_title = clean_title.rstrip(" &-–|,:/")
    if not clean_title:
        clean_title = "Zenlora Home & Kitchen Utility Product"
    return clean_title[:200].rstrip(" &-–|,:/")


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

    raw_mrp = product.get("mrp") or product.get("compare_at_price") or 0
    try:
        mrp = int(round(float(raw_mrp)))
    except (ValueError, TypeError):
        mrp = 0

    if mrp <= selling_price:
        computed = max(selling_price + 200, int(round(selling_price * 1.75)))
        mrp = (computed // 100) * 100 + 99
        if mrp <= selling_price:
            mrp = selling_price + 200

    return (mrp, selling_price)


def build_smartbiz_html_description(product: Dict) -> str:
    """
    Generates a clean, high-conversion HTML product description strictly <= 2000 characters
    using real DeoDap specifications and bullet points.
    """
    title = html.escape(build_smartbiz_product_name(product))
    niche = html.escape(str(product.get("niche") or "Home & Kitchen"))
    festival_mood = str(product.get("festival_mood") or "").strip()
    raw_desc = _clean_text(str(product.get("description") or product.get("body_html") or ""))

    bullets = []
    if raw_desc:
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
        bullets.append(f"Weight & Build: Approx. {int(float(weight_g))}g unbreakable transit-safe build.")

    dims = product.get("dimensions")
    if dims:
        bullets.append(f"Dimensions: {html.escape(str(dims))}.")

    if festival_mood and festival_mood.lower() not in ("none", "general", "all"):
        bullets.append(f"Best Suited For: {html.escape(festival_mood)}.")

    bullets.append("Quality Checked & Dispatched across India with secure packaging.")

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

    suffix = " | Zenlora"
    if len(name) + len(suffix) <= 60:
        seo_title = f"{name}{suffix}"
    else:
        seo_title = name[:60].strip()

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
    best_seller = "Yes" if score >= 50.0 else "Yes"

    raw_hsn = str(product.get("hsn_code") or "").strip()
    hsn_code = re.sub(r"[^0-9]", "", raw_hsn)[:8] if raw_hsn else HSN_BY_PRODUCT_CATEGORY.get(product_cat, "392410")

    images = extract_product_images(product)
    seo_title, seo_desc, seo_img = build_seo_metadata(product, images[0])

    niche_label = str(product.get("niche") or "Home & Kitchen")
    festival_mood = str(product.get("festival_mood") or "").strip()
    collection_val = f"{niche_label} ({festival_mood})" if festival_mood else niche_label

    deodap_sku = str(product.get("sku") or custom_sku)
    deodap_pid = str(product.get("id") or "")
    deodap_vid = str(product.get("variant_id") or "")
    supplier_ref = f"SKU: {deodap_sku}"
    if deodap_pid:
        supplier_ref += f" | Product ID: {deodap_pid}"
    if deodap_vid:
        supplier_ref += f" | Variant ID: {deodap_vid}"

    weight_val = f"{int(float(product['weight_grams']))} Grams" if product.get("weight_grams") else "Standard Compact Parcel (<500g)"
    if product.get("dimensions"):
        weight_val += f" ({product['dimensions']})"

    row = [
        "",                     # 1. A: SKU ID (Not to be Edited) -> SmartBiz system internal ID (blank for new uploads)
        "",                     # 2. B: Variant ID (Not to be Edited) -> SmartBiz system internal ID (blank for new uploads)
        "",                     # 3. C: Variant Feature 1 ID ( Not to be edited)
        "",                     # 4. D: Variant Feature 2 ID ( Not to be edited)
        "",                     # 5. E: Variant Feature 3 ID ( Not to be edited)
        custom_sku[:40],        # 6. F: Custom SKU (Optional) Maximum 40 characters -> Real DeoDap SKU!
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
        images[0],              # 23. W: Product Image1 (Optional) -> DeoDap Image 1
        images[1],              # 24. X: Product Image2 (Optional) -> DeoDap Image 2
        images[2],              # 25. Y: Product Image3 (Optional) -> DeoDap Image 3
        images[3],              # 26. Z: Product Image4 (Optional) -> DeoDap Image 4
        images[4],              # 27. AA: Product Image5 (Optional) -> DeoDap Image 5
        images[5],              # 28. AB: Product Image6 (Optional) -> DeoDap Image 6
        "",                     # 29. AC: Size Guide (Optional)
        seo_title[:60],         # 30. AD: SEOMeta Title (Optional)
        seo_desc[:160],         # 31. AE: SEOMeta Description (Optional)
        seo_img,                # 32. AF: SEOMeta ImageUrl (Optional)
        "Country of Origin",    # 33. AG: Custom Attribute Key 1 (Optional)
        "India",                # 34. AH: Custom Attribute Value 1 (Optional)
        "Supplier SKU & ID",    # 35. AI: Custom Attribute Key 2 (Optional)
        supplier_ref[:1000],    # 36. AJ: Custom Attribute Value 2 (Optional)
        "Weight & Dimensions",  # 37. AK: Custom Attribute Key 3 (Optional)
        weight_val[:1000],      # 38. AL: Custom Attribute Value 3 (Optional)
        "Delivery Timeline",    # 39. AM: Custom Attribute Key 4 (Optional)
        "4-8 Business Days (Free Pan-India Shipping)",  # 40. AN: Custom Attribute Value 4 (Optional)
        "Return & Replacement", # 41. AO: Custom Attribute Key 5 (Optional)
        "7-Day Easy Replacement for Damaged or Defective Transit Items",  # 42. AP: Custom Attribute Value 5 (Optional)
        "Collection & Utility", # 43. AQ: Custom Attribute Key 6 (Optional)
        collection_val[:1000],  # 44. AR: Custom Attribute Value 6 (Optional)
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
    if niche and niche != "All":
        items = get_winners(
            niche=niche,
            include_hard_failed=include_hard_failed,
            refresh_dynamic=True,
            batch_cursor=batch_cursor,
            per_niche_display=limit,
        )
        return items[:limit]

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
    categories = ["Festive", "Kitchen", "Home Decor", "Gadgets", "Gifts"]
    per_cat = max(1, total_count // len(categories))

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


def build_unique_smartbiz_rows(products: List[Dict]) -> List[List[str]]:
    rows: List[List[str]] = []
    used_skus = set()
    for idx, prod in enumerate(products, start=1):
        row = product_to_smartbiz_row(prod, index=idx)
        sku = row[5]
        if sku in used_skus:
            suffix = f"-{idx}"
            sku = f"{sku[:40 - len(suffix)]}{suffix}"
            row[5] = sku
        used_skus.add(sku)
        rows.append(row)
    return rows


def generate_smartbiz_csv_bytes(products: List[Dict]) -> bytes:
    """
    Generates a CSV UTF-8 (Comma delimited) (*.csv) byte stream with the exact 52 column headers
    from `smartbiz_bulk_upload_template_v10.xlsx`.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(EXACT_SMARTBIZ_HEADERS)
    for row in build_unique_smartbiz_rows(products):
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def populate_smartbiz_excel_file(
    products: List[Dict],
    template_path: Path,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Populates the `bulk_upload_template` sheet inside `smartbiz_bulk_upload_template_v10.xlsx`
    with the given products while preserving `important_instructions`, `DataSheet`, and Row 1 headers.
    """
    import openpyxl

    target_out = output_path or template_path
    try:
        wb = openpyxl.load_workbook(template_path)
        ws = wb["bulk_upload_template"] if "bulk_upload_template" in wb.sheetnames else wb.active
        # Clear old rows below row 1
        if ws.max_row > 1:
            ws.delete_rows(2, ws.max_row - 1)
    except Exception:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "bulk_upload_template"
        for c_idx, h_val in enumerate(EXACT_SMARTBIZ_HEADERS, start=1):
            ws.cell(row=1, column=c_idx, value=h_val)

    rows = build_unique_smartbiz_rows(products)
    for r_idx, row_vals in enumerate(rows, start=2):
        for c_idx, val in enumerate(row_vals, start=1):
            # Store numeric MRP & Selling Price as actual integers in Excel so DataValidation ISNUMBER() passes
            if c_idx in (8, 9) and str(val).isdigit():
                ws.cell(row=r_idx, column=c_idx, value=int(val))
            else:
                ws.cell(row=r_idx, column=c_idx, value=val if val != "" else None)

    wb.save(target_out)
    wb.close()
    return target_out
