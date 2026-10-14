import os
import subprocess

html_content = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zenlora Storefront Preview</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
  body { font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif; }
</style>
</head>
<body class="bg-zinc-100 min-h-screen p-4 sm:p-6 flex flex-col items-center justify-start text-zinc-900">

  <!-- Desktop Browser Frame -->
  <div class="w-full max-w-5xl bg-white rounded-2xl shadow-2xl overflow-hidden border border-zinc-200">
    
    <!-- Browser Top Bar -->
    <div class="bg-zinc-900 text-zinc-400 px-4 py-2.5 flex items-center justify-between text-xs border-b border-zinc-800">
      <div class="flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-rose-500 inline-block"></span>
        <span class="w-3 h-3 rounded-full bg-amber-500 inline-block"></span>
        <span class="w-3 h-3 rounded-full bg-emerald-500 inline-block"></span>
      </div>
      <div class="bg-zinc-800 px-6 py-1 rounded-full text-zinc-300 font-mono text-[11px] flex items-center gap-2 border border-zinc-700/60 shadow-inner">
        <span class="text-emerald-400">🔒</span>
        <span class="font-medium text-white">https://zenlora.store</span><span class="text-zinc-400">/products/vintage-heart-shaped-photo-frame</span>
      </div>
      <div class="text-[11px] text-zinc-400 font-medium">SmartBiz by Amazon Live Store</div>
    </div>

    <!-- Announcement Bar -->
    <div class="bg-gradient-to-r from-emerald-600 via-teal-700 to-indigo-800 text-white text-center py-2 px-4 text-xs font-bold tracking-wide flex items-center justify-center gap-2 shadow-xs">
      <span>⚡ PREPAID PRIVILEGE:</span>
      <span>Instant 15% OFF on UPI &amp; Cards | Priority 24-Hour Express Dispatch | Zero Delivery Fee</span>
      <span class="bg-white/20 px-2 py-0.5 rounded text-[10px] font-mono uppercase">Auto-Applied</span>
    </div>

    <!-- Store Header -->
    <header class="px-8 py-4 border-b border-zinc-200 flex items-center justify-between bg-white">
      <div class="flex items-center gap-8">
        <div class="flex items-center gap-2.5">
          <div class="w-9 h-9 rounded-xl bg-zinc-900 text-white flex items-center justify-center text-xl font-black shadow-xs">
            Z
          </div>
          <div>
            <h1 class="text-xl font-black tracking-tight text-zinc-900 leading-none">ZENLORA</h1>
            <span class="text-[9px] tracking-widest uppercase font-semibold text-zinc-500">SMART DROPSHIP STORE</span>
          </div>
        </div>
        <nav class="hidden md:flex items-center gap-5 text-xs font-semibold text-zinc-700">
          <span class="hover:text-black cursor-pointer">Home</span>
          <span class="text-emerald-700 font-bold border-b-2 border-emerald-600 pb-0.5">Home Decor</span>
          <span class="hover:text-black cursor-pointer">Kitchen &amp; Dining</span>
          <span class="hover:text-black cursor-pointer">Smart Gadgets</span>
          <span class="hover:text-black cursor-pointer">Festive &amp; Lights</span>
          <span class="hover:text-black cursor-pointer">Toys &amp; Games</span>
          <span class="text-rose-600 font-bold hover:text-rose-700 cursor-pointer">Under 199 Collection</span>
        </nav>
      </div>
      <div class="flex items-center gap-3 text-xs font-semibold">
        <span class="cursor-pointer text-zinc-600 hover:text-black">🔍 Search</span>
        <div class="bg-zinc-100 hover:bg-zinc-200 px-3 py-1.5 rounded-lg flex items-center gap-1.5 cursor-pointer">
          <span>🛍️ Cart</span>
          <span class="bg-zinc-900 text-white text-[10px] font-bold px-1.5 py-0.2 rounded-full">1</span>
        </div>
      </div>
    </header>

    <!-- Breadcrumb -->
    <div class="px-8 py-2.5 text-[11px] text-zinc-500 bg-zinc-50/70 border-b border-zinc-100 flex items-center gap-2">
      <span>Home</span> <span>/</span> <span>Home Decor</span> <span>/</span> <span class="text-zinc-900 font-semibold">Vintage Heart-Shaped Photo Frame</span>
    </div>

    <!-- Product Detail Layout -->
    <main class="p-8 grid grid-cols-1 md:grid-cols-12 gap-8 bg-white">

      <!-- Left Column: Image Gallery -->
      <div class="md:col-span-5 space-y-4">
        <div class="aspect-square rounded-2xl overflow-hidden bg-zinc-50 border border-zinc-200 shadow-xs relative group">
          <img src="https://cdn.shopify.com/s/files/1/0782/3284/6646/files/vQVYnsyzqI.jpg" alt="Product Main Image" class="w-full h-full object-cover">
          <span class="absolute top-3 left-3 bg-zinc-900/90 text-white text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider">
            ⭐ Bestseller
          </span>
          <span class="absolute top-3 right-3 bg-emerald-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider shadow-xs">
            29% OFF
          </span>
        </div>

        <!-- Thumbnail Grid -->
        <div class="grid grid-cols-4 gap-2.5">
          <div class="aspect-square rounded-xl overflow-hidden border-2 border-emerald-600 ring-2 ring-emerald-500/20 p-0.5 bg-white cursor-pointer">
            <img src="https://cdn.shopify.com/s/files/1/0782/3284/6646/files/vQVYnsyzqI.jpg" class="w-full h-full object-cover rounded-lg">
          </div>
          <div class="aspect-square rounded-xl overflow-hidden border border-zinc-200 hover:border-zinc-400 p-0.5 bg-zinc-50 cursor-pointer">
            <img src="https://cdn.shopify.com/s/files/1/0782/3284/6646/files/vQVYnsyzqI.jpg" class="w-full h-full object-cover rounded-lg opacity-80 hover:opacity-100 transition">
          </div>
          <div class="aspect-square rounded-xl overflow-hidden border border-zinc-200 hover:border-zinc-400 p-0.5 bg-zinc-50 cursor-pointer">
            <img src="https://cdn.shopify.com/s/files/1/0782/3284/6646/files/vQVYnsyzqI.jpg" class="w-full h-full object-cover rounded-lg opacity-80 hover:opacity-100 transition">
          </div>
          <div class="aspect-square rounded-xl overflow-hidden border border-zinc-200 hover:border-zinc-400 p-0.5 bg-zinc-50 cursor-pointer">
            <img src="https://cdn.shopify.com/s/files/1/0782/3284/6646/files/vQVYnsyzqI.jpg" class="w-full h-full object-cover rounded-lg opacity-80 hover:opacity-100 transition">
          </div>
        </div>

        <!-- Trust Badges -->
        <div class="p-3.5 rounded-xl bg-zinc-50 border border-zinc-200 grid grid-cols-3 gap-2 text-center text-[10px] font-semibold text-zinc-700">
          <div class="flex flex-col items-center gap-1">
            <span class="text-base">🚚</span>
            <span>Free Pan-India Delivery</span>
          </div>
          <div class="flex flex-col items-center gap-1 border-x border-zinc-200 px-1">
            <span class="text-base">🛡️</span>
            <span>7-Day Replacement</span>
          </div>
          <div class="flex flex-col items-center gap-1">
            <span class="text-base">💯</span>
            <span>100% Quality Verified</span>
          </div>
        </div>
      </div>

      <!-- Right Column: Product Info & Pricing & SmartBiz Description -->
      <div class="md:col-span-7 space-y-4">
        <div>
          <span class="text-[11px] font-bold uppercase tracking-wider text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full border border-emerald-200">
            🟢 In Stock · Ready to Dispatch
          </span>
          <h2 class="text-xl sm:text-2xl font-bold text-zinc-900 mt-2 leading-snug">
            Vintage Heart-Shaped Photo Frame – Elegant Antique Finish
          </h2>
          <div class="flex items-center gap-3 mt-1.5 text-xs text-zinc-600">
            <div class="flex items-center text-amber-500 font-bold">
              <span>★★★★★</span>
              <span class="ml-1 text-zinc-800">4.9/5</span>
            </div>
            <span>•</span>
            <span class="text-zinc-600">142 Ratings</span>
            <span>•</span>
            <span class="font-mono text-zinc-500">SKU: whl205_79558</span>
          </div>
        </div>

        <!-- Price Section -->
        <div class="p-3.5 rounded-xl bg-zinc-50 border border-zinc-200 flex items-center justify-between">
          <div class="flex items-baseline gap-3">
            <span class="text-3xl font-extrabold text-zinc-900">₹349</span>
            <span class="text-sm text-zinc-400 line-through">₹495</span>
            <span class="text-xs font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">Save 29% OFF</span>
          </div>
          <div class="text-right">
            <span class="text-[11px] text-zinc-500 block">Inclusive of all taxes</span>
            <span class="text-[10px] text-emerald-700 font-bold">Pay ₹297 via UPI (15% OFF)</span>
          </div>
        </div>

        <!-- Action CTA Buttons -->
        <div class="grid grid-cols-2 gap-3">
          <button class="w-full py-3 px-4 bg-zinc-900 hover:bg-black text-white rounded-xl font-bold text-sm shadow-md flex items-center justify-center gap-2">
            <span>⚡ BUY NOW</span>
          </button>
          <button class="w-full py-3 px-4 bg-white hover:bg-zinc-50 text-zinc-900 border-2 border-zinc-900 rounded-xl font-bold text-sm flex items-center justify-center gap-2">
            <span>🛒 ADD TO CART</span>
          </button>
        </div>

        <!-- ======================================================== -->
        <!-- THE NEW AUTO-EXPORTED PAYMENT INCENTIVE BOX (COLUMN L) -->
        <!-- ======================================================== -->
        <div class="rounded-xl border-2 border-emerald-500/80 bg-gradient-to-br from-emerald-50/90 via-teal-50/40 to-indigo-50/50 p-4 shadow-xs relative">
          <div class="flex items-center gap-2 mb-2">
            <span class="w-6 h-6 rounded-md bg-emerald-600 text-white flex items-center justify-center text-xs font-bold shadow-xs">⚡</span>
            <h4 class="text-xs font-black uppercase tracking-wider text-emerald-950">
              EXCLUSIVE ONLINE PAYMENT PRIVILEGES (Auto-Applied)
            </h4>
            <span class="ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-600 text-white uppercase">
              Save 15% OFF
            </span>
          </div>

          <div class="space-y-2 text-xs">
            <div class="flex items-start gap-2.5 bg-white p-3 rounded-lg border border-emerald-200 shadow-2xs">
              <span class="text-emerald-700 font-bold text-base leading-none">💳</span>
              <div class="leading-snug">
                <span class="font-bold text-zinc-900">Pay Online (UPI / GPay / PhonePe / Cards):</span>
                <span class="text-emerald-800 font-semibold block mt-0.5 text-xs">
                  Flat <span class="font-extrabold text-emerald-950 underline">15% Instant Discount</span> (Pay only ₹297) + <span class="font-bold text-emerald-950">Priority 24h Express Dispatch</span> + Zero Delivery Fee
                </span>
              </div>
            </div>

            <div class="flex items-start gap-2 bg-white/70 p-2.5 rounded-lg border border-zinc-200 text-zinc-700">
              <span class="text-zinc-500 text-sm leading-none">📦</span>
              <div class="leading-snug">
                <span class="font-semibold text-zinc-800">Cash on Delivery (COD):</span>
                <span class="text-zinc-600 text-[11px] block">Standard delivery available. ₹49 Cash Handling Fee applies on COD.</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Description Text -->
        <div class="space-y-1.5 pt-2 border-t border-zinc-200">
          <h4 class="text-xs font-bold uppercase tracking-wider text-zinc-800">Product Description</h4>
          <p class="text-xs text-zinc-600 leading-relaxed">
            Upgrade your everyday home decor routine with the Vintage Heart-Shaped Photo Frame. Crafted from durable, high-quality materials with an antique handcrafted finish, it offers effortless charm, reliable performance, and an elegant aesthetic ideal for modern Indian living rooms, bedrooms, and festive gifting.
          </p>
        </div>

      </div>

    </main>

    <!-- Store Footer Strip -->
    <footer class="bg-zinc-950 text-zinc-400 py-3.5 px-8 border-t border-zinc-800 flex items-center justify-between text-xs">
      <div>© 2026 Zenlora Store (zenlora.store). Powered by SmartBiz by Amazon.</div>
      <div class="flex items-center gap-4 text-zinc-400 font-medium text-[11px]">
        <span>Privacy Policy</span>
        <span>•</span>
        <span>Terms of Service</span>
        <span>•</span>
        <span>Return &amp; Refund Policy</span>
      </div>
    </footer>

  </div>

</body>
</html>
"""

os.makedirs(r"e:\Zenlora\scratch", exist_ok=True)
html_file = r"e:\Zenlora\scratch\storefront_preview.html"
with open(html_file, "w", encoding="utf-8") as f:
    f.write(html_content)

out_png = r"C:\Users\ASUS\.gemini\antigravity\brain\69fdf60e-0675-4b07-806c-735828bbb8fa\zenlora_store_product_page_preview.png"

cmd = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "--headless",
    "--disable-gpu",
    "--no-sandbox",
    "--hide-scrollbars",
    f"--screenshot={out_png}",
    "--window-size=1200,1180",
    html_file
]
subprocess.run(cmd, check=True)
print("SUCCESS:", out_png)
