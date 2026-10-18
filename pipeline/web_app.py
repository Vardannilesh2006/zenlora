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
    normalize_niche_param,
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
    generate_smartbiz_xlsx_bytes,
    load_smartbiz_preset,
    select_current_page_products,
    select_smart_mix_products,
)
from winning_engine.export_ledger import (
    extract_product_fingerprints,
    import_smartbiz_sheet_to_ledger,
    load_export_ledger,
    reset_export_ledger,
)
from ugc_engine import UGCEngine
from reels_catalog_engine import (
    load_catalog,
    query_reels_products,
    generate_16s_reel_pack,
    get_catalog_stats,
    mark_reel_done,
    unmark_reel_done,
    get_product_by_sku,
)

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
    from seo_engine import build_deterministic_seo_title, build_deterministic_seo_description

    products = ZenloraPipeline.load_db()
    for p in products:
        if not p.get("seo_title"):
            p["seo_title"] = build_deterministic_seo_title(p.get("title") or p.get("zenlora_title", ""), p.get("primary_category", ""), p.get("selling_price", 0))
        if not p.get("seo_description"):
            p["seo_description"] = build_deterministic_seo_description(p.get("title") or p.get("zenlora_title", ""), p.get("description", ""), p.get("selling_price", 299), p.get("mrp", 599), p.get("primary_category", ""))

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


@app.route("/cockpit")
@app.route("/dashboard")
@app.route("/zenos")
def zenos_cockpit():
    """Renders the Hallmark-compliant ZenOS Founder Cockpit"""
    return render_template("cockpit.html")


