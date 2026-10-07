# UpayX user manual

**Version reviewed: 2 October 2026 · local hackathon prototype · Bangladesh time (UTC+6)**

This manual covers the implemented screens, demo money rules and project maintenance commands. All supplied account activity is synthetic. Wallet success messages mean the local database was updated; no real bank, mobile operator, biller, lender or cash machine receives an instruction.

For a feature comparison and presentation script, see [README_LEGENDARY.md](README_LEGENDARY.md). For the original project overview, see [README.md](README.md). Example prices and recipients are also listed in [DEMO_DATA.txt](DEMO_DATA.txt).

## 1. Start the project

In PowerShell, from the project directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

If `.venv` already exists, activate it and install the requirements. Open `http://127.0.0.1:5000`. Keep the terminal running while using the app. Press `Ctrl+C` in that terminal to stop the server. Restart after changing environment settings or dependencies.

The default SQLite file is `instance/upay_hackathon.db`. `DATABASE_URL` can select another database; maintenance commands must target the intended local file. `APP_NAME`, `SECRET_KEY` and `DEMO_OTP` are configurable in `.env`; use `.env.example` as the configuration reference.

### Demo accounts and references

| Purpose | Value | How it behaves |
| --- | --- | --- |
| Main account | `01329097775` | Main synthetic household history. |
| Demo OTP | `123456` | Default shared demonstration code; not sent by SMS. |
| Wallet recipient | `01944000001` | Demo Recipient Ayesha; can receive local Send Money. |
| Sender wallet | `01944000004` | Demo Sender Karim. |
| Landlord wallet | `01944000005` | Demo Landlord Rahman. |
| Agent | `01944000002` | Demo Authorized Agent. |
| Recharge subscriber | `01944000003` | Demo Subscriber Rafi; choose Banglalink. |
| Blocked mobile | `01944000099` | Mock block flag; applicable forms reject it. |
| Electricity account | `DEMO-METER-1001` | Choose DESCO Electricity. |
| Gas account | `DEMO-GAS-1001` | Choose Titas Gas. |
| Blocked bill reference | `DEMO-BLOCKED-1001` | Mock block flag; bill payment is rejected. |
| Example bank account | `1234567890` | Use only with a listed demo bank and holder name. |
| Example card | `4111 1111 1111 1111` | Checksum-valid demo card; no real card charging. |

## 2. Sign in, create an account and sign out

1. On **Login**, enter a registered mobile number and continue.
2. On the OTP page, enter the demo code displayed by the app. The default is `123456`.
3. After verification, the Dashboard opens. You can sign in to the recipient wallet to inspect its received transfer history.
4. To create another wallet, open **Signup**, provide a full name, unused Bangladesh mobile number and optional email, then complete the demo OTP step. New signup wallets receive a synthetic BDT 5,000 opening balance.
5. Use **Logout** in the navigation to end the session.

The **Verified Account** badge indicates this prototype's local flag. It is not a completed real-world KYC check. The profile mobile number identifies the wallet and cannot be edited on the Profile screen.

## 3. Navigation and display

The desktop sidebar contains Dashboard, Financial Health, Send Money, Transfer Money, Cash Out, Payment, Add Money, Financial Services, Other Services, Auto Pay and Report. On a small screen, open the menu button for the full sidebar; the bottom navigation provides common destinations. Financial Health also appears in service search and has a Dashboard shortcut.

Use the top search field to find service names, bill categories, providers or your own transaction references. Select a result to open the relevant service or receipt. Search does not expose another account's transactions.

Choose **EN / বাংলা** in the top bar for interface language. The appearance menu offers **Light**, **Dark** and **System**. Choices persist for the signed-in account. The Profile link shows your name/nickname and mobile. Contextual **Back to …** links return to the service's parent or its originating Dashboard period.

## 4. Dashboard

The balance card always shows the **current** wallet balance. Activity cards and linked reports use the selected historical period. The Dashboard initially shows today's activity; choose a preset or a whole-day value from 1 to 120.

