# ZenOS browser bridge setup

This extension only acts after a founder clicks **Review & Sync Order** or **Load confirmed order**. It does not submit a Wukusy order or silently send a WhatsApp message.

## 1. Configure the ZenOS backend

1. Deploy the ZenOS backend from its separate repository with a persistent PostgreSQL database and the required Vercel environment variables. Follow that repository's `README.md`.
2. Generate a random `ZENOS_EXTENSION_API_KEY` of at least 32 characters and set it as a Vercel environment variable. Use a different value from the admin password and webhook tokens.
3. After updating Vercel environment variables, redeploy the backend.

## 2. Load the extension

1. Open `brave://extensions` or `chrome://extensions`.
2. Turn on **Developer mode**.
3. Select **Load unpacked** and choose this `extension` folder.
4. Pin **ZenOS Bridge** to the browser toolbar.

## 3. Store the local extension connection

1. Open the extension popup.
2. Enter the deployed HTTPS backend URL, for example `https://your-zenos-project.vercel.app`.
3. Paste the same `ZENOS_EXTENSION_API_KEY` set on Vercel, then choose **Save connection settings**.
4. Confirm the backend status changes from **Setup required** to **Backend reachable**.

The key is kept in this browser's extension local storage, not in the source code or synchronized across browser profiles. Do not share it or paste it into a webpage.

## 4. SmartBiz order review

1. Open the order in SmartBiz and click **ZenOS: Review & Sync Order**.
2. Check every extracted field. Detection is heuristic; never assume a suggested name, phone, address, pincode, amount, city, state, or order reference is correct. Blank values are not fabricated.
3. Record the evidence/source for WhatsApp consent only when you have actually verified that consent.
4. Mark order-update opt-in only when the customer explicitly opted in. Mark promotional opt-in separately before sending the 15% offer.
5. **Save without messaging** only stores the order. **Save & send approved template** sends only when the backend has an approved template configured and both opt-ins are recorded.

WhatsApp templates must be approved in WhatsApp Manager and use the body variables and quick-reply button order documented in the ZenOS setup guide. A `wa.me` link only opens a prefilled chat; a person must press Send.

## 5. Wukusy fulfillment

The Wukusy panel requests orders from ZenOS and only lists COD-confirmed or prepaid-paid orders with a complete shipping address. Choose the right order, review the preview, and click **Fill address fields**. The extension fills matching form fields only; the final fulfillment submission remains a manual action.

If the Wukusy checkout changes its form markup, stop and review the fields before using autofill. Never place the fulfillment order based on a mismatched preview.

## Product/privacy safeguards

- Customer data is personal information. Use it only for the order purpose, according to platform terms and applicable consent/privacy requirements.
- The extension does not persist a local copy of order data after sync. The backend stores order and message records in its configured database.
- A WhatsApp cancellation button records a cancellation request; it does **not** cancel the marketplace order or stop a courier. Manually verify and cancel through the seller portal.
- This project currently has no official SmartBiz or Wukusy fulfillment API integration. Do not treat page scraping/autofill as an official integration.
