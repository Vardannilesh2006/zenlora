import os
import json
import logging
import re
import hmac
import hashlib
import secrets
from pathlib import Path
from datetime import datetime
import requests
from flask import Flask, request, jsonify, render_template, redirect, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if not os.getenv("VERCEL"):
    from dotenv import load_dotenv
    load_dotenv(Path(BASE_DIR) / ".env")

from db import (
    init_db,
    get_dashboard_data,
    save_or_update_order,
    update_order_status,
    record_message,
    log_event,
    get_order,
    get_confirmed_wukusy_orders,
    get_last_inbound_at,
    claim_webhook_event,
    get_crm_conversations,
    get_crm_thread,
)
from services.address_validator import evaluate_address_health, generate_address_fix_prompt
from services.whatsapp_openwa import (
    send_openwa_text,
    send_openwa_image,
    dispatch_order_confirmation as openwa_dispatch_order_confirmation,
    dispatch_rto_killer_prepay as openwa_dispatch_rto_killer_prepay,
    dispatch_rto_killer_rs50_prepay as openwa_dispatch_rto_killer_rs50_prepay,
    dispatch_address_fix_request as openwa_dispatch_address_fix_request,
    dispatch_ofd_confirmation as openwa_dispatch_ofd_confirmation,
    dispatch_shipping_tracking as openwa_dispatch_shipping_tracking,
    dispatch_ndr_rescue as openwa_dispatch_ndr_rescue,
    check_gateway_health as openwa_check_gateway_health,
)
from services.whatsapp_waha import (
    dispatch_rto_killer_prepay,
    dispatch_rto_killer_rs50_prepay,
    dispatch_ofd_confirmation,
    dispatch_address_fix_request,
    dispatch_shipping_tracking,
    dispatch_ndr_rescue,
    send_waha_buttons,
    send_waha_text,
    check_gateway_health,
)
from services.ai_concierge import polish_with_ai_concierge

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
from datetime import timedelta
app.secret_key = os.getenv("ZENOS_SESSION_SECRET", "zenos-secret-session-key-nilesh-2006-enterprise-v1")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

init_db()

# Configurations
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "zenlora_secret_token_2026")
ACTIVE_META_TOKEN = "EAAkmfpCGwLUBS0h9A96A3HTdLQyUbwSsOXZBhoLGh841nZCZBDXQpAoBKdXEZBb1HgylePHJESQYCsQoBsVBiAZCRBZB9NWvXWz8UrK4gxem0jUGMZBSbkRgpm5D6d1xZAOgziPzEaj7ZA0jTTeJZAFuNjif8j0koYkMR1FhHepI7m7OUw5GAlsLZC1kO4s0o1o0tOX2xDjipoXZB1AgXTq7z8ZAeVA9NVZCONRbhyRSul4UfjZCWabfYr0gJE7vCS5hEAbShPvMPnogNHDuTH1rRyWcZAiuVCrZC"
env_token = os.getenv("META_ACCESS_TOKEN", "")
WHATSAPP_TOKEN = env_token if (env_token and not env_token.startswith("EAAkmfpCGwLUBS9vTp")) else ACTIVE_META_TOKEN
PHONE_NUMBER_ID = os.getenv("META_PHONE_ID", "1385477007982491")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_live_TowfcuBZZgrDeg")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "RmTDV14cCIK1YxscAlWCYNvq")
META_APP_SECRET = os.getenv("META_APP_SECRET")


@app.before_request
def authorize_request():
    path = request.path
    if path in {"/login", "/logout", "/api/health", "/webhook", "/api/razorpay/webhook"}:
        return None

    extension_paths = {
        "/api/orders/ingest",
        "/api/orders/pending-wukusy",
        "/api/shipping/send-availability-check",
    }
    if path in extension_paths:
        if request.method == "OPTIONS":
            return None
        expected = os.getenv("ZENOS_EXTENSION_API_KEY")
        if expected:
            supplied = request.headers.get("X-ZenOS-Extension-Key", "")
            if not hmac.compare_digest(supplied, expected):
                return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return None

    if path in {"/api/order-webhook", "/api/ofd-webhook"}:
        expected = os.getenv("ZENOS_STORE_WEBHOOK_TOKEN")
        if expected:
            supplied = request.headers.get("X-ZenOS-Webhook-Key", "")
            if not hmac.compare_digest(supplied, expected):
                return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return None

    admin_route = (
        path in {"/", "/zenos", "/cockpit", "/dashboard"}
        or path.startswith("/api/dashboard/")
        or path.startswith("/api/shipping/")
        or path.startswith("/api/ai/")
        or path.startswith("/api/rto/")
        or path.startswith("/api/whatsapp/")
    )
    if admin_route:
        admin_pass = os.getenv("ZENOS_ADMIN_PASSWORD", "Nilesh@2006").strip()
        if not session.get("zenos_admin_authenticated"):
            if path.startswith("/api/"):
                return jsonify({"status": "error", "message": "Authentication required"}), 401
            return redirect(url_for("admin_login", next=request.full_path))
    return None


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    allowed_origins = {
        "https://smartbiz.amazon.in",
        "https://seller.amazon.in",
        "https://sellercentral.amazon.in",
        "https://wukusy.com",
        "https://www.wukusy.com",
        "https://wukusy.app",
        "https://www.wukusy.app",
        "https://deodap.com",
        "https://www.deodap.com",
    }
    if request.path == "/api/health":
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif (
        request.path in {"/api/orders/ingest", "/api/orders/pending-wukusy", "/api/shipping/send-availability-check", "/api/dashboard/data"}
        or request.path.startswith("/api/")
    ):
        if origin and (
            origin in allowed_origins
            or origin.startswith("chrome-extension://")
            or "wukusy.app" in origin
            or "smartbiz.amazon.in" in origin
            or "vercel.app" in origin
            or "localhost" in origin
        ):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PATCH, DELETE"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-ZenOS-Extension-Key, Authorization"
    # Enterprise HTTP Security Headers
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# In-memory IP rate limiter for login
LOGIN_ATTEMPTS = {}  # ip -> {"count": int, "locked_until": datetime}


@app.route("/login", methods=["GET", "POST"])
def admin_login():
    expected = os.getenv("ZENOS_ADMIN_PASSWORD", "Nilesh@2006").strip()
    if not app.secret_key:
        app.secret_key = "zenos-secret-session-key-nilesh-2006-enterprise-v1"

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
    now = datetime.now()

    ip_data = LOGIN_ATTEMPTS.get(client_ip, {"count": 0, "locked_until": None})
    if ip_data.get("locked_until") and ip_data["locked_until"] > now:
        remaining = int((ip_data["locked_until"] - now).total_seconds() / 60) + 1
        return render_template("login.html", configuration_error=False, login_error=False, locked_error=f"Too many failed login attempts. Locked for {remaining} minutes."), 429

    if request.method == "POST":
        supplied = str(request.form.get("password", "")).strip()
        # Accept exact or case-insensitive fallback (Nilesh@2006 or nilesh@2006)
        is_valid = hmac.compare_digest(supplied, expected) or hmac.compare_digest(supplied.lower(), expected.lower())
        if not is_valid:
            ip_data["count"] += 1
            if ip_data["count"] >= 8:
                from datetime import timedelta
                ip_data["locked_until"] = now + timedelta(minutes=15)
                LOGIN_ATTEMPTS[client_ip] = ip_data
                return render_template("login.html", configuration_error=False, login_error=False, locked_error="Too many failed attempts. Account locked for 15 minutes."), 429
            LOGIN_ATTEMPTS[client_ip] = ip_data
            return render_template("login.html", configuration_error=False, login_error=True), 401

        LOGIN_ATTEMPTS.pop(client_ip, None)
        session.clear()
        session.permanent = True
        session["zenos_admin_authenticated"] = True
        session["zenos_csrf_token"] = secrets.token_urlsafe(32)
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("render_cockpit"))
    return render_template("login.html", configuration_error=False, login_error=False)


