# UpayX: a wallet that explains the numbers

**Hackathon feature guide and judge walkthrough · reviewed 2 October 2026 · Bangladesh time**

**Phase 2 · 7 October 2026:** start with [phase_2.md](phase_2.md) for the isolated judge demo, login, full database catalog and evidence. The product prioritizes weekly planning and recurring payments, with a learned forecast, consented pilot measurement, concurrent/failure verification, scoped APIs, PostgreSQL migrations, durable workers and privacy/security controls. See [feedback 1–4](docs/FEEDBACK_1_4.md) and [feedback 5–6](docs/FEEDBACK_5_6.md). The [original comments and scores](docs/JUDGE_FEEDBACK.md) remain unchanged; the seventh screenshot is pending. The source comparison and initial dataset snapshot below retain their original review date.

UpayX is an independently built Flask wallet prototype inspired by Bangladesh's upay experience. Its strongest story is a connected journey: understand your household's activity, plan upcoming commitments, complete a local demo payment, and trace the result into a chart, receipt and export. It is not affiliated with upay or UCB Fintech.

All balances, identities, transactions, prices, providers, bank destinations and credit terms in the supplied dataset are **synthetic demonstration data**. The app does not move real money, deliver SMS, verify National IDs, approve loans, dispense cash or connect to banks and billers. A successful status proves that the local demo operation was recorded.

For installation details, use [README.md](README.md). For every screen and workflow, use [USER_MANUAL.md](USER_MANUAL.md). This additional README explains what to emphasize, what is shared with the real product, and which claims the evidence supports.

## 1. What differs from the real upay app?

This comparison uses public product descriptions, not access to upay's private systems or a full installed-app audit. **“Not established in reviewed public descriptions” means an exact capability was not confirmed; it does not prove upay lacks it.** Features and availability can change after the review date.

| Capability | Reviewed official upay descriptions | This project's implementation and positioning |
| --- | --- | --- |
| Send Money, Add Money, agent/ATM cash out | Listed in the publisher's app description [S1] | Local wallet and mock external-source flows; familiar baseline, not a unique invention. |
| Recharge, bills, merchant payments | Listed in the publisher's app description [S1] | Recharge and category-specific demo bills; no connected merchant acquiring or billing network. |
| Bangla/English, cash-out fee assistance | Listed in the publisher's app description [S1] | Persistent language/theme controls and exact demo fee previews; usability strengths, not exclusive claims. |
| Transfer to bank/Visa | Listed on the official transfer page [S2] | Offline NPSB/BEFTN and Visa simulations, with fees and masked destination records. |
| Onboarding/security | Publisher describes NID registration and registered-device access [S1] | Fixed demo OTP, session ownership checks and CSRF protection; no production identity or device trust service. |
| Salary/remittance and travel bookings | Listed in the publisher's app description [S1] | Simulated incoming history and payment references; no live remittance, salary distribution or ticket inventory. |
| Explainable financial health calculations | Not established in reviewed public descriptions | A demonstration-specific planning layer; show its inputs, assumptions and links to evidence. |
| Four linked analytical charts with segment exports | Not established in reviewed public descriptions | Filtered bar, cumulative, spending pie and cumulative histogram views link to transactions and PDF/Excel exports. |
| Account-scoped conversational assistant with a local fallback | Not established in reviewed public descriptions | English/Bangla/romanized-Bangla app guidance, bounded own-account conversation and optional hosted AI. |
| Inspectable recurring-payment executor and complete offline database evidence | Not established in reviewed public descriptions | Due-only plans, receipts, source code, tests, labeled fixtures and database documentation make a reproducible demonstration. |

