"""Sales Routes HTTP routes."""

from datetime import datetime
from flask import jsonify, request
import logging, math, time
from ..app import (
    app,
    get_current_user_id,
    get_db,
)


@app.route("/api/income", methods=["GET", "POST"])
@app.route("/add_income", methods=["GET", "POST"])
def api_income():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            rows = db.execute("SELECT * FROM income WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
            income_list = []
            for row in rows:
                item = dict(row)
                total_value = float(item.get("total_value") if item.get("total_value") is not None else item.get("amount", 0))
                amount_paid = float(item.get("amount_paid") if item.get("amount_paid") is not None else item.get("amount", 0))
                balance_owed = max(total_value - amount_paid, 0)
                income_list.append({
                    "id": item["id"],
                    "user_id": item["user_id"],
                    "description": item.get("description", ""),
                    "total_value": total_value,
                    "amount_paid": amount_paid,
                    "balance_owed": balance_owed,
                    "customer_name": item.get("customer_name") or "Walk-in Customer",
                    "payment_mode": item.get("payment_mode") or "Cash",
                    "date": item.get("date"),
                    "receipt_id": item.get("receipt_id") or f"REC-{item['id']}",
                    "checkout_id": item.get("checkout_id"),
                    "checkout_line_id": item.get("checkout_line_id"),
                    "inventory_item_id": item.get("inventory_item_id"),
                    "quantity": int(item.get("quantity") or 1),
                    "unit_price": float(item.get("unit_price") or 0)
                })
        return jsonify({"status": "success", "income": income_list}), 200

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            data = request.form.to_dict()

        income_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        receipt_id = data.get("receipt_id") or f"REC-{int(time.time())}"
        customer_name = str(data.get("customer_name", "Walk-in Customer")).strip() or "Walk-in Customer"

        description = str(data.get("description", "")).strip()
        try:
            total_value = float(str(data.get("total_value", "0")).replace(',', ''))
            amount_paid = float(str(data.get("amount_paid", "0")).replace(',', ''))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Invalid amount format"}), 400

        payment_mode = str(data.get("payment_mode", "Cash")).strip() or "Cash"

        if (
            not description
            or not math.isfinite(total_value)
            or not math.isfinite(amount_paid)
            or total_value <= 0
            or amount_paid < 0
            or amount_paid > total_value
        ):
            return jsonify({"status": "error", "message": "Description and a valid total value are required"}), 400

        with get_db() as db:
            cursor = db.execute(
                "INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, description, total_value, amount_paid, customer_name, payment_mode, income_date, receipt_id)
            )
            saved_item = {
                "id": cursor.lastrowid,
                "user_id": user_id,
                "description": description,
                "total_value": total_value,
                "amount_paid": amount_paid,
                "customer_name": customer_name,
                "payment_mode": payment_mode,
                "date": income_date,
                "receipt_id": receipt_id
            }
            db.commit()

        return jsonify({
            "status": "success",
            "message": "Income logged successfully",
            "receipt_id": receipt_id,
            "income": saved_item
        }), 201


@app.route("/api/income", methods=["DELETE"])
def reject_income_collection_delete():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return jsonify({"status": "error", "message": "Choose a specific sale to delete."}), 405


@app.route("/api/income/<int:income_id>", methods=["DELETE"])
def api_delete_income(income_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    try:
        with get_db() as db:
            target = db.execute(
                "SELECT id, checkout_id, receipt_id FROM income WHERE id = ? AND user_id = ?",
                (income_id, user_id)
            ).fetchone()
            if not target:
                return jsonify({"status": "success", "message": "Sale was already deleted.", "deleted_count": 0, "stock": {}}), 200

            target = dict(target)
            checkout_id = target.get("checkout_id")
            if checkout_id:
                deleted_items = db.execute(
                    "DELETE FROM income WHERE user_id = ? AND checkout_id = ? RETURNING inventory_item_id, quantity",
                    (user_id, checkout_id)
                ).fetchall()
            else:
                deleted_items = db.execute(
                    "DELETE FROM income WHERE id = ? AND user_id = ? RETURNING inventory_item_id, quantity",
                    (income_id, user_id)
                ).fetchall()

            quantities_by_product = {}
            for deleted_item in deleted_items:
                item = dict(deleted_item)
                inventory_id = item.get("inventory_item_id")
                if inventory_id is not None:
                    quantity = max(int(item.get("quantity") or 1), 1)
                    quantities_by_product[inventory_id] = quantities_by_product.get(inventory_id, 0) + quantity

            restored_stock = {}
            for inventory_id, quantity in quantities_by_product.items():
                db.execute(
                    "UPDATE inventory_presets SET stock = COALESCE(stock, 0) + ? WHERE id = ? AND user_id = ? AND track_stock = 1",
                    (quantity, inventory_id, user_id)
                )
                stock_row = db.execute(
                    "SELECT stock FROM inventory_presets WHERE id = ? AND user_id = ? AND track_stock = 1",
                    (inventory_id, user_id)
                ).fetchone()
                if stock_row:
                    restored_stock[str(inventory_id)] = int(dict(stock_row)["stock"] or 0)

            db.commit()

        return jsonify({
            "status": "success",
            "message": "Sale deleted successfully.",
            "receipt_id": target.get("receipt_id"),
            "deleted_count": len(deleted_items),
            "stock": restored_stock
        }), 200
    except Exception as error:
        logging.error("Sale deletion failed for income %s: %s", income_id, error, exc_info=True)
        return jsonify({"status": "error", "message": "Could not delete this sale. Please try again."}), 500


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    """Record a multi-item inventory sale and decrement tracked stock atomically."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Checkout details must be a JSON object."}), 400
    checkout_id = str(data.get("checkout_id") or "").strip()
    customer_name = str(data.get("customer_name") or "Walk-in Customer").strip() or "Walk-in Customer"
    payment_mode = str(data.get("payment_mode") or "Cash").strip() or "Cash"
    raw_items = data.get("items")
    if not checkout_id or len(checkout_id) > 120 or not isinstance(raw_items, list) or not raw_items or len(raw_items) > 50:
        return jsonify({"status": "error", "message": "A checkout ID and between 1 and 50 sale items are required."}), 400

    try:
        amount_paid = float(str(data.get("amount_paid", "0")).replace(",", ""))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Enter a valid payment amount."}), 400
    if not math.isfinite(amount_paid) or amount_paid < 0:
        return jsonify({"status": "error", "message": "Payment must be zero or greater."}), 400

    parsed_items = []
    line_ids = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            return jsonify({"status": "error", "message": "Each cart item must be valid."}), 400
        raw_preset_id = raw.get("inventory_item_id")
        try:
            preset_id_value = float(raw_preset_id) if raw_preset_id not in (None, "") else None
            quantity_value = float(raw.get("quantity"))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Each item needs a valid product and whole-number quantity."}), 400
        if preset_id_value is not None and (not math.isfinite(preset_id_value) or not preset_id_value.is_integer()):
            return jsonify({"status": "error", "message": "Inventory product IDs must be whole numbers."}), 400
        preset_id = int(preset_id_value) if preset_id_value is not None else None
        if not math.isfinite(quantity_value) or not quantity_value.is_integer():
            return jsonify({"status": "error", "message": "Item quantities must be whole numbers."}), 400
        quantity = int(quantity_value)
        if (preset_id is not None and preset_id <= 0) or quantity <= 0 or quantity > 10000:
            return jsonify({"status": "error", "message": "Product quantity must be between 1 and 10,000."}), 400
        item_name = str(raw.get("item_name") or raw.get("description") or "").strip()
        if preset_id is None and (not item_name or len(item_name) > 120):
            return jsonify({"status": "error", "message": "A custom cart item needs a name no longer than 120 characters."}), 400
        line_id = str(raw.get("checkout_line_id") or f"line-{index + 1}").strip()
        if not line_id or len(line_id) > 120 or line_id in line_ids:
            return jsonify({"status": "error", "message": "Sale line identifiers must be unique and no longer than 120 characters."}), 400
        line_ids.add(line_id)
        try:
            requested_price = raw.get("unit_price")
            requested_price = float(str(requested_price).replace(",", "")) if requested_price is not None else None
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Product price is invalid."}), 400
        if requested_price is not None and (not math.isfinite(requested_price) or requested_price <= 0):
            return jsonify({"status": "error", "message": "Product price must be greater than zero."}), 400
        if preset_id is None and requested_price is None:
            return jsonify({"status": "error", "message": "A custom cart item needs a unit price."}), 400
        parsed_items.append({"preset_id": preset_id, "quantity": quantity, "line_id": line_id, "requested_price": requested_price, "item_name": item_name})

    sale_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    receipt_id = str(data.get("receipt_id") or f"REC-{checkout_id[:12].upper()}").strip()
    try:
        with get_db() as db:
            existing_rows = db.execute(
                "SELECT * FROM income WHERE user_id = ? AND checkout_id = ? ORDER BY id ASC",
                (user_id, checkout_id)
            ).fetchall()
            if existing_rows:
                existing_items = [dict(row) for row in existing_rows]
                existing_stock = {}
                for preset_id in {item.get("inventory_item_id") for item in existing_items if item.get("inventory_item_id") is not None}:
                    stock_row = db.execute(
                        "SELECT stock FROM inventory_presets WHERE id = ? AND user_id = ?",
                        (preset_id, user_id)
                    ).fetchone()
                    if stock_row:
                        existing_stock[str(preset_id)] = int(dict(stock_row)["stock"])
                return jsonify({
                    "status": "success", "receipt_id": existing_items[0].get("receipt_id"),
                    "items": [{"id": item["id"], "checkout_line_id": item.get("checkout_line_id"), "inventory_item_id": item.get("inventory_item_id"), "quantity": item.get("quantity", 1), "unit_price": float(item.get("unit_price") or 0), "total_value": float(item.get("total_value") or 0), "amount_paid": float(item.get("amount_paid") or 0)} for item in existing_items],
                    "stock": existing_stock
                }), 200

            lines = []
            for item in parsed_items:
                if item["preset_id"] is None:
                    lines.append({**item, "name": item["item_name"], "unit_price": item["requested_price"], "track_stock": False})
                    continue
                row = db.execute(
                    "SELECT id, item_name, price, stock, track_stock FROM inventory_presets WHERE id = ? AND user_id = ?",
                    (item["preset_id"], user_id)
                ).fetchone()
                if not row:
                    raise ValueError("A product in this cart no longer exists. Refresh inventory and try again.")
                product = dict(row)
                unit_price = float(item["requested_price"] if item["requested_price"] is not None else product["price"])
                if not math.isfinite(unit_price) or unit_price <= 0:
                    raise ValueError(f"{product['item_name']} has an invalid price.")
                if bool(product.get("track_stock")) and int(product.get("stock") or 0) < item["quantity"]:
                    raise ValueError(f"Not enough stock for {product['item_name']}. Available: {int(product.get('stock') or 0)}.")
                lines.append({**item, "name": product["item_name"], "unit_price": unit_price, "track_stock": bool(product.get("track_stock"))})

            grand_total = sum(line["unit_price"] * line["quantity"] for line in lines)
            if not math.isfinite(grand_total) or grand_total <= 0 or amount_paid > grand_total:
                raise ValueError("Amount paid cannot exceed the cart total.")

            quantities_by_product = {}
            for line in lines:
                if line["track_stock"]:
                    quantities_by_product[line["preset_id"]] = quantities_by_product.get(line["preset_id"], 0) + line["quantity"]
            updated_stock = {}
            for preset_id, quantity in quantities_by_product.items():
                update = db.execute(
                    "UPDATE inventory_presets SET stock = stock - ? WHERE id = ? AND user_id = ? AND track_stock = 1 AND stock >= ?",
                    (quantity, preset_id, user_id, quantity)
                )
                if update.rowcount != 1:
                    raise ValueError("Inventory changed while saving this sale. Refresh stock and try again.")
                stock_row = db.execute("SELECT stock FROM inventory_presets WHERE id = ? AND user_id = ?", (preset_id, user_id)).fetchone()
                updated_stock[str(preset_id)] = int(dict(stock_row)["stock"])

            remaining_paid = amount_paid
            saved_items = []
            for line in lines:
                line_total = line["unit_price"] * line["quantity"]
                line_paid = min(remaining_paid, line_total)
                remaining_paid -= line_paid
                cursor = db.execute(
                    """INSERT INTO income (
                        user_id, description, total_value, amount_paid, customer_name, payment_mode, date,
                        receipt_id, checkout_id, checkout_line_id, inventory_item_id, quantity, unit_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, line["name"], line_total, line_paid, customer_name, payment_mode, sale_date,
                     receipt_id, checkout_id, line["line_id"], line["preset_id"], line["quantity"], line["unit_price"])
                )
                saved_items.append({
                    "id": cursor.lastrowid, "checkout_line_id": line["line_id"], "inventory_item_id": line["preset_id"],
                    "description": line["name"], "quantity": line["quantity"], "unit_price": line["unit_price"],
                    "total_value": line_total, "amount_paid": line_paid, "customer_name": customer_name,
                    "payment_mode": payment_mode, "date": sale_date, "receipt_id": receipt_id, "checkout_id": checkout_id
                })
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 409

    return jsonify({"status": "success", "message": "Sale recorded successfully.", "receipt_id": receipt_id, "items": saved_items, "stock": updated_stock}), 201


@app.route('/update_payment/<int:receipt_id>', methods=['POST'])
def update_payment(receipt_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.form.to_dict() if request.form else {}
    if not data and request.is_json:
        data = request.get_json(silent=True) or {}

    payment_amount_raw = str(data.get('payment_amount') or data.get('amount_paid') or '').strip()
    try:
        payment_amount = float(payment_amount_raw)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Please enter a valid payment amount."}), 400

    if not math.isfinite(payment_amount) or payment_amount <= 0:
        return jsonify({"status": "error", "message": "Payment must be greater than zero."}), 400

    with get_db() as db:
        row = db.execute("SELECT * FROM income WHERE id = ? AND user_id = ?", (receipt_id, user_id)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Receipt not found."}), 404

        item = dict(row)
        total_value = float(item.get("total_value") if item.get("total_value") is not None else item.get("amount", 0))
        current_paid = float(item.get("amount_paid") if item.get("amount_paid") is not None else item.get("amount", 0))
        updated_paid = min(total_value, current_paid + payment_amount)
        db.execute(
            "UPDATE income SET amount_paid = ? WHERE id = ? AND user_id = ?",
            (updated_paid, receipt_id, user_id)
        )
        db.commit()

    return jsonify({
        "status": "success",
        "message": "Payment added successfully.",
        "updated_amount_paid": updated_paid,
        "balance_owed": max(total_value - updated_paid, 0)
    }), 200


@app.route("/api/sync-sales", methods=["POST"])
def sync_sales():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.get_json(force=True, silent=True) or {}
    sales_array = data.get("sales", [])

    if not sales_array or not isinstance(sales_array, list):
        return jsonify({"status": "success", "success": True, "message": "No sales to sync", "count": 0}), 200

    saved_items = []
    with get_db() as db:
        for sale in sales_array:
            if not isinstance(sale, dict):
                continue

            description = str(sale.get("description") or sale.get("item_sold") or sale.get("item") or "").strip()
            try:
                total_value = float(str(sale.get("total_value", sale.get("amount", 0))).replace(",", ""))
                amount_paid = float(str(sale.get("amount_paid", sale.get("amount", 0))).replace(",", ""))
            except (TypeError, ValueError):
                continue
            payment_mode = str(sale.get("payment_mode", "Cash")).strip()
            customer_name = str(sale.get("customer_name") or "Walk-in Customer").strip() or "Walk-in Customer"
            sale_date = sale.get("date") or datetime.now().strftime("%Y-%m-%d %I:%M %p")
            receipt_id = sale.get("receipt_id") or f"REC-{int(time.time())}"

            try:
                if (
                    not math.isfinite(total_value)
                    or not math.isfinite(amount_paid)
                    or total_value <= 0
                    or amount_paid < 0
                    or amount_paid > total_value
                    or not description
                ):
                    continue
            except (TypeError, ValueError):
                continue

            cursor = db.execute(
                """INSERT INTO income (
                    user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, description, total_value, amount_paid, customer_name, payment_mode, sale_date, receipt_id)
            )
            saved_items.append({
                "id": cursor.lastrowid, "user_id": user_id,
                "description": description, "total_value": total_value, "amount_paid": amount_paid,
                "customer_name": customer_name, "payment_mode": payment_mode,
                "date": sale_date, "receipt_id": receipt_id
            })
        db.commit()

    return jsonify({
        "status": "success",
        "success": True,
        "message": f"Successfully synced {len(saved_items)} sales",
        "count": len(saved_items),
        "items": saved_items
    }), 200
