# -*- coding: utf-8 -*-
"""Static affiliate-link safety check for the built site.

This checker deliberately does not request atth.me. Calling an affiliate URL
creates a network click, contaminates publisher reports, and can look like
self-clicking. Merchant availability must be verified against a direct,
non-tracking merchant URL maintained outside the affiliate redirect.

Exit 0: every published link has a valid AccessTrade shape.
Exit 1: malformed or non-HTTPS affiliate links were found.
Exit 2: the built site is missing, or a forbidden network flag was requested.
"""
import glob
import os
import re
import sys


SITE = "site"
HREF = re.compile(r'href=["\'](https?://atth\.me/[^"\']+)["\']', re.I)
VALID = re.compile(r"^https://atth\.me/(?:go/)?[0-9A-Za-z]+(?:\?[^\s]*)?$")


def main():
    if any(flag in sys.argv[1:] for flag in ("--http", "--live", "--network")):
        print("REFUSED: network-checking affiliate redirects creates synthetic clicks")
        return 2

    pages = sorted(glob.glob(os.path.join(SITE, "*.html")))
    if not pages:
        print("ERR: site/*.html not found; run build_site.py first")
        return 2

    occurrences = []
    for path in pages:
        with open(path, encoding="utf-8") as handle:
            for url in HREF.findall(handle.read()):
                occurrences.append((os.path.basename(path), url))

    malformed = [(page, url) for page, url in occurrences if not VALID.fullmatch(url)]
    unique = sorted({url.split("?", 1)[0] for _, url in occurrences})
    print(
        "checked %d built pages, %d affiliate placements, %d unique links"
        % (len(pages), len(occurrences), len(unique))
    )
    print("network requests: 0 (intentional anti-self-click guard)")

    if malformed:
        print("MALFORMED LINKS:")
        for page, url in malformed:
            print("  - %s: %s" % (page, url))
        return 1
    if not occurrences:
        print("WARN: no published affiliate links found")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