**Sources:** [S1: upay publisher listing on Google Play](https://play.google.com/store/apps/details?hl=en-US&id=bd.com.upay.customer); [S2: official upay bank/Visa transfer page](https://www.upaybd.com/products/utility/transfer-fund); [S3: official upay website](https://www.upaybd.com/). S1 identified UCB Fintech Company Limited as developer and displayed a 29 September 2026 update when reviewed. S3 is a product/source directory; its initial page rendered mainly navigation, so unrendered content was not used to infer missing capabilities.

## 2. Which creations are most extraordinary?

### Financial Health Center: the strongest new showcase

Open **Financial Health** at `/insights`. The safe-to-spend estimate subtracts recorded unpaid schedules and Pay Later amounts due within the next seven Bangladesh calendar days, including overdue items, from the current balance. Both automatic and manual schedules count; completed/cancelled items and successfully linked payments are excluded. The estimate is floored at zero, and a negative remainder becomes a visible funding gap. The screen shows the formula and each reserved commitment.

The same screen compares the balance with a persisted opening anchor plus successful incoming activity minus outgoing amounts and fees. A match is arithmetic consistency with that recorded anchor, not proof of bank settlement. Accounts without an anchor show that verification is unavailable. Last-30-day flow and average spending are labeled observed activity, not income or expense predictions.

Two transparent review rules link back to receipts: an unusually large same-service debit based on earlier payments, and two equal successful debits to the same counterparty within ten minutes. Neither rule declares fraud or changes a transaction. This combination of explanation, due-date context and inspectable evidence is the project's strongest distinct demonstration.

### Evidence-linked reports

The reports are an implemented showcase feature: choose a date, bill category, operation, direction or status; every chart and export follows those filters. Activate a bar, pie segment, legend or histogram selection to inspect the contributing transactions and download just that selection. Each record links to a branded PDF/JPG receipt. Education has separate school, college and university views.

This creates a visible chain from a claim such as “education is our largest spending category” to the records that justify it. Successful money out includes fees. Deferred purchases, pending plans, failed records and cancelled plans do not inflate completed wallet totals. Cumulative net change starts at zero and is labeled as period activity rather than current balance.

### A helpful assistant with controlled authority

The assistant answers app questions, explains fees and routes users to the right form. The isolated judge demo uses local guidance. Hosted AI in a separate environment requires explicit owner consent after disclosure and sends redacted questions, bounded history and minimal aggregates. Profile fields, recipient details, references and transaction notes are excluded from the account snapshot. Conversation history is limited to eight messages and seven days of inactivity; privacy settings support export, erasure and independent research consent.

The assistant cannot authorize or execute payments. The user reviews and submits the payment form. Demonstrate an education-fee question, follow its action, and open the resulting invoice receipt. Example prompts are in [AI_ASSISTANT_PROMPTS.txt](AI_ASSISTANT_PROMPTS.txt).

### Future commitments separated from today's money

Auto Pay creates one-time or monthly installments through the last day of the second upcoming calendar month. Monthly dates anchor to the originally chosen day and adjust for short months. Plans debit funds only when due and successfully processed. A pending installment has its own document; completion links it to its actual payment receipt.

Pay Later similarly separates a deferred purchase from a repayment. Savings stores a goal and estimate without taking deposits. This makes “planned,” “owed” and “already spent” visibly different.

### Demonstrable operation integrity

Send Money records matching outgoing and incoming references across two local wallets. Server checks reject blocked demo destinations even if a browser is bypassed. Wallet form tokens, bill invoices, scheduled installment claims and Pay Later repayments protect their supported repeated-operation paths. This is inspectable local behavior; it is not a claim of production fraud prevention, blockchain or live settlement guarantees.

## 3. How to make the presentation memorable

Lead with one household problem: **“Can I meet my upcoming commitments, and can I explain where my money went?”** Build the story around observable product behavior and evidence.

| Presentation priority | What to show | Why it strengthens a submission |
| --- | --- | --- |
| 1. Explainability | The Financial Health Center's inputs and calculation, then its source records | Makes the result understandable and auditable. |
| 2. Traceability | Chart segment → matching rows → receipt → filtered PDF/Excel | Shows a complete user journey with consistent totals. |
| 3. Local accessibility | Bangla interface, English/Bangla guidance, desktop and mobile layout | Connects the experience to its intended context. |
| 4. Reliable operations | Blocked destination rejection, future plan without an early debit, repayment with one receipt | Demonstrates failure handling alongside success. |
| 5. Reproducibility | Clearly labeled 120-day fixtures, code boundaries and database report | Allows reviewers to inspect and repeat the demonstration. |

These are strengths that judges can assess; no feature or document can guarantee a winning score. Avoid unsupported claims such as “upay has no analytics,” “bank-grade security,” “real customer data,” or “AI approves safe payments.” Use the public-source comparison above and the product's own limitations.

## 4. Complete implemented feature inventory

| Area | Included functionality |
| --- | --- |
| Access | Mobile login, signup, fixed demo OTP, logout and authenticated account ownership. |
| Dashboard | Current balance, Bangladesh calendar-day filters from 1–120 days, successful activity totals and linked service/report navigation. |
| Financial Health | Seven-day/overdue commitment reserve, explained safe-to-spend and funding gap, observed 30-day flow, opening-anchor ledger reconciliation and receipt-linked review signals. |
| Wallet | Two-wallet Send Money; Add Money from mock bank/card/agent; agent/ATM Cash Out; bank/Visa Transfer Money; fee/total/remaining-balance previews. |
| Payments | Five mobile operators with demo-prefix validation; 17 bill categories with ten example providers each; category-specific references and bill invoice receipts. |
| Financial services | Saved savings goals and estimates; deferred purchases and manual repayments; prepared money requests; recurring or one-time payment plans. |
| Reports | Date/direction/type/category/status/text/plan-mode filters, chart drilldowns, separate schedule totals, user-owned PDF/JPG receipts and filtered PDF/Excel exports. |
| QR instructions | Signed 15-minute operation codes, image/pasted-text reading, local server image fallback, and shareable money-request instructions. Reading only prepares a form. |
| Guidance | Account-scoped assistant, local fallback, optional hosted AI, service shortcuts and clear-chat action. |
| Navigation | Search across services/providers and own transactions; persistent unread notifications; receipt links; contextual Back links. |
| Personalization | Bangla/English; Light/Dark/System; editable profile details; raster photo resizing/cropping; saved notification preferences. |
| Architecture | Flask application factory, Blueprints, service layer, repository interfaces, SQLAlchemy, SQLite and composition-root dependency injection. |
| Evidence | Deterministic demo data, isolated regression tests, export/browser QA utilities and database documentation. |

Bill categories are Electricity, Gas, Internet, Water, TV Bill, Credit Card, Education, School, College, University, Traffic Fine, Toll Payment, Government Payment, Insurance, Donation, Ticket and Hotel. A ticket or hotel screen records payment against an existing demo reference; it does not search availability or issue a reservation.

## 5. A five-minute judge walkthrough

Use the seeded main account `01329097775` and demo OTP `123456`. Start with a clean demonstration so the account has its expected sample records.

The supplied 2 October scenario includes a **manual** DESCO plan for BDT 620 due 5 October and a pending Pay Later purchase for BDT 840 due 6 October. Financial Health therefore explains a BDT 1,460 reserve and a BDT 106,752.50 safe-to-spend estimate from a BDT 108,212.50 balance. It also contains labeled, legitimate synthetic recharge examples for comparing similar receipts and an unusually large amount. Explain these as review prompts, without inventing a fraud finding. On a later demonstration date, use the current displayed window and prepare a new due-soon manual plan if needed.

| Time | Action | Evidence to narrate |
| --- | --- | --- |
| 0:00–0:30 | Sign in, show Dashboard, select 120 days | “These are 120 days of labeled synthetic household activity; the balance is current, the statistics are filtered.” |
| 0:30–1:30 | Open Financial Health Center and inspect the explained result | “The estimate names each due commitment. Ledger arithmetic and receipt review signals have visible evidence.” |
| 1:30–2:20 | Open Report, select Electricity, activate a category/chart segment | “Every number has contributing transactions; download the same selection.” |
| 2:20–3:10 | Ask “How do I pay school fees?”, follow the action, record a small demo bill and inspect its receipt | “Guidance finds the right flow; a person confirms the local payment.” |
| 3:10–4:00 | Show a pending Auto Pay installment and click **Pay if due** before its due date | “A future commitment stays planned and does not debit today's wallet early.” |
| 4:00–4:35 | Enter blocked fixture `01944000099` on Send Money | “This local directory flag is enforced by the server, not just presented as a badge.” |
| 4:35–5:00 | Download a filtered report and show database documentation | “The demonstration is reproducible, clearly scoped, and leaves inspectable evidence.” |

Prepare downloaded examples in advance so browser download prompts do not interrupt the story. Keep the optional hosted assistant disabled if no provider/key is available; demonstrate the working local guide.

For the School step, choose **Demo School**, reference `DEMO-STUDENT-1001`, amount BDT 100 and a fresh provider invoice such as `JUDGE-EDU-001`. Its unregistered-reference warning is expected in the local directory. A previously used invoice must not be reused. This step changes demo balance/history; the static counts below describe the initial reset, before that payment. Electricity already has seeded records, so its initial chart drilldown does not require preparing a new bill.

## 6. Data and production boundaries

The requested refreshed history is a realistic synthetic demo, not real upay customer data. The supplied window is **5 June–2 October 2026 inclusive**, using Asia/Dhaka calendar dates. A labeled generated fixture is suitable for demonstrating filters, receipts, plans and reconciliation; it does not prove real-world adoption, model accuracy, fraud detection performance or business outcomes.

For an intentional reset, stop the local app/worker and run `python scripts/reset_demo_data.py --confirm --as-of 2026-10-02`; a scoped SQLite backup is preserved under `instance/backups`. Run `python scripts/export_database_pdf.py` to regenerate the [complete database report](output/pdf/UPAYX_DATABASE_REPORT.pdf). This administrator PDF includes every table and stored row/column, schemas, empty tables, repeated row numbers for wide tables, and an embedded exact JSON snapshot with a SHA-256 checksum. It is separate from the signed-in wallet's filtered report downloads.

The initial generated snapshot has **4 users, 345 transaction rows (208 for the main household), 18 tables and 913 total stored rows**. Its main wallet opens at BDT 12,450.00 and reconciles to BDT 108,212.50. The generated complete database PDF has 110 pages. These describe the initial snapshot; new payments, chat, profile edits and notification actions can change current records or counts.

The project remains a prototype with implemented one-use OTP boundaries, browser session revocation, scoped APIs, quotas, signed audit, field encryption, review signals and provider recovery. Contracted identity/SMS/payment connections, managed production operations, provider settlement validation and independent security assessment remain external work. Reported demo fees and savings/Pay Later estimates are code examples, not official upay prices or financial offers.

## 7. Engineering evidence

Key implementation files include [financial_health_service.py](app/services/financial_health_service.py), [reporting_service.py](app/services/reporting_service.py), [export_service.py](app/services/export_service.py), [schedule_service.py](app/services/schedule_service.py), [assistant_service.py](app/services/assistant_service.py), [wallet_service.py](app/services/wallet_service.py), [payment_plans_service.py](app/services/payment_plans_service.py) and [container.py](app/container.py). Read these alongside the [tests](tests/) when explaining the architecture.

Run the isolated regression suite with the installed project dependencies:

```powershell
python -m unittest discover -s tests -v
```

For export QA, run `python -m tests.export_preview`; for browser layout/interaction QA, run `python -m tests.browser_qa`. The isolated preview, `python -m tests.preview`, listens on port 5001 and does not use the regular project wallet database. These are verification tools; consult the execution output before claiming a check passed.
