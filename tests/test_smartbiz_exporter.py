import csv
import io
import sys
from pathlib import Path
import openpyxl
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "pipeline"))

from pipeline.winning_engine.smartbiz_exporter import (
    EXACT_SMARTBIZ_HEADERS,
    OFFICIAL_BUSINESS_CATEGORIES,
    generate_smartbiz_csv_bytes,
    sanitize_smartbiz_image_url,
    select_current_page_products,
    select_smart_mix_products,
)
from pipeline.web_app import app

TEMPLATE_XLSX_PATH = ROOT_DIR / "smartbiz_bulk_upload_template_v10.xlsx"


def test_exact_52_headers_match_excel_template():
    """Verify EXACT_SMARTBIZ_HEADERS matches bulk_upload_template Row 1 (A1:AZ1) character-for-character."""
    assert len(EXACT_SMARTBIZ_HEADERS) == 52
    if TEMPLATE_XLSX_PATH.exists():
        wb = openpyxl.load_workbook(TEMPLATE_XLSX_PATH, read_only=True)
        ws = wb["bulk_upload_template"]
        row1 = [c for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))][:52]
        wb.close()
        assert row1 == EXACT_SMARTBIZ_HEADERS


def test_image_url_sanitization():
    raw = "https://cdn.shopify.com/s/files/1/0001/products/festive_diya.webp?v=1712345678"
    clean = sanitize_smartbiz_image_url(raw)
    assert clean == "https://cdn.shopify.com/s/files/1/0001/products/festive_diya.jpg"
    assert "?" not in clean
    assert clean.endswith(".jpg")


def test_smart_mix_and_csv_validation_rules():
    """Verify 55-product mix across all 5 categories passes every SmartBiz Excel validation rule."""
    mix_products = select_smart_mix_products(total_count=55, batch_cursor=0)
    assert 50 <= len(mix_products) <= 60

    csv_bytes = generate_smartbiz_csv_bytes(mix_products)
    text = csv_bytes.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))

    headers = reader[0]
    assert headers == EXACT_SMARTBIZ_HEADERS
    data_rows = reader[1:]
    assert len(data_rows) == len(mix_products)

    seen_skus = set()
    product_cat_to_business_cat = {}

    for row in data_rows:
        assert len(row) == 52
        # Cols A-E (0..4) must be empty
        assert all(row[i] == "" for i in range(5))

        # Col F (5): Custom SKU <= 40 chars and unique
        sku = row[5]
        assert 1 <= len(sku) <= 40
        assert sku not in seen_skus
        seen_skus.add(sku)

        # Col G (6): Product Name <= 200 chars
        prod_name = row[6]
        assert 1 <= len(prod_name) <= 200

        # Col H (7) & Col I (8): MRP & Selling Price numeric and MRP > Selling Price > 0
        mrp = int(row[7])
        sp = int(row[8])
        assert sp > 0
        assert mrp > sp
        assert mrp <= 999999
        # Strictly forbid flat 50% discount trap (MRP == 2 * Selling Price)
        assert mrp != sp * 2

        # Col J (9) & Col K (10): Business Category & Product Category
        b_cat = row[9]
        p_cat = row[10]
        assert b_cat == "GENERAL"
        assert b_cat in OFFICIAL_BUSINESS_CATEGORIES
        assert 1 <= len(p_cat) <= 100
        # Enforce Row 17 rule: Same Product Category name cannot appear under different Business Categories
        if p_cat in product_cat_to_business_cat:
            assert product_cat_to_business_cat[p_cat] == b_cat
        else:
            product_cat_to_business_cat[p_cat] = b_cat

        # Col L (11): Product Description <= 2000 chars
        desc = row[11]
        assert 1 <= len(desc) <= 2000

        # Col M (12): Variant Relationship blank for standalone
        assert row[12] == ""

        # Col U (20): Best Seller is "Yes" or "No" (matching user's SmartBiz preset)
        assert row[20] in ("Yes", "No", "")

        # Cols W-AB (22..27): Product Images must not have .webp or ? query strings
        for img_col in row[22:28]:
            if img_col:
                assert "?" not in img_col
                assert img_col.lower().endswith((".jpg", ".jpeg", ".png"))

        # Cols AD (29) & AE (30): Left blank matching user's SmartBiz preset
        assert len(row[29]) <= 60
        assert len(row[30]) <= 160


