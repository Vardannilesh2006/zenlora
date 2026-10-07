import os
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

# Add pipeline directory to path
PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.append(str(PIPELINE_DIR))

from pipeline_controller import ZenloraPipeline
from config import EXPORTS_DIR
from winning_engine.radar_controller import get_winners, scan_and_update_winners, import_to_studio

app = Flask(__name__, template_folder=str(PIPELINE_DIR / "templates"), static_folder=str(PIPELINE_DIR / "static"))
app.config['SECRET_KEY'] = 'zenlora-luxury-dropshipping-2026'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.jinja_env.auto_reload = True

@app.route('/')
def index():
    products = ZenloraPipeline.load_db()
    # Compute summary metrics
    total_products = len(products)
    total_profit = sum(p.get("gross_profit", 0) for p in products)
    avg_margin = round(sum(p.get("profit_margin_pct", 0) for p in products) / total_products, 1) if total_products > 0 else 0

    return render_template(
        'index.html',
        products=products,
        total_products=total_products,
        total_profit=total_profit,
        avg_margin=avg_margin
    )

@app.route('/radar')
def radar():
    niche = request.args.get('niche', 'All')
    winners = get_winners(niche=niche)
    all_winners = get_winners()
    
    total_winners = len(all_winners)
    avg_score = round(sum(w.get("winning_score", 0) for w in all_winners) / total_winners, 1) if total_winners > 0 else 0
    super_winners = sum(1 for w in all_winners if w.get("winning_score", 0) >= 88)
    scaling_fast = sum(1 for w in all_winners if 78 <= w.get("winning_score", 0) < 88)

    niches = ["All", "Home Decor", "Kitchen", "Gadgets", "Festive", "Gifts"]

    return render_template(
        'radar.html',
        winners=winners,
        selected_niche=niche,
        niches=niches,
        total_winners=total_winners,
        avg_score=avg_score,
        super_winners=super_winners,
        scaling_fast=scaling_fast
    )

@app.route('/api/radar/scan', methods=['POST'])
def api_radar_scan():
    try:
        data = request.get_json() or {}
        limit = int(data.get('limit', 8))
        winners = scan_and_update_winners(limit_per_niche=limit)
        return jsonify({
            'success': True,
            'count': len(winners),
            'winners': winners
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/radar/products', methods=['GET'])
def api_radar_products():
    niche = request.args.get('niche', 'All')
    winners = get_winners(niche=niche)
    return jsonify(winners)

@app.route('/api/radar/import/<handle>', methods=['POST'])
def api_radar_import(handle):
    try:
        imported_product = import_to_studio(handle)
        return jsonify({
            'success': True,
            'product': imported_product,
            'message': f"Product '{imported_product['extracted']['title']}' imported to Studio with 3-scene UGC storyboards!"
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/product/<handle>')
def product_detail(handle):
    products = ZenloraPipeline.load_db()
    product = next((p for p in products if p.get('handle') == handle), None)
    if not product:
        return "Product not found", 404
    return render_template('product_detail.html', p=product)

@app.route('/api/process', methods=['POST'])
def process_single():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'}), 400

    try:
        record = ZenloraPipeline.process_url(url)
        return jsonify({'success': True, 'product': record})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/process-batch', methods=['POST'])
def process_batch():
    data = request.get_json() or {}
    urls_raw = data.get('urls', '')
    if isinstance(urls_raw, str):
        urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
    elif isinstance(urls_raw, list):
        urls = urls_raw
    else:
        urls = []

    if not urls:
        return jsonify({'success': False, 'error': 'No URLs provided'}), 400

    results = ZenloraPipeline.process_batch(urls)
    successful = [r for r in results if r.get('success', False) != False and not r.get('error')]
    return jsonify({
        'success': True,
        'processed_count': len(successful),
        'results': results
    })

@app.route('/api/products', methods=['GET'])
def get_products():
    return jsonify(ZenloraPipeline.load_db())

@app.route('/api/products/<handle>', methods=['DELETE'])
def delete_product(handle):
    deleted = ZenloraPipeline.delete_product(handle)
    return jsonify({'success': deleted})

@app.route('/api/clear', methods=['POST'])
def clear_db():
    ZenloraPipeline.clear_db()
    return jsonify({'success': True})

@app.route('/api/export-excel', methods=['GET'])
def export_excel():
    try:
        filepath = ZenloraPipeline.export_excel()
        return send_file(
            filepath,
            as_attachment=True,
            download_name=os.path.basename(filepath),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print(" Zenlora AI Dropshipping & UGC Pipeline Engine")
    print(" Dashboard running at: http://127.0.0.1:5000")
    print("="*60 + "\n")
    app.run(host='127.0.0.1', port=5000, debug=False)
