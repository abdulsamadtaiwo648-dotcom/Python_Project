"""Page Routes HTTP routes."""

from datetime import datetime, timezone
from flask import make_response, redirect, render_template, send_from_directory
import logging, os
from ..app import (
    app,
    APP_VERSION,
    CLIENT_ROOT,
    get_current_user_id,
    get_db,
)


@app.route("/")
def root():
    if get_current_user_id():
        return redirect("/dashboard")
    return render_template("landing.html")


@app.route("/data-access")
def data_access_notice():
    return render_template("data_access.html")


@app.route("/privacy")
def privacy_policy():
    return render_template("privacy.html")


@app.route('/sw.js')
def service_worker():
    sw_script = render_template('sw.js', version=APP_VERSION)
    response = make_response(sw_script)
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.route("/sitemap.xml")
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://solobiz.dev/</loc><lastmod>2026-09-20</lastmod><priority>1.0</priority></url>
  <url><loc>https://solobiz.dev/login</loc><priority>0.8</priority></url>
  <url><loc>https://solobiz.dev/register</loc><priority>0.8</priority></url>
  <url><loc>https://solobiz.dev/privacy</loc><priority>0.5</priority></url>
</urlset>"""
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml; charset=utf-8"
    return response


@app.route("/robots.txt")
def robots():
    txt = """User-agent: *
Allow: /
Allow: /login
Allow: /register
Allow: /privacy
Disallow: /dashboard
Disallow: /api/

Sitemap: https://solobiz.dev/sitemap.xml"""
    response = make_response(txt)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(CLIENT_ROOT, "static"), "favicon.png", mimetype="image/png")


@app.route("/dashboard")
def dashboard_home():
    """Render the business snapshot."""
    if not get_current_user_id():
        return redirect("/login")
    return render_dashboard_page("dashboard")


@app.route("/budget")
def budget_page():
    return render_dashboard_page("budget")


@app.route("/expenses")
def expenses_page():
    return render_dashboard_page("expenses")


@app.route("/sales")
def sales_page():
    return render_dashboard_page("sales")


@app.route("/inventory")
def inventory_page():
    return render_dashboard_page("inventory")


@app.route("/analytics")
def analytics_page():
    return redirect("/dashboard")


@app.route("/profile")
def profile_page():
    return render_dashboard_page("profile")


@app.route("/dashboard/<section>")
def legacy_dashboard_section(section):
    if section not in {"expenses", "sales", "inventory", "analytics", "budget", "profile"}:
        return render_template("404.html"), 404
    if section == "analytics":
        return redirect("/dashboard", code=302)
    return redirect(f"/{section}", code=302)


def render_dashboard_page(section):
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    if section not in {"dashboard", "expenses", "sales", "inventory", "budget", "profile"}:
        return render_template("404.html"), 404

    active_tab = "income" if section == "sales" else section

    expenses = []
    total_sales = 0.0
    total_expenses = 0.0
    total_outstanding = 0.0
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_collected = 0.0
    today_expenses = 0.0
    outstanding_sale_count = 0
    total_unpaid_balance = 0.0
    low_stock_items = []
    username = "Entrepreneur"

    try:
        with get_db() as db:
            try:
                user = db.execute("SELECT email, first_name FROM users WHERE id = ?", (user_id,)).fetchone()
                if user and user["email"]:
                    username = (user["first_name"] or user["email"].split("@")[0]).capitalize()
            except Exception as e:
                print(f"Dashboard user query note: {e}", flush=True)

            if section == "expenses":
                try:
                    expenses = db.execute(
                        "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user_id,)
                    ).fetchall() or []
                except Exception as e:
                    print(f"Dashboard expenses list note: {e}", flush=True)

            try:
                row = db.execute(
                    "SELECT SUM(COALESCE(amount_paid, 0)) AS total FROM income WHERE user_id = ? AND date LIKE ?",
                    (user_id, current_month + "%")
                ).fetchone()
                if row and row["total"] is not None:
                    total_sales = float(row["total"])
            except Exception as e:
                print(f"Dashboard sales sum note: {e}", flush=True)

            try:
                row = db.execute(
                    "SELECT SUM(amount) AS total FROM expenses WHERE user_id = ? AND date LIKE ?",
                    (user_id, current_month + "%")
                ).fetchone()
                if row and row["total"] is not None:
                    total_expenses = float(row["total"])
            except Exception as e:
                print(f"Dashboard expenses sum note: {e}", flush=True)

            try:
                row = db.execute(
                    "SELECT SUM(CASE WHEN COALESCE(total_value, 0) > COALESCE(amount_paid, 0) THEN COALESCE(total_value, 0) - COALESCE(amount_paid, 0) ELSE 0 END) AS total FROM income WHERE user_id = ? AND date LIKE ?",
                    (user_id, current_month + "%")
                ).fetchone()
                if row and row["total"] is not None:
                    total_outstanding = float(row["total"])
            except Exception as e:
                print(f"Dashboard outstanding sum note: {e}", flush=True)

            try:
                row = db.execute(
                    "SELECT COALESCE(SUM(amount_paid), 0) AS total "
                    "FROM income WHERE user_id = ? AND date LIKE ?",
                    (user_id, today + "%"),
                ).fetchone()
                today_collected = float(row["total"] or 0)
                row = db.execute(
                    "SELECT COALESCE(SUM(amount), 0) AS total "
                    "FROM expenses WHERE user_id = ? AND date LIKE ?",
                    (user_id, today + "%"),
                ).fetchone()
                today_expenses = float(row["total"] or 0)
                row = db.execute(
                    "SELECT COUNT(CASE WHEN COALESCE(total_value, 0) > COALESCE(amount_paid, 0) "
                    "THEN 1 END) AS sale_count, COALESCE(SUM("
                    "CASE WHEN COALESCE(total_value, 0) > COALESCE(amount_paid, 0) "
                    "THEN COALESCE(total_value, 0) - COALESCE(amount_paid, 0) ELSE 0 END), 0) AS balance "
                    "FROM income WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                outstanding_sale_count = int(row["sale_count"] or 0)
                total_unpaid_balance = float(row["balance"] or 0)
                low_stock_items = db.execute(
                    "SELECT item_name, stock FROM inventory_presets "
                    "WHERE user_id = ? AND track_stock = 1 AND COALESCE(stock, 0) <= 3 "
                    "ORDER BY stock ASC, item_name ASC",
                    (user_id,),
                ).fetchall() or []
            except Exception as e:
                print(f"Dashboard daily check-in note: {e}", flush=True)

    except Exception as e:
        logging.error(f"Dashboard data fetch error for user '{user_id}': {e}", exc_info=True)

    net_profit = total_sales - total_expenses

    profile = None
    try:
        with get_db() as db:
            prof_row = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if prof_row:
                profile = dict(prof_row)
    except Exception as e:
        print(f"Dashboard profile query note: {e}", flush=True)

    return render_template(
        "index.html",
        expenses=expenses,
        total=total_expenses,
        total_sales=total_sales,
        total_expenses=total_expenses,
        total_outstanding=total_outstanding,
        current_month=current_month,
        net_profit=net_profit,
        today=today,
        today_collected=today_collected,
        today_expenses=today_expenses,
        today_net=today_collected - today_expenses,
        outstanding_sale_count=outstanding_sale_count,
        total_unpaid_balance=total_unpaid_balance,
        low_stock_items=low_stock_items,
        username=username,
        profile=profile,
        active_tab=active_tab
    )
