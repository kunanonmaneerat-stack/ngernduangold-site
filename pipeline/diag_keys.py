"""Diagnose configured legacy LLM providers without exposing credentials.

The shared network-generation sink is currently disabled. A configured key
that cannot be verified is BLOCKED/FAILED and must produce a non-zero exit;
missing optional keys remain explicit SKIPs.
"""
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm


def diagnose(pool=None, get_key=None, call=None):
    selected_pool = free_llm.POOL if pool is None else pool
    key_reader = free_llm._get_key if get_key is None else get_key
    provider_call = free_llm._call if call is None else call
    configured = 0
    verified = 0
    failed = 0
    for label, url, model, env in selected_pool:
        key = key_reader(env)
        if not key:
            print("%-16s SKIP (credential not configured)" % label)
            continue
        configured += 1
        try:
            result = provider_call(url, model, key, "ตอบคำว่า OK", "", 20, 0.2)
            if not isinstance(result, str) or not result.strip():
                raise RuntimeError("empty provider response")
            verified += 1
            print("%-16s VERIFIED" % label)
        except urllib.error.HTTPError as exc:
            failed += 1
            print("%-16s FAILED (HTTP %s)" % (label, exc.code))
        except free_llm.NetworkGenerationBlocked:
            failed += 1
            print("%-16s BLOCKED (network generation policy)" % label)
        except Exception as exc:
            failed += 1
            print("%-16s FAILED (%s)" % (label, type(exc).__name__))
    return {"configured": configured, "verified": verified, "failed": failed}


def main():
    result = diagnose()
    if result["configured"] == 0:
        print("DIAGNOSTIC UNAVAILABLE: no provider credentials are configured")
        return 2
    if result["failed"] or result["verified"] != result["configured"]:
        print("DIAGNOSTIC FAILED: %d/%d configured providers verified" %
              (result["verified"], result["configured"]))
        return 1
    print("DIAGNOSTIC PASS: %d/%d configured providers verified" %
          (result["verified"], result["configured"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