@app.route("/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

def normalize_whatsapp_phone(raw_phone):
    digits = re.sub(r"\D", "", str(raw_phone or ""))
    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    raise ValueError("Enter a valid Indian mobile number")


def _send_whatsapp_payload(payload):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp Cloud API credentials are not configured")
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if response.ok:
            return response.json()
        logger.warning("Direct Meta API returned %s: %s. Attempting bridge...", response.status_code, response.text)
    except Exception as ex:
        logger.warning("Direct Meta API exception: %s. Attempting bridge...", ex)

    # Resilient fallback via live Render engine (registered with Meta webhook)
    try:
        recipient = payload.get("to", "")
        bridge_url = "https://zenlora-whatsapp-bot.onrender.com/api/order-webhook"
        bridge_res = requests.post(
            bridge_url,
            json={
                "phone": recipient,
                "customer_name": "Valued Customer",
                "order_id": "ZEN-DISPATCH",
                "product_name": "Zenlora Order",
                "amount": 349
            },
            timeout=15
        )
        if bridge_res.ok:
            data = bridge_res.json()
            return data.get("result", data)
    except Exception as bridge_err:
        logger.error("Bridge fallback error: %s", bridge_err)

    raise RuntimeError("WhatsApp Cloud API rejected the message")


def send_whatsapp_message(to_number, text_message):
    try:
        from services.whatsapp_openwa import send_openwa_text
        res = send_openwa_text(to_number, text_message)
        if res.get("delivered") or res.get("status") == "ok":
            return res
    except Exception as ex:
        logger.warning("OpenWA direct send failed: %s. Attempting fallback...", ex)

    payload = {
        "messaging_product": "whatsapp",
        "to": normalize_whatsapp_phone(to_number),
        "type": "text",
        "text": {"body": text_message},
    }
    return _send_whatsapp_payload(payload)


def send_template_message(to_number, template_name, body_parameters, button_payloads):
    if not template_name:
        return None
    components = [{
        "type": "body",
        "parameters": [{"type": "text", "text": str(value)} for value in body_parameters],
    }]
    components.extend({
        "type": "button",
        "sub_type": "quick_reply",
        "index": str(index),
        "parameters": [{"type": "payload", "payload": payload}],
    } for index, payload in enumerate(button_payloads))
    return _send_whatsapp_payload({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalize_whatsapp_phone(to_number),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": os.getenv("META_TEMPLATE_LANGUAGE", "en_US")},
            "components": components,
        },
    })


def send_interactive_order_confirmation(to_phone, customer_name, order_id, product_name, cod_amount):
    amount = int(cod_amount)
    if amount <= 0:
        amount = 349
    order_ref = str(order_id)
    savings = round(amount * 0.15)
    payable = amount - savings
    phone = normalize_whatsapp_phone(to_phone)

    body_text = (
        f"Hi {customer_name}! 👋\n\n"
        f"Thank you for shopping with *Zenlora*. Your order #{order_ref} has been placed successfully!\n\n"
        f"────────────────────────\n"
        f"📦 *Order Summary*\n"
        f"• *Order ID:* #{order_ref}\n"
        f"• *Product:* {product_name}\n"
        f"• *COD Amount:* ₹{amount}\n"
        f"────────────────────────\n\n"
        f"⚡ *Prepaid Privilege Offer:*\n"
        f"Pay online now & get *Flat 15% OFF*\n"
        f"• *Payable Amount:* ₹{payable} (Save ₹{savings})\n"
        f"• *Free Express Delivery* & priority 24h dispatch\n"
        f"• Contactless & 1-tap UPI payment\n\n"
        f"⏱️ _Offer valid for the next 15 minutes._\n\n"
        f"Please choose how you would like to proceed:"
    )

    formatted_msg = (
        body_text + "\n\n"
        "👉 Reply *'YES'* to Confirm COD Order\n"
        "👉 Reply *'PAY'* to Pay Online & Save 15%\n"
        "👉 Reply *'CANCEL'* to Cancel Order"
    )
    return send_whatsapp_message(phone, formatted_msg)


def send_interactive_ofd_check(to_phone, customer_name, order_id, product_name, cod_amount, contact_phone="02242567777"):
    amount = int(cod_amount)
    if amount <= 0:
        amount = 349
    order_ref = str(order_id)
    phone = normalize_whatsapp_phone(to_phone)

    body_text = (
        f"🚚 *Out For Delivery Today!*\n\n"
        f"Hi {customer_name}, your Zenlora order is arriving today!\n\n"
        f"────────────────────────\n"
        f"📦 *Shipment Details*\n"
        f"• *Order ID:* #{order_ref}\n"
        f"• *Product:* {product_name}\n"
        f"• *COD to Pay:* ₹{amount}\n"
        f"• *Security PIN:* 159\n"
        f"────────────────────────\n\n"
        f"To ensure seamless delivery, please confirm if you will be available to collect your order today between *9:00 AM – 8:00 PM*."
    )

    formatted_msg = (
        body_text + "\n\n"
        "👉 Reply *'AVAILABLE'* if you are at home to collect today\n"
        "👉 Reply *'TOMORROW'* to reschedule delivery date\n\n"
        f"Helpline: {contact_phone or '02242567777'}"
    )
    return send_whatsapp_message(phone, formatted_msg)

def create_razorpay_payment_link(original_amount_inr, customer_name, customer_phone, order_ref, discount_pct=15):
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise RuntimeError("Razorpay credentials are not configured")
    amount = int(original_amount_inr)
    if amount <= 0 or not 0 < discount_pct < 100:
        raise ValueError("Invalid payment amount or discount")
    phone = normalize_whatsapp_phone(customer_phone)
    discount_amount = round(amount * (discount_pct / 100.0))
    payable_amount = amount - discount_amount
    payload = {
        "amount": payable_amount * 100,
        "currency": "INR",
        "accept_partial": False,
        "description": f"Zenlora order {order_ref} - prepaid discount",
        "customer": {"name": str(customer_name).strip(), "contact": f"+{phone}"},
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "upi_link": True,
        "notes": {
            "order_ref": str(order_ref),
            "original_cod_amount": str(amount),
            "discount_saved": str(discount_amount),
            "final_paid": str(payable_amount),
        },
    }
    response = requests.post(
        "https://api.razorpay.com/v1/payment_links",
        json=payload,
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
        timeout=15,
    )
    if response.status_code not in (200, 201):
        logger.error("Razorpay rejected payment link creation (HTTP %s)", response.status_code)
        raise RuntimeError("Razorpay rejected payment link creation")
    result = response.json()
    short_url = result.get("short_url")
    if not short_url:
        raise RuntimeError("Razorpay response did not contain a payment link")
    return short_url, payable_amount, discount_amount


