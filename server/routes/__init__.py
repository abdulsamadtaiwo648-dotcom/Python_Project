"""Route modules for the SoloBiz web application."""

from . import auth_routes, expense_routes, inventory_routes, misc_routes
from . import floor_routes, page_routes, profile_routes, sales_routes

__all__ = [
    "auth_routes",
    "expense_routes",
    "floor_routes",
    "inventory_routes",
    "misc_routes",
    "page_routes",
    "profile_routes",
    "sales_routes",
]
