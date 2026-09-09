#!/usr/bin/env python3
"""Regression tests for the page-only public identity gate."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import public_identity_guard as guard


BRAND = "\u0e40\u0e07\u0e34\u0e19\u0e40\u0e14\u0e37\u0e2d\u0e19\u0e2a\u0e21\u0e2d\u0e07\u0e17\u0e2d\u0e07"
PERSONAL = "\u0e1c\u0e21"
MARKER = "PUBLIC_IDENTITY_PAGE_ONLY"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, (dict, list)):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(value, encoding="utf-8")


def _fixture(root: Path) -> tuple[Path, Path]:
    policy = {
        "public_identity": {
            "canonical_name": BRAND,
            "entity_type": "Organization",
            "page_only": True,
            "forbidden_public_speakers": [
                "codex", "claude", "cowork", "chatgpt", "gemini"
            ],
            "forbidden_personal_claim_patterns": [
                "(?<![\u0E00-\u0E7F])(?:\u0e1c\u0e21|\u0e09\u0e31\u0e19|\u0e14\u0e34\u0e09\u0e31\u0e19)(?![\u0E00-\u0E7F])",
                "personal-experience-claim",
            ],
            "allowed_ai_disclosures": ["\u0e1c\u0e25\u0e34\u0e15\u0e14\u0e49\u0e27\u0e22 AI"],
            "required_prompt_marker": MARKER,
            "outward_copy_tasks": ["draft-task"],
        }
    }
    _write(root / ".system_control" / "policy.json", policy)
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "safe",
        "author": {"@type": "Organization", "name": BRAND},
        "publisher": {"@type": "Organization", "name": BRAND},
    }
    page = (
        '<!doctype html><html><head><meta name="author" content="%s">'
        '<meta property="og:site_name" content="%s">'
        '<script type="application/ld+json">%s</script></head>'
        '<body>%s safe \u0e1c\u0e25\u0e34\u0e15\u0e14\u0e49\u0e27\u0e22 AI</body></html>'
        % (BRAND, BRAND, json.dumps(article, ensure_ascii=False), BRAND)
    )
    _write(root / "site" / "index.html", page)
    _write(
        root / ".system_control" / "content_manifest.json",
        {
            "items": [
                {
                    "id": "c1",
                    "topic_th": "safe",
                    "disclosure": "\u0e1c\u0e25\u0e34\u0e15\u0e14\u0e49\u0e27\u0e22 AI",
                    "captions": {"facebook": "safe"},
                }
            ]
        },
    )
    _write(
        root / "automation-log" / "KNOWLEDGE-POSTS-test.md",
        "| date | id | copy |\n|---|---|---|\n| 2026-08-16 | k1 | safe |\n",
    )
    prompts = root / "prompts"
    _write(
        prompts / "draft-task" / "SKILL.md",
        "---\nname: draft-task\n---\n%s %s safe\n" % (MARKER, BRAND),
    )
    return root / ".system_control" / "policy.json", prompts


def _run(mutator=None) -> set[str]:
    with tempfile.TemporaryDirectory(prefix="public_identity_") as temp:
        root = Path(temp)
        policy, prompts = _fixture(root)
        if mutator:
            mutator(root, policy, prompts)
        findings, _counts = guard.scan(
            repo=root,
            policy_path=policy,
            site=root / "site",
            manifest=root / ".system_control" / "content_manifest.json",
            prompt_roots=(("test", prompts),),
        )
        return {finding.category for finding in findings}


def _replace(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def _add_data_label_contract(root: Path) -> None:
    _replace(
        root / "site" / "index.html",
        "</head>",
        '<style>.x::before { content: attr(data-l); }</style></head>',
    )
    _replace(
        root / "site" / "index.html",
        "</body>",
        '<span class="x" data-l="safe"></span></body>',
    )


def _trust_remote_stylesheet(policy: Path, value: str) -> None:
    payload = json.loads(policy.read_text(encoding="utf-8"))
    payload["public_identity"]["trusted_remote_stylesheets"] = [value]
    _write(policy, payload)


cases = []


def check(label: str, got: bool) -> None:
    cases.append(got)
    print(("PASS " if got else "FAIL ") + label)


check("valid page identity fixture", _run() == set())
check(
    "missing page author is blocked",
    "PAGE_AUTHOR_MISSING" in _run(
        lambda root, _p, _r: _replace(root / "site" / "index.html", '<meta name="author" content="%s">' % BRAND, "")
    ),
)
check(
    "wrong JSON-LD byline is blocked",
    "JSONLD_AUTHOR_NOT_PAGE" in _run(
        lambda root, _p, _r: _replace(root / "site" / "index.html", '"@type": "Organization"', '"@type": "Person"')
    ),
)
check(
    "personal voice on a page is blocked",
    "PERSONAL_PUBLIC_VOICE" in _run(
        lambda root, _p, _r: _replace(root / "site" / "index.html", "safe", PERSONAL)
    ),
)
check(
    "agent byline on a page is blocked",
    "AGENT_AS_PUBLIC_SPEAKER" in _run(
        lambda root, _p, _r: _replace(root / "site" / "index.html", "safe", "Codex")
    ),
)
check(
    "personal voice in public HTML metadata is blocked",
    "PERSONAL_PUBLIC_VOICE" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<meta name="description" content="%s"></head>' % PERSONAL,
        )
    ),
)
check(
    "agent voice in public HTML metadata is blocked",
    "AGENT_AS_PUBLIC_SPEAKER" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<meta property="og:description" content="Codex"></head>',
        )
    ),
)
check(
    "personal voice in nested JSON-LD metadata is blocked",
    "PERSONAL_PUBLIC_VOICE" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<script type="application/ld+json">%s</script></head>'
            % json.dumps(
                {"mainEntity": [{"description": PERSONAL}]},
                ensure_ascii=False,
            ),
        )
    ),
)
check(
    "arbitrarily nested JSON-LD article identity is blocked",
    "JSONLD_AUTHOR_NOT_PAGE" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<script type="application/ld+json">%s</script></head>'
            % json.dumps(
                {
                    "mainEntity": {
                        "itemListElement": [{
                            "@type": "Article",
                            "author": {"@type": "Person", "name": "Other"},
                            "publisher": {"@type": "Organization", "name": BRAND},
                        }]
                    }
                },
                ensure_ascii=False,
            ),
        )
    ),
)
check(
    "personal voice in a manifest caption is blocked",
    "PERSONAL_PUBLIC_VOICE" in _run(
        lambda root, _p, _r: _replace(root / ".system_control" / "content_manifest.json", '"facebook": "safe"', '"facebook": "%s"' % PERSONAL)
    ),
)
check(
    "personal voice in a knowledge row is blocked",
    "PERSONAL_PUBLIC_VOICE" in _run(
        lambda root, _p, _r: _replace(root / "automation-log" / "KNOWLEDGE-POSTS-test.md", "| k1 | safe |", "| k1 | %s |" % PERSONAL)
    ),
)
check(
    "missing outward prompt marker is blocked",
    "PAGE_IDENTITY_MARKER_MISSING" in _run(
        lambda _root, _p, prompts: _replace(prompts / "draft-task" / "SKILL.md", MARKER, "MISSING")
    ),
)
check(
    "personal voice in an outward prompt is blocked",
    "PERSONAL_VOICE_IN_OUTWARD_PROMPT" in _run(
        lambda _root, _p, prompts: _replace(prompts / "draft-task" / "SKILL.md", "safe", PERSONAL)
    ),
)
check(
    "new outward task cannot bypass the SSOT list",
    "OUTWARD_TASK_UNDECLARED" in _run(
        lambda _root, _p, prompts: _write(
            prompts / "ngernduangold-new-copy-task" / "SKILL.md",
            "---\nname: ngernduangold-new-copy-task\n"
            "description: active\n---\ndraft pack for public copy\n",
        )
    ),
)
check(
    "page_only must be explicitly true",
    "PAGE_ONLY_NOT_TRUE" in _run(
        lambda _root, policy, _r: _replace(policy, '"page_only": true', '"page_only": false')
    ),
)
check(
    "malformed JSON-LD is blocked",
    "JSONLD_INVALID" in _run(
        lambda root, _p, _r: _replace(root / "site" / "index.html", '"headline": "safe"', '"headline": }')
    ),
)
check(
    "meta-refresh cannot hide personal public voice",
    "PERSONAL_PUBLIC_VOICE" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "<head>",
            '<head><meta http-equiv="refresh" content="0;url=/">'
        ) or _replace(root / "site" / "index.html", "safe", PERSONAL)
    ),
)
check(
    "nested public pages are identity-scanned",
    "PERSONAL_PUBLIC_VOICE" in _run(
        lambda root, _p, _r: _write(
            root / "site" / "nested" / "leak.html",
            (root / "site" / "index.html").read_text(encoding="utf-8").replace(
                "safe", PERSONAL
            ),
        )
    ),
)
check(
    "non-finite JSON-LD is blocked",
    "JSONLD_INVALID" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html", '"headline": "safe"', '"headline": NaN'
        )
    ),
)
check(
    "Infinity JSON-LD is blocked",
    "JSONLD_INVALID" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html", '"headline": "safe"',
            '"headline": Infinity',
        )
    ),
)
check(
    "overflowing finite-syntax JSON-LD is blocked",
    "JSONLD_INVALID" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html", '"headline": "safe"',
            '"headline": 1e999',
        )
    ),
)
check(
    "duplicate JSON-LD keys are blocked",
    "JSONLD_INVALID" in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            '"headline": "safe"',
            '"headline": "other", "headline": "safe"',
        )
    ),
)
check(
    "reordered identity meta attributes remain valid",
    _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            '<meta name="author" content="%s">' % BRAND,
            '<meta data-safe="1" content="%s" name="author">' % BRAND,
        )
        or _replace(
            root / "site" / "index.html",
            '<meta property="og:site_name" content="%s">' % BRAND,
            '<meta content="%s" property="og:site_name" data-safe="1">' % BRAND,
        )
    )
    == set(),
)
check(
    "conflicting duplicate author meta is blocked",
    {"PAGE_AUTHOR_AMBIGUOUS", "PAGE_AUTHOR_WRONG"}.issubset(
        _run(
            lambda root, _p, _r: _replace(
                root / "site" / "index.html",
                "</head>",
                '<meta content="Other Person" name="author"></head>',
            )
        )
    ),
)
check(
    "identical duplicate author meta is ambiguous",
    "PAGE_AUTHOR_AMBIGUOUS"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<meta content="%s" name="author"></head>' % BRAND,
        )
    ),
)
check(
    "empty author meta is blocked",
    "PAGE_AUTHOR_WRONG"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            '<meta name="author" content="%s">' % BRAND,
            '<meta content="" name="author">',
        )
    ),
)
check(
    "conflicting duplicate site-name meta is blocked",
    {"PAGE_SITE_NAME_AMBIGUOUS", "PAGE_SITE_NAME_WRONG"}.issubset(
        _run(
            lambda root, _p, _r: _replace(
                root / "site" / "index.html",
                "</head>",
                '<meta content="Other Page" property="og:site_name"></head>',
            )
        )
    ),
)
check(
    "personal voice in generated style-block text is blocked",
    "PERSONAL_PUBLIC_VOICE"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>body::before { content: "%s"; }</style></head>' % PERSONAL,
        )
    ),
)
check(
    "CSS-escaped agent voice in generated inline text is blocked",
    "AGENT_AS_PUBLIC_SPEAKER"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</body>",
            '<div style=\'content: "Co\\64 ex"\'></div></body>',
        )
    ),
)
check(
    "malformed generated CSS text fails closed",
    "CSS_GENERATED_TEXT_INVALID"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>.x::before { content: "unterminated; }</style></head>',
        )
    ),
)
check(
    "CSS selectors comments and unrelated declarations are not public copy",
    _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>.Codex { color: red; } /* content: "%s" */</style></head>'
            % PERSONAL,
        )
    )
    == set(),
)
check(
    "site data-label generated content is accepted after value inspection",
    _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>.cmp-t td::before { content: attr(data-l); }</style></head>',
        )
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<table class="cmp-t"><tr><td data-l="safe">safe</td></tr></table></body>',
        )
    )
    == set(),
)
check(
    "personal voice in generated data-label value is blocked",
    "PERSONAL_PUBLIC_VOICE"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>.x::before { content: attr(data-l); }</style></head>',
        )
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<span class="x" data-l="%s"></span></body>' % PERSONAL,
        )
    ),
)
check(
    "HTML-escaped agent voice in generated data-label value is blocked",
    "AGENT_AS_PUBLIC_SPEAKER"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>.x::before { content: attr(data-l); }</style></head>',
        )
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<span class="x" data-l="Co&#100;ex"></span></body>',
        )
    ),
)
check(
    "unapproved generated attribute name fails closed",
    "CSS_GENERATED_TEXT_INVALID"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>.x::before { content: attr(title); }</style></head>',
        )
    ),
)
check(
    "dynamic attr fallback construct fails closed",
    "CSS_GENERATED_TEXT_INVALID"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<style>.x::before { content: attr(data-l, "safe"); }</style></head>',
        )
    ),
)
check(
    "inline setAttribute runtime mutation is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>document.querySelector(".x").setAttribute("data-l", "Codex")</script></body>',
        )
    ),
)
check(
    "setAttributeNS and toggleAttribute runtime mutation are blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>var x=document.querySelector(".x");'
            'x.setAttributeNS(null,"data-l","Codex");'
            'x.toggleAttribute("data-l",true)</script></body>',
        )
    ),
)
check(
    "dataset runtime assignment is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>document.querySelector(".x").dataset["l"]="Codex"</script></body>',
        )
    ),
)
check(
    "unprovable computed attribute mutation is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>var key=location.hash.slice(1);'
            'document.querySelector(".x").setAttribute(key,"Codex")</script></body>',
        )
    ),
)
check(
    "computed mutation method is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>var method=location.hash.slice(1),key="data-l";'
            'document.querySelector(".x")[method](key,"Codex")</script></body>',
        )
    ),
)
check(
    "local external script mutation is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _write(
            root / "site" / "mutate.js",
            'document.querySelector(".x").dataset.l="Codex";',
        )
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script src="mutate.js"></script></body>',
        )
    ),
)
check(
    "untrusted remote script on generated-attribute page is unverified",
    "CSS_GENERATED_ATTRIBUTE_SCRIPT_UNVERIFIED"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script src="https://example.invalid/runtime.js"></script></body>',
        )
    ),
)
check(
    "remote dynamic module import on generated-attribute page is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script type="module">import("https://example.invalid/mutate.js")'
            ';</script></body>',
        )
    ),
)
check(
    "local dynamic module import cannot bypass script confinement",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _write(
            root / "site" / "mutate.js",
            'document.querySelector(".x").setAttribute("data-l","Codex");',
        )
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script type="module">import("./mutate.js");</script></body>',
        )
    ),
)
check(
    "escaped dynamic module import cannot bypass analysis",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script type="module">\\u0069mport("./mutate.js");</script></body>',
        )
    ),
)
check(
    "eval string mutation is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>eval(\'document.querySelector(".x").setAttribute('
            '"data-l","Codex")\')</script></body>',
        )
    ),
)
check(
    "timer string execution is blocked without rejecting function callbacks",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>setTimeout(\'document.querySelector(".x").setAttribute('
            '"data-l","Codex")\',0)</script></body>',
        )
    )
    and _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>setTimeout(function(){return "safe"},0)</script></body>',
        )
    )
    == set(),
)
check(
    "HTML parsing sinks cannot replace a generated attribute",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>document.querySelector(".x").outerHTML='
            '\'<span class="x" data-l="Codex"></span>\'</script></body>',
        )
    ),
)
check(
    "innerHTML that creates a generated attribute is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>document.querySelector("#safe").innerHTML='
            '\'<span data-l="Codex"></span>\'</script></body>',
        )
    ),
)
check(
    "unrelated bounded innerHTML is not a generated-attribute mutation",
    _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>document.querySelector("#safe").innerHTML='
            '\'<ul><li>safe</li></ul>\'</script></body>',
        )
    )
    == set(),
)
check(
    "linked local CSS generated data is identity-scanned",
    "PERSONAL_PUBLIC_VOICE"
    in _run(
        lambda root, _p, _r: _write(
            root / "site" / "style.css",
            ".x::before { content: attr(data-l); }",
        )
        or _replace(
            root / "site" / "index.html",
            "</head>",
            '<link rel="stylesheet" href="style.css"></head>',
        )
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<span class="x" data-l="%s"></span></body>' % PERSONAL,
        )
    ),
)
check(
    "CSS-escaped import in a linked stylesheet fails closed",
    "CSS_EXTERNAL_STYLESHEET_UNVERIFIED"
    in _run(
        lambda root, _p, _r: _write(
            root / "site" / "style.css",
            r"@i\6d port url('nested.css');",
        )
        or _replace(
            root / "site" / "index.html",
            "</head>",
            '<link rel="stylesheet" href="style.css"></head>',
        )
    ),
)
check(
    "remote linked CSS fails closed",
    "CSS_EXTERNAL_STYLESHEET_UNVERIFIED"
    in _run(
        lambda root, _p, _r: _replace(
            root / "site" / "index.html",
            "</head>",
            '<link rel="stylesheet" href="https://example.invalid/style.css"></head>',
        )
    ),
)
check(
    "remote linked CSS requires an exact policy trust decision",
    _run(
        lambda root, policy, _r: _trust_remote_stylesheet(
            policy, "https://example.invalid/style.css"
        )
        or _replace(
            root / "site" / "index.html",
            "</head>",
            '<link rel="stylesheet" href="https://example.invalid/style.css"></head>',
        )
    )
    == set(),
)
check(
    "inline script body is inert when src is present",
    _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _write(root / "site" / "safe.js", "void 0;")
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script src="safe.js">document.querySelector(".x")'
            '.setAttribute("data-l","Codex")</script></body>',
        )
    )
    == set(),
)
check(
    "data-label reads and mutation words in literals remain benign",
    _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>var x=document.querySelector(".x");'
            'var a=x.getAttribute("data-l"),b=x.dataset.l;'
            'var example="setAttribute(\\\"data-l\\\", \\\"Codex\\\")";'
            'var pattern=/setAttribute\\(\\"data-l\\"\\)/;'
            '/* x.setAttribute("data-l","Codex") */</script></body>',
        )
    )
    == set(),
)
check(
    "finite safe computed mutation name remains provable",
    _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>["data-pos","data-content-id"].forEach(function(k){'
            'document.querySelector(".x").setAttribute(k,"safe")})</script></body>',
        )
    )
    == set(),
)
check(
    "mutation inside a template expression is blocked",
    "CSS_GENERATED_ATTRIBUTE_RUNTIME_MUTATION"
    in _run(
        lambda root, _p, _r: _add_data_label_contract(root)
        or _replace(
            root / "site" / "index.html",
            "</body>",
            '<script>`${document.querySelector(".x").setAttribute('
            '"data-l","Codex")}`</script></body>',
        )
    ),
)

print("public identity guard tests: %d/%d passed" % (sum(cases), len(cases)))
if __name__ == "__main__":
    raise SystemExit(0 if all(cases) else 1)