@app.route("/api/orders/ingest", methods=["POST", "OPTIONS"])
def api_orders_ingest():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A JSON order payload is required"}), 400

    required = ("order_ref", "customer_name", "phone", "product_name", "amount")
    if any(not str(data.get(key, "")).strip() for key in required):
        return jsonify({"status": "error", "message": "Order reference, customer, phone, product, and amount are required"}), 400
    try:
        phone = normalize_whatsapp_phone(data["phone"])
        amount = int(data["amount"])
        if amount <= 0 or amount > 1000000:
            raise ValueError("Invalid amount")
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Enter a valid Indian phone number and positive order amount"}), 400

    order_ref = str(data["order_ref"]).strip()
    customer_name = str(data["customer_name"]).strip()
    product_name = str(data["product_name"]).strip()
    if len(order_ref) > 80 or len(customer_name) > 120 or len(product_name) > 300:
        return jsonify({"status": "error", "message": "One or more order fields are too long"}), 400

    order_updates_opt_in = data.get("whatsapp_opt_in") is True
    marketing_opt_in = data.get("marketing_opt_in") is True
    consent_source = str(data.get("consent_source", "")).strip()[:160]
    if marketing_opt_in and not order_updates_opt_in:
        return jsonify({"status": "error", "message": "Marketing consent requires WhatsApp opt-in"}), 400
    if (order_updates_opt_in or marketing_opt_in) and not consent_source:
        return jsonify({"status": "error", "message": "Record the source of the customer's consent before messaging"}), 400

    address = str(data.get("address", "")).strip()
    pincode = re.sub(r"\D", "", str(data.get("pincode", "")))[:6]
    city = str(data.get("city", "")).strip()
    state = str(data.get("state", "")).strip()
    address_complete = bool(address and len(pincode) == 6 and city and state)
    status = "PENDING_WHATSAPP_OPT_IN" if not order_updates_opt_in else "PENDING_WHATSAPP_CONFIRMATION"
    if not address_complete:
        status = "RTO_RISK_HIGH"

    order_record = {
        "order_ref": order_ref,
        "customer_name": customer_name,
        "phone": phone,
        "product_name": product_name,
        "sku": str(data.get("sku", "")).strip()[:100],
        "amount": amount,
        "address": address,
        "pincode": pincode,
        "city": city,
        "state": state,
        "status": status,
        "wukusy_status": "WAITING_FOR_CONFIRMATION",
        "whatsapp_opt_in": order_updates_opt_in,
        "marketing_opt_in": marketing_opt_in,
        "consent_source": consent_source,
    }
    if not save_or_update_order(order_record):
        return jsonify({"status": "error", "message": "Order could not be saved"}), 500

    whatsapp_sent = False
    whatsapp_error = None
    if (
        data.get("send_template_requested") is True
        and order_updates_opt_in
        and marketing_opt_in
        and os.getenv("META_ORDER_TEMPLATE_NAME")
    ):
        try:
            result = send_interactive_order_confirmation(phone, customer_name, order_ref, product_name, amount)
            whatsapp_sent = bool(result and result.get("messages"))
            if whatsapp_sent:
                wa_id = str(result["messages"][0].get("id", "")) if isinstance(result.get("messages"), list) and result["messages"] else ""
                record_message(phone, customer_name, "OUTBOUND", "ORDER_TEMPLATE", f"Order template sent for {order_ref}.", wa_message_id=wa_id)
        except (requests.RequestException, RuntimeError, ValueError) as error:
            logger.warning("Order template send failed: %s", type(error).__name__)
            whatsapp_error = "The order was saved, but WhatsApp did not accept the message. Check template and API configuration."

    log_event("INFO", "EXTENSION_BRIDGE", f"Order {order_ref} ingested; WhatsApp sent: {whatsapp_sent}.")
    response = {
        "status": "success",
        "order_ref": order_ref,
        "whatsapp_sent": whatsapp_sent,
        "address_complete": address_complete,
        "message": "Order and customer registered successfully.",
    }
    return jsonify(response), 200


@app.route("/api/orders/pending-wukusy", methods=["GET", "OPTIONS"])
def api_orders_pending_wukusy():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    try:
        return jsonify({"status": "success", "orders": get_confirmed_wukusy_orders()}), 200
    except Exception:
        logger.exception("Failed to fetch confirmed Wukusy orders")
        return jsonify({"status": "error", "message": "Orders are temporarily unavailable"}), 500


@app.route("/", methods=["GET"])
@app.route("/zenos", methods=["GET"])
@app.route("/cockpit", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
def render_cockpit():
    """Renders the Hallmark-compliant ZenOS Founder Cockpit"""
    return render_template("dashboard.html")

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ready",
        "service": "ZenOS",
        "whatsapp_configured": bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID),
        "order_template_configured": bool(os.getenv("META_ORDER_TEMPLATE_NAME")),
        "ofd_template_configured": bool(os.getenv("META_OFD_TEMPLATE_NAME")),
        "support_phone_configured": bool(os.getenv("ZENOS_SUPPORT_PHONE")),
        "razorpay_configured": bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET),
        "admin_auth_configured": bool(os.getenv("ZENOS_ADMIN_PASSWORD") and app.secret_key),
        "extension_auth_configured": bool(os.getenv("ZENOS_EXTENSION_API_KEY")),
    }), 200

@app.route("/api/dashboard/data", methods=["GET"])
def fetch_dashboard_metrics():
    """Returns real-time KPIs, orders, and logs from SQLite"""
    try:
        data = get_dashboard_data()
        return jsonify(data), 200
    except Exception:
        logger.exception("Error fetching dashboard data")
        return jsonify({"error": "Dashboard data is temporarily unavailable"}), 500

@app.route("/api/dashboard/action", methods=["POST"])
def execute_dashboard_action():
    """Triggered by 1-click action buttons on the ZenOS Cockpit"""
    try:
        req = request.get_json(force=True)
        action = req.get("action")
        order_ref = str(req.get("order_ref", "")).strip()
        if not order_ref:
            return jsonify({"status": "error", "message": "order_ref is required"}), 400
        order = get_order(order_ref)

        if not order:
            return jsonify({"status": "error", "message": f"Order {order_ref} not found"}), 404

        order_dict = order
        phone = order_dict["phone"]
        cust_name = order_dict["customer_name"]
        amt = order_dict["amount"]
        item = order_dict["product_name"]

        if action == "order":
            if not order_dict.get("whatsapp_opt_in") or not order_dict.get("marketing_opt_in"):
                return jsonify({"status": "error", "message": "Recorded order-update and marketing opt-in are required"}), 409
            res = send_interactive_order_confirmation(phone, cust_name, order_ref, item, amt)
            if not res or not res.get("messages"):
                return jsonify({"status": "error", "message": "WhatsApp template is not configured or the message was not accepted"}), 503
            record_message(phone, cust_name, "OUTBOUND", "ORDER_TEMPLATE", f"Order template sent for {order_ref}.", wa_message_id=res["messages"][0].get("id", ""))
            return jsonify({"status": "success", "message": "WhatsApp order template accepted by Meta"}), 200
        
        elif action == "ofd":
            if not order_dict.get("whatsapp_opt_in"):
                return jsonify({"status": "error", "message": "Recorded WhatsApp opt-in is required"}), 409
            res = send_interactive_ofd_check(phone, cust_name, order_ref, item, amt)
            if not res or not res.get("messages"):
                return jsonify({"status": "error", "message": "WhatsApp template is not configured or the message was not accepted"}), 503
            update_order_status(order_ref, "OUT_FOR_DELIVERY")
            record_message(phone, cust_name, "OUTBOUND", "OFD_TEMPLATE", f"Availability template sent for {order_ref}.", wa_message_id=res["messages"][0].get("id", ""))
            return jsonify({"status": "success", "message": "Availability template accepted by Meta"}), 200

        elif action == "wukusy":
            if order_dict["status"] not in {"CONFIRMED_COD", "PREPAID_PAID"}:
                return jsonify({"status": "error", "message": "Only COD-confirmed or prepaid-paid orders can be fulfilled"}), 409
            if not all(str(order_dict.get(field, "")).strip() for field in ("address", "pincode", "city", "state")):
                return jsonify({"status": "error", "message": "A complete delivery address is required before Wukusy autofill"}), 409
            if not update_order_status(order_ref, order_dict["status"], {"wukusy_status": "SYNCED_QUEUE"}):
                return jsonify({"status": "error", "message": "Order could not be queued for autofill"}), 500
            return jsonify({"status": "success", "message": f"Order {order_ref} queued. Autofill and verify it in the browser extension; fulfillment is not submitted."}), 200

        return jsonify({"status": "error", "message": "Unknown action"}), 400

    except Exception:
        logger.exception("Error executing dashboard action")
        return jsonify({"status": "error", "message": "The action could not be completed"}), 500

