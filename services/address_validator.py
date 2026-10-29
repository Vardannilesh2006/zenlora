"""
ZenOS RTO Killer 2.0 - Smart Indian Address Validator & Completeness Engine
Validates customer addresses against real-world Indian delivery criteria to prevent NDR and courier returns.
"""

import re
from typing import Dict, List, Any

# Indian 6-digit PIN code regex
PINCODE_REGEX = re.compile(r"\b[1-9][0-9]{5}\b")

# Indicators of House / Flat / Plot / Floor number
HOUSE_NUMBER_REGEX = re.compile(
    r"\b(flat|house|plot|room|quarter|h\.?no|qtr|floor|door|building|bldg|block|tower|wing|apt|apartment|c/o|w/o|s/o|d/o)\b|\b\d{1,5}[/-]?\w*\b",
    re.IGNORECASE,
)

# Indicators of Road / Gali / Area / Colony
STREET_AREA_REGEX = re.compile(
    r"\b(road|rd|street|gali|lane|chowk|nagar|colony|sector|vihar|enclave|market|bazaar|path|marg|mohalla|para|tola|cross|main|layout|phase)\b",
    re.IGNORECASE,
)

# Indicators of Landmark
LANDMARK_REGEX = re.compile(
    r"\b(near|opp|opposite|behind|beside|adj|adjacent|front of|in front|mandir|temple|masjid|mosque|church|gurudwara|school|college|hospital|station|bus stand|police station|metro|post office|bank|atm|park|circle|bridge|pul)\b",
    re.IGNORECASE,
)


def evaluate_address_health(address: str, pincode: str = "") -> Dict[str, Any]:
    """
    Evaluates the quality and completeness of an Indian delivery address.
    Returns:
        - status: 'COMPLETE' (Green), 'MISSING_LANDMARK' (Amber), 'MISSING_PINCODE' (Amber), 'MISSING_HOUSE' (Amber), 'INCOMPLETE' (Red)
        - score: 0 to 100
        - missing_parts: list of string descriptions for missing items
        - clean_address: trimmed string
        - pincode_valid: bool
        - has_house: bool (aliased as has_house_number)
        - has_landmark: bool
        - has_valid_pincode: bool
        - message: str
    """
    clean_addr = str(address or "").strip()
    clean_pin = "".join(ch for ch in str(pincode or "") if ch.isdigit())

    # Fallback: check if pincode was embedded in the address text
    if len(clean_pin) != 6:
        pin_match = PINCODE_REGEX.search(clean_addr)
        if pin_match:
            clean_pin = pin_match.group(0)

    score = 100
    missing = []

    # 1. Length check
    if len(clean_addr) < 18:
        score -= 40
        missing.append("Detailed Address (too brief)")
    elif len(clean_addr) < 30:
        score -= 15

    # 2. House / Flat / Building check
    has_house = bool(HOUSE_NUMBER_REGEX.search(clean_addr))
    if not has_house:
        score -= 25
        missing.append("House / Flat / Building No.")

    # 3. Street / Colony / Road check
    has_street = bool(STREET_AREA_REGEX.search(clean_addr))
    if not has_street and len(clean_addr) < 40:
        score -= 15
        missing.append("Street / Colony / Gali Name")

    # 4. Landmark check
    has_landmark = bool(LANDMARK_REGEX.search(clean_addr))
    if not has_landmark:
        score -= 15
        missing.append("Nearby Landmark (e.g. Near Temple / School)")

    # 5. Pincode check
    pincode_valid = bool(PINCODE_REGEX.fullmatch(clean_pin))
    if not pincode_valid:
        score -= 25
        missing.append("Valid 6-Digit PIN Code")

    # Clamp score
    score = max(10, min(100, score))

    if score >= 75 and len(missing) == 0:
        status = "COMPLETE"
        message = "🟢 Address Complete"
    elif score >= 55:
        if not pincode_valid and has_house and has_landmark:
            status = "MISSING_PINCODE"
            message = "⚠️ Valid 6-Digit PIN Code missing"
        elif not has_landmark and has_house:
            status = "MISSING_LANDMARK"
            message = "⚠️ Nearby Landmark missing"
        elif not has_house:
            status = "MISSING_HOUSE"
            message = "⚠️ House/Flat number missing"
        else:
            status = "INCOMPLETE"
            message = f"⚠️ Incomplete Address ({', '.join(missing) if missing else 'Insufficient details'})"
    else:
        status = "INCOMPLETE"
        message = f"⚠️ Incomplete Address ({', '.join(missing) if missing else 'Insufficient details'})"

    return {
        "status": status,
        "score": score,
        "missing_parts": missing,
        "clean_address": clean_addr,
        "pincode": clean_pin,
        "pincode_valid": pincode_valid,
        "has_house": has_house,
        "has_house_number": has_house,
        "has_landmark": has_landmark,
        "has_valid_pincode": pincode_valid,
        "message": message,
    }


def generate_address_fix_prompt(
    customer_name: str,
    order_ref: str,
    raw_address: str,
    missing_parts: List[str],
) -> str:
    """
    Generates a premium, polite, and effective D2C WhatsApp message asking the customer
    to complete their address so courier delivery does not fail.
    """
    name = (customer_name or "Valued Customer").strip()
    clean_addr = (raw_address or "Not provided").strip()
    missing_bullets = "\n".join(f"• {item}" for item in (missing_parts or ["House/Flat No.", "Nearby Landmark"]))

    message = (
        f"Namaste, {name}! 🙏✨\n\n"
        f"Thank you for your order *#{order_ref}* with *Zenlora*!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Delivery Address Verification*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Our logistics team is packing your parcel. However, your delivery address appears incomplete for priority courier routing:\n\n"
        f"📍 *Current Address:* \"{clean_addr}\"\n\n"
        f"To ensure the delivery partner reaches your doorstep without any delay, please reply with the following missing details:\n\n"
        f"{missing_bullets}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Simply reply directly to this WhatsApp message, and our system will update your order automatically! 🚚\n\n"
        f"🌟 _Team Zenlora_ | zenlora.store"
    )
    return message
