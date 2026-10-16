import os
import json
import pytest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PIPELINE_DIR = BASE_DIR / "pipeline"

import sys
sys.path.append(str(PIPELINE_DIR))

from reels_catalog_engine import (
    load_catalog,
    query_reels_products,
    generate_16s_reel_pack,
    get_catalog_stats,
    mark_reel_done,
    unmark_reel_done,
    get_product_by_sku,
    recommend_character_mode,
)
from web_app import app
from config import CONTINUITY_PROMPT


def test_catalog_loaded_and_complete():
    products = load_catalog()
    assert len(products) >= 5, f"Expected at least 5 products, got {len(products)}"
    first = products[0]
    assert "sku" in first and first["sku"]
    assert "title" in first and first["title"]
    assert "selling_price" in first and first["selling_price"] > 0
    assert "mrp" in first and first["mrp"] >= first["selling_price"]
    assert "category" in first and first["category"]
    assert "image_url" in first


def test_catalog_stats():
    stats = get_catalog_stats()
    assert stats["total_products"] >= 5
    assert stats["done_reels"] >= 0
    assert stats["remaining_reels"] == stats["total_products"] - stats["done_reels"]
    assert len(stats["categories"]) >= 1  # at least one category present


def test_query_reels_products_20_per_page():
    res = query_reels_products(category="All", page=1, limit=20)
    assert len(res["products"]) <= 20
    assert res["limit"] == 20
    assert res["current_page"] == 1
    assert res["total_pages"] >= 1


def test_query_reels_search():
    products = load_catalog()
    sample = products[0]
    token = sample["title"].split()[0]
    res = query_reels_products(search=token)
    assert len(res["products"]) >= 1
    assert any(token.lower() in p["title"].lower() for p in res["products"])


def test_mark_and_unmark_done_lifecycle():
    products = load_catalog()
    test_prod = products[5]
    sku = test_prod["sku"]

    # Mark done
    res = mark_reel_done(sku=sku, title=test_prod["title"], character_mode="female_creator")
    assert res["status"] == "success"
    assert res["is_done"] is True

    # Query without search and without show_done: product MUST be hidden
    query_res = query_reels_products(search="", show_done=False, limit=500)
    found_skus = [p["sku"] for p in query_res["products"]]
    assert sku not in found_skus, f"Marked SKU {sku} should be hidden from browse view"

    # Query with show_done=True: product should be present with is_done=True
    query_res_done = query_reels_products(search="", show_done=True, limit=500)
    matching = [p for p in query_res_done["products"] if p["sku"] == sku]
    assert len(matching) == 1
    assert matching[0]["is_done"] is True

    # Unmark done to restore clean state
    unmark_res = unmark_reel_done(sku=sku)
    assert unmark_res["status"] == "success"
    assert unmark_res["is_done"] is False


def test_generate_16s_reel_pack_dual_act_and_continuity():
    products = load_catalog()
    prod = products[0]

    # Test Female Creator Mode
    pack = generate_16s_reel_pack(prod, character_mode="female_creator")
    assert pack["duration_seconds"] == 16
    assert pack["character_mode"] == "female_creator"
    
    # Storyboard Grid Prompt
    assert "6-panel" in pack["storyboard_grid_prompt"].lower()
    assert "panel 1" in pack["storyboard_grid_prompt"].lower()
    assert "panel 6" in pack["storyboard_grid_prompt"].lower()

    # Act 1 (0-8s)
    act1 = pack["acts"]["act_1"]["prompt"]
    assert "0 to 8 Seconds" in act1
    assert "ANCHOR FRAME" in act1

    # Act 2 (8-16s) with CONTINUITY_PROMPT
    act2 = pack["acts"]["act_2"]["prompt"]
    assert CONTINUITY_PROMPT in act2
    assert "8 to 16 Seconds" in act2

    # Voiceover Script
    vo_hinglish = pack["voiceover_script"]["hinglish"]
    assert len(vo_hinglish) > 30
    assert "Zenlora" in vo_hinglish or "link" in vo_hinglish.lower()
    assert 25 <= pack["voiceover_script"]["word_count"] <= 60

    # Viral Engagement Pack
    assert len(pack["hooks"]) >= 3
    assert len(pack["cta_keyword"]) >= 2
    assert "#zenlora" in pack["hashtags"].lower()
    assert len(pack["recommendation_keywords"]) >= 5
    assert pack["store_url"].startswith("https://www.zenlora.store/product/")


def test_character_mode_toggle_asmr():
    products = load_catalog()
    prod = products[0]
    pack = generate_16s_reel_pack(prod, character_mode="asmr_hands")
    assert pack["character_mode"] == "asmr_hands"
    assert "ASMR" in pack["acts"]["act_1"]["prompt"]
    assert CONTINUITY_PROMPT in pack["acts"]["act_2"]["prompt"]


def test_web_routes():
    client = app.test_client()

    # Test /reels HTML page
    res = client.get("/reels")
    assert res.status_code == 200
    assert b"Reels Studio" in res.data
    assert b"16-Second" in res.data

    # Test /api/reels/products
    res = client.get("/api/reels/products?category=All&limit=5")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert len(data["products"]) == 5

    # Test /api/reels/generate
    sample_sku = data["products"][0]["sku"]
    res = client.get(f"/api/reels/generate?sku={sample_sku}&character_mode=female_creator")
    assert res.status_code == 200
    gen_data = res.get_json()
    assert gen_data["success"] is True
    assert gen_data["pack"]["duration_seconds"] == 16
    assert CONTINUITY_PROMPT in gen_data["pack"]["acts"]["act_2"]["prompt"]
