"""
ZenOS RTO Killer 2.0 - WAHA (WhatsApp HTTP API / Baileys) Client
Provides resilient, 100% free, zero-Meta-verification WhatsApp automation.
Connects with WAHA gateway running locally or on cloud (Render / Docker).
"""

import os
import re
import json
import logging
import requests
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

DEFAULT_WAHA_URL = (
    os.environ.get("OPENWA_GATEWAY_URL")
    or os.environ.get("WAHA_GATEWAY_URL")
    or "https://easily-bidding-ones-race.trycloudflare.com"
)
WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "")
WAHA_SESSION = os.environ.get("OPENWA_SESSION") or os.environ.get("WAHA_SESSION", "zenos")


def normalize_phone(raw_phone: str) -> str:
    """Normalizes phone to 91XXXXXXXXXX format for WhatsApp"""
    digits = re.sub(r"\D", "", str(raw_phone or ""))
    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        return "91" + digits[1:]
    return digits


def to_chat_id(phone: str) -> str:
    norm = normalize_phone(phone)
    return f"{norm}@c.us"


def get_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    return headers


def check_gateway_health(base_url: Optional[str] = None) -> Dict[str, Any]:
    url = (base_url or DEFAULT_WAHA_URL).rstrip("/")
    # 1. Try OpenWA session
    try:
        resp = requests.get(f"{url}/api/sessions/zenos", headers=get_headers(), timeout=4)
        if resp.ok:
            data = resp.json()
            is_active = data.get("status") in ("WORKING", "CONNECTED")
            return {
                "online": True,
                "active_session": is_active,
                "status": "CONNECTED" if is_active else data.get("status", "SCAN_QR"),
                "phone": data.get("phone", "919771370945"),
                "gateway_url": url,
                "sessions": [data]
            }
    except Exception:
        pass
    # 2. Try WAHA sessions list
    try:
        resp = requests.get(f"{url}/api/sessions", headers=get_headers(), timeout=4)
        if resp.ok:
            sessions = resp.json() if isinstance(resp.json(), list) else []
            active = any(s.get("status") == "WORKING" for s in sessions) if sessions else False
            return {"online": True, "active_session": active, "status": "CONNECTED" if active else "DISCONNECTED", "phone": "919771370945", "sessions": sessions}
    except Exception:
        pass
    # 3. Localhost fallback
    try:
        resp = requests.get("http://localhost:2785/api/sessions/zenos", timeout=2)
        if resp.ok:
            data = resp.json()
            is_active = data.get("status") in ("WORKING", "CONNECTED")
            return {
                "online": True,
                "active_session": is_active,
                "status": "CONNECTED" if is_active else data.get("status", "SCAN_QR"),
                "phone": data.get("phone", "919771370945"),
                "gateway_url": "http://localhost:2785",
                "sessions": [data]
            }
    except Exception as e:
        logger.debug("Gateway health check failed: %s", e)
    return {"online": False, "active_session": False, "status": "DISCONNECTED", "phone": None, "sessions": []}


def send_waha_text(phone: str, text: str, base_url: Optional[str] = None) -> Dict[str, Any]:
    url = (base_url or DEFAULT_WAHA_URL).rstrip("/")
    clean_phone = normalize_phone(phone)
    chat_id = f"{clean_phone}@s.whatsapp.net"
    payload = {
        "chatId": chat_id,
        "phone": clean_phone,
        "text": text,
        "message": text,
        "session": WAHA_SESSION,
    }
    endpoints = [
        f"{url}/api/sessions/zenos/messages/send-text",
        f"{url}/api/sendText",
        "http://localhost:2785/api/sessions/zenos/messages/send-text",
        "http://localhost:2785/api/sendText",
    ]
    last_err = None
    for ep in endpoints:
        try:
            resp = requests.post(ep, headers=get_headers(), json=payload, timeout=12)
            if resp.ok:
                return resp.json()
            last_err = f"Endpoint {ep} returned {resp.status_code}: {resp.text}"
        except Exception as ex:
            last_err = str(ex)
    raise RuntimeError(f"OpenWA gateway send failed: {last_err}")


