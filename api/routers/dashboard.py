"""Dashboard summary: the figures behind the KPI cards and daily check-in.

Month figures are for one calendar month, chosen by the client or defaulted by the server, and
are counted on each record's business date (entry_date), never on the time it was saved."""

import calendar
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from server.database import get_db

from ..deps import require_user

router = APIRouter(prefix="/api")

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def month_label(ym):
    """'2026-11' -> 'November 2026'."""
    year, month = ym.split("-")
    return f"{calendar.month_name[int(month)]} {year}"


def shift_month(ym, delta):
    """'2026-01' shifted by -1 -> '2025-12'."""
    year, month = (int(x) for x in ym.split("-"))
    index = year * 12 + (month - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


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


def months_with_data(db, user_id):
    """Every month that has a sale, expense or money in, newest first."""
    rows = db.execute(
        """SELECT DISTINCT SUBSTR(entry_date, 1, 7) AS ym FROM (
               SELECT entry_date FROM income WHERE user_id = ?
               UNION ALL SELECT entry_date FROM expenses WHERE user_id = ?
               UNION ALL SELECT entry_date FROM money_in WHERE user_id = ?
           ) AS records WHERE entry_date IS NOT NULL""",
        (user_id, user_id, user_id),
    ).fetchall()
    return sorted({r["ym"] for r in rows if r["ym"]}, reverse=True)


def _error(message, status=400):
    return JSONResponse({"status": "error", "message": message}, status_code=status)


@router.get("/dashboard")
def dashboard(month: str | None = Query(None), user_id: str = Depends(require_user)):
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    current = now.strftime("%Y-%m")
    if month is not None:
        if not MONTH_RE.match(month):
            return _error("Choose a month in the form YYYY-MM.")
        if month > current:
            return _error("You can't choose a month after this one.")
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

            # The month shown: the one asked for, or by default this month, or the latest month with
            # data when this month is still empty.
            all_months = [m for m in months_with_data(db, user_id) if m <= current]
            notice = None
            if month is not None:
                selected = month
            else:
                selected = current
                if current not in all_months and all_months:
                    selected = all_months[0]
                    notice = {
                        "current_month": current,
                        "shown_month": selected,
                        "message": f"No records in {month_label(current)} yet. Showing {month_label(selected)}.",
                    }
            previous = shift_month(selected, -1)

            month_income = _sum(db, income_sql, (user_id, selected + "%"))
            month_expenses = _sum(db, expense_sql, (user_id, selected + "%"))
            prev_income = _sum(db, income_sql, (user_id, previous + "%"))
            prev_expenses = _sum(db, expense_sql, (user_id, previous + "%"))
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
        "current_month": current,
        "selected_month": selected,
        "months_with_data": all_months,
        "notice": notice,
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
