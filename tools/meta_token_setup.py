#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provision the Meta credentials used by this repository's GitHub Actions.

Credentials are kept in process memory only.  This program intentionally never
prints request URLs, API response bodies, command output, or credential values.
"""

import getpass
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
import webbrowser


GRAPH_API = "https://graph.facebook.com/v22.0"
REPOSITORY = "kunanonmaneerat-stack/ngernduangold-site"
FB_PAGE_ID = "583765282304956"
DEFAULT_IG_USER_ID = "17841439942473239"
GITHUB_SECRETS_URL = (
    "https://github.com/kunanonmaneerat-stack/ngernduangold-site/"
    "settings/secrets/actions"
)
SECRET_NAMES = (
    "IG_ACCESS_TOKEN",
    "IG_USER_ID",
    "FB_PAGE_ID",
    "FB_PAGE_TOKEN",
    "FB_APP_ID",
    "FB_APP_SECRET",
)


class SetupError(Exception):
    """A user-facing error that does not include sensitive data."""


class ApiError(SetupError):
    def __init__(self, endpoint, status=None, graph_code=None):
        detail = "เชื่อมต่อ Graph API ไม่สำเร็จ"
        if status is not None:
            detail += " (HTTP %s)" % status
        if graph_code is not None:
            detail += " (Graph code %s)" % graph_code
        detail += " ที่ %s" % endpoint
        super().__init__(detail)


def configure_utf8_output():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def safe_text(value, limit=160):
    """Return display-safe, single-line public metadata from an API response."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def graph_error_code(raw_body):
    """Extract only numeric error codes; never surface response messages/bodies."""
    try:
        payload = json.loads(raw_body.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error", {})
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, int) else None


