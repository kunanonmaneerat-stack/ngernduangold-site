# YouTube batch2 scheduled-uploader report — 2026-07-16

## Step 1 — credential recon

- `pipeline/gsc_pull.py` uses `google.oauth2.credentials.Credentials.from_authorized_user_file`; it is an OAuth user-token setup, not a service-account setup.  The script references `secrets/gsc-token.json` and `secrets/ga4-token.json`.
- `secrets/ga4-client.json` is an OAuth **installed-app (Desktop)** client (its top-level client type is `installed`).  It is the only reusable Google OAuth client found.  It can be used by the uploader only when its Google Cloud project has **YouTube Data API v3** enabled and the channel owner completes a new YouTube-upload consent flow.
- `secrets/ga4-token.json` is an existing OAuth token cache, not a YouTube upload token.  The uploader does not reuse it; it writes a separate `secrets/yt_token.json` cache after owner consent.
- No service-account credential was found for this workflow; a service account would not be suitable for uploads to the personal channel.
- `.gitignore` ignores `secrets/`; the uploader also verifies this with `git check-ignore` before selecting `secrets/yt_token.json`.  If that check fails, it uses `%USERPROFILE%\.ngernduangold\yt_token.json` instead.

No credential contents or secret values were read into this report.

## Step 2 — delivered uploader

Created `tools/yt_upload_batch2.py`.

- Default `--dry-run` reads only the manifest and prints the seven planned uploads; it never imports Google libraries, starts OAuth, writes files, or uploads.
- `--live` validates the seven MP4 paths, uses the first line of `captions.youtube` as a maximum-100-character title ending in `#Shorts`, schedules each item for 19:00 Asia/Bangkok (`12:00Z`), and uses private scheduled uploads with category `27`, Thai default language, and the full caption as the description.
- It automatically discovers an installed OAuth client in `secrets/` (preferring an explicit YouTube client file, then the existing `secrets/ga4-client.json`), stores a dedicated YouTube token cache safely, caps one run at six uploads, retries 5xx failures up to three times with backoff, and handles `quotaExceeded` / `uploadLimitExceeded` cleanly.
- `.system_control/yt_upload_log.json` is used as the date-to-videoId deduplication log.  After each confirmed upload, the script atomically updates that log and the corresponding manifest field to `scheduled (yt-api <videoId>)` using UTF-8 with two-space JSON indentation.
- `--check` makes best-effort authenticated title searches for the seven planned titles and never uploads or writes files.

## Planned dry-run output (derived from the current manifest)

The required `py` launcher is not available in this execution environment, so the command below could not be run here.  The following seven rows were reconstructed directly from the actual UTF-8 manifest using the uploader's title and timestamp rules; no OAuth was triggered.

```text
2026-07-20 | file=reels/batch2/20_debt-health-check.mp4 | title=ไม่รู้จะเริ่มปลดหนี้ตรงไหน? 🚦 เช็กสุขภาพหนี้ 60 วิ ตอบ 6 คำถาม รู้เลยว่าอยู่โซนเขียว/เหลือง/ #Shorts | publishAt=2026-07-20T12:00:00Z | desc80=ไม่รู้จะเริ่มปลดหนี้ตรงไหน? 🚦 เช็กสุขภาพหนี้ 60 วิ ตอบ 6 คำถาม รู้เลยว่าอยู่โซนเ
2026-07-21 | file=reels/batch2/21_freedom-clock.mp4 | title=จ่ายหนี้ไปเรื่อยๆ แต่ไม่รู้จะหมดเมื่อไหร่? ⏰ กรอกยอดหนี้ + เงินที่โปะได้ เห็น "วันปลอดหนี้" #Shorts | publishAt=2026-07-21T12:00:00Z | desc80=จ่ายหนี้ไปเรื่อยๆ แต่ไม่รู้จะหมดเมื่อไหร่? ⏰ กรอกยอดหนี้ + เงินที่โปะได้ เห็น "ว
2026-07-22 | file=reels/batch2/22_letter-lower-rate.mp4 | title=ดอกเบี้ยบัตร/สินเชื่อ "ขอลดได้" นะ 💰 บอกว่า "อยากปิดให้เร็วขึ้น" ไม่ใช่ "ไม่มีจ่าย" — พิมพ์ #Shorts | publishAt=2026-07-22T12:00:00Z | desc80=ดอกเบี้ยบัตร/สินเชื่อ "ขอลดได้" นะ 💰 บอกว่า "อยากปิดให้เร็วขึ้น" ไม่ใช่ "ไม่มีจ่
2026-07-23 | file=reels/batch2/23_credit-bureau.mp4 | title=สมัครบัตร/สินเชื่อไม่ผ่านบ่อยๆ? 🤔 เช็กเครดิตบูโรตัวเองก่อนยื่น รู้จุดที่ต้องแก้ · ลิงก์ในไบโ #Shorts | publishAt=2026-07-23T12:00:00Z | desc80=สมัครบัตร/สินเชื่อไม่ผ่านบ่อยๆ? 🤔 เช็กเครดิตบูโรตัวเองก่อนยื่น รู้จุดที่ต้องแก้ 
2026-07-24 | file=reels/batch2/24_first-card.mp4 | title=เงินเดือนยังไม่เยอะ อยากมีบัตรใบแรกสร้างเครดิต? 💳 มีบัตรสำหรับคนเริ่มต้น เทียบค่าธรรมเนียม+ส #Shorts | publishAt=2026-07-24T12:00:00Z | desc80=เงินเดือนยังไม่เยอะ อยากมีบัตรใบแรกสร้างเครดิต? 💳 มีบัตรสำหรับคนเริ่มต้น เทียบค่
2026-07-25 | file=reels/batch2/25_card-fees.mp4 | title=ถือบัตรอยู่แต่ไม่รู้จ่ายค่าธรรมเนียมอะไรบ้าง? 🔍 ค่ารายปี · กดเงินสด · แปลงสกุล · ดอกผ่อน บาง #Shorts | publishAt=2026-07-25T12:00:00Z | desc80=ถือบัตรอยู่แต่ไม่รู้จ่ายค่าธรรมเนียมอะไรบ้าง? 🔍 ค่ารายปี · กดเงินสด · แปลงสกุล ·
2026-07-26 | file=reels/batch2/26_high-yield-savings.mp4 | title=เงินเย็นในออมทรัพย์ ดอกน้อยไม่ทันเงินเฟ้อ 😴 มีบัญชีออมดอกสูงที่ "ถอนได้" ดอกสูงกว่าหลายเท่า #Shorts | publishAt=2026-07-26T12:00:00Z | desc80=เงินเย็นในออมทรัพย์ ดอกน้อยไม่ทันเงินเฟ้อ 😴 มีบัญชีออมดอกสูงที่ "ถอนได้" ดอกสูงก
```

