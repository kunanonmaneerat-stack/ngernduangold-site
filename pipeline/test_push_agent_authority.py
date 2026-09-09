#!/usr/bin/env python3
"""Regression tests for push_agent's permanent local-only boundary."""

import push_agent


def main():
    original_guard = push_agent.guard_truncation
    original_verify = push_agent.verify_build
    push_agent.guard_truncation = lambda: []
    push_agent.verify_build = lambda: (70, [])
    try:
        commands = []

        def local_runner(cmd, cwd=push_agent.ROOT):
            commands.append(list(cmd))
            return 0, "quiz.html written"

        rc = push_agent.execute(runner=local_runner)
        if rc != 0 or commands != [[push_agent.sys.executable, "build_site.py"]]:
            raise AssertionError("default execution must only build locally")
        print("PASS default execution performs only a local build")

        for kwargs in (
            {"actor": "owner", "do_commit": True, "paths": ["build_site.py"]},
            {"actor": "owner", "do_commit": True, "do_push": True,
             "paths": ["build_site.py"]},
            {"actor": "codex", "do_commit": True, "paths": ["build_site.py"]},
        ):
            commands.clear()
            if push_agent.execute(runner=local_runner, **kwargs) != 2:
                raise AssertionError("all Git mutation modes must be blocked")
            if commands:
                raise AssertionError("blocked mutations must fail before build or Git")
        print("PASS owner string cannot enable commit")
        print("PASS owner string cannot enable push or deploy")
        print("PASS Codex cannot enable commit")

        source = push_agent.Path(push_agent.__file__).read_text(encoding="utf-8")
        for forbidden in ('["git", "add"', '["git", "commit"', '["git", "push"'):
            if forbidden in source:
                raise AssertionError("reachable Git mutator remains in push_agent")
        print("PASS source contains no Git mutator command")
    finally:
        push_agent.guard_truncation = original_guard
        push_agent.verify_build = original_verify

    print("push agent authority: 5/5 PASS")


if __name__ == "__main__":
    main()
