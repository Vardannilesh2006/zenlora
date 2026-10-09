"""
RTO Killer Engine — Zenlora D2C Anti-RTO Shield
Transforms standard high-risk COD orders into verified, zero-risk deliveries
using UPI price arbitrage and mandatory 2-button WhatsApp confirmation.
"""
from typing import Dict, Any

class RTOKillerEngine:
    """Generates anti-RTO pricing arbitrage and WhatsApp interactive confirmation copy."""

    UPI_INSTANT_DISCOUNT = 50  # Instant discount for prepaid UPI / GPay
    FREE_GIFT_VALUE = 199      # Perceived value of mystery free gift

    @classmethod
    def generate_rto_killer_data(cls, product_title: str, cod_selling_price: int) -> Dict[str, Any]:
        cod_price = int(cod_selling_price)
        upi_price = max(199, cod_price - cls.UPI_INSTANT_DISCOUNT)
        savings = cod_price - upi_price

        # 1. Checkout Banner Copy (for Shopify / Website Checkout)
        checkout_badge = f"Save ₹{savings} with UPI"
        checkout_copy = (
            f"⚡ Pay via UPI / GPay: ₹{upi_price} (Save ₹{savings} Instantly + Free Mystery Gift worth ₹{cls.FREE_GIFT_VALUE}) "
            f"| COD: ₹{cod_price}"
        )

        # 2. Dual-Action WhatsApp Confirmation Flow (Sent within 60 seconds of COD order)
        clean_title = product_title.replace("Zenlora™", "").strip()
        whatsapp_message = (
            f"Namaste [Customer Name]! 👋\n\n"
            f"Aapka Zenlora order receive ho gaya hai:\n"
            f"📦 Product: *{clean_title}*\n"
            f"💵 Total: *₹{cod_price} (Cash on Delivery)*\n\n"
            f"🔥 *SPECIAL VIP PREPAID UPGRADE (Next 15 Mins Only):*\n"
            f"Agar aap abhi UPI/GPay se pay karte hain:\n"
            f"✅ *Instant ₹{savings} Discount* (Pay only ₹{upi_price})\n"
            f"✅ *FREE Mystery Gift* (worth ₹{cls.FREE_GIFT_VALUE})\n"
            f"✅ *Express Priority Shipping* (Delivered 2 days faster)\n\n"
            f"Kripya niche diye gaye 2 options me se ek select karein:"
        )

        button_1_upi = f"💳 Pay ₹{upi_price} via UPI (Claim Free Gift)"
        button_2_cod = "📦 No, I Continue with Cash on Delivery"

        # 3. Backend Operational Guardrail
        backend_rule = (
            "⚠️ RTO Killer Protocol: Jab tak customer WhatsApp par 'Continue with Cash on Delivery' "
            "click karke confirm na kare ya UPI se pay na kare, tab tak order 'PENDING VERIFICATION' "
            "rahega. Fake ya timepass orders dispatch se pehle hi filter ho jayenge."
        )

        return {
            "cod_price": cod_price,
            "upi_price": upi_price,
            "savings": savings,
            "checkout_copy": checkout_copy,
            "checkout_badge": checkout_badge,
            "whatsapp_message": whatsapp_message,
            "button_1_upi": button_1_upi,
            "button_2_cod": button_2_cod,
            "backend_rule": backend_rule
        }
