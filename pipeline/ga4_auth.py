"""ga4_auth.py — ขอ token ครั้งเดียวด้วย OAuth (installed-app) แล้วเซฟ secrets/ga4-token.json
ใช้ client_secret ที่ secrets/ga4-client.json (โหลดจาก Cloud Console -> Credentials -> OAuth client = Desktop app)
รันครั้งเดียว: py pipeline\\ga4_auth.py  -> เบราว์เซอร์เปิด -> กด Allow (ถ้าเตือน unverified ให้ Advanced -> Go to app)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEC = os.path.join(ROOT, "secrets")
CLIENT = os.path.join(SEC, "ga4-client.json")
TOKEN = os.path.join(SEC, "ga4-token.json")
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly",
          "https://www.googleapis.com/auth/webmasters.readonly"]  # +GSC keyword data (re-consent 1 ครั้ง)


def main():
    if not os.path.exists(CLIENT):
        print("ไม่พบไฟล์", CLIENT)
        print("-> โหลด OAuth client (Desktop app) JSON จาก Cloud Console มาวางที่ secrets\\ga4-client.json ก่อน")
        return
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception as e:
        print("ต้องติดตั้ง: pip install google-auth-oauthlib (%s)" % e)
        return
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    os.makedirs(SEC, exist_ok=True)
    open(TOKEN, "w", encoding="utf-8").write(creds.to_json())
    print("OK -> เซฟ token ที่", TOKEN, "| เชื่อม GA4 สำเร็จ พร้อมรัน ga4_pull.py")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
