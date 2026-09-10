@echo off
rem Standard Codex dispatcher. Use: tools\codex_send.cmd <spec-relative-path> <report-relative-path>
rem
rem WHY NOT codex_run.cmd: that wrapper passes the report path to codex -o, and -o
rem overwrites that file with Codex's final chat message when the run ends. On
rem 9 Sep a spec told Codex to write its report to the same path, Codex did the
rem whole job, and -o then replaced 15 KB of findings with three lines. The report
rem path and the -o path must never be the same file.
rem
rem The final chat message lands next to the report as <report>.final.txt.
cd /d C:\Users\nL_ku\ngernduangold-site
codex exec -C C:\Users\nL_ku\ngernduangold-site -s workspace-write --skip-git-repo-check --color never -o "%2.final.txt" "Read the file %1 (UTF-8, Thai) and execute exactly what it specifies. Obey every rule in it: UTF-8 files only, no git push, no git add -A, touch only the files it names, delete nothing unless it explicitly says so. Write your full report to %2 - that file is yours to overwrite. Your final message must be the short summary the spec asks for." < nul
echo CODEX_EXIT=%ERRORLEVEL%
