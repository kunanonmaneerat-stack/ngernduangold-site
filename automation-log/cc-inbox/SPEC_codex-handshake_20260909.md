# SPEC — Codex handshake test (Cowork → Codex, 9 Sep 2026)

This is a channel test. Do NOT change any file except the one output file named below.

## Do exactly this

1. Read `.system_control/policy.json`. Find the object `publication_control`.
2. Report, as plain facts you actually read (not from memory):
   - the value of `default_publication_authorized`
   - for each channel key under `publication_control`, its `publication_authorized` value
   - whether a key named `_lifted_20260909` exists, and if so quote its `date` and `by` fields verbatim
3. Report whether `forbidden_public_speakers` (under `public_identity`) contains the string `grok`. Answer only yes or no.
4. Report your own model name and the working directory you are running in.

## Output

Your final message must be at most 20 lines, in this exact shape:

```
HANDSHAKE: ok
default_publication_authorized = <value>
<channel> = <value>     (one line per channel)
_lifted_20260909 = <present|absent> date=<...> by=<...>
grok_in_forbidden_public_speakers = <yes|no>
model = <...>
cwd = <...>
```

## Rules

- Read only. Do not write, edit, delete, move or create any file in the repo.
- Do not run git. Do not push.
- If any value above cannot be read, write `UNKNOWN` for that line and add one line saying what you could not read and why. Do not guess, and do not report a missing value as `false`.
