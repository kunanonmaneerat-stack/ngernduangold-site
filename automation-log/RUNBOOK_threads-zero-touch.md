# RUNBOOK: Threads zero-touch video post (พิสูจน์แล้ว 16 ก.ค. 2026)

ใช้โดย scheduled tasks threads-post-17..26 — โพสต์วิดีโอ Threads โดยไม่ต้องให้เจ้าของแนบไฟล์
หลักการ: คลิกในเพจ = Chrome extension (trusted) · OS file dialog = สคริปต์ `tools\picker_fill.ps1` (WM_SETTEXT + IDOK)

## เงื่อนไขก่อนเริ่ม
- เครื่องเจ้าของเปิดอยู่ + Chrome ล็อกอิน Threads (@ngernduangold)
- ห้ามโพสต์ซ้ำ: เช็กโปรไฟล์ก่อนเสมอ (ขั้น 2)

## ขั้นตอน (ตามลำดับเป๊ะ)
1. โหลดเครื่องมือ (ToolSearch): `mcp__claude-in-chrome__*` (tabs_context_mcp, tabs_create_mcp, navigate, computer, find, read_page, resize_window) + `mcp__Windows-MCP__Snapshot, Click` + Desktop Commander (start_process, read_process_output)
2. **กันซ้ำ**: tabs_context (createIfEmpty) → navigate ไป https://www.threads.com/@ngernduangold → get_page_text → ถ้าเห็นข้อความ 20 ตัวอักษรแรกของแคปชั่นวันนี้แล้ว → หยุด รายงาน "มีแล้ว ไม่โพสต์ซ้ำ"
3. **ยกหน้าต่างขึ้น foreground**: เรียก resize_window (tabId ของแท็บเรา, width 1536, height 960) — คำสั่งนี้ดึงหน้าต่าง Chrome ที่มีแท็บเราขึ้นหน้า
4. **ทำให้แท็บเรา active**: Windows-MCP Snapshot (use_ui_tree true) → ดู "Focused Window" ต้องเป็น Chrome → หา element รายการแท็บ (control_type รายการแท็บ) ที่ name มีทั้ง "Threads" และชื่อกลุ่มของ session เรา → Windows-MCP Click label=<id นั้น> → เช็กด้วย extension screenshot ว่าเห็นหน้า Threads
5. **เปิด composer**: คลิก (extension) ช่อง "มีอะไรมาเล่าสู่กันฟังไหม" → dialog "เธรดใหม่" เปิด
6. **พิมพ์แคปชั่น**: คลิกในช่องข้อความของ dialog → type แคปชั่น verbatim (จาก prompt ของ task)
   - ถ้ามี link preview card โผล่ (แคปชั่นมีลิงก์) ให้กด X มุมการ์ดก่อนแนบวิดีโอ — แถวไอคอนสื่อจะกลับมา
7. **แนบวิดีโอ**: คลิกไอคอนรูปภาพ/สื่อ (ตัวแรกในแถวไอคอนใต้ข้อความ) → จากนั้นรันทันทีด้วย Desktop Commander:
   `powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\nL_ku\ngernduangold-site\tools\picker_fill.ps1" -FilePath "<path ไฟล์ mp4 เต็ม>"`
   → ต้องเห็น `SETTEXT_OK;IDOK_CLICKED` และ `DIALOG_CLOSED_OK`
   - ถ้า `NO_DIALOG_FOUND`: หน้าต่างไม่ได้ foreground → ทำขั้น 3–4 ใหม่ แล้วคลิกไอคอนสื่อใหม่ → รันสคริปต์ซ้ำ (ลองได้สูงสุด 2 รอบ)
   - ถ้า dialog มี error "ไม่พบแฟ้ม" ค้าง: Windows-MCP Snapshot → Click ปุ่ม "ตกลง" → รันสคริปต์ซ้ำ
8. **ตรวจ + โพสต์**: extension screenshot → ต้องเห็น thumbnail วิดีโอใน composer → คลิกปุ่ม "โพสต์" → รอ 8 วิ → ต้องเห็น toast "โพสต์แล้ว" หรือโพสต์ใหม่บนโปรไฟล์
9. **บันทึก**: Desktop Commander รัน
   `cmd /c "cd /d C:\Users\nL_ku\ngernduangold-site && py tools\threads_ledger.py --date <YYYY-MM-DD>"`
   → ต้องได้ `LEDGER_OK` (หรือ `ALREADY_LEDGERED`)
10. รายงานผลสั้นๆ ภาษาไทย

## FALLBACK A — extension ล่ม (Claude in Chrome ไม่เชื่อม) → ใช้ Windows-MCP ล้วน (พิสูจน์แล้ว 17 ก.ค.)
ถ้า tabs_context ตอบ "not connected" ซ้ำ 2 ครั้ง: ทำทุกขั้นด้วย Windows-MCP แทน (คลิกจริง OS-level = trusted เหมือนกัน):
1. App switch หา window Chrome ที่ title มี "เงินเดือนสมองทอง (@ngernduangold) • Threads" (ถ้าเจอ composer ค้างของเก่า: กดยกเลิก → "ไม่บันทึก" ทิ้งก่อน) · ถ้าไม่มี: เปิด window ใหม่ Ctrl+N → พิมพ์ URL ในแถบที่อยู่ (label จาก Snapshot) → threads.com/@ngernduangold
2. กันซ้ำ: F5 → pagedown → Snapshot(vision) ดู timestamp โพสต์บนสุดที่ไม่ใช่ปักหมุด — ถ้าเป็นของวันนี้ → หยุด
3. แคปชั่น: ห้ามพิมพ์ตรง (คีย์บอร์ดไทยพัง) → Clipboard set แคปชั่น → คลิก "เธรดใหม่" → ctrl+v → เช็ค value จาก Snapshot ต้อง verbatim
4. การ์ด link preview: คลิกปุ่ม "ลบออก" (X บนการ์ด)
5. คลิก "แนบสื่อ" → รันทันที: cmd /c "ping -n 3 127.0.0.1 > nul & powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\nL_ku\ngernduangold-site\tools\picker_fill.ps1 -FilePath <ไฟล์>" → ต้องได้ SETTEXT_OK;IDOK_CLICKED + DIALOG_CLOSED_OK
6. Snapshot เห็น thumbnail → คลิก "โพสต์" → รอ 9 วิ → Snapshot เห็นโพสต์ใหม่ "x นาที" บนโปรไฟล์ → ledger ตามปกติ
ระวัง: แอป ChatGPT/Codex ชอบเด้งแย่ง foreground — ถ้าหน้าจอเปลี่ยนเป็นแอปอื่น ให้ Esc แล้ว App switch กลับ ห้ามคลิกอะไรในแอปนั้น (โดยเฉพาะเมนู "รีเซ็ตได้ 1 ครั้ง")

## FALLBACK B (ล้มเหลวทุกทางเกิน 2 รอบ)
พิมพ์แคปชั่นค้างไว้ใน composer แล้วแจ้งเจ้าของ: "รบกวนแนบไฟล์ <ชื่อไฟล์> แล้วกดโพสต์" — ห้ามกดโพสต์เองถ้ายังไม่มีวิดีโอ

## ห้าม
- โพสต์ซ้ำ / โพสต์โดยไม่มีวิดีโอ / แก้แคปชั่นเอง
- แตะแท็บอื่นใน Chrome นอกจากแท็บของเราเอง (ห้ามปิด/สลับแท็บงานอื่น)
- เกิน 1 โพสต์ Threads ต่อวัน
