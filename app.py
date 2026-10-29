import os
import json
import logging
import re
import hmac
import hashlib
import secrets
import threading
from pathlib import Path
from datetime import datetime, timezone
import time
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
    get_open_orders_for_phone,
    update_order_address,
    revoke_whatsapp_consent,
    get_confirmed_wukusy_orders,
    get_last_inbound_at,
    claim_webhook_event,
    get_crm_conversations,
    get_crm_thread,
    add_abandoned_cart,
    get_pending_cart_drips,
    update_cart_drip_status,
    mark_cart_recovered,
    mark_cart_cancelled,
    get_abandoned_carts,
    get_abandoned_cart,
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
    dispatch_cod_confirm_prepay,
    dispatch_rto_killer_prepay,
    dispatch_rto_killer_rs50_prepay,
    dispatch_ofd_confirmation,
    dispatch_address_fix_request,
    dispatch_shipping_tracking,
    dispatch_ndr_rescue,
    dispatch_cart_drip_touch1,
    dispatch_cart_drip_touch2,
    dispatch_cart_drip_touch3,
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
app.secret_key = os.getenv("ZENOS_SESSION_SECRET") or "zenos-secret-session-key-nilesh-2006-enterprise-v1"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=bool(os.getenv("VERCEL")),
    SESSION_COOKIE_SAMESITE="Lax",
)

init_db()

# Configurations
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("META_PHONE_ID", "")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
META_APP_SECRET = os.getenv("META_APP_SECRET")


@app.before_request
def authorize_request():
    path = request.path
    if path in {"/login", "/logout", "/api/health", "/webhook", "/api/razorpay/webhook"} or path.startswith("/api/customer/avatar/"):
        return None

    if path.startswith("/api/cart/"):
        if request.method == "OPTIONS":
            return None
        if session.get("zenos_admin_authenticated") or app.config.get("TESTING"):
            return None
        expected = os.getenv("ZENOS_EXTENSION_API_KEY")
        supplied = request.headers.get("X-ZenOS-Extension-Key", "") or request.headers.get("X-ZenOS-Webhook-Key", "")
        if supplied and expected and hmac.compare_digest(supplied, expected):
            return None
        # Allow cart webhook/ingestion if no secret required or if from store
        if not expected:
            return None
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    extension_paths = {
        "/api/orders",
        "/api/orders/ingest",
        "/api/orders/pending-wukusy",
        "/api/shipping/send-availability-check",
        "/api/extension/crm/send",
        "/api/whatsapp/quick-dispatch",
        "/api/whatsapp/status",
    }
    if path.startswith("/api/orders/") and request.method in ("PATCH", "DELETE"):
        return None

    if path in extension_paths or path.startswith("/api/orders/"):
        if request.method == "OPTIONS":
            return None
        if session.get("zenos_admin_authenticated") or app.config.get("TESTING"):
            return None
        expected = os.getenv("ZENOS_EXTENSION_API_KEY")
        supplied = request.headers.get("X-ZenOS-Extension-Key", "")
        if supplied and expected and hmac.compare_digest(supplied, expected):
            return None
        if not expected:
            return None
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if path in {"/api/order-webhook", "/api/ofd-webhook"}:
        expected = os.getenv("ZENOS_STORE_WEBHOOK_TOKEN")
        if not expected:
            return jsonify({"status": "error", "message": "Store webhook token is not configured"}), 503
        supplied = request.headers.get("X-ZenOS-Webhook-Key", "")
        if not hmac.compare_digest(supplied, expected):
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return None

    if path == "/api/waha/webhook":
        if session.get("zenos_admin_authenticated") or app.config.get("TESTING"):
            return None
        expected = os.getenv("WAHA_WEBHOOK_SECRET")
        if not expected:
            return None
        supplied = request.headers.get("X-ZenOS-Webhook-Key", "") or request.headers.get("X-Api-Key", "")
        if not supplied or not hmac.compare_digest(supplied, expected):
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return None

    if path.startswith("/static/"):
        return None

    admin_pass = os.getenv("ZENOS_ADMIN_PASSWORD") or "zenlora2026"
    if not app.secret_key:
        app.secret_key = os.getenv("ZENOS_SESSION_SECRET") or "zenos-default-dev-secret-key-32b"
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
        app.secret_key = os.getenv("ZENOS_SESSION_SECRET") or "zenos-secret-session-key-nilesh-2006-enterprise-v1"

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
    now = datetime.now()

    ip_data = LOGIN_ATTEMPTS.get(client_ip, {"count": 0, "locked_until": None})
    if ip_data.get("locked_until") and ip_data["locked_until"] > now:
        remaining = int((ip_data["locked_until"] - now).total_seconds() / 60) + 1
        return render_template("login.html", configuration_error=False, login_error=False, locked_error=f"Too many failed login attempts. Locked for {remaining} minutes."), 429

    if request.method == "POST":
        supplied = str(request.form.get("password", "")).strip()
        # Accept Nilesh@2006 (exact or case-insensitive) or configured ZENOS_ADMIN_PASSWORD
        is_valid = (
            hmac.compare_digest(supplied, expected) or 
            hmac.compare_digest(supplied.lower(), expected.lower()) or 
            hmac.compare_digest(supplied, "Nilesh@2006") or 
            hmac.compare_digest(supplied.lower(), "nilesh@2006")
        )
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
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    if not response.ok:
        logger.warning("Meta WhatsApp API rejected the message (HTTP %s)", response.status_code)
        raise RuntimeError(f"Meta WhatsApp API rejected the message (HTTP {response.status_code})")
    return response.json()


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
        raise ValueError("Order amount must be positive")
    order_ref = str(order_id)
    savings = round(amount * 0.15)
    payable = amount - savings
    return send_template_message(
        to_phone,
        os.getenv("META_ORDER_TEMPLATE_NAME", ""),
        [customer_name, order_ref, product_name, amount, payable, savings],
        [f"btn_pay_{order_ref}_{amount}", f"btn_cod_{order_ref}", f"btn_cancel_{order_ref}"],
    )


def send_interactive_ofd_check(to_phone, customer_name, order_id, product_name, cod_amount, contact_phone=None):
    amount = int(cod_amount)
    if amount <= 0:
        raise ValueError("Order amount must be positive")
    order_ref = str(order_id)
    support_phone = contact_phone or os.getenv("ZENOS_SUPPORT_PHONE", "")
    if not support_phone:
        raise RuntimeError("Support phone is not configured for the delivery template")
    return send_template_message(
        to_phone,
        os.getenv("META_OFD_TEMPLATE_NAME", ""),
        [customer_name, order_ref, product_name, amount, support_phone],
        [f"btn_collect_{order_ref}", f"btn_resched_{order_ref}"],
    )

def create_razorpay_payment_link(original_amount_inr, customer_name, customer_phone, order_ref, discount_pct=15, fixed_discount=None):
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise RuntimeError("Razorpay credentials are not configured")
    amount = int(original_amount_inr)
    if amount <= 1 or (fixed_discount is None and not 0 < discount_pct < 100):
        raise ValueError("Invalid payment amount or discount")
    phone = normalize_whatsapp_phone(customer_phone)
    discount_amount = (
        min(amount - 1, int(fixed_discount))
        if fixed_discount is not None
        else round(amount * (discount_pct / 100.0))
    )
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


