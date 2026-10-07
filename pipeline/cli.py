import sys
import argparse
from pathlib import Path

# Add current folder to path
sys.path.append(str(Path(__file__).resolve().parent))

from pipeline_controller import ZenloraPipeline

def main():
    parser = argparse.ArgumentParser(description="Zenlora AI DeoDap Sourcing & UGC Prompt CLI")
    parser.add_argument("url", nargs="?", help="DeoDap product URL to process")
    parser.add_argument("--file", "-f", help="Text file containing list of DeoDap URLs (one per line)")
    parser.add_argument("--export", "-e", action="store_true", help="Export entire pipeline database to Excel (.xlsx)")
    parser.add_argument("--list", "-l", action="store_true", help="List all processed products currently in database")
    parser.add_argument("--clear", action="store_true", help="Clear all products from database")

    args = parser.parse_args()

    if args.clear:
        ZenloraPipeline.clear_db()
        print("✓ Zenlora pipeline database cleared successfully.")
        return

    if args.list:
        db = ZenloraPipeline.load_db()
        print(f"\n📦 Zenlora Pipeline Database ({len(db)} products):")
        print("-" * 75)
        for i, p in enumerate(db, 1):
            print(f"{i}. {p.get('zenlora_title')} | Cat: {p.get('primary_category')} | Price: ₹{p.get('selling_price')} (Cost: ₹{p.get('wholesale_price')}) | Margin: +₹{p.get('gross_profit')}")
        print("-" * 75 + "\n")
        return

    if args.export:
        try:
            excel_path = ZenloraPipeline.export_excel()
            print(f"\n✨ Formatted Excel exported successfully to:\n👉 {excel_path}\n")
        except Exception as e:
            print(f"Export Error: {e}")
        return

    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"Error: File '{args.file}' not found.")
            return
        with open(filepath, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
        print(f"Processing {len(urls)} URLs from '{args.file}'...")
        results = ZenloraPipeline.process_batch(urls)
        print(f"✓ Processed {len(results)} products.")
        excel_path = ZenloraPipeline.export_excel()
        print(f"✓ Excel exported to: {excel_path}")
        return

    if args.url:
        print(f"Fetching and processing: {args.url} ...")
        try:
            rec = ZenloraPipeline.process_url(args.url)
            print("\n" + "=" * 60)
            print(f" 🎉 PROCESSED: {rec['zenlora_title']}")
            print("=" * 60)
            print(f" • Primary Category  : {rec['primary_category']}")
            print(f" • Content Bucket     : {rec['content_bucket']}")
            print(f" • DeoDap Wholesale   : ₹{rec['wholesale_price']}")
            print(f" • Zenlora Price      : ₹{rec['selling_price']} (MRP: ₹{rec['mrp']}, {rec['discount_pct']}% OFF)")
            print(f" • Net Profit Margin  : +₹{rec['gross_profit']} ({rec['profit_margin_pct']}%)")
            print(f" • Hook Text (0-3s)   : \"{rec['on_screen_hook_text']}\"")
            print(f" • CTA Keyword        : '{rec['cta_keyword']}'")
            print("-" * 60)
            print(f" [Storyboard Image Prompt (9:16)]:\n {rec['storyboard_image_prompt']}\n")
            print(f" [Scene 1 Video Prompt (0-5s)]:\n {rec['scene_1_video_prompt']}\n")
            print(f" [Scene 2 Video Prompt (5-10s with Continuity)]:\n {rec['scene_2_video_prompt']}\n")
            print(f" [Scene 3 Video Prompt (10-15s with Continuity)]:\n {rec['scene_3_video_prompt']}\n")
            print("=" * 60)

            excel_path = ZenloraPipeline.export_excel()
            print(f"✓ Automatically saved to database & Excel: {excel_path}\n")
        except Exception as e:
            print(f"Processing Error: {e}")
        return

    parser.print_help()

if __name__ == "__main__":
    main()
