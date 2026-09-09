# Traffic Monitor — สัญญาณรายช่อง (20260825-1409)
> ที่มา: metrics.csv (49 แถว) · ช่อง = prefix ของ source · metrics.csv = ยอด reach ฝั่งโซเชียล (กรอก/sync มือ) — ดูของจริงที่ section GA4 ด้านล่าง

| ช่อง | โพสต์ | views | clicks | quiz_start | legacy_intent* | CTR% | intent/click% |
|---|---|---|---|---|---|---|---|
| ig | 27 | 1517 | 0 | 0 | 0 | 0.0 | 0.0 |
| fb | 22 | 40 | 0 | 0 | 0 | 0.0 | 0.0 |
| tiktok | 0 | n/a | n/a | n/a | n/a | – | – |
| pantip | 0 | n/a | n/a | n/a | n/a | – | – |
| threads | 0 | n/a | n/a | n/a | n/a | – | – |
| yt | 0 | n/a | n/a | n/a | n/a | – | – |
| pinterest | 0 | n/a | n/a | n/a | n/a | – | – |

รวม (metrics.csv): views=1557 clicks=0 quiz_start=0 legacy_intent=0
_*legacy_intent อ่านจากคอลัมน์เดิม `conversion` ใน metrics.csv; ถือเป็นเพียง intent ไม่ใช่รายได้._

## GA4 observed intent — Decision Trust=UNTRUSTED
> bundle=INVALID_METADATA; capture=UNTRUSTED; current=UNTRUSTED
funnel: quiz_start=0 -> quiz_complete=0 -> recommendation_view=0 -> affiliate_click=6

| source (GA4) | sessions | quiz_start | affiliate_click (intent) |
|---|---|---|---|
| pantip | 14 | 0 | 4 |
| chatgpt | 12 | 0 | 2 |
| bing | 1 | 0 | 0 |
| direct | 67 | 0 | 0 |
| fb | 3 | 0 | 0 |
| threads | 2 | 0 | 0 |
| yt | 3 | 0 | 0 |

| หน้า (GA4 observed) | views | affiliate_click (intent) |
|---|---|---|
| /links | 14 | 2 |
| /bureau-blacklist-loan-2026 | 13 | 2 |
| /personal-loan-2026 | 5 | 1 |
| /insurance-compare-2026 | 1 | 1 |
| / | 73 | 0 |
| /debt-letter-kit | 11 | 0 |
| /debt-clinic-sam-2026 | 6 | 0 |
| /debt-health-check | 5 | 0 |

## Legacy manual commerce observation (not verified revenue)
legacy manual commerce observation: — (UNRECONCILED; excluded from verified revenue; ยังไม่มีแถวข้อมูล)