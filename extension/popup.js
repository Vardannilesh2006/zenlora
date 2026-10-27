document.addEventListener("DOMContentLoaded", () => {
  const backendField = document.getElementById("backend-url");
  const keyField = document.getElementById("extension-key");
  const configStatus = document.getElementById("config-status");
  const defaultUrl = "https://zenos-nine.vercel.app";

  let activeScrapedOrder = null;
  let scrapedOrdersSession = [];
  let confirmedOrdersCache = [];
  let scrapedOrdersList = [];
  let extPendingAiButtons = [];

  // ==================== 1. TAB SWITCHING (MV3 COMPLIANT) ====================
  function switchTab(tabName) {
    document.querySelectorAll(".segment-btn").forEach(btn => {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === tabName);
    });
    document.querySelectorAll(".page-content").forEach(p => {
      p.classList.toggle("active", p.id === `page-${tabName}`);
    });

    if (tabName === "wukusy") {
      loadWukusyOrders();
    } else if (tabName === "whatsapp") {
      renderAiPreview();
    }
  }

  document.querySelectorAll("[data-tab]").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      if (tab) switchTab(tab);
    });
  });

  // WhatsApp Sub-Tabs
  function switchWaSub(subName) {
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
  }

  document.querySelectorAll("[data-wa-sub]").forEach(btn => {
    btn.addEventListener("click", () => {
      const sub = btn.getAttribute("data-wa-sub");
      if (sub) switchWaSub(sub);
    });
  });

  // Quick Preset Chips for AI Studio
  document.querySelectorAll("[data-preset]").forEach(btn => {
    btn.addEventListener("click", () => {
      const p = btn.getAttribute("data-preset");
      const input = document.getElementById("ext-ai-prompt");
      if (p === "address") {
        input.value = "aapka addresh aaduhra hai, kripya pura address landmark ke sath share kare";
      } else if (p === "prepay50") {
        input.value = "50 rs flat discount offer on online payment, prepaid confirm kare";
      } else if (p === "cod") {
        input.value = "cod order confirmation with details and tracking";
      }
      renderAiPreview();
    });
  });

  // Settings Quick URL buttons
  const btnCloud = document.getElementById("btn-url-cloud");
  if (btnCloud) {
    btnCloud.addEventListener("click", () => {
      backendField.value = "https://zenos-nine.vercel.app";
    });
  }
  const btnLocal = document.getElementById("btn-url-local");
  if (btnLocal) {
    btnLocal.addEventListener("click", () => {
      backendField.value = "http://localhost:5000";
    });
  }

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
    const backendUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;
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

  // ==================== PAGE 1: SMARTBIZ ORDER SCRAPER ====================
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

      // Ensure content script is injected
      chrome.scripting.executeScript({
        target: { tabId: tabs[0].id },
        files: ["smartbiz_bridge.js"]
      }).catch(() => {});

      setTimeout(() => {
        chrome.tabs.sendMessage(tabs[0].id, { action: "SCRAPE_SMARTBIZ_ORDERS_LIST" }, (response) => {
          if (chrome.runtime.lastError) {
            statusMsg.style.color = "#b91c1c";
            statusMsg.textContent = "⚠️ Could not connect to SmartBiz page. Refresh the tab and retry.";
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

          if (count >= 1) activeScrapedOrder = scrapedOrdersList[0];

          renderScrapedList();
        });
      }, 400);
    });
  });

  // Sync a single scraped order by index
  async function syncScrapedOrderByIndex(idx, btn) {
    const order = scrapedOrdersList[idx];
    if (!order) return false;
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
        payment_mode: order.payment_mode || "COD",
        address: order.address,
        pincode: order.pincode || "",
        city: order.city || "",
        state: order.state || "",
        whatsapp_opt_in: true,
        marketing_opt_in: true,
        consent_source: "SmartBiz Popup Sync"
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
        return true;
      } else {
        throw new Error(data.message || `Error ${res.status}`);
      }
    } catch (err) {
      statusMsg.style.color = "#b91c1c";
      statusMsg.textContent = `❌ ${err.message}`;
      if (btn) { btn.disabled = false; btn.textContent = "Sync"; }
      return false;
    }
  }

  // Sync All Scraped Orders to ZenOS
  const btnSyncAll = document.getElementById("btn-sync-all-to-zenos");
  if (btnSyncAll) {
    btnSyncAll.addEventListener("click", async () => {
      if (!scrapedOrdersList.length) return;
      btnSyncAll.disabled = true;
      const statusMsg = document.getElementById("scrape-status");
      let successCount = 0;

      for (let i = 0; i < scrapedOrdersList.length; i++) {
        btnSyncAll.textContent = `⏳ Syncing ${i + 1}/${scrapedOrdersList.length}…`;
        const rowBtn = document.querySelector(`[data-sync-idx="${i}"]`);
        const ok = await syncScrapedOrderByIndex(i, rowBtn);
        if (ok) successCount++;
      }

      btnSyncAll.disabled = false;
      btnSyncAll.textContent = `✅ Synced ${successCount}/${scrapedOrdersList.length} to ZenOS!`;
      statusMsg.style.color = "#047857";
      statusMsg.textContent = `🎉 All ${successCount} orders successfully saved to ZenOS!`;
    });
  }

  function renderScrapedList() {
    const list = document.getElementById("scraped-orders-list");
    const countBadge = document.getElementById("scraped-count");
    const actionsBar = document.getElementById("scraped-actions-bar");
    const syncAllCount = document.getElementById("sync-all-count");

    const displayOrders = scrapedOrdersList.length > 0 ? scrapedOrdersList : scrapedOrdersSession;
    const isLive = scrapedOrdersList.length > 0;

    if (countBadge) countBadge.textContent = `${displayOrders.length} ${isLive ? "found" : "saved"}`;

    if (actionsBar) {
      actionsBar.style.display = isLive && displayOrders.length > 0 ? "block" : "none";
      if (syncAllCount) syncAllCount.textContent = displayOrders.length;
    }

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
        <div class="customer-row">
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:2px;">
              <div style="font-weight:700;font-size:12px;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;" title="${escapeHtml(o.customer_name || "")}">
                ${idx + 1}. ${escapeHtml(o.customer_name || "—")}
              </div>
              <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;">
                <span style="font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:999px;background:${statusBg};color:${statusColor};">${escapeHtml(o.order_status_smartbiz || "Pending")}</span>
                <span style="font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:999px;background:${o.payment_mode === 'PREPAID' ? '#eff6ff' : '#fef3c7'};color:${o.payment_mode === 'PREPAID' ? '#1d4ed8' : '#92400e'};">${escapeHtml(o.payment_mode || "COD")}</span>
                <span style="font-family:monospace;font-size:11px;font-weight:700;color:#059669;">₹${o.amount || "—"}</span>
              </div>
            </div>
            <div style="font-size:10.5px;color:#475569;font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">#${escapeHtml(o.order_ref || "—")} ${o.sku ? "• SKU: " + escapeHtml(o.sku) : ""}</div>
            ${hasPhone ? `<div style="font-size:10.5px;color:#1d4ed8;">📱 +91 ${phone10}</div>` : '<div style="font-size:10.5px;color:#b91c1c;">⚠️ No phone number</div>'}
            ${o.address ? `<div style="font-size:10px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escapeHtml(o.address)}">📍 ${escapeHtml(o.address)}</div>` : ""}
          </div>
          ${isLive ? `<button type="button" class="btn-sync-single" data-sync-idx="${idx}" style="flex-shrink:0;padding:4px 9px;background:#008069;color:#fff;border:0;border-radius:5px;font-size:10.5px;font-weight:700;cursor:pointer;white-space:nowrap;">Sync</button>` : `<span style="font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:3px;background:#ecfdf5;color:#047857;border:1px solid #a7f3d0;flex-shrink:0;">Done</span>`}
        </div>
      `;
    }).join("");

    // Wire sync buttons via event delegation
    list.querySelectorAll(".btn-sync-single").forEach(b => {
      b.addEventListener("click", () => {
        const idx = parseInt(b.getAttribute("data-sync-idx"), 10);
        syncScrapedOrderByIndex(idx, b);
      });
    });
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

      const res = await fetch(`${backendUrl}/api/orders/pending-wukusy`, { headers });
      if (!res.ok) throw new Error(`Could not reach ZenOS API (${res.status})`);

      const data = await res.json();
      if (data.status !== "success" || !Array.isArray(data.orders)) {
        throw new Error(data.message || "ZenOS returned an invalid fulfillment queue.");
      }
      confirmedOrdersCache = data.orders;
      countBadge.textContent = `${data.orders.length} Available`;
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
      return `
        <div class="customer-row">
          <div style="flex:1; min-width:0;">
            <div style="font-weight:700; font-size:11.5px; color:#0f172a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
              ${idx + 1}. ${escapeHtml(o.customer_name)}
            </div>
            <div style="font-size:10.5px; color:#64748b; font-family:monospace; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
              ${escapeHtml(o.order_ref)} • ${escapeHtml(location)} • +${escapeHtml(o.phone)}
            </div>
          </div>
          <button type="button" class="btn-wukusy-fill" data-wukusy-idx="${idx}" style="padding:4px 9px; background:#6366f1; color:white; border:none; border-radius:6px; font-size:11px; font-weight:700; cursor:pointer; flex-shrink:0;">
            ⚡ Fill in Wukusy
          </button>
        </div>
      `;
    }).join("");

    list.querySelectorAll(".btn-wukusy-fill").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.getAttribute("data-wukusy-idx"), 10);
        const orderData = confirmedOrdersCache[idx];
        if (orderData) executeWukusyFill(orderData, btn);
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
    statusMsg.textContent = `Injecting address fields for ${order.customer_name}…`;

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs[0]) {
        statusMsg.style.color = "#b91c1c";
        statusMsg.textContent = "No active browser tab found.";
        buttonElement.disabled = false;
        buttonElement.textContent = "⚡ Fill in Wukusy";
        return;
      }

      // First ensure wukusy_bridge.js is injected
      chrome.scripting.executeScript({
        target: { tabId: tabs[0].id },
        files: ["wukusy_bridge.js"]
      }).catch(() => {});

      setTimeout(() => {
        chrome.tabs.sendMessage(tabs[0].id, { action: "FILL_WUKUSY_FORM", order }, (response) => {
          buttonElement.disabled = false;
          buttonElement.textContent = "⚡ Fill in Wukusy";

          if (chrome.runtime.lastError || !response) {
            statusMsg.style.color = "#b91c1c";
            statusMsg.textContent = "Please make sure https://wukusy.app/ is open with 'Add Address' visible.";
            return;
          }

          if (response.status === "success") {
            statusMsg.style.color = "#047857";
            statusMsg.textContent = `✅ Success! ${response.filledCount} fields populated for ${order.customer_name}!`;
            if (feedbackCard) feedbackCard.style.display = "block";
            if (feedbackText) {
              feedbackText.textContent = `${response.filledCount} fields populated. Verify every value in Wukusy; the extension does not submit the booking.`;
            }
          } else {
            statusMsg.style.color = "#b91c1c";
            statusMsg.textContent = response.message || "Failed to inject fields.";
          }
        });
      }, 400);
    });
  }

  // ==================== PAGE 3: WHATSAPP QUEUE & AI STUDIO ====================
  // Register Customer
  document.getElementById("btn-save-customer-queue").addEventListener("click", async () => {
    const status = document.getElementById("ext-add-status");
    const phone = document.getElementById("ext-add-phone").value.trim();
    const name = document.getElementById("ext-add-name").value.trim();
    const ref = document.getElementById("ext-add-ref").value.trim();
    const amount = document.getElementById("ext-add-amount").value.trim();
    const product = document.getElementById("ext-add-product").value.trim();
    const sku = document.getElementById("ext-add-sku").value.trim();
    const whatsappOptIn = document.getElementById("ext-add-wa-opt-in").checked;
    const marketingOptIn = document.getElementById("ext-add-marketing-opt-in").checked;
    const consentSource = document.getElementById("ext-add-consent-source").value.trim();

    if (!phone || !name || !ref || !amount || !product) {
      status.style.color = "#b91c1c";
      status.textContent = "All required fields (*) must be provided!";
      return;
    }
    if (marketingOptIn && !whatsappOptIn) {
      status.style.color = "#b91c1c";
      status.textContent = "Marketing consent requires WhatsApp order-update consent too.";
      return;
    }
    if ((whatsappOptIn || marketingOptIn) && !consentSource) {
      status.style.color = "#b91c1c";
      status.textContent = "Record where the customer gave consent before saving.";
      return;
    }

    status.style.color = "#64748b";
    status.textContent = "Saving customer to ZenOS…";

    const backendUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;
    const apiKey = keyField.value.trim();

    try {
      const headers = { "Content-Type": "application/json" };
      if (apiKey) headers["X-ZenOS-Extension-Key"] = apiKey;

      const payload = {
        customer_name: name,
        phone: phone.replace(/\D/g, "").slice(-10),
        order_ref: ref,
        amount: parseInt(amount, 10) || 0,
        product_name: product,
        sku: sku,
        whatsapp_opt_in: whatsappOptIn,
        marketing_opt_in: marketingOptIn,
        consent_source: whatsappOptIn ? consentSource : ""
      };

      const res = await fetch(`${backendUrl}/api/orders/ingest`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (res.ok && (data.status === "saved" || data.status === "success")) {
        status.style.color = "#047857";
        status.textContent = `✅ ${name} registered in ZenOS!`;
        document.getElementById("ext-add-wa-opt-in").checked = false;
        document.getElementById("ext-add-marketing-opt-in").checked = false;
        document.getElementById("ext-add-consent-source").value = "";
        const clean10 = phone.replace(/\D/g, "").slice(-10);
        setTimeout(() => {
          window.open(`https://wa.me/91${clean10}`, "_blank");
        }, 800);
      } else {
        throw new Error(data.message || `Error ${res.status}`);
      }
    } catch (err) {
      status.style.color = "#b91c1c";
      status.textContent = `❌ ${err.message}`;
    }
  });

  // AI Prompt live preview
  const extAiPrompt = document.getElementById("ext-ai-prompt");
  if (extAiPrompt) {
    extAiPrompt.addEventListener("input", renderAiPreview);
  }
  ["ext-add-ref", "ext-add-name", "ext-add-product", "ext-add-amount", "ext-add-marketing-opt-in"].forEach(id => {
    document.getElementById(id).addEventListener("input", renderAiPreview);
    document.getElementById(id).addEventListener("change", renderAiPreview);
  });

  function renderAiPreview() {
    const promptInput = document.getElementById("ext-ai-prompt");
    const previewBox = document.getElementById("ext-ai-preview-box");
    const buttonsBox = document.getElementById("ext-ai-buttons-preview");
    if (!previewBox) return;

    const raw = (promptInput?.value || "").toLowerCase().trim();
    const orderRef = document.getElementById("ext-add-ref").value.trim().replace(/^#/, "");
    const customerName = document.getElementById("ext-add-name").value.trim() || "Customer";
    const productName = document.getElementById("ext-add-product").value.trim() || "your order";
    const amount = Number.parseInt(document.getElementById("ext-add-amount").value, 10);
    let text = "";
    extPendingAiButtons = [];

    if (!orderRef) {
      previewBox.textContent = "Enter a saved order reference in Add Customer before creating a customer-specific message.";
      if (buttonsBox) buttonsBox.replaceChildren();
      return;
    }

    if (raw.includes("aaduhra") || raw.includes("address") || raw.includes("landmark") || raw.includes("pin")) {
      text = `Namaste ${customerName},\n\nWe are checking the delivery details for order *#${orderRef}*. Please reply in this format so our team can review the address:\n\nHouse / Flat No:\nStreet / Landmark:\nCity & State:\nPincode:`;
    } else if (raw.includes("50") || raw.includes("prepay") || raw.includes("discount") || raw.includes("online")) {
      const marketingOptIn = document.getElementById("ext-add-marketing-opt-in").checked;
      if (!marketingOptIn || !Number.isInteger(amount) || amount < 2) {
        text = "A prepaid discount message requires a valid order amount and separately recorded marketing consent.";
      } else {
        const savings = Math.min(50, amount - 1);
        text = `Namaste ${customerName},\n\nFor order *#${orderRef}* (${productName}), choose the prepaid option if you would like a secure payment link. Pay ₹${amount - savings} and save ₹${savings}.`;
        extPendingAiButtons = [
          { id: `btn_pay50_${orderRef}_${amount}`, text: `Pay ₹${amount - savings} (₹${savings} off)` },
          { id: `btn_cod_${orderRef}`, text: `Confirm COD (₹${amount})` },
          { id: `btn_cancel_${orderRef}`, text: "Request cancellation" }
        ];
      }
    } else {
      text = `Namaste ${customerName},\n\nWe received order *#${orderRef}* for *${productName}* (₹${Number.isInteger(amount) ? amount : "amount"}). Please confirm the COD order or request cancellation below.`;
      extPendingAiButtons = [
        { id: `btn_cod_${orderRef}`, text: "Confirm COD" },
        { id: `btn_cancel_${orderRef}`, text: "Request cancellation" }
      ];
    }

    previewBox.textContent = text;
    if (buttonsBox) {
      buttonsBox.innerHTML = extPendingAiButtons.map(b => `
        <div style="background:#ffffff; border:1px solid #10b981; border-radius:6px; padding:5px; font-weight:700; font-size:10.5px; color:#047857; text-align:center;">
          ${escapeHtml(b.text)}
        </div>
      `).join("");
    }
  }

  // Dispatch AI WhatsApp
  document.getElementById("btn-dispatch-ai-whatsapp").addEventListener("click", async () => {
    const status = document.getElementById("ext-ai-status");
    const previewBox = document.getElementById("ext-ai-preview-box");
    const text = previewBox ? previewBox.textContent : "";
    const phoneInput = document.getElementById("ext-add-phone");
    const cleanPhone = (phoneInput?.value || "").replace(/\D/g, "").slice(-10);
    const orderRef = document.getElementById("ext-add-ref").value.trim().replace(/^#/, "");
    const customerName = document.getElementById("ext-add-name").value.trim();

    if (!cleanPhone || cleanPhone.length !== 10) {
      status.style.color = "#b91c1c";
      status.textContent = "Please enter a valid 10-digit WhatsApp number in the form first!";
      return;
    }

    if (!orderRef || !customerName || !text || text.startsWith("A prepaid discount message requires")) {
      status.style.color = "#b91c1c";
      status.textContent = "Complete the order details and required consent before sending.";
      return;
    }

    status.style.color = "#64748b";
    status.textContent = "Sending through the configured provider…";

    const backendUrl = backendField.value.trim().replace(/\/+$/, "") || defaultUrl;
    const apiKey = keyField.value.trim();
    try {
      const res = await fetch(`${backendUrl}/api/extension/crm/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-ZenOS-Extension-Key": apiKey },
        body: JSON.stringify({
          phone: `91${cleanPhone}`,
          customer_name: customerName,
          order_ref: orderRef,
          message: text,
          buttons: extPendingAiButtons
        })
      });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        status.style.color = "#047857";
        status.textContent = `Provider accepted the message for +91 ${cleanPhone}; recipient delivery is not confirmed.`;
      } else if (data.delivery_method === "MANUAL_LINK_REQUIRED" && (data.web_wa_link || data.wa_link)) {
        status.style.color = "#b91c1c";
        status.textContent = "Automated sending failed. Opening WhatsApp for you to review and send manually.";
        window.open(data.web_wa_link || data.wa_link, "_blank", "noopener");
      } else {
        throw new Error(data.message || `Error ${res.status}`);
      }
    } catch (err) {
      status.style.color = "#b91c1c";
      status.textContent = `❌ ${err.message}`;
    }
  });

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, m => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[m]);
  }
});
