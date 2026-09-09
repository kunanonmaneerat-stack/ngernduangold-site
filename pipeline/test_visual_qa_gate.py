#!/usr/bin/env python3
"""Regression proof that visual QA fails closed before publication."""
import sys
from PIL import Image

import qa_gate


def test_check_closes_image_even_when_provider_retains_reference(tmp_path, monkeypatch):
    frame = tmp_path / "frame.png"
    with Image.new("RGB", (4, 4), "white") as image:
        image.save(frame)
    retained = []

    def fake_generate(_prompt, **kwargs):
        retained.append(kwargs["images"][0])
        return '{"pass":true,"fails":[]}', "ok"

    monkeypatch.setattr(qa_gate.free_ai, "generate", fake_generate)
    result = qa_gate.check(str(frame))
    assert result["pass"] is True
    assert retained and retained[0].fp is None


def main():
    original_check = qa_gate.check
    original_argv = list(sys.argv)
    cases = [
        ("explicit pass", {"status": "ok", "pass": True, "fails": []}, 0),
        ("explicit visual fail", {"status": "ok", "pass": False, "fails": ["logo"]}, 2),
        ("missing model key", {"status": "SKIP_NO_KEY", "pass": None, "fails": []}, 2),
        ("unparseable model output", {"status": "PARSE_ERROR", "pass": None, "fails": []}, 2),
        ("provider error", {"status": "ERROR", "pass": None, "fails": []}, 2),
    ]
    try:
        sys.argv = ["qa_gate.py", "fixture.png"]
        for label, result, expected in cases:
            qa_gate.check = lambda _path, value=result: value
            got = qa_gate.main()
            if got != expected:
                raise AssertionError("%s returned %s, expected %s" % (label, got, expected))
            print("PASS", label)
    finally:
        qa_gate.check = original_check
        sys.argv = original_argv
    print("visual QA fail-closed: 5/5 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
