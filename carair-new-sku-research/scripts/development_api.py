"""Scoped employee API client for development drafts. Never uses the product read-only token."""
from __future__ import annotations
import ctypes
import getpass
import json
import os
import platform
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SERVICE = "com.baijia.codex-development-api"
ACCOUNT = "production"
TARGET = f"{SERVICE}:{ACCOUNT}"

def _windows_types():
    from ctypes import wintypes
    class Credential(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
    return wintypes, Credential

def _windows_token() -> str:
    wintypes, Credential = _windows_types()
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    ptr = ctypes.POINTER(Credential)()
    read = api.CredReadW; read.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]; read.restype=wintypes.BOOL
    if not read(TARGET,1,0,ctypes.byref(ptr)): return ""
    try: return ctypes.string_at(ptr.contents.CredentialBlob,ptr.contents.CredentialBlobSize).decode("utf-16-le").strip()
    finally: api.CredFree(ptr)

def _save_windows(token: str) -> None:
    wintypes, Credential = _windows_types()
    raw=token.encode("utf-16-le"); blob=ctypes.create_string_buffer(raw); cred=Credential()
    cred.Type=1;cred.TargetName=TARGET;cred.Comment="Baijia Codex Development API";cred.CredentialBlobSize=len(raw)
    cred.CredentialBlob=ctypes.cast(blob,ctypes.POINTER(ctypes.c_ubyte));cred.Persist=2;cred.UserName=ACCOUNT
    api=ctypes.WinDLL("Advapi32.dll",use_last_error=True)
    write=api.CredWriteW;write.argtypes=[ctypes.POINTER(Credential),wintypes.DWORD];write.restype=wintypes.BOOL
    if not write(ctypes.byref(cred),0): raise RuntimeError("Could not save Windows credential")

def token() -> str:
    value=os.environ.get("CAR_AIR_DEVELOPMENT_API_TOKEN","").strip()
    if value: return value
    if platform.system()=="Darwin":
        p=subprocess.run(["/usr/bin/security","find-generic-password","-a",ACCOUNT,"-s",SERVICE,"-w"],capture_output=True,text=True,timeout=5)
        if p.returncode==0 and p.stdout.strip(): return p.stdout.strip()
    elif platform.system()=="Windows":
        value=_windows_token()
        if value: return value
    raise RuntimeError("Development API credential is missing; configure it locally, never paste it into chat")

def configure_credential() -> None:
    if platform.system()=="Darwin":
        print("Enter the employee development token at the macOS Keychain prompt.",file=sys.stderr)
        p=subprocess.run(["/usr/bin/security","add-generic-password","-U","-a",ACCOUNT,"-s",SERVICE,"-l","Baijia Codex Development API","-w"])
        if p.returncode: raise RuntimeError("Keychain did not save the credential")
    elif platform.system()=="Windows":
        value=getpass.getpass("Employee development API token: ").strip()
        if not value: raise RuntimeError("Empty credential")
        _save_windows(value)
    else: raise RuntimeError("Use CAR_AIR_DEVELOPMENT_API_TOKEN on this platform")

def base_url() -> str:
    value=os.environ.get("CAR_AIR_DEVELOPMENT_API_BASE_URL",os.environ.get("CAR_AIR_API_BASE_URL","https://www.baijia.com.my")).strip().rstrip("/")
    p=urlsplit(value)
    if p.username or p.password or not p.hostname or p.path not in {"","/"} or (p.scheme!="https" and not(p.scheme=="http" and p.hostname in {"localhost","127.0.0.1","::1"})):
        raise RuntimeError("Development API base must be HTTPS origin or localhost HTTP")
    return value

class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        old,new=urlsplit(req.full_url),urlsplit(newurl)
        if (old.scheme,old.netloc)!=(new.scheme,new.netloc): raise HTTPError(req.full_url,502,"Cross-origin redirect refused",headers,fp)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def call(method: str,path: str,*,query: dict|None=None,payload: dict|None=None,file: Path|None=None,meta: dict|None=None) -> dict:
    url=base_url()+"/api/codex/development/"+path
    if query: url+="?"+urlencode(query)
    headers={"Accept":"application/json","Authorization":"Bearer "+token(),"User-Agent":"carair-new-sku-research/3.0","X-Request-ID":"skill_"+uuid.uuid4().hex[:16]}
    body=None
    if file is not None:
        boundary="cad"+uuid.uuid4().hex
        chunks=[]
        for key,value in (meta or {}).items():
            chunks.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n").encode())
        chunks += [(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode(),file.read_bytes(),f"\r\n--{boundary}--\r\n".encode()]
        body=b"".join(chunks);headers["Content-Type"]="multipart/form-data; boundary="+boundary
    elif payload is not None:
        body=json.dumps(payload,ensure_ascii=False).encode();headers["Content-Type"]="application/json"
    request=Request(url,data=body,headers=headers,method=method)
    try:
        with build_opener(SameOriginRedirect()).open(request,timeout=45) as response: raw=response.read().decode();status=response.status
    except HTTPError as exc: raw=exc.read().decode(errors="replace");status=exc.code
    except (URLError,socket.timeout,TimeoutError) as exc: raise RuntimeError("Development API could not be reached") from exc
    try: result=json.loads(raw)
    except ValueError as exc: raise RuntimeError(f"Development API returned non-JSON HTTP {status}") from exc
    if status!=200 or result.get("code")!=1: raise RuntimeError(str(result.get("msg") or f"Development API HTTP {status}"))
    return result.get("data") or {}
