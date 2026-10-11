import re
import html
import socket
import requests
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# Ensure dual-stack IPv6 (2620:127:f00f:e::) + IPv4 resolution for deodap.in on Indian mobile/ISP networks
_orig_getaddrinfo = socket.getaddrinfo
def _deodap_dual_stack_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in ("deodap.in", "www.deodap.in"):
        try:
            base = _orig_getaddrinfo(host, port, family, type, proto, flags)
        except Exception:
            base = []
        ipv6_entry = (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2620:127:f00f:e::", port, 0, 0))
        if ipv6_entry not in base:
            return [ipv6_entry] + base
        return base
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _deodap_dual_stack_getaddrinfo


class DeoDapExtractor:
    """Extracts real product details directly from DeoDap's Shopify store API with full provenance metadata."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    }

    @staticmethod
    def clean_handle(url_or_handle: str) -> str:
        """Extracts the product handle from a full URL or raw string."""
        url_or_handle = (url_or_handle or "").strip()
        if not url_or_handle:
            return ""
        clean_url = url_or_handle.split("?")[0].split("#")[0].rstrip("/")
        if "/products/" in clean_url:
            parts = clean_url.split("/products/")
            return parts[-1].strip().replace(" ", "-").lower()
        return clean_url.replace(" ", "-").lower()

    @staticmethod
    def extract_dimensions_from_text(text: str):
        """Extracts real dimensions string from supplier description if present; otherwise returns None."""
        if not text:
            return None
        patterns = [
            r"(?:dimension|size|measurement)s?\s*[:\-]?\s*(\d+(?:\.\d+)?\s*[xX×*]\s*\d+(?:\.\d+)?(?:\s*[xX×*]\s*\d+(?:\.\d+)?)?\s*(?:cm|mm|inch|inches|in|m)\b)",
            r"\b(\d+(?:\.\d+)?\s*[xX×]\s*\d+(?:\.\d+)?(?:\s*[xX×]\s*\d+(?:\.\d+)?)?\s*(?:cm|mm|inch|inches)\b)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def extract_delivery_days_from_text(text: str):
        """Extracts real min/max delivery days if explicitly stated on the product page; otherwise (None, None)."""
        if not text:
            return None, None
        m = re.search(r"(?:delivery|deliver|dispatch|shipping).*?(\d+)\s*(?:to|\-)\s*(\d+)\s*(?:business|working)?\s*days", text, re.IGNORECASE)
        if m:
            d1, d2 = int(m.group(1)), int(m.group(2))
            if 1 <= d1 <= d2 <= 30:
                return d1, d2
        return None, None

    @classmethod
    def fetch_product(cls, url_or_handle: str) -> dict:
        """Fetches complete real product information for a given DeoDap URL or handle."""
        handle = cls.clean_handle(url_or_handle)
        if not handle:
            raise ValueError(f"Invalid DeoDap product URL or handle: {url_or_handle}")

        api_endpoints = [
            f"https://www.deodap.in/products/{handle}.json",
            f"https://deodap.in/products/{handle}.json",
        ]

        for endpoint in api_endpoints:
            try:
                resp = requests.get(endpoint, headers=cls.HEADERS, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    if "product" in data:
                        return cls._parse_shopify_json(data["product"], handle, endpoint)
            except Exception:
                continue

        return cls._scrape_html_fallback(handle)

    @classmethod
    def _parse_shopify_json(cls, p: dict, handle: str, source_endpoint: str) -> dict:
        fetched_at = datetime.now(IST).isoformat(timespec="seconds")
        variants = p.get("variants", [])
        images = [img.get("src") for img in p.get("images", []) if img.get("src")]
        primary_image = images[0] if images else None

        first_variant = variants[0] if variants else {}
        raw_price = first_variant.get("price")
        try:
            wholesale_price = float(raw_price) if raw_price is not None and float(raw_price) > 0 else None
        except (ValueError, TypeError):
            wholesale_price = None

        raw_compare = first_variant.get("compare_at_price")
        try:
            compare_price = float(raw_compare) if raw_compare is not None and float(raw_compare) > 0 else None
        except (ValueError, TypeError):
            compare_price = None

        # Real stock status from supplier variant
        in_stock = first_variant.get("available")
        if in_stock is None and variants:
            in_stock = any(bool(v.get("available")) for v in variants)

        # Real weight from supplier variant (Null if 0 or missing — never guess)
        raw_grams = first_variant.get("grams")
        try:
            weight_grams = int(raw_grams) if raw_grams is not None and int(raw_grams) > 0 else None
        except (ValueError, TypeError):
            weight_grams = None

        raw_html = p.get("body_html", "") or ""
        clean_desc = re.sub(r"<[^>]+>", " ", raw_html)
        clean_desc = html.unescape(clean_desc)
        clean_desc = " ".join(clean_desc.split())

        dimensions = cls.extract_dimensions_from_text(clean_desc)
        deliv_min, deliv_max = cls.extract_delivery_days_from_text(clean_desc)

        return {
            "success": True,
            "id": p.get("id"),
            "handle": handle,
            "deodap_url": f"https://www.deodap.in/products/{handle}",
            "source": "DeoDap Shopify API",
            "source_url": source_endpoint,
            "fetched_at": fetched_at,
            "method": "api",
            "title": p.get("title", "").strip(),
            "vendor": p.get("vendor", "DeoDap"),
            "product_type": p.get("product_type", ""),
            "tags": p.get("tags", []),
            "wholesale_price": wholesale_price,
            "compare_at_price": compare_price,
            "in_stock": in_stock,
            "sku": first_variant.get("sku") or None,
            "weight_grams": weight_grams,
            "dimensions": dimensions,
            "delivery_min_days": deliv_min,
            "delivery_max_days": deliv_max,
            "primary_image": primary_image,
            "images": images,
            "raw_html": raw_html,
            "description": clean_desc,
        }

    @classmethod
    def _scrape_html_fallback(cls, handle: str) -> dict:
        url = f"https://www.deodap.in/products/{handle}"
        fetched_at = datetime.now(IST).isoformat(timespec="seconds")
        resp = requests.get(url, headers=cls.HEADERS, timeout=10)
        if resp.status_code != 200:
            raise ConnectionError(f"Failed to fetch DeoDap product page (Status: {resp.status_code})")

        content = resp.text
        title_match = re.search(r"<h1[^>]*class=[\"'][^\"']*product__title[^\"']*[\"'][^>]*>(.*?)</h1>", content, re.DOTALL)
        if not title_match:
            title_match = re.search(r"<meta\s+property=[\"']og:title[\"']\s+content=[\"'](.*?)[\"']", content)
        title = html.unescape(title_match.group(1).strip()) if title_match else None

        img_match = re.search(r"<meta\s+property=[\"']og:image[\"']\s+content=[\"'](.*?)[\"']", content)
        primary_image = img_match.group(1).strip() if img_match else None

        price_match = re.search(r"<meta\s+property=[\"']product:price:amount[\"']\s+content=[\"'](.*?)[\"']", content)
        try:
            price = float(price_match.group(1)) if price_match else None
        except (ValueError, TypeError):
            price = None

        deliv_min, deliv_max = cls.extract_delivery_days_from_text(content)

        return {
            "success": True,
            "handle": handle,
            "deodap_url": url,
            "source": "DeoDap Public HTML Page",
            "source_url": url,
            "fetched_at": fetched_at,
            "method": "scrape",
            "title": title,
            "vendor": "DeoDap",
            "product_type": None,
            "tags": [],
            "wholesale_price": price,
            "compare_at_price": None,
            "in_stock": None,
            "sku": None,
            "weight_grams": None,
            "dimensions": cls.extract_dimensions_from_text(content),
            "delivery_min_days": deliv_min,
            "delivery_max_days": deliv_max,
            "primary_image": primary_image,
            "images": [primary_image] if primary_image else [],
            "raw_html": "",
            "description": title or "",
        }
