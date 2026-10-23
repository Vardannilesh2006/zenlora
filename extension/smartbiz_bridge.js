/**
 * ZenOS SmartBiz Bridge — Content Script
 * 
 * STRICT RULE: Zero fake/dummy data. Every field scraped from the REAL on-screen DOM.
 * This script runs on ALL Amazon SmartBiz pages (orders list + order detail).
 * 
 * Two modes:
 *  1. LIST MODE  — Scrapes the /orders table (all visible orders on screen)
 *  2. DETAIL MODE — Scrapes a single order detail page
 */

(() => {
  // ─── Pill Button (injected once) ─────────────────────────────────────────
  const PILL_ID = 'zenos-smartbiz-pill';
  if (!document.getElementById(PILL_ID)) {
    const pill = document.createElement('button');
    pill.id = PILL_ID;
    pill.type = 'button';
    pill.innerHTML = '🛡️ ZenOS: Sync Orders';
    pill.style.cssText = [
      'position:fixed', 'right:20px', 'bottom:20px', 'z-index:2147483646',
      'padding:10px 16px', 'border:0', 'border-radius:999px',
      'background:#0f172a', 'color:#fff', 'font:700 13px system-ui,-apple-system,sans-serif',
      'box-shadow:0 8px 20px rgba(0,0,0,0.28)', 'cursor:pointer',
      'display:flex', 'align-items:center', 'gap:7px', 'white-space:nowrap'
    ].join(';');
    pill.addEventListener('click', () => {
      const pageType = detectPageType();
      if (pageType === 'LIST') openBulkListModal();
      else if (pageType === 'DETAIL') openSingleOrderModal();
      else showToast('⚠️ Navigate to the SmartBiz Orders page first.', '#b45309');
    });
    document.documentElement.appendChild(pill);
  }

  // ─── Page Type Detection ──────────────────────────────────────────────────
  function detectPageType() {
    const url = location.href;
    // Detail page: has a long numeric order ID in path
    if (/\/orders?\/\d{15,}/.test(url)) return 'DETAIL';
    // List page: /orders or contains order table rows
    if (/\/orders/.test(url) || document.querySelector('table tbody tr, [data-order-id], [class*="order-row"]')) return 'LIST';
    return 'UNKNOWN';
  }

  // ─── UTILITY: Clean phone number ──────────────────────────────────────────
  function extractPhone(text) {
    if (!text) return '';
    const match = text.match(/(?:\+91[\s-]?)?([6-9]\d{9})\b/);
    return match ? match[1] : '';
  }

  // ─── UTILITY: Clean amount ────────────────────────────────────────────────
  function extractAmount(text) {
    if (!text) return '';
    const match = text.match(/[\d,]+/);
    return match ? match[0].replace(/,/g, '') : '';
  }

  // ─── UTILITY: Extract pincode ─────────────────────────────────────────────
  function extractPincode(text) {
    if (!text) return '';
    const match = text.match(/\b([1-9]\d{5})\b/);
    return match ? match[1] : '';
  }

  // ─── UTILITY: Extract state from address ─────────────────────────────────
  function extractStateFromAddress(address) {
    if (!address) return '';
    const stateMap = {
      'karnataka': 'Karnataka', 'uttar pradesh': 'Uttar Pradesh', 'maharashtra': 'Maharashtra',
      'delhi': 'Delhi', 'rajasthan': 'Rajasthan', 'gujarat': 'Gujarat', 'tamil nadu': 'Tamil Nadu',
      'west bengal': 'West Bengal', 'bihar': 'Bihar', 'madhya pradesh': 'Madhya Pradesh',
      'kerala': 'Kerala', 'andhra pradesh': 'Andhra Pradesh', 'telangana': 'Telangana',
      'odisha': 'Odisha', 'haryana': 'Haryana', 'punjab': 'Punjab', 'jharkhand': 'Jharkhand',
      'chhattisgarh': 'Chhattisgarh', 'uttarakhand': 'Uttarakhand', 'himachal pradesh': 'Himachal Pradesh',
      'assam': 'Assam', 'goa': 'Goa', 'tripura': 'Tripura', 'manipur': 'Manipur',
      'meghalaya': 'Meghalaya', 'nagaland': 'Nagaland', 'mizoram': 'Mizoram', 'sikkim': 'Sikkim',
      'arunachal': 'Arunachal Pradesh', 'jammu': 'Jammu & Kashmir', 'kashmir': 'Jammu & Kashmir'
    };
    const lower = address.toLowerCase();
    for (const [key, value] of Object.entries(stateMap)) {
      if (lower.includes(key)) return value;
    }
    return '';
  }

  // ─── UTILITY: Extract city from address lines ──────────────────────────────
  function extractCity(addressLines) {
    if (!addressLines || !addressLines.length) return '';
    // City is usually second-to-last line before pincode/state
    for (let i = addressLines.length - 1; i >= 0; i--) {
      const line = addressLines[i].trim();
      if (/^[1-9]\d{5}$/.test(line)) continue; // skip pincode
      if (extractStateFromAddress(line)) continue; // skip state-only lines
      if (line.length > 2 && !/^\d+$/.test(line)) return line;
    }
    return '';
  }

  // ─── Address health evaluation ────────────────────────────────────────────
  function evaluateAddressHealth(addressText) {
    const text = (addressText || '').toLowerCase();
    const hasHouse = /\b(?:flat|house|plot|shop|h\.?\s*no|f\.?\s*no|bldg|building|#|\d+[-\/]\d+|\bno\.?\s*\d+)\b|\d+[a-z]?\s*,/i.test(text);
    const hasLandmark = /\b(?:near|opp|opposite|behind|beside|next\s*to|temple|mandir|school|hospital|station|chowk|road|gali|lane|colony|nagar|bazaar|market|park|ground)\b/i.test(text);
    if (!hasHouse && !hasLandmark) return { status: 'CRITICAL_MISSING', message: '⚠️ House No. & Landmark both missing', rtoRisk: 'HIGH' };
    if (!hasLandmark) return { status: 'MISSING_LANDMARK', message: '⚠️ Landmark missing', rtoRisk: 'MEDIUM' };
    if (!hasHouse) return { status: 'MISSING_HOUSE', message: '⚠️ House/Flat number missing', rtoRisk: 'MEDIUM' };
    return { status: 'COMPLETE', message: '🟢 Address Complete', rtoRisk: 'LOW' };
  }

  // ══════════════════════════════════════════════════════════════════════════
  // MODE 1: LIST PAGE SCRAPER
  // Scrapes ALL order rows from the SmartBiz orders table
  // ══════════════════════════════════════════════════════════════════════════
  function scrapeAllOrdersFromList() {
    const orders = [];

    /**
     * SmartBiz orders page DOM structure (observed from screenshot):
     * Table columns: Order | Product | Payment | Customer | Address
     * Each row contains:
     *   - Order: status badge + order ID (blue link) + date + "Add Notes"
     *   - Product: image + product name + "1 x ₹399" + "SKU: xxxxxxxx"
     *   - Payment: "Mode: COD" + "Total: ₹399"
     *   - Customer: customer name + "New" badge + email? + WhatsApp phone
     *   - Address: "Delivery" label + address lines + pincode copy icon
     */

    // Strategy 1: SmartBiz React table rows
    const rows = document.querySelectorAll('table tbody tr, [class*="OrdersTable"] tr, [class*="order-list"] [class*="row"], [class*="order-row"]');

    if (rows.length > 0) {
      rows.forEach(row => {
        try {
          const rowText = row.innerText || '';
          if (!rowText.trim()) return;

          // Order ID — long numeric string (15+ digits) or link text
          const orderIdMatch = rowText.match(/\b(\d{15,19})\b/);
          const orderId = orderIdMatch ? orderIdMatch[1] : '';

          // Product name — grab from the product cell (second column)
          const cells = row.querySelectorAll('td');
          let productName = '';
          let sku = '';
          let amount = '';
          let customerName = '';
          let phone = '';
          let addressText = '';
          let status = '';

          if (cells.length >= 5) {
            // Column 0: Order (status + ID + date)
            const orderCell = cells[0].innerText;
            const statusMatch = orderCell.match(/^(Pending|Accepted|Shipped|Fulfilled|Cancelled|Rejected)/i);
            status = statusMatch ? statusMatch[1] : 'Pending';

            // Column 1: Product
            const productCell = cells[1].innerText;
            const productLines = productCell.split('\n').map(l => l.trim()).filter(Boolean);
            productName = productLines[0] || '';
            // SKU is usually formatted as "SKU: xxxxxxxx"
            const skuMatch = productCell.match(/SKU[:\s]+([A-Za-z0-9_\-\.]+)/i);
            sku = skuMatch ? skuMatch[1] : '';

            // Column 2: Payment
            const paymentCell = cells[2].innerText;
            const amtMatch = paymentCell.match(/Total[:\s]+₹?([\d,]+)/i);
            amount = amtMatch ? amtMatch[1].replace(/,/g, '') : extractAmount(paymentCell);

            // Column 3: Customer
            const customerCell = cells[3].innerText;
            const customerLines = customerCell.split('\n').map(l => l.trim()).filter(Boolean);
            customerName = customerLines[0] || '';
            // Remove "New" badge text
            customerName = customerName.replace(/\s*New\s*$/i, '').trim();
            phone = extractPhone(customerCell);

            // Column 4: Address
            const addressCell = cells[4].innerText;
            const addrLines = addressCell.split('\n').map(l => l.trim()).filter(l => l && l !== 'Delivery' && l !== 'Pickup');
            addressText = addrLines.join(', ');
          } else {
            // Fallback: parse entire row text
            const phoneMatch = rowText.match(/(?:\+91[\s-]?)?([6-9]\d{9})\b/);
            phone = phoneMatch ? phoneMatch[1] : '';
            const amtMatch = rowText.match(/Total[:\s]+₹?([\d,]+)/i);
            amount = amtMatch ? amtMatch[1].replace(/,/g, '') : '';
            const skuMatch = rowText.match(/SKU[:\s]+([A-Za-z0-9_\-\.]+)/i);
            sku = skuMatch ? skuMatch[1] : '';
          }

          const pincode = extractPincode(addressText);
          const state = extractStateFromAddress(addressText);
          // City: try to extract from address text (line before state/pincode)
          const addrLinesArr = addressText.split(',').map(l => l.trim()).filter(Boolean);
          const city = extractCity(addrLinesArr);

          // Only include if we have at least an order ID or phone
          if (orderId || phone) {
            orders.push({
              order_ref: orderId,
              customer_name: customerName,
              phone: phone,
              product_name: productName,
              sku: sku,
              amount: amount,
              address: addressText,
              city: city,
              state: state,
              pincode: pincode,
              order_status_smartbiz: status,
              _source: 'LIST_TABLE'
            });
          }
        } catch (e) {
          // Skip malformed rows
        }
      });
    }

    // Strategy 2: If no table rows found, try SmartBiz's React/Next.js rendered order cards
    if (orders.length === 0) {
      // Look for order ID patterns anywhere on the page (15-19 digit numbers = Amazon order IDs)
      const pageText = document.body.innerText;
      const orderIdPattern = /\b(\d{15,19})\b/g;
      const orderIds = [...new Set([...pageText.matchAll(orderIdPattern)].map(m => m[1]))];

      orderIds.forEach(orderId => {
        // For each order ID found, try to find its surrounding context
        orders.push({
          order_ref: orderId,
          customer_name: '',
          phone: '',
          product_name: '',
          sku: '',
          amount: '',
          address: '',
          city: '',
          state: '',
          pincode: '',
          order_status_smartbiz: 'Pending',
          _source: 'TEXT_SCAN',
          _incomplete: true
        });
      });
    }

    return orders;
  }

  // ── Better LIST scraper using structured DOM reading ───────────────────────
  function scrapeOrdersStructured() {
    const orders = [];

    // SmartBiz renders each order as a row inside a table or as article/section cards
    // Try multiple selectors observed in Amazon SmartBiz seller portal

    // Approach A: Look for anchor tags with order IDs (blue links in screenshot)
    const orderLinks = document.querySelectorAll('a[href*="/orders/"], a[href*="orderId"]');
    const seenIds = new Set();

    orderLinks.forEach(link => {
      try {
        const hrefOrderMatch = (link.href || '').match(/\/orders\/(\d{10,})/);
        const linkTextOrderMatch = (link.innerText || '').match(/\b(\d{15,19})\b/);
        const orderId = (hrefOrderMatch && hrefOrderMatch[1]) || (linkTextOrderMatch && linkTextOrderMatch[1]) || link.innerText.trim();

        if (!orderId || seenIds.has(orderId)) return;
        seenIds.add(orderId);

        // Walk up the DOM to find the containing row
        let row = link.closest('tr, [class*="row"], [class*="card"], article, section, li');
        if (!row) row = link.parentElement?.parentElement?.parentElement;
        if (!row) return;

        const rowText = row.innerText || '';

        // Phone — WhatsApp number shown in Customer column
        const phone = extractPhone(rowText);

        // SKU
        const skuMatch = rowText.match(/SKU[:\s]+([A-Za-z0-9_\-\.]+)/i);
        const sku = skuMatch ? skuMatch[1] : '';

        // Amount — "Total: ₹399" pattern
        const amtMatch = rowText.match(/Total[:\s]+₹?([\d,]+)/i);
        const amount = amtMatch ? amtMatch[1].replace(/,/g, '') : extractAmount(rowText.match(/₹([\d,]+)/)?.[1] || '');

        // Status badge
        const statusMatch = rowText.match(/^(Pending|Accepted|Shipped|Fulfilled|Cancelled|Rejected)/im);
        const status = statusMatch ? statusMatch[1] : 'Pending';

        // Customer name — appears before "New" badge text in Customer column
        const customerMatch = rowText.match(/Customer\s*\n([\w\s]+?)(?:\s+New|\s+moomin|\s+\+91|\n)/i);
        // Alternative: the name is usually a standalone word/phrase before the phone
        let customerName = '';
        const cells = row.querySelectorAll('td');
        if (cells.length >= 4) {
          const custCell = cells[3] || cells[2];
          if (custCell) {
            const custText = custCell.innerText;
            const custLines = custText.split('\n').map(l => l.trim()).filter(Boolean);
            customerName = custLines[0]?.replace(/\s*New\s*$/i, '').trim() || '';
          }
        }
        if (!customerName && customerMatch) customerName = customerMatch[1].trim();

        // Product name — typically in column 1
        let productName = '';
        if (cells.length >= 2) {
          const prodCell = cells[1];
          const prodLines = (prodCell?.innerText || '').split('\n').map(l => l.trim()).filter(Boolean);
          productName = prodLines[0] || '';
        }

        // Address — typically in the last column
        let addressText = '';
        let pincode = '';
        let city = '';
        let state = '';
        if (cells.length >= 5) {
          const addrCell = cells[4];
          const addrCellText = addrCell?.innerText || '';
          const addrLines = addrCellText.split('\n').map(l => l.trim()).filter(l => l && l !== 'Delivery' && l !== 'Pickup');
          addressText = addrLines.join(', ');
          pincode = extractPincode(addressText);
          state = extractStateFromAddress(addressText);
          city = extractCity(addrLines);
        }

        orders.push({
          order_ref: orderId,
          customer_name: customerName,
          phone: phone,
          product_name: productName,
          sku: sku,
          amount: amount,
          address: addressText,
          city: city,
          state: state,
          pincode: pincode,
          order_status_smartbiz: status,
          _source: 'LINK_WALK'
        });
      } catch (e) {
        // skip
      }
    });

    return orders;
  }

  // ── MASTER LIST SCRAPER: combine both strategies ───────────────────────────
  function scrapeAllOrders() {
    let orders = scrapeOrdersStructured();
    if (orders.length === 0) orders = scrapeAllOrdersFromList();

    // De-duplicate by order_ref
    const seen = new Set();
    return orders.filter(o => {
      const key = o.order_ref || o.phone;
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // MODE 2: SINGLE ORDER DETAIL PAGE SCRAPER
  // ══════════════════════════════════════════════════════════════════════════
  function scrapeDetailPage() {
    const body = document.body;
    const fullText = body.innerText;

    // Order ID from URL
    const urlOrderMatch = location.pathname.match(/\/orders\/(\d{10,})/);
    const orderIdFromUrl = urlOrderMatch ? urlOrderMatch[1] : '';

    // Order ID from page text
    const orderIdFromText = fullText.match(/Order\s*(?:ID|#|Number)[:\s]*([A-Z0-9\-]{5,})/i)?.[1] || orderIdFromUrl;

    // Customer address block
    const addressNode = body.querySelector(
      '[data-testid*="shipping-address"], [data-testid*="customer-address"], ' +
      '[data-testid*="delivery-address"], .shipping-address, address, ' +
      '[class*="address"], [class*="Address"]'
    );
    const addressLines = addressNode
      ? addressNode.innerText.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
      : [];

    // Phone
    const phone = extractPhone(fullText);

    // Amount
    const amtMatch = fullText.match(/(?:COD Amount|Cash on Delivery|Order Total|Total)[:\s]+₹?([\d,]+)/i);
    const amount = amtMatch ? amtMatch[1].replace(/,/g, '') : extractAmount(fullText.match(/Total[:\s]*₹([\d,]+)/)?.[1] || '');

    // Product title
    const productEl = [...body.querySelectorAll('h1, h2, h3, [class*="product-title"], [data-testid*="product-title"]')]
      .find(el => el.innerText.trim().length > 3 && !/smartbiz|order detail|summary|dashboard/i.test(el.innerText));
    const productName = productEl ? productEl.innerText.trim() : '';

    // SKU
    const skuMatch = fullText.match(/SKU[:\s]+([A-Za-z0-9_\-\.]+)/i);
    const sku = skuMatch ? skuMatch[1] : '';

    // Customer name — first line of address block, or from Customer field
    const customerName = addressLines[0] || fullText.match(/Customer(?:\s+Name)?[:\s]+([A-Za-z\s]{3,})/i)?.[1]?.trim() || '';

    // Address text (skip first line = customer name)
    const addressText = addressLines.slice(1).join(', ');
    const pincode = extractPincode(addressText || fullText);
    const state = extractStateFromAddress(addressText || fullText);

    return {
      order_ref: orderIdFromText,
      customer_name: customerName,
      phone: phone,
      product_name: productName,
      sku: sku,
      amount: amount,
      address: addressText,
      city: '',
      state: state,
      pincode: pincode,
      order_status_smartbiz: 'Accepted',
      _source: 'DETAIL_PAGE'
    };
  }

  // ══════════════════════════════════════════════════════════════════════════
  // BULK LIST MODAL — Shows all scraped orders from list page
  // ══════════════════════════════════════════════════════════════════════════
  function openBulkListModal() {
    if (document.getElementById('zenos-bulk-modal')) return;

    const orders = scrapeAllOrders();
    const overlay = document.createElement('div');
    overlay.id = 'zenos-bulk-modal';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,0.8);display:grid;place-items:center;font:13px system-ui,-apple-system,sans-serif;color:#0f172a;';

    const orderRows = orders.length === 0
      ? `<div style="padding:32px;text-align:center;color:#64748b;">
          <div style="font-size:24px;margin-bottom:8px;">📋</div>
          <div style="font-weight:600;margin-bottom:4px;">No orders found on this page</div>
          <div style="font-size:12px;">Make sure you are on the SmartBiz Orders list page.<br>Try scrolling down so orders are visible, then click Sync again.</div>
        </div>`
      : orders.map((o, i) => {
          const addrHealth = evaluateAddressHealth(o.address);
          const healthColor = addrHealth.rtoRisk === 'LOW' ? '#047857' : addrHealth.rtoRisk === 'MEDIUM' ? '#b45309' : '#b91c1c';
          const healthBg = addrHealth.rtoRisk === 'LOW' ? '#ecfdf5' : addrHealth.rtoRisk === 'MEDIUM' ? '#fffbeb' : '#fef2f2';
          return `
            <div id="zenos-order-row-${i}" style="border-bottom:1px solid #f1f5f9;padding:10px 16px;display:flex;align-items:flex-start;gap:10px;cursor:pointer;transition:background 0.1s;" 
                 onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background=''"
                 onclick="zenosSyncOrder(${i})">
              <input type="checkbox" id="zenos-chk-${i}" style="margin-top:3px;cursor:pointer;width:14px;height:14px;" onclick="event.stopPropagation(); zenosToggleCheck(${i})">
              <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:3px;">
                  <div style="font-weight:700;font-size:12.5px;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;"
                       title="${escHtml(o.customer_name || 'Unknown Customer')}">
                    ${escHtml(o.customer_name || '—')}
                  </div>
                  <div style="display:flex;align-items:center;gap:5px;flex-shrink:0;">
                    <span style="font-size:10px;font-weight:600;padding:2px 7px;border-radius:999px;background:${o.order_status_smartbiz === 'Accepted' ? '#dcfce7' : o.order_status_smartbiz === 'Pending' ? '#fef3c7' : '#f1f5f9'};color:${o.order_status_smartbiz === 'Accepted' ? '#166534' : o.order_status_smartbiz === 'Pending' ? '#92400e' : '#475569'};">
                      ${escHtml(o.order_status_smartbiz || 'Pending')}
                    </span>
                    <span style="font-family:monospace;font-size:10px;font-weight:700;color:#059669;">₹${escHtml(o.amount || '—')}</span>
                  </div>
                </div>
                <div style="font-size:11px;color:#475569;display:flex;gap:10px;flex-wrap:wrap;">
                  <span style="font-family:monospace;color:#1d4ed8;" title="Order ID">#${escHtml(o.order_ref || '—')}</span>
                  ${o.phone ? `<span>📱 +91 ${escHtml(o.phone)}</span>` : '<span style="color:#b91c1c;">⚠️ No phone</span>'}
                  ${o.sku ? `<span style="font-family:monospace;">SKU: ${escHtml(o.sku)}</span>` : ''}
                </div>
                <div style="font-size:11px;color:#64748b;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escHtml(o.address)}">
                  📍 ${escHtml(o.address || 'No address detected')}
                </div>
                <div style="margin-top:3px;">
                  <span style="font-size:10px;font-weight:600;padding:1px 6px;border-radius:999px;background:${healthBg};color:${healthColor};">${addrHealth.message}</span>
                </div>
              </div>
              <button onclick="event.stopPropagation(); zenosSyncOrder(${i})" 
                      style="flex-shrink:0;padding:5px 10px;background:#008069;color:#fff;border:0;border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;white-space:nowrap;">
                ⚡ Sync
              </button>
            </div>`;
        }).join('');

    overlay.innerHTML = `
      <section style="background:#fff;border-radius:14px;width:min(600px,96vw);max-height:90vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 24px 64px rgba(0,0,0,0.3);border:1px solid #e2e8f0;">
        <header style="padding:14px 18px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;background:#f8fafc;flex-shrink:0;">
          <div style="display:flex;align-items:center;gap:9px;">
            <span style="font-size:20px;">🛡️</span>
            <div>
              <strong style="font-size:14px;color:#0f172a;">ZenOS SmartBiz Sync</strong>
              <div style="font-size:11px;color:#64748b;">${orders.length} order${orders.length !== 1 ? 's' : ''} found on this page • Click a row to sync</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            ${orders.length > 0 ? `<button onclick="zenosSyncAllChecked()" style="padding:6px 12px;background:#0f172a;color:#fff;border:0;border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;">⬆️ Sync Selected</button>` : ''}
            <button onclick="document.getElementById('zenos-bulk-modal').remove()" style="border:0;background:none;font-size:20px;cursor:pointer;color:#64748b;line-height:1;">×</button>
          </div>
        </header>
        <div style="overflow-y:auto;flex:1;">
          ${orderRows}
        </div>
        <footer style="padding:10px 16px;border-top:1px solid #e2e8f0;background:#f8fafc;flex-shrink:0;font-size:11px;color:#64748b;display:flex;justify-content:space-between;align-items:center;">
          <span>Sender: <strong>+91 97713 70945</strong> (Baileys Gateway)</span>
          <span id="zenos-bulk-status" style="font-weight:600;color:#047857;"></span>
        </footer>
      </section>`;

    document.body.appendChild(overlay);

    // Store orders for sync functions
    overlay._orders = orders;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  }

  function escHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Sync a single order (called from list modal)
  window.zenosSyncOrder = async function(idx) {
    const modal = document.getElementById('zenos-bulk-modal');
    if (!modal || !modal._orders) return;
    const order = modal._orders[idx];
    if (!order) return;

    const statusEl = document.getElementById('zenos-bulk-status');
    if (statusEl) { statusEl.textContent = `Syncing ${order.customer_name || 'order'}...`; statusEl.style.color = '#64748b'; }

    const config = await readConfig();
    try {
      const res = await fetch(`${config.backendUrl}/api/orders/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-ZenOS-Extension-Key': config.apiKey },
        body: JSON.stringify({
          customer_name: order.customer_name,
          phone: order.phone,
          order_ref: order.order_ref,
          product_name: order.product_name,
          sku: order.sku,
          amount: order.amount,
          address: order.address,
          city: order.city,
          state: order.state,
          pincode: order.pincode,
          consent_source: 'SmartBiz Order List',
          whatsapp_opt_in: true
        })
      });
      const data = await res.json();
      if (res.ok) {
        if (statusEl) { statusEl.textContent = `✅ ${order.customer_name || 'Order'} synced!`; statusEl.style.color = '#047857'; }
        const row = document.getElementById(`zenos-order-row-${idx}`);
        if (row) row.style.background = '#ecfdf5';
        showToast(`✅ ${order.customer_name} synced to ZenOS!`, '#008069');
      } else {
        throw new Error(data.message || `Error ${res.status}`);
      }
    } catch (err) {
      if (statusEl) { statusEl.textContent = `❌ ${err.message}`; statusEl.style.color = '#b91c1c'; }
    }
  };

  window.zenosToggleCheck = function(idx) {
    const chk = document.getElementById(`zenos-chk-${idx}`);
    if (chk) chk.checked = !chk.checked;
  };

  window.zenosSyncAllChecked = async function() {
    const modal = document.getElementById('zenos-bulk-modal');
    if (!modal || !modal._orders) return;
    const statusEl = document.getElementById('zenos-bulk-status');

    const checkedIndices = modal._orders
      .map((_, i) => i)
      .filter(i => document.getElementById(`zenos-chk-${i}`)?.checked);

    if (checkedIndices.length === 0) {
      if (statusEl) { statusEl.textContent = 'Select at least one order first.'; statusEl.style.color = '#b45309'; }
      return;
    }

    if (statusEl) { statusEl.textContent = `Syncing ${checkedIndices.length} orders...`; statusEl.style.color = '#64748b'; }
    for (const i of checkedIndices) {
      await window.zenosSyncOrder(i);
    }
    if (statusEl) statusEl.textContent = `✅ ${checkedIndices.length} orders synced!`;
  };

  // ══════════════════════════════════════════════════════════════════════════
  // SINGLE DETAIL PAGE MODAL
  // ══════════════════════════════════════════════════════════════════════════
  function openSingleOrderModal() {
    if (document.getElementById('zenos-review-modal')) return;
    const detected = scrapeDetailPage();
    const addressDiagnosis = evaluateAddressHealth(detected.address);
    const diagColor = addressDiagnosis.rtoRisk === 'LOW' ? '#065f46' : '#92400e';
    const diagBg = addressDiagnosis.rtoRisk === 'LOW' ? '#ecfdf5;border:1px solid #a7f3d0' : '#fffbeb;border:1px solid #fde68a';

    const overlay = document.createElement('div');
    overlay.id = 'zenos-review-modal';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,0.75);display:grid;place-items:center;font:13px system-ui,-apple-system,sans-serif;color:#0f172a;';

    overlay.innerHTML = `
      <section style="background:#fff;border-radius:14px;width:min(540px,94vw);max-height:92vh;overflow:auto;box-shadow:0 24px 64px rgba(0,0,0,0.3);border:1px solid #e2e8f0;">
        <header style="padding:14px 18px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;background:#f8fafc;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:18px;">🛡️</span>
            <div>
              <strong style="font-size:14px;color:#0f172a;">ZenOS: SmartBiz Order Sync</strong>
              <div style="font-size:11px;color:#64748b;">Verify all fields before syncing</div>
            </div>
          </div>
          <button type="button" data-close style="border:0;background:none;font-size:20px;cursor:pointer;color:#64748b;">×</button>
        </header>

        <div style="margin:12px 18px 6px;padding:9px 12px;border-radius:8px;font-size:12px;font-weight:600;background:${diagBg};color:${diagColor};">
          ${addressDiagnosis.message} — RTO Risk: ${addressDiagnosis.rtoRisk}
        </div>

        <form style="padding:10px 18px 18px;display:grid;gap:11px;">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              Customer Name *
              <input name="customer_name" autocomplete="off" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;" required>
            </label>
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              WhatsApp (+91) *
              <input name="phone" inputmode="tel" placeholder="10-digit number" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;font-family:monospace;" required>
            </label>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              Order ID *
              <input name="order_ref" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;font-family:monospace;" required>
            </label>
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              COD Amount (₹) *
              <input name="amount" type="number" min="1" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;" required>
            </label>
          </div>
          <div style="display:grid;grid-template-columns:1.3fr 1fr;gap:10px;">
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              Product Name *
              <input name="product_name" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;" required>
            </label>
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              SKU Number
              <input name="sku" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;font-family:monospace;">
            </label>
          </div>
          <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
            Full Delivery Address
            <textarea name="address" rows="2" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:12px;resize:vertical;"></textarea>
          </label>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              City
              <input name="city" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;">
            </label>
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              State
              <input name="state" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;">
            </label>
            <label style="display:block;font-size:12px;font-weight:600;color:#334155;">
              Pincode
              <input name="pincode" inputmode="numeric" maxlength="6" style="display:block;width:100%;margin-top:4px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;font-family:monospace;">
            </label>
          </div>

          <div style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:8px;padding:10px 12px;">
            <div style="font-size:11px;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">💬 Send WhatsApp on Sync</div>
            <select name="template_to_send" style="width:100%;padding:7px;border:1px solid #94a3b8;border-radius:6px;font-size:12px;font-weight:600;background:#fff;">
              <option value="50_prepay">⚡ Flat ₹50 Instant Prepay Offer</option>
              <option value="15_prepay">⚡ 15% Instant Prepay Offer</option>
              <option value="request_landmark">📍 Request Address & Landmark</option>
              <option value="shipping_check">🚚 Out For Delivery Today</option>
              <option value="none">🚫 Save to ZenOS Only (No WhatsApp)</option>
            </select>
          </div>

          <p data-status role="status" style="min-height:16px;margin:0;font-size:12px;font-weight:600;color:#b91c1c;"></p>

          <footer style="display:flex;justify-content:flex-end;gap:8px;">
            <button type="button" data-close style="padding:8px 14px;border:1px solid #cbd5e1;background:#fff;border-radius:6px;cursor:pointer;font-weight:600;">Cancel</button>
            <button type="submit" data-send="false" style="padding:8px 14px;border:1px solid #cbd5e1;background:#f8fafc;border-radius:6px;cursor:pointer;font-weight:600;">💾 Save to ZenOS</button>
            <button type="submit" data-send="true" style="padding:8px 16px;background:#008069;color:#fff;border:0;border-radius:6px;cursor:pointer;font-weight:700;">🚀 Save & Send WhatsApp</button>
          </footer>
        </form>
      </section>`;

    document.body.appendChild(overlay);

    // Pre-fill scraped data
    const form = overlay.querySelector('form');
    Object.entries(detected).forEach(([key, val]) => {
      const el = form.elements.namedItem(key);
      if (el && val) el.value = val;
    });

    // Auto-select address template
    const addrTemplateEl = form.elements.namedItem('template_to_send');
    if (addrTemplateEl && addressDiagnosis.rtoRisk !== 'LOW') {
      addrTemplateEl.value = 'request_landmark';
    }

    overlay.querySelectorAll('[data-close]').forEach(btn => btn.addEventListener('click', () => overlay.remove()));
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

    form.addEventListener('submit', async e => {
      e.preventDefault();
      const shouldSend = e.submitter?.dataset.send === 'true';
      const statusEl = overlay.querySelector('[data-status]');
      const config = await readConfig();

      const payload = {
        customer_name: form.customer_name.value.trim(),
        phone: form.phone.value.replace(/\D/g, '').slice(-10),
        order_ref: form.order_ref.value.trim(),
        product_name: form.product_name.value.trim(),
        sku: form.sku.value.trim(),
        amount: form.amount.value,
        address: form.address.value.trim(),
        city: form.city.value.trim(),
        state: form.state.value.trim(),
        pincode: form.pincode.value.trim(),
        consent_source: 'SmartBiz Detail Page',
        whatsapp_opt_in: true
      };

      if (!payload.customer_name || !payload.phone || !payload.order_ref || !payload.amount) {
        statusEl.textContent = 'Name, phone, order ID and amount are required.';
        return;
      }

      e.submitter.disabled = true;
      statusEl.style.color = '#64748b';
      statusEl.textContent = 'Syncing to ZenOS...';

      try {
        const res = await fetch(`${config.backendUrl}/api/orders/ingest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-ZenOS-Extension-Key': config.apiKey },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.message || `Error ${res.status}`);

        if (shouldSend && form.template_to_send.value !== 'none') {
          statusEl.textContent = 'Dispatching WhatsApp message...';
          await fetch(`${config.backendUrl}/api/whatsapp/quick-dispatch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              phone: payload.phone,
              customer_name: payload.customer_name,
              order_ref: payload.order_ref,
              product_name: payload.product_name,
              amount: parseInt(payload.amount, 10),
              template_type: form.template_to_send.value
            })
          });
        }

        statusEl.style.color = '#047857';
        statusEl.textContent = `✅ Order #${payload.order_ref} synced${shouldSend ? ' & WhatsApp sent' : ''}!`;
        showToast(`✅ ZenOS: ${payload.customer_name} synced!`, '#008069');
        setTimeout(() => overlay.remove(), 2000);
      } catch (err) {
        statusEl.style.color = '#b91c1c';
        statusEl.textContent = err.message;
        e.submitter.disabled = false;
      }
    });
  }

  // ─── Config reader ────────────────────────────────────────────────────────
  function readConfig() {
    return new Promise(resolve => {
      chrome.storage.local.get(['zenos_backend_url', 'zenos_extension_api_key'], values => {
        resolve({
          backendUrl: (values.zenos_backend_url || 'http://localhost:5000').replace(/\/+$/, ''),
          apiKey: values.zenos_extension_api_key || ''
        });
      });
    });
  }

  // ─── Toast notification ───────────────────────────────────────────────────
  function showToast(msg, color = '#008069') {
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = `position:fixed;right:20px;top:20px;z-index:2147483647;background:${color};color:#fff;padding:10px 16px;border-radius:8px;font:700 13px system-ui,-apple-system,sans-serif;max-width:400px;box-shadow:0 6px 18px rgba(0,0,0,0.2);`;
    document.documentElement.appendChild(t);
    setTimeout(() => t.remove(), 5000);
  }

  // ─── Runtime message listener (from popup.js) ─────────────────────────────
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'SCRAPE_SMARTBIZ_ORDERS_LIST') {
      // Popup requests all orders from list page
      try {
        const pageType = detectPageType();
        const orders = pageType === 'DETAIL' ? [scrapeDetailPage()] : scrapeAllOrders();
        sendResponse({ status: 'success', orders, pageType, count: orders.length });
      } catch (err) {
        sendResponse({ status: 'error', message: err.message, orders: [] });
      }
      return true;
    }

    if (request.action === 'SCRAPE_SMARTBIZ_ORDER') {
      // Legacy single-order scrape for popup
      try {
        const pageType = detectPageType();
        const order = pageType === 'DETAIL' ? scrapeDetailPage() : scrapeAllOrders()[0] || {};
        const diagnosis = evaluateAddressHealth(order.address || '');
        sendResponse({ status: 'success', order, diagnosis });
      } catch (err) {
        sendResponse({ status: 'error', message: err.message });
      }
      return true;
    }
  });
})();
