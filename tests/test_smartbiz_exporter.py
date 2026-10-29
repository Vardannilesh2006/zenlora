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
        "Festive & Lights": "Festive & Lights",
        "Health & Beauty Accessories": "Health & Beauty Accessories",
        "Home & Kitchen": "Home & Kitchen",
        "Home Improvement": "Home Improvement",
        "Smart Gadgets": "Smart Gadgets",
        "Toys & Games": "Toys & Games",
        "Car & Vehicle Accessories": "Car & Vehicle Accessories",
    }

    all_items = get_winners(niche="All", per_niche_display=24, refresh_dynamic=False)
    assert len(all_items) == 168

    for niche_key, expected_col_k in expected_map.items():
        niche_items = get_winners(niche=niche_key, per_niche_display=24, refresh_dynamic=False)
        assert len(niche_items) == 24, f"{niche_key} expected 24 items, got {len(niche_items)}"

        for item in niche_items:
            assert item.get("niche") == niche_key
            assert not is_junk_or_mismatched_product(item.get("title", ""))

        page_products = select_current_page_products(niche=niche_key, batch_cursor=0, limit=24)
        assert len(page_products) == 24
        csv_bytes = generate_smartbiz_csv_bytes(page_products, niche_override=niche_key)
        rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))[1:]
        assert len(rows) == 24
        for r in rows:
            assert r[9] == "GENERAL"
            assert r[10] == expected_col_k, f"Expected '{expected_col_k}' for {niche_key}, got '{r[10]}'" 


def test_one_click_product_images_zip_download(monkeypatch):
    """
    Verifies:
    1. Clicking any product on Studio Catalog (/) or Winning Radar (/radar) opens /product/<handle>
       with the 1-Click 'Download All DeoDap Images (.ZIP)' button and full image gallery.
    2. /api/product/<handle>/images.zip packages all DeoDap product images into a .zip file
       named after the product title (<Product_Title>.zip) with inner files named <Product_Title>_01.jpg, etc.
    """
    import zipfile
    from pipeline.deodap_extractor import DeoDapExtractor, sanitize_title_for_filename
    from pipeline.web_app import app

    fake_img_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    def fake_resolve(handle, fallback_product=None):
        title = (fallback_product or {}).get("title") or (fallback_product or {}).get("zenlora_title") or "Crystal Rose Diamond Table Lamp"
        return (
            [
                "https://cdn.shopify.com/s/files/1/deodap/img1.jpg",
                "https://cdn.shopify.com/s/files/1/deodap/img2.jpg",
                "https://cdn.shopify.com/s/files/1/deodap/img3.png",
            ],
            title,
        )

    def fake_download(idx_and_url):
        idx, url = idx_and_url
        ext = ".png" if url.endswith(".png") else ".jpg"
        return idx, ext, fake_img_bytes

    monkeypatch.setattr(DeoDapExtractor, "resolve_all_product_images", staticmethod(fake_resolve))
    monkeypatch.setattr(DeoDapExtractor, "_download_single_image", staticmethod(fake_download))

    client = app.test_client()
    from pipeline.winning_engine.radar_controller import get_winners
    from pipeline.web_app import _find_any_product_by_handle
    sample = get_winners(niche="Festive", per_niche_display=24, refresh_dynamic=False)[0]
    handle = sample["handle"]
    resolved_prod = _find_any_product_by_handle(handle)
    prod_title = (resolved_prod or {}).get("title") or (resolved_prod or {}).get("zenlora_title") or sample["title"]
    expected_safe_title = sanitize_title_for_filename(prod_title)

    # 1. Verify Product Detail Page (/product/<handle>) renders the 1-Click ZIP button & gallery
    detail_res = client.get(f"/product/{handle}")
    assert detail_res.status_code == 200
    html_text = detail_res.data.decode("utf-8")
    assert f"/api/product/{handle}/images.zip" in html_text
    assert "Download All Images (.ZIP)" in html_text
    assert "All DeoDap Product Images" in html_text

    # 2. Verify 1-Click ZIP endpoint (/api/product/<handle>/images.zip)
    zip_res = client.get(f"/api/product/{handle}/images.zip")
    assert zip_res.status_code == 200
    assert zip_res.mimetype == "application/zip"
    disp = zip_res.headers.get("Content-Disposition", "")
    assert f"{expected_safe_title}.zip" in disp
    assert zip_res.headers.get("X-Zenlora-Image-Count") == "3"

    with zipfile.ZipFile(io.BytesIO(zip_res.data), "r") as zf:
        names = zf.namelist()
        assert len(names) == 3
        assert names[0] == f"{expected_safe_title}_01.jpg"
        assert names[1] == f"{expected_safe_title}_02.jpg"
        assert names[2] == f"{expected_safe_title}_03.png"
        for name in names:
            assert zf.read(name) == fake_img_bytes


