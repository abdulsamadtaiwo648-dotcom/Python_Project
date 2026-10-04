"""Auth Routes HTTP routes."""

from flask import flash, jsonify, make_response, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash
import json, logging, time, uuid
from ..app import (
    app,
    GENERIC_RESET_MESSAGE,
    complete_login,
    get_current_user_id,
    get_db,
    record_user_activity,
    record_user_login,
    is_unique_violation,
    is_valid_password,
    send_and_store_otp,
    verify_otp,
)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        privacy_accepted = request.form.get("privacy_accepted") == "on"
        otp_code = request.form.get("otp_code", "").strip()

        if otp_code:
            if not email:
                flash("Email is required for OTP verification.", "danger")
                return render_template("register.html")
            record, error = verify_otp(email, "register", otp_code, consume=False)
            if error:
                flash(error, "danger")
                return render_template("register.html", step="otp", pending_email=email)
            new_user_id = f"user_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            try:
                registration = json.loads(record.get("payload") or "{}")
                with get_db() as db:
                    db.execute(
                        "INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                        (new_user_id, email, registration.get("password"), registration.get("first_name"), registration.get("last_name"))
                    )
                    record_user_activity(db, new_user_id, "account_created", "Created a SoloBiz account")
                    db.commit()
                verify_otp(email, "register", otp_code, consume=True)
                session.pop("user_id", None)
                flash("Your account is ready. Please sign in.", "success")
                return redirect("/login")
            except Exception as e:
                logging.error(f"Account creation failed after OTP verify: {e}", exc_info=True)
                if is_unique_violation(e):
                    flash("Email already registered. Please log in.", "danger")
                    return render_template("register.html")
                flash("Account creation failed. Please try again.", "danger")
                return render_template("register.html", step="otp", pending_email=email)

        if not email or not password or not first_name or not last_name or not confirm_password:
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html")
        if not privacy_accepted:
            flash("Please review and accept the Privacy Policy to create an account.", "danger")
            return render_template("register.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
        if not is_valid_password(password):
            flash("Password must be at least 8 characters and include a letter and a number.", "danger")
            return render_template("register.html")

        try:
            with get_db() as db:
                existing = db.execute(
                    "SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)
                ).fetchone()
                if existing:
                    flash("Email already registered. Please log in.", "danger")
                    return render_template("register.html", error="Email already registered. Please log in.")
        except Exception as e:
            logging.error(f"User check error during registration: {e}", exc_info=True)
            flash("Could not start registration. Please try again.", "danger")
            return render_template("register.html")

        ok, message, status, is_live = send_and_store_otp(
            email, "register", json.dumps({"password": generate_password_hash(password), "first_name": first_name, "last_name": last_name}), "Email Verification"
        )
        flash(message, "success" if ok else "danger")
        if not ok:
            return render_template("register.html"), status if status != 429 else 200
        return render_template("register.html", step="otp", pending_email=email)

    return render_template("register.html")


@app.route("/api/register/request", methods=["POST"])
def register_api_request():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()
        password = (data.get("password") or "").strip()
        confirm_password = (data.get("confirm_password") or "").strip()
        privacy_accepted = data.get("privacy_accepted") is True

        if not email or not first_name or not last_name or not password or not confirm_password:
            return jsonify({"status": "error", "message": "Complete all required fields."}), 400
        if not privacy_accepted:
            return jsonify({"status": "error", "message": "Please review and accept the Privacy Policy to create an account."}), 400
        if password != confirm_password:
            return jsonify({"status": "error", "message": "Passwords do not match."}), 400
        if not is_valid_password(password):
            return jsonify({"status": "error", "message": "Password must be at least 8 characters long and contain both letters and numbers."}), 400

        with get_db() as db:
            if db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone():
                return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400

        ok, message, status, _ = send_and_store_otp(
            email, "register", json.dumps({"password": generate_password_hash(password), "first_name": first_name, "last_name": last_name}), "Email Verification"
        )
        if not ok:
            return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": message, "code": None})
    except Exception as e:
        logging.error(f"register_api_request error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to send verification PIN. Please try again."}), 500


@app.route("/api/register/verify", methods=["POST"])
def register_api_verify():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()

        if not email or not code:
            return jsonify({"status": "error", "message": "Email and verification PIN are required."}), 400

        with get_db() as db:
            if db.execute("SELECT 1 FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone():
                return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400

        record, error = verify_otp(email, "register", code, consume=False)
        if error:
            return jsonify({"status": "error", "message": error}), 400

        new_user_id = f"user_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        registration = json.loads(record.get("payload") or "{}")
        with get_db() as db:
            db.execute(
                "INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                (new_user_id, email, registration.get("password"), registration.get("first_name"), registration.get("last_name"))
            )
            record_user_activity(db, new_user_id, "account_created", "Created a SoloBiz account")
            db.commit()
        verify_otp(email, "register", code, consume=True)
        session.pop("user_id", None)
        flash("Your account is ready. Please sign in.", "success")
        return jsonify({"status": "ok", "message": "Account created. Please sign in.", "redirect": "/login"})
    except Exception as e:
        logging.error(f"register_api_verify error: {e}", exc_info=True)
        if is_unique_violation(e):
            return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400
        return jsonify({"status": "error", "message": "Failed to verify account. Please try again."}), 500


@app.route("/api/register/resend", methods=["POST"])
def register_api_resend():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"status": "error", "message": "Email address is required."}), 400

        with get_db() as db:
            existing = db.execute(
                "SELECT payload FROM otp_codes WHERE email = ? AND purpose = ?",
                (email, "register")
            ).fetchone()
        if not existing:
            return jsonify({"status": "error", "message": "No pending registration found for this email."}), 400

        ok, message, status, _ = send_and_store_otp(
            email, "register", existing["payload"], "Email Verification"
        )
        if not ok:
            return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": message, "code": None})
    except Exception as e:
        logging.error(f"register_api_resend error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to resend PIN. Please try again."}), 500