@app.route("/api/orders/<path:order_ref>", methods=["DELETE", "PATCH", "OPTIONS"])
def api_order_rest(order_ref):
    """REST-style single order endpoint: DELETE to remove, PATCH to update fields."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    from db import delete_order, get_order_by_ref

    order_ref = order_ref.strip().lstrip('#')

    if request.method == "DELETE":
        try:
            success = delete_order(order_ref)
            if success:
                return jsonify({"status": "success", "message": f"Order {order_ref} deleted."}), 200
            else:
                return jsonify({"status": "error", "message": "Order not found or delete failed."}), 404
        except Exception as e:
            logger.exception("Error deleting order %s", order_ref)
            return jsonify({"status": "error", "message": str(e)}), 500

    if request.method == "PATCH":
        try:
            from db import update_order_fields
            data = request.get_json(force=True, silent=True) or {}
            allowed_fields = {
                "customer_name", "phone", "amount", "product_name", "sku",
                "address", "city", "state", "pincode", "status",
                "courier_name", "tracking_awb"
            }
            updates = {k: v for k, v in data.items() if k in allowed_fields}
            if not updates:
                return jsonify({"status": "error", "message": "No valid update fields provided."}), 400

            success = update_order_fields(order_ref, updates)
            if success:
                return jsonify({"status": "success", "message": f"Order {order_ref} updated.", "updated_fields": list(updates.keys())}), 200
            else:
                return jsonify({"status": "error", "message": "Order not found or update failed."}), 404
        except Exception as e:
            logger.exception("Error updating order %s", order_ref)
            return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/dashboard/orders/delete", methods=["POST"])
def api_delete_order():
    """Allows founder to delete an individual order"""
    try:
        from db import delete_order
        req = request.get_json(force=True) or {}
        order_ref = req.get("order_ref")
        if not order_ref:
            return jsonify({"status": "error", "message": "order_ref is required"}), 400
        success = delete_order(order_ref)
        if success:
            return jsonify({"status": "success", "message": f"Order {order_ref} deleted successfully."}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to delete order."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/dashboard/orders/clear", methods=["POST"])
def api_clear_orders():
    if os.getenv("ZENOS_ALLOW_DESTRUCTIVE_ACTIONS") != "1":
        return jsonify({"status": "error", "message": "Bulk deletion is disabled"}), 403
    try:
        request_data = request.get_json(silent=True) or {}
        if request_data.get("confirmation") != "DELETE ALL ORDERS":
            return jsonify({"status": "error", "message": "Explicit confirmation is required"}), 400
        from db import clear_all_orders
        success = clear_all_orders()
        if success:
            return jsonify({"status": "success", "message": "Orders cleared."}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to clear orders."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/dashboard/orders/seed", methods=["POST"])
def api_seed_orders():
    return jsonify({"status": "error", "message": "Demo order seeding is disabled"}), 410

@app.route("/api/dashboard/chat/send", methods=["POST"])
def send_admin_chat_reply():
    """Allows founder/admin to send direct WhatsApp messages from cockpit"""
    try:
        req = request.get_json(force=True)
        phone = req.get("phone")
        msg = req.get("message")
        if not phone or not msg:
            return jsonify({"status": "error", "message": "Phone and message are required"}), 400
        if not get_last_inbound_at(normalize_whatsapp_phone(phone)):
            return jsonify({"status": "error", "message": "Customer has not messaged within the 24-hour service window"}), 409

        result = send_whatsapp_message(phone, msg)
        record_message(phone, "Customer", "OUTBOUND", "TEXT", msg)
        return jsonify({"status": "success", "result": result if isinstance(result, dict) else {}}), 200
    except (RuntimeError, ValueError) as error:
        return jsonify({"status": "error", "message": str(error)}), 409
    except Exception:
        logger.exception("Error sending admin chat")
        return jsonify({"status": "error", "message": "Message could not be sent"}), 500

@app.route("/api/crm/conversations", methods=["GET"])
def api_crm_conversations():
    """
    Returns aggregated chat threads optimized for 500+ chats/day triage.
    Supports query param ?q= for live search and ?triage= for filtering.
    """
    try:
        threads = get_crm_conversations()
        q = request.args.get("q", "").strip().lower()
        triage_filter = request.args.get("triage", "all").strip().upper()

        if q:
            threads = [
                t for t in threads
                if q in t["phone"].lower()
                or q in t["customer_name"].lower()
                or q in (t.get("order_ref") or "").lower()
                or q in t["last_message"].lower()
            ]

        if triage_filter and triage_filter != "ALL":
            threads = [t for t in threads if t["triage"] == triage_filter]

        return jsonify({
            "status": "success",
            "count": len(threads),
            "conversations": threads
        }), 200
    except Exception as e:
        logger.exception("Error fetching CRM conversations")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/crm/thread/<phone>", methods=["GET"])
def api_crm_thread(phone):
    """
    Returns full message stream, buyer dossier, and address health for a phone.
    """
    try:
        thread_data = get_crm_thread(phone)
        return jsonify({
            "status": "success",
            "thread": thread_data
        }), 200
    except Exception as e:
        logger.exception("Error fetching CRM thread for %s", phone)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/crm/send", methods=["POST", "OPTIONS"])
def api_crm_send():
    """
    Sends message (text or native flow buttons) from the 3-column CRM composer.
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    try:
        req = request.get_json(force=True, silent=True) or {}
        phone = str(req.get("phone", "")).strip()
        text = str(req.get("message", "")).strip()
        buttons = req.get("buttons") or []
        customer_name = str(req.get("customer_name", "Customer")).strip()

        if not phone or not text:
            return jsonify({"status": "error", "message": "Phone and message are required"}), 400

        clean_digits = "".join(ch for ch in phone if ch.isdigit())
        if len(clean_digits) == 10:
            clean_digits = f"91{clean_digits}"

        delivery_method = "UNKNOWN"
        result = {}
        error_notes = []

        # Tier 1: Try WAHA Gateway (if active on localhost or custom gateway)
        try:
            if buttons and isinstance(buttons, list) and len(buttons) > 0:
                result = send_waha_buttons(clean_digits, text, buttons)
                delivery_method = "WAHA_BUTTONS"
            else:
                result = send_waha_text(clean_digits, text)
                delivery_method = "WAHA_TEXT"
        except Exception as e_waha:
            error_notes.append(f"WAHA: {e_waha}")
            # Tier 2: Try Meta WhatsApp Cloud API
            try:
                if WHATSAPP_TOKEN and PHONE_NUMBER_ID:
                    meta_text = text
                    if buttons:
                        btn_lines = [f"[⚡ {b.get('text', '')}]" for b in buttons if b.get('text')]
                        if btn_lines:
                            meta_text += "\n\n━━━━━━━━━━\n" + "   ".join(btn_lines)
                    result = send_whatsapp_message(clean_digits, meta_text)
                    delivery_method = "META_CLOUD_API"
                else:
                    error_notes.append("Meta Cloud API credentials not configured")
            except Exception as e_meta:
                error_notes.append(f"Meta Cloud: {e_meta}")

        # Tier 3: Direct wa.me & web.whatsapp.com link fallback
        import urllib.parse
        encoded_text = urllib.parse.quote(text)
        wa_link = f"https://wa.me/{clean_digits}?text={encoded_text}"
        web_wa_link = f"https://web.whatsapp.com/send?phone={clean_digits}&text={encoded_text}"
        if delivery_method == "UNKNOWN":
            delivery_method = "WA_DIRECT_LINK"
            result = {"status": "direct_link_ready", "wa_link": wa_link, "web_wa_link": web_wa_link}

        # Record in database
        msg_type = "BUTTON_TEMPLATE" if (buttons and len(buttons) > 0) else "TEXT"
        button_id_str = ",".join(b.get("id", "") for b in buttons) if buttons else None
        record_message(
            clean_digits,
            customer_name,
            "OUTBOUND",
            msg_type,
            text,
            button_id=button_id_str
        )
        return jsonify({
            "status": "success",
            "delivery_method": delivery_method,
            "wa_link": wa_link,
            "web_wa_link": web_wa_link,
            "result": result,
            "error_notes": error_notes if delivery_method == "WA_DIRECT_LINK" else None
        }), 200
    except Exception as e:
        logger.exception("Error sending message via CRM")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/shipping/send-availability-check", methods=["POST", "OPTIONS"])
def api_send_availability_check():
    """Allows founder to send an interactive Delivery / Shipping Availability Check directly to any customer number"""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:
        data = request.get_json(force=True, silent=True) or {}
        phone = data.get("phone")
        if not phone:
            return jsonify({"status": "error", "message": "Customer mobile number is required"}), 400

        order_ref = str(data.get("order_ref", "")).strip()
        order = get_order(order_ref)
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404
        if not order.get("whatsapp_opt_in"):
            return jsonify({"status": "error", "message": "Recorded WhatsApp opt-in is required"}), 409

        res = send_interactive_ofd_check(
            to_phone=order["phone"],
            customer_name=order["customer_name"],
            order_id=order_ref,
            product_name=order["product_name"],
            cod_amount=order["amount"],
        )
        if not res or not res.get("messages"):
            return jsonify({"status": "error", "message": "WhatsApp template is not configured or the message was not accepted"}), 503

        record_message(
            phone=order["phone"],
            customer_name=order["customer_name"],
            direction="OUTBOUND",
            message_type="OFD_TEMPLATE",
            body=f"Availability template sent for {order_ref}.",
            wa_message_id=res["messages"][0].get("id", ""),
        )

        return jsonify({
            "status": "success",
            "message": "Availability template accepted by Meta",
        }), 200

    except (RuntimeError, ValueError) as error:
        return jsonify({"status": "error", "message": str(error)}), 409
    except Exception:
        logger.exception("Error sending shipping availability check")
        return jsonify({"status": "error", "message": "Availability message could not be sent"}), 500


