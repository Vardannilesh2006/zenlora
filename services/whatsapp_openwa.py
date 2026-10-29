"""
ZenOS OpenWA WhatsApp Client
Direct, high-speed, 100% Meta-independent WhatsApp messaging.
Connects directly to OpenWA Gateway running on http://localhost:2785.
"""

import os
import re
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

OPENWA_GATEWAY_URL = os.environ.get("OPENWA_GATEWAY_URL", "http://localhost:2785").rstrip("/")
OPENWA_SESSION = os.environ.get("OPENWA_SESSION", "zenos")


def normalize_phone(raw_phone: str) -> str:
    """Normalizes phone to clean 10-digit or 12-digit 91XXXXXXXXXX format"""
    digits = re.sub(r"\D", "", str(raw_phone or ""))
    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        return "91" + digits[1:]
    return digits


def check_gateway_health(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Checks if OpenWA gateway is online and WhatsApp session is active"""
    url = (base_url or OPENWA_GATEWAY_URL).rstrip("/")
    try:
        resp = requests.get(f"{url}/api/sessions/{OPENWA_SESSION}", timeout=3)
        if resp.ok:
            data = resp.json()
            is_connected = data.get("status") == "WORKING"
            return {
                "online": True,
                "connected": is_connected,
                "phone": data.get("phone"),
                "status": data.get("status")
            }
    except Exception as e:
        logger.debug("OpenWA health check failed: %s", e)
    return {"online": False, "connected": False, "phone": None, "status": "OFFLINE"}


def send_openwa_text(phone: str, text: str, base_url: Optional[str] = None) -> Dict[str, Any]:
    """Sends a formatted WhatsApp message to an Indian phone number via OpenWA"""
    url = (base_url or OPENWA_GATEWAY_URL).rstrip("/")
    norm_phone = normalize_phone(phone)
    chat_id = f"{norm_phone}@s.whatsapp.net"

    endpoint = f"{url}/api/sessions/{OPENWA_SESSION}/messages/send-text"
    payload = {
        "chatId": chat_id,
        "phone": norm_phone,
        "text": text
    }

    try:
        resp = requests.post(endpoint, json=payload, timeout=12)
        if resp.ok:
            data = resp.json()
            logger.info("OpenWA message sent to %s (ID: %s)", norm_phone, data.get("id"))
            return {"status": "ok", "delivered": True, "id": data.get("id"), "raw": data}
        logger.warning("OpenWA error %s: %s", resp.status_code, resp.text)
        return {"status": "error", "delivered": False, "message": resp.text}
    except Exception as ex:
        logger.error("OpenWA connection exception: %s", ex)
        return {"status": "error", "delivered": False, "message": str(ex)}


def send_openwa_image(phone: str, image_url: str, caption: str = "", base_url: Optional[str] = None) -> Dict[str, Any]:
    """Sends an image with caption via OpenWA"""
    url = (base_url or OPENWA_GATEWAY_URL).rstrip("/")
    norm_phone = normalize_phone(phone)
    chat_id = f"{norm_phone}@s.whatsapp.net"

    endpoint = f"{url}/api/sessions/{OPENWA_SESSION}/messages/send-image"
    payload = {
        "chatId": chat_id,
        "phone": norm_phone,
        "url": image_url,
        "caption": caption
    }

    try:
        resp = requests.post(endpoint, json=payload, timeout=15)
        if resp.ok:
            return {"status": "ok", "delivered": True, "raw": resp.json()}
        return {"status": "error", "delivered": False, "message": resp.text}
    except Exception as ex:
        return {"status": "error", "delivered": False, "message": str(ex)}


# ─── QUICK TEMPLATE AUTOMATIONS ───────────────────────────────────────────────

def dispatch_order_confirmation(order: Dict[str, Any]) -> Dict[str, Any]:
    """Template 1: COD Order Confirmation"""
    cust_name = order.get("customer_name") or "Valued Customer"
    order_id = order.get("order_ref") or order.get("order_id") or "ZEN"
    amount = order.get("amount") or 349
    address = order.get("address") or "Your delivery address"
    product = order.get("product_name") or "Zenlora Order"

    msg = (
        f"Namaste *{cust_name}* Ji! 🙏\n\n"
        f"Aapka order *Zenlora* par confirm ho chuka hai!\n\n"
        f"📦 *Product:* {product}\n"
        f"💰 *Total Amount:* ₹{amount} (Cash on Delivery)\n"
        f"📍 *Delivery Address:* {address}\n\n"
        f"Kripya dispatch se pehle confirm karein:\n"
        f"👉 *'YES'* reply karein to CONFIRM order\n"
        f"👉 *'CANCEL'* reply karein to Cancel\n\n"
        f"Team Zenlora\n"
        f"Support: +91 7250366344"
    )
    return send_openwa_text(order.get("phone", ""), msg)


def dispatch_rto_killer_prepay(order: Dict[str, Any]) -> Dict[str, Any]:
    """Template 2: RTO Killer (15% OFF Online Prepayment)"""
    cust_name = order.get("customer_name") or "Valued Customer"
    amount = int(order.get("amount") or 349)
    discount = int(amount * 0.15)
    final_amt = amount - discount
    pay_link = order.get("payment_link") or "https://rzp.io/l/zenlora"

    msg = (
        f"⚡ *SPECIAL PRIVILEGE OFFER* for *{cust_name}*!\n\n"
        f"Aapke order par *15% Extra Discount* (Save ₹{discount}) mil raha hai!\n\n"
        f"💵 Original Price: ~₹{amount}~\n"
        f"🎉 *Discounted Price: ₹{final_amt} Only!*\n\n"
        f"Agar aap online pay karte hain toh hum priority air shipping se deliver karenge.\n"
        f"🔗 *Pay Securely via UPI/Card:*\n"
        f"{pay_link}\n\n"
        f"_Pay karne ke baad delivery boy ko zero cash dena hoga!_"
    )
    return send_openwa_text(order.get("phone", ""), msg)


def dispatch_rto_killer_rs50_prepay(order: Dict[str, Any]) -> Dict[str, Any]:
    """Template 2B: RTO Killer (₹50 Advance Cashback / Lock Order)"""
    cust_name = order.get("customer_name") or "Valued Customer"
    amount = int(order.get("amount") or 349)
    remaining = amount - 50
    pay_link = order.get("payment_link") or "https://rzp.io/l/zenlora-50"

    msg = (
        f" Namaste *{cust_name}* Ji! 🌟\n\n"
        f"Aapke order ko *100% Dispatch Guarantee* karne ke liye bas *₹50 Advance Token* pay karein aur payein *₹50 Instant Cashback*!\n\n"
        f"👉 *Bas ₹50 pay karein:* {pay_link}\n"
        f"💰 Baki amount (₹{remaining}) delivery ke waqt Cash on Delivery dein.\n\n"
        f"_Is se aapka order direct Priority Courier se dispatch ho jayega!_"
    )
    return send_openwa_text(order.get("phone", ""), msg)


def dispatch_address_fix_request(order: Dict[str, Any], health_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Template 3: Missing Address / Landmark Fix"""
    cust_name = order.get("customer_name") or "Valued Customer"
    address = order.get("address") or ""

    msg = (
        f"⚠️ *Important Address Update Notice*\n\n"
        f"Namaste *{cust_name}* Ji,\n"
        f"Courier partner ko aapka address locate karne me dikkat ho sakti hai kyunki House Number ya Landmark missing hai:\n\n"
        f"📝 *Current Address:* {address}\n\n"
        f"Kripya courier delivery fail ya return hone se bachane ke liye apna *Exact House/Flat No, Gali/Road, aur Nearby Landmark (e.g. Near Shiv Mandir / School)* yaha reply karein.\n\n"
        f"Aapka reply aate hi hum order dispatch kar denge!"
    )
    return send_openwa_text(order.get("phone", ""), msg)


def dispatch_ofd_confirmation(order: Dict[str, Any]) -> Dict[str, Any]:
    """Template 4: Out For Delivery (OFD) Alert"""
    cust_name = order.get("customer_name") or "Valued Customer"
    product = order.get("product_name") or "Zenlora Package"
    amount = order.get("amount") or 349

    msg = (
        f"🚚 *OUT FOR DELIVERY ALERT!*\n\n"
        f"Namaste *{cust_name}* Ji,\n"
        f"Aapka *{product}* aaj delivery executive le kar nikal chuka hai!\n\n"
        f"💵 *Amount to Pay:* ₹{amount} (COD)\n\n"
        f"Kripya confirm karein:\n"
        f"👉 *'AVAILABLE'* reply karein agar aap receive karne ke liye ghar par hain.\n"
        f"👉 *'TOMORROW'* reply karein agar kal deliver karwana chahte hain.\n\n"
        f"Executive ka call attend zaroor karein!"
    )
    return send_openwa_text(order.get("phone", ""), msg)


def dispatch_shipping_tracking(order: Dict[str, Any], tracking_info: Dict[str, Any]) -> Dict[str, Any]:
    """Template 5: Live Courier Tracking Details"""
    cust_name = order.get("customer_name") or "Valued Customer"
    courier = tracking_info.get("courier") or "BlueDart / Delhivery"
    awb = tracking_info.get("awb") or "AWB"
    track_url = tracking_info.get("tracking_url") or f"https://shipway.com/track/{awb}"

    msg = (
        f"📦 *ORDER DISPATCHED!*\n\n"
        f"Namaste *{cust_name}* Ji,\n"
        f"Aapka order courier se dispatch ho gaya hai!\n\n"
        f"🚚 *Courier:* {courier}\n"
        f"🔢 *AWB Number:* {awb}\n"
        f"📍 *Live Tracking Link:*\n{track_url}\n\n"
        f"Expected Delivery: 2-4 business days.\n"
        f"Thank you for choosing Zenlora!"
    )
    return send_openwa_text(order.get("phone", ""), msg)


def dispatch_ndr_rescue(order: Dict[str, Any]) -> Dict[str, Any]:
    """Template 6: NDR Delivery Re-Attempt (Non-Delivery Rescue)"""
    cust_name = order.get("customer_name") or "Valued Customer"

    msg = (
        f"🚨 *Delivery Failed Attempt Notice*\n\n"
        f"Namaste *{cust_name}* Ji,\n"
        f"Courier boy ne aapka order deliver karne ki koshish ki thi par delivery incomplete rahi (Customer Unavailable / Door Closed).\n\n"
        f"Kya hum kal dobara re-attempt karwayein?\n"
        f"👉 *'RETRY'* reply karein taaki hum re-delivery schedule kar dein.\n"
        f"👉 Agar address galat tha toh correct address reply karein.\n\n"
        f"Order return hone se pehle kripya reply karein!"
    )
    return send_openwa_text(order.get("phone", ""), msg)