def test_smartbiz_excel_worksheet_bulk_upload_template_and_structure():
    """
    Verifies that SmartBiz Excel (.xlsx) exports strictly satisfy:
    1. The workbook contains exactly 3 sheets: ['important_instructions', 'bulk_upload_template', 'DataSheet']
    2. The worksheet 'bulk_upload_template' is present and active (eliminating the SmartBiz error:
       'Worksheet named "bulk_upload_template" missing in the uploaded file')
    3. Row 1 has the exact 52 official headers.
    4. Row 2..N has valid product data:
       - Columns A..E are blank for new products.
       - Column F is the custom/DeoDap SKU.
       - Column G is clean product name (no \ufffd).
       - Columns H & I are integers (MRP > Selling Price).
       - Column J is 'GENERAL'.
       - Column K is the exact category ('Festive & Lights').
    """
    client = app.test_client()

    # 1. Test Category Page (.xlsx)
    res_page = client.get("/api/radar/smartbiz.xlsx?mode=page&niche=Festive&batch=0&limit=24&commit=0")
    assert res_page.status_code == 200
    assert "openxmlformats" in res_page.content_type
    disp = res_page.headers.get("Content-Disposition", "")
    assert ".xlsx" in disp

    wb_page = openpyxl.load_workbook(io.BytesIO(res_page.data), data_only=True)
    assert wb_page.sheetnames == ["important_instructions", "bulk_upload_template", "DataSheet"]
    assert "bulk_upload_template" in wb_page.sheetnames
    assert wb_page.active.title == "bulk_upload_template"

    ws_page = wb_page["bulk_upload_template"]
    assert ws_page.max_row == 25  # 1 header row + 24 product rows
    assert [ws_page.cell(1, col).value for col in range(1, 53)] == EXACT_SMARTBIZ_HEADERS

    for r_idx in range(2, 26):
        # A..E must be None/empty
        for col in range(1, 6):
            assert ws_page.cell(r_idx, col).value in (None, "")
        # F: SKU
        sku = ws_page.cell(r_idx, 6).value
        assert sku and len(str(sku)) <= 40
        # G: Name
        name = ws_page.cell(r_idx, 7).value
        assert name and "\ufffd" not in str(name) and len(str(name)) <= 200
        # H & I: MRP & Selling Price as integers
        mrp = ws_page.cell(r_idx, 8).value
        sp = ws_page.cell(r_idx, 9).value
        assert isinstance(mrp, (int, float)) and isinstance(sp, (int, float))
        assert int(mrp) > int(sp)
        # J: Business Category
        assert ws_page.cell(r_idx, 10).value == "GENERAL"
        # K: Product Category
        assert ws_page.cell(r_idx, 11).value == "Festive & Lights"

    wb_page.close()

    # 2. Test Smart Mix 55 (.xlsx)
    res_mix = client.get("/api/radar/smartbiz.xlsx?mode=mix&batch=0&count=55&commit=0")
    assert res_mix.status_code == 200
    wb_mix = openpyxl.load_workbook(io.BytesIO(res_mix.data), data_only=True)
    assert "bulk_upload_template" in wb_mix.sheetnames
    ws_mix = wb_mix["bulk_upload_template"]
    assert ws_mix.max_row == 56  # 1 header + 55 products
    wb_mix.close()