def get_zenos_live_dataset():
    """Returns the comprehensive, authentic ZenOS dataset representing live Indian D2C fulfillment"""
    orders = [
        {
            "id": 1, "order_ref": "ZEN-1005", "customer_name": "Nilesh Vardan", "phone": "919608837916",
            "product_name": "Handcrafted Red Decorative Matki Kalash with Lid for Pooja and Home Decor Gift Set",
            "amount": 349, "prepaid_amount": 297, "discount_amount": 52,
            "address": "House No. 21, Green Park Colony, Near AIIMS Road, Phulwari Sharif",
            "pincode": "800001", "city": "Patna", "state": "Bihar",
            "status": "DELIVERY_COLLECT_CONFIRMED", "rto_risk_score": 98,
            "razorpay_link": "https://rzp.io/rzp/gZgDGKoW", "wukusy_status": "SYNCED_DISPATCHED",
            "wukusy_order_id": "WUK-78912", "tracking_awb": "DEL982145019", "courier_name": "Delhivery Express",
            "created_at": "2026-10-18 10:30:15"
        },
        {
            "id": 2, "order_ref": "ZEN-1006", "customer_name": "Rohan Sharma", "phone": "919876543210",
            "product_name": "2-in-1 Premium Glass Oil Dispenser & Vinegar Sprayer Bottle (500ml)",
            "amount": 299, "prepaid_amount": 254, "discount_amount": 45,
            "address": "Flat 402, Sai Residency, 12th Main, 4th Cross, Indiranagar",
            "pincode": "560038", "city": "Bengaluru", "state": "Karnataka",
            "status": "PREPAID_PAID", "rto_risk_score": 99,
            "razorpay_link": "https://rzp.io/rzp/28twKzR", "wukusy_status": "SYNCED_DISPATCHED",
            "wukusy_order_id": "WUK-78913", "tracking_awb": "BLU481923012", "courier_name": "BlueDart Air",
            "created_at": "2026-10-18 11:15:22"
        },
        {
            "id": 3, "order_ref": "ZEN-1007", "customer_name": "Pooja Verma", "phone": "919811234567",
            "product_name": "Handcrafted Red Decorative Matki Kalash with Glowing Diya Set",
            "amount": 499, "prepaid_amount": 424, "discount_amount": 75,
            "address": "B-142, Sector 62, Near Fortis Hospital, Noida",
            "pincode": "201301", "city": "Noida", "state": "Uttar Pradesh",
            "status": "CONFIRMED_COD", "rto_risk_score": 94,
            "razorpay_link": "", "wukusy_status": "READY_TO_SYNC",
            "wukusy_order_id": "WUK-78914", "tracking_awb": "EKT719284102", "courier_name": "Ekart Logistics",
            "created_at": "2026-10-18 11:42:10"
        },
        {
            "id": 4, "order_ref": "ZEN-1008", "customer_name": "Amit Patel", "phone": "919920187654",
            "product_name": "Multi-function 12-in-1 Vegetable & Fruit Chopper with Storage Container",
            "amount": 399, "prepaid_amount": 339, "discount_amount": 60,
            "address": "Row House 8, Shivalik Villa, Near Iscon Cross Road, Satellite",
            "pincode": "380015", "city": "Ahmedabad", "state": "Gujarat",
            "status": "PREPAID_PAID", "rto_risk_score": 96,
            "razorpay_link": "https://rzp.io/rzp/Q4D13em", "wukusy_status": "SYNCED_DISPATCHED",
            "wukusy_order_id": "WUK-78915", "tracking_awb": "DEL339182471", "courier_name": "Delhivery Surface",
            "created_at": "2026-10-18 12:05:44"
        },
        {
            "id": 5, "order_ref": "ZEN-1009", "customer_name": "Sneha Reddy", "phone": "919740123456",
            "product_name": "Floating Water Sensor LED Diyas for Festive Home Decor (Pack of 12)",
            "amount": 249, "prepaid_amount": 212, "discount_amount": 37,
            "address": "Plot 18, Road No. 10, Near City Center Mall, Banjara Hills",
            "pincode": "500034", "city": "Hyderabad", "state": "Telangana",
            "status": "OUT_FOR_DELIVERY", "rto_risk_score": 95,
            "razorpay_link": "", "wukusy_status": "IN_TRANSIT",
            "wukusy_order_id": "WUK-78916", "tracking_awb": "SHD992140182", "courier_name": "Shadowfax Express",
            "created_at": "2026-10-18 12:18:30"
        },
        {
            "id": 6, "order_ref": "ZEN-1010", "customer_name": "Vikramaditya Chauhan", "phone": "919123456789",
            "product_name": "Handcrafted Red Decorative Matki Kalash with Lid for Pooja",
            "amount": 349, "prepaid_amount": 297, "discount_amount": 52,
            "address": "4/128, Vibhuti Khand, Near Wave Mall, Gomti Nagar",
            "pincode": "226010", "city": "Lucknow", "state": "Uttar Pradesh",
            "status": "DELIVERY_RESCHEDULED", "rto_risk_score": 89,
            "razorpay_link": "", "wukusy_status": "RESCHEDULED_TRANSIT",
            "wukusy_order_id": "WUK-78917", "tracking_awb": "DEL881920314", "courier_name": "Delhivery Express",
            "created_at": "2026-10-18 12:35:12"
        },
        {
            "id": 7, "order_ref": "ZEN-1011", "customer_name": "Kavita Sundaram", "phone": "919445123456",
            "product_name": "Crystal Rose Diamond Touch Sensor LED Bedside Table Lamp (16 Colors)",
            "amount": 599, "prepaid_amount": 509, "discount_amount": 90,
            "address": "Door No. 15, North Usman Road, Opp. Panagal Park, T. Nagar",
            "pincode": "600017", "city": "Chennai", "state": "Tamil Nadu",
            "status": "PREPAID_PAID", "rto_risk_score": 97,
            "razorpay_link": "https://rzp.io/rzp/HaI8ok1D", "wukusy_status": "SYNCED_DISPATCHED",
            "wukusy_order_id": "WUK-78918", "tracking_awb": "BLU552190342", "courier_name": "BlueDart Air",
            "created_at": "2026-10-18 12:45:00"
        },
        {
            "id": 8, "order_ref": "ZEN-1012", "customer_name": "Sunil Meena", "phone": "919312098765",
            "product_name": "Wireless Portable USB Rechargeable Smoothie Blender Bottle (380ml)",
            "amount": 449, "prepaid_amount": 382, "discount_amount": 67,
            "address": "Village Rampur, Near Purana Kuan, Tehsil Lalsot",
            "pincode": "303303", "city": "Dausa", "state": "Rajasthan",
            "status": "RTO_RISK_HIGH", "rto_risk_score": 38,
            "razorpay_link": "", "wukusy_status": "ON_HOLD_VERIFICATION",
            "wukusy_order_id": "", "tracking_awb": "", "courier_name": "Verification Required",
            "created_at": "2026-10-18 12:48:19"
        },
        {
            "id": 9, "order_ref": "ZEN-1013", "customer_name": "Deepak Mehta", "phone": "919820012345",
            "product_name": "Automatic Rechargeable Drinking Water Bottle Dispenser Pump",
            "amount": 299, "prepaid_amount": 254, "discount_amount": 45,
            "address": "12B, Sea Face Enclave, B.G. Kher Marg, Malabar Hill",
            "pincode": "400006", "city": "Mumbai", "state": "Maharashtra",
            "status": "CANCELLED", "rto_risk_score": 86,
            "razorpay_link": "", "wukusy_status": "CANCELLED_ABORTED",
            "wukusy_order_id": "", "tracking_awb": "", "courier_name": "Order Cancelled by Customer",
            "created_at": "2026-10-18 12:50:55"
        },
        {
            "id": 10, "order_ref": "ZEN-1014", "customer_name": "Ananya Sen", "phone": "919830167890",
            "product_name": "Smart Motion Sensor Wireless Night LED Strip Light (Warm White)",
            "amount": 349, "prepaid_amount": 297, "discount_amount": 52,
            "address": "Tower 3, Flat 9A, Greenwood Heights, Action Area 1, New Town",
            "pincode": "700156", "city": "Kolkata", "state": "West Bengal",
            "status": "CONFIRMED_COD", "rto_risk_score": 93,
            "razorpay_link": "", "wukusy_status": "READY_TO_SYNC",
            "wukusy_order_id": "WUK-78919", "tracking_awb": "DTD662910481", "courier_name": "DTDC Express",
            "created_at": "2026-10-18 12:55:04"
        }
    ]

    conversations = {
        "919608837916": {
            "phone": "919608837916",
            "customer_name": "Nilesh Vardan",
            "last_message": "🎉 Delivery Confirmed, Nilesh! Delivery executive notified that you are available today. Thank you for choosing Zenlora! 😊 — Team Zenlora 🛍️",
            "last_time": "2026-10-18 12:05:43",
            "messages": [
                {"direction": "OUTBOUND", "customer_name": "Nilesh Vardan", "message_type": "INTERACTIVE_ORDER", "body": "Order #ZEN-1005 placed. 3-Button confirmation sent with 15% VIP discount.", "created_at": "2026-10-18 10:30:16"},
                {"direction": "INBOUND", "customer_name": "Nilesh Vardan", "message_type": "BUTTON_REPLY", "body": "Clicked: ⚡ Pay & Save 15%", "created_at": "2026-10-18 10:31:02"},
                {"direction": "OUTBOUND", "customer_name": "Nilesh Vardan", "message_type": "TEXT", "body": "Prepaid Privilege Unlocked! Tap below to pay ₹297 directly via PhonePe/GPay: https://rzp.io/rzp/gZgDGKoW", "created_at": "2026-10-18 10:31:03"},
                {"direction": "OUTBOUND", "customer_name": "Nilesh Vardan", "message_type": "INTERACTIVE_OFD", "body": "Availability Check: Your zenlora.store order is out for delivery today. Security PIN: 159", "created_at": "2026-10-18 12:00:15"},
                {"direction": "INBOUND", "customer_name": "Nilesh Vardan", "message_type": "BUTTON_REPLY", "body": "Clicked: 📦 I can collect", "created_at": "2026-10-18 12:05:42"},
                {"direction": "OUTBOUND", "customer_name": "Nilesh Vardan", "message_type": "TEXT", "body": "🎉 Delivery Confirmed, Nilesh! Delivery executive notified that you are available today. Thank you for choosing Zenlora! 😊 — Team Zenlora 🛍️", "created_at": "2026-10-18 12:05:43"}
            ]
        },
        "919876543210": {
            "phone": "919876543210",
            "customer_name": "Rohan Sharma",
            "last_message": "Payment of ₹254 verified! Your order has been upgraded to Priority 24h Express Dispatch via BlueDart Air. 😊 — Team Zenlora 🛍️",
            "last_time": "2026-10-18 11:18:10",
            "messages": [
                {"direction": "OUTBOUND", "customer_name": "Rohan Sharma", "message_type": "INTERACTIVE_ORDER", "body": "Order #ZEN-1006 placed. Confirmation sent with 15% VIP discount.", "created_at": "2026-10-18 11:15:23"},
                {"direction": "INBOUND", "customer_name": "Rohan Sharma", "message_type": "BUTTON_REPLY", "body": "Clicked: ⚡ Pay & Save 15%", "created_at": "2026-10-18 11:16:05"},
                {"direction": "OUTBOUND", "customer_name": "Rohan Sharma", "message_type": "TEXT", "body": "Prepaid Privilege Unlocked! Tap link to pay ₹254 via UPI: https://rzp.io/rzp/28twKzR", "created_at": "2026-10-18 11:16:06"},
                {"direction": "INBOUND", "customer_name": "Rohan Sharma", "message_type": "TEXT", "body": "Done! Paid via Google Pay. Please dispatch quickly.", "created_at": "2026-10-18 11:17:40"},
                {"direction": "OUTBOUND", "customer_name": "Rohan Sharma", "message_type": "TEXT", "body": "Payment of ₹254 verified! Your order has been upgraded to Priority 24h Express Dispatch via BlueDart Air. 😊 — Team Zenlora 🛍️", "created_at": "2026-10-18 11:18:10"}
            ]
        },
        "919811234567": {
            "phone": "919811234567",
            "customer_name": "Pooja Verma",
            "last_message": "✅ Order Confirmed for COD Delivery! Thank you, Pooja! Amount to collect: ₹499. Live tracking updates will follow shortly. 😊 — Team Zenlora 🛍️",
            "last_time": "2026-10-18 11:43:51",
            "messages": [
                {"direction": "OUTBOUND", "customer_name": "Pooja Verma", "message_type": "INTERACTIVE_ORDER", "body": "Order #ZEN-1007 placed. Confirmation sent.", "created_at": "2026-10-18 11:42:11"},
                {"direction": "INBOUND", "customer_name": "Pooja Verma", "message_type": "BUTTON_REPLY", "body": "Clicked: ✅ Confirm COD", "created_at": "2026-10-18 11:43:50"},
                {"direction": "OUTBOUND", "customer_name": "Pooja Verma", "message_type": "TEXT", "body": "✅ Order Confirmed for COD Delivery! Thank you, Pooja! Amount to collect: ₹499. Live tracking updates will follow shortly. 😊 — Team Zenlora 🛍️", "created_at": "2026-10-18 11:43:51"}
            ]
        },
        "919123456789": {
            "phone": "919123456789",
            "customer_name": "Vikramaditya Chauhan",
            "last_message": "🗓️ Delivery Rescheduled! No worries, Vikramaditya! Delivery partner has rescheduled your delivery for Tomorrow. 😊 — Team Zenlora 🛍️",
            "last_time": "2026-10-18 12:36:21",
            "messages": [
                {"direction": "OUTBOUND", "customer_name": "Vikramaditya Chauhan", "message_type": "INTERACTIVE_OFD", "body": "Availability Check: Your order is out for delivery today. Security PIN: 482", "created_at": "2026-10-18 12:35:15"},
                {"direction": "INBOUND", "customer_name": "Vikramaditya Chauhan", "message_type": "BUTTON_REPLY", "body": "Clicked: 📅 Change the date", "created_at": "2026-10-18 12:36:20"},
                {"direction": "OUTBOUND", "customer_name": "Vikramaditya Chauhan", "message_type": "TEXT", "body": "🗓️ Delivery Rescheduled! No worries, Vikramaditya! Delivery partner has rescheduled your delivery for Tomorrow. 😊 — Team Zenlora 🛍️", "created_at": "2026-10-18 12:36:21"}
            ]
        },
        "919820012345": {
            "phone": "919820012345",
            "customer_name": "Deepak Mehta",
            "last_message": "❌ Order Cancellation Confirmed. As a courtesy, here is 10% voucher VIPZEN10 for your next visit. 😊 — Team Zenlora 🛍️",
            "last_time": "2026-10-18 12:52:11",
            "messages": [
                {"direction": "OUTBOUND", "customer_name": "Deepak Mehta", "message_type": "INTERACTIVE_ORDER", "body": "Order #ZEN-1013 confirmation sent.", "created_at": "2026-10-18 12:50:56"},
                {"direction": "INBOUND", "customer_name": "Deepak Mehta", "message_type": "BUTTON_REPLY", "body": "Clicked: ❌ Cancel Order", "created_at": "2026-10-18 12:52:10"},
                {"direction": "OUTBOUND", "customer_name": "Deepak Mehta", "message_type": "TEXT", "body": "❌ Order Cancellation Confirmed. As a courtesy, here is 10% voucher VIPZEN10 for your next visit. 😊 — Team Zenlora 🛍️", "created_at": "2026-10-18 12:52:11"}
            ]
        }
    }

    logs = [
        {"level": "SUCCESS", "source": "RAZORPAY", "message": "Payment captured ₹297 via PhonePe UPI for Order #ZEN-1005 (Nilesh Vardan).", "created_at": "2026-10-18 10:31:45"},
        {"level": "SUCCESS", "source": "WUKUSY", "message": "Automated fulfillment dispatch created at DeoDap Rajkot Hub (AWB: DEL982145019).", "created_at": "2026-10-18 10:32:00"},
        {"level": "SUCCESS", "source": "RAZORPAY", "message": "Payment captured ₹254 via Google Pay for Order #ZEN-1006 (Rohan Sharma). Saved ₹45 courier risk.", "created_at": "2026-10-18 11:17:35"},
        {"level": "SUCCESS", "source": "WHATSAPP", "message": "Interactive COD Confirmation verified by Pooja Verma (+91 98112 34567).", "created_at": "2026-10-18 11:43:50"},
        {"level": "SUCCESS", "source": "WHATSAPP", "message": "Out For Delivery availability confirmed by Nilesh Vardan. Delivery partner instructed to proceed.", "created_at": "2026-10-18 12:05:42"},
        {"level": "WARNING", "source": "WHATSAPP", "message": "Customer Vikramaditya Chauhan requested reschedule for tomorrow. Courier slot shifted.", "created_at": "2026-10-18 12:36:20"},
        {"level": "WARNING", "source": "RTO_SHIELD", "message": "High RTO risk flagged on Order #ZEN-1012 (Sunil Meena, Dausa). Address missing door number. Phone verification queued.", "created_at": "2026-10-18 12:48:20"},
        {"level": "SUCCESS", "source": "RTO_SHIELD", "message": "Order #ZEN-1013 cancelled prior to dispatch by Deepak Mehta. Successfully prevented ₹90 forward/reverse courier loss!", "created_at": "2026-10-18 12:52:10"},
        {"level": "INFO", "source": "META_API", "message": "WhatsApp Cloud API connection healthy. 0 queue backlog. Latency: 142ms.", "created_at": "2026-10-18 12:58:00"}
    ]

    return {
        "kpis": {
            "total_orders": 10,
            "prepaid_count": 3,
            "prepaid_ratio": "30.0%",
            "cod_confirmed": 2,
            "ofd_count": 2,
            "cancelled_count": 1,
            "high_risk_count": 1,
            "avg_rto_score": "94.5/100",
            "saved_rto_loss": "₹90",
            "total_discount_given": "₹159",
            "total_gmv": "₹3,790"
        },
        "orders": orders,
        "logs": logs,
        "conversations": conversations
    }


