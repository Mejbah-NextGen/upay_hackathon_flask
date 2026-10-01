# UpayX — Flask AI Hackathon Fintech Prototype

A responsive **desktop + mobile wallet web app** inspired by the supplied UI references. This is a hackathon/demo project only; it does not connect to real financial rails, SMS providers, banks, cards, or payment gateways.

## Features

- Passwordless mobile login + demo OTP
- Responsive desktop sidebar + mobile bottom navigation
- Dashboard with current wallet balance and history-based statistics
- Dashboard filters for any 1–90 calendar days, with Today / 7 / 30 / 90 day shortcuts
- Send Money
- Add Money
- Cash Out with demo fee calculation
- Mobile Recharge
- Bill Payment
- Separate payments, financial services and other services hubs
- Category-specific providers and references for utility bills and other payments
- Service, bill, provider and personal transaction search
- Transaction notifications with persistent unread state
- Transaction history with date, direction, type and text filters, fees and wallet changes
- Profile editing
- Saved notification preferences
- Savings contribution calculator and money request message preparation
- Demo seed account and transactions
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

### Demo login

- Mobile: `01329097775`
- OTP: `123456`

## Dashboard and services

The dashboard starts with today's activity. Choose any number of days from 1 to 90 or use a preset. Ranges include today and the previous selected calendar days in Bangladesh time (UTC+6). The balance card always shows the current wallet balance. Payments total only successful bill payments and mobile recharges; Money Out includes successful transfers, payments, cash-outs and their fees. History links retain the selected period.

Each bill link opens its selected category. Gas bills list gas companies, electricity bills list electricity providers, and recharge lists mobile operators. Changing the category updates the provider choices and reference label. Without JavaScript, the Update Category button loads the matching providers without moving any money. Provider names are demo examples; payments only update the local wallet and history.

Navbar search accepts service names, bill types, providers and transaction references. Search and notifications only show the signed-in user's transactions. Notifications have a persistent Mark All as Read action; their display can be disabled and re-enabled under Profile → Settings.

Send Money requires another account registered in this app and records matching debit/credit references in both wallets. Create a second demo account to test transfers. Add Money records its selected mock source. Cash Out charges 1.5%, rounded to the nearest paisa with halves rounded up, and validates the balance including the fee. Savings calculates contributions without moving funds. Request Money prepares a message for you to copy and share; it does not automatically send a request.

Existing accounts and transaction history are retained. The app creates the new notification and preference tables automatically on startup; a database reset is not required.

## Verification

Run the isolated regression suite:

```powershell
python -m unittest discover -s tests -v
node --check app/static/js/app.js
```

Tests use in-memory SQLite databases and do not change `instance/upay_hackathon.db`. They cover provider/category validation, date boundaries, user isolation, transaction totals, transfers, fees, search, notifications, preferences, authentication and CSRF protection.

For a separate browser preview with sample activity spread over 90 days:

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