Dates use Bangladesh calendar days. A seven-day period includes today and the previous six dates. **Payments** totals successful bills and recharges. **Money Out** includes successful outgoing operations and their fees. Failed, pending and deferred entries do not deduct from these completed totals. Open the Report link to investigate the same period.

## 5. Financial Health Center

Open **Financial Health** (`/insights`) to inspect a read-only planning estimate for your signed-in wallet. This screen neither moves money nor blocks a payment.

### Safe-to-spend and upcoming commitments

The window includes today and the next six Bangladesh dates, plus overdue unpaid commitments. For a 2 October 2026 session, the seven-day window is 2–8 October.

```text
Recorded reserve = unpaid scheduled commitments + unpaid Pay Later amounts due in the window or earlier
Safe-to-spend estimate = max(0, current wallet balance − recorded reserve)
Funding gap = max(0, recorded reserve − current wallet balance)
```

Automatic and manual schedules count. Scheduled, failed and processing installments remain obligations. Completed/cancelled installments and items linked to a successful payment are excluded. Pending/processing Pay Later purchases are reserved until repaid; later obligations remain visible on Pay Later. Supported scheduled operations and Pay Later repayment have zero demo fees. If an unsupported legacy schedule has an unknown fee, only its principal is reserved and an incomplete-fee notice appears. Savings goals do not reserve funds.

The list shows due date, recipient, mode, principal and fee. **Manage Auto Pay**, **Review Pay Later** and **Add Money** lead to the corresponding flows. This estimate sees only recorded commitments; unrecorded living costs, later obligations and future fees are not a spending guarantee.

### Observed flow and ledger reconciliation

**Last 30 days** shows successful incoming money, outgoing amounts including fees, net flow and daily outgoing average. The average divides by all thirty calendar days, including dates without activity. Top-ups and received transfers are wallet inflows, not estimated salary. **Open 30-day Report** opens their report period.

**Ledger reconciliation** compares a persisted opening anchor with all successful records since that anchor:

```text
Expected balance = recorded opening balance + successful incoming amounts − successful outgoing amounts and fees
Difference = current wallet balance − expected balance
```

**Matched to opening anchor** means that difference is zero. **Difference to review** means the arithmetic does not reconcile to the recorded anchor. **Opening anchor unavailable** means this account lacks a trusted recorded starting value; the app does not infer one merely to manufacture a match. The screen explains excluded statuses and any records before the anchor. This is local ledger consistency, not a bank-settlement audit.

### Activity review signals

Signals review successful outgoing receipts dated within the latest seven calendar days:

| Signal | Transparent rule | What to inspect |
| --- | --- | --- |
| Larger than your usual payment | More than both BDT 1,000 and three times the median of at least five earlier successful same-type payments within the preceding thirty days. Amount includes fee. | The named prior median, sample count and **Inspect receipt** link. |
| Similar payments close together | Same type, nonempty counterparty, amount and fee in two successful receipts within ten minutes. | **Inspect receipt** and **Compare earlier receipt**. |

Up to eight most recent signals are displayed; the count can include more. A large amount or repeated payment can be intentional. These are review prompts, not fraud verdicts or automatic refunds. A sparse history may produce no unusual-amount signal. Use Report to inspect further.

In the supplied 2 October scenario, a BDT 620 manual bill due 5 October and BDT 840 Pay Later amount due 6 October reserve BDT 1,460. The initial balance is BDT 108,212.50, so the displayed safe-to-spend estimate is BDT 106,752.50. Two BDT 100 recharges on 30 September at 19:00 and 19:03, plus a BDT 1,500 recharge on 1 October at 19:00 Bangladesh time, are explicitly labeled legitimate synthetic examples for demonstrating the two review rules.

## 6. Send Money

1. Open **Send Money** and enter another wallet's mobile number, such as `01944000001`.
2. Review the local recipient name/status. An unregistered number cannot receive Send Money; the blocked fixture is rejected.
3. Enter a positive amount with at most two decimal places and an optional note of up to 255 characters.
4. Submit **Send Money**. The outgoing receipt opens after success.
5. Sign in to the recipient wallet if you want to inspect the matching incoming entry. Both entries share the reference.

