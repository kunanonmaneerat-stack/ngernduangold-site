"""One fail-closed readiness view for analytics consumers.

Consumers may display raw observations, but only this hash-bound state can
authorize ranking, timing, cadence, SEO prioritisation or scaling decisions.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

try:
    import observation_snapshot
except ImportError:  # pragma: no cover - package import path
    from pipeline import observation_snapshot


def _current_expiry(bundle, current):
    """Return one canonical exclusive expiry, or ``None`` fail-closed."""
    try:
        expiry = dt.datetime.fromisoformat(
            str(bundle.get("expires_at") or "").replace("Z", "+00:00")
        )
    except (AttributeError, TypeError, ValueError):
        return None
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        return None
    if current.tzinfo is None or current.utcoffset() is None:
        return None
    if expiry <= current:
        return None
    return expiry.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def read(*, now=None, today=None, sales_path=None):
    """Return GA4/GSC/revenue readiness; observation errors fail closed."""
    try:
        collect_options = {}
        if now is not None:
            collect_options["now"] = now
        if today is not None:
            collect_options["today"] = today
        if sales_path is not None:
            collect_options["sales_path"] = sales_path
        observed = observation_snapshot.collect(**collect_options)
        current = now
        if current is None:
            current = dt.datetime.fromisoformat(
                str(observed.get("observed_at") or "").replace("Z", "+00:00")
            )
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("readiness evaluation time must be timezone-aware")
        ga4_source = observed["sources"]["ga4"]
        gsc_source = observed["sources"]["gsc"]
        revenue_source = observed["sources"]["revenue_ledger"]
        observed_metrics = observed.get("metrics")
        observed_metrics = (
            observed_metrics if isinstance(observed_metrics, dict) else {}
        )
        revenue_metrics = observed_metrics.get("verified_affiliate_revenue")
        revenue_metrics = (
            revenue_metrics if isinstance(revenue_metrics, dict) else {}
        )
        learning_sources = observed["learning_readiness"]["sources"]
        revenue_learning = learning_sources["revenue"]
        ga4_bundle = ga4_source["bundle"]
        gsc_bundle = gsc_source["bundle"]
        ga4_expiry = _current_expiry(ga4_bundle, current)
        gsc_expiry = _current_expiry(gsc_bundle, current)
        revenue_expiry = _current_expiry(
            {"expires_at": revenue_metrics.get("trust_expires_at")}, current
        )
        ga4_ready = (
            ga4_bundle.get("decisionable") is True
            and ga4_bundle.get("state") == "CURRENT"
            and ga4_bundle.get("capture_trust") == "TRUSTED"
            and ga4_bundle.get("current_trust") == "TRUSTED"
            and ga4_expiry is not None
        )
        gsc_ready = (
            gsc_bundle.get("decisionable") is True
            and gsc_bundle.get("state") == "CURRENT"
            and gsc_expiry is not None
        )
        revenue_ready = (
            revenue_source.get("trusted") is True
            and revenue_source.get("learning_ready") is True
            and revenue_source.get("quality_state") == "CURRENT"
            and revenue_source.get("reconcile_required") is False
            and revenue_learning.get("ready") is True
            and revenue_learning.get("state") == "CURRENT"
            and revenue_expiry is not None
        )
        ga4_state = ga4_bundle.get("state", "UNKNOWN")
        gsc_state = gsc_bundle.get("state", "UNKNOWN")
        if ga4_bundle.get("decisionable") is True and ga4_expiry is None:
            ga4_state = "INVALID_EXPIRY"
        if gsc_bundle.get("decisionable") is True and gsc_expiry is None:
            gsc_state = "INVALID_EXPIRY"
        ga4 = SimpleNamespace(
            trusted=ga4_ready,
            label="TRUSTED" if ga4_ready else "UNTRUSTED",
            reason=("hash-bound 28-day bundle is current and trusted at capture and now"
                    if ga4_ready else "bundle=%s; capture=%s; current=%s" % (
                        ga4_state,
                        ga4_bundle.get("capture_trust", "UNKNOWN"),
                        ga4_bundle.get("current_trust", "UNKNOWN"),
                    )),
            schema="hash-bound-28d-v3",
            state=ga4_state,
            expires_at=ga4_expiry,
        )
        gsc = SimpleNamespace(
            trusted=gsc_ready,
            label="CURRENT" if gsc_ready else "UNTRUSTED",
            reason=("hash-bound non-truncated 28-day bundle is current"
                    if gsc_ready else "bundle=%s" % gsc_state),
            schema="hash-bound-28d-v2",
            state=gsc_state,
            expires_at=gsc_expiry,
        )
        revenue_state = str(
            revenue_source.get("quality_state")
            or revenue_learning.get("state")
            or "UNAVAILABLE"
        )
        if (
            revenue_source.get("trusted") is True
            and revenue_source.get("quality_state") == "CURRENT"
            and revenue_expiry is None
        ):
            revenue_state = "INVALID_EXPIRY"
        revenue = SimpleNamespace(
            trusted=revenue_ready,
            label="CURRENT" if revenue_ready else "UNTRUSTED",
            reason=(
                "reconciled affiliate revenue is current and learning-ready"
                if revenue_ready else "ledger=%s; reconcile_required=%s" % (
                    revenue_state,
                    revenue_source.get("reconcile_required", "UNKNOWN"),
                )
            ),
            schema="reconciled-affiliate-revenue",
            state=revenue_state,
            expires_at=revenue_expiry,
        )
        return SimpleNamespace(
            ga4=ga4, gsc=gsc, revenue=revenue, observation=observed
        )
    except Exception as exc:
        blocked = SimpleNamespace(
            trusted=False,
            label="UNTRUSTED",
            reason="observation readiness unavailable (%s)" % type(exc).__name__,
            schema="error",
            state="UNAVAILABLE",
            expires_at=None,
        )
        return SimpleNamespace(
            ga4=blocked, gsc=blocked, revenue=blocked, observation=None
        )


def ga4():
    return read().ga4


def gsc():
    return read().gsc


def revenue():
    return read().revenue
