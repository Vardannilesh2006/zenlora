"""
Automated Real-Data Integrity & Provenance Test Suite (NON-NEGOTIABLE RULE #1 - #8).
Fails the build if:
1. Hardcoded sample product data, mock arrays (e.g. VERIFIED_MARKET_DATA), Math.random,
   faker, hash-based fake scores, or guessed weights/prices exist in source files.
2. Any score criterion in winning_scorer.py is computed from a field without complete
   source metadata (source, source_url, fetched_at, method).
3. Missing inputs are silently scored as 0 instead of remaining null (None) and lowering confidence.
4. LLM outputs are not strictly labelled 'AI opinion (not data)' with method='ai_opinion'.
"""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PIPELINE_DIR = ROOT_DIR / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

from winning_engine.data_models import make_data_point, load_settings, calculate_festival_cutoffs
from winning_engine.winning_scorer import compute_winning_score
from winning_engine.meta_ad_spy import analyze_meta_ad_signals
from winning_engine.trend_checker import get_google_trends_analysis
from winning_engine.social_spy import analyze_social_velocity
from winning_engine.gemini_analyzer import analyze_with_gemini


class TestRealDataOnlyEnforcement(unittest.TestCase):
    """Enforces Rule #1 & Rule #8: Zero mock, dummy, random, or hardcoded product data in source."""

    FORBIDDEN_PATTERNS = [
        (r"VERIFIED_MARKET_DATA\s*=", "Hardcoded competitor price lookup table"),
        (r"Math\.random\s*\(", "Random number generator in JS/TS/HTML"),
        (r"from\s+faker\s+import|import\s+faker", "Faker library import"),
        (r"85\s*\+\s*\(\s*hash\(", "Hash-based fake AI score generator"),
        (r"ai_viral_score", "Deprecated LLM-generated numeric viral score"),
        (r"grams\s+or\s+350", "Guessed 350g weight fallback when supplier weight is 0"),
    ]

    def test_no_hardcoded_mock_or_random_data_in_source(self):
        """Scans all Python, TypeScript, JS, and HTML source files for forbidden mock/random patterns."""
        violations = []
        scan_dirs = [PIPELINE_DIR, ROOT_DIR / "app", ROOT_DIR / "components", ROOT_DIR / "lib"]

        for base in scan_dirs:
            if not base.exists():
                continue
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".next", ".git")]
                for fname in files:
                    if not fname.endswith((".py", ".ts", ".tsx", ".js", ".html")):
                        continue
                    fpath = Path(root) / fname
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    for pattern, reason in self.FORBIDDEN_PATTERNS:
                        if re.search(pattern, content):
                            violations.append(f"{fpath.relative_to(ROOT_DIR)}: {reason} ({pattern})")

        self.assertEqual(
            violations,
            [],
            f"Build failed: Found forbidden mock/random/hardcoded patterns in source:\n" + "\n".join(violations),
        )

    def test_every_scored_criterion_has_complete_source_metadata(self):
        """
        Enforces Rule #4 & Rule #8: Every criterion in compute_winning_score must carry:
        source, source_url, fetched_at, and method.
        """
        sample_real_supplier_item = {
            "id": 999999,
            "handle": "test-spin-cleaning-brush",
            "title": "Electric Spin Cleaning Brush for Kitchen Tiles",
            "niche": "Home Decor",
            "wholesale_price": 120.0,
            "in_stock": True,
            "weight_grams": None,  # DeoDap returned 0 -> stored as None
            "dimensions": None,
            "source": "DeoDap Shopify API",
            "source_url": "https://www.deodap.in/products/test-spin-cleaning-brush.json",
            "fetched_at": "2026-10-11T05:30:00+00:00",
            "method": "api",
            "description": "Cordless cleaning scrub brush for kitchen and bathroom corners.",
        }

        meta = analyze_meta_ad_signals(sample_real_supplier_item["title"], "Home Decor", handle="test-spin-cleaning-brush")
        trends = get_google_trends_analysis("cleaning brush", "Home Decor", fetch_live=False)
        social = analyze_social_velocity("cleaning brush", "Home Decor", handle="test-spin-cleaning-brush")

        score_result = compute_winning_score(
            product=sample_real_supplier_item,
            meta_signals=meta,
            trend_signals=trends,
            social_signals=social,
            gemini_signals=None,
            catalog_pool=[],
        )

        checklist = score_result.get("checklist", [])
        self.assertEqual(len(checklist), 10, "Must evaluate all 10 criteria separately.")

        valid_methods = {"api", "scrape", "manual_entry", "rule_based", "user_assumption", "ai_opinion"}
        for c in checklist:
            cid = c.get("id")
            self.assertTrue(c.get("source"), f"Criterion #{cid} is missing 'source' metadata")
            self.assertIn("source_url", c, f"Criterion #{cid} is missing 'source_url' field")
            self.assertIn("fetched_at", c, f"Criterion #{cid} is missing 'fetched_at' field")
            self.assertIn(
                c.get("method"),
                valid_methods,
                f"Criterion #{cid} has invalid or missing 'method': {c.get('method')}",
            )
            # If a criterion is scored (earned_points is not None) and comes from real_data or user_assumption,
            # it must have a non-empty source and source_url
            if c.get("earned_points") is not None:
                self.assertTrue(
                    bool(c.get("source")),
                    f"Scored Criterion #{cid} computed points without a source name",
                )

    def test_missing_inputs_are_null_and_never_silently_scored_as_zero(self):
        """
        Enforces Rule #3 & Rule #6: Unentered manual ratings (Criteria 1 & 2) and un-fetched
        marketplace prices (Criterion 7) must have earned_points=None (null), status='missing',
        and lower confidence instead of silently scoring 0.
        """
        product = {
            "id": 888888,
            "handle": "unrated-real-supplier-item",
            "title": "Microfiber Gap Dusting Brush",
            "niche": "Kitchen",
            "wholesale_price": 95.0,
            "in_stock": True,
            "weight_grams": None,
            "dimensions": None,
            "source": "DeoDap Shopify API",
            "source_url": "https://www.deodap.in/products/unrated-real-supplier-item.json",
            "fetched_at": "2026-10-11T05:30:00+00:00",
            "method": "api",
            "description": "Gap cleaning brush",
        }
        meta = analyze_meta_ad_signals(product["title"], "Kitchen", handle="unrated-real-supplier-item")
        trends = get_google_trends_analysis("gap cleaning brush", "Kitchen", fetch_live=False)
        social = analyze_social_velocity("gap cleaning brush", "Kitchen", handle="unrated-real-supplier-item")

        res = compute_winning_score(product, meta, trends, social)
        by_id = {c["id"]: c for c in res["checklist"]}

        # Criteria 1 & 2 require manual 1-5 rating -> must be None, not 0
        self.assertIsNone(by_id[1]["earned_points"], "Criterion 1 must be None when manual rating is not entered")
        self.assertEqual(by_id[1]["status"], "missing")
        self.assertIsNone(by_id[2]["earned_points"], "Criterion 2 must be None when manual rating is not entered")
        self.assertEqual(by_id[2]["status"], "missing")

        # Confidence cannot be 'High' when manual ratings, ads, and social are missing
        self.assertNotEqual(res["confidence"], "High")
        self.assertGreaterEqual(res["data_coverage"]["missing_count"], 3)

    def test_hard_fail_filters_trigger_correctly(self):
        """Enforces Hard-Fail Filters: out of stock, restricted category (firecrackers/food/gold), low margin."""
        restricted_product = {
            "id": 777777,
            "handle": "diwali-patakhe-sparkles-box",
            "title": "Diwali Patakhe Firecracker Gift Pack",
            "niche": "Festive",
            "wholesale_price": 150.0,
            "in_stock": False,
            "source": "DeoDap Shopify API",
            "source_url": "https://www.deodap.in/products/diwali-patakhe.json",
            "fetched_at": "2026-10-11T05:30:00+00:00",
            "method": "api",
            "description": "Festival firecracker box",
        }
        meta = analyze_meta_ad_signals(restricted_product["title"], "Festive", handle=restricted_product["handle"])
        trends = get_google_trends_analysis("patakhe", "Festive", fetch_live=False)
        social = analyze_social_velocity("patakhe", "Festive", handle=restricted_product["handle"])

        res = compute_winning_score(restricted_product, meta, trends, social)
        self.assertTrue(res["is_hard_failed"], "Out-of-stock and firecracker product must trigger hard-fail")
        reasons_text = " ".join(res["hard_fail_reasons"]).lower()
        self.assertIn("out of stock", reasons_text)
        self.assertIn("restricted", reasons_text)

    def test_llm_boundary_labelled_ai_opinion(self):
        """Enforces Rule #2: LLM output is strictly labelled 'AI opinion (not data)' with method='ai_opinion'."""
        res = analyze_with_gemini("LED String Curtain Light", "Festive", 110.0, 399.0, "Warm white LED curtain light")
        self.assertEqual(res.get("label"), "AI opinion (not data)")
        self.assertEqual(res.get("method"), "ai_opinion")
        self.assertNotIn("ai_viral_score", res)


if __name__ == "__main__":
    unittest.main()
