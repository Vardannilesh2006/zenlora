"""
ZenOS RTO Killer 2.0 - AI Founder Concierge & Dynamic Button Generator
Transforms raw founder notes/Hinglish prompts into premium English D2C WhatsApp communications
with auto-generated context-aware interactive buttons.
"""

import os
import re
import json
import logging
import requests
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def generate_d2c_fallback(
    raw_prompt: str,
    customer_name: str,
    order_ref: str,
    product_name: str,
    amount: int = 349,
) -> Dict[str, Any]:
    """
    Institutional D2C rules engine that parses raw prompt in Hindi, Hinglish, or English
    and generates premium English message + context-aware native buttons without external API dependencies.
    """
    name = (customer_name or "Valued Customer").strip()
    clean_prompt = raw_prompt.strip()
    prompt_lower = clean_prompt.lower()
    total = int(amount) if amount else 349
    ref = order_ref.strip() or "ZN-1001"
    prod = product_name.strip() or "Zenlora Lifestyle Product"

    def has_any_word(words: List[str], text: str) -> bool:
        for w in words:
            if re.search(r'\b' + re.escape(w) + r'\b', text, re.IGNORECASE):
                return True
        return False

    # Intent detection with word boundaries
    is_address = has_any_word([
        "address", "addresh", "aadresh", "aaduhra", "aadhura", "adhura", "aadha",
        "landmark", "gali", "house", "pincode", "pin", "missing", "incomplete", "kam", "galat"
    ], prompt_lower)
    is_prepay = has_any_word([
        "prepay", "prepaid", "discount", "offer", "50", "15%", "online", "upi", "save", "bachat"
    ], prompt_lower)
    is_confirm = has_any_word([
        "confirm", "pakka", "dispatch", "ready", "pack", "approved", "bhejna", "order confirm"
    ], prompt_lower)
    is_delivery = has_any_word([
        "time", "baje", "deliver", "delivery", "aayega", "out for delivery", "reach", "ghar", "available"
    ], prompt_lower)
    is_tracking = has_any_word([
        "track", "tracking", "awb", "courier", "kaha hai", "status", "delhivery", "shipped"
    ], prompt_lower)
    is_color = has_any_word([
        "color", "colour", "red", "blue", "black", "gold", "golden", "design", "variant"
    ], prompt_lower)
    is_alternate_phone = has_any_word([
        "phone", "number", "alternate", "dusra", "contact", "call"
    ], prompt_lower)

    buttons = []
    message = ""

    if is_address:
        buttons = [
            {"id": f"btn_addr_full_{ref}", "text": "📍 Send Full Address"},
            {"id": f"btn_landmark_{ref}", "text": "🏛️ Share Landmark"},
        ]
        message = (
            f"Hello, {name}! 👋✨\n\n"
            f"Thank you for choosing *Zenlora* — India's festive home & lifestyle brand.\n"
            f"We are preparing your order *#{ref}* ({prod}) for priority dispatch.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 *Delivery Address Verification Required*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Our courier partner requires your complete delivery details to ensure seamless, first-attempt doorstep delivery without any delay:\n\n"
            f"1️⃣ *House / Flat / Shop Number:* [Please reply]\n"
            f"2️⃣ *Building / Street / Gali Name:* [Please reply]\n"
            f"3️⃣ *Nearest Landmark (Temple, School, Chowk):* [Please reply]\n"
            f"4️⃣ *City & 6-Digit PIN Code:* [Please reply]\n\n"
            f"Please tap a button below or reply directly to this message with your complete details!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    elif is_prepay:
        is_50 = "50" in prompt_lower or "flat 50" in prompt_lower
        if is_50:
            savings = 50
            prepaid_total = max(1, total - 50)
            offer_title = "Flat ₹50 Instant Discount"
            btn_text = f"⚡ Pay ₹{prepaid_total} (₹50 OFF)"
        else:
            savings = round(total * 0.15)
            prepaid_total = total - savings
            offer_title = "Flat 15% Instant Discount"
            btn_text = f"⚡ Pay ₹{prepaid_total} (15% OFF)"

        upi_note = f"Prepay {ref}"
        upi_link = f"upi://pay?pa=zenlora@upi&pn=Zenlora%20Store&am={prepaid_total}&cu=INR&tn={upi_note}"

        buttons = [
            {"id": f"btn_prepay_{ref}", "text": btn_text},
            {"id": f"btn_confirm_cod_{ref}", "text": "✅ Confirm COD Order"},
            {"id": f"btn_cancel_{ref}", "text": "❌ Cancel My Order"},
        ]
        message = (
            f"Hello, {name}! 🙏✨\n\n"
            f"Thank you for choosing *Zenlora* — India's home & lifestyle brand.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Your Order Summary*\n"
            f"• Order ID   : *#{ref}*\n"
            f"• Product    : {prod}\n"
            f"• COD Total  : ₹{total}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚡ *Exclusive Prepay Privilege — {offer_title}!* 🎉\n"
            f"Pay online right now and pay only *₹{prepaid_total}* (You save *₹{savings}* straight away + Free Priority Express Shipping!)\n\n"
            f"👉 *Instant UPI Payment Link:* {upi_link}\n\n"
            f"Please tap a button below to confirm your preference:\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    elif is_confirm:
        buttons = [
            {"id": f"btn_dispatch_yes_{ref}", "text": "✅ Confirm Dispatch"},
            {"id": f"btn_cancel_order_{ref}", "text": "❌ Cancel Order"},
        ]
        message = (
            f"Hello, {name}! 🙏✨\n\n"
            f"Thank you for choosing *Zenlora*! We are preparing your order *#{ref}* for priority dispatch.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Order Dispatch Confirmation*\n"
            f"• Order ID   : *#{ref}*\n"
            f"• Item       : {prod}\n"
            f"• COD Amount : ₹{total}\n"
            f"• Status     : Quality Checked & Ready to Ship\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Please confirm your order by tapping below so our courier team can pick it up today:\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    elif is_delivery:
        buttons = [
            {"id": f"btn_available_today_{ref}", "text": "✅ Yes, I am Available"},
            {"id": f"btn_reschedule_tomorrow_{ref}", "text": "⏰ Deliver Tomorrow"},
        ]
        message = (
            f"Hello, {name}! 🚚✨\n\n"
            f"Your *Zenlora* order *#{ref}* ({prod}) is out for delivery today!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Delivery Coordination*\n"
            f"• COD to Pay: ₹{total}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Our delivery executive will arrive at your address today. "
            f"Please tap below to confirm if someone will be available to collect the parcel:\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    elif is_tracking:
        buttons = [
            {"id": f"btn_track_{ref}", "text": "🔎 Track My Order"},
            {"id": f"btn_help_{ref}", "text": "📞 Customer Support"},
        ]
        message = (
            f"Great news, {name}! 🚀\n\n"
            f"Your *Zenlora* order *#{ref}* ({prod}) has been shipped and is on its way!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🚚 *Shipment Details*\n"
            f"• Order ID  : *#{ref}*\n"
            f"• Product   : {prod}\n"
            f"• Partner   : Delhivery Express\n"
            f"• Status    : In Transit (2-4 Days Delivery)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"You will receive live tracking updates directly as your package approaches your destination.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    elif is_color:
        if "red" in prompt_lower and "gold" in prompt_lower:
            buttons = [
                {"id": "btn_color_red", "text": "🔴 Red Festive Edition"},
                {"id": "btn_color_gold", "text": "🟡 Royal Gold Edition"},
            ]
        elif "blue" in prompt_lower and "black" in prompt_lower:
            buttons = [
                {"id": "btn_color_blue", "text": "🔵 Classic Blue"},
                {"id": "btn_color_black", "text": "⚫ Midnight Black"},
            ]
        else:
            buttons = [
                {"id": "btn_choice_a", "text": "✨ Option A"},
                {"id": "btn_choice_b", "text": "🌟 Option B"},
            ]
        message = (
            f"Hello, {name}! 👋✨\n\n"
            f"Thank you for choosing *Zenlora*! We are preparing your order *#{ref}* ({prod}).\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎨 *Variant Confirmation*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"To ensure you receive your preferred design variant, could you please confirm your color choice by tapping an option below?\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    elif is_alternate_phone:
        buttons = [
            {"id": f"btn_share_alt_{ref}", "text": "📱 Provide Alternate No"},
            {"id": f"btn_primary_ok_{ref}", "text": "✅ This Number is Active"},
        ]
        message = (
            f"Hello, {name}! 👋✨\n\n"
            f"Thank you for choosing *Zenlora* regarding order *#{ref}* ({prod}).\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📞 *Delivery Contact Update*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"To guarantee uninterrupted communication during doorstep delivery, please let us know if you have an alternate contact number for delivery coordination.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    else:
        buttons = [
            {"id": f"btn_ack_{ref}", "text": "✅ Acknowledged"},
            {"id": f"btn_help_{ref}", "text": "📞 Need Help"},
        ]
        capitalized = clean_prompt[0].upper() + clean_prompt[1:] if clean_prompt else ""
        message = (
            f"Hello, {name}! 👋✨\n\n"
            f"Thank you for being a part of the *Zenlora* community regarding order *#{ref}* ({prod}).\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 *Store Team Update*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{capitalized}.\n\n"
            f"If you have any questions or need adjustments, please let us know!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 _Team Zenlora_ | zenlora.store"
        )

    return {
        "message": message,
        "buttons": buttons,
        "engine": "zenlora_d2c_rules_engine",
    }


def polish_with_ai_concierge(
    raw_prompt: str,
    customer_name: str = "Valued Customer",
    order_ref: str = "",
    product_name: str = "",
    amount: int = 0,
) -> Dict[str, Any]:
    """
    Transforms raw founder prompt into an ultra-premium English D2C brand message with
    auto-generated interactive buttons. Uses Gemini Flash when configured, otherwise falls back
    to the Zenlora institutional D2C rules engine.
    """
    if not raw_prompt or not raw_prompt.strip():
        raise ValueError("Founder prompt cannot be empty")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={gemini_key}"
            system_prompt = (
                "You are the Lead Communications Architect for Zenlora (zenlora.store), an elite Indian home & lifestyle D2C brand. "
                "The founder has provided a quick instruction in raw Hindi, Hinglish, or shorthand English. "
                "Your mission: Transform this instruction into a warm, polite, highly polished WhatsApp message in flawless English, "
                "and generate 2 or 3 relevant, concise, interactive clickable buttons for the customer to tap.\n\n"
                f"Customer Name: {customer_name}\n"
                f"Order Reference: {order_ref or 'Recent Order'}\n"
                f"Product: {product_name or 'Zenlora Curated Item'}\n"
                f"Amount: ₹{amount}\n\n"
                "Rules:\n"
                "1. Language must be 100% fluent, warm, professional English.\n"
                "2. Include clear WhatsApp formatting: *bold* for key terms, dividers '━━━━━━━━━━━━━━━━━━━━'.\n"
                "3. If address is incomplete, draft a 4-point structured address request:\n"
                "   1. House / Flat Number\n"
                "   2. Street / Road / Colony\n"
                "   3. Nearest Landmark\n"
                "   4. PIN code\n"
                "4. End with '🌟 _Team Zenlora_ | zenlora.store'.\n"
                "5. Generate 2 or 3 buttons (max 20 characters per button text).\n"
                "6. Return strictly valid JSON in this exact structure without markdown backticks:\n"
                '{"message": "...", "buttons": [{"id": "btn_1", "text": "Label 1"}, {"id": "btn_2", "text": "Label 2"}]}'
            )
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"{system_prompt}\n\nFounder raw prompt: {raw_prompt}"}]
                    }
                ],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
            }
            resp = requests.post(url, json=payload, timeout=8)
            if resp.ok:
                resp_json = resp.json()
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                clean_json_str = re.sub(r"^```json\s*", "", text_content.strip())
                clean_json_str = re.sub(r"\s*```$", "", clean_json_str)
                data = json.loads(clean_json_str)
                if "message" in data and "buttons" in data:
                    return {
                        "message": data["message"],
                        "buttons": data["buttons"],
                        "engine": "gemini_flash_ai"
                    }
        except Exception as e:
            logger.warning("Gemini AI API call failed or timed out: %s. Using institutional D2C rules engine.", e)

    return generate_d2c_fallback(
        raw_prompt,
        customer_name=customer_name,
        order_ref=order_ref,
        product_name=product_name,
        amount=amount,
    )