@app.route("/api/orders", methods=["POST", "OPTIONS"])
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
    """Allows founder/admin to send direct WhatsApp messages from cockpit with guaranteed WhatsApp Web fallback"""
    try:
        req = request.get_json(force=True)
        phone = req.get("phone")
        msg = req.get("message")
        if not phone or not msg:
            return jsonify({"status": "error", "message": "Phone and message are required"}), 400

        clean_phone = normalize_whatsapp_phone(phone)
        import urllib.parse
        encoded_text = urllib.parse.quote(msg)
        wa_link = f"https://wa.me/{clean_phone}?text={encoded_text}"
        web_wa_link = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_text}"

        delivery_method = "UNKNOWN"
        result = {}
        try:
            result = send_waha_text(clean_phone, msg)
            delivery_method = "WAHA_GATEWAY"
        except Exception as e_waha:
            logger.info("WAHA send failed or offline: %s", e_waha)
            delivery_method = "MANUAL_LINK_REQUIRED"
            result = {"error": str(e_waha)}

        record_message(clean_phone, "Customer", "OUTBOUND", "TEXT", msg)
        return jsonify({
            "status": "success" if delivery_method == "WAHA_GATEWAY" else "manual_required",
            "delivery_method": delivery_method,
            "wa_link": wa_link,
            "web_wa_link": web_wa_link,
            "result": result
        }), 200
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
@app.route("/api/extension/crm/send", methods=["POST", "OPTIONS"])
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
        if not isinstance(buttons, list) or len(buttons) > 3 or any(
            not isinstance(button, dict) or not str(button.get("text", "")).strip()
            for button in buttons
        ):
            return jsonify({"status": "error", "message": "Buttons must be a list of up to three labeled actions"}), 400

        clean_digits = normalize_whatsapp_phone(phone)
        if len(clean_digits) != 12 or not clean_digits.startswith("91"):
            return jsonify({"status": "error", "message": "Enter a valid Indian WhatsApp number"}), 400

        service_window_open = _within_customer_service_window(clean_digits)

        button_order = None
        linked_order_refs = set()
        waha_configured = bool(os.getenv("WAHA_GATEWAY_URL", "http://localhost:3000"))
        for button in buttons if isinstance(buttons, list) else []:
            button_id = str(button.get("id", ""))
            match = re.match(r"^btn_(?:confirm_cod|cod|cancel)_(.+)$", button_id)
            payment_match = re.match(r"^btn_pay(?:50)?_(.+)_\d+$", button_id)
            order_ref = (match or payment_match).group(1) if (match or payment_match) else ""
            if order_ref:
                b_order = get_order(order_ref)
                if not b_order or b_order["phone"][-10:] != clean_digits[-10:]:
                    return jsonify({"status": "error", "message": "Action button does not match a saved order for this customer"}), 409
                button_order = b_order
                linked_order_refs.add(order_ref)
                if not waha_configured and button_id.startswith(("btn_pay_", "btn_pay50_")) and not button_order.get("marketing_opt_in"):
                    return jsonify({"status": "error", "message": "Recorded marketing consent is required for payment offers"}), 409
            elif not waha_configured:
                return jsonify({"status": "error", "message": "Interactive CRM actions must reference a saved order"}), 400
        if len(linked_order_refs) > 1:
            return jsonify({"status": "error", "message": "All interactive actions must belong to the same saved order"}), 400

        if button_order is None and (service_window_open or waha_configured):
            open_orders = get_open_orders_for_phone(clean_digits)
            button_order = open_orders[0] if open_orders else None

        if not service_window_open and not waha_configured:
            if (
                button_order
                and button_order.get("whatsapp_opt_in")
                and button_order.get("marketing_opt_in")
                and os.getenv("META_ORDER_TEMPLATE_NAME")
            ):
                try:
                    template_result = send_interactive_order_confirmation(
                        clean_digits,
                        button_order["customer_name"],
                        button_order["order_ref"],
                        button_order["product_name"],
                        button_order["amount"],
                    )
                except (requests.RequestException, RuntimeError, ValueError) as error:
                    logger.warning("CRM template send failed: %s", type(error).__name__)
                    template_result = None
                if not template_result or not template_result.get("messages"):
                    import urllib.parse
                    encoded_text = urllib.parse.quote(text)
                    wa_link = f"https://wa.me/{clean_digits}?text={encoded_text}"
                    web_wa_link = f"https://web.whatsapp.com/send?phone={clean_digits}&text={encoded_text}"
                    return jsonify({
                        "status": "error",
                        "delivery_method": "MANUAL_LINK_REQUIRED",
                        "message": "The approved order template was not accepted. Review and send manually.",
                        "wa_link": wa_link,
                        "web_wa_link": web_wa_link,
                    }), 503
                wa_id = str(template_result["messages"][0].get("id", ""))
                record_message(
                    clean_digits,
                    button_order["customer_name"],
                    "OUTBOUND",
                    "ORDER_TEMPLATE",
                    f"Approved order template sent for {button_order['order_ref']}.",
                    wa_message_id=wa_id,
                )
                return jsonify({
                    "status": "success",
                    "delivery_method": "META_APPROVED_TEMPLATE",
                    "message": "Meta accepted the approved template; recipient delivery is not confirmed.",
                }), 200
            return jsonify({"status": "error", "message": "A recent customer message is required for a free-form reply. Outside the 24-hour service window, an approved template and recorded consent are required."}), 409

        delivery_method = "UNKNOWN"
        result = {}
        error_notes = []

        # Tier 1: Try WAHA Gateway (if active on localhost or custom gateway)
        try:
            if buttons and isinstance(buttons, list) and len(buttons) > 0:
                result = send_waha_buttons(clean_digits, text, buttons)
                delivery_method = "WAHA_BUTTONS" if result.get("interactive_buttons", True) else "WAHA_TEXT_FALLBACK"
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
                        btn_lines = [f"• {b.get('text', '')}" for b in buttons if b.get('text')]
                        if btn_lines:
                            meta_text += "\n\nPlease reply with one of these options:\n" + "\n".join(btn_lines)
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
            record_message(clean_digits, customer_name, "OUTBOUND", "TEXT", text)
            return jsonify({
                "status": "manual_required",
                "delivery_method": "MANUAL_LINK_REQUIRED",
                "message": "Automated WhatsApp gateway offline. Opening WhatsApp Web to deliver directly...",
                "wa_link": wa_link,
                "web_wa_link": web_wa_link,
                "error_notes": error_notes,
            }), 200

        # Record in database
        interactive_sent = delivery_method == "WAHA_BUTTONS" and bool(buttons)
        msg_type = "BUTTON_TEMPLATE" if interactive_sent else "TEXT"
        button_id_str = ",".join(b.get("id", "") for b in buttons) if interactive_sent else None
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
            "error_notes": None
        }), 200
    except Exception as e:
        logger.exception("Error sending message via CRM")
        return jsonify({"status": "error", "message": str(e)}), 500


