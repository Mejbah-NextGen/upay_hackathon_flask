# UpayX — Flask AI Hackathon Fintech Prototype

A responsive **desktop + mobile wallet web app** inspired by the supplied UI references. This is a hackathon/demo project only; it does not connect to real financial rails, SMS providers, banks, cards, or payment gateways.

## Features

- Passwordless mobile login + demo OTP
- Responsive desktop sidebar + mobile bottom navigation
- Dashboard with current wallet balance and history-based statistics
- Dashboard filters for any 1–120 Bangladesh calendar days
- Send Money
- Add Money
- Cash Out with demo fee calculation
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
- Savings contribution calculator and money request message preparation
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

The new dependencies are ReportLab, OpenPyXL, Pillow, PyMuPDF and HarfBuzz. Run `pip install -r requirements.txt` when upgrading an existing installation. The project database creates the new profile, recipient and scheduled-payment tables automatically; existing accounts, balances and transaction records are retained.

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

Startup safely adds missing demo transactions for each of the latest 120 calendar days, covering all six ledger operation types and bill categories. Imported records are labeled with `DEMO120-` references and explanatory notes. They are sample history added alongside the demo opening balance, so seeding does not recompute or overwrite existing balances. Data is retained beyond 120 days as well; nothing is automatically deleted. Repeated startup does not duplicate the same dated fixture.

## Auto Pay

Open **Auto Pay** to schedule Send Money, Recharge or Bill Payment. Choose a first date, one-time or monthly frequency, and automatic or manual payment mode. The horizon ends on the last day of the second upcoming calendar month. Monthly installments retain the chosen day, adjusting for shorter months. Review the dates and total before saving. Plans debit the wallet only when due, with sufficient balance and valid recipients; failed plans retain an explanation and do not deduct funds. Cancel pending plans individually. Four labeled demonstration installments are added across the next two months.

Due automatic installments run when their owner opens the app. For processing even while nobody is browsing, run the separate demo worker:

```powershell
.venv\Scripts\python.exe -m flask --app run run-due-payments --watch --interval 30
```

For one pass, omit `--watch`. The page's **Process Due Auto Pay** button uses the same executor. Each installment is claimed and recorded atomically, preventing duplicate processing. `flask --app run seed-demo-operations` idempotently adds missing fixtures.

## Profile and app assistant

Profile groups your account overview and editable full name, nickname, email, address and picture. JPG, PNG and WebP pictures up to 5 MB are validated, resized, stripped of metadata and stored in a dedicated database table. Uploaded pictures are served only to their owner.

The assistant beside Notifications explains services, reports, recipient checks, fees and Auto Pay, and summarizes the signed-in user's balance and spending. A local app guide works without a key. To enable the hosted AI, copy `.env.example` to `.env`, set `OPENAI_API_KEY` and optionally `ASSISTANT_MODEL`, then restart. It uses the [OpenAI Responses API](https://developers.openai.com/api/docs/guides/text) with `store: false`. Questions, bounded chat history and account aggregates are sent to OpenAI; profile fields, recipient names, account numbers and transaction notes are excluded from the account snapshot. The assistant never executes payments. A provider failure falls back to the local guide.

Operation screens have logical Back links. Sidebar overview pages hide the link, and returning never depends on browser history that could lead to the login screen.

### Demo login

- Mobile: `01329097775`
- OTP: `123456`

## Dashboard and services

The dashboard starts with today's activity. Choose any number of days from 1 to 120 or use a preset. Ranges include today and the previous selected calendar days in Bangladesh time (UTC+6). The balance card always shows the current wallet balance. Payments total only successful bill payments and mobile recharges; Money Out includes successful transfers, payments, cash-outs and their fees. Report links retain the selected period.

Each bill link opens its selected category. Gas bills list gas companies, electricity bills list electricity providers, and recharge lists mobile operators. Changing the category updates the provider choices and reference label. Without JavaScript, the Update Category button loads the matching providers without moving any money. Provider names are demo examples; payments only update the local wallet and history.

Navbar search accepts service names, bill types, providers and transaction references. Search and notifications only show the signed-in user's transactions. Notifications have a persistent Mark All as Read action; their display can be disabled and re-enabled under Profile → Settings.

Send Money requires another account registered in this app and records matching debit/credit references in both wallets. Create a second demo account to test transfers. Add Money records its selected mock source. Cash Out charges 1.5%, rounded to the nearest paisa with halves rounded up, and validates the balance including the fee. Savings calculates contributions without moving funds. Request Money prepares a message for you to copy and share; it does not automatically send a request.

Existing accounts and transaction history are retained. The app creates the new notification and preference tables automatically on startup; a database reset is not required.

## Verification

Run the isolated regression suite:

```powershell
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node --check app/static/js/app.js
```

Tests use in-memory SQLite databases and do not change `instance/upay_hackathon.db`. They cover provider/category validation, date boundaries, user isolation, transaction totals, transfers, fees, search, notifications, preferences, authentication, CSRF protection, profile upload validation, recipient blocking, due-only scheduled payments, report formats, PDF pagination, Excel formulas/cached totals and assistant privacy. The development dependencies include PDF parsing and rendering tools for export QA.

Generate isolated sample exports and page images for visual review:

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

Stop the app and delete:

```text
instance/upay_hackathon.db
```

Then run the app again. The demo account and sample transactions will be recreated.

## Hackathon notes

For a real production wallet, replace the demo implementations with secure integrations for KYC, OTP/SMS, banking/payment rails, transaction limits, encryption/key management, audit logging, fraud detection, idempotency, rate limiting, reconciliation, monitoring, and regulatory compliance.
