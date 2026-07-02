# Traffic Monitor — สัญญาณรายช่อง (20260702-0908)
> ที่มา: metrics.csv (27 แถว) · ช่อง = prefix ของ source · metrics.csv = ยอด reach ฝั่งโซเชียล (กรอก/sync มือ) — ดูของจริงที่ section GA4 ด้านล่าง

| ช่อง | โพสต์ | views | clicks | quiz_start | conversion | CTR% | conv% |
|---|---|---|---|---|---|---|---|
| ig | 10 | 370 | 0 | 0 | 0 | 0.0 | 0.0 |
| fb | 17 | 0 | 0 | 0 | 0 | 0.0 | 0.0 |
| tiktok | 0 | n/a | n/a | n/a | n/a | – | – |
| pantip | 0 | n/a | n/a | n/a | n/a | – | – |
| threads | 0 | n/a | n/a | n/a | n/a | – | – |
| yt | 0 | n/a | n/a | n/a | n/a | – | – |
| pinterest | 0 | n/a | n/a | n/a | n/a | – | – |

รวม (metrics.csv): views=370 clicks=0 quiz_start=0 conversion=0

## GA4 (จริง)
funnel: quiz_start=4 -> quiz_complete=3 -> recommendation_view=1 -> affiliate_click=69

| source (GA4) | sessions | quiz_start | conversion |
|---|---|---|---|
| direct | 149 | 4 | 41 |
| fb | 64 | 2 | 18 |
| ig | 3 | 1 | 6 |
| pantip | 26 | 1 | 3 |
| threads | 14 | 0 | 1 |
| app | 1 | 0 | 0 |
| bing | 3 | 0 | 0 |
| cowork | 5 | 3 | 0 |
| test | 1 | 0 | 0 |
| tiktok | 2 | 0 | 0 |
| yt | 1 | 0 | 0 |

| หน้า (GA4 top) | views | conversion |
|---|---|---|
| /links | 110 | 26 |
| /kept-savings-2026 | 28 | 26 |
| /title-loan-2026 | 14 | 10 |
| /emergency-fund-2026 | 3 | 3 |
| /debt-consolidation-2026 | 9 | 2 |
| /personal-loan-2026 | 6 | 1 |
| /lifestyle-credit-card-2026 | 4 | 1 |
| / | 139 | 0 |

## Sales
sales: — (ยังไม่มีไฟล์ gumroad-sales.csv — เจ้าของ export CSV จาก Gumroad วางที่ automation-log/gumroad-sales.csv คอลัมน์ date,units,amount_thb)