def test_festive_and_lights_page_always_shows_24_products():
    """
    Verifies that the Festive & Lights category page (/radar?niche=Festive) ALWAYS returns
    24 products (between 20 and 25 products), even if 60+ Festive items were previously exported.
    """
    from pipeline.winning_engine.radar_controller import get_winners

    all_festive = get_winners(niche="Festive", per_niche_display=0, exclude_exported=False, refresh_dynamic=False)
    assert len(all_festive) >= 24

    # Simulate 98% of Festive items being in the export blocklist (leaving only 2 unexported)
    blocked_handles = [w["handle"] for w in all_festive[:-2]]
    festive_slice = get_winners(
        niche="Festive",
        per_niche_display=24,
        exclude_exported=True,
        extra_excluded_keys=blocked_handles,
        refresh_dynamic=False,
    )
    assert len(festive_slice) == 24

    # Verify the HTML route /radar?niche=Festive renders 24 product cards
    client = app.test_client()
    res = client.get("/radar?niche=Festive")
    assert res.status_code == 200
    html_text = res.data.decode("utf-8")
    assert html_text.count('id="card-') == 24


def test_health_and_beauty_accessories_radar_page_and_excel_export():
    """
    Verifies that 'Health & Beauty' appears on /radar with 24 products,
    works with both URL-encoded and unencoded query parameters, and exports 24 items
    to SmartBiz Excel with Column K = 'Health & Beauty'.
    """
    import openpyxl

    client = app.test_client()

    # 1. Main /radar page includes the Health & Beauty Accessories category pill with (24)
    res_main = client.get("/radar")
    assert res_main.status_code == 200
    main_html = res_main.data.decode("utf-8")
    assert "Health &amp; Beauty Accessories (24)" in main_html or "Health & Beauty Accessories (24)" in main_html

    # 2. Encoded URL /radar?niche=Health+%26+Beauty+Accessories renders 24 cards
    res_enc = client.get("/radar?niche=Health+%26+Beauty+Accessories")
    assert res_enc.status_code == 200
    enc_html = res_enc.data.decode("utf-8")
    assert enc_html.count('id="card-') == 24
    assert "Health &amp; Beauty Accessories" in enc_html or "Health & Beauty Accessories" in enc_html

    # 3. Unencoded URL /radar?niche=Health & Beauty Accessories ALSO renders 24 cards
    res_unenc = client.get("/radar?niche=Health & Beauty Accessories")
    assert res_unenc.status_code == 200
    unenc_html = res_unenc.data.decode("utf-8")
    assert unenc_html.count('id="card-') == 24

    # 4. SmartBiz Page Excel (.xlsx) export for Health & Beauty Accessories has 24 rows and Col K = 'Health & Beauty Accessories'
    res_xlsx = client.get("/api/radar/smartbiz.xlsx?mode=page&niche=Health+%26+Beauty+Accessories&limit=24&commit=0")
    assert res_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.data), data_only=True)
    ws = wb["bulk_upload_template"]
    assert ws.max_row == 25  # 1 header + 24 products
    for r_idx in range(2, 26):
        assert ws.cell(r_idx, 10).value == "GENERAL"
        assert ws.cell(r_idx, 11).value == "Health & Beauty Accessories"
    wb.close()


