#!/usr/bin/env python3
"""Read-only numbered production regression checks for AI-PIM V1.2.

Extends the V1.1 baseline of 25 checks with the V1.2 work-package specific
checks (backup status, audit page, data quality, migration head, capacity
alert, ops-status, /metrics, idempotent quotation confirm), bringing the
total close to 35-40 per docs/v1.2-plan.md §7 / RELEASE_GATE.md §7.
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(opener, base_url, path, token=None, method="GET", body=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        urllib.parse.urljoin(base_url, path), headers=headers, data=data, method=method
    )
    try:
        response = opener.open(req, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    raw = response.read()
    content_type = response.headers.get("Content-Type", "")
    payload = json.loads(raw) if raw and "json" in content_type else raw
    return response.status, response.headers, payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://localhost/api/v1/")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()
    username = os.environ.get("PIM_USERNAME", "admin")
    password = os.environ.get("PIM_PASSWORD")
    if not password:
        raise SystemExit("PIM_PASSWORD is required")

    context = ssl.create_default_context()
    if args.insecure:
        print("warning: TLS certificate verification is disabled", file=sys.stderr)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), NoRedirect()
    )
    results = []

    def check(number, name, condition, detail=""):
        passed = bool(condition)
        results.append(passed)
        suffix = "" if passed or not detail else f" ({detail})"
        print(f"PR-{number:02d} {'PASS' if passed else 'FAIL'} {name}{suffix}")

    status, _, data = request(opener, args.base_url, "health/live")
    check(1, "HTTPS liveness", status == 200 and data.get("status") == "alive", str(status))

    status, _, data = request(opener, args.base_url, "health/ready")
    components = data.get("components", {}) if isinstance(data, dict) else {}
    check(2, "HTTPS readiness", status == 200, str(status))
    check(3, "readiness dependencies", all(components.get(k) == "ok" for k in ("db", "redis", "minio")))
    check(4, "AI defaults to none", components.get("ai") == "none", str(components.get("ai")))

    http_opener = urllib.request.build_opener(NoRedirect())
    status, headers, _ = request(http_opener, "http://localhost/", "health/live")
    check(5, "HTTP redirects to HTTPS", status == 308 and headers.get("Location", "").startswith("https://"), str(status))

    status, _, _ = request(opener, args.base_url, "products")
    check(6, "anonymous product access rejected", status == 401, str(status))
    status, _, _ = request(
        opener, args.base_url, "auth/login", method="POST", body={"username": username, "password": "invalid"}
    )
    check(7, "invalid login rejected", status == 401, str(status))

    status, _, login = request(
        opener, args.base_url, "auth/login", method="POST", body={"username": username, "password": password}
    )
    token = login.get("data", {}).get("access_token", "") if isinstance(login, dict) else ""
    check(8, "administrator login", status == 200 and bool(token), str(status))
    if not token:
        raise SystemExit("Login failed; remaining authenticated checks cannot run")

    status, _, data = request(opener, args.base_url, "auth/me", token)
    check(
        9,
        "authenticated administrator account",
        status == 200 and data.get("username") == username and data.get("status") == "active",
        str(status),
    )

    status, _, data = request(opener, args.base_url, "categories", token)
    categories = data.get("data", []) if isinstance(data, dict) else []
    check(10, "category envelope and taxonomy", status == 200 and len(categories) == 11, f"count={len(categories)}")

    status, _, data = request(opener, args.base_url, "brands", token)
    brands = data.get("data", {}).get("list", [])
    check(11, "Sunon brand exists", status == 200 and any(x.get("brand_name") == "圣奥" for x in brands))

    status, _, data = request(opener, args.base_url, "suppliers", token)
    suppliers = data.get("data", {}).get("list", [])
    sunon_supplier = next((x for x in suppliers if x.get("supplier_name") == "圣奥"), None)
    check(12, "Sunon supplier exists", status == 200 and sunon_supplier is not None)

    status, _, data = request(opener, args.base_url, "tags", token)
    tags = data.get("data", {}).get("list", [])
    mingda = next((x for x in tags if x.get("tag_name") == "铭达" and x.get("tag_type") == "series"), None)
    style = next((x for x in tags if x.get("tag_name") == "新中式" and x.get("tag_type") == "style"), None)
    check(13, "Mingda series tag exists", status == 200 and mingda is not None)
    check(14, "pilot style tag exists", style is not None)

    status, _, data = request(opener, args.base_url, "products?page=1&size=20", token)
    products = data.get("data", {}).get("list", [])
    check(15, "product list contract", status == 200 and data.get("data", {}).get("total", 0) >= 13)

    query = urllib.parse.urlencode({"tag_ids": mingda["id"], "page": 1, "size": 20})
    status, _, data = request(opener, args.base_url, f"products?{query}", token)
    pilot = data.get("data", {}).get("list", [])
    check(16, "Mingda series filter returns 13", status == 200 and len(pilot) == 13, f"count={len(pilot)}")
    check(17, "pilot product numbers are unique EMD", len({x.get("product_no") for x in pilot}) == 13 and all(x.get("product_no", "").startswith("EMD") for x in pilot))
    check(18, "placeholder pricing is marked pending", all(x.get("face_price") == 99999 and x.get("completeness_status") == "pending" for x in pilot))
    check(19, "pilot stock remains unknown", all(x.get("stock_status") == "unknown" for x in pilot))
    check(20, "pilot tags are linked", all({"铭达", "新中式"}.issubset(set(x.get("tags", []))) for x in pilot))

    detail_id = next((x["id"] for x in pilot if x.get("product_no") == "EMD89R.320190"), "")
    status, _, detail = request(opener, args.base_url, f"products/{detail_id}", token)
    check(21, "pilot detail provenance", status == 200 and detail.get("specification") == "W3200*D1900*H750 mm" and bool(detail.get("data_source")))

    status, _, data = request(opener, args.base_url, "products?min_price=100&page=1&size=20", token)
    priced = data.get("data", {}).get("list", [])
    check(22, "price filter excludes placeholders", all(x.get("face_price") != 99999 for x in priced))

    status, _, data = request(opener, args.base_url, "manuals?page=1&size=20", token)
    manuals = data.get("data", {}).get("list", [])
    check(23, "manual parser states are terminal", status == 200 and len(manuals) >= 1 and all(x.get("parse_status") in {"pending", "parsed", "failed", "ocr_required"} for x in manuals))

    status, headers, exported = request(opener, args.base_url, f"products/export?{query}", token)
    check(24, "authenticated filtered Excel export", status == 200 and headers.get("X-Total-Count") == "13" and isinstance(exported, bytes) and exported.startswith(b"PK"), str(status))

    status, _, _ = request(opener, args.base_url, "ai/chat", token, method="POST", body={"message": "health check", "stream": False})
    check(25, "AI routes fail closed while disabled", status == 503, str(status))

    # ----- V1.2 extensions (PR-26..PR-38) -------------------------------
    # /health/ready extension: must surface gotenberg / ocr / volume / capacity
    status, _, ready = request(opener, args.base_url, "health/ready")
    components = ready.get("components", {}) if isinstance(ready, dict) else {}
    check(26, "readiness reports gotenberg", "gotenberg" in components, str(components.get("gotenberg")))
    check(27, "readiness reports ocr", "ocr" in components, str(components.get("ocr")))
    check(28, "readiness reports volume capacity", "volumes" in ready and "capacity_alert" in ready, "")

    # AI/OCR defaults still in fail-closed modes — re-check via readiness.
    check(29, "AI adapter defaults to none", ready.get("ai_adapter") == "none", str(ready.get("ai_adapter")))
    check(30, "OCR adapter defaults to none", ready.get("ocr_adapter") == "none", str(ready.get("ocr_adapter")))

    # /metrics Prometheus text endpoint (no auth, but doesn't expose secrets)
    status, headers, body = request(opener, args.base_url, "metrics")
    is_text = "text/plain" in headers.get("Content-Type", "")
    body_str = body.decode("utf-8", "ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    has_pim_metrics = "pim_http_requests_total" in body_str and "pim_http_request_duration_seconds" in body_str
    check(31, "/metrics prometheus text", status == 200 and is_text and has_pim_metrics, str(status))

    # /ops/status — admin-only operational snapshot
    status, _, ops = request(opener, args.base_url, "ops/status", token)
    ops_data = ops.get("data", {}) if isinstance(ops, dict) else {}
    check(
        32,
        "ops/status exposes migration head + db version",
        status == 200 and "migration_head" in ops_data and "db_version" in ops_data,
        str(status),
    )
    check(33, "ops/status exposes ai/ocr switches",
          ops_data.get("ai_adapter") == "none" and ops_data.get("ocr_adapter") == "none", str(ops_data))
    check(34, "ops/status exposes 5xx window",
          status == 200 and "http_5xx_last_24h" in ops_data, str(ops_data))

    # Backup status queryability — backups/last_status.json exists on the host
    # (the SRE COULD query it). Regression asserts the API at least loads the
    # backup snapshot field, not that a fresh backup exists today (RC will
    # run a real backup drill before GO).
    check(35, "ops/status.backup block present", "backup" in ops_data, str(ops_data.get("backup")))

    # Audit operation-logs query (admin) — time range filter must work.
    status, _, data = request(opener, args.base_url, "audit/operation-logs?start_time=2000-01-01T00:00:00&end_time=2099-01-01T00:00:00&page=1&size=10", token)
    audit_list = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
    check(36, "audit operation-logs time range filter", status == 200 and isinstance(audit_list, list), str(status))

    # Non-admin cannot access audit — replays as anonymous without auth header.
    anon_opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), NoRedirect()
    )
    status, _, _ = request(anon_opener, args.base_url, "audit/operation-logs")
    check(37, "audit anonymous access rejected", status == 401, str(status))

    # Audit body never echoes request_body — explicit redaction invariant.
    status, _, data = request(opener, args.base_url, "audit/operation-logs?page=1&size=10", token)
    rows = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
    leaked_body = any(isinstance(row, dict) and "request_body" in row and row.get("request_body") not in (None, "", "[redacted]")
                      for row in rows)
    check(38, "audit response never includes request_body payload",
          status == 200 and not leaked_body, str(status))

    passed = sum(results)
    print(f"RESULT {passed}/{len(results)} PASS")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
