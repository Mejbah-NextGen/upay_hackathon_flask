"""Isolated browser verification for feedback 1–4. No normal wallet DB writes."""

import json
import logging
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from app import create_app
from app.domain.models import User
from app.domain.pilot import PilotEvent, PilotFeedback, PilotParticipant
from app.extensions import db
from tests.helpers import TestConfig


class BrowserFeedbackConfig(TestConfig):
    WTF_CSRF_ENABLED = True
    SCHEDULE_AUTO_RUN_ON_REQUEST = False


def run():
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app = create_app(BrowserFeedbackConfig)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    output = Path("tmp/feedback-qa")
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 960})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin + "/auth/login")
            page.locator("[name=mobile]").fill("01329097775")
            page.locator(".auth-card button[type=submit]").click()
            page.locator("[name=otp]").fill("123456")
            page.locator(".auth-card button[type=submit]").click()
            page.wait_for_url(origin + "/")
            page.goto(origin + "/pilot")
            page.locator("[name=consent]").check()
            page.get_by_role("button", name="Join planning pilot", exact=True).click()
            page.wait_for_url(origin + "/pilot")
            with app.app_context():
                user_id = User.query.filter_by(mobile="01329097775").one().id
                participant = db.session.get(PilotParticipant, user_id)
                assert participant.data_source == "DEMO"
                participant.variant = "control"
                db.session.commit()
            page.goto(origin + "/insights?variant=treatment")
            assert page.locator("#forecastTitle").count() == 0
            assert page.locator("#planningReviewTitle").count() == 1
            with app.app_context():
                db.session.get(PilotParticipant, user_id).variant = "treatment"
                db.session.commit()
            page.goto(origin + "/insights")
            assert page.locator("#forecastTitle").count() == 1
            assert page.get_by_text("Expected everyday money out", exact=True).count() == 1
            page.locator("[name=acknowledge]").check()
            page.get_by_role("button", name="Record planning review", exact=True).click()
            page.wait_for_url(origin + "/insights")
            page.reload()
            with app.app_context():
                assert PilotEvent.query.filter_by(user_id=user_id, kind="TASK_STARTED", task_key="financial_health").count() == 1
                assert PilotEvent.query.filter_by(user_id=user_id, kind="TASK_COMPLETED", task_key="financial_health").count() == 1
            page.goto(origin + "/pilot")
            page.locator("#researchProblem").select_option("both")
            page.locator("#researchUseful").select_option("5")
            page.locator("#researchEase").select_option("4")
            page.locator("#researchMissed").fill("1")
            page.locator("#researchComment").fill("Synthetic browser QA response only")
            page.get_by_role("button", name="Record research response", exact=True).click()
            page.wait_for_url(origin + "/pilot")
            assert page.get_by_text("Synthetic browser QA response only", exact=True).count() == 1
            with app.app_context():
                assert PilotFeedback.query.filter_by(user_id=user_id, kind="RESEARCH").count() == 1
                previous_balance = db.session.get(User, user_id).balance
            page.goto(origin + "/schedules")
            page.locator("[name=kind]").select_option("BILL_PAYMENT")
            page.locator("[name=category]").select_option("electricity")
            page.locator("[name=provider]").select_option("DESCO Electricity")
            page.locator("[name=recipient_number]").fill("DEMO-METER-1001")
            page.locator("[name=amount]").fill("25")
            page.locator("[name=frequency]").select_option("MONTHLY")
            page.get_by_role("button", name="Save Payment Plan", exact=True).click()
            page.wait_for_url(origin + "/schedules")
            with app.app_context():
                assert db.session.get(User, user_id).balance == previous_balance
                assert PilotEvent.query.filter_by(user_id=user_id, kind="TASK_COMPLETED", task_key="recurring_payment").count() == 1
            for language in ("en", "bn"):
                page.goto(origin + "/")
                page.locator("#navbarLanguage").select_option(language)
                page.wait_for_function("language => document.documentElement.lang === language", arg=language)
                for width in (320, 375, 768, 1440):
                    page.set_viewport_size({"width": width, "height": 900})
                    for path in ("/", "/insights", "/pilot", "/schedules"):
                        response = page.goto(origin + path, wait_until="load")
                        page.evaluate("() => new Promise(resolve => requestAnimationFrame(resolve))")
                        scroll = page.evaluate("document.documentElement.scrollWidth")
                        record = {"language": language, "viewport": width, "path": path,
                                  "status": response.status, "scroll_width": scroll}
                        checks.append(record)
                        if response.status != 200 or scroll > width + 1:
                            errors.append(record)
                        if path == "/pilot" and not page.locator(".pilot-evidence .table-wrap").evaluate("e => e.scrollWidth <= e.clientWidth + 1"):
                            errors.append({**record, "error": "Study denominators require horizontal scrolling"})
                        if width in (320, 1440) and path in ("/insights", "/pilot"):
                            page.screenshot(path=str(output / f"{language}-{width}-{path[1:]}.png"), full_page=True)
            browser.close()
    finally:
        server.shutdown()
        worker.join(timeout=5)
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
    result = {"checks": checks, "errors": errors,
              "flows": ["CSRF-protected login", "consented demo enrolment", "controlled model exposure",
                        "planning acknowledgement and refresh", "research response", "recurring plan without debit"]}
    (output / "browser-feedback-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{len(checks)} new-feature browser checks; {len(errors)} errors; 6 flows verified.")
    if errors:
        raise AssertionError(errors)


if __name__ == "__main__":
    run()
