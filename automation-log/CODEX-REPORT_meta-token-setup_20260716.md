# Meta token setup helper — report (2026-07-16)

## Delivered

- `tools/meta_token_setup.py` is an interactive, standard-library-only helper for provisioning the six requested GitHub Actions secrets used by the Instagram and Facebook automations.
- It validates the short-lived Meta user token, exchanges it for a long-lived token, retrieves the target Page token, verifies the linked Instagram Business Account, and then stores the results as GitHub repository secrets.
- Secret values remain in process memory only. Token and app-secret prompts use hidden input; API/GitHub command output and Graph response bodies are suppressed; values are never written to repository files or logs. In the browser fallback, the script places one value at a time on the Windows clipboard and clears the clipboard at the end.

## Owner command

```powershell
py tools\meta_token_setup.py
```

## The three requested pastes

1. `SHORT_LIVED_USER_TOKEN` — in [Graph API Explorer](https://developers.facebook.com/tools/explorer/), select the Meta app, generate a User Token, and grant: `instagram_content_publish`, `instagram_basic`, `pages_show_list`, `pages_read_engagement`, and `pages_manage_posts`.
2. `FB_APP_ID` — from the selected app’s [Basic Settings page](https://developers.facebook.com/apps/) (open the app, then **Settings → Basic**).
3. `FB_APP_SECRET` — from that same app’s **Settings → Basic** page, using **Show** next to App Secret. The script hides this paste.

## GitHub CLI fallback

When `gh` is missing or `gh auth status` is not authenticated, the script opens the repository’s GitHub Actions Secrets page. It copies each secret value to the Windows clipboard one at a time, prints only its secret name, and waits for the owner to create/update that secret in the browser before continuing. It clears the clipboard after the final step and asks the owner to confirm the six secret names in the UI.

After successful setup, `ig-reels` runs daily at 20:00 Thailand time, and `fb-feed` runs daily at 15:00 Thailand time and automatically invokes `schedule_fb_batch2.py` when the Page token is present.

## Verification

The helper passed a compile-only check with an available Python launcher. The prescribed `py` launcher was not exposed in this sandbox’s `PATH`, so the check used the available Python executable instead. The interactive flow was not run and no network calls were made during verification.
