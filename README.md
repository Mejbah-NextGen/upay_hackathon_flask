# UpayX — Flask AI Hackathon Fintech Prototype

A responsive **desktop + mobile wallet web app** focused on **weekly financial planning and recurring payments**. This is a hackathon/demo project only; it does not connect to real financial rails, SMS providers, banks, cards, or payment gateways.

## Feedback 1–4 update

The dashboard now leads with two planning tasks. Financial Health adds a trained, local seven-day spending forecast alongside its explained commitment calculation. A consented randomized pilot records task outcomes, simulated payment completion, support feedback and retention with explicit denominators and demo/verified-research separation. Concurrent database and injected failure tests exercise the critical payment paths.

See [feedback implementation and judge walkthrough](docs/FEEDBACK_1_4.md), [model methodology and evaluation](docs/MODEL_CARD.md), [pilot protocol](docs/PILOT_PROTOCOL.md) and [reliability evidence](docs/RELIABILITY.md). The existing dataset is preserved. Model validation is synthetic; real customer impact remains to be measured through the pilot.

## Competition package and new Financial Health Center

- [Competition README](README_LEGENDARY.md): researched comparison with the real Bangladesh upay app, implemented differentiators, judging evidence and a five-minute demo.
- [Complete user manual](USER_MANUAL.md): setup, every service, reports, financial insights, troubleshooting and administrator tasks.
- [Complete database PDF](output/pdf/UPAYX_DATABASE_REPORT.pdf): every table, row and stored column, schema definitions, page directory and an embedded exact JSON snapshot.

Open **Financial Health** from the sidebar or Dashboard to see the next seven calendar days' payment reserves, an explained safe-to-spend estimate, 30-day cash flow, review signals for unusual or closely repeated payments, and reconciliation against a separately recorded opening balance. Signals invite receipt review; they do not decide whether a payment is fraud. All views use the signed-in account's data.

The replacement dataset is **realistic synthetic demo data**, approved for this hackathon, spanning **5 June through 2 October 2026** in Bangladesh time. It contains no real upay customer records. Its opening balances and successful ledger effects reconcile with the stored wallet balances. Repeat startup preserves the dataset and the user's later activity.

## Features

- Passwordless mobile login + demo OTP
- Responsive desktop sidebar + mobile bottom navigation
- Dashboard with current wallet balance and history-based statistics
- Dashboard filters for any 1–120 Bangladesh calendar days
- Send Money
- Add Money
- Cash Out through Agent or ATM, with exact fees, total debit and remaining balance previews
- Separate bank/Visa Transfer Money, with NPSB and BEFTN (BFTN alias) methods
- Bangla/English language and Light/Dark/System theme controls in the navbar
- Mobile Recharge
- Bill Payment
- Separate payments, financial services and other services hubs
- Category-specific providers and references for utility bills and other payments
- Service, bill, provider and personal transaction search
- Transaction notifications with persistent unread state
- Report with date range, direction, type, status and text filters, fees and wallet changes
- Individual PDF/JPG receipts and successful transaction summaries
- Filtered Excel/PDF exports with final summaries and page numbers
- Recipient name and authorizing provider lookup with server-side blocked-number checks
- Profile pictures, nickname, address and contact editing
- One-time plans and monthly Auto Pay for the next two calendar months
- App assistant beside Notifications, with optional OpenAI integration
- Saved notification preferences
- Saved fixed-contribution savings plans with tenure and a prorated demo 10% annual estimate
- Pay Later with a demo credit limit, due dates and idempotent wallet repayment
- Signed QR instructions with browser-independent image decoding and shareable money requests
- Bar, cumulative, pie and cumulative histogram report visualizations using the same filters
- Persisted, labeled 120-day demo transaction history and upcoming demo installments
- SQLite database
- CSRF protection
- Application factory + Blueprints
- Repository interfaces + service layer + **IoC container / dependency injection**

## IoC / dependency architecture

```text
HTTP Route / Blueprint
        ↓
IoC Container resolves Service
        ↓
Application Service
        ↓
Repository Interface
        ↓
SQLAlchemy Repository
        ↓
SQLite Database
```

The routes do not create database repositories or business services directly. `app/container.py` is the composition root and wires the concrete implementations together.

