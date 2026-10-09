import re
import html
import requests
from urllib.parse import urlparse

class DeoDapExtractor:
    """Extracts rich product details directly from DeoDap's Shopify store API."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    @staticmethod
    def clean_handle(url_or_handle: str) -> str:
        """Extracts the product handle from a full URL or raw string."""
        url_or_handle = url_or_handle.strip()
        if not url_or_handle:
            return ""

        # Remove query parameters and hashes
        clean_url = url_or_handle.split("?")[0].split("#")[0].rstrip("/")

        # If it's a full URL
        if "/products/" in clean_url:
            parts = clean_url.split("/products/")
            return parts[-1].strip().replace(" ", "-").lower()

        # If already a handle
        return clean_url.replace(" ", "-").lower()

    @classmethod
    def fetch_product(cls, url_or_handle: str) -> dict:
        """Fetches complete product information for a given DeoDap URL or handle."""
        handle = cls.clean_handle(url_or_handle)
        if not handle:
            raise ValueError(f"Invalid DeoDap product URL or handle: {url_or_handle}")

        # Try JSON endpoint first (Shopify native API - ultra fast and reliable)
        api_endpoints = [
            f"https://deodap.in/products/{handle}.json",
            f"https://deodap.com/products/{handle}.json",
        ]

        product_data = None
        for endpoint in api_endpoints:
            try:
                resp = requests.get(endpoint, headers=cls.HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if "product" in data:
                        product_data = data["product"]
                        break
            except Exception:
                continue

        # If JSON succeeded, parse into normalized structure
        if product_data:
            return cls._parse_shopify_json(product_data, handle)

        # Fallback: scrape directly via HTML
        return cls._scrape_html_fallback(handle)

    @classmethod
    def _parse_shopify_json(cls, p: dict, handle: str) -> dict:
        variants = p.get("variants", [])
        images = [img.get("src") for img in p.get("images", []) if img.get("src")]
        primary_image = images[0] if images else ""

        # Extract wholesale price
        first_variant = variants[0] if variants else {}
        try:
            wholesale_price = float(first_variant.get("price", 0.0))
        except (ValueError, TypeError):
            wholesale_price = 0.0

        try:
            compare_price = float(first_variant.get("compare_at_price") or 0.0)
        except (ValueError, TypeError):
            compare_price = 0.0

        # Clean HTML description into readable plain text
        raw_html = p.get("body_html", "") or ""
        clean_desc = re.sub(r"<[^>]+>", " ", raw_html)
        clean_desc = html.unescape(clean_desc)
        clean_desc = " ".join(clean_desc.split())

        return {
            "success": True,
            "id": p.get("id"),
            "handle": handle,
            "deodap_url": f"https://deodap.in/products/{handle}",
            "title": p.get("title", "").strip(),
            "vendor": p.get("vendor", "DeoDap"),
            "product_type": p.get("product_type", ""),
            "tags": p.get("tags", []),
            "wholesale_price": wholesale_price,
            "compare_at_price": compare_price if compare_price > 0 else (wholesale_price * 1.8),
            "sku": first_variant.get("sku", ""),
            "weight_grams": first_variant.get("grams", 0),
            "primary_image": primary_image,
            "images": images,
            "raw_html": raw_html,
            "description": clean_desc,
        }

    @classmethod
    def _scrape_html_fallback(cls, handle: str) -> dict:
        url = f"https://deodap.in/products/{handle}"
        resp = requests.get(url, headers=cls.HEADERS, timeout=12)
        if resp.status_code != 200:
            raise ConnectionError(f"Failed to fetch DeoDap product page (Status: {resp.status_code})")

        content = resp.text
        # Title regex
        title_match = re.search(r"<h1[^>]*class=[\"'][^\"']*product__title[^\"']*[\"'][^>]*>(.*?)</h1>", content, re.DOTALL)
        if not title_match:
            title_match = re.search(r"<meta\s+property=[\"']og:title[\"']\s+content=[\"'](.*?)[\"']", content)
        title = html.unescape(title_match.group(1).strip()) if title_match else handle.replace("-", " ").title()

        # Image regex
        img_match = re.search(r"<meta\s+property=[\"']og:image[\"']\s+content=[\"'](.*?)[\"']", content)
        primary_image = img_match.group(1).strip() if img_match else ""

        # Price regex
        price_match = re.search(r"<meta\s+property=[\"']product:price:amount[\"']\s+content=[\"'](.*?)[\"']", content)
        if price_match:
            price = float(price_match.group(1))
        else:
            price = 99.0

        return {
            "success": True,
            "handle": handle,
            "deodap_url": url,
            "title": title,
            "vendor": "DeoDap",
            "product_type": "General",
            "tags": [],
            "wholesale_price": price,
            "compare_at_price": price * 1.8,
            "sku": "",
            "weight_grams": 0,
            "primary_image": primary_image,
            "images": [primary_image] if primary_image else [],
            "raw_html": "",
            "description": title,
        }