def test_flask_smartbiz_csv_endpoints():
    client = app.test_client()

    # 1. Test Current Page Mode (Festive category, 20 items)
    resp_page = client.get("/api/radar/smartbiz.csv?mode=page&niche=Festive&batch=1&limit=20")
    assert resp_page.status_code == 200
    assert "text/csv" in resp_page.content_type
    rows_page = list(csv.reader(io.StringIO(resp_page.data.decode("utf-8-sig"))))
    assert rows_page[0] == EXACT_SMARTBIZ_HEADERS
    assert 12 <= len(rows_page) - 1 <= 20

    # 2. Test Smart Mix Mode (55 items across all 5 categories)
    resp_mix = client.get("/api/radar/smartbiz.csv?mode=mix&batch=0&count=55")
    assert resp_mix.status_code == 200
    rows_mix = list(csv.reader(io.StringIO(resp_mix.data.decode("utf-8-sig"))))
    assert rows_mix[0] == EXACT_SMARTBIZ_HEADERS
    assert len(rows_mix) - 1 == 55

    # 3. Test Saved SmartBiz Preset Endpoint
    resp_preset = client.get("/api/radar/smartbiz-preset")
    assert resp_preset.status_code == 200
    preset_json = resp_preset.get_json()
    assert preset_json["preset_id"] == "zenlora_smartbiz_v10_new_winners"
    assert len(preset_json["discount_bands"]) == 4

    # 4. Test SmartBiz 3-Sheet Excel (.xlsx) Endpoint (without committing to ledger)
    resp_xlsx = client.get("/api/radar/smartbiz.xlsx?mode=page&niche=Kitchen&batch=0&limit=15&commit=0")
    assert resp_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(resp_xlsx.data), read_only=True)
    assert "bulk_upload_template" in wb.sheetnames
    wb.close()

    # Reset test exports back to store baseline
    client.post("/api/radar/export-ledger", json={"action": "reset", "keep_store_baseline": True})


def test_zero_repeat_vault_across_multiple_csv_exports():
    """
    Strictly verifies that generating CSV multiple times in a row NEVER repeats a single SKU or product title,
    and never exports any of the 90 existing store baseline products.
    """
    client = app.test_client()
    client.post("/api/radar/export-ledger", json={"action": "reset", "keep_store_baseline": True})

    baseline_ledger = client.get("/api/radar/export-ledger").get_json()
    baseline_skus = set(baseline_ledger.get("skus", []))
    assert len(baseline_skus) >= 39

    all_exported_skus = set()
    all_exported_titles = set()

    try:
        # Generate 3 consecutive CSV files (25 products each = 75 products total)
        for run_idx in range(3):
            resp = client.post(
                "/api/radar/smartbiz.csv?mode=page&niche=All&limit=25",
                json={"excluded_keys": list(all_exported_skus)},
            )
            assert resp.status_code == 200
            rows = list(csv.reader(io.StringIO(resp.data.decode("utf-8-sig"))))[1:]
            assert len(rows) == 25

            for r in rows:
                sku = r[5].strip().lower()
                title = r[6].strip().lower()
                assert sku not in baseline_skus, f"Store baseline SKU {sku} was repeated!"
                assert sku not in all_exported_skus, f"SKU {sku} was repeated in run {run_idx + 1}!"
                assert title not in all_exported_titles, f"Title '{title}' was repeated in run {run_idx + 1}!"
                all_exported_skus.add(sku)
                all_exported_titles.add(title)
    finally:
        # Cleanly restore ledger to the 90 store baseline items after test
        client.post("/api/radar/export-ledger", json={"action": "reset", "keep_store_baseline": True})


