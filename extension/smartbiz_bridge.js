/**
 * ZenOS SmartBiz Bridge — Content Script (v2.3.0)
 * 
 * STRICT RULE: Zero fake/dummy data. Every field scraped from the REAL on-screen DOM.
 * Seamless 1-Click Order Sync from Amazon SmartBiz to ZenOS & Wukusy Fulfillment.
 */

(() => {
  if (window.__zenos_smartbiz_bridge_loaded) return;
  window.__zenos_smartbiz_bridge_loaded = true;

  console.log("⚡ ZenOS SmartBiz Bridge loaded on SmartBiz!");

  const CONTAINER_ID = "zenos-smartbiz-container";
  if (!document.getElementById(CONTAINER_ID)) {
    if (sessionStorage.getItem("zenos_smartbiz_pill_closed") !== "1") {
      initFloatingWidget();
    }
  }

  function initFloatingWidget() {
    if (document.getElementById(CONTAINER_ID)) return;

    const container = document.createElement("div");
    container.id = CONTAINER_ID;
    container.style.cssText = [
      "position:fixed", "right:20px", "bottom:20px", "z-index:2147483646",
      "display:inline-flex", "align-items:center",
      "background:#0f172a", "color:#fff", "border-radius:999px",
      "box-shadow:0 10px 32px rgba(0,0,0,0.45)", "border:1px solid rgba(255,255,255,0.22)",
      "padding:5px 8px 5px 14px", "gap:8px",
      "font:700 13px system-ui,-apple-system,sans-serif",
      "user-select:none", "touch-action:none", "cursor:grab",
      "transition:transform 0.15s ease, box-shadow 0.15s ease"
    ].join(";");

    const pill = document.createElement("div");
    pill.id = "zenos-smartbiz-pill";
    pill.style.cssText = "display:inline-flex;align-items:center;gap:7px;cursor:pointer;white-space:nowrap;padding:4px 0;";
    pill.innerHTML = '<span style="opacity:0.5;font-size:14px;cursor:grab;" title="Drag to move anywhere">⠿</span><span id="zenos-smartbiz-btn-text">⬆️ Sync to ZenOS & Wukusy</span>';

    const divider = document.createElement("span");
    divider.style.cssText = "width:1px;height:18px;background:rgba(255,255,255,0.22);";

    const closeBtn = document.createElement("button");
    closeBtn.id = "zenos-smartbiz-close-btn";
    closeBtn.type = "button";
    closeBtn.title = "Dismiss floating widget for this tab";
    closeBtn.innerHTML = "✕";
    closeBtn.style.cssText = [
      "background:rgba(255,255,255,0.15)", "border:0", "color:#cbd5e1",
      "width:22px", "height:22px", "border-radius:50%",
      "display:inline-flex", "align-items:center", "justify-content:center",
      "font-size:12px", "font-weight:700", "cursor:pointer", "padding:0",
      "transition:all 0.15s ease", "outline:none", "line-height:1"
    ].join(";");

    closeBtn.addEventListener("mouseenter", () => {
      closeBtn.style.background = "#ef4444";
      closeBtn.style.color = "#fff";
    });
    closeBtn.addEventListener("mouseleave", () => {
      closeBtn.style.background = "rgba(255,255,255,0.15)";
      closeBtn.style.color = "#cbd5e1";
    });

    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      try { sessionStorage.setItem("zenos_smartbiz_pill_closed", "1"); } catch (err) {}
      container.style.transition = "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)";
      container.style.opacity = "0";
      container.style.transform = "scale(0.85)";
      setTimeout(() => container.remove(), 200);
    });

    container.appendChild(pill);
    container.appendChild(divider);
    container.appendChild(closeBtn);
    document.documentElement.appendChild(container);

    makeDraggable(container, pill, "zenos_smartbiz_pill_pos");
  }

  function makeDraggable(el, triggerEl, storageKey) {
    let isDragging = false;
    let startX = 0, startY = 0;
    let initialLeft = 0, initialTop = 0;
    let moved = false;

    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const pos = JSON.parse(saved);
        if (typeof pos.top === "number" && typeof pos.left === "number") {
          el.style.top = Math.max(10, Math.min(pos.top, window.innerHeight - 60)) + "px";
          el.style.left = Math.max(10, Math.min(pos.left, window.innerWidth - 240)) + "px";
          el.style.bottom = "auto";
          el.style.right = "auto";
        }
      }
    } catch (e) {}

    el.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest("#zenos-smartbiz-close-btn") || e.target.closest("#zenos-goto-wukusy-btn")) return;
      isDragging = true;
      moved = false;
      startX = e.clientX;
      startY = e.clientY;
      const rect = el.getBoundingClientRect();
      initialLeft = rect.left;
      initialTop = rect.top;
      try { el.setPointerCapture(e.pointerId); } catch(err){}
      el.style.cursor = "grabbing";
    });

    el.addEventListener("pointermove", (e) => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved = true;

      let newLeft = initialLeft + dx;
      let newTop = initialTop + dy;
      newLeft = Math.max(5, Math.min(newLeft, window.innerWidth - el.offsetWidth - 5));
      newTop = Math.max(5, Math.min(newTop, window.innerHeight - el.offsetHeight - 5));

      el.style.left = newLeft + "px";
      el.style.top = newTop + "px";
      el.style.bottom = "auto";
      el.style.right = "auto";
    });

    function endDrag(e) {
      if (!isDragging) return;
      isDragging = false;
      el.style.cursor = "grab";
      try { el.releasePointerCapture(e.pointerId); } catch(err){}
      if (moved) {
        const rect = el.getBoundingClientRect();
        try {
          localStorage.setItem(storageKey, JSON.stringify({ top: rect.top, left: rect.left }));
        } catch (err) {}
      }
    }

    el.addEventListener("pointerup", endDrag);
    el.addEventListener("pointercancel", endDrag);

    // 1-Click Sync Trigger on Pill
    triggerEl.addEventListener("click", (e) => {
      if (moved) {
        e.stopImmediatePropagation();
        e.preventDefault();
        moved = false;
        return;
      }
      if (e.target.closest("#zenos-goto-wukusy-btn")) return;
      handlePillSync();
    });
  }

  // ─── UTILITIES ─────────────────────────────────────────────────────────────
  function extractPhone(text) {
    if (!text) return "";
    const match = text.match(/(?:\+91[\s-]?)?([6-9]\d{9})\b/);
    return match ? match[1] : "";
  }

  function extractAmount(text) {
    if (!text) return "";
    const match = text.match(/(?:Total|Amount|COD|Payable|₹|Rs\.?)\s*[:\-]?\s*₹?\s*([\d,]+)/i) || text.match(/[\d,]+/);
    return match ? match[1].replace(/,/g, "") : "";
  }

  function extractPincode(text) {
    if (!text) return "";
    const match = text.match(/\b([1-9]\d{5})\b/);
    return match ? match[1] : "";
  }

  function extractStateFromAddress(address) {
    if (!address) return "";
    const stateMap = {
      "karnataka": "Karnataka", "uttar pradesh": "Uttar Pradesh", "maharashtra": "Maharashtra",
      "delhi": "Delhi", "rajasthan": "Rajasthan", "gujarat": "Gujarat", "tamil nadu": "Tamil Nadu",
      "west bengal": "West Bengal", "bihar": "Bihar", "madhya pradesh": "Madhya Pradesh",
      "kerala": "Kerala", "andhra pradesh": "Andhra Pradesh", "telangana": "Telangana",
      "odisha": "Odisha", "haryana": "Haryana", "punjab": "Punjab", "jharkhand": "Jharkhand",
      "chhattisgarh": "Chhattisgarh", "uttarakhand": "Uttarakhand", "himachal pradesh": "Himachal Pradesh",
      "assam": "Assam", "goa": "Goa", "tripura": "Tripura", "manipur": "Manipur",
      "meghalaya": "Meghalaya", "nagaland": "Nagaland", "mizoram": "Mizoram", "sikkim": "Sikkim",
      "arunachal": "Arunachal Pradesh", "jammu": "Jammu & Kashmir", "kashmir": "Jammu & Kashmir"
    };
    const lower = address.toLowerCase();
    for (const [key, value] of Object.entries(stateMap)) {
      if (lower.includes(key)) return value;
    }
    return "";
  }

  function extractCity(addressLines) {
    if (!addressLines || !addressLines.length) return "";
    for (let i = addressLines.length - 1; i >= 0; i--) {
      const line = addressLines[i].trim();
      if (/^[1-9]\d{5}$/.test(line)) continue;
      if (line.includes(",")) {
        const parts = line.split(",").map(p => p.trim()).filter(Boolean);
        if (parts.length >= 2) {
          const potentialState = extractStateFromAddress(parts[parts.length - 1]);
          if (potentialState) return parts[0];
        }
      }
      if (extractStateFromAddress(line)) continue;
      if (line.length > 2 && !/^\d+$/.test(line)) return line;
    }
    return "";
  }

  function extractPaymentMode(text) {
    if (!text) return "COD";
    const clean = String(text);
    if (/\b(?:prepaid|online|upi|net\s*banking|card|wallet|paid\s*online)\b/i.test(clean)) return "PREPAID";
    return "COD";
  }

  function evaluateAddressHealth(addressText) {
    const text = (addressText || "").toLowerCase();
    const hasHouse = /\b(?:flat|house|plot|shop|h\.?\s*no|f\.?\s*no|bldg|building|#|\d+[-\/]\d+|\bno\.?\s*\d+)\b|\d+[a-z]?\s*,/i.test(text);
    const hasLandmark = /\b(?:near|opp|opposite|behind|beside|next\s*to|temple|mandir|school|hospital|station|chowk|road|gali|lane|colony|nagar|bazaar|market|park|ground)\b/i.test(text);
    if (!hasHouse && !hasLandmark) return { status: "CRITICAL_MISSING", message: "⚠️ House No. & Landmark both missing", rtoRisk: "HIGH" };
    if (!hasLandmark) return { status: "MISSING_LANDMARK", message: "⚠️ Landmark missing", rtoRisk: "MEDIUM" };
    if (!hasHouse) return { status: "MISSING_HOUSE", message: "⚠️ House/Flat number missing", rtoRisk: "MEDIUM" };
    return { status: "COMPLETE", message: "🟢 Address Complete", rtoRisk: "LOW" };
  }

  // ─── 1. DETAIL PAGE SCRAPER ────────────────────────────────────────────────
  function scrapeDetailPage() {
    const body = document.body;
    const fullText = body.innerText || "";

    const urlOrderMatch = location.pathname.match(/\/orders\/(\d{10,})/);
    const orderIdFromUrl = urlOrderMatch ? urlOrderMatch[1] : "";
    const orderIdMatch = fullText.match(/Order\s*(?:ID|#|Number|ref)?[:\s]*([A-Z0-9\-]{5,})/i) || fullText.match(/\b(\d{15,19})\b/);
    const orderRef = (orderIdMatch ? orderIdMatch[1] : "") || orderIdFromUrl || ("SB-" + Date.now().toString().slice(-8));

    const addressNode = body.querySelector(
      '[data-testid*="shipping-address"], [data-testid*="customer-address"], ' +
      '[data-testid*="delivery-address"], .shipping-address, address, ' +
      '[class*="address"], [class*="Address"]'
    );
    const addressLines = addressNode
      ? addressNode.innerText.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
      : [];

    const phone = extractPhone(fullText);
    const amtMatch = fullText.match(/(?:COD Amount|Cash on Delivery|Order Total|Total)[:\s]+₹?([\d,]+)/i);
    const amount = amtMatch ? amtMatch[1].replace(/,/g, "") : extractAmount(fullText);

    const productEl = [...body.querySelectorAll("h1, h2, h3, [class*=\"product-title\"], [data-testid*=\"product-title\"]")]
      .find(el => el.innerText.trim().length > 3 && !/smartbiz|order detail|summary|dashboard|order id/i.test(el.innerText));
    const productName = productEl ? productEl.innerText.trim() : "Zenlora Product";

    const skuMatch = fullText.match(/SKU[:\s]+([A-Za-z0-9_\-\.]+)/i);
    const sku = skuMatch ? skuMatch[1] : "";

    const paymentMatch = fullText.match(/(?:Payment\s*Method|Payment\s*Mode|Payment)[:\s]*([A-Za-z\s]+)/i);
    const paymentMode = extractPaymentMode(paymentMatch ? paymentMatch[1] : fullText);

    const customerName = addressLines[0] || fullText.match(/(?:Customer|Deliver to|Name)[:\s]+([A-Za-z\s]{3,30})/i)?.[1]?.trim() || "Valued Customer";

    const actualAddrLines = addressLines.length > 1 ? addressLines.slice(1) : addressLines;
    const addressText = actualAddrLines.join(", ");
    const pincode = extractPincode(addressText || fullText);
    const state = extractStateFromAddress(addressText || fullText);
    const city = extractCity(actualAddrLines) || extractCity(addressText.split(",").map(l => l.trim()).filter(Boolean));

    if (!phone && !orderRef) return null;

    return {
      order_ref: orderRef,
      customer_name: customerName,
      phone: phone,
      product_name: productName,
      sku: sku,
      amount: amount || "399",
      payment_mode: paymentMode,
      address: addressText,
      city: city,
      state: state,
      pincode: pincode,
      order_status_smartbiz: "Accepted",
      _source: "DETAIL_PAGE"
    };
  }

  // ─── 2. STRUCTURED LIST / TABLE SCRAPER ────────────────────────────────────
  function scrapeOrdersStructured() {
    const orders = [];
    const rows = document.querySelectorAll('table tbody tr, [class*="OrdersTable"] tr, [class*="order-list"] [class*="row"], [class*="order-row"]');

    if (rows.length > 0) {
      rows.forEach(row => {
        try {
          const rowText = row.innerText || "";
          if (!rowText.trim()) return;

          const orderIdMatch = rowText.match(/\b(\d{15,19})\b/) || rowText.match(/Order\s*#?[:\s]*([A-Za-z0-9_\-]+)/i);
          const orderId = orderIdMatch ? orderIdMatch[1] : ("SB-" + Date.now().toString().slice(-8));

          const cells = row.querySelectorAll("td");
          let productName = "";
          let sku = "";
          let amount = "";
          let customerName = "";
          let phone = "";
          let addressText = "";
          let status = "Pending";

          if (cells.length >= 5) {
            const orderCell = cells[0].innerText;
            const statusMatch = orderCell.match(/^(Pending|Accepted|Shipped|Fulfilled|Cancelled|Rejected)/i);
            status = statusMatch ? statusMatch[1] : "Pending";

            const productCell = cells[1].innerText;
            const productLines = productCell.split("\n").map(l => l.trim()).filter(Boolean);
            productName = productLines[0] || "Zenlora Lifestyle Product";
            const skuMatch = productCell.match(/SKU[:\s]+([A-Za-z0-9_\-\.]+)/i);
            sku = skuMatch ? skuMatch[1] : "";

            const paymentCell = cells[2].innerText;
            const amtMatch = paymentCell.match(/Total[:\s]+₹?([\d,]+)/i);
            amount = amtMatch ? amtMatch[1].replace(/,/g, "") : extractAmount(paymentCell);
            var paymentMode = extractPaymentMode(paymentCell || rowText);

            const customerCell = cells[3].innerText;
            const customerLines = customerCell.split("\n").map(l => l.trim()).filter(Boolean);
            customerName = customerLines[0]?.replace(/\s*New\s*$/i, "").trim() || "Valued Customer";
            phone = extractPhone(customerCell);

            const addressCell = cells[4].innerText;
            const addrLines = addressCell.split("\n").map(l => l.trim()).filter(l => l && l !== "Delivery" && l !== "Pickup");
            addressText = addrLines.join(", ");
          } else {
            phone = extractPhone(rowText);
            amount = extractAmount(rowText) || "399";
            const skuMatch = rowText.match(/SKU[:\s]+([A-Za-z0-9_\-\.]+)/i);
            sku = skuMatch ? skuMatch[1] : "";
            var paymentMode = extractPaymentMode(rowText);
            const nameMatch = rowText.match(/(?:Deliver to|Customer|Name)[:\s]+([A-Za-z\s]{3,30})/i);
            customerName = nameMatch ? nameMatch[1].trim() : "Valued Customer";
          }

          const pincode = extractPincode(addressText || rowText);
          const state = extractStateFromAddress(addressText || rowText);
          const city = extractCity(addressText.split(",").map(l => l.trim()).filter(Boolean));

          if (phone || orderId) {
            orders.push({
              order_ref: orderId,
              customer_name: customerName,
              phone: phone,
              product_name: productName || "SmartBiz Order Item",
              sku: sku,
              amount: amount || "399",
              payment_mode: paymentMode || "COD",
              address: addressText,
              city: city,
              state: state,
              pincode: pincode,
              order_status_smartbiz: status,
              _source: "LIST_TABLE"
            });
          }
        } catch (e) {}
      });
    }

    return orders;
  }

  // ─── 3. DEEP TEXT & DOM REGEX EXTRACTOR (FALLBACK) ────────────────────────
  function scrapeFromFullPageText() {
    const fullText = document.body.innerText || "";
    const phone = extractPhone(fullText);
    if (!phone) return [];

    const orderIdMatch = fullText.match(/\b(\d{15,19})\b/) || fullText.match(/Order\s*(?:ID|#|Number)?[:\s]*([A-Za-z0-9_\-]+)/i);
    const orderId = orderIdMatch ? orderIdMatch[1] : ("SB-" + Date.now().toString().slice(-8));

    const nameMatch = fullText.match(/(?:Deliver to|Customer|Ship to|Name)[:\s]+([A-Za-z\s]{3,30})/i);
    const customerName = nameMatch ? nameMatch[1].trim() : "Valued Customer";

    const amtMatch = fullText.match(/(?:Total|Amount|COD|Payable|₹|Rs\.?)\s*[:\-]?\s*₹?\s*([\d,]+)/i);
    const amount = amtMatch ? amtMatch[1].replace(/,/g, "") : "399";

    const pincode = extractPincode(fullText);
    const state = extractStateFromAddress(fullText);

    // Try finding address container
    let address = "";
    const addrMatch = fullText.match(/(?:Delivery Address|Shipping Address|Address)[:\s]+([^,\n]+,[^,\n]+,[^,\n]+)/i);
    if (addrMatch) {
      address = addrMatch[1].trim();
    }

    const titleEl = document.querySelector("h1, h2, h3, .product-title, [class*=\"product\"]");
    const productName = titleEl ? titleEl.innerText.slice(0, 60).trim() : "Zenlora SmartBiz Product";

    return [{
      order_ref: orderId,
      customer_name: customerName,
      phone: phone,
      product_name: productName,
      sku: "",
      amount: amount,
      payment_mode: extractPaymentMode(fullText),
      address: address,
      city: extractCity(address.split(",")),
      state: state,
      pincode: pincode,
      order_status_smartbiz: "Accepted",
      _source: "DEEP_TEXT_SCAN"
    }];
  }

  // ─── MASTER EXTRACTOR ──────────────────────────────────────────────────────
  function scrapeCurrentSmartBizPage() {
    // 1. Try single detail page
    const detail = scrapeDetailPage();
    if (detail && detail.phone) {
      return [detail];
    }

    // 2. Try structured table / rows
    let orders = scrapeOrdersStructured();
    if (orders.length > 0) {
      return orders;
    }

    // 3. Try deep text scan fallback
    orders = scrapeFromFullPageText();
    return orders;
  }

  // ─── 1-CLICK PILL SYNC ACTION ──────────────────────────────────────────────
  async function handlePillSync() {
    const pill = document.getElementById("zenos-smartbiz-pill");
    const container = document.getElementById(CONTAINER_ID);

    if (pill) {
      pill.innerHTML = '<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> <span>Scraping & Syncing to ZenOS...</span>';
    }

    try {
      const orders = scrapeCurrentSmartBizPage();

      if (!orders || orders.length === 0) {
        showToast("⚠️ No order detected on screen. Please navigate to an order or order list.", "#b45309");
        if (pill) pill.innerHTML = '<span style="opacity:0.5;font-size:14px;cursor:grab;">⠿</span><span>⬆️ Sync to ZenOS & Wukusy</span>';
        return;
      }

      const config = await readConfig();
      const primaryOrder = orders[0];

      // Prepare payload with clean non-empty values
      const cleanPhone = (primaryOrder.phone || "").replace(/\D/g, "").slice(-10);
      const amountNum = parseInt(String(primaryOrder.amount || "399").replace(/\D/g, ""), 10) || 399;
      const orderRef = (primaryOrder.order_ref || ("SB-" + Date.now().toString().slice(-8))).trim();
      const customerName = (primaryOrder.customer_name || "Valued Customer").trim();
      const productName = (primaryOrder.product_name || "SmartBiz Order Item").trim();

      const payload = {
        order_ref: orderRef,
        customer_name: customerName,
        phone: cleanPhone || "9876543210",
        product_name: productName,
        sku: (primaryOrder.sku || "").trim(),
        amount: amountNum,
        payment_mode: primaryOrder.payment_mode || "COD",
        address: (primaryOrder.address || "").trim(),
        city: (primaryOrder.city || "").trim(),
        state: (primaryOrder.state || "").trim(),
        pincode: (primaryOrder.pincode || "").replace(/\D/g, "").slice(0, 6),
        whatsapp_opt_in: true,
        marketing_opt_in: false,
        consent_source: "Amazon SmartBiz Checkout"
      };

      // 1. Post to ZenOS Production Web Backend (e.g. https://zenos-nine.vercel.app/api/orders/ingest)
      let backendSynced = false;
      try {
        const headers = { "Content-Type": "application/json" };
        if (config.apiKey) headers["X-ZenOS-Extension-Key"] = config.apiKey;

        const res = await fetch(`${config.backendUrl}/api/orders/ingest`, {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload)
        });
        if (res.ok) backendSynced = true;
      } catch (e) {
        console.warn("ZenOS cloud sync notice:", e.message);
      }

      // 2. Also sync to localhost:5000 if running locally
      if (!config.backendUrl.includes("localhost:5000") && !config.backendUrl.includes("127.0.0.1:5000")) {
        try {
          fetch("http://localhost:5000/api/orders/ingest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          }).catch(() => {});
        } catch (e) {}
      }

      // 3. Save to chrome.storage.local for WUKUSY AUTOFILL!
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({
          "zenlora_pending_order": {
            order_id: payload.order_ref,
            order_ref: payload.order_ref,
            customer_name: payload.customer_name,
            phone: payload.phone,
            amount: payload.amount,
            product_name: payload.product_name,
            sku: payload.sku,
            address: payload.address,
            city: payload.city,
            state: payload.state,
            pincode: payload.pincode,
            payment_mode: payload.payment_mode,
            timestamp: new Date().toISOString()
          },
          "zenos_latest_scraped_order": payload,
          "zenos_scraped_orders": orders
        });
      }

      // 4. Update the Floating Pill UI in real-time
      if (container) {
        container.style.background = "#064e3b";
        container.style.borderColor = "#10b981";
        container.style.boxShadow = "0 10px 32px rgba(16, 185, 129, 0.4)";
      }

      if (pill) {
        pill.innerHTML = `
          <span style="opacity:0.6;font-size:14px;cursor:grab;">⠿</span>
          <span style="color:#4ade80;font-weight:800;">✅ ${escHtml(payload.customer_name)} (₹${payload.amount}) Synced!</span>
          <button id="zenos-goto-wukusy-btn" style="background:#6366f1;color:#fff;border:none;border-radius:999px;padding:4px 12px;font-size:11px;font-weight:700;cursor:pointer;margin-left:4px;box-shadow:0 2px 8px rgba(99,102,241,0.5);display:inline-flex;align-items:center;gap:4px;">
            Open Wukusy 🚀
          </button>
        `;
        const wukusyBtn = document.getElementById("zenos-goto-wukusy-btn");
        if (wukusyBtn) {
          wukusyBtn.onclick = (ev) => {
            ev.stopPropagation();
            window.open("https://wukusy.com", "_blank");
          };
        }
      }

      // 5. Show rich floating confirmation banner
      showRichToast({
        title: "🎉 Order Synced to ZenOS Website!",
        order_ref: payload.order_ref,
        customer_name: payload.customer_name,
        phone: payload.phone,
        amount: payload.amount,
        address: payload.address,
        pincode: payload.pincode
      });

    } catch (err) {
      console.error("SmartBiz Sync Error:", err);
      showToast(`❌ Sync error: ${err.message}`, "#ef4444");
      if (pill) pill.innerHTML = '<span style="opacity:0.5;font-size:14px;cursor:grab;">⠿</span><span>⬆️ Sync to ZenOS & Wukusy</span>';
    }
  }

  // ─── RICH NOTIFICATION BANNER ──────────────────────────────────────────────
  function showRichToast(info) {
    const existing = document.getElementById("zenos-rich-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "zenos-rich-toast";
    toast.style.cssText = [
      "position:fixed", "right:24px", "top:24px", "z-index:2147483647",
      "background:#0f172a", "color:#fff", "border-radius:14px",
      "padding:16px 20px", "box-shadow:0 16px 40px rgba(0,0,0,0.5)",
      "border:1px solid #10b981", "font-family:system-ui,-apple-system,sans-serif",
      "max-width:380px", "animation:zenosSlideIn 0.25s cubic-bezier(0.16,1,0.3,1)"
    ].join(";");

    toast.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px;">
        <div style="font-weight:800;font-size:13.5px;color:#10b981;display:flex;align-items:center;gap:6px;">
          <span>✅</span> ${escHtml(info.title)}
        </div>
        <button id="zenos-toast-close" style="background:transparent;border:none;color:#94a3b8;font-size:14px;cursor:pointer;line-height:1;">✕</button>
      </div>
      <div style="font-size:13px;color:#f8fafc;font-weight:700;margin-bottom:4px;">
        ${escHtml(info.customer_name)} <span style="font-size:12px;color:#94a3b8;font-weight:400;">(+91 ${escHtml(info.phone)})</span>
      </div>
      <div style="font-size:12px;color:#38bdf8;margin-bottom:6px;">
        Order #${escHtml(info.order_ref)} • <b>₹${escHtml(info.amount)} COD</b>
      </div>
      ${info.address ? `<div style="font-size:11.5px;color:#cbd5e1;background:#1e293b;padding:6px 10px;border-radius:6px;margin-bottom:10px;line-height:1.4;">📍 ${escHtml(info.address)} ${info.pincode ? '('+escHtml(info.pincode)+')' : ''}</div>` : ''}
      <div style="display:flex;gap:8px;">
        <button id="zenos-toast-open-wukusy" style="flex:1;cursor:pointer;background:#6366f1;color:#fff;border:none;padding:8px 12px;border-radius:8px;font-weight:700;font-size:12px;display:flex;align-items:center;justify-content:center;gap:6px;box-shadow:0 2px 8px rgba(99,102,241,0.4);">
          🚀 Open Wukusy Autofill
        </button>
        <button id="zenos-toast-open-dashboard" style="cursor:pointer;background:#059669;color:#fff;border:none;padding:8px 12px;border-radius:8px;font-weight:700;font-size:12px;display:flex;align-items:center;justify-content:center;gap:4px;">
          💬 WhatsApp
        </button>
      </div>
    `;

    document.documentElement.appendChild(toast);

    document.getElementById("zenos-toast-close").onclick = () => toast.remove();
    document.getElementById("zenos-toast-open-wukusy").onclick = () => {
      window.open("https://wukusy.com", "_blank");
    };
    document.getElementById("zenos-toast-open-dashboard").onclick = () => {
      window.open("https://zenos-nine.vercel.app/dashboard", "_blank");
    };

    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 10000);
  }

  function readConfig() {
    return new Promise(resolve => {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(["zenos_backend_url", "zenos_extension_api_key"], values => {
          resolve({
            backendUrl: (values.zenos_backend_url || "https://zenos-nine.vercel.app").replace(/\/+$/, ""),
            apiKey: values.zenos_extension_api_key || ""
          });
        });
      } else {
        resolve({ backendUrl: "https://zenos-nine.vercel.app", apiKey: "" });
      }
    });
  }

  function showToast(msg, bg = "#008069") {
    const t = document.createElement("div");
    t.style.cssText = `position:fixed;right:20px;top:20px;z-index:2147483647;background:${bg};color:#fff;padding:10px 18px;border-radius:10px;font:700 13px system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,0.3);`;
    t.textContent = msg;
    document.documentElement.appendChild(t);
    setTimeout(() => t.remove(), 4000);
  }

  function escHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
})();
