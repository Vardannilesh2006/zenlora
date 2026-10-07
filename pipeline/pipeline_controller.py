import json
import os
from config import DATABASE_FILE
from deodap_extractor import DeoDapExtractor
from classifier_pricing import ClassifierAndPricingEngine
from ugc_engine import UGCEngine
from excel_exporter import ExcelExporter

class ZenloraPipeline:
    """Master controller that ingests DeoDap URLs, processes AI pipelines, and manages exports."""

    @classmethod
    def load_db(cls) -> list:
        if not DATABASE_FILE.exists():
            return []
        try:
            with open(DATABASE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def save_db(cls, products: list):
        with open(DATABASE_FILE, "w", encoding="utf-8") as f:
            json.dump(products, f, indent=2, ensure_ascii=False)

    @classmethod
    def process_url(cls, url: str) -> dict:
        """Processes a single DeoDap URL through the entire pipeline."""
        # Step 1: Extract from DeoDap
        extracted = DeoDapExtractor.fetch_product(url)

        # Step 2: Classify and Price
        pricing_data = ClassifierAndPricingEngine.process(extracted)

        # Step 3: Generate Storyboard & Multi-Scene Prompts
        ugc_data = UGCEngine.generate_prompts(extracted, pricing_data)

        # Step 4: Merge into master record
        full_record = {
            **extracted,
            **pricing_data,
            **ugc_data
        }

        # Step 5: Save or update in DB
        db = cls.load_db()
        # Check if already exists (by handle or deodap_url)
        existing_idx = next((i for i, item in enumerate(db) if item.get("handle") == full_record.get("handle")), None)
        if existing_idx is not None:
            db[existing_idx] = full_record
        else:
            db.insert(0, full_record)  # Newest first

        cls.save_db(db)
        return full_record

    @classmethod
    def process_batch(cls, urls: list) -> list:
        """Processes a list of URLs and returns list of processed records."""
        results = []
        for u in urls:
            u = u.strip()
            if not u:
                continue
            try:
                rec = cls.process_url(u)
                results.append(rec)
            except Exception as e:
                results.append({"url": u, "error": str(e), "success": False})
        return results

    @classmethod
    def export_excel(cls, products: list = None) -> str:
        """Exports given products (or entire DB) to Excel."""
        if products is None:
            products = cls.load_db()
        if not products:
            raise ValueError("No products found to export. Please process at least one DeoDap product URL first.")
        return ExcelExporter.export(products)

    @classmethod
    def clear_db(cls):
        """Clears all stored products in the database."""
        cls.save_db([])

    @classmethod
    def delete_product(cls, handle: str) -> bool:
        """Deletes a product by its handle."""
        db = cls.load_db()
        filtered = [p for p in db if p.get("handle") != handle]
        if len(filtered) != len(db):
            cls.save_db(filtered)
            return True
        return False
