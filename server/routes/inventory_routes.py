"""Inventory Routes HTTP routes."""

from flask import jsonify, request
import math
from .. import push
from ..app import (
    app,
    get_current_user_id,
    get_db,
    record_user_activity,
)

BULK_ERROR = (
    "Bulk sale needs a bundle size of at least 2 units and a bundle price "
    "greater than zero. Leave both empty to sell this product by the piece only."
)


def _is_blank(value):
    return value is None or str(value).strip() in ("", "0")


def parse_bulk_pricing(data, existing=None):
    """Return (bulk_quantity, bulk_price, error).

    Bulk pricing is optional: `bulk_price` is the price for a bundle of
    `bulk_quantity` units. It is only applied to a sale when the seller marks
    that sale line as a bulk sale; buying many pieces never switches to it.
    On update, fields left out of the payload keep their current values.
    """
    existing = dict(existing or {})
    raw_quantity = data["bulk_quantity"] if "bulk_quantity" in data else existing.get("bulk_quantity")
    raw_price = data["bulk_price"] if "bulk_price" in data else existing.get("bulk_price")

    if _is_blank(raw_quantity) and _is_blank(raw_price):
        return None, None, None
    if _is_blank(raw_quantity) or _is_blank(raw_price):
        return None, None, BULK_ERROR
    try:
        quantity_value = float(str(raw_quantity).replace(",", ""))
        price = float(str(raw_price).replace(",", ""))
    except (TypeError, ValueError):
        return None, None, BULK_ERROR
    if (
        not math.isfinite(quantity_value)
        or not quantity_value.is_integer()
        or not 2 <= quantity_value <= 10000
        or not math.isfinite(price)
        or price <= 0
    ):
        return None, None, BULK_ERROR
    return int(quantity_value), price, None


DEFAULT_LOW_STOCK_THRESHOLD = 3


def parse_low_stock_threshold(data, existing=None):
    """Return (threshold, error). Stock at or below the threshold is "low"."""
    if "low_stock_threshold" in data and data["low_stock_threshold"] not in (None, ""):
        raw = data["low_stock_threshold"]
    elif existing is not None and dict(existing).get("low_stock_threshold") is not None:
        return int(dict(existing)["low_stock_threshold"]), None
    else:
        return DEFAULT_LOW_STOCK_THRESHOLD, None
    try:
        value = float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        value = -1
    if not math.isfinite(value) or not value.is_integer() or not 0 <= value <= 10000:
        return None, "Low-stock alert level must be a whole number from 0 to 10,000."
    return int(value), None


def serialize_preset(row):
    item = dict(row)
    bulk_quantity = item.get("bulk_quantity")
    bulk_price = item.get("bulk_price")
    has_bulk = bool(bulk_quantity) and bulk_price is not None and float(bulk_price) > 0
    return {
        "id": item["id"],
        "item_name": item["item_name"],
        "price": float(item["price"]),
        "stock": int(item["stock"] or 0),
        "track_stock": bool(item.get("track_stock", 0)),
        "bulk_quantity": int(bulk_quantity) if has_bulk else None,
        "bulk_price": float(bulk_price) if has_bulk else None,
        "low_stock_threshold": int(item["low_stock_threshold"])
        if item.get("low_stock_threshold") is not None else DEFAULT_LOW_STOCK_THRESHOLD,
    }


