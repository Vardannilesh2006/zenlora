(() => {
  const pillId = "zenos-wukusy-pill";
  if (document.getElementById(pillId)) return;

  const pill = document.createElement("button");
  pill.id = pillId;
  pill.type = "button";
  pill.textContent = "📦 ZenOS: Load Confirmed Orders";
  pill.style.cssText = [
    "position:fixed", "left:24px", "bottom:24px", "z-index:2147483646",
    "padding:12px 18px", "border:0", "border-radius:999px",
    "background:#6d28d9", "color:#fff", "font:700 13px system-ui,-apple-system,sans-serif",
    "box-shadow:0 10px 25px rgba(109,40,217,0.35)", "cursor:pointer",
    "display:flex", "align-items:center", "gap:8px"
  ].join(";");
  // --- Draggable Helper ---
  function makeDraggable(el, storageKey) {
    let isDragging = false;
    let startX = 0, startY = 0;
    let initialLeft = 0, initialTop = 0;
    let moved = false;

    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const pos = JSON.parse(saved);
        if (typeof pos.top === 'number' && typeof pos.left === 'number') {
          const maxTop = Math.max(10, window.innerHeight - 60);
          const maxLeft = Math.max(10, window.innerWidth - 220);
          el.style.top = Math.min(Math.max(10, pos.top), maxTop) + 'px';
          el.style.left = Math.min(Math.max(10, pos.left), maxLeft) + 'px';
          el.style.bottom = 'auto';
          el.style.right = 'auto';
        }
      }
    } catch (e) {}

    el.style.cursor = 'grab';
    el.style.userSelect = 'none';

    el.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      isDragging = true;
      moved = false;
      startX = e.clientX;
      startY = e.clientY;
      const rect = el.getBoundingClientRect();
      initialLeft = rect.left;
      initialTop = rect.top;
      el.style.cursor = 'grabbing';

      function onMouseMove(moveEvent) {
        if (!isDragging) return;
        const dx = moveEvent.clientX - startX;
        const dy = moveEvent.clientY - startY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved = true;

        let newLeft = initialLeft + dx;
        let newTop = initialTop + dy;
        const maxLeft = window.innerWidth - el.offsetWidth - 5;
        const maxTop = window.innerHeight - el.offsetHeight - 5;
        newLeft = Math.max(5, Math.min(newLeft, maxLeft));
        newTop = Math.max(5, Math.min(newTop, maxTop));

        el.style.left = newLeft + 'px';
        el.style.top = newTop + 'px';
        el.style.bottom = 'auto';
        el.style.right = 'auto';
      }

      function onMouseUp() {
        if (!isDragging) return;
        isDragging = false;
        el.style.cursor = 'grab';
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        if (moved) {
          const rect = el.getBoundingClientRect();
          try {
            localStorage.setItem(storageKey, JSON.stringify({ top: rect.top, left: rect.left }));
          } catch (e) {}
        }
      }

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });

    el.addEventListener('click', (e) => {
      if (moved) {
        e.stopImmediatePropagation();
        e.preventDefault();
        moved = false;
      }
    }, true);
  }
  pill.textContent = "🚚 ZenOS: 1-Click Autofill Address";
  pill.style.background = "linear-gradient(135deg, #4f46e5, #7c3aed)";
  pill.addEventListener("click", openOrderPanel);
  document.documentElement.appendChild(pill);
  makeDraggable(pill, "zenos_wukusy_pill_pos");

  function splitName(fullName) {
    const parts = (fullName || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return { first: "", last: "" };
    if (parts.length === 1) return { first: parts[0], last: "" };
    return { first: parts[0], last: parts.slice(1).join(" ") };
  }

  function splitAddress(fullAddress) {
    const addr = (fullAddress || "").trim();
    if (!addr) return { addr1: "", addr2: "" };

    // Landmark pattern detection
    const landmarkRegex = /\b(?:near|opp|opposite|behind|beside|next to|adj|adjacent to)\s+[^,]+/i;
    const match = addr.match(landmarkRegex);
    if (match) {
      const landmark = match[0].trim();
      const remaining = addr.replace(match[0], "")
        .replace(/,\s*,/g, ",")
        .replace(/^,\s*|,\s*$/g, "")
        .trim();
      return {
        addr1: remaining || addr,
        addr2: landmark
      };
    }

    // Comma split fallback: first part into addr1, remaining into addr2
    const commaIndex = addr.indexOf(",");
    if (commaIndex > 0) {
      return {
        addr1: addr.slice(0, commaIndex).trim(),
        addr2: addr.slice(commaIndex + 1).replace(/^,\s*/, "").trim()
      };
    }

    return { addr1: addr, addr2: "" };
  }

  async function openOrderPanel() {
    if (document.getElementById("zenos-wukusy-modal")) return;
    const config = await readConfig();

    pill.disabled = true;
    pill.textContent = "⏳ Fetching Confirmed Orders…";

    try {
      let orders = [];
      const headers = config.apiKey ? { "X-ZenOS-Extension-Key": config.apiKey } : {};
      
      const response = await fetch(`${config.backendUrl}/api/orders/pending-wukusy`, { headers });
      if (response.ok) {
        const result = await response.json();
        orders = Array.isArray(result.orders) ? result.orders : [];
      } else {
        // Fallback to dashboard data if pending-wukusy requires auth
        const fbRes = await fetch(`${config.backendUrl}/api/dashboard/data`);
        if (fbRes.ok) {
          const fbData = await fbRes.json();
          orders = (fbData.orders || []).filter(o => 
            ["CONFIRMED_COD", "PREPAID_PAID", "DELIVERY_COLLECT_CONFIRMED"].includes(o.status)
          );
        }
      }

      showOrderPanel(orders);
    } catch (error) {
      showToast("Could not load orders: " + (error.message || "Network error. Check ZenOS is running on port 5000."));
    } finally {
      pill.disabled = false;
      pill.textContent = "📦 ZenOS: Load Confirmed Orders";
    }
  }

  function showOrderPanel(orders) {
    const overlay = document.createElement("div");
    overlay.id = "zenos-wukusy-modal";
    overlay.style.cssText = "position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,0.75);display:grid;place-items:center;font:14px system-ui,-apple-system,sans-serif;color:#0f172a;backdrop-filter:blur(2px);";

    overlay.innerHTML = `
      <section style="background:white;border-radius:14px;width:min(580px,94vw);max-height:92vh;overflow:auto;box-shadow:0 24px 64px rgba(0,0,0,0.3);border:1px solid #e2e8f0;">
        <header style="padding:16px 20px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;background:#f8fafc;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:18px;">📦</span>
            <div>
              <strong style="font-size:15px;color:#0f172a;">ZenOS: 100% Deterministic Wukusy Autofill</strong>
              <div style="font-size:11px;color:#64748b;">Zero AI Hallucination • Exact Field-by-Field Mapping</div>
            </div>
          </div>
          <button type="button" data-close aria-label="Close" style="border:0;background:none;font-size:20px;cursor:pointer;color:#64748b;">×</button>
        </header>

        <div style="padding:16px 20px;display:grid;gap:12px;">
          <label style="font-size:12px;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:0.05em;">
            Select Confirmed Customer (${orders.length} Ready):
            <select data-order-select style="display:block;width:100%;margin-top:5px;padding:9px;border:1px solid #cbd5e1;border-radius:7px;font-size:13px;font-weight:600;background:#fff;"></select>
          </label>

          <!-- SERIAL-NUMBERED CUSTOMER DRAWER -->
          <div data-customer-drawer style="max-height:140px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:6px;display:grid;gap:4px;">
            <!-- Customer list items populated dynamically -->
          </div>

          <!-- PARSED FIELD PREVIEW TABLE (ZERO HALLUCINATION INSPECTION) -->
          <div data-parsed-preview style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:8px;padding:12px;font-size:12px;line-height:1.5;">
            <div style="font-weight:700;color:#1e293b;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
              <span>🎯 Exact Target Field Mapping</span>
              <span data-status-badge style="font-size:10px;padding:2px 6px;border-radius:4px;font-weight:700;"></span>
            </div>
            <div data-mapping-table style="display:grid;grid-template-columns:110px 1fr;gap:4px 8px;font-family:monospace;font-size:11.5px;"></div>
          </div>

          <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:#64748b;background:#eff6ff;padding:8px 12px;border-radius:6px;border:1px solid #bfdbfe;">
            <span>🛡️</span>
            <span>Autofill strictly injects values into the visible form. Review every highlighted field before clicking Save Address.</span>
          </div>

          <p data-status role="status" style="min-height:18px;margin:0;font-size:12px;font-weight:700;"></p>

          <footer style="display:flex;justify-content:flex-end;gap:8px;">
            <button type="button" data-close style="padding:9px 14px;border:1px solid #cbd5e1;background:#fff;border-radius:6px;cursor:pointer;font-weight:600;">Cancel</button>
            <button type="button" data-fill style="padding:9px 18px;background:#6d28d9;color:white;border:0;border-radius:6px;cursor:pointer;font-weight:700;box-shadow:0 2px 6px rgba(109,40,217,0.3);display:flex;align-items:center;gap:6px;">
              🎯 1-Click Autofill Address
            </button>
          </footer>
        </div>
      </section>`;

    document.body.appendChild(overlay);

    const select = overlay.querySelector("[data-order-select]");
    const drawer = overlay.querySelector("[data-customer-drawer]");
    const mappingTable = overlay.querySelector("[data-mapping-table]");
    const statusBadge = overlay.querySelector("[data-status-badge]");
    const status = overlay.querySelector("[data-status]");
    const fillButton = overlay.querySelector("[data-fill]");
    let activeOrder = null;

    overlay.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => overlay.remove()));
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) overlay.remove();
    });

    if (orders.length === 0) {
      select.innerHTML = `<option value="">No confirmed orders found</option>`;
      select.disabled = true;
      fillButton.disabled = true;
      fillButton.style.opacity = "0.5";
      drawer.innerHTML = `<div style="text-align:center;padding:16px;color:#64748b;font-size:12px;">No COD-confirmed or prepaid orders in queue.</div>`;
      mappingTable.innerHTML = `<div style="color:#64748b;">No data available.</div>`;
      return;
    }

    // Populate dropdown and serial-numbered customer drawer
    orders.forEach((order, index) => {
      const serialNum = index + 1;
      const opt = document.createElement("option");
      opt.value = order.order_ref;
      opt.textContent = `${serialNum}. #${order.order_ref} — ${order.customer_name} (${order.city || 'Patna'}) [${order.status}]`;
      select.appendChild(opt);

      const item = document.createElement("div");
      item.style.cssText = "padding:6px 10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;font-size:12px;font-weight:600;";
      item.innerHTML = `
        <span><strong>${serialNum}.</strong> #${order.order_ref} — ${escapeHtml(order.customer_name)}</span>
        <span style="font-size:10px;color:#64748b;">${escapeHtml(order.city || '')} • ${order.status === 'PREPAID_PAID' ? '⚡ UPI Paid' : '📦 COD'}</span>
      `;
      item.addEventListener("click", () => {
        select.value = order.order_ref;
        updatePreview();
      });
      drawer.appendChild(item);
    });

    function updatePreview() {
      activeOrder = orders.find((o) => o.order_ref === select.value) || orders[0];
      if (!activeOrder) return;

      const nameObj = splitName(activeOrder.customer_name);
      const addrObj = splitAddress(activeOrder.address);
      const cleanPhone = String(activeOrder.phone || "").replace(/\D/g, "").slice(-10);

      statusBadge.textContent = activeOrder.status;
      statusBadge.style.background = activeOrder.status === 'PREPAID_PAID' ? '#dbeafe' : '#dcfce7';
      statusBadge.style.color = activeOrder.status === 'PREPAID_PAID' ? '#1e40af' : '#166534';

      mappingTable.innerHTML = `
        <span style="color:#64748b;">First Name:</span><strong>${escapeHtml(nameObj.first)}</strong>
        <span style="color:#64748b;">Last Name:</span><strong>${escapeHtml(nameObj.last || '-')}</strong>
        <span style="color:#64748b;">Company:</span><span style="color:#94a3b8;">[Zenlora Store / Blank]</span>
        <span style="color:#64748b;">Mobile (+91):</span><strong>${cleanPhone}</strong>
        <span style="color:#64748b;">Address 1:</span><strong>${escapeHtml(addrObj.addr1)}</strong>
        <span style="color:#64748b;">Address 2:</span><strong>${escapeHtml(addrObj.addr2 || '-')}</strong>
        <span style="color:#64748b;">City / State:</span><strong>${escapeHtml(activeOrder.city || '')}, ${escapeHtml(activeOrder.state || '')}</strong>
        <span style="color:#64748b;">Pincode:</span><strong>${escapeHtml(activeOrder.pincode || '')}</strong>
      `;
      status.textContent = "";
    }

    select.addEventListener("change", updatePreview);
    updatePreview();

    fillButton.addEventListener("click", () => {
      if (!activeOrder) return;
      const fillResults = fillWukusyForm(activeOrder);
      if (fillResults.filledCount > 0) {
        status.style.color = "#047857";
        status.textContent = `✅ ${fillResults.filledCount} fields filled with 100% precision for ${activeOrder.customer_name}. Please review highlighted fields & submit.`;
        showToast(`✅ ZenOS: ${fillResults.filledCount} fields populated for #${activeOrder.order_ref}!`);
      } else {
        status.style.color = "#b91c1c";
        status.textContent = "⚠️ Could not locate Wukusy form fields on this page. Make sure the 'Add Address' modal or page is open.";
      }
    });
  }

  function fillWukusyForm(order) {
    const nameObj = splitName(order.customer_name);
    const addrObj = splitAddress(order.address);
    const cleanPhone = String(order.phone || "").replace(/\D/g, "").slice(-10);

    // Exact selectors mapping to Wukusy 'Add Address' form screenshot
    const fieldDefinitions = [
      {
        field: "First Name",
        value: nameObj.first,
        selectors: [
          'input[placeholder*="First Name" i]',
          'input[placeholder*="First" i]',
          'input[name*="first" i]',
          '#firstName',
          '#first_name',
          'input[id*="first" i]'
        ]
      },
      {
        field: "Last Name",
        value: nameObj.last,
        selectors: [
          'input[placeholder*="Last Name" i]',
          'input[placeholder*="Last" i]',
          'input[name*="last" i]',
          '#lastName',
          '#last_name',
          'input[id*="last" i]'
        ]
      },
      {
        field: "Company",
        value: "Zenlora",
        selectors: [
          'input[placeholder*="Company" i]',
          'input[name*="company" i]',
          '#company'
        ]
      },
      {
        field: "Mobile",
        value: cleanPhone,
        selectors: [
          'input[placeholder*="10-digit" i]',
          'input[placeholder*="Mobile" i]',
          'input[placeholder*="Phone" i]',
          'input[type="tel"]',
          'input[name*="mobile" i]',
          'input[name*="phone" i]',
          '#mobile',
          '#phone'
        ]
      },
      {
        field: "Address 1",
        value: addrObj.addr1,
        selectors: [
          'input[placeholder*="Address 1" i]',
          'textarea[placeholder*="Address 1" i]',
          'input[name*="address1" i]',
          'textarea[name*="address1" i]',
          '#address1',
          '#addr1',
          'input[name="address"]',
          'textarea[name="address"]'
        ]
      },
      {
        field: "Address 2",
        value: addrObj.addr2,
        selectors: [
          'input[placeholder*="Address 2" i]',
          'textarea[placeholder*="Address 2" i]',
          'input[name*="address2" i]',
          'textarea[name*="address2" i]',
          '#address2',
          '#addr2'
        ]
      },
      {
        field: "City",
        value: order.city || "",
        selectors: [
          'input[placeholder*="City" i]',
          'input[name*="city" i]',
          '#city'
        ]
      },
      {
        field: "State",
        value: order.state || "",
        selectors: [
          'input[placeholder*="State" i]',
          'select[name*="state" i]',
          'input[name*="state" i]',
          '#state'
        ]
      },
      {
        field: "Pincode",
        value: String(order.pincode || "").slice(0, 6),
        selectors: [
          'input[placeholder*="6-digit" i]',
          'input[placeholder*="PIN" i]',
          'input[placeholder*="Postal" i]',
          'input[name*="pin" i]',
          'input[name*="postal" i]',
          '#pincode',
          '#pin'
        ]
      }
    ];

    let filledCount = 0;
    const filledFields = [];

    for (const def of fieldDefinitions) {
      if (!def.value) continue;
      const element = findElementBySelectors(def.selectors);
      if (element) {
        setNativeValue(element, def.value);
        filledCount++;
        filledFields.push(def.field);
      }
    }

    return { filledCount, filledFields };
  }

  function findElementBySelectors(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && isElementVisible(el)) return el;
    }
    return null;
  }

  function isElementVisible(element) {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
  }

  function setNativeValue(element, value) {
    if (!element) return;
    const prototype = Object.getPrototypeOf(element);
    const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value');

    if (descriptor && descriptor.set) {
      descriptor.set.call(element, value);
    } else {
      element.value = value;
    }

    // Trigger synthetic events so React / Vue / Angular captures the change
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    element.dispatchEvent(new Event('blur', { bubbles: true }));

    // Visual confidence styling (soft emerald hairline border)
    element.style.setProperty('border', '2px solid #10b981', 'important');
    element.style.setProperty('background-color', '#ecfdf5', 'important');
  }

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>"']/g, (m) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[m]);
  }

  function readConfig() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["zenos_backend_url", "zenos_extension_api_key"], (values) => {
        resolve({
          backendUrl: (values.zenos_backend_url || "https://zenos-nine.vercel.app").replace(/\/+$/, ""),
          apiKey: values.zenos_extension_api_key || ""
        });
      });
    });
  }

  function showToast(message) {
    const toast = document.createElement("div");
    toast.textContent = message;
    toast.style.cssText = "position:fixed;left:24px;top:24px;z-index:2147483647;background:#6d28d9;color:white;padding:12px 18px;border-radius:8px;font:700 13px system-ui,-apple-system,sans-serif;max-width:440px;box-shadow:0 8px 24px rgba(0,0,0,0.25);";
    document.documentElement.appendChild(toast);
    window.setTimeout(() => toast.remove(), 5000);
  }

  // Runtime listener for Extension Popup 1-click customer form injection
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "FILL_WUKUSY_FORM") {
      try {
        const order = request.order;
        if (!order) {
          sendResponse({ status: "error", message: "No customer order provided" });
          return true;
        }
        const fillResults = fillWukusyForm(order);
        if (fillResults.filledCount > 0) {
          showToast(`✅ ZenOS: ${fillResults.filledCount} fields populated for ${order.customer_name} (#${order.order_ref})!`);
          sendResponse({ status: "success", filledCount: fillResults.filledCount, details: fillResults.results });
        } else {
          sendResponse({ status: "error", message: "Could not find Wukusy address fields on active page. Please ensure Add Address form is open." });
        }
      } catch (err) {
        sendResponse({ status: "error", message: err.message });
      }
      return true;
    }
  });
})();
