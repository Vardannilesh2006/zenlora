import csv
import io
import json
import os
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.append(str(PIPELINE_DIR))

from pipeline_controller import ZenloraPipeline
from config import EXPORTS_DIR
from winning_engine.radar_controller import (
    get_winners,
    scan_and_update_winners,
    import_to_studio,
    enrich_winner_record,
)
from winning_engine.data_models import (
    load_settings,
    save_settings,
    save_product_manual_entry,
    get_audit_logs,
    calculate_festival_cutoffs,
)
from winning_engine.trend_checker import get_google_trends_analysis
from winning_engine.competitor_pricing import get_competitor_price_intelligence
from winning_engine.gemini_analyzer import analyze_with_gemini
from winning_engine.smartbiz_exporter import (
    generate_smartbiz_csv_bytes,
    select_current_page_products,
    select_smart_mix_products,
)
from ugc_engine import UGCEngine

app = Flask(
    __name__,
    template_folder=str(PIPELINE_DIR / "templates"),
    static_folder=str(PIPELINE_DIR / "static"),
)
app.config["SECRET_KEY"] = "zenlora-luxury-dropshipping-2026"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True


@app.route("/favicon.ico")
def favicon():
    ico_path = PIPELINE_DIR / "static" / "favicon.ico"
    if ico_path.exists():
        return send_file(ico_path, mimetype="image/x-icon")
    return send_file(PIPELINE_DIR / "static" / "favicon.svg", mimetype="image/svg+xml")


@app.route("/")
def index():
    products = ZenloraPipeline.load_db()
    total_products = len(products)
    total_profit = sum(p.get("gross_profit", 0) for p in products)
    avg_margin = (
        round(sum(p.get("profit_margin_pct", 0) for p in products) / total_products, 1)
        if total_products > 0
        else 0
    )
    return render_template(
        "index.html",
        products=products,
        total_products=total_products,
        total_profit=total_profit,
        avg_margin=avg_margin,
    )


@app.route("/radar")
def radar():
    niche = request.args.get("niche", "All")
    festival_filter = request.args.get("festival", "All")
    status_filter = request.args.get("status", "All")
    confidence_filter = request.args.get("confidence", "All")
    stale_filter = request.args.get("stale", "All")
    min_score = float(request.args.get("min_score", 0) or 0)
    min_margin = float(request.args.get("min_margin", 0) or 0)
    show_hard_failed = request.args.get("show_hard_failed", "0") == "1"
    batch_cursor = int(request.args.get("batch", 0) or 0)

    all_winners = get_winners(include_hard_failed=True, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=12)
    winners = get_winners(niche=niche, include_hard_failed=show_hard_failed, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=12)

    # Apply dashboard filters
    if festival_filter != "All":
        winners = [w for w in winners if festival_filter.lower() in str(w.get("festival_mood", "")).lower()]
    if status_filter != "All":
        winners = [
            w for w in winners
            if str(w.get("sample_tracking", {}).get("status", "shortlisted")).lower() == status_filter.lower()
        ]
    if confidence_filter != "All":
        winners = [w for w in winners if str(w.get("confidence", "")).lower() == confidence_filter.lower()]
    if stale_filter == "stale":
        winners = [w for w in winners if w.get("is_stale")]
    elif stale_filter == "fresh":
        winners = [w for w in winners if not w.get("is_stale")]
    if min_score > 0:
        winners = [w for w in winners if float(w.get("winning_score", 0)) >= min_score]
    if min_margin > 0:
        winners = [
            w for w in winners
            if float(w.get("competitor_pricing", {}).get("net_profit", w.get("gross_profit", 0))) >= min_margin
        ]

    active_winners = [w for w in all_winners if not w.get("is_hard_failed", False)]
    hard_failed_count = sum(1 for w in all_winners if w.get("is_hard_failed", False))
    total_winners = len(active_winners)
    avg_score = (
        round(sum(w.get("winning_score", 0) for w in active_winners) / total_winners, 1)
        if total_winners > 0
        else 0
    )
    high_conf_count = sum(1 for w in active_winners if w.get("confidence") == "High")
    med_conf_count = sum(1 for w in active_winners if w.get("confidence") == "Medium")

    niches = ["All", "Home Decor", "Kitchen", "Gadgets", "Festive", "Gifts"]
    settings = load_settings()
    policy_max = int(settings.get("general", {}).get("supplier_policy_delivery_max_days", 8))
    festival_cutoffs = calculate_festival_cutoffs(policy_max, settings)
    audit_logs = get_audit_logs(limit=25)

    return render_template(
        "radar.html",
        winners=winners,
        selected_niche=niche,
        selected_festival=festival_filter,
        selected_status=status_filter,
        selected_confidence=confidence_filter,
        selected_stale=stale_filter,
        min_score=int(min_score),
        min_margin=int(min_margin),
        show_hard_failed=show_hard_failed,
        hard_failed_count=hard_failed_count,
        niches=niches,
        total_winners=total_winners,
        avg_score=avg_score,
        super_winners=high_conf_count,
        scaling_fast=med_conf_count,
        settings=settings,
        festival_cutoffs=festival_cutoffs,
        audit_logs=audit_logs,
        current_batch=batch_cursor,
    )