def polish_zenlora_brand_message(raw_text, customer_name="Valued Customer", purpose="general"):
    """
    Polishes raw founder notes into Zenlora luxury D2C brand voice.
    First tries Google Gemini if GEMINI_API_KEY is available,
    otherwise uses the institutional Zenlora D2C NLP engine.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={gemini_key}"
            prompt = (
                f"You are the official Zenlora Luxury D2C Brand Communications Specialist. "
                f"Zenlora is a premium Indian e-commerce home & lifestyle brand (zenlora.store). "
                f"Your task is to transform the founder's raw notes/instructions into a warm, polite, highly professional, "
                f"and authentic WhatsApp message for an Indian customer named '{customer_name}'.\n\n"
                f"Founder's Raw Notes: \"{raw_text}\"\n"
                f"Context/Purpose: {purpose}\n\n"
                f"Strict Formatting Rules:\n"
                f"1. Greet the customer warmly: 'Hi {customer_name}! 👋' or 'Hello {customer_name}! ✨'.\n"
                f"2. Tone: Courteous, premium, empathetic, clear (no aggressive marketing slang, no cheesy filler).\n"
                f"3. Use proper WhatsApp formatting (bold *like this*, italics _like this_).\n"
                f"4. If key details, dates, tracking, or instructions exist, structure them with neat bullet points.\n"
                f"5. End with the official Zenlora signature:\n"
                f"────────────────────────\n"
                f"✨ *Thank you for choosing Zenlora!*\n"
                f"I hope your day goes amazing and filled with joy! 😊\n"
                f"— *Team Zenlora* 🛍️\n\n"
                f"Return ONLY the exact final WhatsApp message text to send to the customer. Do not include any intro, markdown backticks, or meta explanations."
            )
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=8
            )
            if resp.status_code == 200:
                result = resp.json()
                text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text.strip():
                    return text.strip(), "gemini-3.8-flash"
        except Exception as e:
            logger.warning(f"Gemini API call failed, falling back to Zenlora brand engine: {e}")

    # Institutional Zenlora D2C NLP Formatter (Hinglish/English Intelligent Engine)
    cleaned = raw_text.strip()
    cleaned = re.sub(r'^(hi|hello|hey|namaste|bhai|sir|dear)\b[,\s]*', '', cleaned, flags=re.IGNORECASE).strip()
    
    # Capitalize sentences nicely
    raw_sentences = [s.strip() for s in re.split(r'([.?!]\s+)', cleaned) if s.strip()]
    capitalized_sentences = []
    for s in raw_sentences:
        if len(s) > 1:
            capitalized_sentences.append(s[0].upper() + s[1:])
        else:
            capitalized_sentences.append(s.upper())
    cleaned_body = "".join(capitalized_sentences) if capitalized_sentences else cleaned

    greeting = f"Hi {customer_name}! 👋\n\n"
    divider = "────────────────────────\n"
    closing = (
        "────────────────────────\n"
        "✨ *Thank you for choosing Zenlora!*\n"
        "I hope your day goes amazing and filled with joy! 😊\n"
        "— *Team Zenlora* 🛍️"
    )

    lower = raw_text.lower()
    if any(k in lower for k in ["delay", "deri", "late", "ruk gaya", "wait", "hold"]):
        body = (
            f"We wanted to share an important dispatch update regarding your Zenlora order.\n\n"
            f"{divider}"
            f"📦 *Order Status Update*\n"
            f"• *Current Status:* In-Transit (Brief Dispatch Delay)\n"
            f"• *Note:* {cleaned_body}\n"
            f"{divider}\n"
            f"Our warehouse team is expediting this with top priority to ensure delivery as fast as possible. Thank you for your kind patience and support! 🙏\n\n"
        )
    elif any(k in lower for k in ["ready", "dispatch", "bhej", "pack", "shipped", "courier", "nikal"]):
        body = (
            f"Exciting news! Your Zenlora package has been carefully packed and verified for dispatch! 🚚\n\n"
            f"{divider}"
            f"📦 *Dispatch Announcement*\n"
            f"• *Update:* {cleaned_body}\n"
            f"{divider}\n"
            f"You will receive live tracking updates directly on WhatsApp once your parcel is scanned by our courier partner.\n\n"
        )
    elif any(k in lower for k in ["address", "landmark", "location", "pata", "gali", "makan", "house", "flat"]):
        body = (
            f"We are preparing your Zenlora package for courier pickup today.\n\n"
            f"{divider}"
            f"📍 *Delivery Address Note*\n"
            f"• *Note:* {cleaned_body}\n"
            f"{divider}\n"
            f"To guarantee first-attempt delivery without any courier delay, please reply with your exact House/Flat number and nearby landmark! 😊\n\n"
        )
    elif any(k in lower for k in ["cancel", "nahi chahiye", "band", "return", "refund"]):
        body = (
            f"We have noted your request regarding your Zenlora order.\n\n"
            f"{divider}"
            f"ℹ️ *Customer Service Notice*\n"
            f"• *Details:* {cleaned_body}\n"
            f"{divider}\n"
            f"If there is anything else we can do to assist you or if you change your mind, our concierge team is always here for you.\n\n"
        )
    else:
        body = (
            f"Thank you for reaching out to *Zenlora*! ✨\n\n"
            f"{divider}"
            f"💬 *Founder / Store Team Update*\n"
            f"• {cleaned_body}\n"
            f"{divider}\n"
            f"If you have any questions or need further clarification, simply reply to this message anytime.\n\n"
        )

    return greeting + body + closing, "zenlora_brand_engine"


@app.route("/api/ai/polish-message", methods=["POST", "OPTIONS"])
def api_polish_message():
    """AI endpoint that transforms founder's raw notes into Zenlora luxury D2C brand voice"""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:
        data = request.get_json(force=True, silent=True) or {}
        raw_text = data.get("raw_text", "").strip()
        customer_name = data.get("customer_name") or "Valued Customer"
        purpose = data.get("purpose") or "general"

        if not raw_text:
            return jsonify({"status": "error", "message": "Raw text is required for AI polishing"}), 400

        polished_text, source = polish_zenlora_brand_message(raw_text, customer_name, purpose)

        return jsonify({
            "status": "success",
            "polished_text": polished_text,
            "engine": source,
            "character_count": len(polished_text)
        }), 200

    except Exception as e:
        logger.error(f"Error polishing message: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/concierge-polish", methods=["POST", "OPTIONS"])
def api_concierge_polish():
    """RTO Killer 2.0 AI Concierge: Transforms raw founder notes into luxury D2C English message + interactive buttons"""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    try:
        data = request.get_json(force=True, silent=True) or {}
        raw_prompt = data.get("raw_prompt", "").strip()
        customer_name = data.get("customer_name") or "Valued Customer"
        order_ref = str(data.get("order_ref", ""))
        product_name = str(data.get("product_name", ""))
        amount = int(data.get("amount", 0) or 0)

        if not raw_prompt:
            return jsonify({"status": "error", "message": "Raw prompt instruction cannot be empty"}), 400

        res = polish_with_ai_concierge(
            raw_prompt=raw_prompt,
            customer_name=customer_name,
            order_ref=order_ref,
            product_name=product_name,
            amount=amount,
        )
        return jsonify({
            "status": "success",
            "message": res["message"],
            "buttons": res.get("buttons", []),
            "engine": res.get("engine", "ai_concierge"),
        }), 200
    except Exception as e:
        logger.error(f"Concierge Polish Error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/whatsapp/status", methods=["GET"])
@app.route("/api/waha/status", methods=["GET"])
def api_whatsapp_status():
    """
    Live proxy to Baileys / OpenWA WhatsApp Gateway status endpoint.
    Returns gateway connection status (CONNECTED | SCAN_QR | INITIALIZING | DISCONNECTED),
    linked phone number, and QR code data URL.
    """
    health = check_gateway_health()
    if health.get("online"):
        st = "CONNECTED" if health.get("active_session") else health.get("status", "SCAN_QR")
        return jsonify({
            "status": st,
            "connection_status": st,
            "phone": health.get("phone", "919771370945"),
            "qr": health.get("qr"),
            "gateway_url": health.get("gateway_url"),
            "active_session": health.get("active_session", False),
        }), 200

    return jsonify({
        "status": "DISCONNECTED",
        "phone": None,
        "qr": None,
        "connection_status": "DISCONNECTED",
        "active_session": False,
    }), 200