## Verification status

- All seven `reels/batch2/20_*.mp4` through `26_*.mp4` files were confirmed present.
- `py -m py_compile tools/yt_upload_batch2.py` was attempted but could not run because the required `py` launcher is unavailable (`'py' is not recognized`).
- `py tools/yt_upload_batch2.py --dry-run` was also attempted and failed for the same missing launcher. A discovered `python.exe` fallback is a sandboxed `uv` trampoline; both fallback compile and dry-run attempts fail before Python starts with `permission denied (os error 5)`. No OAuth flow, dependency installation, or live upload was attempted.

## Exact owner actions

### Existing OAuth client path (this repo's current setup)

1. In the Google Cloud project that owns `secrets/ga4-client.json`, enable **YouTube Data API v3** at <https://console.cloud.google.com/apis/library/youtube.googleapis.com>.
2. If the three Python packages are not already installed, run:

   ```powershell
   py -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2
   ```

3. Review the plan, then run this single live command:

   ```powershell
   py tools/yt_upload_batch2.py --live --limit 6
   ```

   A browser consent screen will open.  Sign in as the owner of YouTube channel `UCVuqb7l5rJ4Q7PUKSIgsL4w` and allow the app to upload/manage the channel's YouTube videos (the required `youtube.upload` scope).  The first six videos will remain private until their scheduled 19:00 Asia/Bangkok publication times.

4. On the next YouTube quota day, run:

   ```powershell
   py tools/yt_upload_batch2.py --live --limit 1
   ```

### If an OAuth Desktop client is unavailable or cannot be used

1. Open <https://console.cloud.google.com/> and select or create the owner-managed Google Cloud project.
2. Enable YouTube Data API v3 at <https://console.cloud.google.com/apis/library/youtube.googleapis.com>.
3. Configure the OAuth consent screen at <https://console.cloud.google.com/apis/credentials/consent>; add the channel owner as a test user if the app remains in Testing.
4. Open <https://console.cloud.google.com/apis/credentials> and choose **Create credentials** → **OAuth client ID**.
5. Choose **Desktop app**, name it, and create it.
6. Download the JSON client file and save it as `secrets/yt_client_secret.json` (do not commit it).
7. Install the three packages with the command above if needed.
8. Run `py tools/yt_upload_batch2.py --live --limit 6` and approve the owner consent screen.

## Caveats

- A YouTube Data API upload costs about 1,600 quota units.  Six uploads are about 9,600 of the usual 10,000-unit daily allowance; the final video should normally wait for the next quota day.  All seven can be scheduled on one day only if the project's available quota is demonstrably at least about 11,200 units; the script still enforces six uploads per invocation, so make a second `--limit 1` invocation only after confirming that headroom.
- `--check` is intentionally best effort: missing auth, a quota response, or insufficient read permission is reported without uploading anything.  The local deduplication log remains the authoritative guard for prior API uploads.
- No `--live` command was run in this task.
