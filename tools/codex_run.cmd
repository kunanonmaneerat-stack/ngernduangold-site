@echo off
rem ตัวรัน Codex มาตรฐาน (ประหยัด token: ไม่ต้องเขียน wrapper ใหม่ทุกรอบ)
rem ใช้: tools\codex_run.cmd <spec.md ใน repo> <out.md ใน repo>
rem spec = คำสั่งละเอียดภาษาไทย UTF-8 · out = ข้อความสรุปสุดท้ายของ Codex
cd /d C:\Users\nL_ku\ngernduangold-site
codex exec -C C:\Users\nL_ku\ngernduangold-site -s workspace-write --skip-git-repo-check --color never -o %2 "Read the file %1 (UTF-8, Thai) and execute exactly what it specifies. Obey every rule in it: UTF-8 files only, no git push, no git add -A, touch only the files it names, delete nothing unless it explicitly says so. Your final message must be the short report it asks for." < nul
echo CODEX_EXIT=%ERRORLEVEL%