You cannot send to your own wallet. The demo maximum per normal wallet operation is BDT 100,000, subject to available balance and any channel limit. The supported wallet form replay path reopens its original receipt instead of deducting again. Open a new form for a new transfer.

## 7. Add Money

Open **Add Money**, choose a source, complete its fields and enter the amount:

| Source | Required demonstration details |
| --- | --- |
| Bank Account | Listed demo bank, a 6–20 digit account number and account holder name. |
| Debit / Credit Card | A checksum-valid 13–19 digit sample card number and holder name. |
| Agent | A demo agent mobile number. |

Submit **Add Money** to credit the local wallet and open its receipt. Bank/card destination numbers are masked in stored records. Re-enter those numbers after a validation error. Without JavaScript, **Update source** switches the source-specific fields without adding funds.

## 8. Cash Out and fee previews

Open **Cash Out**, select **Agent Cash Out** or **ATM Cash Out**, enter the destination and amount, and inspect the amount, fee, total deduction and remaining balance before confirmation.

| Channel | Demo rule | Example |
| --- | --- | --- |
| Agent | Fee is 1.5% of amount. Use agent `01944000002`. | BDT 1,000 amount + BDT 15 fee = BDT 1,015 wallet deduction. |
| ATM | Fee is 1%; choose a listed demo location; amount must be a multiple of BDT 500, maximum BDT 20,000. | BDT 1,000 amount + BDT 10 fee = BDT 1,010 wallet deduction. |

Fees round to the nearest paisa, with half values rounded up. The server checks the available balance including the fee. Submit **Confirm Demo Cash Out** to create the local record and receipt. The listed ATM locations are examples; no physical cash is dispensed.

## 9. Transfer Money to bank or Visa

This is separate from Send Money between local wallets.

1. Open **Transfer Money** and select **Bank Account** or **Visa Card**.
2. For a bank transfer, choose a listed demo bank, NPSB or BEFTN method, a 6–20 digit account number and holder name.
3. For Visa, use a checksum-valid 16-digit sample Visa beginning with `4`, plus the holder name.
4. Enter the amount and optional note, review the fee preview, then submit **Confirm Demo Transfer**.

| Method | Demo fee |
| --- | --- |
| NPSB | BDT 10 fixed. |
| BEFTN (BFTN alias) | BDT 0. |
| Visa | 1% of amount. |

The wallet is debited locally and its receipt opens. This does not settle funds with a bank or card network. Demo fees and timing do not represent actual provider terms.

## 10. Payment hubs and Mobile Recharge

**Payment**, **Financial Services** and **Other Services** organize service cards. The same services can be found through search or Dashboard shortcuts.

For recharge, open **Mobile Recharge**, select an operator, enter a valid mobile and amount, then submit. A local receipt opens after success. The demonstration checks number prefixes:

| Operator | Prefixes |
| --- | --- |
| Grameenphone | `013`, `017` |
| Banglalink | `014`, `019` |
| Teletalk | `015` |
| Airtel | `016` |
| Robi | `018` |

This is a demo-prefix check and does not resolve mobile number portability. Use Banglalink for `01944000003`. Suggested amounts are shortcuts; normal validated amounts can also be entered. No phone airtime is actually delivered.

## 11. Pay Bill and category-specific services

There are 17 categories, each with ten example providers:

| Hub | Categories |
| --- | --- |
| Payment | Electricity, Gas, Internet, Water, TV Bill, Education, School, College, University. |
| Financial Services | Credit Card, Insurance. |
| Other Services | Traffic Fine, Toll Payment, Government Payment, Donation, Ticket, Hotel. |

1. Open a category card or generic **Pay Bill**. A category card locks the form to its category.
2. Choose one of that category's listed providers.
3. Enter the shown account/reference field: a meter, customer, student, policy, fine, booking or payment reference as appropriate.
4. Review the local registered/unregistered/blocked status. Most mock external payment forms can use an unregistered reference with a visible warning; blocked references are rejected by the server.
5. Enter the amount and optional provider invoice reference, then submit.
6. Review the receipt's provider, account, invoice number, provider reference and transaction ID. Download PDF or JPG if needed.

