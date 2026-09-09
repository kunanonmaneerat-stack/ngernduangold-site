#!/usr/bin/env python3
"""Fail-closed reader for append-only legacy post-ledger identity bindings.

The historical post ledger is never rewritten.  A binding is a separately chained
receipt which names one physical JSONL line, hashes that exact row, and points to an
immutable source-evidence snapshot.  The reader applies the overlay atomically: one
invalid, duplicated, ambiguous, or tampered binding invalidates the whole overlay.

This module deliberately does not infer publication status.  It supplies only the
missing permanent-dedup identity and, for quarantined media, a non-reuse policy.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import urllib.parse


ZERO_SHA256 = "0" * 64
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
BINDING_ID_RE = re.compile(r"^plid-v1-[0-9]{6}$")
EVIDENCE_FIELD_RE = re.compile(
    r"^records\[evidence_id=([a-z0-9][a-z0-9._-]*)\]\.value$"
)
KNOWLEDGE_FIELD_RE = re.compile(
    r"^table\[id=(kn-[0-9]+)\]\.(threads_text|fb_text)$"
)
PAGE2_FIELD_RE = re.compile(r"^table\[id=(p2-[0-9]+)\]\.fb_text$")
LINE_RANGE_FIELD_RE = re.compile(r"^lines\[([0-9]+):([0-9]+)\]$")
LINE_BROADCAST_SECTION_FIELD_RE = re.compile(
    r"^section\[version=([AB])\]\.body$"
)
MANIFEST_FIELD_RE = re.compile(r"^items\[id=([^\]]+)\]$")
PUBLISHED_MEDIA_FIELD_RE = re.compile(r"^items\[content_id=([^\]]+)\]$")
PRIVATE_COMMITMENT_FIELD_RE = re.compile(
    r"^records\[commitment_id=(private-session-line-[0-9]{6})\]$"
)
PANTIP_PUBLIC_OBSERVATION_FIELD_RE = re.compile(
    r"^observations\[observation_id=(pantip-44168590-comment3)\]$"
)
FACEBOOK_GROUP_PUBLIC_OBSERVATION_FIELD_RE = re.compile(
    r"^observations\[observation_id=(facebook-group-2410303406132246-comment-2410314352797818)\]$"
)
FACEBOOK_PAGE_PUBLIC_OBSERVATION_FIELD_RE = re.compile(
    r"^observations\[observation_id=(facebook-page-1824608881851102-comment-1028158030069586)\]$"
)

FACEBOOK_STORY_UNRESOLVED_LINE = 39
FACEBOOK_STORY_REQUIRED_RECOVERY_EVIDENCE = (
    "stable Facebook Story object id and canonical Story permalink",
    "displayed Story publication timestamp matching 2026-07-19T13:03:00+07:00",
    "exact source-post id or Story-media SHA-256 tied to that Story object",
    "exact displayed Story text, or an explicit no-text observation tied to the same Story object",
)

TOP_KEYS = {
    "schema_version", "record_type", "binding_id", "previous_binding_sha256",
    "target", "source", "evidence_type", "identity", "reuse_policy",
    "binding_sha256",
}
SEAL_KEYS = {
    "schema_version", "record_type", "binding_count", "sealed_target_lines",
    "previous_record_sha256", "seal_sha256",
}
TARGET_KEYS = {"ledger_path", "line", "row_sha256"}
SOURCE_KEYS = {
    "path", "sha256", "field", "evidence_path", "evidence_sha256",
    "evidence_field",
}
IDENTITY_KEYS = {"kind", "value", "value_sha256"}
EVIDENCE_TOP_KEYS = {"schema_version", "created_at", "purpose", "records"}
EVIDENCE_RECORD_KEYS = {
    "evidence_id", "source_path", "source_sha256", "source_field", "value",
}
PUBLIC_OBSERVATION_EVIDENCE_VALUE_KEYS = {
    "observation_id", "observation_sha256",
}
CLIP_ROW_TYPES = {"claim", "now", "schedule", "manual", "video", "image"}
TEXT_ROW_TYPES = {"text", "comment", "story", "broadcast-scheduled"}

PRIVATE_COMMITMENT_SOURCE = (
    "automation-log/dedup-evidence/"
    "private-session-tool-input-commitments-v1.json"
)
PRIVATE_COMMITMENT_TOP_KEYS = {
    "schema_version", "created_at", "purpose", "extraction_contract", "records",
}
PRIVATE_COMMITMENT_VALUE_KEYS = {
    "commitment_id", "ledger_line", "task_id", "row_source", "channel",
    "target_date", "transcript_sha256", "transcript_size_bytes",
    "event_physical_line", "event_sha256", "json_field", "tool_name",
    "input_mode", "event_timestamp", "text_length", "text_sha256",
    "text_identity_sha1", "ledger_prefix_length", "ledger_prefix_sha256",
    "matching_event_count", "join_mode", "privacy_status",
}
PRIVATE_COMMITMENT_EXTRACTION_CONTRACT = (
    "claude-local-session-structured-tool-input-v1"
)
PRIVATE_COMMITMENT_PRIVACY_STATUS = (
    "SANITIZED_HASH_ONLY_NO_PATH_SESSION_ID_OR_TEXT"
)

PANTIP_PUBLIC_OBSERVATION_SOURCE = (
    "automation-log/dedup-evidence/"
    "pantip-public-observation-44168590-comment3-v1.json"
)
PANTIP_PUBLIC_OBSERVATION_TOP_KEYS = {
    "schema_version", "created_at", "purpose", "observation_contract",
    "observations",
}
PANTIP_PUBLIC_OBSERVATION_VALUE_KEYS = {
    "observation_id", "platform", "canonical_url", "topic_id", "root_id",
    "comment_id", "comment_no", "author_display", "author_profile_path",
    "displayed_time", "dom_selector", "observed_text_length",
    "observed_text_sha256", "observed_text", "ledger_line",
    "ledger_row_sha256", "observation_mode", "privacy_status",
}
PANTIP_PUBLIC_OBSERVATION_CONTRACT = "read-only-public-dom-observation-v1"
PANTIP_PUBLIC_OBSERVATION_PRIVACY_STATUS = (
    "PUBLIC_WEB_ONLY_NO_SESSION_ID_PRIVATE_PATH_OR_COOKIE"
)
PANTIP_PUBLIC_OBSERVATION_PIN = {
    "observation_id": "pantip-44168590-comment3",
    "platform": "pantip",
    "canonical_url": "https://pantip.com/topic/44168590/comment3",
    "topic_id": "44168590",
    "root_id": "119809716",
    "comment_id": "119809716",
    "comment_no": 3,
    "author_display": "สมาชิกหมายเลข 9373300",
    "author_profile_path": "/profile/9373300",
    "displayed_time": "20 กรกฎาคม เวลา 18:39 น.",
    "dom_selector": ".display-post-story",
    "observed_text_length": 2218,
    "observed_text_sha256": (
        "B767094C49F5D42A244DE50738A0C283"
        "220ACEAAD74DB9F444E9B2D30EE557FE"
    ),
    "ledger_line": 53,
    "ledger_row_sha256": (
        "31CFDB6FDE47B551CAEE69D84BE63B68"
        "D95A6668B76A294E6E75BE5B32AA51C0"
    ),
    "observation_mode": "read_only_public_dom",
    "privacy_status": PANTIP_PUBLIC_OBSERVATION_PRIVACY_STATUS,
}

FACEBOOK_GROUP_PUBLIC_OBSERVATION_SOURCE = (
    "automation-log/dedup-evidence/"
    "facebook-group-public-observation-2410314352797818-v1.json"
)
FACEBOOK_GROUP_PUBLIC_OBSERVATION_TOP_KEYS = {
    "schema_version", "created_at", "purpose", "observation_contract",
    "observations",
}
FACEBOOK_GROUP_PUBLIC_OBSERVATION_VALUE_KEYS = {
    "observation_id", "platform", "target_post_url", "stable_comment_url",
    "group_id", "post_id", "actor_display", "actor_profile_id", "comment_id",
    "displayed_time", "observed_text_length", "observed_text_sha256",
    "observed_text", "ledger_line", "ledger_row_sha256", "observation_mode",
    "privacy_status",
}
FACEBOOK_GROUP_PUBLIC_OBSERVATION_CONTRACT = (
    "read-only-public-facebook-comment-observation-v1"
)
FACEBOOK_GROUP_PUBLIC_OBSERVATION_PRIVACY_STATUS = (
    "PUBLIC_WEB_ONLY_NO_SESSION_ID_PRIVATE_PATH_OR_COOKIE"
)
FACEBOOK_GROUP_PUBLIC_OBSERVATION_PIN = {
    "observation_id": (
        "facebook-group-2410303406132246-comment-2410314352797818"
    ),
    "platform": "facebook",
    "target_post_url": (
        "https://www.facebook.com/groups/1036176276878306/"
        "posts/2410303406132246/"
    ),
    "stable_comment_url": (
        "https://www.facebook.com/groups/1036176276878306/"
        "posts/2410303406132246/?comment_id=2410314352797818"
    ),
    "group_id": "1036176276878306",
    "post_id": "2410303406132246",
    "actor_display": "เงินเดือนสมองทอง",
    "actor_profile_id": "100029060247015",
    "comment_id": "2410314352797818",
    "displayed_time": "5 สัปดาห์",
    "observed_text_length": 657,
    "observed_text_sha256": (
        "CE2695AFE405DE203BB2BD0D823D7BCA"
        "1012035629236D2EDF19BB258145CF12"
    ),
    "ledger_line": 45,
    "ledger_row_sha256": (
        "4D62E6C5C4C889F46C1D791F549E2649"
        "24634E2BC73B19D76AB51ABF2F089313"
    ),
    "observation_mode": "read_only_public_dom",
    "privacy_status": FACEBOOK_GROUP_PUBLIC_OBSERVATION_PRIVACY_STATUS,
}

FACEBOOK_PAGE_PUBLIC_OBSERVATION_SOURCE = (
    "automation-log/dedup-evidence/"
    "facebook-page-public-observation-1028158030069586-v1.json"
)
FACEBOOK_PAGE_PUBLIC_OBSERVATION_TOP_KEYS = {
    "schema_version", "created_at", "purpose", "observation_contract",
    "observations",
}
FACEBOOK_PAGE_PUBLIC_OBSERVATION_VALUE_KEYS = {
    "observation_id", "platform", "resolved_parent_url", "page_actor",
    "page_id", "post_id", "comment_id", "displayed_time",
    "rendered_text_length", "rendered_text_sha256", "rendered_text",
    "normalized_merchant_link", "link_resolution_mode", "ledger_line",
    "ledger_row_sha256", "observation_mode", "privacy_status",
}
FACEBOOK_PAGE_PUBLIC_OBSERVATION_CONTRACT = (
    "read-only-public-facebook-comment-and-link-observation-v1"
)
FACEBOOK_PAGE_PUBLIC_OBSERVATION_PRIVACY_STATUS = (
    "PUBLIC_WEB_ONLY_NO_SESSION_ID_PRIVATE_PATH_COOKIE_OR_TRANSIENT_FBCLID"
)
FACEBOOK_PAGE_PUBLIC_OBSERVATION_PIN = {
    "observation_id": (
        "facebook-page-1824608881851102-comment-1028158030069586"
    ),
    "platform": "facebook",
    "resolved_parent_url": (
        "https://www.facebook.com/100029060247015/posts/1824608881851102/"
    ),
    "page_actor": "เงินเดือนสมองทอง",
    "page_id": "100029060247015",
    "post_id": "1824608881851102",
    "comment_id": "1028158030069586",
    "displayed_time": "3 สัปดาห์",
    "rendered_text_length": 137,
    "rendered_text_sha256": (
        "1716C3BDC6EDB6C29A54254E09DD9F6D"
        "CE4C6573B75318BBB2F62301D7EB77BF"
    ),
    "normalized_merchant_link": (
        "https://ngernduangold.com/debt-calculator"
        "?utm_source=fb&utm_medium=comment"
    ),
    "link_resolution_mode": "decoded_redirect_parameter_without_navigation",
    "ledger_line": 109,
    "ledger_row_sha256": (
        "04860712923DBDABF22E4B658BE0A64F"
        "DE7C70979781E579DD16559DD09CBB6A"
    ),
    "observation_mode": "read_only_public_dom",
    "privacy_status": FACEBOOK_PAGE_PUBLIC_OBSERVATION_PRIVACY_STATUS,
}

# These are privacy-preserving commitments, not session identifiers or raw text.
# Each tuple was reproduced from one stable local Claude/Cowork transcript by
# ``tools/build_private_session_identity_patch.py``.  Keeping the exact hashes in
# code makes this a narrow recovery contract: editing and resealing the JSON files
# cannot silently redirect a binding to another private event.
PRIVATE_SESSION_LINE_CONTRACT = {
    27: {'task_id': 'fb-comment-catchup-tonight', 'row_source': 'fb-comment-catchup-20260718', 'channel': 'facebook', 'target_date': '2026-07-18', 'transcript_sha256': 'D902D90A3075BDFD0A3EE036E60C73C71C7F4FC29CA91BDCF1C28DF352ADF2C9', 'transcript_size_bytes': 20100311, 'event_physical_line': 153, 'event_sha256': 'FDF4CA86A61BB6981A1C722338B42429EAA4A63A368A6C9285AAC259412D7918', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__Windows-MCP__Clipboard', 'input_mode': 'clipboard_set', 'event_timestamp': '2026-07-17T18:00:15.027Z', 'text_length': 142, 'text_sha256': '8DA764FA60DCDBC7668BFD9F2E47B29C265360BDB715642E7F08DBB781993605', 'text_identity_sha1': '2c9889ccad159f15ce294f1f8c0674b338cb8d9f'},
    30: {'task_id': 'ngernduangold-ig-comment-cta', 'row_source': 'ig-comment-cta', 'channel': 'instagram', 'target_date': '2026-07-18', 'transcript_sha256': '27EFAE6A23E897C9251823955A79CEFED4BFC31E0DE836CB127DC102735D51EA', 'transcript_size_bytes': 2640519, 'event_physical_line': 93, 'event_sha256': 'A406F065C4589FDA29A142BEC9CA28EE21288AF474D6B1B98C917C3D496083EE', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-18T12:37:58.568Z', 'text_length': 53, 'text_sha256': '3C79929DF6F767DEFEE7A605295D74FBAF28F0927A65211C3EBE948E5EBF3FD0', 'text_identity_sha1': '0dc147ea168c166897c0bfb1ca08d9582100b4c3'},
    32: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-07-18', 'transcript_sha256': 'B05AB5FA7CC9CC15FA572F82FF07E4CB898DE0EAD3D647D5C1B1DBF3155A5D85', 'transcript_size_bytes': 2664029, 'event_physical_line': 95, 'event_sha256': '2B7D80D43D0D77E772F78B65B12B238BB882C73D8ABF019DDC200D5437AF0D5D', 'json_field': 'message.content[0].input.actions[2].input.text', 'tool_name': 'mcp__claude-in-chrome__browser_batch', 'input_mode': 'type', 'event_timestamp': '2026-07-18T14:36:38.362Z', 'text_length': 137, 'text_sha256': '61F0903562C8C9C7B42E0596F60E76763531374F425C22D1D5FD257AB6136E93', 'text_identity_sha1': '624e9c2adae44db8618dcbab6484ef6e6815da33'},
    49: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-07-19', 'transcript_sha256': 'B3F14C7711DACC8C605230FF5CDAF9CB51947D11E11A2C3DFFE054D34E5A0A47', 'transcript_size_bytes': 1948043, 'event_physical_line': 77, 'event_sha256': '26D2195E606C6C3C1F5ED1C475101B1362560CECF59F957017ED412EE4D7E05A', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-19T14:34:46.685Z', 'text_length': 151, 'text_sha256': '79DF350ACA520150144394B1A9CF96760A278AF79DC852B1D49CAC82B9B2A48C', 'text_identity_sha1': '31cbdb49e0476f0fd2045271c5891ccb6bcd6a38'},
    56: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-07-20', 'transcript_sha256': '523C5AA905C385746B609CFF51E1932DE48B9A88F3A8FB0FFB58B7961A979F16', 'transcript_size_bytes': 2213563, 'event_physical_line': 74, 'event_sha256': '76AE1FD923DBA7ED17B7E5766CD96F8D15DEF5C3F6AC405C95F7611D94CE3480', 'json_field': 'message.content[0].input.actions[3].input.text', 'tool_name': 'mcp__claude-in-chrome__browser_batch', 'input_mode': 'type', 'event_timestamp': '2026-07-20T14:36:48.234Z', 'text_length': 123, 'text_sha256': '63F99D8F1E0B57331C36D61495D19855F52B0B53B60F12C36D1129245818F7D7', 'text_identity_sha1': '5d104b344a8d65048f10ce36607cc9e16e4321c2'},
    71: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-07-23', 'transcript_sha256': '75877BAF821D20E1CF60543ADF241E5033DFD2A25C251CE5042DB61CF60F7D71', 'transcript_size_bytes': 1793810, 'event_physical_line': 81, 'event_sha256': '5CA8DF84490D6DE9FDAFAEB2DC7B9CB6D1D2B55D6CDC52B77BE8E8E0B0554833', 'json_field': 'message.content[0].input.actions[3].input.text', 'tool_name': 'mcp__claude-in-chrome__browser_batch', 'input_mode': 'type', 'event_timestamp': '2026-07-23T14:36:18.770Z', 'text_length': 148, 'text_sha256': '2B77E279D344B39E86ADD7DADCCF5F612E2313F46DDB8385FA8622FDB3E67C06', 'text_identity_sha1': '62d8e08e3846f45d52459afaacc9b590d9e69467'},
    79: {'task_id': 'ngernduangold-ig-comment-cta', 'row_source': 'ig-comment-cta', 'channel': 'instagram', 'target_date': '2026-07-24', 'transcript_sha256': '592F251EFAA5F7FB3C885C966DCC40F27C60F8589E1A336AF8D10E874F9552E6', 'transcript_size_bytes': 1722976, 'event_physical_line': 94, 'event_sha256': 'FF108F8676C0D3ABEE2AAF3280E8A770D4B7516248DC3B1ABF4C94A918391F58', 'json_field': 'message.content[0].input.actions[2].input.text', 'tool_name': 'mcp__claude-in-chrome__browser_batch', 'input_mode': 'type', 'event_timestamp': '2026-07-24T14:55:50.566Z', 'text_length': 61, 'text_sha256': '9603ED90ACC5002E3AE797233D0399B990CCF9F19343AEB803C436507C40497B', 'text_identity_sha1': '27a48d84ea2e51322f1391f2c61251b5eb307c3e'},
    88: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-07-25', 'transcript_sha256': '97A999D89938FEF91277B7DA5E0DEBE77B8869C2071A2BA7733863FEE9ABE1F7', 'transcript_size_bytes': 2622911, 'event_physical_line': 110, 'event_sha256': '7B4C1648BA015999E4D37F109E74963F2526E3FFC18FD77D959428534CC4A36E', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-25T14:37:05.214Z', 'text_length': 153, 'text_sha256': 'F1DA8022D1306993F58590CAEF987DA8B8B0AB78D2A5182D51BBE58A7BDDD982', 'text_identity_sha1': 'eaa557538f75f96a02a2e68b2745d2b5a8e942f1'},
    95: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-07-26', 'transcript_sha256': '5F96BB07B2569FCF6C318E1AF46BDB026C98E7D0CBE60EBDC2A792DF834B8ECD', 'transcript_size_bytes': 2605580, 'event_physical_line': 90, 'event_sha256': '4B03F2ECC0C37696AE47585061D11D1B9DF9D79EBF2F393CA15718A1C73B91F1', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-26T14:36:45.599Z', 'text_length': 119, 'text_sha256': '6902F4B26003779EFE7E8EDB5F60A1D6ECAE1BBF0DE25598C926047A3CC85541', 'text_identity_sha1': '0be7d302b989e49c2b62a1997d7477ab38faeeb4'},
    114: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-07-31', 'transcript_sha256': '6525D706E9076E58EA0422AA37A4AED664DED2174285A69E81D28A5B4CD1D74A', 'transcript_size_bytes': 2046302, 'event_physical_line': 66, 'event_sha256': '6794FA24EC0768C9F53E6066BCAF3A7C4018C7CE76140838F0EBBE274E38F57E', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-31T14:34:26.880Z', 'text_length': 144, 'text_sha256': 'ECA244DE5D4DE44549248752AF08BD9A855CCECB5E38306B34811B5716E0FB69', 'text_identity_sha1': '5bd892e1a03c2adbb52b7cf354f816e90b39b723'},
    121: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-08-01', 'transcript_sha256': 'A26B8CC9EF3AE1594881134B7E8227E0C3E59645BFA5A697767509A8FE150CE7', 'transcript_size_bytes': 1641066, 'event_physical_line': 50, 'event_sha256': '140DBA935127F11D4DBA20BF25F325FF28B1D020E2705EDE220E5746DE69B4EF', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-08-01T14:34:12.495Z', 'text_length': 133, 'text_sha256': '8BD28663D13C2FB110A27183319734542BD7373A197F78DC1C0A22250FDB5055', 'text_identity_sha1': '3192836bb198a703128bd87d521f6c48fa19a207'},
    175: {'task_id': 'ngernduangold-fb-page-comment-link', 'row_source': 'fb-comment-daily', 'channel': 'facebook', 'target_date': '2026-08-14', 'transcript_sha256': '7DC7E2ABBF6B59F95F8F9AC124F7DC7D7D02F5987DE07B9B96A0CA0EEB082E8B', 'transcript_size_bytes': 2256648, 'event_physical_line': 85, 'event_sha256': '9556F7FB18D3DFD548B89190DF76517BC794AAB887DB3EE5E769D484234BF776', 'json_field': 'message.content[0].input.actions[4].input.text', 'tool_name': 'mcp__claude-in-chrome__browser_batch', 'input_mode': 'type', 'event_timestamp': '2026-08-14T14:35:05.717Z', 'text_length': 155, 'text_sha256': 'C13C79FDDF5280BA5AE9ADE503D16DBFFE22192D6913498EBE801B074634B008', 'text_identity_sha1': '27f5b788187946a99183ddc15e2c6b698079218d'},
    31: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-18', 'transcript_sha256': '7ED03B633FF70807BD3B7B9C33385E6F1D5D4DFF4CB625A6E047B2B2084ACD00', 'transcript_size_bytes': 2486511, 'event_physical_line': 122, 'event_sha256': '3D8ADD1799B38CC818AB2C2F9058DABCC09AEFA29FA4C899DB2040FA2EBF2E74', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-18T14:29:25.010Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    47: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-19', 'transcript_sha256': '1F8FA77A8E7F418D4B83E4CF3DC7A5DECAAEAB7F48AFD39697E0F897590E8862', 'transcript_size_bytes': 3681570, 'event_physical_line': 80, 'event_sha256': 'C0F9237E5EB421D08BB6231073D2EBB33B56AA7B20EBE78AA8ABFA290CA5F030', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-19T14:27:41.960Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    55: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-20', 'transcript_sha256': 'CD0CE8013E876F1C5F455BE7DC87D98DC1ABA2E39C9CA6D2206CA9F6905ED930', 'transcript_size_bytes': 2944763, 'event_physical_line': 80, 'event_sha256': 'EE81528F89165987C91372F8A2E41DC56BCD86D0A474F96EA8324E4C7D25D927', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-20T14:29:50.785Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    62: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-21', 'transcript_sha256': 'EF3DFA37C093E1E19B885C5BB736E4EA2A4CAC55A59ED531E274CF5669500B08', 'transcript_size_bytes': 2840334, 'event_physical_line': 117, 'event_sha256': 'C2AD4A6315FEB92AEAB3A176B3D56D522DC816D3AB96E00D2FB3E3BB67F7B171', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-21T14:30:11.566Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    63: {'task_id': 'ngernduangold-ig-comment-cta', 'row_source': 'ig-comment-cta', 'channel': 'instagram', 'target_date': '2026-07-21', 'transcript_sha256': '2B8AD112041CD6D50FEE137EF15985619BB24B3D128DB086C75A97D7F839C24A', 'transcript_size_bytes': 2959182, 'event_physical_line': 90, 'event_sha256': 'EADCD337289468D4FDBA19EF8DA43A24E0576922D55B8BD48448E3B172EDDD38', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-21T14:57:20.977Z', 'text_length': 81, 'text_sha256': '5F60EF2538593C40F633F14829BF05E5D92B4B64FCC1F4900A86B6BCEFE21853', 'text_identity_sha1': 'aed0406157eb7257c3bf86c7906a6822f8b86e79'},
    70: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-23', 'transcript_sha256': 'DFA1204307C9D2DC6C7CBF082337C9F1CADA506E10140197523F60911DE79102', 'transcript_size_bytes': 2267303, 'event_physical_line': 101, 'event_sha256': '0F62F908051C6916CF947A272B8512C1FAEDCA6E16BE7CC5348AE4443D00EF5C', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-23T14:29:02.912Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    78: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-24', 'transcript_sha256': 'AE76FFCE58A88879FD1C5E969BF2003015082E217B5719082F4925ABAE955002', 'transcript_size_bytes': 3137884, 'event_physical_line': 126, 'event_sha256': 'C970BDC91DEAEF54A2C4868667CA6759F3B560ECBD4150FB3F1996C66E79C5BA', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-24T14:30:09.901Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    87: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-25', 'transcript_sha256': '8FF3F522DD0DFD08B5714C04C8276C9CD5F8EEB3801343D89CC3D17A1450E8E3', 'transcript_size_bytes': 2927043, 'event_physical_line': 93, 'event_sha256': '4BE0E1B27D7E80637F257DCA4952C79810ED5F6631471F59025B48814E8D14BB', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-25T14:28:07.464Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    89: {'task_id': 'ngernduangold-ig-comment-cta', 'row_source': 'ig-comment-cta', 'channel': 'instagram', 'target_date': '2026-07-25', 'transcript_sha256': '3B586C066C9DE9D789DB2E84EE164BE350B8405E91ADC521217B72C3918E5B87', 'transcript_size_bytes': 1620710, 'event_physical_line': 52, 'event_sha256': '4610ECFC0D58CED7697A58940B14886BE0A943732C99D6BDAC52F2CC30C4AE3C', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-25T14:53:20.680Z', 'text_length': 81, 'text_sha256': '5F60EF2538593C40F633F14829BF05E5D92B4B64FCC1F4900A86B6BCEFE21853', 'text_identity_sha1': 'aed0406157eb7257c3bf86c7906a6822f8b86e79'},
    94: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-26', 'transcript_sha256': '20A28844598A4C1452FB93083468D7D2EBB2B79D82E5501865A75D3B02646F2A', 'transcript_size_bytes': 4158764, 'event_physical_line': 81, 'event_sha256': '966429375DE8F15281ED26E68A2A43C15E1562AE3C9A5D209E65D739BBF070D5', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-26T14:29:41.343Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    103: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-30', 'transcript_sha256': '80B108D0CD331031C917A8F16104AA96704FDDA9D1FDE9C9D27326580A98B262', 'transcript_size_bytes': 1567821, 'event_physical_line': 78, 'event_sha256': '72EF30C0E470C3E71718B2079D38B7B8730B1A9E40BC4284658D680635CF9C3B', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-30T14:32:01.411Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    113: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-07-31', 'transcript_sha256': '7E7165135CFC670C90C8BF161964B4E4F4F38E3556806A280A2082ABD901AA94', 'transcript_size_bytes': 3207428, 'event_physical_line': 76, 'event_sha256': '8FA3193A69A228AEF15A10EA48E416217B17DE914DFD0CC590D88D87B23CF541', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-07-31T14:28:02.814Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    120: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-08-01', 'transcript_sha256': 'EB164C59755BFD69668BC3F89ED54D528CF1941CD298CE444A0FB8669A70427D', 'transcript_size_bytes': 4598656, 'event_physical_line': 79, 'event_sha256': 'C20FAD17645AF95772771849AE47362EEF4938C205D96956FE164F105685BEF9', 'json_field': 'message.content[0].input.actions[2].input.text', 'tool_name': 'mcp__claude-in-chrome__browser_batch', 'input_mode': 'type', 'event_timestamp': '2026-08-01T14:30:04.371Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    129: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-08-06', 'transcript_sha256': '1F108A699C9980549F74CF992A21FC2017218758A0116E13DC9F08334750935F', 'transcript_size_bytes': 4395997, 'event_physical_line': 64, 'event_sha256': '00769ADC9C644EC6BCB35043405A56F36A421C1BF897D7D28BC8B6814A9D5245', 'json_field': 'message.content[0].input.actions[2].input.text', 'tool_name': 'mcp__claude-in-chrome__browser_batch', 'input_mode': 'type', 'event_timestamp': '2026-08-06T14:28:02.874Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    137: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-08-07', 'transcript_sha256': '6D87E6D17E0D15E9AB5F1A9550F0CCE03ACD7FDDC49D1EF08A870F202169462A', 'transcript_size_bytes': 4382821, 'event_physical_line': 109, 'event_sha256': '9CDE9340D2A966950FCCB870EC85871C5554FAE9694398739729424FCD12865B', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-08-07T14:28:48.858Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
    155: {'task_id': 'ngernduangold-yt-comment-link', 'row_source': 'yt-comment-link-auto', 'channel': 'youtube', 'target_date': '2026-08-09', 'transcript_sha256': '46E6BD15012AC84C5DA052425DE8A560818D028CF11F4CABF7071867055E0979', 'transcript_size_bytes': 3212419, 'event_physical_line': 87, 'event_sha256': 'AFFFD9778B4E96D3F328D4A48935FB73E187584CB2697450EF94F9993C0DF973', 'json_field': 'message.content[0].input.text', 'tool_name': 'mcp__claude-in-chrome__computer', 'input_mode': 'type', 'event_timestamp': '2026-08-09T14:28:58.711Z', 'text_length': 137, 'text_sha256': '56F2E19EE93FBCEC3FBC5A95E1D258A3A04AF3A9AAEAC432DD3CFA1636A97B3C', 'text_identity_sha1': '90e43a4ddc4d3da3f72e17d10fd38f153e0741bc'},
}

PRIVATE_SESSION_MATCH_COUNTS = {63: 2, 129: 2}
PRIVATE_SESSION_MAX_LAG_SECONDS = {121: 3 * 60 * 60}
PRIVATE_SESSION_ZERO_PREFIX_LINES = frozenset({
    31, 47, 55, 62, 70, 78, 87, 94, 103, 113, 120, 129, 137, 155,
})


class IdentityBindingError(ValueError):
    """A binding overlay cannot be proven trustworthy."""


def _strict_json_loads(value: str):
    def reject_constant(token: str):
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicate_keys(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    document = json.loads(
        value,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    require_finite(document)
    return document


def _canonical_json(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def binding_sha256(record: dict) -> str:
    payload = dict(record)
    payload.pop("binding_sha256", None)
    return sha256_bytes(_canonical_json(payload))


def seal_sha256(record: dict) -> str:
    payload = dict(record)
    payload.pop("seal_sha256", None)
    return sha256_bytes(_canonical_json(payload))


def identity_value_sha256(value: str) -> str:
    return sha256_bytes(str(value).encode("utf-8"))


def _normalize_text(text: str) -> str:
    cleaned = re.sub(
        r"https?://\S+|www\.\S+|atth\.me/\S+", "", str(text or "")
    )
    return "".join(ch for ch in cleaned.casefold() if ch.isalnum())


def _text_hash(text: str) -> str:
    return hashlib.sha1(_normalize_text(text).encode("utf-8")).hexdigest()


def _norm_channel(channel: str) -> str:
    aliases = {
        "youtube": "yt", "instagram": "ig", "facebook": "fb",
        "facebook_feed": "fb_feed", "fbfeed": "fb_feed", "tt": "tiktok",
    }
    value = str(channel or "").strip().casefold()
    return aliases.get(value, value)


def _full_channel(channel: str) -> str:
    return {"fb": "facebook", "ig": "instagram", "yt": "youtube"}.get(
        _norm_channel(channel), _norm_channel(channel)
    )


def _stable_bytes(path: Path) -> bytes:
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise IdentityBindingError(f"cannot read {path}: {exc}") from exc
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise IdentityBindingError(f"file changed while reading: {path}")
    return raw


def _strict_relative(value: str, label: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    pure = PurePosixPath(text)
    if not text or pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise IdentityBindingError(f"{label} must be a canonical repo-relative path")
    canonical = pure.as_posix()
    if canonical != text:
        raise IdentityBindingError(f"{label} is not canonical: {text!r}")
    return canonical


def _inside_root(root: Path, relative: str, label: str) -> Path:
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise IdentityBindingError(f"{label} escapes repository root") from exc
    return target


def _repo_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise IdentityBindingError("target ledger is outside repository root") from exc
    return relative.as_posix()


def _parse_jsonl(raw: bytes, label: str) -> list[dict]:
    if raw and not raw.endswith(b"\n"):
        raise IdentityBindingError(f"{label} lacks final newline commit boundary")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IdentityBindingError(f"{label} is not UTF-8: {exc}") from exc
    records = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            raise IdentityBindingError(f"{label} has blank row at line {line_no}")
        try:
            record = _strict_json_loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise IdentityBindingError(
                f"{label} malformed JSON at line {line_no}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise IdentityBindingError(f"{label} line {line_no} is not an object")
        records.append(record)
    return records


def _require_keys(value: dict, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise IdentityBindingError(
            f"{label} keys are not exact: expected={sorted(expected)} actual={actual}"
        )


def _require_sha(value, label: str) -> str:
    text = str(value or "")
    if not SHA256_RE.fullmatch(text):
        raise IdentityBindingError(f"{label} must be uppercase SHA-256")
    return text


def _load_evidence(
    root: Path, source: dict, cache: dict[tuple[str, str], dict]
) -> tuple[dict, dict]:
    evidence_path = _strict_relative(source["evidence_path"], "source.evidence_path")
    expected_hash = _require_sha(
        source["evidence_sha256"], "source.evidence_sha256"
    )
    key = (evidence_path, expected_hash)
    if key not in cache:
        full = _inside_root(root, evidence_path, "source.evidence_path")
        raw = _stable_bytes(full)
        actual_hash = sha256_bytes(raw)
        if actual_hash != expected_hash:
            raise IdentityBindingError(
                f"source evidence hash mismatch for {evidence_path}"
            )
        try:
            payload = _strict_json_loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise IdentityBindingError(
                f"source evidence is not valid UTF-8 JSON: {evidence_path}"
            ) from exc
        _require_keys(payload, EVIDENCE_TOP_KEYS, "source evidence")
        if payload["schema_version"] != 1:
            raise IdentityBindingError("source evidence schema_version must be 1")
        if not isinstance(payload["created_at"], str) or not payload["created_at"]:
            raise IdentityBindingError("source evidence created_at is missing")
        if not isinstance(payload["purpose"], str) or not payload["purpose"]:
            raise IdentityBindingError("source evidence purpose is missing")
        records = payload["records"]
        if not isinstance(records, list) or not records:
            raise IdentityBindingError("source evidence records must be non-empty")
        by_id = {}
        for number, record in enumerate(records, 1):
            _require_keys(record, EVIDENCE_RECORD_KEYS, f"source evidence record {number}")
            evidence_id = str(record["evidence_id"] or "")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", evidence_id):
                raise IdentityBindingError("source evidence_id is invalid")
            if evidence_id in by_id:
                raise IdentityBindingError(
                    f"ambiguous duplicate source evidence_id: {evidence_id}"
                )
            record["source_path"] = _strict_relative(
                record["source_path"], "evidence source_path"
            )
            _require_sha(record["source_sha256"], "evidence source_sha256")
            if not isinstance(record["source_field"], str) or not record["source_field"]:
                raise IdentityBindingError("evidence source_field is missing")
            by_id[evidence_id] = record
        cache[key] = by_id
    by_id = cache[key]
    selector = str(source["evidence_field"] or "")
    match = EVIDENCE_FIELD_RE.fullmatch(selector)
    if not match:
        raise IdentityBindingError("source.evidence_field selector is invalid")
    evidence_id = match.group(1)
    record = by_id.get(evidence_id)
    if record is None:
        raise IdentityBindingError(
            f"source.evidence_field did not resolve: {evidence_id}"
        )
    return record, record["value"]


def _parse_date(value, label: str) -> str:
    try:
        return datetime.date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError) as exc:
        raise IdentityBindingError(f"{label} is not an ISO date") from exc


def _source_bytes(root: Path, source: dict) -> bytes:
    """Read and hash the cited source itself, not only its evidence snapshot."""
    path = _inside_root(root, source["path"], "source.path")
    raw = _stable_bytes(path)
    actual = sha256_bytes(raw)
    expected = _require_sha(source["sha256"], "source.sha256")
    if actual != expected:
        raise IdentityBindingError(f"source hash mismatch for {source['path']}")
    return raw


def _markdown_table_value(raw: bytes, source: dict, value: dict) -> str:
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise IdentityBindingError("markdown source is not UTF-8") from exc
    knowledge = KNOWLEDGE_FIELD_RE.fullmatch(source["field"])
    page2 = PAGE2_FIELD_RE.fullmatch(source["field"])
    if not knowledge and not page2:
        raise IdentityBindingError("markdown table source selector is invalid")
    expected_id = (knowledge or page2).group(1)
    matches = []
    for line in lines:
        if not line.startswith("| 2026-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        expected_cells = 5 if knowledge else 4
        if len(cells) != expected_cells or cells[1] != expected_id:
            continue
        if knowledge:
            field = (knowledge.group(2))
            cell = cells[3] if field == "threads_text" else cells[4]
        else:
            cell = cells[3]
        matches.append((cells[0], cell.replace("<br>", "\n")))
    if len(matches) != 1:
        raise IdentityBindingError("markdown table selector is missing or ambiguous")
    date, exact_text = matches[0]
    if date != value["date"] or expected_id != value["id"]:
        raise IdentityBindingError("markdown table id/date does not match evidence")
    return exact_text


def _line_range_value(raw: bytes, source: dict) -> str:
    selector = LINE_RANGE_FIELD_RE.fullmatch(source["field"])
    if not selector:
        raise IdentityBindingError("line-range source selector is invalid")
    start, end = map(int, selector.groups())
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise IdentityBindingError("line-range source is not UTF-8") from exc
    if start < 1 or end < start or end > len(lines):
        raise IdentityBindingError("line-range source selector is out of bounds")
    exact_text = "\n".join(lines[start - 1:end]).strip()
    if not exact_text:
        raise IdentityBindingError("line-range source text is empty")
    return exact_text


def _line_broadcast_section_value(raw: bytes, source: dict) -> str:
    """Extract one exact, uniquely named broadcast version from the source draft."""
    selector = LINE_BROADCAST_SECTION_FIELD_RE.fullmatch(source["field"])
    if not selector:
        raise IdentityBindingError("LINE broadcast source selector is invalid")
    version = selector.group(1)
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise IdentityBindingError("LINE broadcast source is not UTF-8") from exc

    heading = f"## เวอร์ชัน {version}"
    starts = [number for number, line in enumerate(lines) if line == heading]
    if len(starts) != 1:
        raise IdentityBindingError(
            "LINE broadcast version heading is missing or ambiguous"
        )
    start = starts[0] + 1
    end = next(
        (number for number in range(start, len(lines))
         if lines[number].startswith("## ")),
        len(lines),
    )
    exact_text = "\n".join(lines[start:end]).strip()
    if not exact_text:
        raise IdentityBindingError("LINE broadcast version body is empty")
    return exact_text


def _validate_exact_text_join(row: dict, identity: dict, value: dict,
                              exact_text: str) -> dict:
    required = {"id", "date", "channel", "text_sha256", "join_mode"}
    if set(value) != required:
        raise IdentityBindingError("exact-text evidence value keys are not exact")
    expected_sha = sha256_bytes(exact_text.encode("utf-8"))
    if _require_sha(value["text_sha256"], "exact text SHA-256") != expected_sha:
        raise IdentityBindingError("exact source text hash does not match evidence")
    expected_hash = _text_hash(exact_text)
    if identity["kind"] != "text_hash" or identity["value"] != expected_hash:
        raise IdentityBindingError("text identity is not recomputed from exact source")
    if str(row.get("type") or "").casefold() not in TEXT_ROW_TYPES:
        raise IdentityBindingError("exact-text binding targets a non-text row")
    if _full_channel(row.get("channel")) != value["channel"]:
        raise IdentityBindingError("exact-text channel does not match target row")
    prefix = str(row.get("text_first80") or "")
    join_mode = value["join_mode"]
    prefix_matches = exact_text.startswith(prefix)
    if join_mode == "whitespace_equivalent_prefix":
        prefix_matches = re.sub(r"\s+", "", exact_text).startswith(
            re.sub(r"\s+", "", prefix)
        )
    elif join_mode != "exact_prefix":
        raise IdentityBindingError("exact-text join_mode is invalid")
    if len(prefix) < 40 or not prefix_matches:
        raise IdentityBindingError("exact source text does not match target prefix")
    if _parse_date(row.get("ts"), "target timestamp") != _parse_date(
        value["date"], "exact-text date"
    ):
        raise IdentityBindingError("exact-text date does not match target row")
    return {
        "kind": "text_hash", "value": expected_hash,
        "text_norm": _normalize_text(exact_text),
    }


def _validate_markdown_table_hash_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes
) -> dict:
    if not isinstance(value, dict):
        raise IdentityBindingError("markdown-table evidence value must be an object")
    if source["path"] not in {
        "automation-log/KNOWLEDGE-POSTS_20260720-0802.md",
        "automation-log/KNOWLEDGE-POSTS-B_20260802-0815.md",
        "automation-log/PAGE2-POSTS_20260721-0814.md",
    }:
        raise IdentityBindingError("markdown-table binding uses an unapproved source path")
    exact_text = _markdown_table_value(source_raw, source, value)
    virtual = _validate_exact_text_join(row, identity, value, exact_text)
    if PAGE2_FIELD_RE.fullmatch(source["field"]):
        if value["channel"] != "facebook-page2":
            raise IdentityBindingError("page2 binding targets the wrong channel")
        if value["id"] not in str(row.get("note") or ""):
            raise IdentityBindingError("target row lacks deterministic page2 id evidence")
    return virtual


def _validate_knowledge_manual_descriptor_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes
) -> dict:
    """Bind the two manually published ``kn-01`` rows to exact library copy.

    These legacy ledger rows recorded an editorial descriptor around the content
    id rather than a literal prefix of the public caption.  The ordinary table
    join must therefore continue to reject them.  This deliberately narrow join
    accepts only the source file, content id, date, channels and exact manual-post
    note that are independently present in the same hash-bound document.
    """
    if not isinstance(value, dict):
        raise IdentityBindingError("knowledge manual descriptor value must be an object")
    required = {"id", "date", "channel", "text_sha256", "join_mode"}
    if set(value) != required:
        raise IdentityBindingError("knowledge manual descriptor value keys are not exact")
    if (
        source["path"] != "automation-log/KNOWLEDGE-POSTS_20260720-0802.md"
        or value["id"] != "kn-01"
        or value["date"] != "2026-07-19"
        or value["channel"] not in {"threads", "facebook"}
        or value["join_mode"] != "kn01_manual_descriptor"
    ):
        raise IdentityBindingError("knowledge manual descriptor scope is not exact")
    selector = KNOWLEDGE_FIELD_RE.fullmatch(source["field"])
    expected_field = "threads_text" if value["channel"] == "threads" else "fb_text"
    if (
        not selector
        or selector.group(1) != "kn-01"
        or selector.group(2) != expected_field
    ):
        raise IdentityBindingError("knowledge manual descriptor selector is mismatched")

    exact_text = _markdown_table_value(source_raw, source, value)
    expected_sha = sha256_bytes(exact_text.encode("utf-8"))
    if _require_sha(value["text_sha256"], "knowledge manual text SHA-256") != expected_sha:
        raise IdentityBindingError("knowledge manual descriptor text hash does not match")
    expected_hash = _text_hash(exact_text)
    if identity["kind"] != "text_hash" or identity["value"] != expected_hash:
        raise IdentityBindingError("knowledge manual identity is not recomputed from exact source")
    if str(row.get("type") or "").casefold() != "text":
        raise IdentityBindingError("knowledge manual descriptor targets a non-text row")
    if _full_channel(row.get("channel")) != value["channel"]:
        raise IdentityBindingError("knowledge manual descriptor channel does not match")
    expected_timestamp = {
        "threads": "2026-07-19T17:30:00+07:00",
        "facebook": "2026-07-19T21:28:00+07:00",
    }[value["channel"]]
    if str(row.get("ts") or "") != expected_timestamp:
        raise IdentityBindingError("knowledge manual descriptor timestamp does not match")

    try:
        source_text = source_raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IdentityBindingError("knowledge manual descriptor source is not UTF-8") from exc
    proof = (
        "kn-01 ถูกโพสต์จริงไปแล้ววันที่ 19 ก.ค. "
        "(Threads 17:30 + FB 21:28)"
    )
    if source_text.count(proof) != 1:
        raise IdentityBindingError("knowledge manual publication proof is missing or ambiguous")

    table_rows = []
    for line in source_text.splitlines():
        if not line.startswith("| 2026-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[1] == "kn-01":
            table_rows.append(cells)
    if len(table_rows) != 1:
        raise IdentityBindingError("knowledge manual descriptor table row is ambiguous")
    topic = table_rows[0][2]
    first_line = exact_text.splitlines()[0].strip()
    prefix = str(row.get("text_first80") or "")
    descriptor = ""
    if "(" in prefix and prefix.endswith(")"):
        descriptor = prefix.rsplit("(", 1)[1][:-1].strip()
        descriptor = re.sub(r"^kn-01\s+", "", descriptor)
    topic_evidenced = topic in prefix or (
        len(descriptor) >= 20 and topic.startswith(descriptor)
    )
    if len(prefix) < 40 or "kn-01" not in prefix or not topic_evidenced:
        raise IdentityBindingError("knowledge manual descriptor lacks id/topic evidence")
    if value["channel"] == "threads":
        if not prefix.startswith("kn-01 " + first_line):
            raise IdentityBindingError("Threads manual descriptor does not bind the source opening")
    elif not prefix.startswith(first_line):
        raise IdentityBindingError("Facebook manual descriptor does not bind the source opening")
    return {
        "kind": "text_hash", "value": expected_hash,
        "text_norm": _normalize_text(exact_text),
    }


def _validate_private_session_commitment_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes,
    target_line: int,
) -> dict:
    """Validate a privacy-preserving exact tool-input commitment.

    Raw Claude/Cowork transcripts contain credentials, private filesystem paths,
    session identifiers and unrelated conversation text.  They must never be
    copied into a public repository.  The one-time builder therefore emits only
    cryptographic commitments to a narrowly allowlisted structured tool-input
    event.  This reader pins every commitment field in code and binds it back to
    the public ledger prefix/date/channel/source.  It does not infer publication
    state and it cannot be used for an unlisted row.
    """
    if source["path"] != PRIVATE_COMMITMENT_SOURCE:
        raise IdentityBindingError("private commitment source path is not allowlisted")
    selector = PRIVATE_COMMITMENT_FIELD_RE.fullmatch(source["field"])
    expected_id = "private-session-line-%06d" % target_line
    if not selector or selector.group(1) != expected_id:
        raise IdentityBindingError("private commitment selector does not bind target line")
    contract = PRIVATE_SESSION_LINE_CONTRACT.get(target_line)
    if contract is None:
        raise IdentityBindingError("target line is outside private commitment contract")
    if not isinstance(value, dict):
        raise IdentityBindingError("private commitment evidence value must be an object")
    try:
        source_text = source_raw.decode("utf-8")
        payload = _strict_json_loads(source_text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IdentityBindingError("private commitment source is not valid UTF-8 JSON") from exc
    _require_keys(payload, PRIVATE_COMMITMENT_TOP_KEYS, "private commitment source")
    if payload["schema_version"] != 1:
        raise IdentityBindingError("private commitment schema_version must be 1")
    if payload["extraction_contract"] != PRIVATE_COMMITMENT_EXTRACTION_CONTRACT:
        raise IdentityBindingError("private commitment extraction contract is invalid")
    if not isinstance(payload["created_at"], str) or not payload["created_at"]:
        raise IdentityBindingError("private commitment created_at is missing")
    if not isinstance(payload["purpose"], str) or not payload["purpose"]:
        raise IdentityBindingError("private commitment purpose is missing")
    # A strict record schema already prevents a raw-text field.  Reject common
    # absolute-path and local-session-id shapes as a second privacy boundary.
    if re.search(r"(?i)(?:[A-Z]:[\\/]|/Users/|\\\\Users\\\\|local_[0-9a-f]{8}-)", source_text):
        raise IdentityBindingError("private path or session identifier leaked into commitment")
    records = payload["records"]
    if not isinstance(records, list) or not records:
        raise IdentityBindingError("private commitment records must be non-empty")
    by_id = {}
    actual_lines = []
    for number, item in enumerate(records, 1):
        _require_keys(
            item, PRIVATE_COMMITMENT_VALUE_KEYS,
            f"private commitment record {number}",
        )
        line = item["ledger_line"]
        if not isinstance(line, int) or isinstance(line, bool):
            raise IdentityBindingError("private commitment ledger_line is invalid")
        item_contract = PRIVATE_SESSION_LINE_CONTRACT.get(line)
        if item_contract is None:
            raise IdentityBindingError("private commitment contains an unallowlisted line")
        commitment_id = "private-session-line-%06d" % line
        expected = dict(item_contract)
        join_mode = (
            "exact_task_date_time_tool_input_set"
            if line in PRIVATE_SESSION_ZERO_PREFIX_LINES
            else "exact_structured_tool_input_prefix"
        )
        expected.update({
            "commitment_id": commitment_id,
            "ledger_line": line,
            "ledger_prefix_length": item["ledger_prefix_length"],
            "ledger_prefix_sha256": item["ledger_prefix_sha256"],
            "matching_event_count": PRIVATE_SESSION_MATCH_COUNTS.get(line, 1),
            "join_mode": join_mode,
            "privacy_status": PRIVATE_COMMITMENT_PRIVACY_STATUS,
        })
        if item != expected:
            raise IdentityBindingError("private commitment differs from pinned event contract")
        if commitment_id in by_id:
            raise IdentityBindingError("duplicate private commitment id")
        by_id[commitment_id] = item
        actual_lines.append(line)
        _require_sha(item["transcript_sha256"], "private transcript SHA-256")
        _require_sha(item["event_sha256"], "private event SHA-256")
        _require_sha(item["text_sha256"], "private text SHA-256")
        _require_sha(item["ledger_prefix_sha256"], "ledger prefix SHA-256")
        if not SHA1_RE.fullmatch(str(item["text_identity_sha1"] or "")):
            raise IdentityBindingError("private text identity must be lowercase SHA-1")
    if actual_lines != sorted(PRIVATE_SESSION_LINE_CONTRACT):
        raise IdentityBindingError("private commitment target set is incomplete or unordered")
    selected = by_id.get(expected_id)
    if selected is None or selected != value:
        raise IdentityBindingError("private commitment evidence selector is missing or mismatched")

    if str(row.get("type") or "").casefold() != "comment":
        raise IdentityBindingError("private commitment targets a non-comment row")
    if _full_channel(row.get("channel")) != contract["channel"]:
        raise IdentityBindingError("private commitment channel does not match ledger row")
    if str(row.get("source") or "") != contract["row_source"]:
        raise IdentityBindingError("private commitment source task does not match ledger row")
    if _parse_date(row.get("ts"), "target timestamp") != contract["target_date"]:
        raise IdentityBindingError("private commitment date does not match ledger row")
    prefix = str(row.get("text_first80") or "")
    if target_line in PRIVATE_SESSION_ZERO_PREFIX_LINES:
        if prefix or selected["ledger_prefix_length"] != 0:
            raise IdentityBindingError("private time-join row unexpectedly has a prefix")
    elif len(prefix) < 40 or len(prefix) != selected["ledger_prefix_length"]:
        raise IdentityBindingError("private commitment ledger prefix length is invalid")
    if sha256_bytes(prefix.encode("utf-8")) != selected["ledger_prefix_sha256"]:
        raise IdentityBindingError("private commitment ledger prefix hash mismatch")
    if selected["text_length"] < len(prefix):
        raise IdentityBindingError("private committed text is shorter than ledger prefix")
    if not (
        isinstance(selected["transcript_size_bytes"], int)
        and not isinstance(selected["transcript_size_bytes"], bool)
        and 0 < selected["transcript_size_bytes"] <= 32 * 1024 * 1024
        and isinstance(selected["event_physical_line"], int)
        and not isinstance(selected["event_physical_line"], bool)
        and selected["event_physical_line"] > 0
        and isinstance(selected["text_length"], int)
        and not isinstance(selected["text_length"], bool)
        and selected["text_length"] > 0
        and isinstance(selected["matching_event_count"], int)
        and not isinstance(selected["matching_event_count"], bool)
        and selected["matching_event_count"] > 0
    ):
        raise IdentityBindingError("private commitment numeric bounds are invalid")
    if identity["kind"] != "text_hash" or identity["value"] != selected["text_identity_sha1"]:
        raise IdentityBindingError("private commitment identity does not match pinned text hash")

    try:
        event_at = datetime.datetime.fromisoformat(
            selected["event_timestamp"].replace("Z", "+00:00")
        )
        ledger_at = datetime.datetime.fromisoformat(str(row.get("ts") or ""))
    except (TypeError, ValueError) as exc:
        raise IdentityBindingError("private commitment timestamps are invalid") from exc
    if event_at.tzinfo is None or ledger_at.tzinfo is None:
        raise IdentityBindingError("private commitment timestamps require timezone")
    lag = (ledger_at.astimezone(datetime.timezone.utc) - event_at.astimezone(
        datetime.timezone.utc
    )).total_seconds()
    if lag < 0 or lag > PRIVATE_SESSION_MAX_LAG_SECONDS.get(target_line, 30 * 60):
        raise IdentityBindingError("private tool input is outside target ledger time window")
    return {"kind": "text_hash", "value": selected["text_identity_sha1"]}


def _validate_public_observation_commitment(
    value, selected: dict, label: str,
) -> None:
    if not isinstance(value, dict):
        raise IdentityBindingError(f"{label} evidence value must be an object")
    _require_keys(
        value, PUBLIC_OBSERVATION_EVIDENCE_VALUE_KEYS,
        label + " evidence commitment",
    )
    if value["observation_id"] != selected.get("observation_id"):
        raise IdentityBindingError(f"{label} evidence id is redirected")
    expected = sha256_bytes(_canonical_json(selected))
    if _require_sha(
        value["observation_sha256"], label + " observation SHA-256"
    ) != expected:
        raise IdentityBindingError(f"{label} evidence commitment is redirected")


def _validate_pantip_public_observation_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes,
    target_line: int,
) -> dict:
    """Bind one legacy Pantip row to an exact, public, read-only DOM observation.

    This is intentionally a single-observation contract.  It cannot be reused as
    a generic remote-proof mechanism: URL, topic/comment ids, author, displayed
    time, target row and exact public text digest are pinned below and in the
    append-only binding.  The observation proves only permanent-dedup identity;
    it grants no publication authority and makes no claim about later visibility.
    """
    if source["path"] != PANTIP_PUBLIC_OBSERVATION_SOURCE:
        raise IdentityBindingError("Pantip observation source path is not allowlisted")
    selector = PANTIP_PUBLIC_OBSERVATION_FIELD_RE.fullmatch(source["field"])
    if (
        not selector
        or selector.group(1) != PANTIP_PUBLIC_OBSERVATION_PIN["observation_id"]
    ):
        raise IdentityBindingError("Pantip observation selector is redirected")
    if target_line != PANTIP_PUBLIC_OBSERVATION_PIN["ledger_line"]:
        raise IdentityBindingError("Pantip observation targets an unpinned ledger line")
    try:
        source_text = source_raw.decode("utf-8")
        payload = _strict_json_loads(source_text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IdentityBindingError(
            "Pantip observation source is not valid UTF-8 JSON"
        ) from exc
    _require_keys(
        payload, PANTIP_PUBLIC_OBSERVATION_TOP_KEYS,
        "Pantip public observation source",
    )
    if payload["schema_version"] != 1:
        raise IdentityBindingError("Pantip observation schema_version must be 1")
    if payload["observation_contract"] != PANTIP_PUBLIC_OBSERVATION_CONTRACT:
        raise IdentityBindingError("Pantip observation contract is invalid")
    if not isinstance(payload["purpose"], str) or not payload["purpose"]:
        raise IdentityBindingError("Pantip observation purpose is missing")
    try:
        created_at = datetime.datetime.fromisoformat(payload["created_at"])
    except (TypeError, ValueError) as exc:
        raise IdentityBindingError("Pantip observation created_at is invalid") from exc
    if created_at.tzinfo is None:
        raise IdentityBindingError("Pantip observation created_at requires timezone")

    # Exact schemas exclude browser/session fields.  Scan serialized material as
    # a second boundary against accidental private host paths or credential data.
    if re.search(
        r"(?i)(?:(?<![A-Z])[A-Z]:[\\/]|/Users/|\\\\Users\\\\|local_[0-9a-f]{8}-|"
        r'"(?:session_?id|browser_?session|cookie|authorization)"\s*:)',
        source_text,
    ):
        raise IdentityBindingError(
            "private path, browser session, or credential leaked into Pantip observation"
        )

    observations = payload["observations"]
    if not isinstance(observations, list) or len(observations) != 1:
        raise IdentityBindingError("Pantip observation must contain exactly one record")
    selected = observations[0]
    _require_keys(
        selected, PANTIP_PUBLIC_OBSERVATION_VALUE_KEYS,
        "Pantip public observation record",
    )
    _validate_public_observation_commitment(
        value, selected, "Pantip public observation"
    )
    for key, expected in PANTIP_PUBLIC_OBSERVATION_PIN.items():
        if selected.get(key) != expected:
            raise IdentityBindingError(
                "Pantip observation pinned field differs: " + key
            )

    exact_text = selected["observed_text"]
    if not isinstance(exact_text, str) or not exact_text:
        raise IdentityBindingError("Pantip observed text is empty")
    if len(exact_text) != selected["observed_text_length"]:
        raise IdentityBindingError("Pantip observed text length mismatch")
    exact_sha = sha256_bytes(exact_text.encode("utf-8"))
    if exact_sha != selected["observed_text_sha256"]:
        raise IdentityBindingError("Pantip observed text SHA-256 mismatch")
    expected_identity = _text_hash(exact_text)
    if identity["kind"] != "text_hash" or identity["value"] != expected_identity:
        raise IdentityBindingError(
            "Pantip identity is not recomputed from exact public text"
        )

    if str(row.get("type") or "").casefold() != "comment":
        raise IdentityBindingError("Pantip observation targets a non-comment row")
    if _full_channel(row.get("channel")) != "pantip":
        raise IdentityBindingError("Pantip observation channel does not match row")
    if str(row.get("topic") or "") != selected["topic_id"]:
        raise IdentityBindingError("Pantip observation topic does not match row")
    if row.get("comment_no") != selected["comment_no"]:
        raise IdentityBindingError("Pantip observation comment number does not match row")
    if str(row.get("source") or "") != "cowork-assisted-approved-20260720":
        raise IdentityBindingError("Pantip observation row source is not pinned")
    if str(row.get("ts") or "") != "2026-07-20T18:42:00+07:00":
        raise IdentityBindingError("Pantip observation ledger timestamp is not pinned")
    prefix = str(row.get("text_first80") or "")
    descriptor = re.fullmatch(r"(.+?) \(([^()]+)\)", prefix)
    if (
        not descriptor
        or len(descriptor.group(1)) < 40
        or not exact_text.startswith(descriptor.group(1))
        or descriptor.group(2) != "ค้างชำระเกิน90วัน - ค่าธรรมเนียมศาล"
    ):
        raise IdentityBindingError(
            "Pantip public text/topic descriptor does not match ledger row"
        )

    return {
        "kind": "text_hash", "value": expected_identity,
        "text_norm": _normalize_text(exact_text),
    }


def _single_public_observation(
    *, source_raw: bytes, value, top_keys: set[str], value_keys: set[str],
    contract: str, pin: dict, label: str,
) -> tuple[dict, str]:
    """Read one exact public observation with a strict privacy boundary."""
    try:
        source_text = source_raw.decode("utf-8")
        payload = _strict_json_loads(source_text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IdentityBindingError(f"{label} source is not valid UTF-8 JSON") from exc
    _require_keys(payload, top_keys, label + " source")
    if payload["schema_version"] != 1:
        raise IdentityBindingError(f"{label} schema_version must be 1")
    if payload["observation_contract"] != contract:
        raise IdentityBindingError(f"{label} contract is invalid")
    if not isinstance(payload["purpose"], str) or not payload["purpose"]:
        raise IdentityBindingError(f"{label} purpose is missing")
    try:
        created_at = datetime.datetime.fromisoformat(payload["created_at"])
    except (TypeError, ValueError) as exc:
        raise IdentityBindingError(f"{label} created_at is invalid") from exc
    if created_at.tzinfo is None:
        raise IdentityBindingError(f"{label} created_at requires timezone")
    if re.search(
        r"(?i)(?:(?<![A-Z])[A-Z]:[\\/]|/Users/|\\\\Users\\\\|local_[0-9a-f]{8}-|"
        r'"(?:session_?id|browser_?session|cookie|authorization)"\s*:)',
        source_text,
    ):
        raise IdentityBindingError(
            f"private path, browser session, or credential leaked into {label}"
        )
    observations = payload["observations"]
    if not isinstance(observations, list) or len(observations) != 1:
        raise IdentityBindingError(f"{label} must contain exactly one record")
    selected = observations[0]
    _require_keys(selected, value_keys, label + " record")
    _validate_public_observation_commitment(value, selected, label)
    for key, expected in pin.items():
        if selected.get(key) != expected:
            raise IdentityBindingError(f"{label} pinned field differs: {key}")
    return selected, source_text


def _validate_facebook_group_public_observation_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes,
    target_line: int,
) -> dict:
    if source["path"] != FACEBOOK_GROUP_PUBLIC_OBSERVATION_SOURCE:
        raise IdentityBindingError("Facebook Group observation source is not allowlisted")
    selector = FACEBOOK_GROUP_PUBLIC_OBSERVATION_FIELD_RE.fullmatch(source["field"])
    if (
        not selector
        or selector.group(1) != FACEBOOK_GROUP_PUBLIC_OBSERVATION_PIN["observation_id"]
    ):
        raise IdentityBindingError("Facebook Group observation selector is redirected")
    if target_line != FACEBOOK_GROUP_PUBLIC_OBSERVATION_PIN["ledger_line"]:
        raise IdentityBindingError("Facebook Group observation targets an unpinned line")
    selected, _source_text = _single_public_observation(
        source_raw=source_raw,
        value=value,
        top_keys=FACEBOOK_GROUP_PUBLIC_OBSERVATION_TOP_KEYS,
        value_keys=FACEBOOK_GROUP_PUBLIC_OBSERVATION_VALUE_KEYS,
        contract=FACEBOOK_GROUP_PUBLIC_OBSERVATION_CONTRACT,
        pin=FACEBOOK_GROUP_PUBLIC_OBSERVATION_PIN,
        label="Facebook Group public observation",
    )
    exact_text = selected["observed_text"]
    if not isinstance(exact_text, str) or not exact_text:
        raise IdentityBindingError("Facebook Group observed text is empty")
    if len(exact_text) != selected["observed_text_length"]:
        raise IdentityBindingError("Facebook Group observed text length mismatch")
    if sha256_bytes(exact_text.encode("utf-8")) != selected["observed_text_sha256"]:
        raise IdentityBindingError("Facebook Group observed text SHA-256 mismatch")
    expected_identity = _text_hash(exact_text)
    if identity["kind"] != "text_hash" or identity["value"] != expected_identity:
        raise IdentityBindingError(
            "Facebook Group identity is not recomputed from exact public text"
        )

    if str(row.get("type") or "").casefold() != "comment":
        raise IdentityBindingError("Facebook Group observation targets a non-comment row")
    if _full_channel(row.get("channel")) != "fb-group":
        raise IdentityBindingError("Facebook Group observation channel does not match row")
    if str(row.get("group") or "") != "วิถีออมเงินมนุษย์เงินเดือน":
        raise IdentityBindingError("Facebook Group name is not pinned")
    if str(row.get("post") or "") != (
        "https://www.facebook.com/groups/1036176276878306/"
        "permalink/2410303406132246/"
    ):
        raise IdentityBindingError("Facebook Group ledger post is redirected")
    if str(row.get("source") or "") != "cowork-assisted-approved-20260719":
        raise IdentityBindingError("Facebook Group ledger source is not pinned")
    if str(row.get("ts") or "") != "2026-07-19T21:35:00+07:00":
        raise IdentityBindingError("Facebook Group ledger timestamp is not pinned")

    prefix = str(row.get("text_first80") or "")
    match = re.fullmatch(r"(.+?) \(([^()]+)\)", prefix)
    if not match or len(match.group(1)) < 40 or not exact_text.startswith(match.group(1)):
        raise IdentityBindingError("Facebook Group public text does not match ledger opening")
    descriptor_tokens = match.group(2).split("/")
    if descriptor_tokens != ["ตารางระบายสี", "ตามวันที่", "เป้าหมายเดียว"]:
        raise IdentityBindingError("Facebook Group ledger descriptor is not pinned")
    if not all(token in exact_text for token in descriptor_tokens):
        raise IdentityBindingError("Facebook Group descriptor is absent from public text")
    return {
        "kind": "text_hash", "value": expected_identity,
        "text_norm": _normalize_text(exact_text),
    }


def _validate_facebook_page_public_observation_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes,
    target_line: int,
) -> dict:
    if source["path"] != FACEBOOK_PAGE_PUBLIC_OBSERVATION_SOURCE:
        raise IdentityBindingError("Facebook Page observation source is not allowlisted")
    selector = FACEBOOK_PAGE_PUBLIC_OBSERVATION_FIELD_RE.fullmatch(source["field"])
    if (
        not selector
        or selector.group(1) != FACEBOOK_PAGE_PUBLIC_OBSERVATION_PIN["observation_id"]
    ):
        raise IdentityBindingError("Facebook Page observation selector is redirected")
    if target_line != FACEBOOK_PAGE_PUBLIC_OBSERVATION_PIN["ledger_line"]:
        raise IdentityBindingError("Facebook Page observation targets an unpinned line")
    selected, source_text = _single_public_observation(
        source_raw=source_raw,
        value=value,
        top_keys=FACEBOOK_PAGE_PUBLIC_OBSERVATION_TOP_KEYS,
        value_keys=FACEBOOK_PAGE_PUBLIC_OBSERVATION_VALUE_KEYS,
        contract=FACEBOOK_PAGE_PUBLIC_OBSERVATION_CONTRACT,
        pin=FACEBOOK_PAGE_PUBLIC_OBSERVATION_PIN,
        label="Facebook Page public observation",
    )
    if "fbclid=" in source_text.casefold():
        raise IdentityBindingError("transient fbclid leaked into Facebook Page evidence")
    exact_text = selected["rendered_text"]
    if not isinstance(exact_text, str) or not exact_text:
        raise IdentityBindingError("Facebook Page rendered text is empty")
    if len(exact_text) != selected["rendered_text_length"]:
        raise IdentityBindingError("Facebook Page rendered text length mismatch")
    if sha256_bytes(exact_text.encode("utf-8")) != selected["rendered_text_sha256"]:
        raise IdentityBindingError("Facebook Page rendered text SHA-256 mismatch")
    expected_identity = _text_hash(exact_text)
    if identity["kind"] != "text_hash" or identity["value"] != expected_identity:
        raise IdentityBindingError(
            "Facebook Page identity is not recomputed from exact rendered text"
        )

    link = urllib.parse.urlsplit(selected["normalized_merchant_link"])
    if (
        link.scheme != "https"
        or link.netloc != "ngernduangold.com"
        or link.path != "/debt-calculator"
        or link.fragment
        or urllib.parse.parse_qsl(link.query, keep_blank_values=True) != [
            ("utm_source", "fb"), ("utm_medium", "comment")
        ]
    ):
        raise IdentityBindingError("Facebook Page normalized merchant link is invalid")
    rendered_link_prefix = (
        "https://ngernduangold.com/debt-calculator?utm_source=fb"
    )
    if rendered_link_prefix not in exact_text:
        raise IdentityBindingError("rendered Facebook text lacks pinned merchant link prefix")

    if str(row.get("type") or "").casefold() != "comment":
        raise IdentityBindingError("Facebook Page observation targets a non-comment row")
    if _full_channel(row.get("channel")) != "facebook":
        raise IdentityBindingError("Facebook Page observation channel does not match row")
    if str(row.get("source") or "") != "fb-comment-daily":
        raise IdentityBindingError("Facebook Page ledger source is not pinned")
    if str(row.get("ts") or "") != "2026-07-31T14:08:00+07:00":
        raise IdentityBindingError("Facebook Page ledger timestamp is not pinned")
    prefix = str(row.get("text_first80") or "")
    if len(prefix) < 40 or not exact_text.startswith(prefix):
        raise IdentityBindingError("Facebook Page rendered text does not match ledger prefix")
    note = str(row.get("note") or "")
    required_note_fragments = {
        "author=page", "exactly once",
        "CTA /debt-calculator utm_source=fb utm_medium=comment",
    }
    if not all(fragment in note for fragment in required_note_fragments):
        raise IdentityBindingError("Facebook Page ledger verification note is incomplete")
    return {
        "kind": "text_hash", "value": expected_identity,
        "text_norm": _normalize_text(exact_text),
    }


def _validate_line_range_hash_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes
) -> dict:
    if not isinstance(value, dict):
        raise IdentityBindingError("line-range evidence value must be an object")
    if source["path"] not in {
        "automation-log/_pantip_LIVE-opportunity_debt-cashflow-loop_20260716.md",
        "automation-log/_pantip_draft_20260720_44168590.md",
        "automation-log/_pantip_draft_20260726.md",
        "automation-log/FBGROUP-LISTEN_20260726.md",
    }:
        raise IdentityBindingError("line-range binding uses an unapproved source path")
    exact_text = _line_range_value(source_raw, source)
    virtual = _validate_exact_text_join(row, identity, value, exact_text)
    if value["channel"] == "pantip" and row.get("topic"):
        topic = str(row["topic"])
        source_text = source_raw.decode("utf-8-sig", errors="strict")
        if topic.isdigit() and topic not in value["id"] and topic not in source_text:
            raise IdentityBindingError("Pantip topic does not match exact-text evidence id")
    return virtual


def _validate_line_broadcast_local_recovery_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes,
    target_line: int | None,
) -> dict:
    """Recover legacy LINE broadcast #1A without claiming delivery.

    The ledger stored a version descriptor instead of the public copy.  This join
    is intentionally pinned to the single historical row and source draft: the
    row explicitly names version A, the draft contains exactly one version-A
    section, and the scheduled time is preserved separately from the older draft
    queue date.  It supplies permanent-dedup identity only.
    """
    required = {
        "id", "channel", "draft_queue_date", "scheduled_for",
        "text_sha256", "join_mode",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise IdentityBindingError(
            "LINE broadcast recovery evidence value keys are not exact"
        )
    if (
        target_line != 33
        or source["path"] != "automation-log/LINE-BROADCAST-01_draft.md"
        or source["field"] != "section[version=A].body"
        or value["id"] != "line-broadcast-01-a"
        or value["channel"] != "line"
        or value["draft_queue_date"] != "2026-07-20"
        or value["scheduled_for"] != "2026-07-19T11:30:00+07:00"
        or value["text_sha256"]
        != "FFB5159F9D3201560A3E5AF6CC2611CD38B53F992F7666CE5809CA83F003EEE1"
        or value["join_mode"] != "line_broadcast_version_descriptor"
    ):
        raise IdentityBindingError("LINE broadcast recovery scope is not exact")

    exact_text = _line_broadcast_section_value(source_raw, source)
    expected_sha = sha256_bytes(exact_text.encode("utf-8"))
    if _require_sha(value["text_sha256"], "LINE broadcast text SHA-256") != expected_sha:
        raise IdentityBindingError("LINE broadcast source text hash does not match")
    expected_identity = _text_hash(exact_text)
    if identity["kind"] != "text_hash" or identity["value"] != expected_identity:
        raise IdentityBindingError(
            "LINE broadcast identity is not recomputed from exact version A"
        )

    expected_row = {
        "type": "broadcast-scheduled",
        "channel": "line",
        "text_first80": "Broadcast#1 A - send 2026-07-19T11:30",
        "ts": "2026-07-18T22:29:00+07:00",
        "source": "cowork-manual-20260718",
        "note": (
            "confirmed in broadcast list; also VOOM; existing older scheduled "
            "21/07 17:40 + 24/07 17:45"
        ),
    }
    if row != expected_row:
        raise IdentityBindingError("LINE broadcast target row is not the pinned row")
    if not source_raw.decode("utf-8-sig").startswith(
        "# LINE Broadcast #1 — คิว 20 ก.ค.\n"
    ):
        raise IdentityBindingError("LINE broadcast draft queue heading is mismatched")
    return {
        "kind": "text_hash", "value": expected_identity,
        "text_norm": _normalize_text(exact_text),
    }


def _validate_manifest_hash_binding(
    row: dict, source: dict, identity: dict, value, source_raw: bytes
) -> dict:
    required = {"id", "date", "channel", "join_mode", "caption_sha256"}
    if not isinstance(value, dict) or set(value) != required:
        raise IdentityBindingError("manifest-hash evidence value keys are not exact")
    if source["path"] != ".system_control/content_manifest.json":
        raise IdentityBindingError("manifest-hash binding uses the wrong source path")
    selector = MANIFEST_FIELD_RE.fullmatch(source["field"])
    if not selector or selector.group(1) != value["id"]:
        raise IdentityBindingError("manifest-hash source selector is mismatched")
    try:
        payload = _strict_json_loads(source_raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IdentityBindingError("content manifest is not valid UTF-8 JSON") from exc
    items = [item for item in payload.get("items", []) if item.get("id") == value["id"]]
    if len(items) != 1:
        raise IdentityBindingError("manifest-hash item is missing or ambiguous")
    item = items[0]
    if str(item.get("date")) != value["date"]:
        raise IdentityBindingError("manifest-hash date does not match source item")
    if identity["kind"] != "clip" or identity["value"] != value["id"]:
        raise IdentityBindingError("manifest-hash clip identity does not match item id")
    if str(row.get("type") or "").casefold() not in CLIP_ROW_TYPES:
        raise IdentityBindingError("manifest-hash binding targets a non-media row")
    if _full_channel(row.get("channel")) != value["channel"]:
        raise IdentityBindingError("manifest-hash channel does not match target row")
    if _parse_date(row.get("ts"), "target timestamp") != value["date"]:
        raise IdentityBindingError("manifest-hash date does not match target row")
    prefix = str(row.get("text_first80") or "")
    mode = value["join_mode"]
    if mode in {"exact_caption_prefix", "whitespace_equivalent_caption_prefix"}:
        caption = str((item.get("captions") or {}).get(value["channel"]) or "")
        caption_hash = sha256_bytes(caption.encode("utf-8"))
        if _require_sha(value["caption_sha256"], "manifest caption SHA-256") != caption_hash:
            raise IdentityBindingError("manifest caption hash does not match evidence")
        prefix_matches = caption.startswith(prefix)
        if mode == "whitespace_equivalent_caption_prefix":
            prefix_matches = re.sub(r"\s+", "", caption).startswith(
                re.sub(r"\s+", "", prefix)
            )
        if len(prefix) < 40 or not prefix_matches:
            raise IdentityBindingError("manifest caption does not match target prefix")
    elif mode == "canonical_slug_descriptor":
        if value["caption_sha256"] != ZERO_SHA256:
            raise IdentityBindingError("descriptor join must not claim a caption hash")
        token = value["id"].split("_", 1)[-1]
        haystack = (prefix + " " + str(row.get("note") or "")).casefold()
        if len(prefix) < 40 or token.casefold() not in haystack:
            raise IdentityBindingError("manifest canonical slug is absent from target evidence")
    else:
        raise IdentityBindingError("manifest-hash join_mode is invalid")
    return {"kind": "clip", "value": value["id"]}


def _validate_manifest_binding(row: dict, source: dict, identity: dict, value) -> dict:
    if not isinstance(value, dict):
        raise IdentityBindingError("content manifest evidence value must be an object")
    required = {"id", "date", "reel", "posted"}
    if set(value) != required:
        raise IdentityBindingError("content manifest evidence value keys are not exact")
    selector = MANIFEST_FIELD_RE.fullmatch(source["field"])
    if not selector or selector.group(1) != str(value["id"]):
        raise IdentityBindingError("content manifest source_field is ambiguous/mismatched")
    if source["path"] != ".system_control/content_manifest.json":
        raise IdentityBindingError("content manifest binding uses the wrong source path")
    if identity["kind"] != "clip" or identity["value"] != value["id"]:
        raise IdentityBindingError("content manifest identity does not match item id")
    if str(row.get("type") or "").casefold() not in CLIP_ROW_TYPES:
        raise IdentityBindingError("content manifest binding targets a non-media row")
    channel = _full_channel(row.get("channel"))
    posted = value["posted"]
    row_status = str(row.get("status") or "").strip().casefold()
    source_marks_posted = isinstance(posted, dict) and bool(
        str(posted.get(channel) or "").strip()
    )
    row_marks_posted = row_status in {
        "posted", "published", "published_confirmed", "delivered_confirmed"
    }
    if not source_marks_posted and not row_marks_posted:
        raise IdentityBindingError(
            "neither manifest nor target row records this channel as posted"
        )
    reel = str(value["reel"] or "").replace("\\", "/")
    row_video = str(row.get("video") or "").replace("\\", "/")
    row_clip = str(row.get("clip_id") or "")
    row_note = str(row.get("note") or "").replace("\\", "/")
    if row_clip != value["id"] and row_video != reel and reel not in row_note:
        raise IdentityBindingError("target row cannot be joined deterministically to manifest")
    date = _parse_date(value["date"], "manifest date")
    if row.get("slot") and _parse_date(row["slot"], "target slot") != date:
        raise IdentityBindingError("target slot does not match manifest date")
    return {"kind": "clip", "value": str(value["id"])}


def _validate_published_media_binding(
    row: dict, source: dict, identity: dict, value, reuse_policy: str
) -> dict:
    if not isinstance(value, dict):
        raise IdentityBindingError("published-media evidence value must be an object")
    required = {
        "content_id", "asset", "sha256", "status", "channels", "published_date"
    }
    if set(value) != required:
        raise IdentityBindingError("published-media evidence value keys are not exact")
    selector = PUBLISHED_MEDIA_FIELD_RE.fullmatch(source["field"])
    if not selector or selector.group(1) != str(value["content_id"]):
        raise IdentityBindingError("published-media source_field is ambiguous/mismatched")
    if source["path"] != "automation-log/media-qa/published-media.json":
        raise IdentityBindingError("published-media binding uses the wrong source path")
    if identity["kind"] != "clip" or identity["value"] != value["content_id"]:
        raise IdentityBindingError("published-media identity does not match content_id")
    if str(row.get("type") or "").casefold() != "image":
        raise IdentityBindingError("published-media binding targets a non-image row")
    if _full_channel(row.get("channel")) not in value["channels"]:
        raise IdentityBindingError("published-media channel does not match target row")
    if _parse_date(row.get("ts"), "target timestamp") != _parse_date(
        value["published_date"], "published-media date"
    ):
        raise IdentityBindingError("published-media date does not match target row")
    _require_sha(value["sha256"], "published-media asset SHA-256")
    status = str(value["status"] or "")
    asset = str(value["asset"] or "").replace("\\", "/")
    if value["content_id"] == "qt-02":
        if status != "published_then_quarantined_watermarked":
            raise IdentityBindingError("qt-02 quarantine status is not preserved")
        if "/quarantine/" not in "/" + asset or reuse_policy != "QUARANTINED_NON_REUSABLE":
            raise IdentityBindingError("qt-02 must remain quarantined and non-reusable")
    else:
        if status != "published" or reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("published image reuse policy/status is invalid")
    return {"kind": "clip", "value": str(value["content_id"])}


def _validate_knowledge_binding(row: dict, source: dict, identity: dict, value) -> dict:
    if not isinstance(value, dict):
        raise IdentityBindingError("knowledge evidence value must be an object")
    required = {"id", "date", "channel", "exact_text"}
    if set(value) != required:
        raise IdentityBindingError("knowledge evidence value keys are not exact")
    selector = KNOWLEDGE_FIELD_RE.fullmatch(source["field"])
    expected_field = "threads_text" if value["channel"] == "threads" else "fb_text"
    if not selector or selector.group(1) != value["id"] or selector.group(2) != expected_field:
        raise IdentityBindingError("knowledge source_field is ambiguous/mismatched")
    if source["path"] not in {
        "automation-log/KNOWLEDGE-POSTS_20260720-0802.md",
        "automation-log/KNOWLEDGE-POSTS-B_20260802-0815.md",
    }:
        raise IdentityBindingError("knowledge binding uses an unapproved source path")
    exact_text = str(value["exact_text"] or "")
    if not exact_text or not _normalize_text(exact_text):
        raise IdentityBindingError("knowledge exact_text is empty")
    expected_hash = _text_hash(exact_text)
    if identity["kind"] != "text_hash" or identity["value"] != expected_hash:
        raise IdentityBindingError("knowledge identity is not recomputed from exact_text")
    if str(row.get("type") or "").casefold() not in TEXT_ROW_TYPES:
        raise IdentityBindingError("knowledge binding targets a non-text row")
    if _full_channel(row.get("channel")) != value["channel"]:
        raise IdentityBindingError("knowledge channel does not match target row")
    prefix = str(row.get("text_first80") or "")
    if len(prefix) < 40 or not exact_text.startswith(prefix):
        raise IdentityBindingError("knowledge exact_text does not match target prefix")
    if _parse_date(row.get("ts"), "target timestamp") != _parse_date(
        value["date"], "knowledge date"
    ):
        raise IdentityBindingError("knowledge date does not match target row")
    row_kn = str(row.get("kn_id") or "")
    if row_kn and row_kn != value["id"]:
        raise IdentityBindingError("target kn_id does not match knowledge source")
    if not row_kn and value["id"] not in str(row.get("note") or ""):
        raise IdentityBindingError("target row lacks deterministic knowledge id evidence")
    return {
        "kind": "text_hash", "value": expected_hash,
        "text_norm": _normalize_text(exact_text),
    }


def _validate_binding_value(
    row: dict, source: dict, evidence_type: str, identity: dict,
    value, reuse_policy: str, source_raw: bytes, target_line: int | None = None,
) -> dict:
    # Line 39 is a descriptive legacy reshare record.  A generic caption,
    # manifest item, Reel permalink, local asset, or prefix match cannot prove
    # which ephemeral Facebook Story object was created.  Keep this row
    # fail-closed until a dedicated, pinned one-to-one Story observation
    # contract is implemented with every field listed above.  This check runs
    # before every generic evidence route so future helper types cannot
    # accidentally turn a Reel/date similarity into a Story identity.
    if (
        target_line == FACEBOOK_STORY_UNRESOLVED_LINE
        and str(row.get("type") or "").casefold() == "story"
        and _full_channel(row.get("channel")) == "facebook"
    ):
        raise IdentityBindingError(
            "Facebook Story ledger line 39 requires dedicated one-to-one "
            "Story archive evidence; generic manifest, Reel, asset, caption, "
            "prefix, or local-draft evidence is insufficient"
        )
    if evidence_type == "content_manifest_item":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("manifest binding reuse_policy is invalid")
        return _validate_manifest_binding(row, source, identity, value)
    if evidence_type == "published_media_item":
        return _validate_published_media_binding(
            row, source, identity, value, reuse_policy
        )
    if evidence_type == "knowledge_markdown_field":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("knowledge binding reuse_policy is invalid")
        return _validate_knowledge_binding(row, source, identity, value)
    if evidence_type == "markdown_table_text_hash":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("markdown-table reuse_policy is invalid")
        return _validate_markdown_table_hash_binding(
            row, source, identity, value, source_raw
        )
    if evidence_type == "knowledge_manual_descriptor_join":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError(
                "knowledge manual descriptor reuse_policy is invalid"
            )
        return _validate_knowledge_manual_descriptor_binding(
            row, source, identity, value, source_raw
        )
    if evidence_type == "privacy_sanitized_tool_input_commitment":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("private commitment reuse_policy is invalid")
        if target_line is None:
            raise IdentityBindingError("private commitment target line is unavailable")
        return _validate_private_session_commitment_binding(
            row, source, identity, value, source_raw, target_line
        )
    if evidence_type == "pantip_public_dom_observation":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("Pantip observation reuse_policy is invalid")
        if target_line is None:
            raise IdentityBindingError("Pantip observation target line is unavailable")
        return _validate_pantip_public_observation_binding(
            row, source, identity, value, source_raw, target_line
        )
    if evidence_type == "facebook_group_public_dom_observation":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("Facebook Group observation reuse_policy is invalid")
        if target_line is None:
            raise IdentityBindingError("Facebook Group target line is unavailable")
        return _validate_facebook_group_public_observation_binding(
            row, source, identity, value, source_raw, target_line
        )
    if evidence_type == "facebook_page_public_dom_and_link_observation":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("Facebook Page observation reuse_policy is invalid")
        if target_line is None:
            raise IdentityBindingError("Facebook Page target line is unavailable")
        return _validate_facebook_page_public_observation_binding(
            row, source, identity, value, source_raw, target_line
        )
    if evidence_type == "markdown_line_range_text_hash":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("line-range reuse_policy is invalid")
        return _validate_line_range_hash_binding(
            row, source, identity, value, source_raw
        )
    if evidence_type == "line_broadcast_local_recovery":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError(
                "LINE broadcast recovery reuse_policy is invalid"
            )
        return _validate_line_broadcast_local_recovery_binding(
            row, source, identity, value, source_raw, target_line
        )
    if evidence_type == "content_manifest_hash_join":
        if reuse_policy != "PERMANENT_DEDUP":
            raise IdentityBindingError("manifest-hash reuse_policy is invalid")
        return _validate_manifest_hash_binding(
            row, source, identity, value, source_raw
        )
    raise IdentityBindingError(f"unsupported evidence_type: {evidence_type!r}")


def load_identity_bindings(
    *, ledger_path, rows: list[dict], row_sha256: dict[int, str],
    bindings_path=None, repo_root=None,
) -> tuple[dict[int, dict], dict]:
    """Validate and atomically return ``line -> virtual identity`` mappings.

    Missing bindings are valid and simply repair zero legacy rows.  If a binding file
    exists, any defect returns ``state=INVALID`` and an empty mapping; callers must keep
    permanent dedup fail-closed.
    """
    ledger = Path(ledger_path).resolve()
    root = Path(repo_root).resolve() if repo_root else ledger.parent.parent.resolve()
    binding_path = (
        Path(bindings_path).resolve()
        if bindings_path
        else ledger.with_name("post-ledger-identity-bindings.jsonl")
    )
    report = {
        "state": "NOT_PRESENT", "path": str(binding_path), "binding_count": 0,
        "seal_count": 0, "applied_lines": [], "quarantined_non_reusable": [],
        "errors": [],
    }
    if not binding_path.exists():
        return {}, report
    try:
        records = _parse_jsonl(_stable_bytes(binding_path), "identity binding ledger")
        if not records:
            raise IdentityBindingError("identity binding ledger is empty")
        expected_ledger = _repo_relative(ledger, root)
        expected_previous = ZERO_SHA256
        ids = set()
        target_lines = set()
        evidence_cache = {}
        pending = {}
        quarantined = set()
        seal_count = 0
        last_record_was_seal = False
        for physical_line, record in enumerate(records, 1):
            record_type = str(record.get("record_type") or "")
            if record_type == "post_ledger_identity_binding_seal":
                _require_keys(record, SEAL_KEYS, f"seal {physical_line}")
                if record["schema_version"] != 1:
                    raise IdentityBindingError("seal schema_version must be 1")
                previous = _require_sha(
                    record["previous_record_sha256"], "previous_record_sha256"
                )
                if previous != expected_previous:
                    raise IdentityBindingError(
                        f"binding seal hash-chain mismatch at line {physical_line}"
                    )
                if record["binding_count"] != len(pending):
                    raise IdentityBindingError("binding seal count does not match history")
                if record["sealed_target_lines"] != sorted(pending):
                    raise IdentityBindingError("binding seal target set is incomplete/ambiguous")
                stored_seal = _require_sha(record["seal_sha256"], "seal_sha256")
                if stored_seal != seal_sha256(record):
                    raise IdentityBindingError("binding seal payload hash mismatch")
                expected_previous = stored_seal
                seal_count += 1
                last_record_was_seal = True
                continue
            _require_keys(record, TOP_KEYS, f"binding {physical_line}")
            if record["schema_version"] != 1:
                raise IdentityBindingError("binding schema_version must be 1")
            if record["record_type"] != "post_ledger_identity_binding":
                raise IdentityBindingError("binding record_type is invalid")
            last_record_was_seal = False
            binding_id = str(record["binding_id"] or "")
            if not BINDING_ID_RE.fullmatch(binding_id):
                raise IdentityBindingError("binding_id is invalid")
            if binding_id in ids:
                raise IdentityBindingError(f"duplicate binding_id: {binding_id}")
            ids.add(binding_id)
            previous = _require_sha(
                record["previous_binding_sha256"], "previous_binding_sha256"
            )
            if previous != expected_previous:
                raise IdentityBindingError(
                    f"binding hash-chain mismatch at {binding_id}"
                )
            stored_hash = _require_sha(record["binding_sha256"], "binding_sha256")
            calculated_hash = binding_sha256(record)
            if stored_hash != calculated_hash:
                raise IdentityBindingError(f"binding payload hash mismatch at {binding_id}")
            expected_previous = stored_hash

            target = record["target"]
            source = record["source"]
            identity = record["identity"]
            _require_keys(target, TARGET_KEYS, f"{binding_id}.target")
            _require_keys(source, SOURCE_KEYS, f"{binding_id}.source")
            _require_keys(identity, IDENTITY_KEYS, f"{binding_id}.identity")
            if _strict_relative(target["ledger_path"], "target.ledger_path") != expected_ledger:
                raise IdentityBindingError(f"{binding_id} targets another ledger")
            line = target["line"]
            if not isinstance(line, int) or isinstance(line, bool) or not 1 <= line <= len(rows):
                raise IdentityBindingError(f"{binding_id} target line is invalid")
            if line in target_lines:
                raise IdentityBindingError(
                    f"ambiguous duplicate target line: {line}"
                )
            target_lines.add(line)
            target_hash = _require_sha(target["row_sha256"], "target.row_sha256")
            if row_sha256.get(line) != target_hash:
                raise IdentityBindingError(f"target row hash mismatch at line {line}")
            source["path"] = _strict_relative(source["path"], "source.path")
            _require_sha(source["sha256"], "source.sha256")
            if not isinstance(source["field"], str) or not source["field"]:
                raise IdentityBindingError("source.field is missing")
            source_raw = _source_bytes(root, source)
            evidence_record, evidence_value = _load_evidence(
                root, source, evidence_cache
            )
            if (
                evidence_record["source_path"] != source["path"]
                or evidence_record["source_sha256"] != source["sha256"]
                or evidence_record["source_field"] != source["field"]
            ):
                raise IdentityBindingError(
                    f"{binding_id} source provenance does not match evidence snapshot"
                )
            _require_sha(identity["value_sha256"], "identity.value_sha256")
            if identity["value_sha256"] != identity_value_sha256(identity["value"]):
                raise IdentityBindingError(f"{binding_id} identity value hash mismatch")
            if identity["kind"] not in {"clip", "text_hash"}:
                raise IdentityBindingError(f"{binding_id} identity kind is invalid")

            row = rows[line - 1]
            # An overlay is not allowed to overwrite or contradict a native identity.
            kind = str(row.get("type") or "").casefold()
            if identity["kind"] == "text_hash" and (
                str(row.get("text_hash") or "").strip()
                or str(row.get("text_norm") or "").strip()
            ):
                raise IdentityBindingError(f"{binding_id} targets an already-complete text row")
            if identity["kind"] == "clip" and kind in CLIP_ROW_TYPES:
                native = any(
                    str(row.get(field) or "").strip()
                    for field in ("clip_key",)
                )
                if native:
                    raise IdentityBindingError(f"{binding_id} overwrites native clip_key")
            reuse_policy = str(record["reuse_policy"] or "")
            virtual = _validate_binding_value(
                row, source, str(record["evidence_type"] or ""), identity,
                evidence_value, reuse_policy, source_raw, line,
            )
            virtual.update({
                "binding_id": binding_id,
                "binding_sha256": stored_hash,
                "reuse_policy": reuse_policy,
                "source_path": source["path"],
                "source_sha256": source["sha256"],
                "source_field": source["field"],
            })
            pending[line] = virtual
            if reuse_policy == "QUARANTINED_NON_REUSABLE":
                quarantined.add(virtual["value"])

        if pending and not last_record_was_seal:
            raise IdentityBindingError(
                "identity binding ledger has no final append-only seal"
            )
        report.update({
            "state": "PASS", "binding_count": len(pending),
            "seal_count": seal_count,
            "applied_lines": sorted(pending),
            "quarantined_non_reusable": sorted(quarantined),
        })
        return pending, report
    except (IdentityBindingError, OSError, ValueError, TypeError) as exc:
        report.update({"state": "INVALID", "errors": [str(exc)]})
        return {}, report