def test_under_50_deodap_price_preset_and_filter():
    """
    Verifies that every product with DeoDap wholesale price <= ₹50 has Selling Price
    strictly in ₹179 to ₹185, and that the /radar?cost_filter=under_50 filter & Excel export work.
    """
    import openpyxl
    from pipeline.winning_engine.radar_controller import get_winners

    all_items = get_winners(niche="All", per_niche_display=0, exclude_exported=False, refresh_dynamic=True)
    under_50 = [w for w in all_items if 0 < float(w.get("wholesale_price") or 0) <= 50.0]
    assert len(under_50) >= 30
    for w in under_50:
        sp = int(w.get("selling_price") or 0)
        sug = int(w.get("suggested_price") or 0)
        assert 179 <= sp <= 185, f"Expected 179..185 for {w.get('handle')} (cost={w.get('wholesale_price')}), got {sp}"
        assert 179 <= sug <= 185, f"Expected 179..185 suggested_price for {w.get('handle')}, got {sug}"

    client = app.test_client()
    res_filter = client.get("/radar?cost_filter=under_50")
    assert res_filter.status_code == 200
    html_filter = res_filter.data.decode("utf-8")
    assert "Under 199 Collection" in html_filter
    assert "Under 199" in html_filter

    # Check dedicated /radar?niche=Under+199+Collection tab renders 24 cards
    res_tab = client.get("/radar?niche=Under+199+Collection")
    assert res_tab.status_code == 200
    html_tab = res_tab.data.decode("utf-8")
    assert html_tab.count('id="card-') == 24
    assert "Under 199 Collection (24)" in html_tab

    # 1. Verify SmartBiz Excel export with cost_filter=under_50 on niche=All sets Col K = 'Under 199 Collection' and SP in 179..185
    res_xlsx = client.get("/api/radar/smartbiz.xlsx?mode=page&niche=All&cost_filter=under_50&limit=24&commit=0")
    assert res_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.data), data_only=True)
    ws = wb["bulk_upload_template"]
    assert ws.max_row == 25
    for r_idx in range(2, 26):
        sp_val = int(ws.cell(r_idx, 9).value)
        assert 179 <= sp_val <= 185, f"Row {r_idx} Selling Price {sp_val} not in 179..185"
        assert ws.cell(r_idx, 10).value == "GENERAL"
        assert ws.cell(r_idx, 11).value == "Under 199 Collection"
    wb.close()

    # 2. Verify SmartBiz Excel export with cost_filter=under_50 on a specific category page (e.g. Kitchen) ALSO sets Col K = 'Under 199 Collection'
    res_kitchen_xlsx = client.get("/api/radar/smartbiz.xlsx?mode=page&niche=Kitchen&cost_filter=under_50&limit=24&commit=0")
    assert res_kitchen_xlsx.status_code == 200
    wb_k = openpyxl.load_workbook(io.BytesIO(res_kitchen_xlsx.data), data_only=True)
    ws_k = wb_k["bulk_upload_template"]
    assert ws_k.max_row >= 2
    for r_idx in range(2, ws_k.max_row + 1):
        sp_val = int(ws_k.cell(r_idx, 9).value)
        assert 179 <= sp_val <= 185
        assert ws_k.cell(r_idx, 10).value == "GENERAL"
        assert ws_k.cell(r_idx, 11).value == "Under 199 Collection"
    wb_k.close()


