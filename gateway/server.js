/**
 * OpenWA WhatsApp Gateway for ZenOS (RTO Killer & Order Automation)
 * 
 * Free, self-hosted, 100% Meta-independent WhatsApp Gateway.
 * Fully compatible with OpenWA REST API specification and Baileys engine.
 * 
 * Port: 2785 (Default OpenWA Port)
 * Web Dashboard: http://localhost:2785
 */

const express = require('express');
const QRCode = require('qrcode');
const path = require('path');
const fs = require('fs');
const pino = require('pino');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');

const app = express();
const PORT = process.env.PORT || 2785;
const SESSION_DIR = path.join(__dirname, 'session');
const ZENOS_WEBHOOK = process.env.ZENOS_WEBHOOK || 'http://localhost:5000/api/whatsapp/webhook';

if (!fs.existsSync(SESSION_DIR)) {
  fs.mkdirSync(SESSION_DIR, { recursive: true });
}

app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// In-memory gateway state
let sock = null;
let currentQR = null;
let connectionStatus = 'DISCONNECTED'; // DISCONNECTED, SCAN_QR, CONNECTING, CONNECTED
let connectedNumber = null;
let recentLogs = [];

function addLog(type, msg) {
  const time = new Date().toLocaleTimeString('en-IN', { hour12: false });
  const entry = `[${time}] [${type.toUpperCase()}] ${msg}`;
  recentLogs.unshift(entry);
  if (recentLogs.length > 50) recentLogs.pop();
  console.log(entry);
}

// ─── BAILEYS INITIALIZATION & AUTO-RECONNECT ─────────────────────────────────
async function startSocket() {
  try {
    addLog('info', 'Initializing Baileys OpenWA Socket...');
    connectionStatus = 'CONNECTING';

    const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
      version,
      auth: state,
      printQRInTerminal: true,
      logger: pino({ level: 'silent' }),
      browser: ['ZenOS Founder Cockpit', 'Chrome', '1.0.0'],
      syncFullHistory: false,
      markOnlineOnConnect: true,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        currentQR = qr;
        connectionStatus = 'SCAN_QR';
        addLog('qr', 'New QR Code generated! Ready to scan on dashboard.');
      }

      if (connection === 'close') {
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
        connectionStatus = 'DISCONNECTED';
        currentQR = null;
        connectedNumber = null;
        addLog('warn', `Connection closed (Code: ${statusCode}). Reconnecting: ${shouldReconnect}`);

        if (shouldReconnect) {
          setTimeout(startSocket, 3000);
        } else {
          addLog('error', 'Logged out from device. Session wiped. Restart to pair again.');
          try {
            fs.rmSync(SESSION_DIR, { recursive: true, force: true });
          } catch (_) {}
          setTimeout(startSocket, 3000);
        }
      } else if (connection === 'open') {
        connectionStatus = 'CONNECTED';
        currentQR = null;
        const userJid = sock.user?.id || '';
        connectedNumber = userJid.split(':')[0].split('@')[0];
        addLog('success', `WhatsApp Connected successfully! Phone: +${connectedNumber}`);
      }
    });

    // Inbound Messages (Customer Replies -> ZenOS Webhook)
    sock.ev.on('messages.upsert', async (m) => {
      if (m.type !== 'notify') return;
      for (const msg of m.messages) {
        if (msg.key.fromMe) continue; // Ignore messages sent by ourselves

        const remoteJid = msg.key.remoteJid || '';
        if (remoteJid.includes('@g.us') || remoteJid.includes('status@broadcast')) continue; // Ignore groups & status

        const senderPhone = remoteJid.split('@')[0];
        const textContent =
          msg.message?.conversation ||
          msg.message?.extendedTextMessage?.text ||
          msg.message?.buttonsResponseMessage?.selectedDisplayText ||
          msg.message?.templateButtonReplyMessage?.selectedDisplayText ||
          '';

        addLog('inbound', `From +${senderPhone}: "${textContent}"`);

        // Forward to ZenOS webhook using native fetch
        try {
          await fetch(ZENOS_WEBHOOK, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              event: 'message.received',
              sender: senderPhone,
              text: textContent,
              timestamp: msg.messageTimestamp,
              message_id: msg.key.id,
            }),
            signal: AbortSignal.timeout(5000),
          });
          addLog('webhook', `Dispatched to ZenOS Webhook for +${senderPhone}`);
        } catch (webhookErr) {
          // If ZenOS is not running on 5000 right now, log silently
          addLog('warn', `ZenOS webhook offline (${webhookErr.message})`);
        }
      }
    });
  } catch (err) {
    addLog('error', `Socket error: ${err.message}`);
    setTimeout(startSocket, 5000);
  }
}

