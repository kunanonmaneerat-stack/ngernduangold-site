"""diag_keys.py — ตรวจว่า GLM/Qwen auth ผ่านไหม (พิมพ์แค่สถานะ ไม่โชว์คีย์)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm, urllib.request, urllib.error

for label, url, model, env in free_llm.POOL:
    key = free_llm._get_key(env)
    print(f"{label:16} env={env:13} keylen={len(key)}")
    if not key:
        print("   (no key)"); continue
    try:
        txt = free_llm._call(url, model, key, "ตอบคำว่า OK", "", 20, 0.2)
        print("   OK ->", (txt or "")[:60])
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read()[:240].decode("utf-8", "ignore")
        except Exception: pass
        print(f"   HTTP {e.code} -> {body}")
    except Exception as e:
        print("   ERR", str(e)[:160])