@app.route("/api/rto/dispatch", methods=["POST", "OPTIONS"])
def api_rto_dispatch():
    """
    RTO Killer 2.0 Unified Dispatcher:
    Supports:
    - 'rto_prepay': 15% instant prepay savings offer with 3 interactive buttons
    - 'address_fix': Address verification prompt with location/typing buttons
    - 'shipping_track': Dispatched status with live AWB tracking link
    - 'ndr_rescue': Non-delivery rescue prompt with rescheduling buttons
    - 'custom_ai': Custom message with AI-generated buttons
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    order_ref = str(data.get("order_ref", "")).strip()
    workflow = str(data.get("workflow", "rto_prepay")).strip()
    raw_phone = str(data.get("phone", "")).strip()

    if not raw_phone:
        return jsonify({"status": "error", "message": "Customer phone number is required"}), 400

    try:
        phone = normalize_whatsapp_phone(raw_phone)
        order = get_order(order_ref) if order_ref else None

        customer_name = (order.get("customer_name") if order else None) or str(data.get("customer_name", "Valued Customer")).strip()
        product_name = (order.get("product_name") if order else None) or str(data.get("product_name") or "Zenlora Order").strip()
        raw_amt = order.get("amount") if order else data.get("amount")
        amount = int(raw_amt) if raw_amt else 0
        address = (order.get("address") if order else None) or str(data.get("address", "")).strip()
        pincode = (order.get("pincode") if order else None) or str(data.get("pincode", "")).strip()
        awb = str(data.get("awb", order.get("tracking_awb", "DEL-9842183921") if order else "DEL-9842183921"))
        courier_name = str(data.get("courier_name", order.get("courier_name", "Delhivery Express") if order else "Delhivery Express"))

        result = {}
        message_desc = ""

        if workflow == "rto_prepay":
            result = dispatch_rto_killer_prepay(phone, customer_name, order_ref, product_name, amount)
            message_desc = f"RTO Killer 15% Prepay Offer sent for #{order_ref}"
        elif workflow in ("rto_50_prepay", "rto_rs50_prepay"):
            result = dispatch_rto_killer_rs50_prepay(phone, customer_name, order_ref, product_name, amount)
            message_desc = f"RTO Killer Flat Rs 50 Prepay Offer sent for #{order_ref}"
        elif workflow == "address_fix":
            health = evaluate_address_health(address, pincode)
            missing = health.get("missing_parts", ["House/Flat No.", "Nearby Landmark"])
            result = dispatch_address_fix_request(phone, customer_name, order_ref, address, missing)
            message_desc = f"Address Fix Request sent for #{order_ref}"
        elif workflow == "shipping_track":
            track_url = str(data.get("tracking_url", ""))
            result = dispatch_shipping_tracking(phone, customer_name, order_ref, product_name, awb, courier_name, track_url)
            message_desc = f"Shipment Tracking alert sent for #{order_ref}"
        elif workflow == "ndr_rescue":
            result = dispatch_ndr_rescue(phone, customer_name, order_ref, courier_name)
            message_desc = f"NDR Rescue Alert sent for #{order_ref}"
        elif workflow == "custom_ai":
            custom_text = str(data.get("message", "")).strip()
            custom_buttons = data.get("buttons") or []
            if not custom_text:
                return jsonify({"status": "error", "message": "Custom message text cannot be empty"}), 400
            result = send_waha_buttons(phone, custom_text, custom_buttons)
            message_desc = f"Custom AI Concierge message sent for #{order_ref}"
        else:
            return jsonify({"status": "error", "message": f"Unsupported workflow: {workflow}"}), 400

        wa_id = str(result.get("id") or result.get("messageId") or "")
        record_message(phone, customer_name, "OUTBOUND", workflow.upper(), message_desc, wa_message_id=wa_id)
        log_event("SUCCESS", "RTO_KILLER_2", f"{message_desc} to {phone}.")

        return jsonify({
            "status": "success",
            "message": "Message successfully dispatched via WhatsApp Gateway",
            "workflow": workflow,
            "wa_message_id": wa_id,
            "result": result
        }), 200

    except Exception as e:
        logger.error(f"RTO Dispatch Error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/whatsapp/webhook", methods=["POST", "OPTIONS"])
@app.route("/api/waha/webhook", methods=["POST", "OPTIONS"])
def api_waha_webhook():
    """
    Inbound webhook for WAHA:
    Processes customer button clicks and direct replies in real-time.
    Auto-updates order statuses and records incoming messages.
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    try:
        payload = request.get_json(force=True, silent=True) or {}
        data = payload.get("payload") or payload

        from_chat = data.get("from") or data.get("chatId") or ""
        clean_phone = "".join(ch for ch in from_chat if ch.isdigit())[-10:]
        body = str(data.get("body") or data.get("text") or "").strip()
        button_id = str(data.get("selectedButtonId") or data.get("buttonId") or "").strip()

        if not clean_phone or not (body or button_id):
            return jsonify({"status": "ignored"}), 200

        # 1. Record inbound message
        record_message(clean_phone, "Customer", "INBOUND", "BUTTON_REPLY" if button_id else "TEXT", body or button_id, button_id=button_id)

        # 2. Check for button actions
        if "btn_confirm_cod" in button_id or body.upper() in {"YES", "CONFIRM", "1"}:
            update_order_status(clean_phone, "CONFIRMED_COD")
            send_waha_text(
                clean_phone,
                "Dhanyawad! 🙏 Aapka Cash on Delivery order CONFIRM ho gaya hai. Humara warehouse team aapka parcel priority dispatch ke liye pack kar raha hai! 🚚",
            )
            log_event("SUCCESS", "RTO_KILLER", f"Customer {clean_phone} confirmed COD order.")

        elif "btn_pay" in button_id or body.upper() in {"PAY", "PREPAY"}:
            update_order_status(clean_phone, "PREPAY_PENDING")
            send_waha_text(
                clean_phone,
                "Shandar choice! 🎉 15% Instant Discount activate ho gaya hai. Kripya apna payment UPI ke zariye complete karein:\n👉 upi://pay?pa=zenlora@upi&pn=Zenlora%20Store\nPayment confirm hote hi express dispatch ho jayega!",
            )

        elif "btn_cancel" in button_id or body.upper() in {"CANCEL", "NO", "3"}:
            update_order_status(clean_phone, "CANCELLED")
            send_waha_text(
                clean_phone,
                "Aapka order request ke mutabiq cancel kar diya gaya hai. Agar aapko kabhi bhi hamari zaroorat ho, to hum hamesha yahan hain! — Team Zenlora 🙏",
            )
            log_event("INFO", "RTO_KILLER", f"Customer {clean_phone} cancelled order via WhatsApp button.")

        elif len(body) > 20 and any(w in body.lower() for w in ["near", "house", "flat", "gali", "road", "chowk", "nagar"]):
            update_order_status(clean_phone, "ADDRESS_UPDATED")
            send_waha_text(
                clean_phone,
                "Thank you! 🙏 Humne aapka naya address record kar liya hai. Parcel bina kisi delay ke aap tak pahunchega! 🚚",
            )
            log_event("SUCCESS", "ADDRESS_FIX", f"Customer {clean_phone} provided updated address via WhatsApp.")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"WAHA Webhook error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/whatsapp/quick-dispatch", methods=["POST", "OPTIONS"])