@app.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user_id():
        return redirect("/dashboard")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            response = make_response(render_template("login.html"))
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return response

        try:
            with get_db() as db:
                user = db.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
                if not user or not user["password"] or not check_password_hash(user["password"], password):
                    if user:
                        record_user_activity(db, user["id"], "sign_in_failed", "Unsuccessful sign-in attempt")
                    flash("Invalid email or password. Please try again.", "danger")
                    return render_template("login.html")
                if user["account_status"] != "active":
                    record_user_activity(db, user["id"], "sign_in_blocked", "Sign-in attempt blocked because the account is paused")
                    flash("This account is currently unavailable. Please contact support.", "danger")
                    return render_template("login.html")
                record_user_login(db, user["id"])
                complete_login(user["id"])
                return redirect("/dashboard")
        except Exception as e:
            logging.error(f"Login error for '{email}': {e}", exc_info=True)
            flash("An unexpected error occurred. Please try again.", "danger")
            return render_template("login.html")

    return render_template("login.html")


@app.after_request
def prevent_login_page_from_being_cached(response):
    # Back/forward navigation must re-check the current session instead of
    # restoring a stale login form from the browser cache after sign-in.
    if request.path == "/login":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect("/login"))
    resp.delete_cookie(app.config.get("SESSION_COOKIE_NAME", "session"))
    return resp


@app.route("/api/forgot-password/request", methods=["POST"])
def forgot_password_request():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"status": "error", "message": "Please enter a valid email address."}), 400

        with get_db() as db:
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
            if user:
                record_user_activity(db, user["id"], "password_change_requested", "Requested a password reset")
        if user:
            ok, message, status, _ = send_and_store_otp(email, "reset", None, "Password Reset")
            if not ok:
                return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": GENERIC_RESET_MESSAGE, "code": None})
    except Exception as e:
        logging.error(f"forgot_password_request error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to generate PIN. Please try again."}), 500


@app.route("/api/forgot-password/resend", methods=["POST"])
def forgot_password_resend():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"status": "error", "message": "Please enter a valid email address."}), 400
        with get_db() as db:
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
            if user:
                record_user_activity(db, user["id"], "password_reset_code_resent", "Requested another password reset code")
        if user:
            ok, message, status, _ = send_and_store_otp(email, "reset", None, "Password Reset")
            if not ok:
                return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": GENERIC_RESET_MESSAGE, "code": None})
    except Exception as e:
        logging.error(f"forgot_password_resend error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to resend PIN. Please try again."}), 500


@app.route("/api/forgot-password/reset", methods=["POST"])
def forgot_password_reset():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()
        new_password = (data.get("password") or "").strip()

        if not email or not code or not new_password:
            if email:
                with get_db() as db:
                    user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
                    if user:
                        record_user_activity(db, user["id"], "password_change_failed", "Password change submission was incomplete")
            return jsonify({"status": "error", "message": "Email, verification PIN, and new password are required."}), 400
        if not is_valid_password(new_password):
            with get_db() as db:
                user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
                if user:
                    record_user_activity(db, user["id"], "password_change_failed", "Password change attempt did not meet security requirements")
            return jsonify({"status": "error", "message": "New password must be at least 8 characters and include a letter and a number."}), 400

        with get_db() as db:
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
            if not user:
                return jsonify({"status": "error", "message": "No account exists for this email. Please register first."}), 404

        record, error = verify_otp(email, "reset", code, consume=True)
        if error:
            with get_db() as db:
                user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
                if user:
                    record_user_activity(db, user["id"], "password_change_failed", "Password reset verification failed")
            return jsonify({"status": "error", "message": error}), 400

        hashed = generate_password_hash(new_password)
        with get_db() as db:
            db.execute("UPDATE users SET password = ? WHERE LOWER(email) = LOWER(?)", (hashed, email))
            db.commit()
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
            if user:
                record_user_activity(db, user["id"], "password_changed", "Password was changed through account recovery")
                record_user_login(db, user["id"])
                complete_login(user["id"])

        return jsonify({"status": "ok", "message": "Password updated successfully!", "redirect": "/dashboard"})
    except Exception as e:
        logging.error(f"forgot_password_reset error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to update password. Please try again."}), 500
