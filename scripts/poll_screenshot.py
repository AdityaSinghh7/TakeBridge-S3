#!/usr/bin/env python3
import argparse
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime


DEFAULT_URL = "http://34.56.100.192:5000/screenshot"


def parse_headers(header_list):
    headers = {}
    for item in header_list:
        if ":" not in item:
            raise ValueError(f"Invalid header (expected 'Key: Value'): {item}")
        key, value = item.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def should_log_body(content_type):
    if not content_type:
        return False
    ct = content_type.split(";", 1)[0].strip().lower()
    return ct.startswith("text/") or ct in {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-www-form-urlencoded",
    }


def log_line(message):
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()


def run_poll(url, interval, timeout, headers, max_bytes):
    while True:
        req = urllib.request.Request(url, method="GET", headers=headers)
        log_line(f"Request: {req.method} {req.full_url}")
        if headers:
            log_line(f"Request headers: {headers}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                reason = resp.reason
                resp_headers = resp.headers
                body = resp.read()
        except urllib.error.HTTPError as err:
            status = err.code
            reason = err.reason
            resp_headers = err.headers
            body = err.read()
        except urllib.error.URLError as err:
            log_line(f"Response error: {err}")
            time.sleep(interval)
            continue

        if status == 200:
            content_length = resp_headers.get("Content-Length", str(len(body)))
            log_line(
                f"Response: {status} {reason} (len={content_length} bytes)"
            )
        else:
            log_line(f"Response: {status} {reason}")
            if resp_headers:
                log_line("Response headers:")
                for key, value in resp_headers.items():
                    print(f"{key}: {value}")

            content_type = resp_headers.get("Content-Type", "")
            body_len = len(body)
            if should_log_body(content_type):
                shown = body[:max_bytes] if max_bytes > 0 else body
                truncated = len(shown) < body_len
                rendered = shown.decode("utf-8", errors="replace")
                log_line(
                    f"Response body: {body_len} bytes total, {len(shown)} bytes shown"
                )
                if truncated:
                    log_line("Response body (truncated):")
                else:
                    log_line("Response body:")
                print(rendered)
            else:
                log_line(
                    f"Response body: {body_len} bytes (not logged for content-type {content_type})"
                )
            sys.stdout.flush()
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description="Poll an HTTP endpoint and print requests and responses."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Endpoint URL")
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds to wait between requests",
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="Request timeout in seconds"
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=4096,
        help="Max bytes of response body to show; 0 shows full body",
    )
    parser.add_argument(
        "-H",
        "--header",
        action="append",
        default=[],
        help="Add a request header (repeatable), e.g. -H 'Accept: image/png'",
    )
    args = parser.parse_args()

    try:
        headers = parse_headers(args.header)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        run_poll(args.url, args.interval, args.timeout, headers, args.max_bytes)
    except KeyboardInterrupt:
        log_line("Stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())