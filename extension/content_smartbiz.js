// Zenlora Auto-Bridge - SmartBiz Content Script
console.log("⚡ Zenlora Auto-Bridge loaded on SmartBiz!");

const BOT_API = "https://zenlora-whatsapp-bot.onrender.com";

function extractOrderDetails() {
  const bodyText = document.body.innerText;
  
  // Extract Phone Number (10 digits, or +91...)
  let phone = "";
  const phoneMatch = bodyText.match(/(?:\+91|91)?\s*([6-9]\d{9})/);
  if (phoneMatch) {
    phone = phoneMatch[1];
  }

  // Extract Order ID (e.g. SB-12345 or similar)
  let orderId = "1001";
  const orderMatch = bodyText.match(/Order\s*(?:#|ID|id)?\s*[:\-]?\s*([A-Za-z0-9_\-]+)/i);
  if (orderMatch) {
    orderId = orderMatch[1];
  }

  // Extract Amount (e.g. ₹349 or Rs. 349)
  let amount = 349;
  const amtMatch = bodyText.match(/(?:₹|Rs\.?|INR)\s*(\d{2,5})/i);
  if (amtMatch) {
    amount = parseInt(amtMatch[1], 10);
  }

  // Extract Name (heuristic: first capitalized line or from standard patterns)
  let customerName = "Valued Customer";
  const nameMatch = bodyText.match(/(?:Deliver to|Customer|Name|Shipping Address)[:\-]?\s*([A-Za-z ]{3,30})/i);
  if (nameMatch) {
    customerName = nameMatch[1].trim();
  }

  // Extract Pincode
  let pincode = "";
  const pinMatch = bodyText.match(/\b([1-9][0-9]{5})\b/);
  if (pinMatch) {
    pincode = pinMatch[1];
  }

  // Extract Full Address snippet
  let fullAddress = "";
  const addrMatch = bodyText.match(/(?:Address|Ship to)[:\-]?\s*([^,\n]+,[^,\n]+,[^,\n]+)/i);
  if (addrMatch) {
    fullAddress = addrMatch[1].trim();
  }

  // Product Name
  let productName = "Zenlora Lifestyle Product";
  const titleEl = document.querySelector("h1, h2, h3, .product-title, .order-item-title");
  if (titleEl && titleEl.innerText) {
    productName = titleEl.innerText.slice(0, 50).trim();
  }

  return {
    order_id: orderId,
    customer_name: customerName,
    phone: phone,
    amount: amount,
    product_name: productName,
    pincode: pincode,
    address: fullAddress,
    timestamp: new Date().toISOString()
  };
}

function createFloatingWidget() {
  if (document.getElementById("zenlora-floating-bridge")) return;

  const container = document.createElement("div");
  container.id = "zenlora-floating-bridge";
  container.style.cssText = `
    position: fixed;
    bottom: 25px;
    right: 25px;
    z-index: 999999;
    background: #0f172a;
    color: #ffffff;
    border-radius: 16px;
    padding: 16px 20px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    font-family: system-ui, -apple-system, sans-serif;
    border: 1px solid rgba(255,255,255,0.15);
    min-width: 300px;
  `;

  container.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
      <div style="font-weight:800;font-size:15px;color:#38bdf8;">🛍️ Zenlora Auto-Bridge</div>
      <span style="font-size:11px;background:#10b981;color:#fff;padding:2px 8px;border-radius:10px;font-weight:700;">Live Sync</span>
    </div>
    <div id="zenlora-order-preview" style="font-size:12px;color:#94a3b8;margin-bottom:12px;background:#1e293b;padding:8px 12px;border-radius:8px;">
      Detecting order on screen...
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <button id="zenlora-btn-confirm" style="cursor:pointer;background:#2563eb;color:#fff;border:none;padding:10px 14px;border-radius:8px;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;gap:6px;transition:0.2s;">
        ⚡ 1-Click WhatsApp Order Confirm
      </button>
      <button id="zenlora-btn-ofd" style="cursor:pointer;background:#059669;color:#fff;border:none;padding:10px 14px;border-radius:8px;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;gap:6px;transition:0.2s;">
        🚚 Send Out For Delivery Check
      </button>
      <button id="zenlora-btn-wukusy" style="cursor:pointer;background:#e11d2e;color:#fff;border:none;padding:10px 14px;border-radius:8px;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;gap:6px;transition:0.2s;">
        📦 Push to Wukusy Queue
      </button>
    </div>
    <div id="zenlora-status" style="font-size:11px;margin-top:10px;text-align:center;color:#64748b;">Ready</div>
  `;

  document.body.appendChild(container);

  // Update preview
  function refreshPreview() {
    const details = extractOrderDetails();
    const previewEl = document.getElementById("zenlora-order-preview");
    if (previewEl) {
      previewEl.innerHTML = `
        <b>Customer:</b> ${details.customer_name || 'Detecting...'}<br>
        <b>Phone:</b> ${details.phone || 'Detecting...'}<br>
        <b>Amount:</b> ₹${details.amount} | <b>Pin:</b> ${details.pincode || 'N/A'}
      `;
    }
  }

  refreshPreview();
  setInterval(refreshPreview, 3000);

  // 1-Click WhatsApp Order Confirm
  document.getElementById("zenlora-btn-confirm").addEventListener("click", async () => {
    const details = extractOrderDetails();
    const statusEl = document.getElementById("zenlora-status");
    if (!details.phone) {
      statusEl.innerText = "❌ Please open an order page with phone visible!";
      statusEl.style.color = "#f87171";
      return;
    }
    statusEl.innerText = "⏳ Sending WhatsApp confirmation...";
    statusEl.style.color = "#38bdf8";

    try {
      const res = await fetch(`${BOT_API}/api/order-webhook`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(details)
      });
      const data = await res.json();
      if (res.ok) {
        statusEl.innerText = "✅ WhatsApp confirmation sent successfully!";
        statusEl.style.color = "#4ade80";
        // Also save to Wukusy queue
        chrome.storage.local.set({ "zenlora_pending_order": details });
      } else {
        statusEl.innerText = `❌ Error: ${data.message || 'Failed'}`;
        statusEl.style.color = "#f87171";
      }
    } catch (e) {
      statusEl.innerText = `❌ Network Error: ${e.message}`;
      statusEl.style.color = "#f87171";
    }
  });

  // Out For Delivery Check
  document.getElementById("zenlora-btn-ofd").addEventListener("click", async () => {
    const details = extractOrderDetails();
    const statusEl = document.getElementById("zenlora-status");
    if (!details.phone) {
      statusEl.innerText = "❌ Please open an order page with phone visible!";
      statusEl.style.color = "#f87171";
      return;
    }
    statusEl.innerText = "⏳ Sending Out For Delivery check...";
    statusEl.style.color = "#38bdf8";

    try {
      const res = await fetch(`${BOT_API}/api/ofd-webhook`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(details)
      });
      const data = await res.json();
      if (res.ok) {
        statusEl.innerText = "✅ Availability check message delivered!";
        statusEl.style.color = "#4ade80";
      } else {
        statusEl.innerText = `❌ Error: ${data.message || 'Failed'}`;
        statusEl.style.color = "#f87171";
      }
    } catch (e) {
      statusEl.innerText = `❌ Network Error: ${e.message}`;
      statusEl.style.color = "#f87171";
    }
  });

  // Push to Wukusy Queue
  document.getElementById("zenlora-btn-wukusy").addEventListener("click", () => {
    const details = extractOrderDetails();
    chrome.storage.local.set({ "zenlora_pending_order": details }, () => {
      const statusEl = document.getElementById("zenlora-status");
      statusEl.innerText = "✅ Queued! Now open Wukusy to auto-fill!";
      statusEl.style.color = "#4ade80";
    });
  });
}

setTimeout(createFloatingWidget, 1500);