def test_scan_deodap_winners_and_repeated_csv_exports_zero_repeats(monkeypatch):
    """
    Verifies that clicking 'Scan DeoDap Winners' (/api/radar/scan) repeatedly followed by
    generating SmartBiz CSV files NEVER repeats a product, preserves the unexported pool,
    and applies the SmartBiz v10 Store Preset to every row.
    """
    import winning_engine.deodap_harvester as dh

    class _DummyResponse:
        status_code = 200

        def json(self):
            return {"products": [], "resources": {"results": {"products": []}}}

    monkeypatch.setattr(dh.requests, "get", lambda *a, **kw: _DummyResponse())

    client = app.test_client()
    client.post("/api/radar/export-ledger", json={"action": "reset", "keep_store_baseline": True})

    exported_skus = set()
    exported_handles = set()
    exported_titles = set()

    try:
        for cycle in range(1, 3):
            # 1. Click 'Scan DeoDap Winners'
            scan_res = client.post(
                "/api/radar/scan",
                json={
                    "limit": 15,
                    "batch": cycle,
                    "excluded_keys": list(exported_skus | exported_handles),
                },
            )
            assert scan_res.status_code == 200
            scan_data = scan_res.get_json()
            assert scan_data["success"] is True
            assert scan_data["count"] >= 200  # Pool is preserved/merged, never shrunk!

            # Verify none of the already exported SKUs or handles are in the scanned pool
            for w in scan_data["winners"]:
                w_sku = str(w.get("sku") or "").strip().lower()
                w_handle = str(w.get("handle") or "").strip().lower()
                assert w_sku not in exported_skus
                assert w_handle not in exported_handles

            # 2. Generate SmartBiz CSV after scan
            csv_res = client.post(
                f"/api/radar/smartbiz.csv?mode=page&niche=All&batch={cycle}&limit=20",
                json={"excluded_keys": list(exported_skus | exported_handles)},
            )
            assert csv_res.status_code == 200
            rows = list(csv.reader(io.StringIO(csv_res.data.decode("utf-8-sig"))))[1:]
            assert len(rows) == 20

            new_handles = [
                h.strip().lower()
                for h in (csv_res.headers.get("X-Zenlora-Exported-Handles") or "").split(",")
                if h.strip()
            ]
            exported_handles.update(new_handles)

            for r in rows:
                # Preset checks: A-E blank, J = GENERAL, MRP > Selling Price
                assert r[0] == "" and r[4] == ""
                assert r[9] == "GENERAL"
                assert int(r[7]) > int(r[8])

                sku = r[5].strip().lower()
                title = r[6].strip().lower()
                assert sku not in exported_skus, f"Cycle {cycle} repeated SKU {sku}!"
                assert title not in exported_titles, f"Cycle {cycle} repeated title {title}!"
                exported_skus.add(sku)
                exported_titles.add(title)
    finally:
        client.post("/api/radar/export-ledger", json={"action": "reset", "keep_store_baseline": True})


def test_category_purity_and_exact_smartbiz_product_category():
    """
    Verifies:
    1. Every category page (Festive, Home Decor, Kitchen, Gadgets, Gifts) has 24 High-Confidence,
       100% category-matching products (and All has 120).
    2. Downloading CSV for any category sets Column K (Product Category) to the exact storefront
       category name ('Festive & Lights', 'Home Decor', 'Kitchen & Dining', 'Smart Gadgets', 'Gifts & Hampers')
       and NEVER outputs generic 'Home Improvement' or 'Home & Kitchen'.
    """
    from pipeline.winning_engine.deodap_harvester import classify_niche, is_junk_or_mismatched_product
    from pipeline.winning_engine.radar_controller import get_winners

    expected_map = {
        "Festive": "Festive & Lights",
        "Home Decor": "Home Decor",
        "Kitchen": "Kitchen & Dining",
        "Gadgets": "Smart Gadgets",
        "Gifts": "Gifts & Hampers",
    }

    all_items = get_winners(niche="All", per_niche_display=24, refresh_dynamic=False)
    assert len(all_items) == 120

    for niche_key, expected_col_k in expected_map.items():
        niche_items = get_winners(niche=niche_key, per_niche_display=24, refresh_dynamic=False)
        assert len(niche_items) == 24, f"{niche_key} expected 24 items, got {len(niche_items)}"

        for item in niche_items:
            assert item.get("niche") == niche_key
            assert item.get("confidence") == "High", f"{item.get('title')} has confidence {item.get('confidence')}"
            assert not is_junk_or_mismatched_product(item.get("title", ""))
            assert classify_niche(item.get("title", ""), preferred_niche=niche_key) == niche_key

        page_products = select_current_page_products(niche=niche_key, batch_cursor=0, limit=24)
        assert len(page_products) == 24
        csv_bytes = generate_smartbiz_csv_bytes(page_products, niche_override=niche_key)
        rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))[1:]
        assert len(rows) == 24
        for r in rows:
            assert r[9] == "GENERAL"
            assert r[10] == expected_col_k, f"Expected '{expected_col_k}' for {niche_key}, got '{r[10]}'"
            assert r[10] not in ("Home Improvement", "Home & Kitchen")