References accept 2–60 letters, digits, spaces and `/ . _ -`. A previously paid provider invoice for the same account owner/category/provider is rejected. Supported repeated form submissions reopen the recorded transaction. On generic Pay Bill, changing category changes provider options and field labels. Without JavaScript, **Update Category** previews the category without moving money.

Ticket and Hotel forms pay a supplied demo booking reference. They do not create bookings, check inventory or issue tickets. Provider names are examples even where they match a real organization.

## 12. Auto Pay and manual plans

Open **Auto Pay** to create **Send Money**, **Mobile Recharge** or **Bill Payment** plans.

1. Choose the operation, recipient/reference, applicable category/operator/provider and amount.
2. Choose a first payment date from tomorrow through the last day of the second upcoming calendar month.
3. Choose **One-time payment** or **Monthly**, and **Auto Pay when due** or **Remind me · pay manually when due**.
4. Review the displayed installment dates/total and submit **Save Payment Plan**.
5. Inspect the individual rows under **Your payment plans**.

For a 2 October 2026 session, the scheduling window is 3 October–31 December 2026. Monthly repetition stays within the displayed window. A chosen 31st adjusts to the last day in a shorter month and returns to the 31st when available.

Saving a plan does not reserve or deduct wallet funds. Installments become due at midnight Bangladesh time. Automatic due installments run when their owner visits app pages other than the read-only Financial Health Center, when **Process Due Auto Pay** is selected, or when the separate demo worker runs. **Pay if due** manually processes an eligible due installment; it rejects future dates. **Cancel** is available for scheduled and failed installments. To change a plan, cancel its pending installments and create the desired replacement.

A successful installment becomes **Completed** and links to its payment receipt. A failure shows its explanation and does not deduct balance. A failed installment is not automatically retried by the current due-only executor; cancel/recreate after correcting the cause. **Open Report** from Auto Pay filters to automatic plans and their linked transactions.

### Run the local worker

From an activated environment, run one pass:

```powershell
python -m flask --app run run-due-payments
```

For repeated checks while nobody is browsing:

```powershell
python -m flask --app run run-due-payments --watch --interval 30
```

Stop with `Ctrl+C`. The worker uses the same due-only, atomic installment processing. It is a local demo process, not a hosted scheduler.

## 13. Savings Plan

Open **Savings**, enter a name, fixed monthly contribution and tenure of 1–120 months. Select **Calculate Savings** to preview or **Save Savings Plan** to retain the goal. At most ten active goals can be saved; use **Archive** to remove a goal from the active list.

The simple annual demo rate is 10%. Contributions are assumed at the beginning of each month, with a prorated return and no compounding:

```text
Total contributions = monthly contribution × months
Estimated return = monthly contribution × 0.10 × months × (months + 1) / 24
Estimated maturity = total contributions + estimated return
```

For BDT 1,000 monthly over 12 months, the illustration is BDT 12,000 contributions, BDT 650 return and BDT 12,650 maturity. Saving or archiving a plan does not move money or open a savings account. Taxes/fees are excluded; the estimate is not a guaranteed return.

## 14. Pay Later

Open **Pay Later** to inspect the BDT 5,000 demo limit, available credit, outstanding amount and overdue amount.

To record a purchase, choose a demo merchant, supply a unique merchant invoice reference, enter an amount within available credit and select a 7/14/30-day repayment tenure. Submit **Record Demo Purchase**. The purchase receipt is marked **Deferred**, and wallet balance stays unchanged.

Select **Repay from Wallet** beside a pending purchase to deduct its amount and open the repayment receipt. A repeated supported repayment returns the existing receipt rather than charging twice. Insufficient funds leave the purchase unpaid. The demonstration has 0% interest/fees, no automatic repayment and no late fee. No real lender approval or merchant payment occurs.

## 15. Request Money and signed QR instructions