def graph_get(path, params):
    """Make a Graph API GET request without ever logging sensitive query data."""
    endpoint = path.split("?", 1)[0]
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        GRAPH_API + path + "?" + query,
        headers={"User-Agent": "ngernduangold-meta-token-setup/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Meta's response body can contain request-specific context; retain only
        # the numeric Graph code for a safe troubleshooting signal.
        raise ApiError(endpoint, exc.code, graph_error_code(exc.read()))
    except (urllib.error.URLError, OSError, ValueError):
        raise ApiError(endpoint)
    except json.JSONDecodeError:
        raise SetupError("Graph API ตอบกลับในรูปแบบที่ไม่คาดคิดที่ %s" % endpoint)


def require_string(data, key, context):
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise SetupError("Graph API ไม่ส่ง %s สำหรับ%s" % (key, context))
    return value.strip()


def hidden_prompt(label):
    """Read a secret without accepting getpass's visible-input fallback."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass(label)
    except getpass.GetPassWarning:
        raise SetupError("เทอร์มินัลนี้ซ่อนข้อมูลไม่ได้; โปรดรันใน Windows Terminal หรือ PowerShell ปกติ")
    except (EOFError, KeyboardInterrupt):
        raise SetupError("ยกเลิกก่อนรับข้อมูลลับครบถ้วน")
    if not value.strip():
        raise SetupError("ยังไม่ได้ใส่ข้อมูลที่จำเป็น")
    return value.strip()


def public_prompt(label):
    try:
        value = input(label)
    except (EOFError, KeyboardInterrupt):
        raise SetupError("ยกเลิกก่อนรับข้อมูลครบถ้วน")
    if not value.strip():
        raise SetupError("ยังไม่ได้ใส่ข้อมูลที่จำเป็น")
    return value.strip()


def collect_inputs():
    print("Meta Token Setup — ตั้งค่า secrets ให้ GitHub Actions")
    print("สคริปต์จะขอวางข้อมูล 3 รายการ และจะไม่แสดงค่าเหล่านั้นกลับมา")
    print("ข้อมูลลับจะอยู่ในหน่วยความจำชั่วคราวเท่านั้น แล้วส่งตรงไปยัง Meta/GitHub")
    print()
    print("เตรียม short-lived user token จาก Graph API Explorer โดยเลือกสิทธิ์:")
    print("instagram_content_publish, instagram_basic, pages_show_list,")
    print("pages_read_engagement, pages_manage_posts")
    print()
    short_token = hidden_prompt("วาง SHORT_LIVED_USER_TOKEN (ซ่อนข้อความ): ")
    app_id = public_prompt("วาง FB_APP_ID: ")
    app_secret = hidden_prompt("วาง FB_APP_SECRET (ซ่อนข้อความ): ")
    return short_token, app_id, app_secret


def find_page(accounts):
    for page in accounts:
        if isinstance(page, dict) and str(page.get("id", "")) == FB_PAGE_ID:
            token = page.get("access_token")
            if not isinstance(token, str) or not token.strip():
                raise SetupError("พบ FB_PAGE_ID แล้ว แต่ Meta ไม่ส่ง page access token")
            return page, token.strip()
    return None, None


def validate_and_prepare(short_token, app_id, app_secret):
    print("[1/5] ตรวจสอบ SHORT_LIVED_USER_TOKEN ...")
    me = graph_get("/me", {"fields": "id,name", "access_token": short_token})
    print("      PASS: ผู้ใช้ %s" % safe_text(require_string(me, "name", "การตรวจสอบ token")))

    print("[2/5] แลกเป็น long-lived user token ...")
    exchanged = graph_get(
        "/oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
    )
    long_token = require_string(exchanged, "access_token", "การแลก long-lived token")
    print("      PASS: ได้ long-lived user token")

    print("[3/5] ค้นหา Facebook Page ที่กำหนด ...")
    pages_result = graph_get(
        "/me/accounts",
        {"fields": "id,name,access_token", "access_token": long_token},
    )
    accounts = pages_result.get("data") if isinstance(pages_result, dict) else None
    if not isinstance(accounts, list):
        raise SetupError("Graph API ไม่ส่งรายการ Facebook Pages")
    page, page_token = find_page(accounts)
    if page is None:
        print("      FAIL: ไม่พบ FB_PAGE_ID ที่กำหนด")
        if accounts:
            print("      Pages ที่ token นี้เข้าถึงได้:")
            for item in accounts:
                if isinstance(item, dict):
                    print("      - %s (%s)" % (safe_text(item.get("name")), safe_text(item.get("id"))))
        else:
            print("      ไม่พบ Page ใดจาก token นี้")
        raise SetupError("โปรดตรวจสอบว่า token มี pages_show_list และผู้ใช้มีสิทธิ์เข้าถึง Page นี้ แล้วรันใหม่")
    print("      PASS: พบ Page %s (%s)" % (safe_text(page.get("name")), FB_PAGE_ID))

    print("[4/5] ตรวจสอบการเชื่อม Instagram Business Account ...")
    page_detail = graph_get(
        "/%s" % FB_PAGE_ID,
        {"fields": "instagram_business_account", "access_token": long_token},
    )
    ig_account = page_detail.get("instagram_business_account") if isinstance(page_detail, dict) else None
    ig_user_id = ig_account.get("id") if isinstance(ig_account, dict) else None
    if not isinstance(ig_user_id, (str, int)) or not str(ig_user_id).strip():
        raise SetupError("Page นี้ยังไม่มี Instagram Business Account ที่เชื่อมไว้; โปรดเชื่อมบัญชีก่อน แล้วรันใหม่")
    ig_user_id = str(ig_user_id).strip()
    if ig_user_id == DEFAULT_IG_USER_ID:
        print("      PASS: IG_USER_ID ตรงกับค่าที่คาดไว้ (%s)" % ig_user_id)
    else:
        print("      INFO: พบ IG_USER_ID %s (ต่างจากค่าที่คาดไว้ จึงจะใช้ค่านี้)" % ig_user_id)

    print("[5/5] ตรวจสอบสิทธิ์ token กับ Instagram ...")
    ig_profile = graph_get(
        "/%s" % ig_user_id,
        {"fields": "id,username", "access_token": long_token},
    )
    print("      PASS: Instagram @%s" % safe_text(require_string(ig_profile, "username", "การตรวจสอบ Instagram")))

    return {
        "IG_ACCESS_TOKEN": long_token,
        "IG_USER_ID": ig_user_id,
        "FB_PAGE_ID": FB_PAGE_ID,
        "FB_PAGE_TOKEN": page_token,
        "FB_APP_ID": app_id,
        "FB_APP_SECRET": app_secret,
    }


def run_quiet(command, input_value=None):
    """Run a local command with all output discarded to avoid credential leaks."""
    try:
        return subprocess.run(
            command,
            input=input_value,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
    except OSError:
        return None


def github_cli_ready():
    gh_path = shutil.which("gh")
    if not gh_path:
        print("GitHub CLI ไม่พบในเครื่อง — จะใช้หน้าเว็บและ clipboard แทน")
        return None
    if run_quiet([gh_path, "auth", "status"]) != 0:
        print("GitHub CLI ยังไม่ได้ล็อกอิน — จะใช้หน้าเว็บและ clipboard แทน")
        return None
    print("GitHub CLI พร้อมใช้งาน — จะตั้งค่า secrets โดยตรง")
    return gh_path


def list_github_secret_names(gh_path):
    """Return only public secret names; discard all diagnostics."""
    try:
        result = subprocess.run(
            [gh_path, "secret", "list", "--repo", REPOSITORY],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return {line.split(None, 1)[0] for line in result.stdout.splitlines() if line.split()}


def set_secrets_with_gh(gh_path, values):
    print("กำลังตั้งค่า GitHub Actions secrets ...")
    for name in SECRET_NAMES:
        # Current gh reads a secret from stdin when --body is omitted.  Do not
        # pass credentials as command-line arguments or environment variables.
        status = run_quiet(
            [gh_path, "secret", "set", name, "--repo", REPOSITORY],
            input_value=values[name],
        )
        if status != 0:
            print("  FAIL  %s" % name)
            print("หยุดเพื่อความปลอดภัย: โปรดตรวจสอบสิทธิ์ GitHub แล้วรันสคริปต์ใหม่")
            return False
        print("  PASS  %s" % name)

    listed_names = list_github_secret_names(gh_path)
    print("\nผลตรวจสอบ GitHub secrets:")
    if listed_names is None:
        for name in SECRET_NAMES:
            print("  FAIL  %s (อ่านรายการ secrets ไม่สำเร็จ)" % name)
        return False
    for name in SECRET_NAMES:
        print("  %s  %s" % ("PASS" if name in listed_names else "FAIL", name))
    return all(name in listed_names for name in SECRET_NAMES)


def copy_to_windows_clipboard(value):
    return run_quiet(["clip"], input_value=value) == 0


def set_secrets_with_clipboard(values):
    print("เปิดหน้า GitHub Secrets ในเบราว์เซอร์แล้ว")
    webbrowser.open(GITHUB_SECRETS_URL)
    print("เพิ่ม secret ตามชื่อที่แจ้งด้านล่างทีละรายการ แล้ววางค่าจาก clipboard")
    try:
        for name in SECRET_NAMES:
            if not copy_to_windows_clipboard(values[name]):
                print("  FAIL  %s (ไม่สามารถใช้ Windows clipboard ได้)" % name)
                return False
            print("  พร้อมวาง: %s" % name)
            try:
                input("  สร้าง/อัปเดต secret นี้ใน GitHub แล้วกด Enter เพื่อไปต่อ: ")
            except (EOFError, KeyboardInterrupt):
                print("  ยกเลิกโดยผู้ใช้")
                return False
    finally:
        # Do not leave the last credential on the clipboard.
        copy_to_windows_clipboard("")
    print("ล้าง Windows clipboard แล้ว")
    print("\nโปรดตรวจสอบรายชื่อ secrets ใน GitHub UI: %s" % ", ".join(SECRET_NAMES))
    return True


def final_summary(success):
    if success:
        print("\nเสร็จเรียบร้อย: ไม่ต้องตั้งค่าเพิ่ม")
        print("- ig-reels จะเผยแพร่ทุกวันเวลา 20:00 น. (เวลาไทย)")
        print("- fb-feed จะทำงานทุกวันเวลา 15:00 น. และเรียก schedule_fb_batch2.py อัตโนมัติ")
    else:
        print("\nยังตั้งค่าไม่ครบ: แก้ไขรายการที่ FAIL แล้วรันสคริปต์นี้ใหม่")


def main():
    configure_utf8_output()
    values = {}
    try:
        short_token, app_id, app_secret = collect_inputs()
        values = validate_and_prepare(short_token, app_id, app_secret)
        gh_path = github_cli_ready()
        success = set_secrets_with_gh(gh_path, values) if gh_path else set_secrets_with_clipboard(values)
        final_summary(success)
        return 0 if success else 2
    except SetupError as exc:
        print("\nหยุด: %s" % exc)
        print("ไม่มี credential ใดถูกพิมพ์หรือบันทึกลงไฟล์")
        return 2
    finally:
        # Drop references as soon as setup is complete.  Secrets were never
        # written to disk, stdout/stderr, subprocess arguments, or logs.
        values.clear()


if __name__ == "__main__":
    sys.exit(main())