## Project structure

```text
upay_hackathon_flask/
├── run.py
├── config.py
├── requirements.txt
├── README.md
├── instance/
└── app/
    ├── __init__.py
    ├── extensions.py
    ├── container.py
    ├── auth_helpers.py
    ├── domain/
    │   └── models.py
    ├── repositories/
    │   ├── interfaces.py
    │   └── sqlalchemy.py
    ├── services/
    │   ├── auth_service.py
    │   ├── wallet_service.py
    │   ├── payment_service.py
    │   ├── profile_service.py
    │   └── exceptions.py
    ├── blueprints/
    │   ├── auth/
    │   ├── dashboard/
    │   ├── wallet/
    │   ├── payments/
    │   └── profile/
    ├── templates/
    └── static/
        ├── css/
        ├── js/
        └── img/
```

## Run locally

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Open: `http://127.0.0.1:5000`

Dependencies include ReportLab, OpenPyXL, Pillow, PyMuPDF, HarfBuzz, pillow-heif and zxing-cpp. Run `pip install -r requirements.txt` when upgrading an existing installation, then restart the app. New tables are created automatically; existing accounts, balances and transaction records are retained. No database reset is needed.

## Reports and receipts

The former History option is now **Report**. Both `/wallet/report` and the legacy `/wallet/history` open it. Filter by calendar days (up to 120), explicit start/end dates, direction, operation, status or search text. Export downloads the same filtered rows as a formatted **Excel (.xlsx)** workbook or **PDF**, with transaction references, counterparties, amounts, fees, status, wallet changes, documentation, a final summary and page numbers. Excel sheets include print areas, repeated headers and page footers.

Each transaction has a **Print / Receipt** action. Successful Send Money, Add Money, Cash Out, Recharge and Bill Payment open their summary automatically. Choose **PDF** or **JPG**, then download. Scheduled installments also have PDF/JPG plan documents; completed plans link to the actual transaction receipt. Pending, failed and cancelled plans are clearly labeled and are excluded from completed wallet totals.

History range shortcuts apply to past ledger records. Explicit start/end dates also filter plans by their **due date**. Scheduled totals describe future commitments separately, so they do not count as money already spent. Totals count successful transactions only and include outgoing fees.

## Recipients and demo data

After entering a recipient number or bill reference, payment forms show the registered name, authorizing operator/provider, **Not registered**, or **Blocked number**. Send Money requires another wallet in this database. Other mock payments can use an unregistered number with a visible warning; blocked records are always rejected on the server, including scheduled execution. This directory is local demo data, not a live identity or fraud service.

Try these examples:

| Operation | Number / account | Result |
| --- | --- | --- |
| Send Money | `01944000001` | Demo Recipient Ayesha |
| Cash Out | `01944000002` | Demo Authorized Agent |
| Recharge | `01944000003` | Demo Subscriber Rafi |
| Any mobile operation | `01944000099` | Blocked number |
| DESCO Electricity | `DEMO-METER-1001` | Demo Household Electricity |
| Titas Gas | `DEMO-GAS-1001` | Demo Household Gas |
| Bill payment | `DEMO-BLOCKED-1001` | Blocked account |

Startup adds missing initial demo history for a new legacy demo wallet without changing an existing balance. An existing fixture window is preserved rather than extended on every restart. The explicit reset command below creates the richer, reconciled 120-day synthetic dataset with provenance, independent opening balances and related-table fixtures; it replaces previous active database records after backing them up.

## Auto Pay

Open **Auto Pay** to schedule Send Money, Recharge or Bill Payment. Choose a first date, one-time or monthly frequency, and automatic or manual payment mode. The horizon ends on the last day of the second upcoming calendar month. Monthly installments retain the chosen day, adjusting for shorter months. Review the dates and total before saving. Plans debit the wallet only when due, with sufficient balance and valid recipients; failed plans retain an explanation and do not deduct funds. Cancel pending plans individually. Four labeled demonstration installments are added across the next two months.

Due automatic installments run when their owner opens an eligible app page; the Financial Health page stays read-only. For processing even while nobody is browsing, run the separate demo worker:

```powershell
.venv\Scripts\python.exe -m flask --app run run-due-payments --watch --interval 30
```

