"""Inventory Routes HTTP routes."""

from flask import jsonify, request
import math
from ..app import (
    app,
    get_current_user_id,
    get_db,
)


@app.route("/api/inventory-presets", methods=["GET", "POST"])
def api_inventory_presets():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            rows = db.execute("SELECT * FROM inventory_presets WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
            presets = [{"id": dict(r)["id"], "item_name": dict(r)["item_name"], "price": float(dict(r)["price"]), "stock": int(dict(r)["stock"]), "track_stock": bool(dict(r).get("track_stock", 0))} for r in rows]
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

        with get_db() as db:
            count = db.execute("SELECT COUNT(*) as cnt FROM inventory_presets WHERE user_id = ?", (user_id,)).fetchone()
            if int(dict(count)["cnt"]) >= 10:
                return jsonify({"status": "error", "message": "Maximum 10 presets allowed."}), 400

            cursor = db.execute(
                "INSERT INTO inventory_presets (user_id, item_name, price, stock, track_stock) VALUES (?, ?, ?, ?, ?)",
                (user_id, item_name, price, stock, 1 if stock > 0 else 0)
            )
            db.commit()
        return jsonify({"status": "success", "preset": {"id": cursor.lastrowid, "item_name": item_name, "price": price, "stock": stock, "track_stock": stock > 0}}), 201


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

            db.execute(
                "UPDATE inventory_presets SET item_name = ?, price = ?, stock = ?, track_stock = ? WHERE id = ? AND user_id = ?",
                (item_name, price, stock, 1 if stock > 0 or bool(dict(existing).get("track_stock", 0)) else 0, preset_id, user_id)
            )
            db.commit()
            return jsonify({"status": "success", "preset": {"id": preset_id, "item_name": item_name, "price": price, "stock": stock, "track_stock": stock > 0 or bool(dict(existing).get("track_stock", 0))}}), 200


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
            return jsonify({"status": "success", "stock": new_stock}), 200
        else:
            return jsonify({"status": "warning", "message": "Out of stock", "stock": 0}), 200