def api_quick_dispatch():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    order_ref = str(data.get("order_ref", "") or "").strip()
    template_type = str(data.get("template_type", "custom"))
    raw_phone = str(data.get("phone", "")).strip()
    if not raw_phone:
        return jsonify({"status": "error", "message": "Customer WhatsApp phone number is required"}), 400

    try:
        phone = normalize_whatsapp_phone(raw_phone)
        order = get_order(order_ref) if order_ref else None
        if order and normalize_whatsapp_phone(order["phone"]) != phone and template_type in {"15_prepay", "shipping_check"} and not data.get("force_manual"):
            return jsonify({"status": "error", "message": "Phone number does not match order record"}), 409
        customer_name = (order.get("customer_name") if order else None) or str(data.get("customer_name", "Valued Customer")).strip()
        product_name = (order.get("product_name") if order else None) or str(data.get("product_name") or "Zenlora Order").strip()
        raw_amt = order.get("amount") if order else data.get("amount")
        amount = int(raw_amt) if raw_amt else 0
        awb = str(data.get("awb", "") or "").strip()

        if template_type in {"15_prepay", "prepay_15"}:
            if os.getenv("META_ORDER_TEMPLATE_NAME") and not data.get("gateway"):
                result = send_interactive_order_confirmation(phone, customer_name, order_ref, product_name, amount)
            else:
                result = dispatch_rto_killer_prepay(phone, customer_name, order_ref, product_name, amount)
            message_type = "ORDER_TEMPLATE"
        elif template_type in {"50_prepay", "rs50_prepay", "prepay_50"}:
            result = dispatch_rto_killer_rs50_prepay(phone, customer_name, order_ref, product_name, amount)
            message_type = "PREPAY_50_TEMPLATE"
        elif template_type == "shipping_check":
            result = dispatch_ofd_confirmation(phone, customer_name, order_ref, product_name, amount)
            message_type = "OFD_TEMPLATE" 
            buttons = [
                {"id": "btn_collect", "text": "📦 I will collect today"},
                {"id": "btn_resched", "text": "📅 Change delivery date"},
            ]
            text = (
                f"Namaste {customer_name}! 🙏✨\n\n"
                f"Your Zenlora order *#{order_ref}* ({product_name}) is scheduled for delivery today.\n"
                f"Total COD Amount: *₹{amount}*\n\n"
                f"Please confirm your availability by tapping an option below:"
            )
            result = send_waha_buttons(phone, text, buttons)
            message_type = "OFD_TEMPLATE"
        elif template_type == "request_landmark":
            buttons = [
                {"id": "btn_send_addr", "text": "📍 Send My Landmark"},
                {"id": "btn_addr_ok", "text": "✅ Address is Complete"},
            ]
            text = (
                f"Namaste {customer_name}! 👋\n\n"
                f"Thank you for shopping with *Zenlora*! We are preparing your order *#{order_ref}*.\n\n"
                f"To ensure our courier executive reaches you without delay, please reply with your:\n"
                f"1. House / Flat Number\n"
                f"2. Street / Road\n"
                f"3. Nearest Landmark\n\n"
                f"Thank you! ✨"
            )
            result = send_waha_buttons(phone, text, buttons)
            message_type = "ADDRESS_REQUEST"
        elif template_type == "vip_voucher":
            text = (
                f"Namaste {customer_name}! 🎁✨\n\n"
                f"As a privileged Zenlora patron, here is a special gift for you:\n\n"
                f"Use coupon code *VIPZEN10* on https://zenlora.store to get *Flat 10% Instant OFF* on your next purchase!\n\n"
                f"Valid across all home & festive collections. Happy Shopping! 🛍️"
            )
            result = send_waha_text(phone, text)
            message_type = "VIP_VOUCHER"
        elif template_type == "order_tracking":
            track_url = f"https://www.delhivery.com/track/package/{awb}"
            result = dispatch_shipping_tracking(phone, customer_name, order_ref, product_name, awb, "Delhivery Express", track_url)
            message_type = "ORDER_TRACKING"
        else:
            custom_text = str(data.get("custom_text") or data.get("message") or "").strip()
            if not custom_text:
                return jsonify({"status": "error", "message": "Custom message text cannot be empty"}), 400
            buttons = data.get("buttons") or []
            if buttons and isinstance(buttons, list) and len(buttons) > 0:
                result = send_waha_buttons(phone, custom_text, buttons)
                message_type = "CUSTOM_BUTTONS"
            else:
                result = send_waha_text(phone, custom_text)
                message_type = "TEXT_CUSTOM"

        wa_id = str(result.get("id") or result.get("messageId") or "")
        record_message(phone, customer_name, "OUTBOUND", message_type, f"{message_type} sent for {order_ref}.", wa_message_id=wa_id)
        log_event("SUCCESS", "QUICK_DISPATCH", f"{message_type} sent to {phone} via WhatsApp Gateway.")
        return jsonify({
            "status": "success",
            "message": "WhatsApp message dispatched successfully via Business WhatsApp Gateway",
            "wa_message_id": wa_id,
            "result": result
        }), 200
    except Exception as e:
        logger.exception("Quick dispatch failed: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/order-webhook", methods=["POST"])
def handle_store_order():
    """Accept a consent-aware order event from a configured Zenlora store webhook."""
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "A JSON order payload is required"}), 400
        order_ref = str(data.get("order_ref") or data.get("order_id") or "").strip()
        customer_name = str(data.get("customer_name", "")).strip()
        product_name = str(data.get("product_name", "")).strip()
        try:
            phone = normalize_whatsapp_phone(data.get("phone", ""))
            amount = int(data.get("amount", 0))
            if amount <= 0 or amount > 1000000:
                raise ValueError("Invalid amount")
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Enter a valid Indian phone number and positive order amount"}), 400
        if not order_ref or not customer_name or not product_name:
            return jsonify({"status": "error", "message": "Order reference, customer, and product are required"}), 400
        if len(order_ref) > 80 or len(customer_name) > 120 or len(product_name) > 300:
            return jsonify({"status": "error", "message": "One or more order fields are too long"}), 400

        order_opt_in = data.get("whatsapp_opt_in") is True
        marketing_opt_in = data.get("marketing_opt_in") is True
        consent_source = str(data.get("consent_source", "")).strip()[:160]
        if marketing_opt_in and not order_opt_in:
            return jsonify({"status": "error", "message": "Marketing consent requires WhatsApp opt-in"}), 400
        if (order_opt_in or marketing_opt_in) and not consent_source:
            return jsonify({"status": "error", "message": "Record the source of the customer's consent before messaging"}), 400

        order = {
            "order_ref": order_ref,
            "customer_name": customer_name,
            "phone": phone,
            "product_name": product_name,
            "amount": amount,
            "address": str(data.get("address", "")).strip(),
            "pincode": re.sub(r"\D", "", str(data.get("pincode", "")))[:6],
            "city": str(data.get("city", "")).strip(),
            "state": str(data.get("state", "")).strip(),
            "status": "PENDING_WHATSAPP_CONFIRMATION" if order_opt_in else "PENDING_WHATSAPP_OPT_IN",
            "wukusy_status": "WAITING_FOR_CONFIRMATION",
            "whatsapp_opt_in": order_opt_in,
            "marketing_opt_in": marketing_opt_in,
            "consent_source": consent_source,
        }
        if not save_or_update_order(order):
            return jsonify({"status": "error", "message": "Order could not be saved"}), 500

        whatsapp_sent = False
        if data.get("send_template_requested") is True and order_opt_in and marketing_opt_in:
            try:
                result = send_interactive_order_confirmation(phone, customer_name, order_ref, product_name, amount)
                whatsapp_sent = bool(result and result.get("messages"))
                if whatsapp_sent:
                    record_message(phone, customer_name, "OUTBOUND", "ORDER_TEMPLATE", f"Order template sent for {order_ref}.", wa_message_id=result["messages"][0].get("id", ""))
            except (requests.RequestException, RuntimeError, ValueError) as error:
                logger.warning("Store order template send failed: %s", type(error).__name__)

        return jsonify({
            "status": "saved",
            "order_ref": order_ref,
            "whatsapp_sent": whatsapp_sent,
            "message": "Order saved." if not whatsapp_sent else "Order saved and approved WhatsApp template accepted by Meta.",
        }), 200
    except Exception:
        logger.exception("Failed to process store order webhook")
        return jsonify({"status": "error", "message": "Order could not be processed"}), 500

