"""Fail-closed Pantip channel eligibility derived from the durable policy.

This module is deliberately pure and read-only.  It does not grant publication
authority; it only prevents quota/timing helpers from presenting a Pantip slot as
eligible when the manual-pilot review or one-time approval state says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone


BANGKOK = timezone(timedelta(hours=7))
PASSED_REVIEW_STATES = {"PASS", "PASSED", "APPROVED"}
ACTIVE_AUTHORIZATION_STATES = {
    "ONE_TIME_APPROVAL_ACTIVE",
    "FRESH_PER_PIECE_APPROVAL",
}
ACTIVE_PILOT_STATES = {"READY_FOR_CONFIRMED_REPLY"}


@dataclass(frozen=True)
class PantipEligibilityResult:
    allowed: bool
    failures: tuple[str, ...]

    @property
    def reason(self) -> str:
        return "; ".join(self.failures) if self.failures else "Pantip policy gates pass"


def _evaluation_time(now: datetime | date | None) -> datetime:
    if now is None:
        return datetime.now(BANGKOK)
    if isinstance(now, datetime):
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Pantip eligibility time must include a timezone")
        return now.astimezone(BANGKOK)
    if isinstance(now, date):
        return datetime.combine(now, time.min, tzinfo=BANGKOK)
    raise ValueError("Pantip eligibility time is invalid")


def _parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(BANGKOK)


def evaluate_pantip_eligibility(
    policy: object, *, now: datetime | date | None = None,
    content_id: str | None = None, placement_id: str | None = None,
) -> PantipEligibilityResult:
    """Return a complete, exact-piece Pantip eligibility decision.

    Generic quota/timing callers do not know the exact approved piece and therefore
    remain blocked.  A passing result still performs no external action.
    Unknown/malformed policy or identity state fails closed.
    """
    try:
        current = _evaluation_time(now)
    except ValueError as exc:
        return PantipEligibilityResult(False, (str(exc),))

    failures: list[str] = []
    if not isinstance(policy, dict):
        return PantipEligibilityResult(False, ("policy.json missing or invalid",))
    channels = policy.get("channels")
    channel = channels.get("pantip") if isinstance(channels, dict) else None
    if not isinstance(channel, dict):
        return PantipEligibilityResult(False, ("Pantip channel policy is missing",))

    if channel.get("publication_authorized") is not True:
        failures.append("Pantip publication_authorized is not true")
    if channel.get("state") != "limited":
        failures.append("Pantip channel state is not the explicit limited pilot")
    if channel.get("kind") != "forum":
        failures.append("Pantip channel kind is not forum")
    if channel.get("auto") is not False or channel.get("automation_capable") is not False:
        failures.append("Pantip limited pilot must remain manual and automation-incapable")
    try:
        phase_until = date.fromisoformat(str(channel["phase_until"]))
        weekly_quota = int(channel.get("weekly_quota") or 0)
        if phase_until < current.date():
            failures.append("Pantip limited pilot window has expired")
        if weekly_quota <= 0:
            failures.append("Pantip weekly quota is zero")
    except (KeyError, TypeError, ValueError):
        failures.append("Pantip limited pilot window/quota is invalid")

    pilot = channel.get("manual_pilot")
    if not isinstance(pilot, dict):
        failures.append("Pantip manual_pilot policy is missing")
        return PantipEligibilityResult(False, tuple(dict.fromkeys(failures)))

    pilot_status = str(pilot.get("status") or "").strip().upper()
    if pilot_status not in ACTIVE_PILOT_STATES:
        failures.append("Pantip manual pilot is not explicitly ready for one confirmed reply")
    if pilot.get("scope") != "reply_existing_topic_only":
        failures.append("Pantip pilot scope is not reply_existing_topic_only")
    forbidden = pilot.get("forbidden")
    if not isinstance(forbidden, list) or "automated_publication" not in forbidden:
        failures.append("Pantip pilot does not explicitly forbid automated publication")

    authorization_state = str(pilot.get("authorization_state") or "").strip().upper()
    if authorization_state == "ONE_TIME_APPROVAL_CONSUMED":
        failures.append("Pantip one-time approval is consumed")
    elif authorization_state not in ACTIVE_AUTHORIZATION_STATES:
        failures.append("Pantip authorization state is not a fresh per-piece approval")

    normalized_content_id = str(content_id or "").strip()
    normalized_placement_id = str(placement_id or "").strip()
    if pilot.get("per_piece_owner_confirmation_required") is not True:
        failures.append("Pantip per-piece owner confirmation requirement is missing")
    if not normalized_content_id or not normalized_placement_id:
        failures.append("Pantip eligibility requires exact content_id and placement_id")
    elif normalized_placement_id != normalized_content_id + "__pantip_main":
        failures.append("Pantip placement_id is not the canonical Pantip account placement")
    approved_content_id = str(pilot.get("authorized_content_id") or "").strip()
    approved_placement_id = str(pilot.get("authorized_placement_id") or "").strip()
    if (approved_content_id != normalized_content_id
            or approved_placement_id != normalized_placement_id):
        failures.append("Pantip piece does not match the fresh owner authorization")

    not_before = _parse_timestamp(pilot.get("next_publication_not_before"))
    if not_before is None:
        failures.append("Pantip next_publication_not_before is invalid")
    elif current < not_before:
        failures.append("Pantip next publication time has not arrived")

    if pilot.get("review_must_pass_before_reauthorization") is not True:
        failures.append("Pantip review-before-reauthorization rule is missing")
    review_due = _parse_timestamp(pilot.get("review_due_at"))
    if review_due is None:
        failures.append("Pantip manual-pilot review_due_at is invalid")

    gates = policy.get("gates")
    review = None
    if isinstance(gates, list):
        review = next(
            (
                gate for gate in gates
                if isinstance(gate, dict)
                and gate.get("task") == "pantip manual pilot 48h review"
            ),
            None,
        )
    if not isinstance(review, dict):
        failures.append("Pantip manual-pilot review gate is missing")
    else:
        review_status = str(review.get("status") or "").strip().upper()
        if review_status not in PASSED_REVIEW_STATES:
            if review_due is not None and current > review_due:
                failures.append("Pantip manual-pilot review is overdue and has not passed")
            else:
                failures.append("Pantip manual-pilot review has not passed")
        gate_due = _parse_timestamp(review.get("review_due_at"))
        if gate_due is None or review_due is None or gate_due != review_due:
            failures.append("Pantip review gate timestamp does not match manual_pilot")

    return PantipEligibilityResult(False if failures else True,
                                    tuple(dict.fromkeys(failures)))