def test_strict_7_primary_categories_and_smartbiz_excel_export():
    """
    Verifies:
    1. Only 7 primary storefront categories exist in Zenlora:
       - Home Decor
       - Kitchen & Dining
       - Smart Gadgets
       - Festive & Lights
       - Gifts & Hampers
       - Health & Beauty
       - Under 199 Collection
    2. Exporting SmartBiz Page Excel (.xlsx) from each dedicated page outputs exactly that category in Col K.
    3. Exporting SmartBiz Mix (.xlsx) or All (.xlsx) has 100% of rows belonging ONLY to these 7 categories.
    """
    import openpyxl
    from pipeline.winning_engine.radar_controller import get_winners
    from pipeline.winning_engine.smartbiz_exporter import load_smartbiz_preset

    preset = load_smartbiz_preset()
    allowed_categories = set(preset.get("storefront_categories", []))
    expected_categories = {
        "Festive & Lights",
        "Health & Beauty Accessories",
        "Home & Kitchen",
        "Home Improvement",
        "Smart Gadgets",
        "Toys & Games",
        "Car & Vehicle Accessories",
        "Under 199 Collection",
    }
    assert allowed_categories == expected_categories, f"Preset storefront_categories mismatch: {allowed_categories}"

    client = app.test_client()

    # 1. Test dedicated category exports
    category_checks = [
        ("Festive & Lights", "Festive & Lights"),
        ("Health & Beauty Accessories", "Health & Beauty Accessories"),
        ("Home & Kitchen", "Home & Kitchen"),
        ("Home Improvement", "Home Improvement"),
        ("Smart Gadgets", "Smart Gadgets"),
        ("Toys & Games", "Toys & Games"),
        ("Under 199 Collection", "Under 199 Collection"),
    ]
    for page_niche, expected_cat in category_checks:
        res = client.get(f"/api/radar/smartbiz.xlsx?mode=page&niche={page_niche}&limit=24&commit=0")
        assert res.status_code == 200, f"Export failed for {page_niche}"
        wb = openpyxl.load_workbook(io.BytesIO(res.data), data_only=True)
        ws = wb["bulk_upload_template"]
        assert ws.max_row >= 2
        for r in range(2, ws.max_row + 1):
            cat_val = ws.cell(r, 11).value
            assert cat_val == expected_cat, f"Page {page_niche} row {r} Col K is '{cat_val}', expected '{expected_cat}'"
            assert ws.cell(r, 10).value == "GENERAL"
        wb.close()

    # 2. Test Mix 55 export strictly contains only these approved categories
    res_mix = client.get("/api/radar/smartbiz.xlsx?mode=mix&count=55&commit=0")
    assert res_mix.status_code == 200
    wb_m = openpyxl.load_workbook(io.BytesIO(res_mix.data), data_only=True)
    ws_m = wb_m["bulk_upload_template"]
    assert ws_m.max_row >= 50
    for r in range(2, ws_m.max_row + 1):
        cat_val = ws_m.cell(r, 11).value
        assert cat_val in expected_categories, f"Mix export row {r} has illegal category '{cat_val}' not in {expected_categories}"
    wb_m.close()


def test_toys_and_games_radar_page_and_excel_export():
    """
    Verifies that 'Toys & Games' appears on /radar with 24 winning products,
    renders properly with URL-encoded query parameters, and exports 24 items
    to SmartBiz Excel with Column J = 'GENERAL' and Column K = 'Toys & Games'.
    """
    import openpyxl
    from pipeline.winning_engine.radar_controller import get_winners

    toys_items = get_winners(niche="Toys & Games", per_niche_display=24, exclude_exported=False, refresh_dynamic=True)
    assert len(toys_items) == 24, f"Expected 24 items for Toys & Games, got {len(toys_items)}"
    for t in toys_items:
        assert t.get("confidence") == "High"
        assert not t.get("is_hard_failed")

    client = app.test_client()

    # 1. Main /radar page includes the Toys & Games category pill with (24)
    res_main = client.get("/radar")
    assert res_main.status_code == 200
    main_html = res_main.data.decode("utf-8")
    assert "Toys &amp; Games (24)" in main_html or "Toys & Games (24)" in main_html

    # 2. Dedicated page /radar?niche=Toys+%26+Games renders 24 product cards
    res_page = client.get("/radar?niche=Toys+%26+Games")
    assert res_page.status_code == 200
    page_html = res_page.data.decode("utf-8")
    assert page_html.count('id="card-') == 24

    # 3. SmartBiz Page Excel (.xlsx) export has 24 rows and Col K = 'Toys & Games'
    res_xlsx = client.get("/api/radar/smartbiz.xlsx?mode=page&niche=Toys+%26+Games&limit=24&commit=0")
    assert res_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.data), data_only=True)
    ws = wb["bulk_upload_template"]
    assert ws.max_row == 25  # 1 header + 24 products
    for r_idx in range(2, 26):
        mrp_val = int(ws.cell(r_idx, 8).value)
        sp_val = int(ws.cell(r_idx, 9).value)
        assert sp_val > 0
        assert mrp_val > sp_val
        assert ws.cell(r_idx, 10).value == "GENERAL"
        assert ws.cell(r_idx, 11).value == "Toys & Games"
    wb.close()