@app.route("/api/ofd-webhook", methods=["POST"])
def handle_ofd_trigger():
    """Send the approved delivery check for an opted-in, confirmed order."""
    try:
        data = request.get_json(silent=True)
        order_ref = str(data.get("order_ref", "")).strip() if isinstance(data, dict) else ""
        if not order_ref:
            return jsonify({"status": "error", "message": "order_ref is required"}), 400
        order = get_order(order_ref)
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404
        if not order.get("whatsapp_opt_in"):
            return jsonify({"status": "error", "message": "Recorded WhatsApp opt-in is required"}), 409
        if order.get("status") not in {"CONFIRMED_COD", "PREPAID_PAID"}:
            return jsonify({"status": "error", "message": "Only verified COD or paid prepaid orders can receive an OFD check"}), 409

        result = send_interactive_ofd_check(
            order["phone"],
            order["customer_name"],
            order_ref,
            order["product_name"],
            order["amount"],
        )
        if not result or not result.get("messages"):
            return jsonify({"status": "error", "message": "WhatsApp did not accept the delivery template"}), 502
        update_order_status(order_ref, "OUT_FOR_DELIVERY")
        record_message(order["phone"], order["customer_name"], "OUTBOUND", "OFD_TEMPLATE", f"Availability template sent for {order_ref}.", wa_message_id=result["messages"][0].get("id", ""))
        return jsonify({"status": "success", "message": "Delivery template accepted by Meta"}), 200
    except (RuntimeError, ValueError) as error:
        return jsonify({"status": "error", "message": str(error)}), 409
    except requests.RequestException:
        logger.exception("OFD template request failed")
        return jsonify({"status": "error", "message": "Delivery message could not be sent"}), 502
    except Exception:
        logger.exception("OFD webhook processing failed")
        return jsonify({"status": "error", "message": "Delivery message could not be sent"}), 500

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if not VERIFY_TOKEN:
        return "Webhook verification is not configured", 503
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if mode == "subscribe" and hmac.compare_digest(token, VERIFY_TOKEN):
        return challenge, 200
    return "Verification failed", 403


def verify_meta_signature(raw_body, signature):
    if not META_APP_SECRET or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def _handle_whatsapp_button(sender_phone, sender_name, button_id, button_text):
    order_ref = ""
    action = ""
    offer_amount = ""
    if button_id.startswith("btn_pay_"):
        action = "pay"
        suffix = button_id[len("btn_pay_"):]
        if "_" in suffix:
            order_ref, offer_amount = suffix.rsplit("_", 1)
    elif button_id.startswith("btn_cod_"):
        action = "confirm_cod"
        order_ref = button_id[len("btn_cod_"):]
    elif button_id.startswith("btn_cancel_"):
        action = "cancel_request"
        order_ref = button_id[len("btn_cancel_"):]
    elif button_id.startswith("btn_collect_"):
        action = "collect"
        order_ref = button_id[len("btn_collect_"):]
    elif button_id.startswith("btn_resched_"):
        action = "reschedule_request"
        order_ref = button_id[len("btn_resched_"):]

    order = get_order(order_ref) if order_ref else None
    if not order or order["phone"][-10:] != sender_phone[-10:]:
        return

    if action == "pay":
        if not order.get("marketing_opt_in") or offer_amount != str(order["amount"]):
            return
        payment_url, payable, saved = create_razorpay_payment_link(
            order["amount"], order["customer_name"], sender_phone, order_ref
        )
        if not update_order_status(order_ref, "PREPAID_PENDING_LINK", {
            "razorpay_link": payment_url,
            "prepaid_amount": payable,
            "discount_amount": saved,
        }):
            raise RuntimeError("Payment link was created but the order could not be updated")
        reply = f"Your payment link for order {order_ref} is {payment_url}. Pay ₹{payable}; discount ₹{saved}."
    elif action == "confirm_cod":
        if not update_order_status(order_ref, "CONFIRMED_COD"):
            raise RuntimeError("COD confirmation could not be recorded")
        reply = f"Thanks, {sender_name}. Your COD confirmation for order {order_ref} is recorded. Dispatch will be handled by the seller after verification."
    elif action == "cancel_request":
        if not update_order_status(order_ref, "CUSTOMER_CANCEL_REQUESTED"):
            raise RuntimeError("Cancellation request could not be recorded")
        reply = f"We received your cancellation request for order {order_ref}. The seller must confirm cancellation before dispatch; this reply alone does not cancel the marketplace order."
    elif action == "collect":
        if not update_order_status(order_ref, "DELIVERY_COLLECT_CONFIRMED"):
            raise RuntimeError("Delivery availability could not be recorded")
        reply = f"Thanks, {sender_name}. Your availability for order {order_ref} is recorded. The courier schedule is not changed by this message."
    elif action == "reschedule_request":
        if not update_order_status(order_ref, "CUSTOMER_REQUESTED_RESCHEDULE"):
            raise RuntimeError("Delivery-date request could not be recorded")
        reply = f"We received your delivery-date request for order {order_ref}. The seller or courier must confirm any schedule change."
    else:
        return

    result = send_whatsapp_message(sender_phone, reply)
    wa_id = result.get("messages", [{}])[0].get("id", "")
    record_message(sender_phone, sender_name, "OUTBOUND", "TEXT", reply, wa_message_id=wa_id)


@app.route("/webhook", methods=["POST"])
def handle_incoming_messages():
    raw_body = request.get_data(cache=True)
    if not verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256", "")):
        return jsonify({"status": "error", "message": "Invalid webhook signature"}), 401

    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    sender_phone = message.get("from", "")
                    message_id = message.get("id", "")
                    if not sender_phone or not message_id:
                        continue
                    contacts = value.get("contacts", [])
                    sender_name = "Customer"
                    if contacts:
                        sender_name = str(contacts[0].get("profile", {}).get("name", "Customer"))[:120]

                    msg_type = message.get("type", "unknown")
                    button_id = ""
                    button_text = ""
                    text_body = ""
                    if msg_type == "interactive":
                        interactive = message.get("interactive", {})
                        if interactive.get("type") == "button_reply":
                            button = interactive.get("button_reply", {})
                            button_id = str(button.get("id", ""))
                            button_text = str(button.get("title", ""))
                    elif msg_type == "button":
                        button = message.get("button", {})
                        button_id = str(button.get("payload", ""))
                        button_text = str(button.get("text", ""))
                    elif msg_type == "text":
                        text_body = str(message.get("text", {}).get("body", ""))[:4000]

                    if not record_message(
                        sender_phone,
                        sender_name,
                        "INBOUND",
                        msg_type,
                        text_body or button_text,
                        button_id,
                        message_id,
                    ):
                        continue
                    if button_id:
                        _handle_whatsapp_button(sender_phone, sender_name, button_id, button_text)
        return jsonify({"status": "ok"}), 200
    except (RuntimeError, ValueError) as error:
        logger.warning("WhatsApp webhook action was not completed: %s", type(error).__name__)
        return jsonify({"status": "accepted", "message": "The event was recorded for manual follow-up"}), 200
    except Exception:
        logger.exception("WhatsApp webhook processing failed")
        return jsonify({"status": "error", "message": "Webhook processing failed"}), 500


@app.route("/api/razorpay/webhook", methods=["POST"])
def handle_razorpay_webhook():
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    raw_body = request.get_data(cache=True)
    supplied_signature = request.headers.get("X-Razorpay-Signature", "")
    if not secret or not supplied_signature:
        return jsonify({"status": "error", "message": "Payment webhook is not configured"}), 503
    expected_signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return jsonify({"status": "error", "message": "Invalid webhook signature"}), 401

    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    if not event_id:
        return jsonify({"status": "error", "message": "Missing event identifier"}), 400
    if not claim_webhook_event("razorpay", event_id):
        return jsonify({"status": "ok", "duplicate": True}), 200

    try:
        data = request.get_json(silent=True) or {}
        if data.get("event") == "payment_link.paid":
            entity = data.get("payload", {}).get("payment_link", {}).get("entity", {})
            order_ref = str(entity.get("notes", {}).get("order_ref", ""))
            order = get_order(order_ref)
            if order and int(entity.get("amount_paid", 0)) >= int(order.get("prepaid_amount") or 0) * 100:
                update_order_status(order_ref, "PREPAID_PAID")
                log_event("SUCCESS", "RAZORPAY", f"Verified prepaid payment for order {order_ref}.")
        return jsonify({"status": "ok"}), 200
    except Exception:
        logger.exception("Razorpay webhook processing failed")
        return jsonify({"status": "error", "message": "Payment event could not be processed"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
