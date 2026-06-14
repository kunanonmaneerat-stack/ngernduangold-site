# ngernduangold-site

Static Thai personal-finance affiliate site (เงินเดือนสมองทอง) — 23 articles + /links hub.

- Build: `SITE_BASE=https://ngernduangold.netlify.app SITE_GA=G-17PPE0M1B8 python3 build_site.py` -> ./site
- Deploy: Netlify git-connected (netlify.toml). Every push = auto build + publish.
- Link health: `python3 check_affiliate_links.py`