def _within_customer_service_window(phone):
    # WAHA Baileys gateway operates from a linked phone without Meta Cloud API 24-hr service window blocks
    if os.getenv("WAHA_GATEWAY_URL"):
        return True

    last_inbound = get_last_inbound_at(phone)
    if not last_inbound:
        return False
    try:
        timestamp = datetime.fromisoformat(str(last_inbound).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            from datetime import timezone
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return (datetime.now(timestamp.tzinfo) - timestamp).total_seconds() <= 24 * 60 * 60
    except ValueError:
        logger.warning("Could not parse latest inbound message timestamp")
        return False


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


@app.route("/api/waha/status", methods=["GET"])
def api_waha_status():
    """Checks the health and active session status of WAHA WhatsApp gateway"""
    res = check_gateway_health()
    return jsonify({"status": "success", "gateway": res}), 200


_AVATAR_CACHE = {}
_AVATAR_CACHE_TTL = 3600  # 1 hour in-memory cache


@app.route("/api/customer/avatar/<phone>", methods=["GET"])
def api_customer_avatar(phone):
    """
    Proxies customer WhatsApp profile picture (DP) to Baileys gateway with in-memory TTL caching.
    Returns {"status": "success", "url": avatarUrl} or {"status": "not_found", "url": None}.
    Supports ?redirect=1 to redirect directly to the avatar image URL.
    """
    clean_digits = re.sub(r"\D", "", str(phone or ""))
    if len(clean_digits) == 10 and clean_digits[0] in "6789":
        normalized = "91" + clean_digits
    elif len(clean_digits) == 12 and clean_digits.startswith("91"):
        normalized = clean_digits
    elif len(clean_digits) == 11 and clean_digits.startswith("0"):
        normalized = "91" + clean_digits[1:]
    else:
        normalized = clean_digits

    if not normalized or len(normalized) < 10:
        return jsonify({"status": "not_found", "url": None}), 200

    now = time.time()
    cached = _AVATAR_CACHE.get(normalized)
    if cached:
        cached_url, cached_time = cached
        if now - cached_time < _AVATAR_CACHE_TTL:
            if request.args.get("redirect") == "1" and cached_url:
                return redirect(cached_url)
            return jsonify({
                "status": "success" if cached_url else "not_found",
                "url": cached_url,
                "cached": True,
            }), 200

    waha_url = (os.getenv("OPENWA_GATEWAY_URL") or os.getenv("WAHA_GATEWAY_URL") or "https://easily-bidding-ones-race.trycloudflare.com").rstrip("/")
    headers = {}
    api_key = os.getenv("WAHA_API_KEY", "")
    if api_key:
        headers["X-Api-Key"] = api_key

    avatar_url = None
    try:
        resp = requests.get(f"{waha_url}/api/avatar/{normalized}", headers=headers, timeout=5)
        if resp.ok:
            data = resp.json() if "application/json" in resp.headers.get("Content-Type", "") else {}
            if data.get("status") == "success" and data.get("url"):
                avatar_url = data["url"]
    except Exception as e:
        logger.debug("Avatar proxy fetch failed for %s: %s", normalized, e)

    _AVATAR_CACHE[normalized] = (avatar_url, now)

    if request.args.get("redirect") == "1" and avatar_url:
        return redirect(avatar_url)

    if avatar_url:
        return jsonify({"status": "success", "url": avatar_url}), 200
    return jsonify({"status": "not_found", "url": None}), 200


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




def get_workflow_message_text(workflow: str, customer_name: str, order_ref: str, product_name: str, amount: int, awb: str = "", courier_name: str = "", data: dict = None) -> str:
    """Generates authentic personalized copy for any D2C WhatsApp workflow to ensure guaranteed pre-filled 1-click delivery."""
    name = (customer_name or "Valued Customer").strip()
    order_tag = str(order_ref or "1001").replace("#", "").strip()
    total = int(amount or 349)
    data = data or {}

    if workflow in ("cod_confirm_prepay", "rto_49_prepay", "prepay_49", "49_prepay"):
        prepaid_total = max(total - 49, 100)
        upi_link = f"upi://pay?pa=zenlora@icici&pn=ZenloraStore&am={prepaid_total}&cu=INR&tn=Order_{order_tag}"
        return (
            f"Namaste, {name}! 🙏✨\n\n"
            f"Thank you for choosing *Zenlora* — India's home & lifestyle brand.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Your Order Summary*\n"
            f"• Order ID  : *#{order_tag}*\n"
            f"• Product   : {product_name}\n"
            f"• COD Total : ₹{total}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚡ *Exclusive Prepay Privilege — Save ₹49 Instantly!*\n"
            f"Pay now via UPI for *₹{prepaid_total}* (save ₹49 instantly):\n"
            f"🔗 {upi_link}\n\n"
            f"🛡️ *Zenlora Guarantee:*\n"
            f"• 100% Inspected & Quality-Tested Before Dispatch\n"
            f"• Priority Express Courier Shipping\n\n"
            f"Please reply *CONFIRM* to dispatch as COD or *PAY* to claim ₹49 discount."
        )
    elif workflow in ("rto_prepay", "15_prepay", "prepay_15"):
        savings = round(total * 0.15)
        prepaid_total = total - savings
        return (
            f"Namaste, {name}! 🙏✨\n\n"
            f"Thank you for choosing *Zenlora* — India's home & lifestyle brand.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Your Order Summary*\n"
            f"• Order ID  : *#{order_tag}*\n"
            f"• Product   : {product_name}\n"
            f"• COD Total : ₹{total}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚡ *Exclusive Prepay Privilege — Save 15% Instantly!*\n"
            f"Pay now via UPI for *₹{prepaid_total}* (save *₹{savings}* instantly).\n\n"
            f"🛡️ *Zenlora Guarantee:*\n"
            f"• 100% Inspected & Quality-Tested Before Dispatch\n"
            f"• Pan-India Express Delivery\n\n"
            f"Please reply *YES* to confirm your order or *PAY* to prepay."
        )
    elif workflow in ("rto_50_prepay", "rto_rs50_prepay", "50_prepay", "rs50_prepay", "prepay_50"):
        prepaid_total = max(total - 50, 99)
        return (
            f"Namaste, {name}! 🙏✨\n\n"
            f"Thank you for choosing *Zenlora*.\n\n"
            f"📦 *Order #{order_tag}* ({product_name})\n"
            f"• COD Total: ₹{total}\n"
            f"⚡ *Flat ₹50 OFF:* Pay *₹{prepaid_total}* online to save ₹50 instantly!\n\n"
            f"Reply *CONFIRM* to confirm COD delivery or *PAY* to claim ₹50 discount."
        )
    elif workflow in ("ofd_alert", "out_for_delivery", "shipping_check"):
        return (
            f"Namaste, {name}! 🚚✨\n\n"
            f"Your Zenlora parcel for Order *#{order_tag}* ({product_name}) is *OUT FOR DELIVERY* today!\n\n"
            f"💰 COD Amount to keep ready: *₹{total}* in cash or UPI.\n\n"
            f"Please ensure someone is available at your address to receive it. Thank you!"
        )
    elif workflow in ("address_fix", "request_landmark"):
        return (
            f"Namaste, {name}! 📍\n\n"
            f"Regarding your Zenlora Order *#{order_tag}*, the courier partner requires your complete house/flat number and nearby landmark for timely delivery.\n\n"
            f"Please reply with your complete house number and landmark so we can dispatch your parcel immediately! Thank you."
        )
    elif workflow in ("shipping_track", "order_tracking", "dispatch_tracking"):
        courier = courier_name or "Delhivery Express"
        tracking = awb or "AWB_PENDING"
        track_link = data.get("tracking_url") or "https://www.delhivery.com"
        return (
            f"Namaste, {name}! 📦✈️\n\n"
            f"Great news! Your Zenlora Order *#{order_tag}* ({product_name}) has been dispatched via *{courier}*!\n\n"
            f"• AWB Tracking: *{tracking}*\n"
            f"• Live Tracking: {track_link}\n\n"
            f"Thank you for shopping with Zenlora!"
        )
    elif workflow in ("custom_ai", "custom"):
        txt = str(data.get("message") or data.get("custom_text") or "").strip()
        if txt:
            return txt
    return f"Namaste {name}! Order #{order_tag} update from Zenlora Store."

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

        if not order and not (data.get("customer_name") and (data.get("amount") is not None)):
            return jsonify({"status": "error", "message": "A saved order reference is required"}), 404
        if order and order["phone"][-10:] != phone[-10:]:
            return jsonify({"status": "error", "message": "The phone number does not match this order"}), 409

        waha_configured = bool(os.getenv("WAHA_GATEWAY_URL", "http://localhost:3000"))
        if not waha_configured and order and not order.get("whatsapp_opt_in"):
            return jsonify({"status": "error", "message": "Recorded WhatsApp order-update consent is required"}), 409

        customer_name = (order["customer_name"] if order else data.get("customer_name")) or "Valued Customer"
        product_name = (order.get("product_name") if order else data.get("product_name")) or "Zenlora Lifestyle Item"
        amount = int(order["amount"] if order else data.get("amount", 0))
        address = (order.get("address") if order else data.get("address")) or ""
        pincode = (order.get("pincode") if order else data.get("pincode")) or ""
        awb = str((order.get("tracking_awb") if order else data.get("awb")) or "").strip()
        courier_name = str((order.get("courier_name") if order else data.get("courier_name")) or "Delhivery Express").strip()

        result = {}
        message_desc = ""

        formatted_message = get_workflow_message_text(workflow, customer_name, order_ref, product_name, amount, awb, courier_name, data)
        import urllib.parse
        encoded_text = urllib.parse.quote(formatted_message)
        wa_link = f"https://wa.me/{phone}?text={encoded_text}"
        web_wa_link = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_text}"

        delivery_method = "UNKNOWN"
        result = {}
        try:
            if workflow in ("cod_confirm_prepay", "rto_49_prepay", "prepay_49"):
                result = dispatch_cod_confirm_prepay(phone, customer_name, order_ref, product_name, amount)
                message_desc = f"COD Confirm + ₹49 Prepay sent for #{order_ref}"
            elif workflow == "rto_prepay":
                result = dispatch_rto_killer_prepay(phone, customer_name, order_ref, product_name, amount)
                message_desc = f"RTO Killer 15% Prepay Offer sent for #{order_ref}"
            elif workflow in ("rto_50_prepay", "rto_rs50_prepay"):
                result = dispatch_rto_killer_rs50_prepay(phone, customer_name, order_ref, product_name, amount)
                message_desc = f"RTO Killer Flat Rs 50 Prepay Offer sent for #{order_ref}"
            elif workflow == "address_fix":
                missing = data.get("missing_parts") or ["House / Flat No.", "Nearby Landmark"]
                result = dispatch_address_fix_request(phone, customer_name, order_ref, address, missing)
                message_desc = f"Address Fix Request sent for #{order_ref}"
            elif workflow == "shipping_track":
                track_url = str(data.get("tracking_url", "")).strip()
                result = dispatch_shipping_tracking(phone, customer_name, order_ref, product_name, awb or "AWB_PENDING", courier_name, track_url)
                message_desc = f"Shipment Tracking alert sent for #{order_ref}"
            elif workflow in ("ofd_alert", "out_for_delivery"):
                result = dispatch_ofd_confirmation(phone, customer_name, order_ref, product_name, amount)
                message_desc = f"Out For Delivery Alert sent for #{order_ref}"
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
            delivery_method = "WAHA_GATEWAY"
        except Exception as e_waha:
            logger.info("WAHA automated send failed or offline (%s). Using WhatsApp Web direct fallback.", e_waha)
            delivery_method = "MANUAL_LINK_REQUIRED"
            result = {"error": str(e_waha)}
            message_desc = f"{workflow.upper()} prepared via 1-Click WhatsApp Direct for #{order_ref}"

        wa_id = str(result.get("id") or result.get("messageId") or "")
        record_message(phone, customer_name, "OUTBOUND", workflow.upper(), formatted_message, wa_message_id=wa_id)
        log_event("SUCCESS", "RTO_KILLER_2", f"{message_desc} to {phone}.")

        return jsonify({
            "status": "success" if delivery_method == "WAHA_GATEWAY" else "manual_required",
            "delivery_method": delivery_method,
            "message": "WhatsApp message sent via Gateway" if delivery_method == "WAHA_GATEWAY" else f"Opening WhatsApp Web to send {workflow} directly...",
            "workflow": workflow,
            "wa_message_id": wa_id,
            "wa_link": wa_link,
            "web_wa_link": web_wa_link,
            "text": formatted_message,
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
    inbound_recorded = False
    try:
        payload = request.get_json(force=True, silent=True) or {}
        data = payload.get("payload") or payload

        from_chat = data.get("from") or data.get("chatId") or ""
        clean_phone = "".join(ch for ch in from_chat if ch.isdigit())[-10:]
        body = str(data.get("body") or data.get("text") or "").strip()
        button_id = str(data.get("selectedButtonId") or data.get("buttonId") or "").strip()
        message_key = data.get("key") if isinstance(data.get("key"), dict) else {}
        message_id = str(data.get("id") or data.get("messageId") or message_key.get("id") or f"waha_{int(time.time()*1000)}_{clean_phone}").strip()

        if not clean_phone or not (body or button_id):
            return jsonify({"status": "ignored"}), 200

        if not record_message(clean_phone, "Customer", "INBOUND", "BUTTON_REPLY" if button_id else "TEXT", body or button_id, button_id=button_id, wa_message_id=message_id):
            return jsonify({"status": "duplicate"}), 200
        inbound_recorded = True
        if button_id:
            _handle_whatsapp_button(clean_phone, "Customer", button_id, body, reply_sender=send_waha_text)
        elif body.strip().upper() in {"CONFIRM", "YES", "CANCEL", "NO"} or _looks_like_structured_address(body):
            _handle_customer_text_reply(clean_phone, "Customer", body, reply_sender=send_waha_text)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"WAHA Webhook error: {e}", exc_info=True)
        if inbound_recorded:
            log_event("ERROR", "WAHA_WEBHOOK", "Inbound message was recorded, but its automated action needs manual follow-up.")
            return jsonify({
                "status": "received_manual_followup",
                "message": "The inbound message was recorded, but the automated action failed. Review the conversation in ZenOS.",
            }), 200
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/whatsapp/quick-dispatch", methods=["POST", "OPTIONS"])
def api_quick_dispatch():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    order_ref = str(data.get("order_ref", "") or "").strip()
    template_type = str(data.get("template_type", "custom"))
    raw_phone = str(data.get("phone", "")).strip()
    if not raw_phone or not order_ref:
        return jsonify({"status": "error", "message": "Saved order reference and customer phone are required"}), 400

    try:
        phone = normalize_whatsapp_phone(raw_phone)
        order = get_order(order_ref)
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404
        if normalize_whatsapp_phone(order["phone"]) != phone:
            return jsonify({"status": "error", "message": "Phone number does not match order record"}), 409
        waha_configured = bool(os.getenv("WAHA_GATEWAY_URL", "http://localhost:3000"))
        if not waha_configured:
            if not order.get("whatsapp_opt_in"):
                return jsonify({"status": "error", "message": "Recorded WhatsApp order-update consent is required"}), 409
            if template_type in {"15_prepay", "prepay_15", "50_prepay", "rs50_prepay", "prepay_50", "vip_voucher"} and not order.get("marketing_opt_in"):
                return jsonify({"status": "error", "message": "Recorded marketing consent is required for this offer"}), 409
        service_window_open = _within_customer_service_window(phone)
        approved_template_available = (
            template_type in {"15_prepay", "prepay_15"} and bool(os.getenv("META_ORDER_TEMPLATE_NAME"))
        ) or (
            template_type == "shipping_check" and bool(os.getenv("META_OFD_TEMPLATE_NAME"))
        )
        customer_name = order["customer_name"]
        product_name = order["product_name"]
        amount = int(order["amount"])
        awb = str(order.get("tracking_awb") or "").strip()
        courier_name = str(order.get("courier_name") or "").strip()
        custom_text = str(data.get("custom_text") or data.get("message") or "").strip()

        formatted_message = custom_text if custom_text else get_workflow_message_text(template_type, customer_name, order_ref, product_name, amount, awb, courier_name, data)
        import urllib.parse
        encoded_text = urllib.parse.quote(formatted_message)
        wa_link = f"https://wa.me/{phone}?text={encoded_text}"
        web_wa_link = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_text}"

        delivery_method = "UNKNOWN"
        result = {}
        message_type = template_type.upper()

        try:
            if template_type in {"cod_confirm_prepay", "prepay_49", "49_prepay"}:
                result = dispatch_cod_confirm_prepay(phone, customer_name, order_ref, product_name, amount)
                message_type = "COD_CONFIRM_PREPAY_49"
            elif template_type in {"15_prepay", "prepay_15"}:
                result = dispatch_rto_killer_prepay(phone, customer_name, order_ref, product_name, amount)
                message_type = "ORDER_TEMPLATE"
            elif template_type in {"50_prepay", "rs50_prepay", "prepay_50"}:
                result = dispatch_rto_killer_rs50_prepay(phone, customer_name, order_ref, product_name, amount)
                message_type = "PREPAY_50_TEMPLATE"
            elif template_type in {"shipping_check", "ofd_alert", "out_for_delivery"}:
                result = dispatch_ofd_confirmation(phone, customer_name, order_ref, product_name, amount)
                message_type = "OFD_TEMPLATE"
            elif template_type in {"request_landmark", "address_fix"}:
                health = evaluate_address_health(order.get("address", ""), order.get("pincode", ""))
                result = dispatch_address_fix_request(phone, customer_name, order_ref, order.get("address", ""), health.get("missing_parts"))
                message_type = "ADDRESS_REQUEST"
            elif template_type in {"order_tracking", "shipping_track", "dispatch_tracking"}:
                requested_awb = str(data.get("awb", "")).strip() or awb or "AWB_PENDING"
                requested_courier = str(data.get("courier_name", "")).strip() or courier_name or "Delhivery Express"
                track_url = str(data.get("tracking_url", "")).strip()
                result = dispatch_shipping_tracking(phone, customer_name, order_ref, product_name, requested_awb, requested_courier, track_url)
                message_type = "ORDER_TRACKING"
            else:
                buttons = data.get("buttons") or []
                if buttons and isinstance(buttons, list) and len(buttons) > 0:
                    result = send_waha_buttons(phone, formatted_message, buttons)
                    message_type = "CUSTOM_BUTTONS"
                else:
                    result = send_waha_text(phone, formatted_message)
                    message_type = "TEXT_CUSTOM"
            delivery_method = "WAHA_GATEWAY"
        except Exception as e_waha:
            logger.info("WAHA send failed or offline (%s). Using WhatsApp Web direct fallback.", e_waha)
            delivery_method = "MANUAL_LINK_REQUIRED"
            result = {"error": str(e_waha)}

        wa_id = str(result.get("id") or result.get("messageId") or "")
        record_message(phone, customer_name, "OUTBOUND", message_type, formatted_message, wa_message_id=wa_id)
        log_event("SUCCESS", "QUICK_DISPATCH", f"{message_type} ({delivery_method}) to {phone}.")
        return jsonify({
            "status": "success" if delivery_method == "WAHA_GATEWAY" else "manual_required",
            "delivery_method": delivery_method,
            "message": "WhatsApp provider accepted the message" if delivery_method == "WAHA_GATEWAY" else "Opening WhatsApp Web directly to deliver message to customer...",
            "wa_message_id": wa_id,
            "wa_link": wa_link,
            "web_wa_link": web_wa_link,
            "text": formatted_message,
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


def _handle_whatsapp_button(sender_phone, sender_name, button_id, button_text, reply_sender=None):
    if button_id.startswith("btn_cart_checkout_"):
        cart_id = button_id[len("btn_cart_checkout_"):]
        try:
            mark_cart_recovered(cart_id=int(cart_id))
        except Exception:
            pass
        reply = f"Thanks, {sender_name}! Your cart checkout link has been confirmed. We look forward to fulfilling your Zenlora order!"
        result = (reply_sender or send_waha_text)(sender_phone, reply)
        wa_id = str(result.get("id") or result.get("messageId") or "")
        record_message(sender_phone, sender_name, "OUTBOUND", "TEXT", reply, wa_message_id=wa_id)
        return
    elif button_id.startswith("btn_cart_cancel_"):
        cart_id = button_id[len("btn_cart_cancel_"):]
        try:
            mark_cart_cancelled(cart_id=int(cart_id))
        except Exception:
            pass
        reply = f"Thanks for letting us know, {sender_name}. We have cancelled your cart reminder. Feel free to browse anytime!"
        result = (reply_sender or send_waha_text)(sender_phone, reply)
        wa_id = str(result.get("id") or result.get("messageId") or "")
        record_message(sender_phone, sender_name, "OUTBOUND", "TEXT", reply, wa_message_id=wa_id)
        return

    order_ref = ""
    action = ""
    offer_amount = ""
    if button_id.startswith("btn_pay_"):
        action = "pay"
        suffix = button_id[len("btn_pay_"):]
        if "_" in suffix:
            order_ref, offer_amount = suffix.rsplit("_", 1)
        else:
            order_ref = suffix
    elif button_id.startswith("btn_pay50_"):
        action = "pay_fixed_50"
        suffix = button_id[len("btn_pay50_"):]
        if "_" in suffix:
            order_ref, offer_amount = suffix.rsplit("_", 1)
        else:
            order_ref = suffix
    elif button_id.startswith("btn_confirm_cod_"):
        action = "confirm_cod"
        order_ref = button_id[len("btn_confirm_cod_"):]
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
    elif button_id.startswith("btn_ofd_available_"):
        action = "collect"
        order_ref = button_id[len("btn_ofd_available_"):]
    elif button_id.startswith("btn_ofd_reschedule_"):
        action = "reschedule_request"
        order_ref = button_id[len("btn_ofd_reschedule_"):]
    elif button_id.startswith("btn_ndr_tomorrow_"):
        action = "reschedule_request"
        order_ref = button_id[len("btn_ndr_tomorrow_"):]
    elif button_id.startswith("btn_ndr_call_"):
        action = "call_request"
        order_ref = button_id[len("btn_ndr_call_"):]
    elif button_id.startswith("btn_ndr_address_"):
        action = "address_request"
        order_ref = button_id[len("btn_ndr_address_"):]

    order = get_order(order_ref) if order_ref else None
    if order and order["phone"][-10:] != sender_phone[-10:]:
        return
    if order and order["status"] in {"CANCELLED", "CUSTOMER_CANCELLED", "DELIVERED", "RETURNED"}:
        return

    if action in {"pay", "pay_fixed_50"}:
        if not order:
            return
        if not order.get("marketing_opt_in") or (offer_amount and offer_amount != str(order["amount"])):
            return
        fixed_discount = 50 if action == "pay_fixed_50" else None
        payment_url, payable, saved = create_razorpay_payment_link(
            order["amount"], order["customer_name"], sender_phone, order_ref,
            fixed_discount=fixed_discount,
        )
        if not update_order_status(order_ref, "PREPAID_PENDING_LINK", {
            "razorpay_link": payment_url,
            "prepaid_amount": payable,
            "discount_amount": saved,
        }):
            raise RuntimeError("Payment link was created but the order could not be updated")
        reply = f"Your payment link for order {order_ref} is {payment_url}. Pay ₹{payable}; discount ₹{saved}."
    elif action == "confirm_cod":
        if order:
            update_order_status(order_ref, "CONFIRMED_COD")
        reply = f"Thanks, {sender_name}. Your COD CONFIRMATION for order {order_ref} is recorded. The seller will verify it before dispatch."
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
    elif action == "call_request":
        if not update_order_status(order_ref, "CUSTOMER_REQUESTED_CALL"):
            raise RuntimeError("Call request could not be recorded")
        reply = f"We recorded your request for a courier call before another delivery attempt for order {order_ref}."
    elif action == "address_request":
        if not update_order_status(order_ref, "CUSTOMER_REQUESTED_ADDRESS_UPDATE"):
            raise RuntimeError("Address update request could not be recorded")
        reply = f"Please send the complete address for order {order_ref}, including House/Flat, Street/Landmark, City & State, and Pincode. We will validate it before saving."
    else:
        return

    result = (reply_sender or send_whatsapp_message)(sender_phone, reply)
    wa_id = str(result.get("id") or result.get("messageId") or "")
    if not wa_id and result.get("messages"):
        wa_id = str(result["messages"][0].get("id", ""))
    record_message(sender_phone, sender_name, "OUTBOUND", "TEXT", reply, wa_message_id=wa_id)


def _looks_like_structured_address(body):
    normalized = body.lower()
    return (
        ("house" in normalized or "flat" in normalized)
        and ("landmark" in normalized or "street" in normalized)
        and ("pincode" in normalized or "pin code" in normalized or "pin:" in normalized)
    )


def _text_reply_intent(body):
    normalized = body.strip().upper()
    if normalized in {"STOP", "UNSUBSCRIBE"}:
        return "stop"
    if normalized in {"CONFIRM", "YES"} or re.match(r"^(?:✅\s*)?CONFIRM COD(?: ORDER)?(?:\s|$)", normalized):
        return "confirm"
    if normalized in {"CANCEL", "NO"} or re.match(r"^(?:❌\s*)?(?:REQUEST CANCELLATION|CANCEL(?: MY)? ORDER)(?:\s|$)", normalized):
        return "cancel"
    if normalized in {"PAY", "PREPAY"} or re.match(r"^(?:⚡\s*)?PAY\s+₹?\d+", normalized):
        return "pay_fixed_50" if "50 OFF" in normalized else "pay"
    return ""


def _is_supported_text_reply(body):
    return bool(_text_reply_intent(body)) or _looks_like_structured_address(body)


def _parse_structured_address(body):
    fields = {}
    patterns = {
        "house": r"^\s*(?:house\s*/\s*flat\s*no\.?|house\s*no\.?|flat\s*no\.?)\s*:\s*(.+?)\s*$",
        "street": r"^\s*(?:street\s*/\s*landmark|street|landmark)\s*:\s*(.+?)\s*$",
        "city_state": r"^\s*city\s*(?:&|and)\s*state\s*:\s*(.+?)\s*$",
        "pincode": r"^\s*(?:pincode|pin\s*code|pin)\s*:\s*([0-9]{6})\s*$",
    }
    for line in body.splitlines():
        for key, pattern in patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                fields[key] = match.group(1).strip()
    if not all(fields.get(key) for key in patterns):
        return None
    city_state = re.split(r"\s*,\s*", fields["city_state"], maxsplit=1)
    if len(city_state) != 2 or not all(city_state):
        return None
    address = f"{fields['house']}, {fields['street']}, {city_state[0]}, {city_state[1]}"
    health = evaluate_address_health(address, fields["pincode"])
    if health["status"] != "COMPLETE":
        return None
    return address, fields["pincode"], city_state[0], city_state[1]


def _select_reply_order(phone, body):
    open_orders = get_open_orders_for_phone(phone)
    referenced = [order for order in open_orders if order["order_ref"].lower() in body.lower()]
    if len(referenced) == 1:
        return referenced[0]
    return open_orders[0] if len(open_orders) == 1 else None


def _handle_customer_text_reply(phone, customer_name, body, reply_sender=None):
    intent = _text_reply_intent(body)
    if intent == "stop":
        revoke_whatsapp_consent(phone)
        reply = "You are unsubscribed from WhatsApp order updates and offers. We will not send further automated WhatsApp messages."
        result = (reply_sender or send_whatsapp_message)(phone, reply)
        wa_id = str(result.get("id") or result.get("messageId") or "")
        if not wa_id and result.get("messages"):
            wa_id = str(result["messages"][0].get("id", ""))
        record_message(phone, customer_name, "OUTBOUND", "TEXT", reply, wa_message_id=wa_id)
        return
    order = _select_reply_order(phone, body)
    if not order:
        reply = "Please include the order reference so we can update the correct order."
    elif intent == "confirm":
        if update_order_status(order["order_ref"], "CONFIRMED_COD"):
            reply = f"Thanks, {customer_name}. Your COD confirmation for order {order['order_ref']} is recorded. The seller will verify it before dispatch."
        else:
            reply = "We could not record the confirmation. Please contact the store team."
    elif intent == "cancel":
        if update_order_status(order["order_ref"], "CUSTOMER_CANCEL_REQUESTED"):
            reply = f"We received your cancellation request for order {order['order_ref']}. The seller must confirm cancellation; this message does not cancel the marketplace order."
        else:
            reply = "We could not record the cancellation request. Please contact the store team."
    elif intent in {"pay", "pay_fixed_50"}:
        if not order.get("marketing_opt_in"):
            reply = "A prepaid discount is not available for this order. Please contact the store team for payment options."
        else:
            fixed_discount = 50 if intent == "pay_fixed_50" else None
            payment_url, payable, saved = create_razorpay_payment_link(
                order["amount"], order["customer_name"], phone, order["order_ref"],
                fixed_discount=fixed_discount,
            )
            update_order_status(order["order_ref"], "PREPAID_PENDING_LINK", {
                "razorpay_link": payment_url,
                "prepaid_amount": payable,
                "discount_amount": saved,
            })
            reply = f"Your payment link for order {order['order_ref']} is {payment_url}. Pay ₹{payable}; discount ₹{saved}."
    else:
        address = _parse_structured_address(body)
        if not address:
            reply = "We received your message, but could not validate a complete shipping address. Please reply using the requested House/Flat, Street/Landmark, City & State, and 6-digit Pincode format."
        elif not update_order_address(order["order_ref"], *address):
            reply = "We could not save the address update. Please contact the store team before dispatch."
        else:
            reply = f"Thank you. The address update for order {order['order_ref']} has been saved for seller review; dispatch is not automatic."
    result = (reply_sender or send_whatsapp_message)(phone, reply)
    wa_id = str(result.get("id") or result.get("messageId") or "")
    if not wa_id and result.get("messages"):
        wa_id = str(result["messages"][0].get("id", ""))
    record_message(phone, customer_name, "OUTBOUND", "TEXT", reply, wa_message_id=wa_id)


@app.route("/webhook", methods=["POST"])
def handle_incoming_messages():
    raw_body = request.get_data(cache=True)
    if not verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256", "")):
        return jsonify({"status": "error", "message": "Invalid webhook signature"}), 401

    inbound_recorded = False
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
                    inbound_recorded = True
                    if button_id:
                        _handle_whatsapp_button(sender_phone, sender_name, button_id, button_text)
                    elif _is_supported_text_reply(text_body):
                        _handle_customer_text_reply(sender_phone, sender_name, text_body)
        return jsonify({"status": "ok"}), 200
    except (RuntimeError, ValueError) as error:
        logger.warning("WhatsApp webhook action was not completed: %s", type(error).__name__)
        if inbound_recorded:
            log_event("ERROR", "META_WEBHOOK", "Inbound message was recorded, but its automated action needs manual follow-up.")
            return jsonify({"status": "received_manual_followup", "message": "The event was recorded; review the conversation in ZenOS."}), 200
        return jsonify({"status": "error", "message": "Webhook action could not be processed"}), 500
    except Exception:
        logger.exception("WhatsApp webhook processing failed")
        if inbound_recorded:
            log_event("ERROR", "META_WEBHOOK", "Inbound message was recorded, but its automated action needs manual follow-up.")
            return jsonify({"status": "received_manual_followup", "message": "The event was recorded; review the conversation in ZenOS."}), 200
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


# ============================================================================
# Abandoned Cart Drip Engine (Milestone M3 R5)
# Auto-timed background daemon checking timestamps every 60s:
# Touch 1 at T+15m, Touch 2 at T+2h, Touch 3 at T+18h.
# ============================================================================

def _parse_cart_timestamp(val):
    if isinstance(val, datetime):
        return val.replace(tzinfo=None)
    if not val or not isinstance(val, str):
        return datetime.now(timezone.utc).replace(tzinfo=None)
    clean = val.replace("Z", "").replace("T", " ").strip()
    try:
        return datetime.fromisoformat(clean).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(clean.split("+")[0].strip(), fmt)
        except Exception:
            pass
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check_and_dispatch_cart_drips():
    """
    Checks all pending abandoned carts and evaluates timeline intervals:
    - Touch 1 at T+15m (Reminder + ₹49 discount).
    - Touch 2 at T+2h (Stock reservation timeout + ₹49 discount).
    - Touch 3 at T+18h (Final coupon expiry).
    Returns list of dispatch actions taken.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    pending = get_pending_cart_drips()
    dispatched = []

    for cart in pending:
        try:
            cart_id = cart["id"]
            phone = cart["phone"]
            customer_name = cart.get("customer_name") or "there"
            cart_items = cart.get("cart_items") or "Selected handcrafted items"
            cart_value = float(cart.get("cart_value") or 0.0)
            checkout_url = cart.get("checkout_url") or ""
            status = cart.get("status")

            # Fresh-read guard: re-verify status directly from DB before dispatching network request
            fresh_cart = get_abandoned_cart(cart_id)
            if not fresh_cart or fresh_cart.get("status") in ("RECOVERED", "CANCELLED"):
                logger.info("Cart #%s was recovered or cancelled prior to drip dispatch; skipping.", cart_id)
                continue
            status = fresh_cart.get("status")

            created_dt = _parse_cart_timestamp(cart.get("created_at"))
            elapsed_seconds = (now - created_dt).total_seconds()

            # Touch 1: Dispatched at T+15 mins (>= 900 seconds)
            if status == "ABANDONED" and elapsed_seconds >= 15 * 60:
                result = dispatch_cart_drip_touch1(
                    phone=phone,
                    customer_name=customer_name,
                    cart_id=cart_id,
                    cart_items=cart_items,
                    cart_value=cart_value,
                    checkout_url=checkout_url,
                )
                updated = update_cart_drip_status(cart_id, "TOUCH_1_SENT", "touch1_at")
                if not updated:
                    logger.warning("Cart #%s was recovered/cancelled during dispatch; status update guarded.", cart_id)
                    continue
                wa_id = str(result.get("id") or result.get("messageId") or "")
                record_message(phone, customer_name, "OUTBOUND", "CART_DRIP_1", f"Cart Drip Touch 1 sent for cart #{cart_id}", wa_message_id=wa_id)
                log_event("SUCCESS", "CART_DRIP", f"Touch 1 dispatched for cart #{cart_id} to {phone}.")
                dispatched.append({"cart_id": cart_id, "phone": phone, "touch": 1, "status": "TOUCH_1_SENT", "result": result})

            # Touch 2: Dispatched at T+2 hours (>= 7200 seconds)
            elif status == "TOUCH_1_SENT" and elapsed_seconds >= 2 * 3600:
                result = dispatch_cart_drip_touch2(
                    phone=phone,
                    customer_name=customer_name,
                    cart_id=cart_id,
                    cart_items=cart_items,
                    cart_value=cart_value,
                    checkout_url=checkout_url,
                )
                updated = update_cart_drip_status(cart_id, "TOUCH_2_SENT", "touch2_at")
                if not updated:
                    logger.warning("Cart #%s was recovered/cancelled during dispatch; status update guarded.", cart_id)
                    continue
                wa_id = str(result.get("id") or result.get("messageId") or "")
                record_message(phone, customer_name, "OUTBOUND", "CART_DRIP_2", f"Cart Drip Touch 2 sent for cart #{cart_id}", wa_message_id=wa_id)
                log_event("SUCCESS", "CART_DRIP", f"Touch 2 dispatched for cart #{cart_id} to {phone}.")
                dispatched.append({"cart_id": cart_id, "phone": phone, "touch": 2, "status": "TOUCH_2_SENT", "result": result})

            # Touch 3: Dispatched at T+18 hours (>= 64800 seconds)
            elif status == "TOUCH_2_SENT" and elapsed_seconds >= 18 * 3600:
                result = dispatch_cart_drip_touch3(
                    phone=phone,
                    customer_name=customer_name,
                    cart_id=cart_id,
                    cart_items=cart_items,
                    cart_value=cart_value,
                    checkout_url=checkout_url,
                )
                updated = update_cart_drip_status(cart_id, "TOUCH_3_SENT", "touch3_at")
                if not updated:
                    logger.warning("Cart #%s was recovered/cancelled during dispatch; status update guarded.", cart_id)
                    continue
                wa_id = str(result.get("id") or result.get("messageId") or "")
                record_message(phone, customer_name, "OUTBOUND", "CART_DRIP_3", f"Cart Drip Touch 3 sent for cart #{cart_id}", wa_message_id=wa_id)
                log_event("SUCCESS", "CART_DRIP", f"Touch 3 dispatched for cart #{cart_id} to {phone}.")
                dispatched.append({"cart_id": cart_id, "phone": phone, "touch": 3, "status": "TOUCH_3_SENT", "result": result})

        except Exception as e:
            logger.error("Error processing cart drip for cart %s: %s", cart.get("id"), e)

    return dispatched


_cart_drip_daemon_thread = None
_cart_drip_daemon_stop_event = threading.Event()


def _cart_drip_daemon_loop():
    logger.info("ZenOS Abandoned Cart Drip Daemon started (60s tick).")
    while not _cart_drip_daemon_stop_event.is_set():
        try:
            check_and_dispatch_cart_drips()
        except Exception as e:
            logger.error("Error in cart drip daemon tick: %s", e)
        _cart_drip_daemon_stop_event.wait(60)


def start_abandoned_cart_daemon():
    global _cart_drip_daemon_thread
    if _cart_drip_daemon_thread is None or not _cart_drip_daemon_thread.is_alive():
        _cart_drip_daemon_stop_event.clear()
        _cart_drip_daemon_thread = threading.Thread(
            target=_cart_drip_daemon_loop, daemon=True, name="CartDripDaemon"
        )
        _cart_drip_daemon_thread.start()
        logger.info("Abandoned cart daemon thread spawned.")


def stop_abandoned_cart_daemon():
    global _cart_drip_daemon_thread
    _cart_drip_daemon_stop_event.set()
    if _cart_drip_daemon_thread and _cart_drip_daemon_thread.is_alive():
        _cart_drip_daemon_thread.join(timeout=2)
    _cart_drip_daemon_thread = None


# Launch background daemon if enabled
if not os.getenv("ZENOS_DISABLE_DRIP_DAEMON") and not os.getenv("VERCEL"):
    try:
        start_abandoned_cart_daemon()
    except Exception as e:
        logger.warning("Could not start cart drip daemon on startup: %s", e)


@app.route("/api/cart/abandoned", methods=["POST", "OPTIONS"])
def api_create_abandoned_cart():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    raw_phone = str(data.get("phone", "")).strip()
    if not raw_phone:
        return jsonify({"status": "error", "message": "Customer phone number is required"}), 400

    phone = normalize_whatsapp_phone(raw_phone)
    customer_name = str(data.get("customer_name", "")).strip()
    cart_items = data.get("cart_items", "")
    cart_value = float(data.get("cart_value") or 0.0)
    checkout_url = str(data.get("checkout_url", "")).strip()

    try:
        cart = add_abandoned_cart(
            phone=phone,
            customer_name=customer_name,
            cart_items=cart_items,
            cart_value=cart_value,
            checkout_url=checkout_url,
        )
        return jsonify({
            "status": "success",
            "message": "Abandoned cart tracked successfully",
            "cart": cart,
            "cart_id": cart.get("id"),
        }), 201
    except Exception as e:
        logger.exception("Failed tracking abandoned cart: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cart/recover", methods=["POST", "OPTIONS"])
def api_recover_abandoned_cart():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    cart_id = data.get("cart_id")
    phone = data.get("phone")
    if not cart_id and not phone:
        return jsonify({"status": "error", "message": "Either cart_id or phone is required"}), 400

    if phone and not cart_id:
        clean = "".join(ch for ch in str(phone) if ch.isdigit())[-10:]
        if len(clean) < 10:
            return jsonify({"status": "error", "message": "A valid 10-digit customer phone number is required"}), 400

    try:
        count = mark_cart_recovered(cart_id=cart_id, phone=phone)
        return jsonify({
            "status": "success",
            "message": f"Recovered {count} abandoned cart(s)",
            "count": count,
        }), 200
    except Exception as e:
        logger.exception("Failed recovering abandoned cart: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cart/cancel", methods=["POST", "OPTIONS"])
def api_cancel_abandoned_cart():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    cart_id = data.get("cart_id")
    phone = data.get("phone")
    if not cart_id and not phone:
        return jsonify({"status": "error", "message": "Either cart_id or phone is required"}), 400

    if phone and not cart_id:
        clean = "".join(ch for ch in str(phone) if ch.isdigit())[-10:]
        if len(clean) < 10:
            return jsonify({"status": "error", "message": "A valid 10-digit customer phone number is required"}), 400

    try:
        count = mark_cart_cancelled(cart_id=cart_id, phone=phone)
        return jsonify({
            "status": "success",
            "message": f"Cancelled {count} abandoned cart(s)",
            "count": count,
        }), 200
    except Exception as e:
        logger.exception("Failed cancelling abandoned cart: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cart/abandoned", methods=["GET"])
def api_get_abandoned_carts():
    status = request.args.get("status")
    phone = request.args.get("phone")
    limit = int(request.args.get("limit", 50))
    try:
        carts = get_abandoned_carts(status=status, phone=phone, limit=limit)
        return jsonify({
            "status": "success",
            "carts": carts,
            "total": len(carts),
        }), 200
    except Exception as e:
        logger.exception("Failed fetching abandoned carts: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cart/drip/check", methods=["POST", "OPTIONS"])
def api_trigger_cart_drip_check():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    try:
        dispatched = check_and_dispatch_cart_drips()
        return jsonify({
            "status": "success",
            "message": f"Drip cycle completed. Dispatched {len(dispatched)} messages.",
            "dispatched_count": len(dispatched),
            "dispatched": dispatched,
        }), 200
    except Exception as e:
        logger.exception("Error executing manual cart drip check: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
