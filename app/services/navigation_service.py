import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.domain.models import Transaction
from app.domain.notifications import NotificationReadState, NotificationReadReceipt
from app.extensions import db
from app.services.service_catalog import SERVICES


def service_return_target(value):
    """Accept an explicit app overview, preserving its filters across a service visit."""
    labels = {
        "/": "Dashboard", "/payments": "Payments",
        "/payments/financial-services": "Financial Services",
        "/payments/other-services": "Other Services", "/schedules": "Auto Pay",
        "/wallet/report": "Report", "/wallet/history": "Report", "/search": "Search",
    }
    if not isinstance(value, str) or len(value) > 500:
        return None
    if not value.startswith("/") or value.startswith("//") or "\\" in value or any(ord(c) < 32 for c in value):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.path not in labels:
        return None
    return {"href": value.rstrip("?"), "label": labels[parsed.path]}


def search_terms(query):
    return re.findall(r"[\w\u0980-\u09ff]+", query.casefold())


def find_services(query):
    from app.services.localization import translate
    terms = search_terms(query)
    if query and not terms:
        return []
    # The search field explicitly offers services; this term alone lists them all.
    terms = [term for term in terms if term not in {"service", "services"}]
    matches = []
    for service in SERVICES:
        keywords = service.get("keywords", ())
        if not isinstance(keywords, str):
            keywords = " ".join(keywords)
        text = " ".join([
            service.get("title", service.get("label", "")),
            service.get("description", ""), service.get("category", ""), keywords,
        ]).casefold()
        original_keywords = service.get("keywords", ())
        translated_values = [service.get("label", ""), service.get("description", "")]
        translated_values.extend(original_keywords.split() if isinstance(original_keywords, str) else original_keywords)
        text += " " + " ".join(translate(value) for value in translated_values).casefold()
        if all(term in text for term in terms):
            matches.append(service)
    return matches


def matching_transactions(user_id, query):
    from app.services.localization import BANGLA
    result = Transaction.query.filter_by(user_id=user_id)
    terms = search_terms(query)
    if not terms:
        return result.filter(False)
    for term in terms:
        variants = [term]
        if re.search(r"[\u0980-\u09ff]", term):
            variants += [key.casefold() for key, translated in BANGLA.items()
                         if term in search_terms(translated)][:32]
        # contains(autoescape=True) treats any SQL wildcard characters literally.
        result = result.filter(or_(*[
            func.lower(column).contains(value, autoescape=True)
            for column in (
                Transaction.title, Transaction.counterparty, Transaction.reference,
                Transaction.kind, Transaction.status, Transaction.note,
            )
            for value in variants
        ]))
    return result.order_by(Transaction.created_at.desc(), Transaction.id.desc())


def paginate_transactions(query, raw_page, per_page=20):
    """Bound page input to real results before SQLite receives an offset."""
    total = query.order_by(None).count()
    last_page = max(1, (total + per_page - 1) // per_page)
    try:
        page = int(raw_page or 1)
    except (TypeError, ValueError):
        page = 1
    page = max(1, min(page, last_page))
    return db.paginate(query.statement, page=page, per_page=per_page, error_out=False)


def notification_summary(user_id, limit=6):
    state = db.session.get(NotificationReadState, user_id)
    read_through = state.last_read_transaction_id if state else 0
    transactions = Transaction.query.filter_by(user_id=user_id)
    read_ids = {row[0] for row in db.session.query(NotificationReadReceipt.transaction_id)
                .filter(NotificationReadReceipt.user_id == user_id).all()}
    return {
        "items": transactions.order_by(
            Transaction.created_at.desc(), Transaction.id.desc()
        ).limit(limit).all(),
        "unread_count": transactions.filter(Transaction.id > read_through,
                                             ~Transaction.id.in_(read_ids)).count(),
        "read_through": read_through,
        "read_ids": read_ids,
    }


def mark_notification_read(user_id, transaction_id):
    """Mark precisely the opened transaction, without consuming newer alerts."""
    transaction = Transaction.query.filter_by(user_id=user_id, id=transaction_id).first()
    if transaction is None:
        return None
    if db.session.get(NotificationReadReceipt, (user_id, transaction_id)) is None:
        db.session.add(NotificationReadReceipt(user_id=user_id, transaction_id=transaction_id))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if db.session.get(NotificationReadReceipt, (user_id, transaction_id)) is None:
                raise
    return transaction


def mark_notifications_read(user_id):
    latest = db.session.query(func.max(Transaction.id)).filter(Transaction.user_id == user_id).scalar() or 0
    state = db.session.get(NotificationReadState, user_id)
    if state is None:
        state = NotificationReadState(user_id=user_id, last_read_transaction_id=latest)
        db.session.add(state)
    else:
        state.last_read_transaction_id = max(state.last_read_transaction_id, latest)
    state.updated_at = datetime.now(timezone.utc)
    db.session.commit()