def send_waha_buttons(
    phone: str,
    text: str,
    buttons: List[Dict[str, str]],
    footer: str = "Zenlora Store • Official Verification",
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends interactive buttons using WAHA /api/sendButtons.
    Buttons list format: [{'id': 'btn_1', 'text': 'Button Label'}, ...]
    """
    url = (base_url or DEFAULT_WAHA_URL).rstrip("/")
    chat_id = to_chat_id(phone)

    # WAHA button structure
    formatted_buttons = []
    for b in buttons[:3]:  # WhatsApp limits to 3 buttons
        b_id = b.get("id") or b.get("title") or "btn"
        b_text = b.get("text") or b.get("title") or "Option"
        formatted_buttons.append({"id": str(b_id), "text": str(b_text)})

    payload = {
        "chatId": chat_id,
        "text": text,
        "footer": footer,
        "buttons": formatted_buttons,
        "session": WAHA_SESSION,
    }

    try:
        resp = requests.post(
            f"{url}/api/sendButtons",
            headers=get_headers(),
            json=payload,
            timeout=15,
        )
        if resp.ok:
            result = resp.json()
            if isinstance(result, dict):
                result["interactive_buttons"] = True
                return result
            return {"gateway_response": result, "interactive_buttons": True}
        logger.warning("WAHA /api/sendButtons returned HTTP %s; sending a text-only version", resp.status_code)
    except Exception as e:
        logger.warning("WAHA /api/sendButtons failed: %s. Attempting fallback text...", e)

    fallback_text = text + "\n\nPlease reply with the exact option text below:\n"
    fallback_text += "\n".join(f"• {button['text']}" for button in formatted_buttons)
    fallback_text += f"\n\n{footer}"
    result = send_waha_text(phone, fallback_text, base_url=base_url)
    if isinstance(result, dict):
        result["interactive_buttons"] = False
        return result
    return {"gateway_response": result, "interactive_buttons": False}


def dispatch_cod_confirm_prepay(
    phone: str,
    customer_name: str,
    order_ref: str,
    product_name: str,
    amount: int,
    upi_vpa: str = "zenlora@icici",
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Milestone M3 R4: COD Confirmation + Instant Online Prepay.
    Generates 1-tap upi:// and wa.me links, anchoring on 100% Inspected & Quality-Tested Before Dispatch
    and Transit Damage Protection (Zero wholesale return/replacement claims).
    """
    name = (customer_name or "Valued Customer").strip()
    total = max(0, int(amount or 0))
    savings = min(49, max(0, total - 1))
    prepaid_total = max(1, total - savings)
    clean_p = normalize_phone(phone)
    order_tag = str(order_ref).replace("#", "").strip()

    upi_link = f"upi://pay?pa={upi_vpa}&pn=Zenlora%20Store&am={prepaid_total}&tn=Order_{order_tag}&cu=INR"
    wa_confirm_link = f"https://wa.me/{clean_p}?text=Confirm%20Order%20{order_tag}"

    header_line = f"⚡ *Exclusive Prepay Privilege — Save ₹{savings} Instantly!*\n" if savings > 0 else "⚡ *Exclusive Priority Prepay Privilege!*\n"
    cod_instruction = f"💬 *Or confirm COD delivery:*\n{wa_confirm_link}\n\n"

    message = (
        f"Namaste, {name}! 🙏✨\n\n"
        f"Thank you for choosing *Zenlora* — India's home & lifestyle brand.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Your Order Summary*\n"
        f"• Order ID   : *#{order_tag}*\n"
        f"• Product    : {product_name}\n"
        f"• COD Total  : ₹{total}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{header_line}"
        f"Pay online now via UPI for just *₹{prepaid_total}* (Flat ₹{savings} Discount) with priority dispatch!\n\n"
        f"📲 *1-Tap Instant UPI Pay:*\n"
        f"{upi_link}\n\n"
        f"{cod_instruction}"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection\n\n"
        f"Please tap an option below to confirm your order:"
    )

    buttons = [
        {"id": f"btn_pay_{order_tag}", "text": f"⚡ Pay ₹{prepaid_total} (Save ₹{savings})"},
        {"id": f"btn_confirm_cod_{order_tag}", "text": "✅ Confirm COD Order"},
        {"id": f"btn_cancel_{order_tag}", "text": "❌ Cancel Order"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Store • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )


def dispatch_rto_killer_prepay(
    phone: str,
    customer_name: str,
    order_ref: str,
    product_name: str,
    amount: int,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow 1: Dispatches the high-converting RTO Killer message with 15% instant prepay savings
    and 3 native interactive buttons.
    """
    name = (customer_name or "Valued Customer").strip()
    total = int(amount)
    savings = round(total * 0.15)
    prepaid_total = total - savings
    order_tag = str(order_ref).replace("#", "").strip()

    message = (
        f"Namaste, {name}! 🙏✨\n\n"
        f"Thank you for choosing *Zenlora* — India's home & lifestyle brand.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Your Order Summary*\n"
        f"• Order ID  : *#{order_tag}*\n"
        f"• Product   : {product_name}\n"
        f"• COD Total : ₹{total}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ *Exclusive Prepay Privilege — Save 15% Instantly!*\n"
        f"Choose the prepaid option to request a secure payment link for *₹{prepaid_total}* (save *₹{savings}*).\n\n"
        f"🛡️ *Zenlora Guarantee:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection\n\n"
        f"Please tap a button below to confirm your preference:"
    )

    buttons = [
        {"id": f"btn_pay_{order_tag}", "text": f"⚡ Pay ₹{prepaid_total} (15% OFF)"},
        {"id": f"btn_confirm_cod_{order_tag}", "text": "✅ Confirm COD Order"},
        {"id": f"btn_cancel_{order_tag}", "text": "❌ Cancel My Order"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Official Store • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )


def dispatch_rto_killer_rs50_prepay(
    phone: str,
    customer_name: str,
    order_ref: str,
    product_name: str,
    amount: int,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dispatches the high-converting RTO Killer message with Flat ₹50 instant prepay discount
    and 3 native interactive buttons.
    """
    name = (customer_name or "Valued Customer").strip()
    total = max(0, int(amount or 0))
    savings = min(50, max(0, total - 1))
    prepaid_total = max(1, total - savings)
    order_tag = str(order_ref).replace("#", "").strip()

    header_line = f"⚡ *Exclusive Prepay Privilege — Flat ₹{savings} Instant Discount!*\n" if savings > 0 else "⚡ *Exclusive Priority Prepay Privilege!*\n"

    message = (
        f"Namaste, {name}! 🙏✨\n\n"
        f"Thank you for choosing *Zenlora* — India's home & lifestyle brand.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Your Order Summary*\n"
        f"• Order ID  : *#{order_tag}*\n"
        f"• Product   : {product_name}\n"
        f"• COD Total : ₹{total}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{header_line}"
        f"Choose the prepaid option to request a secure payment link for *₹{prepaid_total}* (save *₹{savings}*).\n\n"
        f"🛡️ *Zenlora Guarantee:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection\n\n"
        f"Please tap a button below to confirm your preference:"
    )

    buttons = [
        {"id": f"btn_pay50_{order_tag}", "text": f"⚡ Pay ₹{prepaid_total} (₹{savings} OFF)"},
        {"id": f"btn_confirm_cod_{order_tag}", "text": "✅ Confirm COD Order"},
        {"id": f"btn_cancel_{order_tag}", "text": "❌ Cancel My Order"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Official Store • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )


def dispatch_ofd_confirmation(
    phone: str,
    customer_name: str,
    order_ref: str,
    product_name: str,
    amount: int,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dispatches Out For Delivery (OFD) morning alert ensuring customer is available with cash.
    """
    name = (customer_name or "Valued Customer").strip()
    total = int(amount)
    order_tag = str(order_ref).replace("#", "").strip()

    message = (
        f"Namaste, {name}! 🚚✨\n\n"
        f"Great news! Your *Zenlora* order *#{order_tag}* ({product_name}) is *Out for Delivery Today*!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Shipment Details*\n"
        f"• Order ID   : *#{order_tag}*\n"
        f"• Product    : {product_name}\n"
        f"• COD to Pay : ₹{total}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Please keep ₹{total} in cash or UPI ready for the delivery executive.\n\n"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection\n\n"
        f"To ensure seamless doorstep delivery, please confirm your availability today:"
    )

    buttons = [
        {"id": f"btn_ofd_available_{order_tag}", "text": "📦 I Can Collect Today"},
        {"id": f"btn_ofd_reschedule_{order_tag}", "text": "📅 Change Delivery Date"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Logistics • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )


def dispatch_address_fix_request(
    phone: str,
    customer_name: str,
    order_ref: str,
    raw_address: str,
    missing_parts: Optional[List[str]] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow 2: Dispatches the structured 4-point incomplete address correction prompt
    with 2 action buttons.
    """
    name = (customer_name or "Valued Customer").strip()
    clean_addr = (raw_address or "Not provided").strip()
    order_tag = str(order_ref).replace("#", "").strip()

    message = (
        f"Hello, {name}! 👋\n\n"
        f"Your *Zenlora* order *#{order_tag}* is being prepared for dispatch.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Address Verification Required*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Our courier partner needs a complete 4-point address to ensure doorstep delivery without delay:\n\n"
        f"📍 *Current Address on Record:*\n"
        f"\"{clean_addr}\"\n\n"
        f"📝 *Please reply with the complete 4 points:*\n"
        f"1. House / Flat / Building No.\n"
        f"2. Street / Road / Colony Name\n"
        f"3. Nearby Landmark (e.g. Near Temple / School)\n"
        f"4. 6-Digit Pincode\n\n"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection\n\n"
        f"Tap an option below or reply directly to this message:"
    )

    buttons = [
        {"id": f"btn_address_update_{order_tag}", "text": "📍 Update Address"},
        {"id": f"btn_confirm_address_{order_tag}", "text": "✅ Address is Correct"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Dispatch Team • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )


def dispatch_shipping_tracking(
    phone: str,
    customer_name: str,
    order_ref: str,
    product_name: str,
    awb: str,
    courier_name: str = "Delhivery Express",
    tracking_url: str = "",
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow 3: Dispatches live order tracking alert when AWB is generated.
    Auto-generates clickable live tracking link if tracking_url is not provided.
    """
    name = (customer_name or "Valued Customer").strip()
    c_name = courier_name or "Delhivery Express"
    awb_no = str(awb or "").strip()
    order_tag = str(order_ref).replace("#", "").strip()

    if not awb_no:
        raise ValueError("A real courier AWB is required")

    track_link = str(tracking_url or "").strip()
    if not track_link:
        if "delhivery" in c_name.lower():
            track_link = f"https://www.delhivery.com/track/package/{awb_no}"
        elif "bluedart" in c_name.lower():
            track_link = f"https://www.bluedart.com/tracking?numbers={awb_no}"
        else:
            track_link = f"https://shipway.com/track/{awb_no}"

    message = (
        f"Great news, {name}! 🚀\n\n"
        f"Your *Zenlora* order *#{order_tag}* has been dispatched and is on its way!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚚 *Shipment Details*\n"
        f"• Order ID   : *#{order_tag}*\n"
        f"• Product    : {product_name}\n"
        f"• Courier    : {c_name}\n"
        f"• AWB No.    : *{awb_no}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔎 *Track Live Parcel:*\n"
        f"{track_link}\n\n"
        f"Estimated delivery in 2-4 business days. Our delivery partner will call before arrival! 📞\n\n"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection"
    )

    return send_waha_text(phone, message, base_url=base_url)


def dispatch_ndr_rescue(
    phone: str,
    customer_name: str,
    order_ref: str,
    courier_name: str = "Delhivery",
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow 4: NDR (Non-Delivery Report) Rescue message sent when courier marks attempt as failed.
    """
    name = (customer_name or "Valued Customer").strip()
    c_name = courier_name or "Delhivery"
    order_tag = str(order_ref).replace("#", "").strip()

    message = (
        f"Hello, {name}! ⚠️\n\n"
        f"Our {c_name} delivery partner attempted to deliver your *Zenlora* order *#{order_tag}* today, but could not reach you.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Delivery Rescue Alert*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Please do not worry!* Your parcel has NOT been returned yet. We can arrange a priority re-attempt tomorrow.\n\n"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection\n\n"
        f"Please tap an option below to confirm your availability:"
    )

    buttons = [
        {"id": f"btn_ndr_tomorrow_{order_tag}", "text": "📅 Deliver Tomorrow"},
        {"id": f"btn_ndr_call_{order_tag}", "text": "📞 Call Before Coming"},
        {"id": f"btn_ndr_address_{order_tag}", "text": "📍 Update Address"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Care • Priority Parcel Rescue",
        base_url=base_url,
    )


def dispatch_cart_drip_touch1(
    phone: str,
    customer_name: str,
    cart_id: int,
    cart_items: str,
    cart_value: float,
    checkout_url: str = "",
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Touch 1 (T+15 mins): Helpful reminder + ₹49 Prepaid Discount + Zenlora brand name.
    Strictly zero wholesale return or replacement claims.
    """
    name = (customer_name or "there").strip()
    val = round(float(cart_value), 2)
    discounted_val = max(1.0, round(val - 49.0, 2))
    items_desc = cart_items or "Selected handcrafted items"
    link = checkout_url or "https://zenlora.com/checkout"

    message = (
        f"Namaste, {name}! 🛒✨\n\n"
        f"You left something special behind at *Zenlora*!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Your Reserved Items:*\n"
        f"{items_desc}\n"
        f"• Cart Total: ₹{val}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ *Special ₹49 Instant Discount Reserved For You!*\n"
        f"Complete your order now and save flat ₹49 with instant online prepay.\n\n"
        f"💰 *Payable Now:* *₹{discounted_val}* (Save ₹49)\n\n"
        f"🛍️ *Complete Your Checkout:*\n"
        f"{link}\n\n"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection\n\n"
        f"Tap below to claim your discount:"
    )

    buttons = [
        {"id": f"btn_cart_checkout_{cart_id}", "text": f"🛍️ Complete Order (-₹49)"},
        {"id": f"btn_cart_cancel_{cart_id}", "text": "❌ Not Interested"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Store • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )


def dispatch_cart_drip_touch2(
    phone: str,
    customer_name: str,
    cart_id: int,
    cart_items: str,
    cart_value: float,
    checkout_url: str = "",
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Touch 2 (T+2 hours): Stock reservation timeout notice + ₹49 Prepaid Discount.
    Strictly zero wholesale return or replacement claims.
    """
    name = (customer_name or "there").strip()
    val = round(float(cart_value), 2)
    discounted_val = max(1.0, round(val - 49.0, 2))
    items_desc = cart_items or "Selected handcrafted items"
    link = checkout_url or "https://zenlora.com/checkout"

    message = (
        f"Hello, {name}! ⏳\n\n"
        f"Your reserved stock at *Zenlora* is about to be released back to other shoppers!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Reserved Cart Items:*\n"
        f"{items_desc}\n"
        f"• Value: ₹{val} (₹{discounted_val} with ₹49 off)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"We can only hold limited stock items for a brief window before releasing them.\n\n"
        f"Claim your order now with flat ₹49 off before the items sell out:\n"
        f"{link}\n\n"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection"
    )

    buttons = [
        {"id": f"btn_cart_checkout_{cart_id}", "text": "🛍️ Secure My Items"},
        {"id": f"btn_cart_cancel_{cart_id}", "text": "❌ Cancel Cart"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Store • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )


def dispatch_cart_drip_touch3(
    phone: str,
    customer_name: str,
    cart_id: int,
    cart_items: str,
    cart_value: float,
    checkout_url: str = "",
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Touch 3 (T+18 hours): Final coupon expiry notice + Zenlora brand name.
    Strictly zero wholesale return or replacement claims.
    """
    name = (customer_name or "there").strip()
    val = round(float(cart_value), 2)
    items_desc = cart_items or "Selected handcrafted items"
    link = checkout_url or "https://zenlora.com/checkout"

    message = (
        f"Namaste, {name}! 🚨\n\n"
        f"Final Notice: Your exclusive ₹49 discount voucher at *Zenlora* is *expiring shortly*!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Cart Items:*\n"
        f"{items_desc}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"This is your last opportunity to complete checkout with your special ₹49 promotional coupon before it is permanently voided.\n\n"
        f"🔗 *Final Checkout Link:*\n"
        f"{link}\n\n"
        f"🛡️ *Zenlora Quality Assurance:*\n"
        f"• 100% Inspected & Quality-Tested Before Dispatch\n"
        f"• Transit Damage Protection"
    )

    buttons = [
        {"id": f"btn_cart_checkout_{cart_id}", "text": "🛍️ Use Coupon Before Expiry"},
        {"id": f"btn_cart_cancel_{cart_id}", "text": "❌ Do Not Remind"},
    ]

    return send_waha_buttons(
        phone=phone,
        text=message,
        buttons=buttons,
        footer="Zenlora Store • 100% Inspected & Quality-Tested Before Dispatch",
        base_url=base_url,
    )