For one pass, omit `--watch`. The page's **Process Due Auto Pay** button uses the same executor. Each installment is claimed and recorded atomically, preventing duplicate processing. `flask --app run seed-demo-operations` idempotently adds missing fixtures.

## Profile and app assistant

Profile groups your account overview and editable full name, nickname, email, address and picture. Upload JPG, PNG, WebP, GIF, BMP, TIFF, ICO, AVIF, HEIC/HEIF, JPEG2000, QOI, PSD, TGA or PPM up to 5 MB and 16 megapixels. Choose an output size of 128, 256, 512 or 1024 pixels, fit the full picture or crop a square with horizontal/vertical positioning. The server validates and resizes the picture, uses the first animation frame, corrects EXIF orientation, strips metadata and stores a private JPEG. Some browsers cannot preview HEIC; server decoding still works after installing requirements. SVG and camera RAW formats are not supported.

The assistant beside Notifications explains services, reports, recipient checks, fees and Auto Pay, and summarizes the signed-in user's balance and spending. A local app guide works without a key. To enable the hosted AI, copy `.env.example` to `.env`, set `OPENAI_API_KEY` and optionally `ASSISTANT_MODEL`, then restart. It uses the [OpenAI Responses API](https://developers.openai.com/api/docs/guides/text) with `store: false`. Questions, bounded chat history and account aggregates are sent to OpenAI; profile fields, recipient names, account numbers and transaction notes are excluded from the account snapshot. The assistant never executes payments. A provider failure falls back to the local guide.

Operation screens have logical Back links. Dashboard service links return to the Dashboard with its selected day filter, including education payments. Sidebar overview pages hide the link, and returning never depends on browser history that could lead to the login screen.

### Demo login

- Mobile: `01329097775`
- OTP: `123456`

## Dashboard and services

The dashboard starts with today's activity. Choose any number of days from 1 to 120 or use a preset. Ranges include today and the previous selected calendar days in Bangladesh time (UTC+6). The balance card always shows the current wallet balance. Payments total only successful bill payments and mobile recharges; Money Out includes successful transfers, payments, cash-outs and their fees. Report links retain the selected period.

Each bill link opens only its selected category and matching providers. The generic Pay Bill page lets you choose a category; changing it updates the provider choices and reference label. Without JavaScript, the Update Category button loads the matching providers without moving any money. Recharge validates the operator against the demo number prefix: 013/017 Grameenphone, 014/019 Banglalink, 015 Teletalk, 016 Airtel and 018 Robi. This demo uses prefixes and does not resolve ported numbers. Provider names are demo examples; payments only update the local wallet and history.

Navbar search accepts service names, bill types, providers and transaction references. Search and notifications only show the signed-in user's transactions. Opening a notification or its receipt marks only that alert read; Mark All as Read handles the remaining alerts. Notification counts refresh when returning with Browser Back or switching tabs. Language appears after Notifications and before the single Profile link. The phone number appears beside Profile. Display preferences persist across login sessions. Notification display can be disabled under Profile → Settings.

Send Money requires another registered account and records matching debit/credit references in both wallets. Transfer Money has separate bank NPSB/BEFTN and Visa destinations; all rails are offline demonstrations. Add Money requires a demo bank/account/holder, checksum-valid card/holder, or agent number. Stored bank and card numbers show only their last four digits. Agent Cash Out charges 1.5%; ATM charges 1%, accepts multiples of BDT 500 up to BDT 20,000, and lists 12 demo locations. Fees round to the nearest paisa with halves rounded up; total deduction and remaining balance include the fee. Wallet forms and bill invoices protect repeated submissions from duplicate debits.

Savings saves a fixed contribution and 1–120 month tenure, without moving funds. Its demo annual simple return is 10%, prorated across beginning-of-month installments: `monthly × 0.10 × months × (months + 1) / 24`. Pay Later records deferred purchases against a BDT 5,000 demo limit with 7/14/30 day repayment dates and zero demo fees/interest; only repayment deducts balance. Request Money prepares a one-view message and a shareable signed QR, with a clear action.

