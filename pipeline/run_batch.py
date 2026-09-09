"""Run a local draft batch through ``head_content`` with truthful exit state."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import head_content

TOPICS = [
    "เงินเดือน 15000 อยากได้บัตรเครดิตใบแรก สมัครใบไหนพอมีโอกาสผ่าน",
    "ฟรีแลนซ์รายได้ไม่ประจำ อยากได้บัตรหรือสินเชื่อ ทำโปรไฟล์การเงินยังไงให้มีโอกาสผ่าน",
    "ผ่อนรถอยู่แต่เริ่มผ่อนไม่ไหว ควรขายดาวน์ รีไฟแนนซ์ หรือคืนรถ ต่างกันยังไง",
]


def _complete(result):
    if not isinstance(result, tuple) or len(result) < 3:
        return False
    rows = result[2]
    if not isinstance(rows, list) or not rows:
        return False
    return all(
        isinstance(row, dict)
        and row.get("ok") is True
        and isinstance(row.get("content"), str)
        and bool(row["content"].strip())
        for row in rows
    )


def main(topics=None, runner=None):
    selected = TOPICS if topics is None else list(topics)
    execute = head_content.run if runner is None else runner
    if not selected:
        print("=== BATCH BLOCKED: no topics configured ===", flush=True)
        return 2
    blockers = 0
    for index, topic in enumerate(selected, 1):
        print("=== [%d/%d] %s ===" % (index, len(selected), str(topic)[:46]), flush=True)
        try:
            result = execute(topic)
            if not _complete(result):
                blockers += 1
                print("  BLOCKED: incomplete or failed platform draft", flush=True)
        except Exception as exc:
            blockers += 1
            print("  RUNNER_FAILED: %s" % type(exc).__name__, flush=True)
    if blockers:
        print("=== BATCH COMPLETED_WITH_BLOCKERS %d/%d ===" % (blockers, len(selected)), flush=True)
        return 1
    print("=== BATCH DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