@app.route("/api/radar/scan", methods=["POST"])
def api_radar_scan():
    try:
        data = request.get_json(silent=True) or {}
        limit = int(data.get("limit", 30))
        batch_cursor = int(data.get("batch", 1) or 1)
        winners = scan_and_update_winners(limit_per_niche=limit, randomize=True, batch_cursor=batch_cursor)
        return jsonify({
            "success": True,
            "batch": batch_cursor,
            "count": len(winners),
            "winners": winners,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/radar/products", methods=["GET"])
def api_radar_products():
    niche = request.args.get("niche", "All")
    show_hard_failed = request.args.get("show_hard_failed", "0") == "1"
    batch_cursor = int(request.args.get("batch", 0) or 0)
    winners = get_winners(niche=niche, include_hard_failed=show_hard_failed, batch_cursor=batch_cursor, per_niche_display=12)
    return jsonify(winners)


@app.route("/api/radar/export.json", methods=["GET"])
def export_radar_json():
    niche = request.args.get("niche", "All")
    winners = get_winners(niche=niche, include_hard_failed=True, per_niche_display=0)
    payload = {
        "exported_at": winners[0].get("scanned_at") if winners else None,
        "count": len(winners),
        "settings_used": load_settings(),
        "products": winners,
    }
    return Response(
        json.dumps(payload, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=zenlora_shortlist_provenance.json"},
    )


@app.route("/api/radar/export.csv", methods=["GET"])
def export_radar_csv():
    niche = request.args.get("niche", "All")
    winners = get_winners(niche=niche, include_hard_failed=True, per_niche_display=0)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Handle", "Title", "Category", "Sample Status", "Score (0-100)", "Confidence",
        "Data Coverage", "Supplier Cost (INR)", "Selling Price (INR)", "Landed Cost (My Assumptions)",
        "Net Profit (INR)", "In Stock", "Weight (g)", "Dimensions", "Supplier Source URL",
        "Fetched At", "Method", "Meta Ads Count (Manual)", "Meta Ads URL",
        "Google Trends Label", "Google Trends URL", "Instagram Views (Manual)", "Instagram URL",
        "Amazon Price", "Flipkart Price", "Meesho Price", "Hard Failed", "Hard Fail Reasons"
    ])
    for w in winners:
        cp = w.get("competitor_pricing", {})
        mkt = cp.get("marketplaces", {})
        writer.writerow([
            w.get("handle"),
            w.get("title"),
            w.get("niche"),
            w.get("sample_tracking", {}).get("status", "shortlisted"),
            w.get("winning_score"),
            w.get("confidence"),
            w.get("data_coverage", {}).get("summary_label"),
            w.get("wholesale_price"),
            w.get("selling_price"),
            cp.get("landed_cost"),
            cp.get("net_profit"),
            w.get("in_stock"),
            w.get("weight_grams") if w.get("weight_grams") is not None else "null",
            w.get("dimensions") if w.get("dimensions") is not None else "null",
            w.get("source_url"),
            w.get("fetched_at"),
            w.get("method"),
            w.get("meta_ads", {}).get("active_ads_count") if w.get("meta_ads", {}).get("active_ads_count") is not None else "null",
            w.get("meta_ads", {}).get("ad_library_url"),
            w.get("trends", {}).get("trend_label"),
            w.get("trends", {}).get("trends_url"),
            w.get("social", {}).get("views") if w.get("social", {}).get("views") is not None else "null",
            w.get("social", {}).get("instagram_url"),
            mkt.get("amazon", {}).get("price") or "null",
            mkt.get("flipkart", {}).get("price") or "null",
            mkt.get("meesho", {}).get("price") or "null",
            w.get("is_hard_failed", False),
            "; ".join(w.get("hard_fail_reasons", [])),
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=zenlora_shortlist_provenance.csv"},
    )


@app.route("/api/radar/smartbiz.csv", methods=["GET"])
def export_smartbiz_csv():
    mode = request.args.get("mode", "page").strip().lower()
    niche = request.args.get("niche", "All").strip()
    batch_cursor = int(request.args.get("batch", 0) or 0)

    if mode == "mix":
        total_count = int(request.args.get("count", 55) or 55)
        products = select_smart_mix_products(total_count=total_count, batch_cursor=batch_cursor)
        filename = f"smartbiz_bulk_upload_mix_{len(products)}_items_batch{batch_cursor}.csv"
    else:
        limit = int(request.args.get("limit", 20) or 20)
        products = select_current_page_products(
            niche=niche,
            batch_cursor=batch_cursor,
            limit=limit,
            include_hard_failed=False,
        )
        safe_niche = niche.lower().replace(" ", "_")
        filename = f"smartbiz_bulk_upload_{safe_niche}_{len(products)}_items_batch{batch_cursor}.csv"

    csv_bytes = generate_smartbiz_csv_bytes(products)
    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify(load_settings())
    try:
        new_cfg = request.get_json(silent=True) or {}
        current = load_settings()
        for k, v in new_cfg.items():
            if isinstance(v, dict) and isinstance(current.get(k), dict):
                current[k].update(v)
            else:
                current[k] = v
        saved = save_settings(current, log_change=True)
        return jsonify({"success": True, "settings": saved})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/audit-log", methods=["GET"])
def api_audit_log():
    return jsonify(get_audit_logs(limit=100))


@app.route("/api/product/<handle>/manual", methods=["POST"])
def api_save_manual_entry(handle):
    try:
        body = request.get_json(silent=True) or {}
        section = body.get("section", "").strip()
        payload = body.get("payload", {})
        if not section:
            return jsonify({"success": False, "error": "Missing section name"}), 400
        saved = save_product_manual_entry(handle, section, payload)
        return jsonify({"success": True, "manual_entry": saved})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/product/<handle>/fetch-demand", methods=["POST"])
def api_fetch_live_demand(handle):
    try:
        winners = get_winners(include_hard_failed=True, refresh_dynamic=False, per_niche_display=0)
        prod = next((w for w in winners if w.get("handle") == handle), None)
        kw = prod.get("meta_ads", {}).get("keyword") if prod else handle.replace("-", " ")
        niche = prod.get("niche", "Festive") if prod else "Festive"
        res = get_google_trends_analysis(kw, niche, fetch_live=True)
        return jsonify({"success": True, "trends": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/product/<handle>/fetch-prices", methods=["POST"])
def api_fetch_live_prices(handle):
    try:
        winners = get_winners(include_hard_failed=True, refresh_dynamic=False, per_niche_display=0)
        prod = next((w for w in winners if w.get("handle") == handle), None)
        title = prod.get("title", handle) if prod else handle
        cost = float(prod.get("wholesale_price", 100.0)) if prod else 100.0
        niche = prod.get("niche", "Festive") if prod else "Festive"
        cp = get_competitor_price_intelligence(title, cost, niche, handle=handle, fetch_live=True)
        return jsonify({"success": True, "competitor_pricing": cp})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/product/<handle>/ai-opinion", methods=["POST"])
def api_fetch_ai_opinion(handle):
    try:
        winners = get_winners(include_hard_failed=True, refresh_dynamic=False, per_niche_display=0)
        prod = next((w for w in winners if w.get("handle") == handle), None)
        if not prod:
            return jsonify({"success": False, "error": "Product not found"}), 404
        gem = analyze_with_gemini(
            prod.get("title", ""),
            prod.get("niche", "Festive"),
            float(prod.get("wholesale_price") or 100.0),
            float(prod.get("selling_price") or 399.0),
            prod.get("description", ""),
        )
        return jsonify({"success": True, "gemini": gem})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/radar/import/<handle>", methods=["POST"])
def api_radar_import(handle):
    try:
        imported_product = import_to_studio(handle)
        return jsonify({
            "success": True,
            "product": imported_product,
            "message": f"Product '{imported_product.get('title')}' imported to Studio!",
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/product/<handle>")
def product_detail(handle):
    winners = get_winners(include_hard_failed=True, refresh_dynamic=True, per_niche_display=0)
    product = next((w for w in winners if w.get("handle") == handle), None)

    if not product:
        products = ZenloraPipeline.load_db()
        studio_p = next((p for p in products if p.get("handle") == handle), None)
        if studio_p:
            product = enrich_winner_record(studio_p, catalog_pool=winners)

    if not product:
        return "Product not found", 404

    if not product.get("storyboard_image_prompt") or not product.get("scene_1_video_prompt"):
        prod_data = {
            "title": product.get("title", ""),
            "description": product.get("description", ""),
        }
        class_data = {
            "zenlora_title": product.get("zenlora_title", product.get("title", "")),
            "primary_category": product.get("primary_category", product.get("niche", "Home Decor")),
            "selling_price": product.get("selling_price", 399),
        }
        try:
            ugc_data = UGCEngine.generate_prompts(prod_data, class_data, skip_gemini=True)
            product.update(ugc_data)
        except Exception:
            pass

    product["primary_image"] = product.get("primary_image") or product.get("image_url", "")
    product["primary_category"] = product.get("primary_category") or product.get("niche", "Home Decor")
    settings = load_settings()

    return render_template("product_detail.html", p=product, settings=settings)


@app.route("/api/process", methods=["POST"])
def process_single():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400
    try:
        record = ZenloraPipeline.process_url(url)
        return jsonify({"success": True, "product": record})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/process-batch", methods=["POST"])
def process_batch():
    data = request.get_json(silent=True) or {}
    urls_raw = data.get("urls", "")
    if isinstance(urls_raw, str):
        urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
    elif isinstance(urls_raw, list):
        urls = urls_raw
    else:
        urls = []

    if not urls:
        return jsonify({"success": False, "error": "No URLs provided"}), 400

    results = ZenloraPipeline.process_batch(urls)
    successful = [r for r in results if r.get("success", False) is not False and not r.get("error")]
    return jsonify({
        "success": True,
        "processed_count": len(successful),
        "results": results,
    })


@app.route("/api/products", methods=["GET"])
def get_products():
    return jsonify(ZenloraPipeline.load_db())


@app.route("/api/products/<handle>", methods=["DELETE"])
def delete_product(handle):
    deleted = ZenloraPipeline.delete_product(handle)
    return jsonify({"success": deleted})


@app.route("/api/clear", methods=["POST"])
def clear_db():
    ZenloraPipeline.clear_db()
    return jsonify({"success": True})


@app.route("/api/export-excel", methods=["GET"])
def export_excel():
    try:
        filepath = ZenloraPipeline.export_excel()
        return send_file(
            filepath,
            as_attachment=True,
            download_name=os.path.basename(filepath),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" Zenlora AI Dropshipping & UGC Pipeline Engine")
    print(" Dashboard running at: http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