The 17 bill categories each offer 10 example providers; School, College and University are separate options. Bill invoices retain the account, provider invoice, generated invoice number and transaction ID, including PDF/JPG receipts. Four report charts use exactly the displayed filters, exclude unsuccessful records and include outgoing fees. Cumulative net change starts at zero and does not represent the current balance.

Tap, click or keyboard-activate a chart bar, pie portion or legend to open its transactions and download that selection as Excel or PDF. Education bill categories have their own portions. Auto Pay's Open Report includes only automatic plans and their linked transactions; its exports retain that filter. PDF reports and transaction/plan receipts show the UpayX logo on every page. The Dashboard places its welcome card and date filters above the summary cards at every screen size.

QR codes expire in 15 minutes and only prepare forms. Bill/cash instructions are scoped to their creator; money-request codes can fill another wallet's Send Money form. Image reading falls back to the local server when a browser has no BarcodeDetector. The assistant uses a bounded server-owned conversation, provides focused actions, and answers only about the app and the authenticated account. Clear Chat clears both the visible chat and stored conversation.

The assistant recognizes education fee questions, explains the applicable demo charge and opens the correct education form. Try the English, Bangla and romanized Bangla examples in [AI_ASSISTANT_PROMPTS.txt](AI_ASSISTANT_PROMPTS.txt).

All code defaults, demo recipients and fraud flags, bank/ATM examples, fees, savings/credit terms and provider choices are documented in [DEMO_DATA.txt](DEMO_DATA.txt). Regenerate with `python scripts/generate_demo_reference.py`; the generator never reads the account database or environment secrets.

Existing accounts and transaction history are retained. The app creates the new notification and preference tables automatically on startup; a database reset is not required.

## Verification

Run the isolated regression suite:

```powershell
pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check app/static/js/app.js
node --check app/static/js/ui.js
node --check app/static/js/wallet.js
node --check app/static/js/reports.js
```

Regression tests use in-memory SQLite or disposable files under the workspace and do not change `instance/upay_hackathon.db`. They cover provider/category validation, date boundaries, user isolation, transaction totals, transfers, fees, search, notifications, preferences, authentication, CSRF protection, profile upload validation, recipient blocking, due-only scheduled payments, report formats, PDF pagination, Excel formulas/cached totals, assistant privacy, financial insights and complete database exports. The dependencies include PDF parsing and rendering tools for export QA.

Generate isolated sample exports and page images for visual review:

For automated desktop/tablet/mobile layout and interaction checks, run `python -m tests.browser_qa`. It uses an isolated in-memory database and headless Chrome (install Chrome first), checks English and Bangla at 320, 375, 768, 1024 and 1440 pixels, and saves screenshots/results under `tmp/browser-qa`.

```powershell
python -m tests.export_preview
```

Files are saved under `tmp/export-qa`. The PDF report uses A4 landscape pages; Excel detail sheets use A3 landscape for readable printing, with an A4 summary. Receipts share one PDF layout with text shaping for supported fonts, and JPG downloads render the same pages.

For a separate preview with 120 days of demo activity and upcoming plans:

```powershell
python -m tests.preview
```

Open `http://127.0.0.1:5001` and use the demo login above. The preview uses a temporary in-memory database, leaving your normal project data untouched.

## Reset demo database

Stop the app and any Auto Pay worker, then run the explicit reset command:

```powershell
python scripts/reset_demo_data.py --confirm --as-of 2026-10-02
```

This replaces all active records in the project's local SQLite database and writes a recovery backup under `instance/backups/`. It creates a deterministic 120-day household dataset with clearly labelled synthetic records, supporting fixtures and ledger anchors. Omit `--as-of` to use the current Bangladesh date. Normal startup never performs this reset.

Regenerate the complete administrator PDF after changing the database:

```powershell
python scripts/export_database_pdf.py
```

The exporter reads SQLite directly in read-only mode without starting the app or inserting fixtures. It includes all accounts and all tables, including empty tables, and verifies database integrity and the embedded snapshot checksum. Customer Report downloads remain scoped to the signed-in user's filtered transactions.

## Hackathon notes

For a real production wallet, replace the demo implementations with secure integrations for KYC, OTP/SMS, banking/payment rails, transaction limits, encryption/key management, audit logging, fraud detection, idempotency, rate limiting, reconciliation, monitoring, and regulatory compliance.