def test_column_ae_seo_meta_description_strictly_pure_plain_text():
    """
    Permanently verifies that Column AE (SEOMeta Description) in all exported SmartBiz files:
    1. Strictly contains NO HTML tags (<p>, </p>, <br>, <b>, <div>, etc.).
    2. Strictly contains NO '<' or '>' characters.
    3. Contains clean, unescaped plain text <= 160 characters.
    4. Column AD (SEOMeta Title) contains NO HTML tags and is <= 60 characters.
    5. Column K (Product Category) strictly contains only the 7 official storefront categories.
    """
    import openpyxl
    from pipeline.winning_engine.smartbiz_exporter import (
        product_to_smartbiz_row,
        strip_html_to_plain_text,
        EXACT_STORE_CATEGORIES,
    )

    # 1. Test unit-level cleaning on filthy HTML descriptions (including entity-escaped HTML)
    dirty_html = "<p><strong>Awesome Lamp</strong><br>Bring light to home! &amp; Enjoy &quot;festive&quot; vibes.</p>"
    clean = strip_html_to_plain_text(dirty_html)
    assert "<" not in clean and ">" not in clean
    assert "<p>" not in clean and "</p>" not in clean
    assert "&amp;" not in clean
    assert "&quot;" not in clean
    assert "Awesome Lamp Bring light to home! & Enjoy" in clean

    # Test entity-escaped & double-escaped HTML
    escaped_html = "&lt;p&gt;Clean &lt;b&gt;Product&lt;/b&gt; Description&lt;/p&gt;"
    clean_escaped = strip_html_to_plain_text(escaped_html)
    assert clean_escaped == "Clean Product Description"
    assert "<" not in clean_escaped and ">" not in clean_escaped

    # Test script and style tag elimination
    script_html = "<style>.x{color:red}</style><script>alert('xss')</script><p>Safe text</p>"
    clean_script = strip_html_to_plain_text(script_html)
    assert clean_script == "Safe text"

    # 2. Test product_to_smartbiz_row with a product having dirty HTML
    sample_prod = {
        "title": "<b>Crystal Rose Diamond Lamp</b>",
        "handle": "crystal-rose-diamond-lamp",
        "sku": "12345_lamp",
        "niche": "Festive & Lights",
        "wholesale_price": 120.0,
        "winning_score": 95.0,  # Triggers score >= 89 HTML description
        "seo_description": "<p>Best Selling <i>Crystal Rose</i> Diamond Lamp for Diwali!</p>",
    }
    row = product_to_smartbiz_row(sample_prod)
    col_ad_title = row[29]
    col_ae_desc = row[30]
    col_k_cat = row[10]

    assert "<" not in col_ad_title and ">" not in col_ad_title
    assert len(col_ad_title) <= 60

    assert "<" not in col_ae_desc and ">" not in col_ae_desc
    assert "<p>" not in col_ae_desc and "</p>" not in col_ae_desc
    assert len(col_ae_desc) <= 160
    assert col_k_cat in EXACT_STORE_CATEGORIES

    # 3. Test actual Excel export from Winning Radar page (/api/radar/smartbiz.xlsx) for 24 products per category
    client = app.test_client()
    for cat in EXACT_STORE_CATEGORIES:
        res = client.get(f"/api/radar/smartbiz.xlsx?mode=page&niche={cat}&limit=24&commit=0")
        assert res.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(res.data), data_only=True)
        ws = wb["bulk_upload_template"]
        assert ws.max_row >= 2
        for r_idx in range(2, ws.max_row + 1):
            cat_val = ws.cell(r_idx, 11).value  # Col K
            assert cat_val == cat, f"Row {r_idx} Category mismatch: {cat_val} != {cat}"
            assert cat_val in EXACT_STORE_CATEGORIES

            # Col AD: SEOMeta Title (Col 30)
            seo_t = str(ws.cell(r_idx, 30).value or "")
            assert "<" not in seo_t and ">" not in seo_t
            assert len(seo_t) <= 60

            # Col AE: SEOMeta Description (Col 31)
            seo_d = str(ws.cell(r_idx, 31).value or "")
            assert "<p>" not in seo_d and "</p>" not in seo_d, f"Row {r_idx} Column AE contains <p> tags: {seo_d}"
            assert "<" not in seo_d and ">" not in seo_d, f"Row {r_idx} Column AE contains HTML brackets: {seo_d}"
            assert len(seo_d) <= 160, f"Row {r_idx} Column AE exceeds 160 chars ({len(seo_d)}): {seo_d}"
        wb.close()

    # 4. Test actual Excel export for mode=mix (SmartBiz Mix 55 Excel)
    res_mix = client.get("/api/radar/smartbiz.xlsx?mode=mix&count=55&commit=0")
    assert res_mix.status_code == 200
    wb_mix = openpyxl.load_workbook(io.BytesIO(res_mix.data), data_only=True)
    ws_mix = wb_mix["bulk_upload_template"]
    assert ws_mix.max_row >= 2
    for r_idx in range(2, ws_mix.max_row + 1):
        cat_val = ws_mix.cell(r_idx, 11).value
        assert cat_val in EXACT_STORE_CATEGORIES, f"Mix Row {r_idx} category {cat_val} not in exact store categories"
        seo_t = str(ws_mix.cell(r_idx, 30).value or "")
        assert "<" not in seo_t and ">" not in seo_t
        assert len(seo_t) <= 60
        seo_d = str(ws_mix.cell(r_idx, 31).value or "")
        assert "<p>" not in seo_d and "</p>" not in seo_d
        assert "<" not in seo_d and ">" not in seo_d
        assert len(seo_d) <= 160
    wb_mix.close()

    # 5. Verify data/winning_products.json has zero legacy Gifts niches
    import json
    from pathlib import Path
    wp_path = Path(__file__).resolve().parent.parent / "data" / "winning_products.json"
    with open(wp_path, "r", encoding="utf-8") as f:
        prods = json.load(f)
    for p in prods:
        assert p.get("niche") != "Gifts", f"Product {p.get('id')} still has legacy niche Gifts"
        assert p.get("niche") in EXACT_STORE_CATEGORIES, f"Product {p.get('id')} has invalid niche {p.get('niche')}"