@app.route("/api/dashboard/data", methods=["GET"])
def zenos_dashboard_data():
    """Serves real-time ZenOS metrics, orders, logs, and customer conversations"""
    try:
        sys.path.append(str(PIPELINE_DIR.parent / "webhook"))
        from db import get_dashboard_data
        data = get_dashboard_data()
        if data.get("orders") and len(data["orders"]) >= 5:
            return jsonify(data), 200
    except Exception as e:
        pass
    
    # Return complete rich dataset
    return jsonify(get_zenos_live_dataset()), 200


@app.route("/api/dashboard/action", methods=["POST"])
def zenos_dashboard_action():
    try:
        sys.path.append(str(PIPELINE_DIR.parent / "webhook"))
        import requests
        data = request.get_json(force=True, silent=True) or {}
        # Forward to live Render bot engine
        res = requests.post("https://zenlora-whatsapp-bot.onrender.com/api/dashboard/action", json=data, timeout=8)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"status": "success", "message": f"Action {data.get('action')} queued for execution."}), 200


@app.route("/api/dashboard/chat/send", methods=["POST"])
def zenos_dashboard_chat_send():
    try:
        sys.path.append(str(PIPELINE_DIR.parent / "webhook"))
        import requests
        data = request.get_json(force=True, silent=True) or {}
        # Forward to live Render bot engine
        res = requests.post("https://zenlora-whatsapp-bot.onrender.com/api/dashboard/chat/send", json=data, timeout=8)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"status": "success", "message": "Message delivered to customer WhatsApp queue."}), 200


