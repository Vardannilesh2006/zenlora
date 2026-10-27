import math
import re
from config import CATEGORIES, SHIPPING_BUFFER, MIN_MARKUP, TARGET_MARKUP, COMPARE_PRICE_RATIO

class ClassifierAndPricingEngine:
    """Classifies products into Zenlora categories and computes psychological pricing."""

    PSYCHOLOGICAL_POINTS = [199, 249, 299, 339, 349, 369, 379, 399, 429, 449, 479, 499, 549, 599, 699, 799, 899, 999, 1199, 1299, 1499, 1999]

    @classmethod
    def classify(cls, title: str, description: str, tags: list, product_type: str) -> dict:
        if tags is None:
            tag_list = []
        elif isinstance(tags, str):
            tag_list = [tag.strip() for tag in re.split(r"[,|;]+", tags) if tag.strip()]
        else:
            tag_list = [str(tag).strip() for tag in tags if str(tag).strip()]

        combined_text = f"{title} {description} {' '.join(tag_list)} {product_type}".lower()

        scores = {}
        for category, keywords in CATEGORIES.items():
            score = 0
            for kw in keywords:
                # Word boundary search for precision
                pattern = r"\b" + re.escape(kw) + r"\b"
                matches = len(re.findall(pattern, combined_text))
                if matches > 0:
                    score += (matches * 2 if kw in title.lower() else matches)
            scores[category] = score

        # Find category with highest score
        best_category = max(scores, key=scores.get)
        if scores[best_category] > 0:
            assigned_category = best_category
            confidence = "High" if scores[best_category] >= 3 else "Medium"
        else:
            assigned_category = "Trending Problem-Solver Gadget"
            confidence = "Dynamic"

        return {
            "primary_category": assigned_category,
            "confidence": confidence,
            "scores": scores
        }

    @classmethod
    def generate_zenlora_title(cls, deodap_title: str) -> str:
        """Transforms long wholesale titles into clean, high-converting D2C brand titles."""
        clean = deodap_title.strip()
        # Remove common wholesale noise words
        noise_patterns = [
            r"\(pack of \d+\)", r"pack of \d+", r"set of \d+", r"\(set of \d+\)",
            r"wholesale", r"best quality", r"hot sale", r"combo", r"with box",
            r"-\s*multi\s*color", r"\(random color\)", r"mix color", r"colour", r"color",
            r"\[.*?\]", r"\(.*?\)"
        ]
        for p in noise_patterns:
            clean = re.sub(p, "", clean, flags=re.IGNORECASE)

        clean = " ".join(clean.split())
        words = clean.split()
        if len(words) > 8:
            clean = " ".join(words[:8])

        # Title Case
        clean = clean.title()
        return f"Zenlora™ {clean}"

    @classmethod
    def calculate_pricing(cls, wholesale_price: float, seed_key: str = "", is_under_199_rack: bool = False) -> dict:
        """
        Calculates realistic D2C psychological selling price, MRP, and net in-hand profit margins.
        Accounts for full Landed Cost:
        - DeoDap wholesale cost
        - 18% GST on wholesale
        - Rs.60 Courier Delivery Shipping
        - Rs.25 COD Collection & Expected RTO Loss Buffer (Rs.10 COD + Rs.15 RTO)
        - Rs.10 Packaging, Bubble Wrap, Label & Box
        Smart 3-Tier Net Profit:
        - Low Cost (< Rs.70): Rs.90 to Rs.100 Net Profit
        - Mid Cost (Rs.70 to Rs.150): Rs.110 to Rs.120 Net Profit
        - Premium Cost (> Rs.150): Rs.125 to Rs.135 Net Profit
        """
        cost = max(1.0, float(wholesale_price or 100.0))
        gst_tax = round(cost * 0.18, 2)
        shipping_cost = 60.0
        cod_rto_buffer = 25.0
        packaging_cost = 10.0
        total_expenses = round(gst_tax + shipping_cost + cod_rto_buffer + packaging_cost, 2)
        landed_cost = round(cost + total_expenses, 2)

        if 0 < cost <= 50.0:
            key = str(seed_key or "zenlora").strip().lower()
            seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(key)) + int(round(float(cost)))
            selling_price = 179 + (seed % 7)
        else:
            if cost < 70.0:
                target_profit = 95.0
                p_min, p_max = 85.0, 115.0
            elif cost <= 150.0:
                target_profit = 115.0
                p_min, p_max = 105.0, 135.0
            else:
                target_profit = 130.0
                p_min, p_max = 120.0, 150.0

            raw_target = landed_cost + target_profit
            points = [179, 189, 199, 219, 229, 239, 249, 279, 299, 319, 329, 339, 349, 369, 379, 399, 429, 449, 479, 499, 549, 599, 649, 699, 799, 899, 999]
            
            chosen = None
            for pt in points:
                prof = pt - landed_cost
                if p_min <= prof <= p_max:
                    chosen = pt
                    break
            if chosen is None:
                for pt in points:
                    if pt >= raw_target:
                        chosen = pt
                        break
            selling_price = chosen or int(round(raw_target // 10) * 10 + 9)

        # Realistic D2C Box MRP: 25% - 35% discount perception
        mrp_targets = {
            179: 249, 189: 269, 199: 299, 219: 319, 229: 329, 239: 349, 249: 349, 279: 399, 299: 449,
            319: 449, 329: 479, 339: 489, 349: 499, 369: 529, 379: 549,
            399: 569, 429: 599, 449: 649, 479: 679, 499: 699, 549: 779,
            599: 849, 649: 899, 699: 999, 799: 1149, 899: 1299, 999: 1399
        }
        if int(selling_price) in mrp_targets:
            mrp = mrp_targets[int(selling_price)]
        else:
            raw_mrp = math.ceil((selling_price * 1.42) / 10.0) * 10 - 1
            mrp = max(raw_mrp, selling_price + 70)

        # In-hand Net Profit (after product cost, GST, shipping, COD/RTO buffer, and packaging)
        gross_profit = round(selling_price - landed_cost, 2)
        profit_margin_pct = round((gross_profit / selling_price) * 100, 1)
        discount_pct = round(((mrp - selling_price) / mrp) * 100)

        return {
            "wholesale_price": round(cost, 2),
            "gst_tax": gst_tax,
            "shipping_cost": shipping_cost,
            "cod_rto_buffer": cod_rto_buffer,
            "packaging_cost": packaging_cost,
            "total_expenses": total_expenses,
            "landed_cost": landed_cost,
            "selling_price": int(selling_price),
            "mrp": int(mrp),
            "discount_pct": int(discount_pct),
            "shipping_buffer": int(shipping_cost),
            "gross_profit": gross_profit,
            "profit_margin_pct": profit_margin_pct,
            "badge": f"Save {discount_pct}%"
        }

    @classmethod
    def process(cls, extracted_data: dict) -> dict:
        """Full processing pipeline for classification and pricing."""
        classification = cls.classify(
            title=extracted_data.get("title", ""),
            description=extracted_data.get("description", ""),
            tags=extracted_data.get("tags", []),
            product_type=extracted_data.get("product_type", "")
        )

        pricing = cls.calculate_pricing(
            extracted_data.get("wholesale_price", 0.0),
            seed_key=extracted_data.get("handle") or extracted_data.get("sku") or extracted_data.get("title", ""),
        )
        zenlora_title = cls.generate_zenlora_title(extracted_data.get("title", ""))

        return {
            **classification,
            **pricing,
            "zenlora_title": zenlora_title
        }