For **Request Money**, enter someone else's valid mobile, requested amount and optional note, then choose **Prepare Request Message**. Copy the displayed message and share it yourself. The request is shown once after preparation; returning later begins a fresh request. **Clear Prepared Request** clears the current prepared view.

The generated request QR names your own authenticated wallet as the payee. Another signed-in local wallet can read it to fill a Send Money form. This does not send a message or collect money automatically.

Payment forms with a **QR payment instructions** panel offer **Generate QR**, **Read QR image**, pasted `UPAYX:…` text and **Read QR**. Generated codes expire after 15 minutes. Reading verifies a signed instruction and fills supported form fields; check the recipient, amount, provider and fee before submitting. Ordinary operation codes belong to their creator; request codes can be read by another wallet to prepare a transfer to the requester.

If browser QR decoding is unavailable, image reading uses the local server decoder. A generic merchant QR or an expired/modified code is rejected. Regenerate an expired code. Reading a QR never executes a payment.

## 16. Report, charts, receipts and downloads

Open **Report** (`/wallet/report`; the older `/wallet/history` URL also works).

| Filter | Meaning |
| --- | --- |
| Historical period | Today, preset periods up to 120 days, or all stored history; applies to recorded transaction dates. |
| Start/End date (BD) | Explicit local dates; override the historical period and filter schedules by due date. |
| Payment plans | All activity, Auto Pay only or manual plans only. |
| Records | Transactions and schedules, recorded transactions only, or schedules only. |
| Direction/Type/Status | Narrow matching records; unsuccessful statuses remain inspectable. |
| Bill category | A category, a specific education level, or all education levels. |
| Search records | Text in names, providers, numbers or references. |

Select **Apply filters**. **Reset** restores the unfiltered report. The count includes records of all matching statuses; monetary totals include **successful transactions only**, and outgoing totals include fees. Scheduled principal totals are separate. A completed schedule links to one real local transaction, counted once.

The four charts use the displayed transaction filters:

1. **Money in and out:** daily/grouped bars.
2. **Cumulative activity:** running incoming/outgoing/net totals beginning at zero.
3. **Spending by category:** successful outgoing amount plus fees.
4. **Cumulative histogram:** outgoing amount bands with cumulative share.

Activate a chart segment or supported legend using click/tap or keyboard to open its contributing transactions. Choose PDF/Excel under **Download selection** to export that segment. **View chart data** provides tables behind the charts. Empty successful selections show an explanation. Cumulative net change is a change within the selected activity; it is not the wallet balance.

Under **Export this report**, choose Excel or PDF and select **Download filtered report**. It exports the matching records, filter description, fee/wallet changes, schedule details and final summary. The PDF has formatted landscape pages with page numbers; Excel includes formatted sheets, print settings and repeated headers.

For an individual transaction, open **View summary** or **Print / download**, select PDF/JPG and download. Successful supported operations open this summary automatically. Schedules have their own plan documents; completed ones also link to the payment receipt. Receipts are restricted to their signed-in owner.

## Feedback update: planning forecast and research pilot

The Dashboard now starts with weekly financial planning and recurring payment management. Expand **More wallet services** for the existing service shortcuts.

Open **Financial Health** to see the trained seven-day ordinary-spending forecast. It needs 28 complete history days and some ordinary outflow activity. Scheduled payments and Pay Later repayments are excluded from training inputs for your prediction because recorded commitments are reserved separately. The forecast uses a model trained on synthetic histories and shows an empirical error range. Its illustrative balance subtracts already posted ordinary spending today from the forecast to avoid counting that spending twice. No prediction moves money. Open **Model and evaluation evidence** for measured synthetic errors and a JSON download.

Open **Pilot & Feedback** to optionally join the planning study. Demo is the default; real recruited participant sessions require operator verification before entering real research totals. Your fixed study group receives the existing commitment calculation, or that calculation plus the forecast. Confirm a planning review, create a payment plan and describe your experience to record actual prototype outcomes. The page shows only your account. Withdrawal stops new observations; prior observations remain under the displayed consent. Study payments remain simulated.

