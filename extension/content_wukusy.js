// Zenlora Auto-Bridge - Wukusy Content Script
console.log("⚡ Zenlora Auto-Bridge loaded on Wukusy!");

function setInputValue(input, value) {
  if (!input || !value) return;
  input.focus();
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  input.blur();
}

function autoFillOrder(order) {
  if (!order) return false;

  let filledCount = 0;

  // Name
  const nameSelectors = [
    'input[name*="name" i]',
    'input[name*="customer" i]',
    'input[placeholder*="name" i]',
    'input[placeholder*="customer" i]',
    '#name',
    '#customer_name'
  ];
  for (const sel of nameSelectors) {
    const el = document.querySelector(sel);
    if (el && el.type !== "hidden") {
      setInputValue(el, order.customer_name);
      filledCount++;
      break;
    }
  }

  // Phone / Mobile
  const phoneSelectors = [
    'input[name*="phone" i]',
    'input[name*="mobile" i]',
    'input[placeholder*="mobile" i]',
    'input[placeholder*="phone" i]',
    '#phone',
    '#mobile'
  ];
  for (const sel of phoneSelectors) {
    const el = document.querySelector(sel);
    if (el && el.type !== "hidden") {
      setInputValue(el, order.phone);
      filledCount++;
      break;
    }
  }

  // Pincode
  const pinSelectors = [
    'input[name*="pin" i]',
    'input[name*="zip" i]',
    'input[placeholder*="pin" i]',
    'input[placeholder*="zip" i]',
    '#pincode',
    '#pin'
  ];
  for (const sel of pinSelectors) {
    const el = document.querySelector(sel);
    if (el && el.type !== "hidden") {
      setInputValue(el, order.pincode);
      filledCount++;
      break;
    }
  }

  // Address
  const addrSelectors = [
    'textarea[name*="address" i]',
    'input[name*="address" i]',
    'textarea[placeholder*="address" i]',
    'input[placeholder*="address" i]',
    '#address',
    '#shipping_address'
  ];
  for (const sel of addrSelectors) {
    const el = document.querySelector(sel);
    if (el && el.type !== "hidden") {
      setInputValue(el, order.address || `${order.customer_name}, Delivery Address`);
      filledCount++;
      break;
    }
  }

  return filledCount > 0;
}

function renderWukusyBanner() {
  chrome.storage.local.get("zenlora_pending_order", (data) => {
    const order = data.zenlora_pending_order;
    if (!order || !order.customer_name) return;

    if (document.getElementById("zenlora-wukusy-banner")) return;

    const banner = document.createElement("div");
    banner.id = "zenlora-wukusy-banner";
    banner.style.cssText = `
      position: fixed;
      top: 15px;
      right: 20px;
      z-index: 999999;
      background: #0f172a;
      color: #fff;
      padding: 14px 18px;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
      font-family: system-ui, sans-serif;
      border: 1px solid #38bdf8;
      display: flex;
      align-items: center;
      gap: 14px;
    `;

    banner.innerHTML = `
      <div>
        <div style="font-weight:800;font-size:13px;color:#38bdf8;">⚡ Zenlora Order Detected</div>
        <div style="font-size:12px;color:#e2e8f0;">
          <b>${order.customer_name}</b> (${order.phone}) • ₹${order.amount}
        </div>
      </div>
      <button id="zenlora-autofill-btn" style="cursor:pointer;background:#e11d2e;color:#fff;border:none;padding:8px 14px;border-radius:8px;font-weight:800;font-size:12px;box-shadow:0 4px 12px rgba(225,29,46,0.3);">
        🚀 Auto-Fill Address
      </button>
      <button id="zenlora-dismiss-btn" style="cursor:pointer;background:transparent;color:#94a3b8;border:none;font-size:14px;">✕</button>
    `;

    document.body.appendChild(banner);

    document.getElementById("zenlora-autofill-btn").addEventListener("click", () => {
      const success = autoFillOrder(order);
      const btn = document.getElementById("zenlora-autofill-btn");
      if (success) {
        btn.innerText = "✅ Auto-Filled!";
        btn.style.background = "#10b981";
      } else {
        btn.innerText = "⚠️ Open Order Form First";
      }
    });

    document.getElementById("zenlora-dismiss-btn").addEventListener("click", () => {
      banner.remove();
      chrome.storage.local.remove("zenlora_pending_order");
    });
  });
}

setInterval(renderWukusyBanner, 2000);
