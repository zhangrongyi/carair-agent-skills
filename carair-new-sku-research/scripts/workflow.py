#!/usr/bin/env python3
"""Research an automotive part and write one company development project for employee review."""
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

import development_api

CATEGORY_ALIASES={"冷凝器":"CONDENSER","蒸发器":"COOLING COIL","鼓风机":"BLOWER MOTOR","风扇马达":"FAN MOTOR",
                  "压缩机":"COMPRESSOR","膨胀阀":"EXPANSION VALVE","电磁离合器":"MAGNET CLUTCH"}
FIELDS={"外部参考编号":"external_refs","品牌":"make","车型":"model","年份":"year_note","类目":"category",
        "产品描述":"title","同行价格":"peer_price_note","车款信息说明":"fitment_note","采购说明":"demand_note",
        "核对来源链接":"source_links"}
FORBIDDEN={"供应商","厂家编号","成本","计划售价","CXA编号","订单号","下单时间","项目阶段","开发类型"}

class WorkflowError(Exception): pass

def emit(data): print(json.dumps(data,ensure_ascii=False,indent=2))

def run_json(argv):
    try: p=subprocess.run(argv,capture_output=True,text=True,timeout=45,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc: raise WorkflowError(f"Command unavailable or timed out: {argv[0]}") from exc
    try: payload=json.loads(p.stdout)
    except ValueError as exc: raise WorkflowError(f"Non-JSON response from {argv[0]}") from exc
    if p.returncode or not payload.get("ok"):
        error=payload.get("error")
        raise WorkflowError(f"{argv[0]} failed: {error.get('message') if isinstance(error,dict) else error}")
    return payload

def product_client():
    override=os.environ.get("CARAIR_PRODUCT_CLIENT")
    path=Path(override).expanduser() if override else Path(os.environ.get("CODEX_HOME",str(Path.home()/".codex")))/"skills"/"query-carair-products"/"scripts"/"query_products.py"
    if not path.is_file(): raise WorkflowError("Install query-carair-products Skill or set CARAIR_PRODUCT_CLIENT")
    return path

def reference_queries(reference):
    parts=[x.strip() for x in re.split(r"[;,\n]",reference) if x.strip()]
    result=[]
    for part in parts:
        if re.search(r"\d",part):
            result.append(part)
            result.extend(x for x in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{3,}",part) if re.search(r"\d",x))
    return list(dict.fromkeys(result or parts))

def product_search(queries):
    path=product_client();prefix=["py","-3"] if sys.platform=="win32" else [sys.executable]
    result=[]
    for query in dict.fromkeys(q.strip() for q in queries if len(q.strip())>=2):
        data=run_json([*prefix,str(path),"search",query,"--limit","20"])
        total=int((data.get("data") or {}).get("total",0))
        if total>200:raise WorkflowError("Internal product candidates exceed 200; narrow the reference or model search")
        for offset in range(20,total,20):
            page=run_json([*prefix,str(path),"search",query,"--limit","20","--offset",str(offset)])
            data["data"]["items"].extend((page.get("data") or {}).get("items",[]))
        if len((data.get("data") or {}).get("items",[]))<total:raise WorkflowError("Internal product search returned incomplete results")
        result.append({"query":query,"data":data.get("data"),"connection":data.get("connection")})
    if not result: raise WorkflowError("At least one product search query is required")
    return result

def inspect(reference,model,category):
    english=CATEGORY_ALIASES.get(category,category)
    own=product_search([*reference_queries(reference),model,f"{model} {english}".strip()])
    remote=development_api.call("GET","inspect",query={"reference":reference,"model":model,"category":english})
    return {**remote,"product_queries":own}

def is_image(path):
    with Path(path).open("rb") as stream: header=stream.read(12)
    return header.startswith(b"\xff\xd8\xff") or header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith((b"GIF87a",b"GIF89a")) or header.startswith(b"RIFF") and header[8:12]==b"WEBP"

def image_extension(header):
    if header.startswith(b"\xff\xd8\xff"):return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):return ".png"
    if header.startswith((b"GIF87a",b"GIF89a")):return ".gif"
    if header.startswith(b"RIFF") and header[8:12]==b"WEBP":return ".webp"
    raise WorkflowError("Source URL did not return a supported product image")

def public_https_url(url):
    p=urlparse(url)
    if p.scheme!="https" or not p.hostname or p.username or p.password or p.port not in {None,443}:raise WorkflowError("Source image must be public HTTPS")
    host=p.hostname.lower()
    if host in {"localhost","localhost.localdomain"} or host.endswith((".local",".internal")):raise WorkflowError("Source image host is private")
    try: addresses={ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
    except (OSError,ValueError) as exc: raise WorkflowError("Could not resolve source image host") from exc
    if not addresses or any(not x.is_global for x in addresses):raise WorkflowError("Source image resolved to a private address")

class PublicImageRedirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_https_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download_source_images(sources,directory):
    opener=build_opener(PublicImageRedirects());result=[]
    for source in sources:
        public_https_url(source["image_url"])
        req=Request(source["image_url"],headers={"User-Agent":"Mozilla/5.0 (compatible; CarAirResearch/3.0)","Referer":source["page_url"],"Accept":"image/jpeg,image/png,image/webp,image/gif"})
        try:
            with opener.open(req,timeout=20) as response:
                if not response.headers.get_content_type().startswith("image/"):raise WorkflowError("Source URL returned non-image content")
                body=response.read(15*1024*1024+1)
        except WorkflowError:raise
        except (OSError,TimeoutError) as exc:raise WorkflowError("Could not download source product image") from exc
        if len(body)>15*1024*1024:raise WorkflowError("Source product image exceeds 15 MB")
        suffix=image_extension(body[:12]);label=re.sub(r"[^A-Za-z0-9]+","_",source["label"]).strip("_")[:40] or "competitor"
        path=directory/f"competitor_{label}_{hashlib.sha256(source['image_url'].encode()).hexdigest()[:8]}{suffix}"
        path.write_bytes(body);result.append((path,source))
    return result

def validate_draft(draft):
    if draft.get("decision") not in {"new","update"}:raise WorkflowError("decision must be new or update")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,100}",str(draft.get("request_key",""))):raise WorkflowError("Add a stable request_key (UUID) to the saved draft")
    if draft["decision"]=="update" and (not isinstance(draft.get("record_id"),int) or not isinstance(draft.get("record_version"),int)):
        raise WorkflowError("update requires numeric record_id and record_version from inspect")
    fields=draft.get("fields")
    if not isinstance(fields,dict) or set(fields)&FORBIDDEN or set(fields)-set(FIELDS):raise WorkflowError("Draft has forbidden or unknown fields")
    for name in ["品牌","车型","类目","产品描述","采购说明","核对来源链接"]:
        if not isinstance(fields.get(name),str) or not fields[name].strip():raise WorkflowError(f"Missing field: {name}")
    if re.search(r"客户指定|客户提供|页面所示|网页所示|需求来源",fields["产品描述"],re.I):raise WorkflowError("产品描述 must be a concise product title")
    urls=[x.strip() for x in fields["核对来源链接"].splitlines() if x.strip()]
    if not urls or any(urlparse(x).scheme!="https" or not urlparse(x).netloc for x in urls):raise WorkflowError("核对来源链接 must list HTTPS URLs")
    for key in ["unresolved","image_paths","source_images","reviewed_product_codes","reviewed_development_record_ids"]:
        if not isinstance(draft.get(key),list):raise WorkflowError(f"{key} must be a list")
    for image in draft["image_paths"]:
        path=Path(image)
        if not path.is_file() or path.suffix.lower() not in {".jpg",".jpeg",".png",".webp",".gif"} or not is_image(path):raise WorkflowError("Customer image is missing or invalid")
    sources=draft["source_images"]
    if len(sources)>20 or len(sources)+len(draft["image_paths"])>50:raise WorkflowError("Too many images")
    if not sources and not str(draft.get("source_image_gap_reason","")).strip():raise WorkflowError("Explain why no comparable competitor image is available")
    if not sources and not draft["image_paths"]:raise WorkflowError("At least one product image is required")
    for source in sources:
        if not isinstance(source,dict) or set(source)!={"label","page_url","image_url"} or source["page_url"] not in urls or not source["label"].strip() or urlparse(source["image_url"]).scheme!="https":
            raise WorkflowError("Each source image needs label, cited page_url, and direct HTTPS image_url")
    if fields.get("同行价格") and (not draft.get("peer_currency") or not draft.get("peer_price_level")):raise WorkflowError("同行价格 requires peer_currency and peer_price_level")
    return urls

def apply(path):
    draft=json.loads(Path(path).read_text(encoding="utf-8"));urls=validate_draft(draft)
    previous=development_api.call("GET","result",query={"request_key":draft["request_key"]})
    if previous:
        emit({"ok":True,"decision":draft["decision"],"record_id":int(previous["project_id"]),"replayed":True,
              "record_url":development_api.base_url()+"/admin/development",
              "human_review":"请在公司后台核对字段、图片与适配；待核实事项不得当作确认适配。"})
        return
    f=draft["fields"];fresh=inspect(f.get("外部参考编号",""),f["车型"],f["类目"])
    current_codes=sorted(fresh.get("reviewed_product_codes",[]));reviewed_codes=sorted(draft["reviewed_product_codes"])
    current_ids=sorted(int(x["id"]) for x in fresh.get("development_candidates",[]));reviewed_ids=sorted(int(x) for x in draft["reviewed_development_record_ids"])
    if current_codes!=reviewed_codes or current_ids!=reviewed_ids:raise WorkflowError("Internal candidates changed; inspect and review again")
    if draft["decision"]=="new" and any(x.get("exact_reference") for x in fresh.get("development_candidates",[])):raise WorkflowError("Exact external reference exists; update that project")
    if draft["decision"]=="new" and current_ids and not draft.get("development_record_difference"):raise WorkflowError("Explain difference from development candidates")
    if draft["decision"]=="new" and current_codes and not draft.get("own_product_difference"):raise WorkflowError("Explain difference from existing products")
    if draft["decision"]=="update" and draft["record_id"] not in current_ids:raise WorkflowError("Update target is no longer a candidate")
    payload={FIELDS[k]:v for k,v in f.items()};payload["source_links"]=urls;payload["unresolved"]=draft["unresolved"]
    payload.update({"decision":draft["decision"],"request_key":draft["request_key"],"reviewed_product_codes":reviewed_codes,
                    "reviewed_development_record_ids":reviewed_ids,"own_product_difference":draft.get("own_product_difference",""),
                    "development_record_difference":draft.get("development_record_difference",""),
                    "source_image_gap_reason":draft.get("source_image_gap_reason",""),"peer_currency":draft.get("peer_currency",""),
                    "peer_price_level":draft.get("peer_price_level","")})
    if draft["decision"]=="update":payload.update({"record_id":draft["record_id"],"record_version":draft["record_version"]})
    with tempfile.TemporaryDirectory(prefix="carair-product-images-") as temp:
        competitor=download_source_images(draft["source_images"],Path(temp));uploads=[(Path(p),{}) for p in draft["image_paths"]]+competitor
        tokens=[]
        for image,source in uploads:
            meta={"source_label":source.get("label","customer"),"page_url":source.get("page_url",""),"image_url":source.get("image_url","")}
            uploaded=development_api.call("POST","uploads",file=image,meta=meta);tokens.append(uploaded["upload_token"])
        payload["upload_tokens"]=tokens
        try: result=development_api.call("POST","drafts",payload=payload)
        except RuntimeError:
            result=development_api.call("GET","result",query={"request_key":draft["request_key"]})
            if not result:raise
            result={"id":int(result["project_id"]),"replayed":True}
    emit({"ok":True,"decision":draft["decision"],"record_id":result["id"],
          "record_url":development_api.base_url()+"/admin/development","image_count":len(uploads),
          "competitor_images":[{"label":s["label"],"page_url":s["page_url"]} for s in draft["source_images"]],
          "human_review":"请在公司后台核对字段、图片与适配；待核实事项不得当作确认适配。"})

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="command",required=True)
    check=sub.add_parser("inspect");check.add_argument("--reference",default="");check.add_argument("--model",default="");check.add_argument("--category",default="")
    sub.add_parser("configure-credential");write=sub.add_parser("apply");write.add_argument("draft")
    args=parser.parse_args()
    try:
        if args.command=="inspect":emit({"ok":True,"data":inspect(args.reference,args.model,args.category)})
        elif args.command=="configure-credential":development_api.configure_credential();emit({"ok":True,"credential_store":development_api.SERVICE})
        else:apply(args.draft)
    except (WorkflowError,RuntimeError,OSError,ValueError,KeyError) as exc:emit({"ok":False,"error":str(exc)});return 1
    return 0

if __name__=="__main__":raise SystemExit(main())
