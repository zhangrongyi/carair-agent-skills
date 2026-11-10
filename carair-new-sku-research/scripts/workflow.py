#!/usr/bin/env python3
"""Research a new part, write one Lark record, and return it for human review."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = os.environ.get("CARAIR_DEVELOPMENT_BASE_URL", "https://hsgvx2m70fxp.sg.larksuite.com/base/EN5xbeBc4apmP9s9ml8lPB8hgbd")
PEERS_URL = os.environ.get("CARAIR_PEERS_BASE_URL", "https://hsgvx2m70fxp.sg.larksuite.com/base/CnRAbuzkoa8ebSsb4w6lesoxg0E")
TRADE_TABLE = "tbl1rZCcrOzPSMZT"
PEER_TABLE = "tblSqbzCKJgUgXOt"
LOOKUP_FIELDS = ["外部参考编号", "品牌", "车型", "年份", "类目", "产品描述", "厂家编号", "CXA编号", "核对来源链接"]
WRITE_FIELDS = ["外部参考编号", "品牌", "车型", "年份", "类目", "产品描述", "同行价格", "车款信息说明", "采购说明", "核对来源链接", "项目阶段", "开发类型"]
DRAFT_FIELDS = set(WRITE_FIELDS) - {"项目阶段", "开发类型"}
FORBIDDEN_FIELDS = {"供应商", "厂家编号", "成本", "计划售价", "CXA编号", "订单号", "下单时间"}
MAX_SOURCE_IMAGE_BYTES = 15 * 1024 * 1024
CATEGORY_ALIASES = {"冷凝器": "CONDENSER", "蒸发器": "COOLING COIL", "鼓风机": "BLOWER MOTOR",
                    "风扇马达": "FAN MOTOR", "压缩机": "COMPRESSOR", "膨胀阀": "EXPANSION VALVE",
                    "电磁离合器": "MAGNET CLUTCH"}


class WorkflowError(Exception):
    pass


def emit(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def token_from_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith("larksuite.com"):
        raise WorkflowError("Lark Base URL must be an HTTPS larksuite.com URL")
    match = re.search(r"/base/([A-Za-z0-9]+)", parsed.path)
    if not match:
        raise WorkflowError("Lark Base URL has no base token")
    return match.group(1)


def run_json(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkflowError(f"Command unavailable or timed out: {argv[0]}") from exc
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Non-JSON response from {argv[0]}") from exc
    if result.returncode != 0 or not payload.get("ok"):
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else str(error or "unknown error")
        raise WorkflowError(f"{argv[0]} failed: {message}")
    return payload


def lark(*args):
    if not shutil.which("lark-cli"):
        raise WorkflowError("lark-cli is not installed")
    return run_json(["lark-cli", "base", *args, "--as", "user"])


def fields(base_url, table):
    result = lark("+field-list", "--base-token", token_from_url(base_url), "--table-id", table)
    return {item["name"]: item for item in result["data"]["fields"]}


def require_fields(base_url, table, names):
    actual = fields(base_url, table)
    missing = sorted(set(names) - actual.keys())
    if missing:
        raise WorkflowError("Missing Lark fields: " + ", ".join(missing))
    return actual


def check_category_option(field_map, category):
    options = {item.get("name") for item in field_map["类目"].get("options", [])}
    if category not in options:
        raise WorkflowError("类目 must be an existing Lark option: " + ", ".join(sorted(x for x in options if x)))


def records(base_url, table, wanted_fields):
    base_token = token_from_url(base_url)
    output = []
    offset = 0
    while True:
        argv = ["+record-list", "--base-token", base_token, "--table-id", table,
                "--limit", "200", "--offset", str(offset), "--json"]
        for name in wanted_fields:
            argv += ["--field-id", name]
        result = lark(*argv)["data"]
        names = result["fields"]
        rows = result["data"]
        ids = result["record_id_list"]
        if len(rows) != len(ids):
            raise WorkflowError("Lark record matrix is inconsistent")
        output.extend({"record_id": record_id, "fields": dict(zip(names, row))}
                      for record_id, row in zip(ids, rows))
        if not result.get("has_more"):
            return output
        if not rows:
            raise WorkflowError("Lark pagination stopped before all records were read")
        offset += len(rows)


def plain(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(plain(v) for v in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("value") or "")
    return str(value)


def norm(value):
    return re.sub(r"[^a-z0-9]", "", plain(value).lower())


def product_client():
    override = os.environ.get("CARAIR_PRODUCT_CLIENT")
    if override:
        path = Path(override).expanduser()
    else:
        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        path = home / "skills" / "query-carair-products" / "scripts" / "query_products.py"
    if not path.is_file():
        raise WorkflowError("Install query-carair-products Skill or set CARAIR_PRODUCT_CLIENT")
    return path


def product_search(queries):
    path = product_client()
    python = "py" if sys.platform == "win32" else sys.executable
    prefix = [python, "-3"] if sys.platform == "win32" else [python]
    results = []
    for query in dict.fromkeys(q.strip() for q in queries if q and q.strip()):
        result = run_json([*prefix, str(path), "search", query, "--limit", "20"])
        results.append({"query": query, "data": result.get("data"), "connection": result.get("connection")})
    if not results:
        raise WorkflowError("At least one product search query is required")
    return results


def reference_queries(reference):
    """Search each supplied number separately; the product API matches query terms jointly."""
    parts = [part.strip() for part in re.split(r"[;,\n]", reference) if part.strip()]
    queries = []
    for part in parts:
        if re.search(r"\d", part):
            queries.append(part)
            queries.extend(token for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{3,}", part)
                           if re.search(r"\d", token))
    return list(dict.fromkeys(queries or parts or ([reference] if reference.strip() else [])))


def is_image(path):
    with Path(path).open("rb") as stream:
        header = stream.read(12)
    return (header.startswith(b"\xff\xd8\xff") or header.startswith(b"\x89PNG\r\n\x1a\n")
            or header.startswith((b"GIF87a", b"GIF89a"))
            or (header.startswith(b"RIFF") and header[8:12] == b"WEBP"))


def image_extension(header):
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    raise WorkflowError("Source URL did not return a supported product image")


def public_https_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise WorkflowError("Source image URL must be public HTTPS without credentials")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
        raise WorkflowError("Source image URL must use a public host")
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except (OSError, ValueError) as exc:
        raise WorkflowError("Could not resolve source image host") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise WorkflowError("Source image URL resolved to a non-public address")


class PublicImageRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_source_images(source_images, directory):
    opener = build_opener(PublicImageRedirects())
    paths = []
    for source in source_images:
        public_https_url(source["image_url"])
        request = Request(source["image_url"], headers={
            "User-Agent": "Mozilla/5.0 (compatible; CarAirResearch/1.0)",
            "Referer": source["page_url"],
            "Accept": "image/jpeg,image/png,image/webp,image/gif",
        })
        try:
            with opener.open(request, timeout=20) as response:
                if not response.headers.get_content_type().startswith("image/"):
                    raise WorkflowError("Source URL returned non-image content")
                body = response.read(MAX_SOURCE_IMAGE_BYTES + 1)
        except WorkflowError:
            raise
        except (OSError, TimeoutError) as exc:
            raise WorkflowError("Could not download source product image") from exc
        if len(body) > MAX_SOURCE_IMAGE_BYTES:
            raise WorkflowError("Source product image exceeds 15 MB")
        suffix = image_extension(body[:12])
        label = re.sub(r"[^A-Za-z0-9]+", "_", source["label"]).strip("_")[:40] or "competitor"
        digest = hashlib.sha256(source["image_url"].encode()).hexdigest()[:8]
        path = directory / f"competitor_{label}_{digest}{suffix}"
        path.write_bytes(body)
        paths.append(str(path))
    return paths


def candidate_records(all_records, reference, model):
    ref = norm(reference)
    ref_tokens = {norm(x) for x in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{4,}", reference) if any(ch.isdigit() for ch in x)}
    ref_tokens |= set(re.findall(r"\d{5,}", reference))
    ref_tokens.add(ref)
    ref_tokens.discard("")
    model_terms = [norm(part) for part in re.split(r"\s+", model) if len(norm(part)) >= 3]
    candidates = []
    for item in all_records:
        f = item["fields"]
        stored_ref = plain(f.get("外部参考编号"))
        ref_values = {norm(x) for x in re.split(r"[,;\n/]", stored_ref)}
        ref_values |= {norm(x) for x in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{4,}", stored_ref) if any(ch.isdigit() for ch in x)}
        ref_values |= set(re.findall(r"\d{5,}", stored_ref))
        exact_ref = bool(ref_tokens & ref_values)
        searchable = norm(" ".join(plain(f.get(name)) for name in ["车型", "产品描述", "品牌", "厂家编号"]))
        model_hit = bool(model_terms and all(term in searchable for term in model_terms))
        if exact_ref or model_hit:
            candidates.append({"record_id": item["record_id"], "exact_reference": exact_ref,
                               "model_hit": model_hit, "fields": f})
    return candidates


def inspect(reference, model, category, include_sources=True):
    if not any(x.strip() for x in [reference, model, category]):
        raise WorkflowError("Supply a reference, model, or category for internal search")
    require_fields(BASE_URL, TRADE_TABLE, LOOKUP_FIELDS)
    english_category = CATEGORY_ALIASES.get(category, category)
    searches = product_search([*reference_queries(reference), model, f"{model} {english_category}".strip()])
    existing = records(BASE_URL, TRADE_TABLE, LOOKUP_FIELDS)
    result = {"product_queries": searches,
              "development_candidates": candidate_records(existing, reference, model),
              "development_records_checked": len(existing)}
    if include_sources:
        require_fields(PEERS_URL, PEER_TABLE, ["显示名称", "官网", "产品检索入口", "对象类型"])
        peers = records(PEERS_URL, PEER_TABLE, ["显示名称", "官网", "产品检索入口", "对象类型"])
        result["peer_sources"] = [{"name": plain(x["fields"].get("显示名称")),
                                   "website": plain(x["fields"].get("官网")),
                                   "search_entry": plain(x["fields"].get("产品检索入口")),
                                   "type": plain(x["fields"].get("对象类型"))} for x in peers]
    return result


def validate_draft(draft):
    if draft.get("decision") not in {"new", "update"}:
        raise WorkflowError("decision must be new or update")
    if draft.get("decision") == "update" and not re.fullmatch(r"rec[A-Za-z0-9]+", str(draft.get("record_id", ""))):
        raise WorkflowError("update requires a valid record_id")
    supplied = draft.get("fields")
    if not isinstance(supplied, dict):
        raise WorkflowError("fields must be an object")
    proposed = dict(supplied)
    if set(proposed) & FORBIDDEN_FIELDS or set(proposed) - DRAFT_FIELDS:
        raise WorkflowError("Draft contains forbidden or unknown fields")
    for required in ["品牌", "车型", "类目", "产品描述", "采购说明", "核对来源链接"]:
        if not isinstance(proposed.get(required), str) or not proposed[required].strip():
            raise WorkflowError(f"Missing field: {required}")
    if re.search(r"客户指定|客户提供|页面所示|网页所示|需求来源", proposed["产品描述"], re.I):
        raise WorkflowError("产品描述 must be a product title; move request and page context to 采购说明")
    for optional in ["外部参考编号"]:
        if optional in proposed and not isinstance(proposed[optional], str):
            raise WorkflowError(f"Invalid field: {optional}")
    urls = [x.strip() for x in proposed["核对来源链接"].splitlines() if x.strip()]
    if not urls or any(urlparse(url).scheme != "https" or not urlparse(url).netloc for url in urls):
        raise WorkflowError("核对来源链接 must contain HTTPS URLs, one per line")
    if not isinstance(draft.get("unresolved"), list):
        raise WorkflowError("unresolved must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in draft["unresolved"]):
        raise WorkflowError("unresolved entries must be nonempty text")
    images = draft.get("image_paths")
    if not isinstance(images, list):
        raise WorkflowError("image_paths must be a list of local customer product images")
    for image in images:
        if not isinstance(image, str) or not Path(image).is_file():
            raise WorkflowError("Every image_path must be an existing local file")
        if Path(image).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            raise WorkflowError("image_paths must be JPG, PNG, WebP, or GIF images")
        if not is_image(image):
            raise WorkflowError("image_paths contains a file without a supported image signature")
    sources = draft.get("source_images")
    if not isinstance(sources, list) or len(sources) > 20:
        raise WorkflowError("source_images must be a list of at most 20 competitor product images")
    if not images and not sources:
        raise WorkflowError("At least one customer or competitor product image is required")
    if not sources and not str(draft.get("source_image_gap_reason", "")).strip():
        raise WorkflowError("Add competitor product images or explain why none are available")
    if len(images) + len(sources) > 50:
        raise WorkflowError("At most 50 product images may be uploaded")
    page_urls = set(urls)
    source_urls = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"label", "page_url", "image_url"}:
            raise WorkflowError("Each source image needs label, page_url, and image_url")
        if not all(isinstance(source[key], str) and source[key].strip() for key in source):
            raise WorkflowError("Source image fields must be nonempty text")
        if source["page_url"] not in page_urls:
            raise WorkflowError("Every source image page_url must appear in 核对来源链接")
        if urlparse(source["image_url"]).scheme != "https":
            raise WorkflowError("Source image_url must use HTTPS")
        if source["image_url"] in source_urls:
            raise WorkflowError("Duplicate source image_url")
        source_urls.add(source["image_url"])
    if draft["unresolved"]:
        proposed["采购说明"] += "；待人工核对：" + "；".join(draft["unresolved"])
    if not isinstance(draft.get("reviewed_product_codes"), list):
        raise WorkflowError("reviewed_product_codes must be a list")
    if not isinstance(draft.get("reviewed_development_record_ids"), list):
        raise WorkflowError("reviewed_development_record_ids must be a list")
    if draft["decision"] == "new" and draft["reviewed_product_codes"] and not str(draft.get("own_product_difference", "")).strip():
        raise WorkflowError("Explain how this differs from existing product candidates")
    if draft["decision"] == "new" and draft["reviewed_development_record_ids"] and not str(draft.get("development_record_difference", "")).strip():
        raise WorkflowError("Explain how this differs from existing development records")
    if draft["decision"] == "new":
        proposed["项目阶段"] = ["信息收集"]
        proposed["开发类型"] = ["贸易型"]
    return proposed


def product_codes(value):
    found = set()
    if isinstance(value, dict):
        code = value.get("product_code")
        if isinstance(code, str) and code:
            found.add(code)
        for child in value.values():
            found.update(product_codes(child))
    elif isinstance(value, list):
        for child in value:
            found.update(product_codes(child))
    return found


def record_id_from_result(data):
    record = data.get("record") or {}
    ids = record.get("record_id_list") or data.get("record_id_list") or []
    return data.get("record_id") or (ids[0] if len(ids) == 1 else None)


def readback(record_id, names):
    args = ["+record-get", "--base-token", token_from_url(BASE_URL), "--table-id", TRADE_TABLE,
            "--record-id", record_id, "--format", "json"]
    for name in names:
        args.extend(["--field-id", name])
    data = lark(*args)["data"]
    if data.get("record_id_list") != [record_id] or len(data.get("data", [])) != 1:
        raise WorkflowError("Record readback did not return exactly the written record")
    return dict(zip(data["fields"], data["data"][0]))


def apply(path):
    draft = json.loads(Path(path).read_text(encoding="utf-8"))
    proposed = validate_draft(draft)
    field_map = require_fields(BASE_URL, TRADE_TABLE, [*WRITE_FIELDS, "产品图片"])
    if field_map.get("产品图片", {}).get("type") != "attachment":
        raise WorkflowError("产品图片 attachment field is missing or changed")
    check_category_option(field_map, proposed["类目"])
    fresh = inspect(proposed.get("外部参考编号", ""), proposed["车型"], proposed["类目"], include_sources=False)
    candidates = fresh["development_candidates"]
    current_development_ids = sorted(x["record_id"] for x in candidates)
    reviewed_development_ids = sorted(set(str(x) for x in draft["reviewed_development_record_ids"]))
    if current_development_ids != reviewed_development_ids:
        raise WorkflowError("Development candidates changed; inspect and review again")
    if draft["decision"] == "new" and any(x["exact_reference"] for x in candidates):
        raise WorkflowError("Exact external reference exists in development table; review before creating")
    if draft["decision"] == "update":
        ids = {x["record_id"] for x in candidates}
        if draft["record_id"] not in ids:
            raise WorkflowError("Update record no longer matches the reviewed reference or model")
        if any(x["exact_reference"] and x["record_id"] != draft["record_id"] for x in candidates):
            raise WorkflowError("Reference is already present in another development record")
    # Product API search results are intentionally left for human review. The draft must
    # name every candidate code the reviewer saw; a changing result set stops the write.
    current_codes = sorted(product_codes(fresh["product_queries"]))
    reviewed_codes = sorted(set(str(x) for x in draft["reviewed_product_codes"]))
    if current_codes != reviewed_codes:
        raise WorkflowError("Product candidates changed; inspect and review again")
    with tempfile.TemporaryDirectory(prefix="carair-product-images-") as temp:
        source_paths = download_source_images(draft["source_images"], Path(temp))
        upload_paths = [*draft["image_paths"], *source_paths]
        args = ["+record-upsert", "--base-token", token_from_url(BASE_URL), "--table-id", TRADE_TABLE,
                "--json", json.dumps(proposed, ensure_ascii=False)]
        if draft["decision"] == "update":
            args += ["--record-id", draft["record_id"]]
        data = (lark(*args).get("data") or {})
        record_id = record_id_from_result(data) or draft.get("record_id")
        if not record_id:
            raise WorkflowError("Record write may have succeeded, but no record ID was returned; inspect the table before retrying")
        try:
            upload = ["+record-upload-attachment", "--base-token", token_from_url(BASE_URL),
                      "--table-id", TRADE_TABLE, "--record-id", record_id, "--field-id", "产品图片"]
            for image in upload_paths:
                upload.extend(["--file", image])
            lark(*upload)
            actual = readback(record_id, [*proposed.keys(), "产品图片", "记录ID"])
            mismatched = [name for name, value in proposed.items() if actual.get(name) != value]
            if mismatched or len(actual.get("产品图片") or []) < len(upload_paths):
                raise WorkflowError("Readback mismatch: " + ", ".join(mismatched or ["产品图片"]))
        except WorkflowError as exc:
            raise WorkflowError(f"Record {record_id} was written, but image upload/readback is incomplete: {exc}. Inspect this record before retrying") from exc
        emit({"ok": True, "decision": draft["decision"], "record_id": record_id,
              "record_number": actual.get("记录ID"), "record_url": f"{BASE_URL}?table={TRADE_TABLE}&record={record_id}",
              "image_count": len(actual["产品图片"]), "customer_image_count": len(draft["image_paths"]),
              "competitor_images": [{"label": source["label"], "page_url": source["page_url"]}
                                    for source in draft["source_images"]],
              "source_image_gap_reason": draft.get("source_image_gap_reason"),
              "human_review": "请在多维表格核对字段、客户图片、同行图片及适配；未核实事项见采购说明/车款信息说明。"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("inspect", help="search own products, development records and peer sources")
    check.add_argument("--reference", default="")
    check.add_argument("--model", default="")
    check.add_argument("--category", default="")
    write = sub.add_parser("apply", help="recheck, write one record with images, then return it for human review")
    write.add_argument("draft")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            emit({"ok": True, "data": inspect(args.reference, args.model, args.category)})
        else:
            apply(args.draft)
    except (WorkflowError, OSError, ValueError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