Study operators can run `python -m flask --app run:app pilot-report --source REAL` or `--source DEMO` for separate aggregate JSON reports. Follow [the pilot protocol](docs/PILOT_PROTOCOL.md) before enrolling or verifying human participants. Missing or immature observations remain unavailable; the app does not invent customer impact or revenue.

For model reproduction and dependencies, see [the model card](docs/MODEL_CARD.md). For concurrent and failure demonstrations, run `python -m unittest tests.test_reliability -v` and read [the reliability evidence](docs/RELIABILITY.md).

## 17. App Assistant

Open the assistant icon beside Notifications or `/assistant`. Select a suggested question or type up to 1,200 characters. Try:

- “What did I spend this month?”
- “How do I pay education fees?”
- “How do I set up Auto Pay?”
- “How do I export my report?”

The local guide works without an AI connection and recognizes selected English, Bangla and romanized-Bangla questions. Follow its action links to service screens. Its bounded own-account conversation persists until **Clear chat** is selected; clearing removes the stored conversation as well as the visible chat. The assistant provides guidance and cannot execute payments.

### Optional hosted AI

In `.env`, configure `OPENAI_API_KEY` and optionally `ASSISTANT_MODEL`, then restart the app. The page displays whether it is using hosted AI or the local guide. Hosted questions, bounded chat history and account aggregates go to the configured provider. Database profile fields, recipient names/numbers and transaction notes are excluded from its account snapshot. Personal information typed into a question can still be sent as question text, so use demo information. Provider failures fall back to local guidance.

The account conversation is bounded to recent messages. The assistant permits twelve requests per minute per account in the current application process. If rate-limited, wait a minute. More demonstration prompts are in [AI_ASSISTANT_PROMPTS.txt](AI_ASSISTANT_PROMPTS.txt).

## 18. Notifications, Profile and Settings

Open the notification bell for recent activity or **View all** for the notification page. Opening an alert or its transaction receipt marks that alert read. **Mark all as read** handles the remaining alerts. Read state persists; notification counts refresh when returning to the page or switching tabs.

Open **Profile** to edit full name, nickname, email, address and picture. Upload a supported raster image under 5 MB and 16 megapixels. Formats include JPG, PNG, WebP, GIF, BMP, TIFF, ICO, AVIF, HEIC/HEIF, JPEG2000, QOI, PSD, TGA and PPM. Choose output size 128/256/512/1024 pixels, **Fit image** or **Square crop**, and horizontal/vertical positioning, then **Save Changes**. The server uses the first animation frame, corrects orientation, strips metadata and stores a private JPEG. **Remove current picture** removes the saved image. SVG and camera RAW are unsupported. HEIC may lack a browser preview but can still be decoded by the installed server dependency.

Open **Notification settings**, toggle **Transaction notifications** and **Save Preferences**. Turning off the menu/badge does not remove transactions; they remain in Report. Language is changed in the top bar.

## 19. Data maintenance and evidence

The refreshed demonstration history covers **5 June–2 October 2026 inclusive** in Asia/Dhaka. It is generated household activity, not customer data imported from the real upay app. Always identify it as synthetic when presenting or sharing reports.

| Initial generated snapshot | Value |
| --- | --- |
| Users | 4 |
| Transaction rows | 345 across wallets; 208 belong to the main household. |
| Database tables / total stored rows | 18 / 913. |
| Main opening / ending balance | BDT 12,450.00 / BDT 108,212.50. |
| Saved goals / Pay Later purchases | 2 savings goals; 2 purchases, one repaid and one pending for BDT 840. |
| Future scheduled installments | 5: one manual DESCO bill due 5 October, and four November/December plans. |
| Complete database PDF | 110 pages. |

All four generated wallets have independent opening anchors and reconcile to their successful ledger activity. Counts and balances above describe the initial reset output, not a wallet after subsequent use. Startup retains this anchored history; it does not append a new rolling 120-day history each day. Select explicit dates to review the fixed window after its end date.