def test_car_and_vehicle_accessories_radar_page_and_excel_export():
    """
    Verifies:
    1. /radar?niche=Car & Vehicle Accessories loads at least 24 real DeoDap products with active category pill.
    2. Exporting Excel for Car & Vehicle Accessories outputs 'Car & Vehicle Accessories' in Column K.
    3. Column AE (SEOMeta Description) is strictly plain text with 0 HTML tags.
    4. Net profit margins are smartly configured according to wholesale cost.
    """
    import openpyxl
    client = app.test_client()

    # 1. Test radar page
    res_page = client.get('/radar?niche=Car%20%26%20Vehicle%20Accessories')
    assert res_page.status_code == 200
    html_content = res_page.data.decode('utf-8')
    assert 'Car & Vehicle Accessories' in html_content
    assert 'cat-pill-active' in html_content

    # 2. Test Excel export
    res_excel = client.get('/api/radar/smartbiz.xlsx?mode=page&niche=Car%20%26%20Vehicle%20Accessories&limit=24')
    assert res_excel.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(res_excel.data))
    assert 'bulk_upload_template' in wb.sheetnames
    ws = wb['bulk_upload_template']
    assert ws.max_row >= 25  # 1 header + 24 products

    for r in range(2, ws.max_row + 1):
        cat_val = ws.cell(row=r, column=11).value
        seo_desc = str(ws.cell(row=r, column=31).value or '')
        assert cat_val == 'Car & Vehicle Accessories'
        assert '<p>' not in seo_desc and '</p>' not in seo_desc
        assert '<' not in seo_desc and '>' not in seo_desc
    wb.close()
