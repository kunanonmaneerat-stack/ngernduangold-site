#!/usr/bin/env python3
"""script_gen — STEP 2: turn each trend topic into 5 short-form script VARIANTS (Gemini free).
Applies the blueprint Prompting Rules: 0-1.5s pattern-interrupt hook, one idea, ends with an
open question + "ลิงก์ในไบโอ", money-intent + sub-id note, finance disclosure.
Writes pipeline/scripts/<topic>-YYYYMMDD.json.

Fail-closed: no key -> skip cleanly (exit 0, no paid call). NO evasion logic.
The clip itself is built by the EXISTING ffmpeg engine (tiktok-weekly-content-engine) — this
script only produces text scripts; it does NOT generate paid video.
"""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_ai

RULES = """กฎการเขียนสคริปต์คลิปสั้น (ต่อ 1 หัวข้อ ให้ 5 variant ที่ต่างกันจริง):
- Hook วินาที 0-1.5 = pattern interrupt (ตัวเลขสะดุด / คำถามเจ็บ / ภาพตรงข้ามคาด) ห้ามเกริ่น
- 1 คลิป = 1 ความคิด, ภาษามนุษย์เงินเดือน 25-45, จบด้วย "คำถามปลายเปิด" + CTA "ลิงก์ในไบโอ"
- ผูก money-intent (บัตร/หนี้/สินเชื่อ/ออม) ระบุ money_page + provider
- สินเชื่อทุกตัวต้องมี disclosure "*เพื่อการศึกษา · กู้เท่าที่จำเป็น" และห้ามแต่งตัวเลขดอกเบี้ย/การันตีอนุมัติ
ตอบเป็น JSON array ล้วน: [{"variant":1,"hook":"...","body":"...","cta_question":"...","money_page":"...","provider":"...","format":"number-shock|compare|myth-bust|pov|checklist"}]"""


def gen_for_topic(topic, intent, money_page):
    prompt = f"หัวข้อ: {topic}\nintent: {intent}\nmoney_page: {money_page}\n\n{RULES}"
    return free_ai.generate(prompt, model="gemini-2.0-flash")


def main():
    # locate latest trends file
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    trends = sorted([f for f in os.listdir(data_dir)] if os.path.isdir(data_dir) else [], reverse=True)
    trends = [f for f in trends if f.startswith("trends-")]
    if not trends:
        # still verify the key path / fail-closed even with no trends file
        _, st = free_ai.generate("ping", model="gemini-2.0-flash")
        if st == "NO_KEY":
            print("SKIP script_gen: no GOOGLE_AI_STUDIO_KEY (fail-closed). Run trend_ingest after owner adds key.")
        else:
            print("script_gen: no trends file yet (run trend_ingest first). key_present:", st != "NO_KEY")
        return 0
    topics = json.load(open(os.path.join(data_dir, trends[0]), encoding="utf-8"))
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
    os.makedirs(out_dir, exist_ok=True)
    made = 0
    for t in topics[:8]:
        txt, st = gen_for_topic(t.get("topic", ""), t.get("intent", ""), t.get("money_page", ""))
        if st == "NO_KEY":
            print("SKIP script_gen: no key (fail-closed).")
            return 0
        if st == "ok" and txt:
            fn = os.path.join(out_dir, (t.get("money_page") or "topic") + "-" +
                              datetime.datetime.now().strftime("%Y%m%d") + ".json")
            open(fn, "w", encoding="utf-8").write(txt)
            made += 1
    print(f"script_gen: wrote {made} script files -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
