#!/usr/bin/env python3
"""Query the protected Zhejiang Baijia read-only Codex API."""

from __future__ import annotations

import argparse
import ctypes
import getpass
import json
import os
import platform
import socket
import subprocess
import sys
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_BASE_URL = "https://www.baijia.com.my"
DEFAULT_TIMEOUT = 15.0
KEYCHAIN_SERVICE = "com.baijia.codex-readonly-api"
KEYCHAIN_ACCOUNT = "production"
WINDOWS_CREDENTIAL_TARGET = f"{KEYCHAIN_SERVICE}:{KEYCHAIN_ACCOUNT}"


def _windows_credential_types():
    """Build Windows Credential Manager ctypes declarations lazily."""
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    return wintypes, Credential


def _windows_advapi32():
    if platform.system() != "Windows":
        raise RuntimeError("Windows Credential Manager is only available on Windows")
    try:
        return ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise RuntimeError("Could not open Windows Credential Manager") from exc


class SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        old = urlsplit(req.full_url)
        new = urlsplit(newurl)
        if (old.scheme.lower(), old.netloc.lower()) != (new.scheme.lower(), new.netloc.lower()):
            raise HTTPError(req.full_url, 502, "Cross-origin redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def fail(message: str, *, status: int = 0, request_id: str | None = None, exit_code: int = 6) -> int:
    emit({
        "ok": False,
        "status": status,
        "request_id": request_id,
        "data": None,
        "error": message,
    })
    return exit_code


def keychain_token() -> str:
    if platform.system() != "Darwin":
        return ""
    try:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a", KEYCHAIN_ACCOUNT,
                "-s", KEYCHAIN_SERVICE,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def windows_credential_token() -> str:
    if platform.system() != "Windows":
        return ""

    wintypes, Credential = _windows_credential_types()
    credential_pointer = ctypes.POINTER(Credential)()
    advapi32 = _windows_advapi32()
    cred_read = advapi32.CredReadW
    cred_read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    cred_read.restype = wintypes.BOOL
    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    cred_free.restype = None

    if not cred_read(
        WINDOWS_CREDENTIAL_TARGET,
        1,  # CRED_TYPE_GENERIC
        0,
        ctypes.byref(credential_pointer),
    ):
        error_code = ctypes.get_last_error()
        if error_code == 1168:  # ERROR_NOT_FOUND
            return ""
        raise RuntimeError(f"Could not read Windows Credential Manager (error {error_code})")

    try:
        credential = credential_pointer.contents
        if credential.CredentialBlobSize == 0 or not credential.CredentialBlob:
            return ""
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return raw.decode("utf-16-le").strip()
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("Windows Credential Manager returned an invalid token") from exc
    finally:
        cred_free(credential_pointer)


def save_windows_credential(token: str) -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Windows Credential Manager is only available on Windows")

    wintypes, Credential = _windows_credential_types()
    raw = token.encode("utf-16-le")
    if len(raw) > 512:
        raise ValueError("API token is too long for Windows Credential Manager")
    blob = ctypes.create_string_buffer(raw)

    credential = Credential()
    credential.Flags = 0
    credential.Type = 1  # CRED_TYPE_GENERIC
    credential.TargetName = WINDOWS_CREDENTIAL_TARGET
    credential.Comment = "Baijia Codex Read-only API"
    credential.CredentialBlobSize = len(raw)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = KEYCHAIN_ACCOUNT

    advapi32 = _windows_advapi32()
    cred_write = advapi32.CredWriteW
    cred_write.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    cred_write.restype = wintypes.BOOL
    if not cred_write(ctypes.byref(credential), 0):
        error_code = ctypes.get_last_error()
        raise RuntimeError(f"Could not save Windows credential (error {error_code})")


def resolve_token() -> tuple[str, str]:
    token = os.environ.get("CAR_AIR_CODEX_API_TOKEN", "").strip()
    if token:
        return token, "environment"

    system = platform.system()
    if system == "Darwin":
        token = keychain_token()
        if token:
            return token, "macos_keychain"
        credential_store = "the macOS Keychain"
    elif system == "Windows":
        try:
            token = windows_credential_token()
        except RuntimeError as exc:
            raise ValueError(str(exc)) from None
        if token:
            return token, "windows_credential_manager"
        credential_store = "Windows Credential Manager"
    else:
        credential_store = "a supported operating-system credential store"

    raise ValueError(
        f"API token is not configured in CAR_AIR_CODEX_API_TOKEN or {credential_store}"
    )


def validated_config(timeout: float) -> tuple[str, str, str, float]:
    token, token_source = resolve_token()

    base_url = os.environ.get("CAR_AIR_API_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("CAR_AIR_API_BASE_URL must be an http(s) origin without credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("CAR_AIR_API_BASE_URL must use HTTPS except for localhost testing")
    if timeout <= 0 or timeout > 60:
        raise ValueError("timeout must be between 0 and 60 seconds")
    return base_url, token, token_source, timeout


def request_json(
    path: str, *, query: dict[str, Any] | None, timeout: float
) -> tuple[int, dict[str, Any], str, str]:
    base_url, token, token_source, timeout = validated_config(timeout)
    url = base_url + path
    if query:
        url += "?" + urlencode(query)

    request_id = "skill_" + uuid.uuid4().hex[:16]
    request = Request(url, method="GET", headers={
        "Accept": "application/json",
        "Authorization": "Bearer " + token,
        "User-Agent": "query-carair-products/2.0",
        "X-Request-ID": request_id,
    })
    opener = build_opener(SameOriginRedirectHandler())

    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    except (socket.timeout, TimeoutError):
        raise RuntimeError("Request timed out") from None
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise RuntimeError("Request timed out") from None
        raise RuntimeError("Could not connect to the product API") from None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Product API returned non-JSON data (HTTP {status})") from None
    if not isinstance(payload, dict):
        raise RuntimeError(f"Product API returned an invalid JSON shape (HTTP {status})")
    return status, payload, base_url, token_source


def run_request(path: str, *, query: dict[str, Any] | None, timeout: float) -> int:
    try:
        status, payload, base_url, token_source = request_json(path, query=query, timeout=timeout)
    except ValueError as exc:
        return fail(str(exc), exit_code=2)
    except RuntimeError as exc:
        return fail(str(exc), exit_code=6)

    request_id = payload.get("request_id")
    if status == 200 and payload.get("code") == 1:
        emit({
            "ok": True,
            "status": status,
            "request_id": request_id,
            "data": payload.get("data"),
            "connection": {
                "api_base_url": base_url,
                "token_source": token_source,
                "environment": (payload.get("data") or {}).get("environment"),
            },
            "error": None,
        })
        return 0

    message = str(payload.get("msg") or f"Product API request failed (HTTP {status})")
    if status == 401:
        exit_code = 3
    elif status in {404, 405, 422}:
        exit_code = 4
    elif status == 429:
        exit_code = 5
    else:
        exit_code = 6
    return fail(message, status=status, request_id=request_id, exit_code=exit_code)


def configure_keychain() -> int:
    if platform.system() != "Darwin":
        return fail("macOS Keychain configuration is only available on macOS", exit_code=2)
    print(
        "Enter the production read-only API token at the secure macOS Keychain prompt. "
        "The token will not be echoed or printed by this script.",
        file=sys.stderr,
    )
    try:
        result = subprocess.run([
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-a", KEYCHAIN_ACCOUNT,
            "-s", KEYCHAIN_SERVICE,
            "-l", "Baijia Codex Read-only API",
            "-w",
        ], check=False)
    except OSError:
        return fail("Could not start the macOS Keychain utility", exit_code=2)
    if result.returncode != 0:
        return fail("The macOS Keychain token was not saved", exit_code=2)
    emit({
        "ok": True,
        "status": 0,
        "request_id": None,
        "data": {
            "keychain_service": KEYCHAIN_SERVICE,
            "keychain_account": KEYCHAIN_ACCOUNT,
        },
        "error": None,
    })
    return 0


def configure_credential() -> int:
    system = platform.system()
    if system == "Darwin":
        return configure_keychain()
    if system != "Windows":
        return fail(
            "Secure credential configuration is supported only on macOS and Windows",
            exit_code=2,
        )

    print(
        "Enter the production read-only API token. Input is hidden and the token will be "
        "saved in Windows Credential Manager.",
        file=sys.stderr,
    )
    try:
        token = getpass.getpass("API token: ").strip()
    except (EOFError, KeyboardInterrupt):
        return fail("Credential configuration was cancelled", exit_code=2)
    if not token:
        return fail("API token cannot be empty", exit_code=2)

    try:
        save_windows_credential(token)
    except (RuntimeError, ValueError) as exc:
        return fail(str(exc), exit_code=2)
    finally:
        token = ""

    emit({
        "ok": True,
        "status": 0,
        "request_id": None,
        "data": {
            "credential_store": "windows_credential_manager",
            "credential_target": WINDOWS_CREDENTIAL_TARGET,
            "account": KEYCHAIN_ACCOUNT,
        },
        "error": None,
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query protected car air-conditioning product data")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="request timeout in seconds (default: 15)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="check API availability and authentication")
    subparsers.add_parser(
        "configure-credential",
        help="securely save the production token in the operating-system credential store",
    )
    subparsers.add_parser(
        "configure-keychain",
        help="macOS compatibility alias for configuring the Keychain token",
    )

    search = subparsers.add_parser("search", help="search products by code, name, model, or category")
    search.add_argument("query", nargs="?", default="", help="product code, name, or vehicle-model keywords")
    search.add_argument("--category", default="", help="category name or code")
    stock = search.add_mutually_exclusive_group()
    stock.add_argument("--in-stock", action="store_true", help="return only products with positive available stock")
    stock.add_argument("--out-of-stock", action="store_true", help="return products with zero or negative available stock")
    search.add_argument("--limit", type=int, default=10, choices=range(1, 21), metavar="1-20")
    search.add_argument("--offset", type=int, default=0, help="result offset (0-5000)")

    detail = subparsers.add_parser("detail", help="get one active product by exact product code")
    detail.add_argument("product_code", help="exact product code")

    customers = subparsers.add_parser("customers", help="search active customers by code or company name")
    customers.add_argument("query", help="customer code or company-name keywords")
    customers.add_argument("--limit", type=int, default=10, choices=range(1, 21), metavar="1-20")
    customers.add_argument("--offset", type=int, default=0, help="result offset (0-5000)")

    customer_price = subparsers.add_parser(
        "customer-price",
        help="get the cached latest sales-invoice price for an exact customer and product",
    )
    customer_price.add_argument("customer_code", help="exact customer code")
    customer_price.add_argument("product_code", help="exact product code")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "configure-credential":
        return configure_credential()
    if args.command == "configure-keychain":
        return configure_keychain()
    if args.command == "health":
        return run_request("/api/codex/health", query=None, timeout=args.timeout)
    if args.command == "detail":
        path = "/api/codex/products/" + quote(args.product_code, safe="")
        return run_request(path, query=None, timeout=args.timeout)
    if args.command == "customers":
        return run_request(
            "/api/codex/customers/search",
            query={"q": args.query, "limit": args.limit, "offset": args.offset},
            timeout=args.timeout,
        )
    if args.command == "customer-price":
        path = (
            "/api/codex/customers/"
            + quote(args.customer_code, safe="")
            + "/products/"
            + quote(args.product_code, safe="")
            + "/price"
        )
        return run_request(path, query=None, timeout=args.timeout)

    query: dict[str, Any] = {
        "q": args.query,
        "category": args.category,
        "limit": args.limit,
        "offset": args.offset,
    }
    if args.in_stock:
        query["in_stock"] = "true"
    elif args.out_of_stock:
        query["in_stock"] = "false"
    return run_request("/api/codex/products/search", query=query, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
