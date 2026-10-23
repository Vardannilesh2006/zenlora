document.addEventListener("DOMContentLoaded", () => {
  const backendField = document.getElementById("backend-url");
  const keyField = document.getElementById("extension-key");
  const configStatus = document.getElementById("config-status");
  const defaultUrl = "http://localhost:5000";

  let activeScrapedOrder = null;
  let scrapedOrdersSession = [];
  let confirmedOrdersCache = [];
  let extPendingAiButtons = [];

  // ==================== 1. MAIN APPLE TAB SWITCHING ====================
  window.switchTab = function(tabName) {
    document.querySelectorAll(".segment-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".page-content").forEach(p => p.classList.remove("active"));

    const targetBtn = document.getElementById(`btn-tab-${tabName}`);
    const targetPage = document.getElementById(`page-${tabName}`);
    if (targetBtn) targetBtn.classList.add("active");
    if (targetPage) targetPage.classList.add("active");

    if (tabName === "wukusy") {
      loadWukusyOrders();
    } else if (tabName === "whatsapp") {
      renderAiPreview();
    }
  };

  // WhatsApp Sub-Tabs
  window.switchWaSub = function(subName) {
    const btnReg = document.getElementById("wa-btn-reg");
    const btnAi = document.getElementById("wa-btn-ai");
    const viewReg = document.getElementById("wa-view-reg");
    const viewAi = document.getElementById("wa-view-ai");

    if (subName === "reg") {
      btnReg.classList.add("active");
      btnAi.classList.remove("active");
      viewReg.style.display = "block";
      viewAi.style.display = "none";
    } else {
      btnAi.classList.add("active");
      btnReg.classList.remove("active");
      viewReg.style.display = "none";
      viewAi.style.display = "block";
      renderAiPreview();
    }
  };

  // Load Saved Configuration
  chrome.storage.local.get(["zenos_backend_url", "zenos_extension_api_key", "zenos_scraped_history"], (config) => {
    backendField.value = config.zenos_backend_url || defaultUrl;
    keyField.value = config.zenos_extension_api_key || "";
    scrapedOrdersSession = config.zenos_scraped_history || [];
    renderScrapedList();
    checkBackendHealth();
  });

  // Save Settings
  document.getElementById("save-config-btn").addEventListener("click", () => {
    const backendUrl = backendField.value.trim().replace(/\/+$/, "");
    const apiKey = keyField.value.trim();
    chrome.storage.local.set({
      zenos_backend_url: backendUrl,
      zenos_extension_api_key: apiKey
    }, () => {
      configStatus.textContent = "Settings saved!";
      configStatus.style.color = "#047857";
      checkBackendHealth();
    });
  });

  async function checkBackendHealth() {
    const activeUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;
    const status = document.getElementById("server-status");
    try {
      const res = await fetch(`${activeUrl}/api/health`);
      if (res.ok) {
        status.innerHTML = `<span style="width:5px; height:5px; border-radius:50%; background:#10b981;"></span><span>ONLINE</span>`;
      } else {
        status.innerHTML = `<span style="width:5px; height:5px; border-radius:50%; background:#f59e0b;"></span><span>READY</span>`;
      }
    } catch {
      status.innerHTML = `<span style="width:5px; height:5px; border-radius:50%; background:#ef4444;"></span><span>OFFLINE</span>`;
    }
  }

  // ==================== PAGE 1: AMAZON SMARTBIZ SCRAPER (MULTI-ORDER LIST) ====================
  // Scrapes ALL visible orders from the SmartBiz orders list page in one click
  let scrapedOrdersList = []; // holds all scraped orders from current page

  document.getElementById("btn-scrape-active-tab").addEventListener("click", () => {
    const statusMsg = document.getElementById("scrape-status");
    statusMsg.style.color = "#64748b";
    statusMsg.textContent = "Scanning SmartBiz orders page…";

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs[0]) {
        statusMsg.style.color = "#b91c1c";
        statusMsg.textContent = "No active browser tab found.";
        return;
      }

      const tabUrl = tabs[0].url || "";
      const isSmartBiz = tabUrl.includes("smartbiz.amazon.in");
      if (!isSmartBiz) {
        statusMsg.style.color = "#b91c1c";
        statusMsg.textContent = "⚠️ Please open your SmartBiz Orders page first, then click Scrape.";
        return;
      }

      // First ensure content script is injected (in case it wasn't auto-injected)
      chrome.scripting.executeScript({
        target: { tabId: tabs[0].id },
        files: ["smartbiz_bridge.js"]
      }).catch(() => {}); // Already injected = OK, ignore error

      setTimeout(() => {
        chrome.tabs.sendMessage(tabs[0].id, { action: "SCRAPE_SMARTBIZ_ORDERS_LIST" }, (response) => {
          if (chrome.runtime.lastError) {
            statusMsg.style.color = "#b91c1c";
            statusMsg.textContent = "⚠️ Could not connect to SmartBiz page. Try refreshing it.";
            return;
          }

          if (!response || response.status !== "success") {
            statusMsg.style.color = "#b91c1c";
            statusMsg.textContent = response?.message || "No orders found. Make sure SmartBiz Orders list is open.";
            return;
          }

          scrapedOrdersList = response.orders || [];
          const count = scrapedOrdersList.length;

          if (count === 0) {
            statusMsg.style.color = "#b45309";
            statusMsg.textContent = "No orders detected on screen. Scroll to load orders, then retry.";
            return;
          }

          statusMsg.style.color = "#047857";
          statusMsg.textContent = `✅ ${count} order${count !== 1 ? "s" : ""} found on screen!`;

          // If single order, also set activeScrapedOrder for legacy compat
          if (count >= 1) activeScrapedOrder = scrapedOrdersList[0];

          renderScrapedList();
        });
      }, 500); // small delay to ensure script injected
    });
  });

  // Sync a specific order from the scraped list
  window.syncScrapedOrderByIndex = async function(idx) {
    const order = scrapedOrdersList[idx];
    if (!order) return;
    const btn = document.getElementById(`btn-sync-scraped-${idx}`);
    const statusMsg = document.getElementById("scrape-status");
    if (btn) { btn.disabled = true; btn.textContent = "⏳…"; }

    const backendUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;
    const apiKey = keyField.value.trim();

    try {
      const headers = { "Content-Type": "application/json" };
      if (apiKey) headers["X-ZenOS-Extension-Key"] = apiKey;

      const payload = {
        customer_name: order.customer_name,
        phone: (order.phone || "").replace(/\D/g, "").slice(-10),
        order_ref: order.order_ref,
        product_name: order.product_name,
        sku: order.sku || "",
        amount: parseInt(order.amount, 10) || 0,
        address: order.address,
        pincode: order.pincode || "",
        city: order.city || "",
        state: order.state || "",
        whatsapp_opt_in: true,
        consent_source: "SmartBiz Extension List Scrape"
      };

      const res = await fetch(`${backendUrl}/api/orders/ingest`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (res.ok && (data.status === "saved" || data.status === "success")) {
        if (btn) { btn.textContent = "✅"; btn.style.background = "#047857"; }
        statusMsg.style.color = "#047857";
        statusMsg.textContent = `✅ ${order.customer_name || "Order"} synced to ZenOS!`;

        scrapedOrdersSession.unshift(payload);
        if (scrapedOrdersSession.length > 30) scrapedOrdersSession.pop();
        chrome.storage.local.set({ zenos_scraped_history: scrapedOrdersSession });
      } else {
        throw new Error(data.message || `Error ${res.status}`);
      }
    } catch (err) {
      statusMsg.style.color = "#b91c1c";
      statusMsg.textContent = `❌ ${err.message}`;
      if (btn) { btn.disabled = false; btn.textContent = "Sync"; }
    }
  };

  // Legacy single-order sync button (kept for compatibility with popup.html)
  const legacySyncBtn = document.getElementById("btn-sync-to-zenos");
  if (legacySyncBtn) {
    legacySyncBtn.addEventListener("click", async () => {
      if (!activeScrapedOrder) return;
      await window.syncScrapedOrderByIndex(0);
    });
  }

  function renderScrapedList() {
    const list = document.getElementById("scraped-orders-list");
    const countBadge = document.getElementById("scraped-count");

    // Show both newly-scraped and session history
    const displayOrders = scrapedOrdersList.length > 0 ? scrapedOrdersList : scrapedOrdersSession;
    const isLive = scrapedOrdersList.length > 0;

    if (countBadge) countBadge.textContent = `${displayOrders.length} ${isLive ? "found" : "saved"}`;

    // Hide old single-order card if it exists
    const singleCard = document.getElementById("card-scraped-order");
    if (singleCard) singleCard.style.display = "none";

    if (!displayOrders.length) {
      list.innerHTML = `<div style="text-align:center;color:#94a3b8;font-size:11.5px;padding:22px 10px;">No orders scraped in this session yet.</div>`;
      return;
    }

    list.innerHTML = displayOrders.map((o, idx) => {
      const phone10 = (o.phone || "").replace(/\D/g, "").slice(-10);
      const hasPhone = phone10.length === 10;
      const statusColor = o.order_status_smartbiz === "Accepted" ? "#047857"
        : o.order_status_smartbiz === "Pending" ? "#b45309" : "#475569";
      const statusBg = o.order_status_smartbiz === "Accepted" ? "#ecfdf5"
        : o.order_status_smartbiz === "Pending" ? "#fffbeb" : "#f1f5f9";

      return `
        <div style="border-bottom:1px solid #f1f5f9;padding:9px 12px;display:flex;align-items:flex-start;gap:8px;">
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:2px;">
              <div style="font-weight:700;font-size:12px;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;" title="${o.customer_name || ""}">
                ${idx + 1}. ${o.customer_name || "—"}
              </div>
              <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;">
                <span style="font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:999px;background:${statusBg};color:${statusColor};">${o.order_status_smartbiz || "Pending"}</span>
                <span style="font-family:monospace;font-size:11px;font-weight:700;color:#059669;">₹${o.amount || "—"}</span>
              </div>
            </div>
            <div style="font-size:10.5px;color:#475569;font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">#${o.order_ref || "—"} ${o.sku ? "• SKU: " + o.sku : ""}</div>
            ${hasPhone ? `<div style="font-size:10.5px;color:#1d4ed8;">📱 +91 ${phone10}</div>` : '<div style="font-size:10.5px;color:#b91c1c;">⚠️ No phone number detected</div>'}
            ${o.address ? `<div style="font-size:10px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${o.address}">📍 ${o.address}</div>` : ""}
          </div>
          ${isLive ? `<button id="btn-sync-scraped-${idx}" onclick="syncScrapedOrderByIndex(${idx})" 
            style="flex-shrink:0;padding:4px 9px;background:#008069;color:#fff;border:0;border-radius:5px;font-size:10.5px;font-weight:700;cursor:pointer;white-space:nowrap;">
            Sync
          </button>` : `<span style="font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:3px;background:#ecfdf5;color:#047857;border:1px solid #a7f3d0;flex-shrink:0;">Done</span>`}
        </div>
      `;
    }).join("");
  }

  // ==================== PAGE 2: WUKUSY 1-CLICK IMPORTER ====================
  document.getElementById("btn-refresh-wukusy").addEventListener("click", loadWukusyOrders);

  async function loadWukusyOrders() {
    const list = document.getElementById("wukusy-customers-list");
    const countBadge = document.getElementById("wukusy-available-count");
    list.innerHTML = `<div style="text-align:center;color:#94a3b8;font-size:11.5px;padding:28px 10px;">⏳ Loading orders from ZenOS…</div>`;

    const backendUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;
    const apiKey = keyField.value.trim();

    try {
      const headers = {};
      if (apiKey) headers["X-ZenOS-Extension-Key"] = apiKey;

      const res = await fetch(`${backendUrl}/api/dashboard/data`, { headers });
      if (!res.ok) throw new Error("Could not reach ZenOS API");

      const data = await res.json();
      const allOrders = data.orders || [];

      let confirmed = allOrders.filter(o => 
        ["CONFIRMED_COD", "PREPAID_PAID", "DELIVERY_COLLECT_CONFIRMED"].includes(o.status)
      );
      if (!confirmed.length) confirmed = allOrders;

      confirmedOrdersCache = confirmed;
      countBadge.textContent = `${confirmed.length} Available`;
      renderWukusyList();
    } catch (err) {
      list.innerHTML = `<div style="text-align:center;color:#b91c1c;font-size:11.5px;padding:28px 10px;">❌ Error: ${err.message}</div>`;
      countBadge.textContent = `0 Available`;
    }
  }

  function renderWukusyList() {
    const list = document.getElementById("wukusy-customers-list");
    if (!confirmedOrdersCache.length) {
      list.innerHTML = `<div style="text-align:center;color:#94a3b8;font-size:11.5px;padding:28px 10px;">No customer orders found in database.</div>`;
      return;
    }

    list.innerHTML = confirmedOrdersCache.map((o, idx) => {
      const location = [o.city, o.pincode].filter(Boolean).join(", ") || (o.address ? o.address.slice(0, 22) + '…' : 'India');
      const orderJson = encodeURIComponent(JSON.stringify(o));
      return `
        <div class="customer-row">
          <div style="flex:1; min-width:0;">
            <div style="font-weight:700; font-size:11.5px; color:#0f172a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
              ${idx + 1}. ${o.customer_name}
            </div>
            <div style="font-size:10.5px; color:#64748b; font-family:monospace; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
              ${o.order_ref} • ${location} • +${o.phone}
            </div>
          </div>
          <button type="button" class="btn-wukusy-fill" data-order="${orderJson}" style="padding:4px 9px; background:#6366f1; color:white; border:none; border-radius:6px; font-size:11px; font-weight:700; cursor:pointer; flex-shrink:0;">
            ⚡ Fill in Wukusy
          </button>
        </div>
      `;
    }).join("");

    list.querySelectorAll(".btn-wukusy-fill").forEach(btn => {
      btn.addEventListener("click", () => {
        const orderData = JSON.parse(decodeURIComponent(btn.getAttribute("data-order")));
        executeWukusyFill(orderData, btn);
      });
    });
  }

  function executeWukusyFill(order, buttonElement) {
    const statusMsg = document.getElementById("wukusy-action-status");
    const feedbackCard = document.getElementById("wukusy-feedback-card");
    const feedbackText = document.getElementById("wukusy-feedback-text");

    buttonElement.disabled = true;
    buttonElement.textContent = "⏳ Filling…";
    statusMsg.style.color = "#475569";
    statusMsg.textContent = `Injecting 8 address fields for ${order.customer_name}…`;

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs[0]) {
        statusMsg.style.color = "#b91c1c";
        statusMsg.textContent = "No active browser tab found.";
        buttonElement.disabled = false;
        buttonElement.textContent = "⚡ Fill in Wukusy";
        return;
      }

      chrome.tabs.sendMessage(tabs[0].id, { action: "FILL_WUKUSY_FORM", order }, (response) => {
        buttonElement.disabled = false;
        buttonElement.textContent = "⚡ Fill in Wukusy";

        if (chrome.runtime.lastError || !response) {
          statusMsg.style.color = "#b91c1c";
          statusMsg.textContent = "Please make sure Wukusy 'Add Address' modal or page is open.";
          return;
        }

        if (response.status === "success") {
          statusMsg.style.color = "#047857";
          statusMsg.textContent = `✅ Success! ${response.filledCount} fields populated for ${order.customer_name}!`;
          feedbackCard.style.display = "block";
          feedbackText.textContent = `First Name, Last Name, Company, Mobile (${order.phone}), Address 1, Address 2, City, Pincode injected with 100% precision.`;
        } else {
          statusMsg.style.color = "#b91c1c";
          statusMsg.textContent = response.message || "Failed to inject fields.";
        }
      });
    });
  }

  // ==================== PAGE 3: WHATSAPP & AI STUDIO ====================
  // Save Customer Form (6 Fields)
  document.getElementById("btn-save-customer-queue").addEventListener("click", async () => {
    const statusEl = document.getElementById("ext-add-status");
    const btn = document.getElementById("btn-save-customer-queue");

    const phone = document.getElementById("ext-add-phone").value.trim();
    const name = document.getElementById("ext-add-name").value.trim();
    const ref = document.getElementById("ext-add-ref").value.trim();
    const amount = document.getElementById("ext-add-amount").value.trim();
    const product = document.getElementById("ext-add-product").value.trim();
    const sku = document.getElementById("ext-add-sku").value.trim();

    if (!phone || !name || !ref || !amount || !product || !sku) {
      statusEl.style.color = "#b91c1c";
      statusEl.textContent = "Please fill all 6 required fields.";
      return;
    }

    btn.disabled = true;
    btn.textContent = "⏳ Saving…";

    const backendUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;
    try {
      const res = await fetch(`${backendUrl}/api/orders/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: name,
          phone: phone,
          order_ref: ref,
          product_name: product,
          sku: sku,
          amount: parseInt(amount, 10) || 349,
          whatsapp_opt_in: true,
          consent_source: "Extension WhatsApp Queue"
        })
      });

      const data = await res.json();
      if (res.ok && (data.status === "saved" || data.status === "success")) {
        statusEl.style.color = "#047857";
        statusEl.textContent = `✅ ${name} registered in WhatsApp Queue!`;
        btn.textContent = "✅ Saved!";
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = "💾 Save Customer & Open WhatsApp Chat";
        }, 1500);
      } else {
        throw new Error(data.message || "Failed to save");
      }
    } catch (err) {
      statusEl.style.color = "#b91c1c";
      statusEl.textContent = `Error: ${err.message}`;
      btn.disabled = false;
      btn.textContent = "💾 Save Customer & Open WhatsApp Chat";
    }
  });

  // AI Prompt live generator
  const promptInput = document.getElementById("ext-ai-prompt");
  if (promptInput) promptInput.addEventListener("input", renderAiPreview);

  window.setExtAiPreset = function(text) {
    document.getElementById("ext-ai-prompt").value = text;
    renderAiPreview();
  };

  function renderAiPreview() {
    const raw = (document.getElementById("ext-ai-prompt")?.value || "").toLowerCase();
    const name = document.getElementById("ext-add-name")?.value.trim() || activeScrapedOrder?.customer_name || "Customer";
    const ref = document.getElementById("ext-add-ref")?.value.trim() || activeScrapedOrder?.order_ref || "";
    const product = document.getElementById("ext-add-product")?.value.trim() || activeScrapedOrder?.product_name || "your order";
    const amount = parseInt(document.getElementById("ext-add-amount")?.value.trim(), 10) || parseInt(activeScrapedOrder?.amount, 10) || 0;
    const prepay50 = Math.max(1, amount - 50);

    const previewBox = document.getElementById("ext-ai-preview-box");
    const btnContainer = document.getElementById("ext-ai-buttons-preview");
    if (!previewBox) return;

    if (!raw && !name) {
      previewBox.textContent = "💬 Type notes or choose a preset below to preview personalized D2C message.";
      if (btnContainer) btnContainer.innerHTML = "";
      return;
    }

    let text = "";
    if (raw.includes("aaduhra") || raw.includes("address") || raw.includes("landmark") || raw.includes("pincode")) {
      text = `Namaste ${name}! 🙏✨\n\nThank you for choosing *Zenlora*! We are preparing your order${ref ? " *" + ref + "*" : ""}${product ? " (" + product + ")" : ""}.\n\n📍 *Delivery Address Verification Needed:*\nYour delivery address appears incomplete (missing house number or landmark). Please reply with your complete address in this format:\n\n• House / Flat No:\n• Street / Landmark:\n• City & State:\n• Pincode:\n\nOnce verified, your parcel will be dispatched immediately. 🚀\n\n━━━━━━━━━━━━━━━━━━━━\n🌟 Team Zenlora | zenlora.store`;
      extPendingAiButtons = [
        { id: "btn_update_addr", text: "📍 Update Address" },
        { id: "btn_prepay_50", text: `⚡ Pay Online (Save ₹50)` },
        { id: "btn_cancel_order", text: "❌ Cancel Order" }
      ];
    } else if (raw.includes("50") || raw.includes("prepay") || raw.includes("discount")) {
      text = `Namaste ${name}! 🙏✨\n\n⚡ *Exclusive Prepay Privilege — Flat ₹50 Instant Discount:*\nPay online now and get Flat ₹50 Instant Discount!\n${amount ? "Your price drops from ₹" + amount + " → only *₹" + prepay50 + "*!\n\n" : ""}Save ₹50 straight into your pocket + get Free Express Delivery 🎁\n\nTap a button below to confirm:`;
      extPendingAiButtons = [
        { id: "btn_prepay_50", text: amount ? `⚡ Pay ₹${prepay50} (Flat ₹50 OFF)` : "⚡ Pay Online (₹50 OFF)" },
        { id: "btn_confirm_cod", text: amount ? `✅ Confirm COD (₹${amount})` : "✅ Confirm COD" },
        { id: "btn_cancel_order", text: "❌ Cancel Order" }
      ];
    } else {
      text = `Namaste ${name}! 🙏✨\n\n📦 *Order Summary:*\n${ref ? "• Order ID: " + ref + "\n" : ""}• Product: ${product}\n${amount ? "• COD Total: ₹" + amount + "\n" : ""}\nPlease tap below to verify dispatch:`;
      extPendingAiButtons = [
        { id: "btn_confirm_cod", text: "✅ Confirm COD Order" },
        { id: "btn_prepay_50", text: `⚡ Pay Online (Save ₹50)` },
        { id: "btn_cancel_order", text: "❌ Cancel Order" }
      ];
    }

    previewBox.textContent = text;
    btnContainer.innerHTML = extPendingAiButtons.map(b => `
      <div style="background:#fff; border:1px solid #10b981; border-radius:5px; padding:4px 6px; font-weight:700; color:#047857; text-align:center; font-size:10.5px;">
        ${b.text}
      </div>
    `).join("");
  }

  // Dispatch AI WhatsApp via Gateway
  document.getElementById("btn-dispatch-ai-whatsapp").addEventListener("click", async () => {
    const statusEl = document.getElementById("ext-ai-status");
    const btn = document.getElementById("btn-dispatch-ai-whatsapp");
    const phone = document.getElementById("ext-add-phone").value.trim();
    const name = document.getElementById("ext-add-name").value.trim();
    const message = document.getElementById("ext-ai-preview-box").textContent;

    btn.disabled = true;
    btn.textContent = "⏳ Sending via Gateway…";

    const cleanDigits = phone.replace(/\D/g, "");
    const backendUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;

    try {
      const res = await fetch(`${backendUrl}/api/crm/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: cleanDigits.length === 10 ? `91${cleanDigits}` : cleanDigits,
          customer_name: name,
          message: message,
          buttons: extPendingAiButtons
        })
      });

      const data = await res.json();
      if (res.ok && data.status === "success") {
        statusEl.style.color = "#047857";
        statusEl.textContent = `✅ Dispatched to +91 ${cleanDigits} via WhatsApp Gateway!`;
        btn.textContent = "✅ Message Delivered!";
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = "🚀 Send via WhatsApp Gateway (+91 97713 70945)";
        }, 2000);
      } else {
        throw new Error(data.message || "Failed to dispatch");
      }
    } catch (err) {
      statusEl.style.color = "#b91c1c";
      statusEl.textContent = `Error: ${err.message}`;
      btn.disabled = false;
      btn.textContent = "🚀 Send via WhatsApp Gateway (+91 97713 70945)";
    }
  });

});