// Helper: Normalize phone to JID
function phoneToJid(phone) {
  let clean = String(phone || '').replace(/\D/g, '');
  if (clean.length === 10 && ['6', '7', '8', '9'].includes(clean[0])) {
    clean = '91' + clean;
  }
  if (clean.startsWith('0')) {
    clean = '91' + clean.slice(1);
  }
  return `${clean}@s.whatsapp.net`;
}

// ─── DASHBOARD UI ROUTE ───────────────────────────────────────────────────────
app.get('/', async (req, res) => {
  let qrImageHtml = '';
  if (connectionStatus === 'CONNECTED') {
    qrImageHtml = `
      <div style="background:#ecfdf5;border:2px solid #10b981;border-radius:16px;padding:30px;text-align:center;">
        <div style="font-size:48px;margin-bottom:10px;">✅</div>
        <h2 style="color:#065f46;margin:0 0 6px;">WhatsApp Connected!</h2>
        <p style="color:#047857;font-size:16px;font-weight:700;margin:0;">Active Number: +${connectedNumber || 'Paired'}</p>
        <p style="color:#059669;font-size:13px;margin-top:8px;">Ready to send Order Confirmations, COD Verifications, and RTO Killer discounts.</p>
      </div>
    `;
  } else if (currentQR) {
    const qrDataUrl = await QRCode.toDataURL(currentQR, { margin: 2, scale: 7 });
    qrImageHtml = `
      <div style="background:#ffffff;border:1px solid #cbd5e1;border-radius:16px;padding:24px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.06);">
        <h3 style="margin:0 0 12px;color:#0f172a;">Scan QR with WhatsApp</h3>
        <img src="${qrDataUrl}" alt="WhatsApp QR Code" style="width:260px;height:260px;border-radius:12px;border:1px solid #e2e8f0;display:inline-block;" />
        <p style="color:#64748b;font-size:13px;margin:12px 0 0;">Open WhatsApp on phone &gt; Linked Devices &gt; Link a Device.</p>
      </div>
    `;
  } else {
    qrImageHtml = `
      <div style="background:#f8fafc;border:1px dashed #cbd5e1;border-radius:16px;padding:40px;text-align:center;">
        <div style="font-size:36px;margin-bottom:8px;">⏳</div>
        <h3 style="color:#475569;margin:0;">Initializing Engine...</h3>
        <p style="color:#94a3b8;font-size:13px;margin-top:6px;">Generating pairing QR code in 2 seconds...</p>
      </div>
    `;
  }

  const logsHtml = recentLogs.map((l) => `<div style="font-family:monospace;font-size:12px;padding:3px 0;border-bottom:1px solid #334155;">${l}</div>`).join('');

  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenWA Gateway — ZenOS Dashboard</title>
  <meta http-equiv="refresh" content="8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
    .container { max-width: 900px; margin: 0 auto; }
    .header { display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 1px solid #334155; margin-bottom: 24px; }
    .badge { padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; }
    .badge-connected { background: #10b981; color: #fff; }
    .badge-scan { background: #f59e0b; color: #000; }
    .badge-disconnected { background: #ef4444; color: #fff; }
    .card { background: #1e293b; border-radius: 16px; padding: 20px; border: 1px solid #334155; margin-bottom: 20px; }
    .btn { background: #2563eb; color: #fff; border: 0; padding: 10px 18px; border-radius: 8px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; }
    .btn-danger { background: #dc2626; }
    input, textarea { width: 100%; box-sizing: border-box; padding: 10px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; margin-top: 6px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1 style="margin:0;font-size:22px;color:#38bdf8;">⚡ OpenWA Gateway — ZenOS</h1>
        <p style="margin:4px 0 0;font-size:13px;color:#94a3b8;">High-Speed, 100% Free WhatsApp Automation & RTO Killer</p>
      </div>
      <div>
        <span class="badge ${connectionStatus === 'CONNECTED' ? 'badge-connected' : connectionStatus === 'SCAN_QR' ? 'badge-scan' : 'badge-disconnected'}">
          ● ${connectionStatus}
        </span>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
      <div>
        ${qrImageHtml}
        ${connectionStatus === 'CONNECTED' ? `
          <div style="margin-top:14px;text-align:center;">
            <a href="/api/sessions/zenos/disconnect" class="btn btn-danger" style="font-size:12px;padding:6px 14px;" onclick="return confirm('Disconnect WhatsApp?');">Unlink & Reset Device</a>
          </div>
        ` : ''}

        <div class="card" style="margin-top:20px;">
          <h3 style="margin:0 0 10px;font-size:15px;color:#38bdf8;">🔎 WhatsApp Number Checker</h3>
          <p style="font-size:12px;color:#94a3b8;margin:0 0 10px;">Check if a customer number is registered on WhatsApp before dispatching COD orders.</p>
          <div style="display:flex;gap:8px;">
            <input type="text" id="chkPhone" placeholder="Enter 10-digit number" style="margin:0;" />
            <button type="button" class="btn" onclick="checkNumber()" style="white-space:nowrap;">Check</button>
          </div>
          <div id="chkResult" style="margin-top:10px;font-size:13px;font-weight:700;"></div>
        </div>
      </div>

      <div class="card">
        <h3 style="margin:0 0 8px;font-size:15px;color:#e2e8f0;">🚀 Quick Template Testing Playground</h3>
        <p style="font-size:12px;color:#94a3b8;margin:0 0 10px;">Select a verified Zenlora quick template to test live dispatch:</p>
        
        <div style="margin-bottom:10px;">
          <label style="font-size:11px;color:#64748b;text-transform:uppercase;font-weight:700;">Template Selector</label>
          <select id="tmplSelect" onchange="applyTemplate()" style="width:100%;padding:9px;border-radius:8px;border:1px solid #475569;background:#0f172a;color:#fff;margin-top:4px;font-weight:600;">
            <option value="cod_confirm">📦 1. COD Order Confirmation</option>
            <option value="rto_prepay">💰 2. RTO Killer (15% / ₹50 Prepayment Discount)</option>
            <option value="address_fix">📍 3. Address Missing / Landmark Fix</option>
            <option value="ofd_alert">🚚 4. Out For Delivery (OFD) Alert</option>
            <option value="vip_coupon">🎁 5. VIP Post-Delivery Privilege Coupon</option>
          </select>
        </div>

        <form method="POST" action="/api/test-send">
          <label style="font-size:12px;color:#94a3b8;">Recipient Mobile (10 Digits)</label>
          <input type="text" id="sendPhone" name="phone" placeholder="e.g. 7250366344" required />

          <label style="font-size:12px;color:#94a3b8;display:block;margin-top:10px;">Message Text (WhatsApp Markdown Supported)</label>
          <textarea id="sendText" name="text" rows="5" required></textarea>

          <button type="submit" class="btn" style="margin-top:12px;width:100%;">⚡ Send WhatsApp Message</button>
        </form>
      </div>
    </div>

    <script>
      const templates = {
        cod_confirm: "Namaste Customer Ji! 🙏\\n\\nAapka order *Zenlora* par confirm ho chuka hai!\\n\\n📦 *Product:* Smart Gadget Lifestyle\\n💰 *Total Amount:* ₹349 (Cash on Delivery)\\n📍 *Address:* Sector 4, Delivery Location\\n\\nKripya confirm karein:\\n👉 *'YES'* reply karein to CONFIRM\\n👉 *'CANCEL'* reply karein to Cancel\\n\\nTeam Zenlora",
        rto_prepay: "⚡ *SPECIAL PRIVILEGE OFFER!*\\n\\nAapke order par *15% Extra Discount* mil raha hai!\\n\\n💵 Original: ~₹349~\\n🎉 *Discounted: ₹299 Only!*\\n\\n🔗 *Pay Securely via UPI:*\\nhttps://rzp.io/l/zenlora-50\\n\\n_Pay karne ke baad delivery boy ko zero cash dena hoga!_",
        address_fix: "⚠️ *Important Address Update Notice*\\n\\nNamaste Customer Ji,\\nAapke order address me House Number ya Landmark missing hai.\\n\\nKripya delivery delay ya return hone se bachane ke liye apna *Exact House/Flat No & Nearby Landmark* yaha reply karein.",
        ofd_alert: "🚚 *OUT FOR DELIVERY ALERT!*\\n\\nAapka Zenlora parcel aaj deliver hone wala hai! (COD: ₹349)\\n\\nKripya confirm karein:\\n👉 *'AVAILABLE'* reply karein agar aap receive karne ke liye ghar par hain.",
        vip_coupon: "Dhanyawaad! 🙏 Aapka order deliver ho gaya hai. Next order par *15% OFF* ke liye use karein code: *ZEN15*"
      };

      function applyTemplate() {
        const val = document.getElementById('tmplSelect').value;
        if (templates[val]) document.getElementById('sendText').value = templates[val];
      }
      applyTemplate();

      async function checkNumber() {
        const phone = document.getElementById('chkPhone').value.trim();
        const resEl = document.getElementById('chkResult');
        if (!phone) { resEl.innerHTML = '<span style=\"color:#f87171;\">Please enter a phone number</span>'; return; }
        resEl.innerHTML = '<span style=\"color:#38bdf8;\">Checking on WhatsApp...</span>';
        try {
          const res = await fetch('/api/check-number', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ phone })
          });
          const data = await res.json();
          if (data.exists) {
            resEl.innerHTML = '<span style=\"color:#10b981;\">✅ Phone has active WhatsApp! (JID: ' + data.jid + ')</span>';
          } else {
            resEl.innerHTML = '<span style=\"color:#f87171;\">❌ Phone is NOT registered on WhatsApp.</span>';
          }
        } catch (err) {
          resEl.innerHTML = '<span style=\"color:#f87171;\">Error: ' + err.message + '</span>';
        }
      }
    </script>

    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <h3 style="margin:0;font-size:14px;color:#94a3b8;">📜 Live Message & Gateway Activity Log</h3>
        <span style="font-size:11px;color:#64748b;">Auto-refreshing every 8s</span>
      </div>
      <div style="max-height:180px;overflow-y:auto;background:#0b1120;padding:12px;border-radius:10px;border:1px solid #1e293b;">
        ${logsHtml || '<span style="color:#64748b;font-size:12px;">No activity yet. Scan QR to connect.</span>'}
      </div>
    </div>
  </div>
</body>
</html>`);
});

// ─── OPENWA REST API SPECIFICATION ENDPOINTS ──────────────────────────────────

// 1. Session Status
app.get(['/api/sessions', '/api/sessions/:sessionId'], (req, res) => {
  res.json({
    id: req.params.sessionId || 'zenos',
    status: connectionStatus === 'CONNECTED' ? 'WORKING' : connectionStatus === 'SCAN_QR' ? 'SCAN_QR' : 'STOPPED',
    phone: connectedNumber,
    engine: 'baileys',
  });
});

// 2. Session QR Code
app.get('/api/sessions/:sessionId/qr', async (req, res) => {
  if (!currentQR) {
    return res.status(connectionStatus === 'CONNECTED' ? 200 : 404).json({
      status: connectionStatus,
      qr: null,
      message: connectionStatus === 'CONNECTED' ? 'Already connected' : 'QR not yet ready',
    });
  }
  const qrDataUrl = await QRCode.toDataURL(currentQR);
  res.json({ status: 'SCAN_QR', qr: qrDataUrl });
});

// 2B. WhatsApp Number Checker (OpenWA Spec)
app.post(['/api/sessions/:sessionId/check-number', '/api/check-number'], async (req, res) => {
  try {
    if (connectionStatus !== 'CONNECTED' || !sock) {
      return res.status(503).json({ status: 'error', message: 'WhatsApp Gateway not connected' });
    }
    const phone = req.body.phone || req.query.phone;
    if (!phone) {
      return res.status(400).json({ status: 'error', message: 'Phone number is required' });
    }
    const jid = phoneToJid(phone);
    const results = await sock.onWhatsApp(jid);
    const result = Array.isArray(results) && results.length > 0 ? results[0] : null;
    return res.json({
      status: 'success',
      phone: phone,
      jid: jid,
      exists: Boolean(result?.exists),
      info: result || null
    });
  } catch (error) {
    return res.status(500).json({ status: 'error', message: error.message });
  }
});

// 2C. Send Document / PDF (OpenWA Spec)
app.post(['/api/sessions/:sessionId/messages/send-document', '/api/sendDocument'], async (req, res) => {
  try {
    if (connectionStatus !== 'CONNECTED' || !sock) {
      return res.status(503).json({ status: 'error', message: 'WhatsApp Gateway not connected.' });
    }
    const recipient = req.body.chatId || req.body.phone || req.body.to;
    const docUrl = req.body.url || req.body.document;
    const fileName = req.body.fileName || 'invoice.pdf';
    const caption = req.body.caption || '';
    const mimetype = req.body.mimetype || 'application/pdf';

    if (!recipient || !docUrl) {
      return res.status(400).json({ status: 'error', message: 'Missing recipient or document url' });
    }
    const jid = phoneToJid(recipient);
    addLog('outbound', `Sending document ${fileName} to ${jid}...`);

    const result = await sock.sendMessage(jid, {
      document: { url: docUrl },
      mimetype: mimetype,
      fileName: fileName,
      caption: caption,
    });
    return res.json({ status: 'success', id: result?.key?.id, recipient: jid });
  } catch (error) {
    addLog('error', `Send document error: ${error.message}`);
    return res.status(500).json({ status: 'error', message: error.message });
  }
});

// 3. Send Text Message (OpenWA Standard Spec)
app.post(['/api/sessions/:sessionId/messages/send-text', '/api/sendText'], async (req, res) => {
  try {
    if (connectionStatus !== 'CONNECTED' || !sock) {
      return res.status(503).json({
        status: 'error',
        message: 'WhatsApp Gateway not connected. Please scan QR at http://localhost:2785 first.',
      });
    }

    const recipient = req.body.chatId || req.body.phone || req.body.to;
    const text = req.body.text || req.body.body || req.body.message;

    if (!recipient || !text) {
      return res.status(400).json({ status: 'error', message: 'Missing recipient or text' });
    }

    const jid = phoneToJid(recipient);
    addLog('outbound', `Sending text to ${jid}...`);

    const result = await sock.sendMessage(jid, { text: String(text) });
    addLog('success', `Message delivered to ${jid}! (ID: ${result?.key?.id})`);

    return res.json({
      status: 'success',
      id: result?.key?.id,
      timestamp: result?.messageTimestamp,
      recipient: jid,
    });
  } catch (error) {
    addLog('error', `Send text error: ${error.message}`);
    return res.status(500).json({ status: 'error', message: error.message });
  }
});

// 3B. Send Buttons / Interactive Choices (OpenWA Standard Spec)
app.post(['/api/sessions/:sessionId/messages/send-buttons', '/api/sendButtons'], async (req, res) => {
  try {
    if (connectionStatus !== 'CONNECTED' || !sock) {
      return res.status(503).json({
        status: 'error',
        message: 'WhatsApp Gateway not connected. Please scan QR at http://localhost:2785 first.',
      });
    }

    const recipient = req.body.chatId || req.body.phone || req.body.to;
    let text = req.body.text || req.body.body || req.body.message || '';
    const buttons = req.body.buttons || [];
    const footer = req.body.footer || 'Zenlora Store • Official Verification';

    if (!recipient || !text) {
      return res.status(400).json({ status: 'error', message: 'Missing recipient or text' });
    }

    if (Array.isArray(buttons) && buttons.length > 0) {
      text += '\n\n*Choose an option by replying with the number or keyword:*';
      buttons.forEach((btn, idx) => {
        const btnText = btn.text || btn.title || btn.id || `Option ${idx + 1}`;
        const emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣'][idx] || '👉';
        text += `\n${emoji} *${btnText}*`;
      });
      if (footer) text += `\n\n_${footer}_`;
    }

    const jid = phoneToJid(recipient);
    addLog('outbound', `Sending button choices to ${jid}...`);

    const result = await sock.sendMessage(jid, { text: String(text) });
    addLog('success', `Button choices delivered to ${jid}! (ID: ${result?.key?.id})`);

    return res.json({
      status: 'success',
      id: result?.key?.id,
      timestamp: result?.messageTimestamp,
      recipient: jid,
      interactive_buttons: true,
    });
  } catch (error) {
    addLog('error', `Send buttons error: ${error.message}`);
    return res.status(500).json({ status: 'error', message: error.message });
  }
});

// 4. Send Image Message (OpenWA Standard Spec)
app.post(['/api/sessions/:sessionId/messages/send-image', '/api/sendImage'], async (req, res) => {
  try {
    if (connectionStatus !== 'CONNECTED' || !sock) {
      return res.status(503).json({ status: 'error', message: 'WhatsApp Gateway not connected.' });
    }

    const recipient = req.body.chatId || req.body.phone || req.body.to;
    const imageUrl = req.body.url || req.body.image;
    const caption = req.body.caption || '';

    if (!recipient || !imageUrl) {
      return res.status(400).json({ status: 'error', message: 'Missing recipient or image url' });
    }

    const jid = phoneToJid(recipient);
    addLog('outbound', `Sending image to ${jid}...`);

    const result = await sock.sendMessage(jid, {
      image: { url: imageUrl },
      caption: caption,
    });

    return res.json({
      status: 'success',
      id: result?.key?.id,
      recipient: jid,
    });
  } catch (error) {
    addLog('error', `Send image error: ${error.message}`);
    return res.status(500).json({ status: 'error', message: error.message });
  }
});

// 5. Test Send from Dashboard form
app.post('/api/test-send', async (req, res) => {
  const { phone, text } = req.body;
  if (connectionStatus !== 'CONNECTED') {
    return res.send('<script>alert("Error: WhatsApp is not connected yet! Scan the QR code first."); window.location.href="/";</script>');
  }
  try {
    const jid = phoneToJid(phone);
    await sock.sendMessage(jid, { text });
    res.send('<script>alert("Message sent successfully to ' + phone + '!"); window.location.href="/";</script>');
  } catch (err) {
    res.send('<script>alert("Send failed: ' + err.message + '"); window.location.href="/";</script>');
  }
});

// 6. Disconnect / Unlink
app.get('/api/sessions/:sessionId/disconnect', async (req, res) => {
  try {
    if (sock) {
      await sock.logout();
    }
  } catch (_) {}
  try {
    fs.rmSync(SESSION_DIR, { recursive: true, force: true });
  } catch (_) {}
  connectionStatus = 'DISCONNECTED';
  connectedNumber = null;
  currentQR = null;
  addLog('info', 'Device unlinked. Restarting socket...');
  setTimeout(startSocket, 2000);
  res.redirect('/');
});

// Start listening & launch Baileys socket
app.listen(PORT, () => {
  console.log(`=======================================================`);
  console.log(`⚡ OpenWA Gateway for ZenOS running at http://localhost:${PORT}`);
  console.log(`📱 Open your browser to scan QR and connect WhatsApp!`);
  console.log(`=======================================================`);
  startSocket();
});
