"""Manual expense-flow check using an isolated temporary SQLite database."""

import os
import tempfile


previous_directory = os.getcwd()
database_url = os.environ.pop("DATABASE_URL", None)
sqlite_database_path = os.environ.get("SQLITE_DATABASE_PATH")

try:
    with tempfile.TemporaryDirectory(prefix="solobiz-expense-flow-") as temp_directory:
        os.chdir(temp_directory)
        os.environ["SQLITE_DATABASE_PATH"] = os.path.join(temp_directory, "solobiz.db")

        # Importing the application initializes its database in the temp directory.
        from server.app import app

        with app.test_client() as client:
            csrf_token = "local-expense-flow-check"
            with client.session_transaction() as session:
                session["user_id"] = "user-123"
                session["csrf_token"] = csrf_token

            add = client.post("/add", json={
                "amount": 150.5,
                "category": "Fuel & Electricity",
                "description": "Generator fuel",
            }, headers={"X-CSRFToken": csrf_token})
            print("ADD", add.status_code, add.get_json())
            expense_id = add.get_json()["expense"]["id"]

            update = client.put(f"/api/expenses/{expense_id}", json={
                "amount": 199.99,
                "category": "Others",
                "description": "Updated fuel",
            }, headers={"X-CSRFToken": csrf_token})
            print("PUT", update.status_code, update.get_json())

            delete = client.post(f"/delete/{expense_id}", headers={"X-CSRFToken": csrf_token})
            print("DELETE_WEB", delete.status_code, delete.location)

            expenses = client.get("/api/expenses")
            print("GET_API", expenses.status_code, expenses.get_json())
finally:
    os.chdir(previous_directory)
    if database_url is not None:
        os.environ["DATABASE_URL"] = database_url
    if sqlite_database_path is None:
        os.environ.pop("SQLITE_DATABASE_PATH", None)
    else:
        os.environ["SQLITE_DATABASE_PATH"] = sqlite_database_path
