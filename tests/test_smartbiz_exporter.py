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

        # Col J (9) & Col K (10): Business Category & Product Category
        b_cat = row[9]
        p_cat = row[10]
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

        # Col U (20): Best Seller is "Yes" or ""
        assert row[20] in ("Yes", "")

        # Cols W-AB (22..27): Product Images must not have .webp or ? query strings
        for img_col in row[22:28]:
            if img_col:
                assert "?" not in img_col
                assert img_col.lower().endswith((".jpg", ".jpeg", ".png"))

        # Cols AD (29) & AE (30): SEOMeta Title <= 60, SEOMeta Description <= 160
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
