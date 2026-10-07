"""Consent, minimization, retention and guards for read-only AI guidance.

These deterministic guards provide containment and regression coverage. They
cannot establish that a hosted model is immune to arbitrary prompt injection.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit
from uuid import uuid4

from flask import current_app
from sqlalchemy import update

from app.domain.ai_governance import AIConsent, AIConversationControl, AIConversationRetention, AIGovernanceEvent
from app.domain.assistant import AssistantConversation
from app.domain.models import Transaction
from app.extensions import db


POLICY_VERSION = "ai-privacy-v1"
PURPOSES = {"hosted_assistant", "model_research"}
DEFAULT_RETENTION_DAYS = 7
ALLOWED_ACTION_PATHS = {
    "/", "/insights", "/schedules", "/wallet/history", "/wallet/report",
    "/wallet/send-money", "/wallet/cash-out", "/wallet/add-money", "/wallet/transfer-money",
    "/payments", "/payments/recharge", "/payments/pay-bill", "/payments/savings",
    "/payments/pay-later", "/payments/request-money", "/payments/financial-services",
    "/payments/other-services", "/profile/", "/profile/settings", "/assistant/privacy",
}
_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_OVERRIDE = (
    "ignore previous", "ignore all", "disregard previous", "override instructions",
    "forget your instructions", "developer mode", "you are now system", "system prompt",
    "developer prompt", "reveal prompt", "dump database", "database dump", "api key",
    "all users", "other users", "another user's", "someone else's", "exfiltrat",
    "আগের নির্দেশ", "পূর্বের নির্দেশ", "নির্দেশনা উপেক্ষা", "সিস্টেম প্রম্পট", "গোপন নির্দেশ",
    "সবার ব্যালেন্স", "অন্য ব্যবহারকারীর", "ডাটাবেস দেখাও", "সব ব্যবহারকারীর",
    "ager nirdesh", "ager instruction", "nirdesh bhule", "nirdesh upekkha",
    "shobar balance", "sobar balance", "onno user", "gopon prompt",
)
_ACTION_CLAIMS = re.compile(
    r"\b(?:i (?:have )?(?:sent|paid|transferred|executed|debited)|payment (?:is )?(?:completed|successful)|"
    r"funds (?:have been |were )?(?:sent|transferred)|transaction (?:is )?completed)\b|"
    r"আমি\s+(?:টাকা পাঠিয়েছি|পেমেন্ট করেছি|বিল দিয়েছি)|পেমেন্ট সম্পন্ন", re.I,
)
_ASK_SECRET = re.compile(
    r"(?:enter|send|share|provide|tell me|give me).{0,40}\b(?:otp|pin|password|cvv)\b|"
    r"(?:ওটিপি|পিন|পাসওয়ার্ড).{0,20}(?:দিন|দাও|পাঠান)", re.I,
)


def utc(value=None):
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def retention_days():
    return max(1, min(30, int(current_app.config.get("AI_CHAT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))))


def record_event(user_id, kind, reason=""):
    # No text, identifiers from the question, or account amounts enter this log.
    db.session.add(AIGovernanceEvent(user_id=user_id, kind=kind, reason=reason))


def _ensure_control(user_id):
    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError("AI privacy controls require PostgreSQL or SQLite.")
    db.session.execute(insert(AIConversationControl).values(user_id=user_id, generation=0, updated_at=utc())
                       .on_conflict_do_nothing(index_elements=["user_id"]))


def conversation_generation(user_id):
    _ensure_control(user_id)
    generation = db.session.query(AIConversationControl.generation).filter_by(user_id=user_id).scalar()
    db.session.commit()  # Never hold this control row across guidance or network.
    return generation


def claim_conversation_write(user_id, generation):
    # A guarded no-op UPDATE obtains the short write lock on both PostgreSQL and
    # SQLite. Erase and chat writes acquire this control before touching content.
    result = db.session.execute(update(AIConversationControl).where(
        AIConversationControl.user_id == user_id, AIConversationControl.generation == generation
    ).values(generation=AIConversationControl.generation), execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        db.session.rollback()
        return False
    return True


def invalidate_conversation(user_id):
    _ensure_control(user_id)
    db.session.execute(update(AIConversationControl).where(AIConversationControl.user_id == user_id)
                       .values(generation=AIConversationControl.generation + 1, updated_at=utc()),
                       execution_options={"synchronize_session": False})


def has_consent(user_id, purpose="hosted_assistant"):
    # Re-read authorization instead of trusting an ORM object cached before a
    # concurrent revocation. No consent may be supplied by the browser here.
    consent = AIConsent.query.filter_by(user_id=user_id, purpose=purpose).populate_existing().first()
    return bool(consent and consent.revoked_at is None and consent.policy_version == POLICY_VERSION)


def set_consent(user_id, purpose, *, accept=False, now=None):
    if purpose not in PURPOSES:
        raise ValueError("Choose a supported AI consent purpose.")
    if not accept:
        raise ValueError("Read the disclosure and explicitly accept before enabling this purpose.")
    if purpose == "hosted_assistant":
        invalidate_conversation(user_id)
    state = db.session.get(AIConsent, (user_id, purpose))
    if state is None:
        state = AIConsent(user_id=user_id, purpose=purpose, policy_version=POLICY_VERSION)
        db.session.add(state)
    state.policy_version = POLICY_VERSION
    state.granted_at = utc(now)
    state.revoked_at = None
    record_event(user_id, "consent_granted", purpose)
    db.session.commit()
    return state


def erase_conversation(user_id, *, invalidate=True):
    if invalidate:
        invalidate_conversation(user_id)
    counts = {"conversation": AssistantConversation.query.filter_by(user_id=user_id).delete(),
              "retention": AIConversationRetention.query.filter_by(user_id=user_id).delete()}
    return counts


def revoke_consent(user_id, purpose):
    if purpose not in PURPOSES:
        raise ValueError("Choose a supported AI consent purpose.")
    erased = erase_conversation(user_id) if purpose == "hosted_assistant" else {}
    state = db.session.get(AIConsent, (user_id, purpose))
    if state:
        state.revoked_at = utc()
    record_event(user_id, "consent_revoked", purpose)
    db.session.commit()
    return {"receipt_id": uuid4().hex, "purpose": purpose, "revoked": True, "erased": erased}


def erase_ai_data(user_id):
    counts = erase_conversation(user_id)
    counts["consents"] = AIConsent.query.filter_by(user_id=user_id).delete()
    counts["events"] = AIGovernanceEvent.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    # A content-free control counter is retained to invalidate in-flight writes.
    return {"receipt_id": uuid4().hex, "erased_at": utc().isoformat(), "erased": counts,
            "scope": "AI conversation, AI consents and AI governance events; wallet ledger retained",
            "retained_control": "Content-free erasure generation prevents in-flight requests from recreating erased chat; retained until account deletion"}


def prune_expired(user_id=None, *, now=None):
    now = utc(now)
    query = AIConversationRetention.query.filter(AIConversationRetention.expires_at <= now)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    expired = [row.user_id for row in query.all()]
    for wallet_id in expired:
        erase_conversation(wallet_id)
    # Legacy conversations without a TTL were created before this policy; erase
    # instead of allowing unlimited retention or guessing their creation date.
    legacy = AssistantConversation.query.filter(~AssistantConversation.user_id.in_(db.session.query(AIConversationRetention.user_id)))
    if user_id is not None:
        legacy = legacy.filter_by(user_id=user_id)
    legacy_ids = [row.user_id for row in legacy.all()]
    legacy_count = len(legacy_ids)
    for wallet_id in legacy_ids:
        erase_conversation(wallet_id)
    events = AIGovernanceEvent.query.filter(AIGovernanceEvent.created_at < now - timedelta(days=30))
    if user_id is not None:
        events = events.filter_by(user_id=user_id)
    event_count = events.delete(synchronize_session=False)
    db.session.commit()
    return {"expired_conversations": len(expired), "legacy_conversations": legacy_count, "expired_events": event_count}


def refresh_retention(user_id):
    row = db.session.get(AIConversationRetention, user_id)
    if row is None:
        row = AIConversationRetention(user_id=user_id)
        db.session.add(row)
    row.expires_at = utc() + timedelta(days=retention_days())


def privacy_state(user_id):
    control = AIConversationControl.query.filter_by(user_id=user_id).populate_existing().first()
    return {"hosted_assistant": has_consent(user_id), "model_research": has_consent(user_id, "model_research"),
            "policy_version": POLICY_VERSION, "retention_days": retention_days(),
            "retained_control": {"generation": control.generation, "updated_at": utc(control.updated_at).isoformat(),
                                 "purpose": "Prevent an in-flight request from recreating erased chat"} if control else None,
            "purposes": [{"purpose": row.purpose, "policy_version": row.policy_version,
                          "granted_at": utc(row.granted_at).isoformat(),
                          "revoked_at": utc(row.revoked_at).isoformat() if row.revoked_at else None}
                         for row in AIConsent.query.filter_by(user_id=user_id).all()]}


def normalized_text(content):
    content = unicodedata.normalize("NFKC", content).translate(_DIGITS).casefold()
    return " ".join(re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", content).split())


def injection_reason(content):
    value = normalized_text(content)
    if any(term in value for term in _OVERRIDE) or re.search(r"<(?:system|developer)>|\[system\]|\"role\"\s*:\s*\"system\"", value):
        return "instruction_override_or_private_data"
    if re.search(r"https?://|www\.|mailto:|javascript:", value):
        return "external_destination"
    return None


def redact_sensitive(content, user=None):
    content = unicodedata.normalize("NFKC", str(content)).translate(_DIGITS)
    if user:
        for value in (user.full_name, user.mobile, user.email):
            if value:
                content = re.sub(re.escape(value), "[private detail]", content, flags=re.I)
    content = re.sub(r"(?<!\d)(?:\+?88[ -]?)?01(?:[ -]?\d){9}(?!\d)", "[private detail]", content)
    content = re.sub(r"(?<!\d)(?:\d[ -]?){12,19}(?!\d)|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[private detail]", content)
    # The label is retained for context, while its nearby value is discarded.
    return re.sub(r"((?:password|otp|pin|cvv|passcode|পাসওয়ার্ড|ওটিপি|পিন)\s*(?:is|হলো|হল|amar|:|=|-)?\s*)[A-Za-z0-9]{3,}",
                  r"\1[private detail]", content, flags=re.I)


def output_is_safe(answer, user=None):
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 6000:
        return False
    if injection_reason(answer) or _ACTION_CLAIMS.search(normalized_text(answer)) or _ASK_SECRET.search(answer):
        return False
    if re.search(r"<[^>]+>|!\[|\[[^\]]+\]\(", answer):
        return False
    # Bangla digits are normalized by redaction; normalization itself must not
    # reject a benign Bangla answer that contains an ordinary currency amount.
    return redact_sensitive(answer, user) == unicodedata.normalize("NFKC", answer).translate(_DIGITS)


def allowlisted_links(links):
    allowed = []
    for link in links:
        if not isinstance(link, dict) or not isinstance(link.get("url"), str) or not isinstance(link.get("label"), str):
            continue
        parts = urlsplit(link["url"])
        if (not parts.scheme and not parts.netloc and not parts.fragment and parts.path in ALLOWED_ACTION_PATHS
                and link["url"].startswith("/") and not link["url"].startswith("//")
                and "\\" not in link["url"] and not re.search(r"%0[ad]|%2f|%5c", link["url"], re.I)):
            allowed.append({"label": link["label"][:100], "url": link["url"]})
    return allowed


def governed_research_export(user):
    """Only an explicit, user-initiated aggregate export; never model training."""
    if not has_consent(user.id, "model_research"):
        raise ValueError("Enable the separate model research consent before exporting research data.")
    from app.services.reporting_service import local_datetime
    daily = {}
    for tx in Transaction.query.filter_by(user_id=user.id, status="SUCCESS").all():
        key = local_datetime(tx.created_at).date().isoformat()
        row = daily.setdefault(key, {"date": key, "incoming": "0.00", "outgoing": "0.00"})
        field = "incoming" if tx.direction == "IN" else "outgoing"
        from decimal import Decimal
        row[field] = str(Decimal(row[field]) + tx.amount + (tx.fee or 0))
    data = [daily[key] for key in sorted(daily)]
    checksum = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"manifest": {"policy_version": POLICY_VERSION, "purpose": "model_research",
                         "source": "user_opt_in_wallet_aggregates", "exported_at": utc().isoformat(),
                         "data_sha256": checksum, "contains_direct_identifiers": False,
                         "training_approved": False, "automatic_training": False,
                         "review_required": "Consent/source verification, minimization, access, retention and held-out evaluation"},
            "daily_aggregates": data}