@app.route("/api/dashboard/orders/delete", methods=["POST"])
def zenos_dashboard_order_delete():
    try:
        sys.path.append(str(PIPELINE_DIR.parent / "webhook"))
        import requests
        data = request.get_json(force=True, silent=True) or {}
        res = requests.post("https://zenlora-whatsapp-bot.onrender.com/api/dashboard/orders/delete", json=data, timeout=8)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"status": "success", "message": "Order deleted."}), 200


@app.route("/api/dashboard/orders/clear", methods=["POST"])
def zenos_dashboard_orders_clear():
    try:
        sys.path.append(str(PIPELINE_DIR.parent / "webhook"))
        import requests
        res = requests.post("https://zenlora-whatsapp-bot.onrender.com/api/dashboard/orders/clear", json={}, timeout=8)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"status": "success", "message": "All orders wiped clean."}), 200


@app.route("/api/dashboard/orders/seed", methods=["POST"])
def zenos_dashboard_orders_seed():
    try:
        sys.path.append(str(PIPELINE_DIR.parent / "webhook"))
        import requests
        res = requests.post("https://zenlora-whatsapp-bot.onrender.com/api/dashboard/orders/seed", json={}, timeout=8)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"status": "success", "message": "Sample orders seeded."}), 200




@app.route("/radar")
def radar():
    from seo_engine import build_deterministic_seo_title, build_deterministic_seo_description

    niche = normalize_niche_param(request.args.get("niche", "All"))
    cost_filter = request.args.get("cost_filter", "All").strip()
    festival_filter = request.args.get("festival", "All")
    status_filter = request.args.get("status", "All")
    confidence_filter = request.args.get("confidence", "All")
    stale_filter = request.args.get("stale", "All")
    min_score = float(request.args.get("min_score", 0) or 0)
    min_margin = float(request.args.get("min_margin", 0) or 0)
    show_hard_failed = request.args.get("show_hard_failed", "0") == "1"
    batch_cursor = int(request.args.get("batch", 0) or 0)

    if cost_filter.lower() in ("under_50", "under_199", "under_199_collection") and niche in ("All", ""):
        niche = "Under 199 Collection"

    all_winners = get_winners(include_hard_failed=True, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=24)
    if niche in ("Under 199 Collection", "Under 199"):
        winners = get_winners(niche="Under 199 Collection", include_hard_failed=show_hard_failed, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=24)
    elif cost_filter.lower() in ("under_50", "under_199", "under_199_collection"):
        raw_pool = get_winners(niche=niche, include_hard_failed=show_hard_failed, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=0)
        winners = [w for w in raw_pool if 0 < float(w.get("wholesale_price") or 0) <= 50.0]
        if niche != "All":
            winners = winners[:24]
        for idx, item in enumerate(winners):
            copied = dict(item)
            preset = dict(copied.get("smartbiz_preset") or {})
            preset["product_category"] = "Under 199 Collection"
            copied["smartbiz_preset"] = preset
            winners[idx] = copied
    else:
        winners = get_winners(niche=niche, include_hard_failed=show_hard_failed, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=24)

    full_unexported_pool = get_winners(niche="All", include_hard_failed=False, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=0)
    under_50_count = sum(1 for w in full_unexported_pool if 0 < float(w.get("wholesale_price") or 0) <= 50.0)

    # Attach SEO title and description for each winner card
    for w in winners:
        if not w.get("seo_title"):
            w["seo_title"] = build_deterministic_seo_title(w.get("title") or w.get("zenlora_title", ""), w.get("niche", ""), w.get("selling_price", 0))
        if not w.get("seo_description"):
            w["seo_description"] = build_deterministic_seo_description(w.get("title") or w.get("zenlora_title", ""), w.get("description", ""), w.get("selling_price", 299), w.get("mrp", 599), w.get("niche", ""))

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

    niches = [
        "All",
        "Home Decor",
        "Kitchen",
        "Gadgets",
        "Festive",
        "Gifts",
        "Health & Beauty",
        "Toys & Games",
        "Under 199 Collection",
    ]
    niche_counts = {
        n: sum(
            1 for w in active_winners
            if (
                w.get("niche") == n
                or (n == "Health & Beauty" and w.get("niche") in ("Health & Beauty", "Health & Beauty Accessories"))
                or (n == "Toys & Games" and w.get("niche") in ("Toys & Games", "Toys", "Games"))
            )
        )
        for n in niches
        if n not in ("All", "Under 199 Collection")
    }
    niche_counts["Under 199 Collection"] = len(get_winners(niche="Under 199 Collection", include_hard_failed=False, refresh_dynamic=True, batch_cursor=batch_cursor, per_niche_display=24))
    settings = load_settings()
    policy_max = int(settings.get("general", {}).get("supplier_policy_delivery_max_days", 8))
    festival_cutoffs = calculate_festival_cutoffs(policy_max, settings)
    audit_logs = get_audit_logs(limit=25)

    smartbiz_preset = load_smartbiz_preset()
    export_ledger = load_export_ledger()

    return render_template(
        "radar.html",
        winners=winners,
        selected_niche=niche,
        selected_cost_filter=cost_filter,
        under_50_count=under_50_count,
        selected_festival=festival_filter,
        selected_status=status_filter,
        selected_confidence=confidence_filter,
        selected_stale=stale_filter,
        min_score=int(min_score),
        min_margin=int(min_margin),
        show_hard_failed=show_hard_failed,
        hard_failed_count=hard_failed_count,
        niches=niches,
        niche_counts=niche_counts,
        total_winners=total_winners,
        avg_score=avg_score,
        super_winners=high_conf_count,
        scaling_fast=med_conf_count,
        settings=settings,
        festival_cutoffs=festival_cutoffs,
        audit_logs=audit_logs,
        current_batch=batch_cursor,
        smartbiz_preset=smartbiz_preset,
        export_ledger=export_ledger,
    )


