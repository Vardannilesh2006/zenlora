"""
Zenlora SmartBiz 1-Click Catalog Fixer
-------------------------------------
Takes a raw SmartBiz catalog export (.xlsx) and fixes all flat 50% fake discounts:
1. Preserves Columns A & B (SKU ID & Variant ID) for seamless in-place updates without creating duplicates.
2. Recalculates realistic 4-Band Variable Box MRP (21% to 63% natural discounts ending in 9, 5, or 0; 0% flat-50% trap).
3. Embeds the high-trust 15% Online Payment Privilege in Column L (Product Description) without any mystery gifts.
4. Generates a 100% SmartBiz-compliant update workbook ready for Bulk Upload.
"""

import sys
import io
import re
import html
from pathlib import Path
import openpyxl

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "pipeline"))

from winning_engine.smartbiz_exporter import calculate_smartbiz_prices, EXACT_SMARTBIZ_HEADERS

def fix_smartbiz_catalog_file(input_path: str, output_path: str = None) -> dict:
    in_file = Path(input_path)
    if not in_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not output_path:
        output_path = str(in_file.parent / f"{in_file.stem}_FIXED_FOR_SMARTBIZ.xlsx")

    wb = openpyxl.load_workbook(str(in_file))
    
    # Locate data sheet (usually 'bulk_upload_template' or the first sheet with headers)
    target_sheet = None
    for sname in ["bulk_upload_template", "Sheet1", wb.sheetnames[0]]:
        if sname in wb.sheetnames:
            ws = wb[sname]
            # Verify if row 1 has 'Product Name' or 'Custom SKU'
            r1_vals = [str(ws.cell(row=1, column=c).value or "") for c in range(1, 15)]
            if any("Product Name" in v or "Custom SKU" in v or "MRP" in v for v in r1_vals):
                target_sheet = ws
                break

    if not target_sheet:
        target_sheet = wb.active

    # Find column indices
    col_map = {}
    for c in range(1, target_sheet.max_column + 1):
        h = str(target_sheet.cell(row=1, column=c).value or "").strip()
        col_map[h] = c

    # Fallback to standard indices if headers don't match exact strings
    c_mrp = col_map.get("MRP (Mandatory)", 8)
    c_sp = col_map.get("Selling Price (Optional)", 9)
    c_desc = col_map.get("Product Description (Optional)", 12)
    c_sku = col_map.get("Custom SKU (Optional)", 6)
    c_title = col_map.get("Product Name (Mandatory)", 7)

    fixed_count = 0
    total_products = 0
    updated_descriptions = 0

    offer_block = (
        "\n\nAvailable offers:\n"
        "• Bank Offer: Flat 15% Instant Discount on UPI and Net Banking payments.\n"
        "• Partner Offer: Free Express Shipping & Priority 24h Dispatch on prepaid orders.\n"
        "• Cash on Delivery: Available across India (₹49 handling fee applies)."
    )

    for r in range(2, target_sheet.max_row + 1):
        title_val = target_sheet.cell(row=r, column=c_title).value
        sku_val = target_sheet.cell(row=r, column=c_sku).value
        if not title_val and not sku_val:
            continue

        total_products += 1

        raw_mrp = target_sheet.cell(row=r, column=c_mrp).value
        raw_sp = target_sheet.cell(row=r, column=c_sp).value

        try:
            sp = int(float(raw_sp)) if raw_sp else 299
        except (ValueError, TypeError):
            sp = 299

        try:
            mrp = int(float(raw_mrp)) if raw_mrp else sp * 2
        except (ValueError, TypeError):
            mrp = sp * 2

        # Check if 50% trap or invalid MRP
        current_disc = round(((mrp - sp) / float(mrp)) * 100) if mrp > 0 else 0

        # Create dummy product dict to pass to 4-band pricing engine
        dummy_prod = {
            "title": str(title_val or ""),
            "sku": str(sku_val or ""),
            "selling_price": sp,
            "wholesale_price": max(35.0, (sp - 120.0) * 0.7),
        }

        # Recalculate realistic 4-band variable MRP
        new_mrp, new_sp = calculate_smartbiz_prices(dummy_prod)
        new_disc = round(((new_mrp - new_sp) / float(new_mrp)) * 100)

        # Update cells in Excel
        if current_disc == 50 or mrp == sp * 2 or new_mrp != mrp:
            target_sheet.cell(row=r, column=c_mrp, value=int(new_mrp))
            target_sheet.cell(row=r, column=c_sp, value=int(new_sp))
            fixed_count += 1

        # Update description with clean Available offers standard
        existing_desc = str(target_sheet.cell(row=r, column=c_desc).value or "").strip()
        # Remove old offer blocks if present
        clean_desc = re.sub(r"\n*⚡\s*(SPECIAL|EXCLUSIVE)\s*(PAYMENT\s*OFFERS|ONLINE\s*PAYMENT\s*PRIVILEGES)[\s\S]*$", "", existing_desc).strip()
        clean_desc = re.sub(r"\n*Available offers:[\s\S]*$", "", clean_desc).strip()
        clean_desc = clean_desc.replace("<p>", "").replace("</p>", "").strip()
        if not clean_desc or len(clean_desc) < 20:
            clean_desc = f"Upgrade your daily lifestyle routine with the {title_val}. Crafted from durable, high-quality materials designed for modern Indian homes."

        trimmed_desc = clean_desc[:1750].strip()
        full_desc = f"{trimmed_desc}{offer_block}"[:2000].strip()
        target_sheet.cell(row=r, column=c_desc, value=full_desc)
        updated_descriptions += 1

    wb.save(output_path)
    wb.close()

    return {
        "success": True,
        "input_file": str(in_file),
        "output_file": str(output_path),
        "total_products": total_products,
        "mrp_discounts_fixed": fixed_count,
        "descriptions_updated": updated_descriptions,
    }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        inp = sys.argv[1]
        outp = sys.argv[2] if len(sys.argv) > 2 else None
        res = fix_smartbiz_catalog_file(inp, outp)
        print("RESULT:", res)
    else:
        print("Usage: python fix_smartbiz_catalog.py <path_to_smartbiz_export.xlsx>")
