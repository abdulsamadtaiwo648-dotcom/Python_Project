"""Dashboard summary: the figures behind the KPI cards and daily check-in."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from server.database import get_db

from ..deps import require_user

router = APIRouter(prefix="/api")


def vs_last_month(current, previous, empty_text):
    """'+12% vs last month' style note; empty_text when last month had nothing."""
    if previous <= 0:
        return empty_text
    change = round((current - previous) / previous * 100)
    sign = "+" if change >= 0 else "−"
    return f"{sign}{abs(change)}% vs last month"


def margin_note(income, net):
    if net < 0:
        return "Spending is above income"
    if income > 0:
        return f"{round(net / income * 100)}% margin"
    return "No income yet"


def _sum(db, sql, params):
    row = db.execute(sql, params).fetchone()
    return float(row["total"] or 0) if row else 0.0


@router.get("/dashboard")
def dashboard(user_id: str = Depends(require_user)):
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")
    prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    unpaid = (
        "CASE WHEN COALESCE(total_value, 0) > COALESCE(amount_paid, 0) "
        "THEN COALESCE(total_value, 0) - COALESCE(amount_paid, 0) ELSE 0 END"
    )
    try:
        with get_db() as db:
            user = db.execute("SELECT email, first_name FROM users WHERE id = ?", (user_id,)).fetchone()
            name = "Entrepreneur"
            if user and user["email"]:
                name = (user["first_name"] or user["email"].split("@")[0]).capitalize()
            total_sales = _sum(db, "SELECT COALESCE(SUM(amount_paid), 0) AS total FROM income WHERE user_id = ?", (user_id,))
            total_expenses = _sum(db, "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ?", (user_id,))
            outstanding = _sum(db, f"SELECT COALESCE(SUM({unpaid}), 0) AS total FROM income WHERE user_id = ?", (user_id,))
            outstanding_count = int(_sum(
                db,
                "SELECT COUNT(CASE WHEN COALESCE(total_value, 0) > COALESCE(amount_paid, 0) THEN 1 END) AS total "
                "FROM income WHERE user_id = ?",
                (user_id,),
            ))
            income_sql = "SELECT COALESCE(SUM(amount_paid), 0) AS total FROM income WHERE user_id = ? AND entry_date LIKE ?"
            expense_sql = "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ? AND entry_date LIKE ?"
            today_collected = _sum(db, income_sql, (user_id, today + "%"))
            today_expenses = _sum(db, expense_sql, (user_id, today + "%"))
            month_income = _sum(db, income_sql, (user_id, month + "%"))
            month_expenses = _sum(db, expense_sql, (user_id, month + "%"))
            prev_income = _sum(db, income_sql, (user_id, prev_month + "%"))
            prev_expenses = _sum(db, expense_sql, (user_id, prev_month + "%"))
            low_stock = [
                {"item_name": r["item_name"], "stock": int(r["stock"] or 0), "threshold": int(r["low_stock_threshold"])}
                for r in db.execute(
                    "SELECT item_name, stock, COALESCE(low_stock_threshold, 3) AS low_stock_threshold "
                    "FROM inventory_presets WHERE user_id = ? AND track_stock = 1 "
                    "AND COALESCE(stock, 0) <= COALESCE(low_stock_threshold, 3) ORDER BY stock ASC, item_name ASC",
                    (user_id,),
                ).fetchall()
            ]
    except Exception:
        logging.exception("Dashboard data fetch failed for user %s", user_id)
        raise
    month_net = month_income - month_expenses
    return {
        "status": "success",
        "username": name,
        "today": today,
        "current_month": month,
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "net_profit": total_sales - total_expenses,
        "total_outstanding": outstanding,
        "outstanding_sale_count": outstanding_count,
        "month_income": month_income,
        "month_expenses": month_expenses,
        "month_net": month_net,
        "income_note": vs_last_month(month_income, prev_income, "No sales last month"),
        "expense_note": vs_last_month(month_expenses, prev_expenses, "No expenses last month"),
        "net_note": margin_note(month_income, month_net),
        "today_collected": today_collected,
        "today_expenses": today_expenses,
        "today_net": today_collected - today_expenses,
        "low_stock_items": low_stock,
    }