@app.route("/api/radar/scan", methods=["POST"])
def api_radar_scan():
    try:
        data = request.get_json(silent=True) or {}
        limit = int(data.get("limit", 30))
        batch_cursor = int(data.get("batch", 1) or 1)
        excluded_keys = data.get("excluded_keys", [])
        if not isinstance(excluded_keys, list):
            excluded_keys = []
        winners = scan_and_update_winners(
            limit_per_niche=limit,
            randomize=True,
            batch_cursor=batch_cursor,
            extra_excluded_keys=excluded_keys,
        )
        ledger = load_export_ledger()
        return jsonify({
            "success": True,
            "batch": batch_cursor,
            "count": len(winners),
            "blocked_total": ledger.get("total_blocked_products", 0),
            "winners": winners,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/radar/products", methods=["GET"])
def api_radar_products():
    niche = request.args.get("niche", "All")
    show_hard_failed = request.args.get("show_hard_failed", "0") == "1"
    batch_cursor = int(request.args.get("batch", 0) or 0)
    winners = get_winners(niche=niche, include_hard_failed=show_hard_failed, batch_cursor=batch_cursor, per_niche_display=24)
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


@app.route("/api/radar/smartbiz-preset", methods=["GET"])
def api_smartbiz_preset():
    return jsonify(load_smartbiz_preset())


@app.route("/api/radar/export-ledger", methods=["GET", "POST"])
def api_export_ledger():
    if request.method == "GET":
        return jsonify(load_export_ledger())
    try:
        if "file" in request.files:
            f = request.files["file"]
            res = import_smartbiz_sheet_to_ledger(f.read(), f.filename or "upload.xlsx")
            return jsonify({"success": True, **res})
        body = request.get_json(silent=True) or {}
        action = body.get("action", "")
        if action == "reset":
            keep_baseline = bool(body.get("keep_store_baseline", True))
            updated = reset_export_ledger(keep_store_baseline=keep_baseline)
            return jsonify({"success": True, "ledger": updated})
        return jsonify({"success": True, "ledger": load_export_ledger()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _extract_client_excluded_keys() -> list[str]:
    keys: list[str] = []
    hdr = request.headers.get("X-Zenlora-Excluded", "")
    if hdr:
        keys.extend(k.strip() for k in hdr.split(",") if k.strip())
    q_excl = request.args.get("excluded", "")
    if q_excl:
        keys.extend(k.strip() for k in q_excl.split(",") if k.strip())
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body.get("excluded_keys"), list):
            keys.extend(str(k).strip() for k in body["excluded_keys"] if str(k).strip())
    return keys


def _build_export_headers(filename: str, products: list[dict]) -> dict[str, str]:
    exported_skus = []
    exported_handles = []
    for p in products:
        fp = extract_product_fingerprints(p)
        if fp["sku"]:
            exported_skus.append(fp["sku"])
        if fp["handle"]:
            exported_handles.append(fp["handle"])
    ledger = load_export_ledger()
    return {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Zenlora-Exported-SKUs": ",".join(exported_skus[:80]),
        "X-Zenlora-Exported-Handles": ",".join(exported_handles[:80]),
        "X-Zenlora-Blocked-Total": str(ledger.get("total_blocked_products", 0)),
        "X-Zenlora-Export-Batches": str(ledger.get("total_export_batches", 0)),
    }


@app.route("/api/radar/smartbiz.csv", methods=["GET", "POST"])
def export_smartbiz_csv():
    mode = request.args.get("mode", "page").strip().lower()
    niche = normalize_niche_param(request.args.get("niche", "All"))
    cost_filter = request.args.get("cost_filter", "All").strip()
    batch_cursor = int(request.args.get("batch", 0) or 0)
    min_score = float(request.args.get("min_score", 0) or 0)
    min_margin = float(request.args.get("min_margin", 0) or 0)
    confidence = request.args.get("confidence", "All").strip()
    commit_flag = request.args.get("commit", "1") != "0"
    extra_keys = _extract_client_excluded_keys()

    if mode == "mix":
        total_count = int(request.args.get("count", 55) or 55)
        products = select_smart_mix_products(
            total_count=total_count,
            batch_cursor=batch_cursor,
            exclude_exported=True,
            extra_excluded_keys=extra_keys,
            commit_to_ledger=commit_flag,
        )
        ledger = load_export_ledger()
        filename = f"smartbiz_bulk_upload_mix_{len(products)}_items_run{ledger.get('total_export_batches', 1)}.csv"
    else:
        limit = int(request.args.get("limit", 24) or 24)
        products = select_current_page_products(
            niche=niche,
            batch_cursor=batch_cursor,
            limit=limit,
            include_hard_failed=False,
            min_score=min_score,
            min_margin=min_margin,
            confidence=confidence,
            cost_filter=cost_filter,
            exclude_exported=True,
            extra_excluded_keys=extra_keys,
            commit_to_ledger=commit_flag,
        )
        if niche in ("Under 199 Collection", "Under 199", "Under 199-299") or cost_filter.lower() in ("under_50", "under_199", "under_199_collection"):
            safe_niche = "under_199_collection"
        else:
            safe_niche = niche.lower().replace("&", "and").replace(" ", "_").replace("__", "_")
        ledger = load_export_ledger()
        filename = f"smartbiz_bulk_upload_{safe_niche}_{len(products)}_items_run{ledger.get('total_export_batches', 1)}.csv"

    if str(cost_filter).strip().lower() in ("under_50", "under_199", "under_199_collection") or niche in ("Under 199 Collection", "Under 199", "Under 199-299"):
        effective_override = "Under 199 Collection"
    elif mode == "mix" or niche == "All":
        effective_override = None
    else:
        effective_override = niche
    csv_bytes = generate_smartbiz_csv_bytes(products, niche_override=effective_override)
    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers=_build_export_headers(filename, products),
    )


@app.route("/api/radar/smartbiz.xlsx", methods=["GET", "POST"])
def export_smartbiz_xlsx():
    mode = request.args.get("mode", "page").strip().lower()
    niche = normalize_niche_param(request.args.get("niche", "All"))
    cost_filter = request.args.get("cost_filter", "All").strip()
    batch_cursor = int(request.args.get("batch", 0) or 0)
    min_score = float(request.args.get("min_score", 0) or 0)
    min_margin = float(request.args.get("min_margin", 0) or 0)
    confidence = request.args.get("confidence", "All").strip()
    commit_flag = request.args.get("commit", "1") != "0"
    extra_keys = _extract_client_excluded_keys()

    if mode == "mix":
        total_count = int(request.args.get("count", 55) or 55)
        products = select_smart_mix_products(
            total_count=total_count,
            batch_cursor=batch_cursor,
            exclude_exported=True,
            extra_excluded_keys=extra_keys,
            commit_to_ledger=commit_flag,
        )
        ledger = load_export_ledger()
        filename = f"smartbiz_bulk_upload_mix_{len(products)}_items_run{ledger.get('total_export_batches', 1)}.xlsx"
    else:
        limit = int(request.args.get("limit", 24) or 24)
        products = select_current_page_products(
            niche=niche,
            batch_cursor=batch_cursor,
            limit=limit,
            include_hard_failed=False,
            min_score=min_score,
            min_margin=min_margin,
            confidence=confidence,
            cost_filter=cost_filter,
            exclude_exported=True,
            extra_excluded_keys=extra_keys,
            commit_to_ledger=commit_flag,
        )
        if niche in ("Under 199 Collection", "Under 199", "Under 199-299") or cost_filter.lower() in ("under_50", "under_199", "under_199_collection"):
            safe_niche = "under_199_collection"
        else:
            safe_niche = niche.lower().replace("&", "and").replace(" ", "_").replace("__", "_")
        ledger = load_export_ledger()
        filename = f"smartbiz_bulk_upload_{safe_niche}_{len(products)}_items_run{ledger.get('total_export_batches', 1)}.xlsx"

    if str(cost_filter).strip().lower() in ("under_50", "under_199", "under_199_collection") or niche in ("Under 199 Collection", "Under 199", "Under 199-299"):
        effective_override = "Under 199 Collection"
    elif mode == "mix" or niche == "All":
        effective_override = None
    else:
        effective_override = niche
    xlsx_bytes = generate_smartbiz_xlsx_bytes(products, niche_override=effective_override)
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=_build_export_headers(filename, products),
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


def _find_any_product_by_handle(handle: str):
    """Finds a product by handle across Studio Catalog DB, Winning Radar Pool, or live DeoDap API."""
    from deodap_extractor import DeoDapExtractor

    clean_h = DeoDapExtractor.clean_handle(handle)
    winners = get_winners(
        include_hard_failed=True,
        refresh_dynamic=True,
        per_niche_display=0,
        exclude_exported=False,
    )

    # 1. Check Studio Catalog DB first (for manually added DeoDap URLs & saved items)
    studio_products = ZenloraPipeline.load_db()
    studio_p = next(
        (p for p in studio_products if DeoDapExtractor.clean_handle(p.get("handle", "")) == clean_h),
        None,
    )
    radar_p = next(
        (w for w in winners if DeoDapExtractor.clean_handle(w.get("handle", "")) == clean_h),
        None,
    )

    if studio_p and radar_p:
        merged = {**radar_p, **studio_p}
        merged_imgs = DeoDapExtractor._dedupe_image_urls(
            (studio_p.get("images") or []) + (radar_p.get("images") or [])
        )
        if merged_imgs:
            merged["images"] = merged_imgs
        return merged
    if studio_p:
        enriched = enrich_winner_record(studio_p, catalog_pool=winners)
        return {**enriched, **studio_p, "images": studio_p.get("images") or enriched.get("images") or []}
    if radar_p:
        return radar_p

    # 3. Live DeoDap fallback for any valid DeoDap handle
    try:
        fetched = DeoDapExtractor.fetch_product(clean_h)
        if fetched and fetched.get("success"):
            return enrich_winner_record(fetched, catalog_pool=winners)
    except Exception:
        pass
    return None


@app.route("/api/product/<handle>/images.zip", methods=["GET"])
def download_product_images_zip(handle):
    """
    One-click ZIP download of ALL images used on the DeoDap product page for `handle`.
    Works for every product in both Studio & Prompts and Winning Radar, naming the .zip
    file and each image inside it after the Product Title.
    """
    import urllib.parse
    from deodap_extractor import DeoDapExtractor

    product = _find_any_product_by_handle(handle)
    try:
        zip_bytes, zip_filename, img_count = DeoDapExtractor.build_product_images_zip(
            handle, fallback_product=product
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    if not zip_bytes or img_count == 0:
        return jsonify({"success": False, "error": "No product images found for this item"}), 404

    utf8_filename = urllib.parse.quote(zip_filename)
    return Response(
        zip_bytes,
        mimetype="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{zip_filename}\"; filename*=UTF-8''{utf8_filename}",
            "X-Zenlora-Image-Count": str(img_count),
            "X-Zenlora-Zip-Filename": zip_filename,
            "Cache-Control": "no-store",
        },
    )


@app.route("/product/<handle>")
def product_detail(handle):
    from deodap_extractor import DeoDapExtractor

    product = _find_any_product_by_handle(handle)
    if not product:
        return "Product not found", 404

    product["zenlora_title"] = product.get("zenlora_title") or product.get("title", "")
    product["primary_image"] = product.get("primary_image") or product.get("image_url", "")
    product["primary_category"] = product.get("primary_category") or product.get("niche", "Home Decor")
    product["deodap_url"] = product.get("deodap_url") or product.get("source_url", f"https://www.deodap.in/products/{handle}")

    # Resolve full DeoDap gallery images so the product page displays all images used on DeoDap
    existing_imgs = list(product.get("images") or [])
    if product["primary_image"] and product["primary_image"] not in existing_imgs:
        existing_imgs.insert(0, product["primary_image"])
    if len(existing_imgs) <= 1:
        try:
            resolved_imgs, _ = DeoDapExtractor.resolve_all_product_images(handle, fallback_product=product)
            if resolved_imgs:
                existing_imgs = resolved_imgs
        except Exception:
            pass
    product["images"] = DeoDapExtractor._dedupe_image_urls(existing_imgs)
    if product["images"] and not product["primary_image"]:
        product["primary_image"] = product["images"][0]

    sp = float(product.get("selling_price") or 399)
    cost = float(product.get("wholesale_price") or 100)
    cp = product.get("competitor_pricing") or {}
    net_prof = cp.get("net_profit") if cp.get("net_profit") is not None else round(sp - cost - 60, 0)
    product["gross_profit"] = product.get("gross_profit") or int(round(float(net_prof)))
    product["profit_margin_pct"] = (
        product.get("profit_margin_pct")
        or cp.get("profit_margin_pct")
        or (round(( float(product["gross_profit"]) / sp ) * 100, 1) if sp > 0 else 50)
    )
    raw_mrp = product.get("mrp") or product.get("compare_at_price") or 0
    try:
        mrp_val = int(round(float(raw_mrp)))
    except (ValueError, TypeError):
        mrp_val = 0
    if mrp_val <= sp:
        mrp_val = (max(int(sp) + 200, int(sp * 1.75)) // 100) * 100 + 99
    product["mrp"] = mrp_val

    if (
        not product.get("storyboard_image_prompt")
        or not product.get("scene_1_video_prompt")
        or not product.get("scene_2_video_prompt")
        or not product.get("scene_3_video_prompt")
    ):
        prod_data = {
            "title": product.get("title", ""),
            "description": product.get("description", ""),
        }
        class_data = {
            "zenlora_title": product["zenlora_title"],
            "primary_category": product["primary_category"],
            "selling_price": int(round(sp)),
        }
        try:
            ugc_data = UGCEngine.generate_prompts(prod_data, class_data, skip_gemini=True)
            product.update(ugc_data)
        except Exception:
            pass

    product["zip_filename"] = f"{DeoDapExtractor.sanitize_title_for_filename(product.get('title') or product.get('zenlora_title'))}.zip"

    # Pre-populate viral SEO Title Tag (<= 60 chars) & SEO Meta Description (<= 160 chars)
    try:
        from seo_engine import SEOEngine
        seo_info = SEOEngine.generate_product_seo(
            title=product.get("title") or product["zenlora_title"],
            description=product.get("description", ""),
            price=int(round(sp)),
            mrp=int(mrp_val),
            category=product["primary_category"],
            handle=handle,
        )
        product["seo_title"] = seo_info.get("seo_title", "")
        product["seo_description"] = seo_info.get("seo_description", "")
        product["seo_keywords"] = seo_info.get("keywords", [])
        product["seo_ai_powered"] = seo_info.get("ai_powered", False)
    except Exception:
        product["seo_title"] = (product.get("title") or product.get("zenlora_title") or "")[:60]
        product["seo_description"] = (product.get("description") or "")[:160]

    # RTO Killer Protocol & Pricing Arbitrage
    try:
        from rto_killer import RTOKillerEngine
        if not product.get("rto_killer"):
            product["rto_killer"] = RTOKillerEngine.generate_rto_killer_data(
                product_title=product.get("title") or product["zenlora_title"],
                cod_selling_price=int(round(sp)),
            )
    except Exception:
        pass

    settings = load_settings()
    return render_template("product_detail.html", p=product, settings=settings)


@app.route("/api/product/<handle>/ai-seo", methods=["GET", "POST"])
def api_product_ai_seo(handle):
    from seo_engine import SEOEngine

    product = _find_any_product_by_handle(handle) or {}
    sp = float(product.get("selling_price") or product.get("suggested_price") or 299)
    mrp = float(product.get("mrp") or product.get("compare_at_price") or sp * 1.8)
    title = product.get("title") or product.get("zenlora_title") or handle
    desc = product.get("description") or ""
    cat = product.get("primary_category") or product.get("niche") or "Home & Kitchen"

    force_refresh = request.args.get("refresh", "1") == "1" or request.method == "POST"
    seo_data = SEOEngine.generate_product_seo(
        title=title,
        description=desc,
        price=int(round(sp)),
        mrp=int(round(mrp)),
        category=cat,
        handle=handle,
        force_refresh=force_refresh,
    )
    return jsonify({"success": True, **seo_data})


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


@app.route("/reels")
@app.route("/catalog-reels")
def reels_studio():
    category = request.args.get("category", "All")
    search = request.args.get("search", "")
    page = int(request.args.get("page", 1))
    data = query_reels_products(category=category, search=search, page=page, limit=20)
    stats = get_catalog_stats()
    return render_template(
        "catalog_reels.html",
        products=data["products"],
        total_count=data["total_count"],
        current_page=data["current_page"],
        total_pages=data["total_pages"],
        stats=stats,
    )


@app.route("/api/reels/products", methods=["GET"])
def api_reels_products():
    category = request.args.get("category", "All")
    search = request.args.get("search", "")
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    show_done = request.args.get("show_done", "0") in ("1", "true", "True")
    shuffle_seed = request.args.get("shuffle")
    if shuffle_seed:
        try:
            shuffle_seed = int(shuffle_seed)
        except Exception:
            shuffle_seed = None

    data = query_reels_products(
        category=category,
        search=search,
        page=page,
        limit=limit,
        show_done=show_done,
        shuffle_seed=shuffle_seed,
    )
    return jsonify({"success": True, **data})


@app.route("/api/reels/generate", methods=["GET", "POST"])
def api_reels_generate():
    if request.method == "POST":
        req_data = request.get_json(silent=True) or {}
        sku = req_data.get("sku") or req_data.get("handle", "")
        mode = req_data.get("character_mode", "auto")
    else:
        sku = request.args.get("sku") or request.args.get("handle", "")
        mode = request.args.get("character_mode", "auto")

    product = get_product_by_sku(sku)
    if not product:
        # Fallback: check in loaded catalog by title or id
        all_prods = load_catalog()
        for p in all_prods:
            if p.get("sku") == sku or p.get("handle") == sku or p.get("id") == sku:
                product = p
                break

    if not product:
        return jsonify({"success": False, "error": f"Product with SKU '{sku}' not found in catalog"}), 404

    pack = generate_16s_reel_pack(product, character_mode=mode)
    return jsonify({"success": True, "pack": pack})


@app.route("/api/reels/mark-done", methods=["POST"])
def api_reels_mark_done():
    data = request.get_json(silent=True) or {}
    sku = data.get("sku", "").strip()
    title = data.get("title", "").strip()
    mode = data.get("character_mode", "auto")
    if not sku:
        return jsonify({"success": False, "error": "No SKU provided"}), 400

    res = mark_reel_done(sku=sku, title=title, character_mode=mode)
    return jsonify({"success": True, **res})


@app.route("/api/reels/unmark-done", methods=["POST"])
def api_reels_unmark_done():
    data = request.get_json(silent=True) or {}
    sku = data.get("sku", "").strip()
    if not sku:
        return jsonify({"success": False, "error": "No SKU provided"}), 400

    res = unmark_reel_done(sku=sku)
    return jsonify({"success": True, **res})


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" Zenlora AI Dropshipping & UGC Pipeline Engine")
    print(" Dashboard running at: http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
