"""
RTO Killer Engine — Zenlora D2C Anti-RTO Shield & Institutional Pricing Engine
Flipkart & Amazon India Standard Architecture:
- 15% Instant Discount for UPI & Net Banking (eliminates high-risk COD orders).
- Clean institutional copy (Bank Offer, Partner Offer, Cash on Delivery terms).
- Professional, non-gimmicky WhatsApp confirmation flow.
"""
from typing import Dict, Any, List

class RTOKillerEngine:
    """Generates anti-RTO pricing arbitrage and Flipkart/Amazon standard offer copy."""

    UPI_DISCOUNT_PERCENT = 15  # 15% instant discount for prepaid UPI / Online Payment
    COD_HANDLING_FEE = 49      # Standard industry COD handling fee

    @classmethod
    def generate_rto_killer_data(cls, product_title: str, cod_selling_price: int) -> Dict[str, Any]:
        cod_price = int(cod_selling_price)
        savings = max(20, int(round(cod_price * (cls.UPI_DISCOUNT_PERCENT / 100.0))))
        upi_price = max(149, cod_price - savings)
        cod_total = cod_price + cls.COD_HANDLING_FEE

        # 1. Flipkart / Amazon Standard Micro-Copy
        checkout_badge = f"Bank Offer: Flat 15% Instant Off (Save ₹{savings})"
        checkout_copy = (
            f"Bank Offer: 15% Instant Discount on UPI & Net Banking (Pay ₹{upi_price} instead of ₹{cod_price}) "
            f"| Priority 24h Express Dispatch"
        )

        # 2. Institutional Structured Offers (for PDP Available Offers Container)
        available_offers: List[Dict[str, str]] = [
            {
                "type": "bank",
                "label": "Bank Offer",
                "title": f"Flat 15% Instant Discount on UPI and Net Banking payments (Pay ₹{upi_price} only).",
                "tc_text": "T&C"
            },
            {
                "type": "partner",
                "label": "Partner Offer",
                "title": "Free Express Shipping + Priority 24h Dispatch on prepaid orders.",
                "tc_text": "T&C"
            },
            {
                "type": "cod",
                "label": "Cash on Delivery",
                "title": f"Available across India (₹{cls.COD_HANDLING_FEE} cash handling fee applies; Total ₹{cod_total}).",
                "tc_text": ""
            }
        ]

        # 3. Dual-Action WhatsApp Confirmation Flow (Clean, professional, high-trust)
        clean_title = product_title.replace("Zenlora™", "").strip()
        whatsapp_message = (
            f"Namaste [Customer Name]! 🙏\n\n"
            f"Thank you for shopping with Zenlora. We have received your order:\n"
            f"📦 Item: *{clean_title}*\n"
            f"💵 COD Amount: *₹{cod_total}* (includes ₹{cls.COD_HANDLING_FEE} COD fee)\n\n"
            f"🏷️ *Instant Bank Offer Available:*\n"
            f"Switch to UPI payment to save 15% instantly:\n"
            f"• Net Amount to Pay: *₹{upi_price}* (Total Savings: ₹{savings + cls.COD_HANDLING_FEE})\n"
            f"• Priority 24-Hour Express Air Dispatch with tracking\n\n"
            f"Please choose your preferred payment option below:"
        )

        button_1_upi = f"💳 Pay ₹{upi_price} via UPI (Save ₹{savings + cls.COD_HANDLING_FEE})"
        button_2_cod = f"📦 Confirm Cash on Delivery (₹{cod_total})"

        # 4. Backend Operational Protocol
        backend_rule = (
            "RTO Shield Protocol: Orders with COD payment remain in 'Pending Verification' "
            "until confirmed via WhatsApp or converted to prepaid UPI. Eliminates unverified deliveries."
        )

        return {
            "cod_price": cod_price,
            "upi_price": upi_price,
            "savings": savings,
            "discount_pct": cls.UPI_DISCOUNT_PERCENT,
            "cod_handling_fee": cls.COD_HANDLING_FEE,
            "cod_total": cod_total,
            "available_offers": available_offers,
            "checkout_copy": checkout_copy,
            "checkout_badge": checkout_badge,
            "whatsapp_message": whatsapp_message,
            "button_1_upi": button_1_upi,
            "button_2_cod": button_2_cod,
            "backend_rule": backend_rule
        }