The project's filtered wallet report is for the signed-in account. A complete database documentation PDF is an administrator artifact: it describes every table and stored row, including app state outside one wallet's report. Keep these two outputs distinct when reviewing totals or account ownership.

### Regenerate the complete database PDF

From the project directory, run:

```powershell
python scripts/export_database_pdf.py
```

The default artifact is [UPAYX_DATABASE_REPORT.pdf](output/pdf/UPAYX_DATABASE_REPORT.pdf). It is generated from a consistent, read-only SQLite snapshot and includes a table directory, schemas, formatted data tables and empty-table sections. Wide tables are split into column groups with repeated row numbers so corresponding cells can be located. Stored timestamps are shown as raw UTC database values; the cover labels Bangladesh-time context.

For exact machine-readable values, the PDF embeds `database_snapshot.json` as an attachment, identified by a SHA-256 checksum. Open the PDF's attachments panel in a compatible viewer to extract it. This documents all current database tables/rows/columns; it does not expose a cross-user download route in the web app. Regenerate after changing data if you need a current administrator snapshot.

The regular startup seeder does not mean “reset everything.” Use the explicit reset tool when intentionally replacing the project dataset. Stop running app/worker processes before a reset and restart afterward so sessions and cached account objects are refreshed. Backup files preserve old database contents and must be handled separately from the current demo.

To intentionally replace all current project records with the supplied synthetic 120-day scenario:

```powershell
python scripts/reset_demo_data.py --confirm --as-of 2026-10-02
```

The `--confirm` flag acknowledges replacement. The tool makes a scoped SQLite backup under `instance/backups` before replacing data. Use it for the local demonstration file, then regenerate the administrator PDF. The backup is not part of the new dataset or report.

### Developer verification and previews

With project dependencies installed:

```powershell
python -m unittest discover -s tests -v
python -m tests.export_preview
```

For isolated browser QA, install Chrome and run `python -m tests.browser_qa`; screenshots/results are placed under `tmp/browser-qa`. The isolated export preview saves outputs under `tmp/export-qa`. `python -m tests.preview` starts a separate in-memory demo at `http://127.0.0.1:5001`; it leaves the normal project database untouched.

`python scripts/generate_demo_reference.py` refreshes [DEMO_DATA.txt](DEMO_DATA.txt) from code defaults. It does not read database accounts or environment secrets.

## 20. Troubleshooting

| Symptom | What to do |
| --- | --- |
| No account found | Use a seeded number or create a demo account first. |
| Invalid OTP | Use the app's displayed demo code; check `DEMO_OTP` if configured. |
| Insufficient balance | Include fees in the total; add local demo funds before retrying a new form. |
| Recipient not registered | Send Money needs another local wallet. Mock external services may show a warning. |
| Blocked destination | Use an allowed demo reference; the server deliberately rejects the flagged fixture. |
| Wrong recharge operator | Match the listed demo prefix; number portability is not modeled. |
| Provider does not match category | Open the intended category and choose one of its listed providers. |
| Invoice already paid | Find the existing receipt in Report; use a new invoice for a distinct bill. |
| Future plan will not pay | It is not due yet; the wallet must stay unchanged until its due date. |
| Failed plan is still listed | Read its reason; cancel and recreate it after correction. |
| QR invalid/expired | Generate a new signed UpayX code and read it within 15 minutes. |
| QR image decoding unavailable | Install `zxing-cpp` from requirements and restart. |
| HEIC/image upload fails | Install requirements, stay within file/pixel limits and use a supported raster format. |
| No successful chart data | Check filters/status/dates; a failed/deferred-only selection has no successful chart totals. |
| Historical date shifted | Dates are Bangladesh local dates; use explicit start/end for a fixed dataset window. |
| AI unavailable | Use the working local guide; verify the configured provider/key only if enabling hosted mode. |
| CSRF/session error after reset | Reload the form and sign in again after restarting the server. |

The project has no real OTP delivery, identity verification, merchant settlement, credit underwriting, bank/card rails or fraud decision service. Public production features and prices belong to their providers; this manual describes the local prototype.
