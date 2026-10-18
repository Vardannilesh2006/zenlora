// Popup JS for Zenlora Auto-Bridge
const BOT_API = "https://zenlora-whatsapp-bot.onrender.com";
const TEST_PHONE = "919608837916";

const statusEl = document.getElementById("status-msg");

document.getElementById("btn-test-confirm").addEventListener("click", async () => {
  statusEl.innerText = "⏳ Sending Order Confirmation...";
  try {
    const res = await fetch(`${BOT_API}/api/order-webhook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_name: "Nilesh Vardan",
        phone: TEST_PHONE,
        order_id: "1002",
        product_name: "Handcrafted Red Decorative Matki Kalash",
        amount: 349
      })
    });
    if (res.ok) {
      statusEl.innerText = "✅ Sent to WhatsApp successfully!";
      statusEl.style.color = "#4ade80";
    } else {
      statusEl.innerText = "❌ Failed to send";
      statusEl.style.color = "#f87171";
    }
  } catch (e) {
    statusEl.innerText = `❌ Error: ${e.message}`;
    statusEl.style.color = "#f87171";
  }
});

document.getElementById("btn-test-ofd").addEventListener("click", async () => {
  statusEl.innerText = "⏳ Sending Out For Delivery Check...";
  try {
    const res = await fetch(`${BOT_API}/api/ofd-webhook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_name: "Nilesh Vardan",
        phone: TEST_PHONE,
        order_id: "1002",
        product_name: "Handcrafted Red Decorative Matki Kalash",
        amount: 349,
        pin: "159"
      })
    });
    if (res.ok) {
      statusEl.innerText = "✅ OFD Check Sent to WhatsApp!";
      statusEl.style.color = "#4ade80";
    } else {
      statusEl.innerText = "❌ Failed to send";
      statusEl.style.color = "#f87171";
    }
  } catch (e) {
    statusEl.innerText = `❌ Error: ${e.message}`;
    statusEl.style.color = "#f87171";
  }
});
