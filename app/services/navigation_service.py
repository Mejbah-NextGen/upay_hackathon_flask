import re
from datetime import datetime, timezone

from sqlalchemy import func, or_

from app.domain.models import Transaction
from app.domain.notifications import NotificationReadState
from app.extensions import db
from app.services.service_catalog import SERVICES


def search_terms(query):
    return re.findall(r"\w+", query.casefold())


def find_services(query):
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
        if all(term in text for term in terms):
            matches.append(service)
    return matches


def matching_transactions(user_id, query):
    result = Transaction.query.filter_by(user_id=user_id)
    terms = search_terms(query)
    if not terms:
        return result.filter(False)
    for term in terms:
        # contains(autoescape=True) treats any SQL wildcard characters literally.
        result = result.filter(or_(*[
            func.lower(column).contains(term, autoescape=True)
            for column in (
                Transaction.title, Transaction.counterparty, Transaction.reference,
                Transaction.kind, Transaction.status, Transaction.note,
            )
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
    return {
        "items": transactions.order_by(
            Transaction.created_at.desc(), Transaction.id.desc()
        ).limit(limit).all(),
        "unread_count": transactions.filter(Transaction.id > read_through).count(),
        "read_through": read_through,
    }


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
