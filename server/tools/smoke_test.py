"""Smoke-test a running SoloBiz release before sending it real traffic.

Usage:
    python -m server.tools.smoke_test https://solobiz-green.onrender.com

Read-only: it only sends GET requests and never signs in. Exits 0 when every
check passes, 1 otherwise. Pass --expect-commit <sha> to also confirm which
commit the release is running.
"""

import argparse
import sys

import requests


def run(base_url, expect_commit=None, timeout=60):
    base_url = base_url.rstrip("/")
    failures = []

    def check(label, ok, detail=""):
        print(("PASS  " if ok else "FAIL  ") + label + (f"  ({detail})" if detail and not ok else ""))
        if not ok:
            failures.append(label)

    def get(path, **kwargs):
        return requests.get(base_url + path, timeout=timeout, allow_redirects=False, **kwargs)

    try:
        health = get("/healthz")
    except requests.RequestException as error:
        check("service answers", False, str(error))
        return failures
    body = health.json() if health.headers.get("content-type", "").startswith("application/json") else {}
    check("health check is ok and the database is reachable", health.status_code == 200 and body.get("status") == "ok", f"HTTP {health.status_code}")
    print(f"      version {body.get('version')}  commit {body.get('commit') or 'unknown'}")
    if expect_commit:
        check(f"running commit {expect_commit[:7]}", (body.get("commit") or "") == expect_commit[:7], body.get("commit") or "unknown")

    login = get("/login")
    check("login page loads with a CSRF token", login.status_code == 200 and 'name="csrf_token"' in login.text, f"HTTP {login.status_code}")
    check("register page loads", get("/register").status_code == 200)
    check("landing page loads", get("/").status_code == 200)
    dashboard = get("/dashboard")
    check("dashboard requires sign-in", dashboard.status_code in (301, 302) and "/login" in dashboard.headers.get("Location", ""), f"HTTP {dashboard.status_code}")
    check("data API requires sign-in", get("/api/expenses").status_code == 401)
    check("website API requires sign-in", get("/api/website").status_code == 401)
    check("stylesheet is served", get("/static/solobiz-ui.css").status_code == 200)
    check("service worker is served", get("/sw.js").status_code == 200)
    check("unknown website address is a 404", get("/site/this-name-is-not-used").status_code == 404)
    check("sign-out by link is ignored", get("/logout").status_code in (301, 302))
    check("removed pages stay removed", get("/user-count").status_code == 404 and get("/floor").status_code == 404)
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("base_url")
    parser.add_argument("--expect-commit")
    args = parser.parse_args()
    failed = run(args.base_url, args.expect_commit)
    print("\nAll checks passed." if not failed else f"\n{len(failed)} check(s) failed.")
    sys.exit(1 if failed else 0)