@app.route("/api/inventory-presets", methods=["GET", "POST"])
def api_inventory_presets():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            rows = db.execute("SELECT * FROM inventory_presets WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
            presets = [serialize_preset(r) for r in rows]
        return jsonify({"status": "success", "presets": presets}), 200

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        item_name = str(data.get("item_name", "")).strip()
        try:
            price = float(str(data.get("price", "0")).replace(",", ""))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Invalid price"}), 400
        try:
            stock = int(data.get("stock", 0))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Stock must be a whole number."}), 400

        if not item_name or not math.isfinite(price) or price <= 0 or stock < 0:
            return jsonify({"status": "error", "message": "Item name and a positive price are required."}), 400

        bulk_quantity, bulk_price, bulk_error = parse_bulk_pricing(data)
        if bulk_error:
            return jsonify({"status": "error", "message": bulk_error}), 400
        threshold, threshold_error = parse_low_stock_threshold(data)
        if threshold_error:
            return jsonify({"status": "error", "message": threshold_error}), 400

        with get_db() as db:
            count = db.execute("SELECT COUNT(*) as cnt FROM inventory_presets WHERE user_id = ?", (user_id,)).fetchone()
            if int(dict(count)["cnt"]) >= 10:
                return jsonify({"status": "error", "message": "Maximum 10 presets allowed."}), 400

            cursor = db.execute(
                "INSERT INTO inventory_presets "
                "(user_id, item_name, price, stock, track_stock, bulk_quantity, bulk_price, low_stock_threshold) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, item_name, price, stock, 1 if stock > 0 else 0, bulk_quantity, bulk_price, threshold)
            )
            record_user_activity(db, user_id, "inventory_item_created", "Added an inventory item")
            db.commit()
        return jsonify({"status": "success", "preset": {
            "id": cursor.lastrowid, "item_name": item_name, "price": price, "stock": stock,
            "track_stock": stock > 0, "bulk_quantity": bulk_quantity, "bulk_price": bulk_price,
            "low_stock_threshold": threshold,
        }}), 201


@app.route("/api/inventory-presets/<int:preset_id>", methods=["PUT", "DELETE"])
def api_inventory_preset_detail(preset_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    with get_db() as db:
        existing = db.execute("SELECT * FROM inventory_presets WHERE id = ? AND user_id = ?", (preset_id, user_id)).fetchone()
        if not existing:
            return jsonify({"status": "error", "message": "Preset not found"}), 404

        if request.method == "DELETE":
            db.execute("DELETE FROM inventory_presets WHERE id = ? AND user_id = ?", (preset_id, user_id))
            record_user_activity(db, user_id, "inventory_item_deleted", "Removed an inventory item")
            db.commit()
            return jsonify({"status": "success", "message": "Preset deleted"}), 200

        elif request.method == "PUT":
            data = request.get_json(silent=True) or {}
            item_name = str(data.get("item_name", dict(existing).get("item_name", ""))).strip()
            try:
                price = float(str(data.get("price", dict(existing).get("price", 0))).replace(",", ""))
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "Invalid price"}), 400
            try:
                stock = int(data.get("stock", dict(existing).get("stock", 0)))
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "Stock must be a whole number."}), 400

            if not item_name or not math.isfinite(price) or price <= 0 or stock < 0:
                return jsonify({"status": "error", "message": "Item name and a positive price are required."}), 400

            bulk_quantity, bulk_price, bulk_error = parse_bulk_pricing(data, existing)
            if bulk_error:
                return jsonify({"status": "error", "message": bulk_error}), 400
            threshold, threshold_error = parse_low_stock_threshold(data, existing)
            if threshold_error:
                return jsonify({"status": "error", "message": threshold_error}), 400

            track_stock = stock > 0 or bool(dict(existing).get("track_stock", 0))
            db.execute(
                "UPDATE inventory_presets SET item_name = ?, price = ?, stock = ?, track_stock = ?, "
                "bulk_quantity = ?, bulk_price = ?, low_stock_threshold = ? WHERE id = ? AND user_id = ?",
                (item_name, price, stock, 1 if track_stock else 0, bulk_quantity, bulk_price, threshold,
                 preset_id, user_id)
            )
            record_user_activity(db, user_id, "inventory_item_updated", "Updated an inventory item")
            db.commit()
            return jsonify({"status": "success", "preset": {
                "id": preset_id, "item_name": item_name, "price": price, "stock": stock,
                "track_stock": track_stock, "bulk_quantity": bulk_quantity, "bulk_price": bulk_price,
                "low_stock_threshold": threshold,
            }}), 200


@app.route("/api/inventory-presets/<int:preset_id>/decrement", methods=["POST"])
def api_preset_decrement_stock(preset_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    with get_db() as db:
        row = db.execute("SELECT * FROM inventory_presets WHERE id = ? AND user_id = ?", (preset_id, user_id)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Preset not found"}), 404

        current_stock = int(dict(row)["stock"])
        if current_stock > 0:
            new_stock = current_stock - 1
            db.execute("UPDATE inventory_presets SET stock = ? WHERE id = ? AND user_id = ?", (new_stock, preset_id, user_id))
            db.commit()
            product = dict(row)
            push.send_to_user(user_id, push.low_stock_notifications([{
                "id": preset_id, "item_name": product["item_name"], "before": current_stock, "after": new_stock,
                "threshold": product.get("low_stock_threshold") if product.get("low_stock_threshold") is not None else 3,
            }]))
            return jsonify({"status": "success", "stock": new_stock}), 200
        else:
            return jsonify({"status": "warning", "message": "Out of stock", "stock": 0}), 200
