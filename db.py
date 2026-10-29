from __future__ import annotations
from typing import Any, Optional, Dict, List, Union
import sqlite3
import os
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.environ.get("ZENOS_DB_PATH", os.path.join(os.path.dirname(__file__), "zenos.db"))


class _CursorAdapter:
    def __init__(self, cursor, postgres):
        self._cursor = cursor
        self._postgres = postgres

    def execute(self, query, params=None):
        if self._postgres:
            query = query.replace("?", "%s")
        if params is None:
            self._cursor.execute(query)
        else:
            self._cursor.execute(query, params)
        return self

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _ConnectionAdapter:
    def __init__(self, connection, postgres):
        self._connection = connection
        self._postgres = postgres

    def cursor(self):
        return _CursorAdapter(self._connection.cursor(), self._postgres)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_db():
    if os.environ.get("RENDER") and not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL environment variable is required on Render")

    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        return _ConnectionAdapter(
            psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10),
            postgres=True,
        )

    target_path = "/tmp/zenos.db" if os.environ.get("VERCEL") else DB_PATH
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    connection = sqlite3.connect(target_path)
    connection.row_factory = sqlite3.Row
    return _ConnectionAdapter(connection, postgres=False)


def init_db():
    connection = get_db()
    cursor = connection.cursor()
    primary_key = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS orders (
        id {primary_key},
        order_ref TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        product_name TEXT NOT NULL,
        sku TEXT DEFAULT '',
        amount INTEGER NOT NULL,
        prepaid_amount INTEGER,
        discount_amount INTEGER,
        address TEXT NOT NULL DEFAULT '',
        pincode TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION',
        rto_risk_score INTEGER DEFAULT 0,
        razorpay_link TEXT DEFAULT '',
        wukusy_status TEXT DEFAULT 'READY_TO_SYNC',
        wukusy_order_id TEXT DEFAULT '',
        tracking_awb TEXT DEFAULT '',
        courier_name TEXT DEFAULT '',
        whatsapp_opt_in INTEGER NOT NULL DEFAULT 0,
        marketing_opt_in INTEGER NOT NULL DEFAULT 0,
        consent_source TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS messages (
        id {primary_key},
        phone TEXT NOT NULL,
        customer_name TEXT NOT NULL DEFAULT '',
        direction TEXT NOT NULL,
        message_type TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        button_id TEXT DEFAULT '',
        wa_message_id TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS messages_provider_id_unique
        ON messages (wa_message_id)
        WHERE wa_message_id IS NOT NULL AND wa_message_id != ''
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS system_logs (
        id {primary_key},
        level TEXT NOT NULL,
        source TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processed_webhooks (
        provider TEXT NOT NULL,
        event_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (provider, event_id)
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS abandoned_carts (
        id {primary_key},
        phone TEXT NOT NULL,
        customer_name TEXT NOT NULL DEFAULT '',
        cart_items TEXT NOT NULL DEFAULT '',
        cart_value REAL NOT NULL DEFAULT 0.0,
        checkout_url TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ABANDONED',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        touch1_at TIMESTAMP,
        touch2_at TIMESTAMP,
        touch3_at TIMESTAMP,
        recovered_at TIMESTAMP,
        cancelled_at TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_abandoned_carts_phone ON abandoned_carts(phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_abandoned_carts_status ON abandoned_carts(status)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS messages_wa_message_id_uq ON messages(wa_message_id) WHERE wa_message_id <> ''")
    if DATABASE_URL:
        cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS whatsapp_opt_in INTEGER NOT NULL DEFAULT 0")
        cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS marketing_opt_in INTEGER NOT NULL DEFAULT 0")
        cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS consent_source TEXT NOT NULL DEFAULT ''")
    else:
        cursor.execute("PRAGMA table_info(orders)")
        existing_columns = {row["name"] for row in cursor.fetchall()}
        for column, definition in (
            ("sku", "TEXT NOT NULL DEFAULT ''"),
            ("whatsapp_opt_in", "INTEGER NOT NULL DEFAULT 0"),
            ("marketing_opt_in", "INTEGER NOT NULL DEFAULT 0"),
            ("consent_source", "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in existing_columns:
                cursor.execute(f"ALTER TABLE orders ADD COLUMN {column} {definition}")
    connection.commit()
    connection.close()
    logger.info("ZenOS database schema initialized.")


def log_event(level, source, message):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO system_logs (level, source, message) VALUES (?, ?, ?)", (level, source, message))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging event: {e}")

def save_or_update_order(order_data):
    try:
        conn = get_db()
        cursor = conn.cursor()
        order_ref = order_data.get("order_ref", f"ZEN-{order_data.get('order_id', '1001')}")
        
        # Calculate address risk score
        address = order_data.get("address", "")
        pincode = str(order_data.get("pincode", ""))
        score = 95
        if len(address) < 15:
            score -= 25
        if not any(c.isdigit() for c in address):
            score -= 15
        if len(pincode) != 6:
            score -= 20
        if score < 20:
            score = 20

        amount = int(order_data["amount"])
        savings = round(amount * 0.15)
        prepaid = amount - savings

        cursor.execute("""
        INSERT INTO orders (
            order_ref, customer_name, phone, product_name, sku, amount, prepaid_amount, discount_amount,
            address, pincode, city, state, status, rto_risk_score, razorpay_link, wukusy_status,
            whatsapp_opt_in, marketing_opt_in, consent_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_ref) DO UPDATE SET
            customer_name = excluded.customer_name,
            phone = excluded.phone,
            product_name = excluded.product_name,
            sku = CASE WHEN excluded.sku != '' THEN excluded.sku ELSE orders.sku END,
            amount = excluded.amount,
            address = CASE WHEN excluded.address != '' THEN excluded.address ELSE orders.address END,
            pincode = CASE WHEN excluded.pincode != '' THEN excluded.pincode ELSE orders.pincode END,
            city = CASE WHEN excluded.city != '' THEN excluded.city ELSE orders.city END,
            state = CASE WHEN excluded.state != '' THEN excluded.state ELSE orders.state END,
            status = CASE
                WHEN orders.status IN ('PENDING_VERIFICATION', 'PENDING_WHATSAPP_CONFIRMATION',
                    'PENDING_WHATSAPP_OPT_IN', 'RTO_RISK_HIGH')
                THEN excluded.status ELSE orders.status END,
            whatsapp_opt_in = CASE WHEN orders.whatsapp_opt_in = 1 OR excluded.whatsapp_opt_in = 1 THEN 1 ELSE 0 END,
            marketing_opt_in = CASE WHEN orders.marketing_opt_in = 1 OR excluded.marketing_opt_in = 1 THEN 1 ELSE 0 END,
            consent_source = CASE WHEN excluded.consent_source != '' THEN excluded.consent_source ELSE orders.consent_source END,
            updated_at = CURRENT_TIMESTAMP
        """, (
            order_ref,
            order_data.get("customer_name", "Valued Customer"),
            order_data.get("phone", ""),
            order_data.get("product_name", "Zenlora Lifestyle Item"),
            order_data.get("sku", ""),
            amount,
            prepaid,
            savings,
            address,
            pincode,
            order_data.get("city", ""),
            order_data.get("state", ""),
            order_data.get("status", "PENDING_VERIFICATION"),
            score,
            order_data.get("razorpay_link", ""),
            order_data.get("wukusy_status", "WAITING_FOR_CONFIRMATION"),
            int(bool(order_data.get("whatsapp_opt_in"))),
            int(bool(order_data.get("marketing_opt_in"))),
            order_data.get("consent_source", ""),
        ))
        conn.commit()
        conn.close()
        log_event("SUCCESS", "SMARTBIZ", f"Order {order_ref} synced to ZenOS.")
        try:
            mark_cart_recovered(phone=order_data.get("phone"))
        except Exception as err:
            logger.debug("Failed auto-recovering cart for order %s: %s", order_ref, err)
        return True
    except Exception as e:
        logger.error("Error saving order")
        log_event("ERROR", "DATABASE", "Failed to save an order.")
        return False

def update_order_status(order_ref_or_phone, new_status, extra_fields=None):
    try:
        conn = get_db()
        cursor = conn.cursor()

        order_ref_or_phone = str(order_ref_or_phone).strip()
        clean_phone = "".join(ch for ch in order_ref_or_phone if ch.isdigit())
        looks_like_phone = len(clean_phone) in {10, 12} and (
            len(clean_phone) == 10 or clean_phone.startswith("91")
        )
        if looks_like_phone:
            clean_phone = clean_phone[-10:]
            cursor.execute(
                "SELECT order_ref FROM orders WHERE phone LIKE ?",
                (f"%{clean_phone}",),
            )
            matches = cursor.fetchall()
            if len(matches) != 1:
                conn.close()
                return False
            where_clause = "order_ref = ?"
            where_params = [matches[0]["order_ref"]]
        else:
            where_clause = "order_ref = ?"
            where_params = [order_ref_or_phone]

        set_clause = "status = ?, updated_at = CURRENT_TIMESTAMP"
        params = [new_status]

        if extra_fields:
            for k, v in extra_fields.items():
                if k not in {"razorpay_link", "prepaid_amount", "discount_amount", "wukusy_status", "wukusy_order_id"}:
                    raise ValueError("Unsupported order update field")
                set_clause += f", {k} = ?"
                params.append(v)

        params.extend(where_params)
        cursor.execute(f"""
        UPDATE orders 
        SET {set_clause}
        WHERE {where_clause}
        """, params)

        updated = cursor.rowcount == 1
        conn.commit()
        conn.close()
        if updated:
            log_event("INFO", "ORDER_STATUS", f"Order status updated to {new_status}.")
        return updated
    except Exception as e:
        logger.error("Error updating order status")
        return False

def record_message(phone, customer_name, direction, message_type, body, button_id="", wa_message_id=""):
    try:
        conn = get_db()
        cursor = conn.cursor()
        clean_phone = str(phone).replace("+", "").replace(" ", "").replace("-", "")
        if len(clean_phone) == 10:
            clean_phone = f"91{clean_phone}"

        cursor.execute("""
        INSERT INTO messages (phone, customer_name, direction, message_type, body, button_id, wa_message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        """, (clean_phone, customer_name, direction, message_type, body, button_id, wa_message_id))
        inserted = cursor.rowcount == 1
        conn.commit()
        conn.close()
        return inserted
    except Exception as e:
        logger.error("Error recording message")
        return False


def claim_webhook_event(provider, event_id):
    if not provider or not event_id:
        return False
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO processed_webhooks (provider, event_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
        (provider, event_id),
    )
    claimed = cursor.rowcount == 1
    connection.commit()
    connection.close()
    return claimed


def get_order(order_ref):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_ref = ?", (order_ref,))
    row = cursor.fetchone()
    connection.close()
    return dict(row) if row else None


def get_open_orders_for_phone(phone):
    clean_phone = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
    if len(clean_phone) < 10:
        return []
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT * FROM orders
           WHERE phone LIKE ?
             AND status NOT IN ('CANCELLED', 'CUSTOMER_CANCELLED', 'DELIVERED', 'RETURNED')
           ORDER BY id DESC LIMIT 10""",
        (f"%{clean_phone}",),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def update_order_address(order_ref, address, pincode, city, state):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        """UPDATE orders
           SET address = ?, pincode = ?, city = ?, state = ?,
               status = CASE WHEN status = 'RTO_RISK_HIGH'
                   THEN CASE WHEN whatsapp_opt_in = 1
                       THEN 'PENDING_WHATSAPP_CONFIRMATION'
                       ELSE 'PENDING_WHATSAPP_OPT_IN' END
                   ELSE status END,
               updated_at = CURRENT_TIMESTAMP
           WHERE order_ref = ?""",
        (address, pincode, city, state, order_ref),
    )
    updated = cursor.rowcount == 1
    connection.commit()
    connection.close()
    return updated


def revoke_whatsapp_consent(phone):
    clean_phone = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
    if len(clean_phone) < 10:
        return 0
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        """UPDATE orders
           SET whatsapp_opt_in = 0, marketing_opt_in = 0,
               consent_source = 'Customer STOP via WhatsApp',
               updated_at = CURRENT_TIMESTAMP
           WHERE phone LIKE ?""",
        (f"%{clean_phone}",),
    )
    affected = cursor.rowcount
    connection.commit()
    connection.close()
    return affected


def get_last_inbound_at(phone):
    clean_phone = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
    if len(clean_phone) < 10:
        return None
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT MAX(created_at) AS latest FROM messages WHERE phone LIKE ? AND direction = 'INBOUND'",
        (f"%{clean_phone}",),
    )
    row = cursor.fetchone()
    connection.close()
    return row["latest"] if row else None


def get_confirmed_wukusy_orders():
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT order_ref, customer_name, phone, address, pincode, city, state, status
        FROM orders
        WHERE status IN ('CONFIRMED_COD', 'PREPAID_PAID')
          AND wukusy_status NOT IN ('SUBMITTED', 'DISPATCHED')
          AND address <> '' AND pincode <> '' AND city <> '' AND state <> ''
        ORDER BY id DESC
        LIMIT 50
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows

def get_dashboard_data():
    conn = get_db()
    cursor = conn.cursor()

    # 1. KPIs
    cursor.execute("SELECT COUNT(*) as total_orders FROM orders")
    total_orders = cursor.fetchone()["total_orders"]

    cursor.execute("SELECT COUNT(*) as prepaid_count FROM orders WHERE status = 'PREPAID_PAID'")
    prepaid_count = cursor.fetchone()["prepaid_count"]

    cursor.execute("SELECT COUNT(*) as cod_confirmed FROM orders WHERE status = 'CONFIRMED_COD'")
    cod_confirmed = cursor.fetchone()["cod_confirmed"]

    cursor.execute("SELECT COUNT(*) as ofd_count FROM orders WHERE status IN ('OUT_FOR_DELIVERY', 'DELIVERY_COLLECT_CONFIRMED')")
    ofd_count = cursor.fetchone()["ofd_count"]

    cursor.execute("SELECT COUNT(*) as cancelled_count FROM orders WHERE status = 'CANCELLED'")
    cancelled_count = cursor.fetchone()["cancelled_count"]

    cursor.execute("SELECT COUNT(*) as high_risk_count FROM orders WHERE rto_risk_score < 60 OR status = 'RTO_RISK_HIGH'")
    high_risk_count = cursor.fetchone()["high_risk_count"]

    cursor.execute("SELECT AVG(rto_risk_score) as avg_rto FROM orders WHERE status != 'CANCELLED'")
    avg_rto_row = cursor.fetchone()
    avg_rto_score = round(avg_rto_row["avg_rto"] or 0, 1)

    cursor.execute("SELECT SUM(amount) as total_gmv FROM orders WHERE status != 'CANCELLED'")
    gmv_row = cursor.fetchone()
    total_gmv = gmv_row["total_gmv"] or 0

    cursor.execute("SELECT SUM(discount_amount) as total_discount FROM orders WHERE status = 'PREPAID_PAID'")
    disc_row = cursor.fetchone()
    total_discount_given = disc_row["total_discount"] or 0

    # 2. Recent Orders (Sorted Newest First)
    cursor.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 50")
    orders = [dict(row) for row in cursor.fetchall()]

    from services.address_validator import evaluate_address_health
    incomplete_addr_count = 0
    for o in orders:
        h = evaluate_address_health(o.get("address", ""), o.get("pincode", ""))
        o["address_health"] = h
        if h["status"] != "COMPLETE":
            incomplete_addr_count += 1

    # 3. System Logs
    cursor.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT 40")
    logs = [dict(row) for row in cursor.fetchall()]

    # 4. Group Messages into Customer Conversations
    cursor.execute("SELECT * FROM messages ORDER BY id ASC")
    raw_messages = [dict(row) for row in cursor.fetchall()]

    conversations = {}
    for m in raw_messages:
        phone = m["phone"]
        if phone not in conversations:
            conversations[phone] = {
                "phone": phone,
                "customer_name": m["customer_name"],
                "last_message": m["body"],
                "last_time": m["created_at"],
                "messages": []
            }
        conversations[phone]["messages"].append(m)
        conversations[phone]["last_message"] = m["body"]
        conversations[phone]["last_time"] = m["created_at"]

    conn.close()

    prepaid_ratio = round((prepaid_count / total_orders * 100), 1) if total_orders > 0 else 0
    return {
        "kpis": {
            "total_orders": total_orders,
            "prepaid_count": prepaid_count,
            "prepaid_ratio": f"{prepaid_ratio}%",
            "cod_confirmed": cod_confirmed,
            "ofd_count": ofd_count,
            "cancelled_count": cancelled_count,
            "high_risk_count": high_risk_count,
            "incomplete_addr_count": incomplete_addr_count,
            "avg_rto_score": f"{avg_rto_score}/100",
            "total_discount_given": f"₹{total_discount_given}",
            "total_gmv": f"₹{total_gmv}"
        },
        "orders": orders,
        "logs": logs,
        "conversations": conversations
    }

def update_order_fields(order_ref, fields_dict):
    """Updates specified fields of an order safely using parameter binding"""
    allowed_fields = {
        "customer_name", "phone", "amount", "product_name", "sku",
        "address", "city", "state", "pincode", "status",
        "courier_name", "tracking_awb", "rto_risk_score"
    }
    updates = {k: v for k, v in fields_dict.items() if k in allowed_fields}
    if not updates:
        return False
    try:
        conn = get_db()
        cursor = conn.cursor()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [order_ref]
        cursor.execute(f"UPDATE orders SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE order_ref = ?", values)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected > 0:
            log_event("INFO", "DATABASE", f"Order {order_ref} updated: {list(updates.keys())}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating order fields: {e}")
        return False

get_order_by_ref = get_order

def delete_order(order_ref):
    """Deletes an order permanently from database"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders WHERE order_ref = ?", (order_ref,))
        conn.commit()
        conn.close()
        log_event("WARNING", "DATABASE", f"Order {order_ref} deleted by founder.")
        return True
    except Exception as e:
        logger.error(f"Error deleting order: {e}")
        return False

def clear_all_orders():
    """Wipes all demo/test orders, conversations, and logs clean"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM messages")
        cursor.execute("DELETE FROM system_logs")
        conn.commit()
        conn.close()
        log_event("WARNING", "DATABASE", "All orders and test data wiped clean by founder.")
        return True
    except Exception as e:
        logger.error(f"Error clearing all orders: {e}")
        return False

def reseed_demo_orders():
    return False


def get_crm_conversations():
    """
    Returns aggregated chat threads optimized for 500+ chats/day triage.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.phone, m.customer_name, m.direction, m.body, m.button_id, m.created_at
        FROM messages m
        INNER JOIN (
            SELECT phone, MAX(id) as max_id
            FROM messages
            GROUP BY phone
        ) latest ON m.id = latest.max_id
        ORDER BY m.id DESC
    """)
    threads = [dict(row) for row in cursor.fetchall()]

    results = []
    for t in threads:
        phone = t["phone"]
        clean_phone = "".join(ch for ch in str(phone) if ch.isdigit())[-10:]

        cursor.execute("SELECT * FROM orders WHERE phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{clean_phone}",))
        order_row = cursor.fetchone()
        order = dict(order_row) if order_row else None

        cursor.execute("SELECT id, direction FROM messages WHERE phone = ? ORDER BY id DESC", (phone,))
        msg_rows = cursor.fetchall()
        unread_count = 0
        for mr in msg_rows:
            if mr["direction"] == "INBOUND":
                unread_count += 1
            else:
                break

        triage = "ALL"
        if t["direction"] == "INBOUND" and unread_count > 0:
            triage = "NEEDS_REPLY"
        elif order and order.get("status") == "PENDING_VERIFICATION":
            triage = "PREPAY_PENDING"
        elif order and order.get("status") == "CONFIRMED_COD":
            triage = "COD_CONFIRMED"
        elif order and order.get("status") == "PREPAID_PAID":
            triage = "PREPAID_PAID"
        elif order and order.get("status") == "CANCELLED":
            triage = "CANCELLED"

        results.append({
            "phone": phone,
            "customer_name": (order.get("customer_name") if order else None) or t["customer_name"] or "Customer",
            "last_message": t["body"],
            "last_time": t["created_at"],
            "last_direction": t["direction"],
            "unread_count": unread_count,
            "triage": triage,
            "order_ref": order.get("order_ref") if order else None,
            "order_status": order.get("status") if order else None,
            "order_amount": order.get("amount") if order else None,
            "product_name": order.get("product_name") if order else None,
            "sku": order.get("sku") if order else None,
            "whatsapp_opt_in": bool(order.get("whatsapp_opt_in")) if order else False,
            "marketing_opt_in": bool(order.get("marketing_opt_in")) if order else False,
        })

    known_phones = set("".join(ch for ch in str(t["phone"]) if ch.isdigit())[-10:] for t in threads)
    try:
        cursor.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 50")
        for o_row in cursor.fetchall():
            o = dict(o_row)
            o_clean = "".join(ch for ch in str(o.get("phone", "")) if ch.isdigit())[-10:]
            if o_clean and o_clean not in known_phones:
                known_phones.add(o_clean)
                results.append({
                    "phone": o.get("phone"),
                    "customer_name": o.get("customer_name") or "Customer",
                    "last_message": f"Order #{o.get('order_ref')} ({o.get('product_name')})",
                    "last_time": o.get("created_at"),
                    "last_direction": "SYSTEM",
                    "unread_count": 0,
                    "triage": "ALL",
                    "order_ref": o.get("order_ref"),
                    "order_status": o.get("status"),
                    "order_amount": o.get("amount"),
                    "product_name": o.get("product_name"),
                    "sku": o.get("sku", ""),
                    "whatsapp_opt_in": bool(o.get("whatsapp_opt_in")),
                    "marketing_opt_in": bool(o.get("marketing_opt_in")),
                })
    except Exception as e:
        logger.warning("Error appending orders to CRM list: %s", e)
    finally:
        conn.close()

    return results


def get_crm_thread(phone):
    """
    Returns complete conversation message stream and live order dossier for a phone.
    """
    conn = get_db()
    cursor = conn.cursor()

    clean_digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(clean_digits) < 10:
        conn.close()
        return {
            "phone": phone,
            "order": None,
            "address_health": None,
            "messages": [],
        }
    clean_phone_10 = clean_digits[-10:] if len(clean_digits) >= 10 else clean_digits

    cursor.execute("""
        SELECT * FROM messages 
        WHERE phone LIKE ? OR phone LIKE ?
        ORDER BY id ASC
    """, (f"%{clean_phone_10}", f"{clean_digits}%"))
    messages = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT * FROM orders 
        WHERE phone LIKE ? 
        ORDER BY id DESC LIMIT 1
    """, (f"%{clean_phone_10}",))
    order_row = cursor.fetchone()
    order = dict(order_row) if order_row else None

    conn.close()

    address_health = None
    if order:
        from services.address_validator import evaluate_address_health
        address_health = evaluate_address_health(order.get("address", ""), order.get("pincode", ""))

    return {
        "phone": phone,
        "order": order,
        "address_health": address_health,
        "messages": messages,
    }


def add_abandoned_cart(
    phone: str,
    customer_name: str = "",
    cart_items: Any = "",
    cart_value: float = 0.0,
    checkout_url: str = "",
    created_at: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Adds a new abandoned cart record with status 'ABANDONED'.
    """
    clean_digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    clean_phone = clean_digits[-10:] if len(clean_digits) >= 10 else clean_digits
    if not clean_phone:
        raise ValueError("A valid customer phone number is required for abandoned cart tracking")

    if isinstance(cart_items, (list, dict)):
        items_str = json.dumps(cart_items)
    else:
        items_str = str(cart_items or "").strip()

    val = float(cart_value or 0.0)
    name = str(customer_name or "").strip()
    url = str(checkout_url or "").strip()

    conn = get_db()
    cursor = conn.cursor()

    if created_at is not None:
        created_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        cursor.execute(
            """INSERT INTO abandoned_carts (
                phone, customer_name, cart_items, cart_value, checkout_url, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'ABANDONED', ?)""",
            (clean_phone, name, items_str, val, url, created_str),
        )
    else:
        cursor.execute(
            """INSERT INTO abandoned_carts (
                phone, customer_name, cart_items, cart_value, checkout_url, status
            ) VALUES (?, ?, ?, ?, ?, 'ABANDONED')""",
            (clean_phone, name, items_str, val, url),
        )

    cart_id = getattr(cursor, "lastrowid", None)
    conn.commit()

    if cart_id:
        cursor.execute("SELECT * FROM abandoned_carts WHERE id = ?", (cart_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else {
            "id": cart_id,
            "phone": clean_phone,
            "customer_name": name,
            "cart_items": items_str,
            "cart_value": val,
            "checkout_url": url,
            "status": "ABANDONED",
        }

    cursor.execute("SELECT * FROM abandoned_carts WHERE phone = ? ORDER BY id DESC LIMIT 1", (clean_phone,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {"phone": clean_phone, "status": "ABANDONED"}


def get_pending_cart_drips(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves all abandoned carts that are eligible for automated drip messages.
    """
    conn = get_db()
    cursor = conn.cursor()
    if status:
        cursor.execute(
            "SELECT * FROM abandoned_carts WHERE status = ? ORDER BY id ASC",
            (status,),
        )
    else:
        cursor.execute(
            "SELECT * FROM abandoned_carts WHERE status IN ('ABANDONED', 'TOUCH_1_SENT', 'TOUCH_2_SENT') ORDER BY id ASC"
        )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def update_cart_drip_status(
    cart_id: int,
    new_status: str,
    touch_column: Optional[str] = None,
    touch_timestamp: Optional[Any] = None,
) -> bool:
    """
    Updates the status and optional timestamp column (touch1_at, touch2_at, touch3_at, recovered_at, cancelled_at) of a cart.
    """
    valid_columns = {"touch1_at", "touch2_at", "touch3_at", "recovered_at", "cancelled_at"}
    conn = get_db()
    cursor = conn.cursor()

    if touch_column and touch_column in valid_columns:
        if touch_timestamp is not None:
            ts_str = touch_timestamp.isoformat() if hasattr(touch_timestamp, "isoformat") else str(touch_timestamp)
            cursor.execute(
                f"UPDATE abandoned_carts SET status = ?, {touch_column} = ? WHERE id = ? AND status NOT IN ('RECOVERED', 'CANCELLED')",
                (new_status, ts_str, cart_id),
            )
        else:
            cursor.execute(
                f"UPDATE abandoned_carts SET status = ?, {touch_column} = CURRENT_TIMESTAMP WHERE id = ? AND status NOT IN ('RECOVERED', 'CANCELLED')",
                (new_status, cart_id),
            )
    else:
        cursor.execute(
            "UPDATE abandoned_carts SET status = ? WHERE id = ? AND status NOT IN ('RECOVERED', 'CANCELLED')",
            (new_status, cart_id),
        )

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def mark_cart_recovered(cart_id: Optional[int] = None, phone: Optional[str] = None) -> int:
    """
    Marks one or more abandoned carts as RECOVERED when an order is completed.
    """
    conn = get_db()
    cursor = conn.cursor()
    count = 0
    if cart_id is not None and str(cart_id).strip().isdigit():
        cursor.execute(
            """UPDATE abandoned_carts 
               SET status = 'RECOVERED', recovered_at = CURRENT_TIMESTAMP 
               WHERE id = ? AND status NOT IN ('RECOVERED', 'CANCELLED')""",
            (int(cart_id),),
        )
        count = cursor.rowcount
    elif phone:
        clean = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
        if len(clean) < 10:
            conn.close()
            return 0
        cursor.execute(
            """UPDATE abandoned_carts 
               SET status = 'RECOVERED', recovered_at = CURRENT_TIMESTAMP 
               WHERE phone LIKE ? AND status NOT IN ('RECOVERED', 'CANCELLED')""",
            (f"%{clean}",),
        )
        count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def mark_cart_cancelled(cart_id: Optional[int] = None, phone: Optional[str] = None) -> int:
    """
    Marks one or more abandoned carts as CANCELLED when the customer declines or opts out.
    """
    conn = get_db()
    cursor = conn.cursor()
    count = 0
    if cart_id is not None and str(cart_id).strip().isdigit():
        cursor.execute(
            """UPDATE abandoned_carts 
               SET status = 'CANCELLED', cancelled_at = CURRENT_TIMESTAMP 
               WHERE id = ? AND status NOT IN ('RECOVERED', 'CANCELLED')""",
            (int(cart_id),),
        )
        count = cursor.rowcount
    elif phone:
        clean = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
        if len(clean) < 10:
            conn.close()
            return 0
        cursor.execute(
            """UPDATE abandoned_carts 
               SET status = 'CANCELLED', cancelled_at = CURRENT_TIMESTAMP 
               WHERE phone LIKE ? AND status NOT IN ('RECOVERED', 'CANCELLED')""",
            (f"%{clean}",),
        )
        count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def get_abandoned_carts(status: Optional[str] = None, phone: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves abandoned carts with optional status and phone filtering.
    """
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM abandoned_carts"
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if phone:
        clean = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
        if len(clean) < 10:
            conn.close()
            return []
        conditions.append("phone LIKE ?")
        params.append(f"%{clean}")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))

    cursor.execute(query, tuple(params))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_abandoned_cart(cart_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single abandoned cart by its ID.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM abandoned_carts WHERE id = ?", (cart_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
