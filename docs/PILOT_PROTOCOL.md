# Planning pilot: observable prototype outcomes

The first four feedback areas call for a narrower product, demonstrated machine
learning, measured impact and resilient flows. The primary customer problems are
planning available wallet money and managing recurring commitments. This study
tests one intervention: a trained cash-flow forecast added to the existing
deterministic financial-health planning page. It does not test every wallet feature
or claim that a forecast improves financial wellbeing before evidence exists.

## Consent, assignment and provenance

Open `/pilot` while signed in. Enrolment requires the displayed consent. The
default source is `DEMO`. Selecting `REAL` also requires confirmation that the
account represents a genuine recruited research participant. A study operator
must check recruitment/consent records and run:

```powershell
python -m flask --app run:app pilot-verify-real --user-id 123 --confirm-researched
```

Until verified, real-labelled sessions are excluded from verified real research
totals. The operator must never verify generated accounts, browser QA traffic,
test fixtures or automated demonstration sessions as real participants. No
names, phone numbers or free-text comments appear in aggregate CLI output.
The authenticated web page exposes only the signed-in account's observations.

Allocation is reproducible 1:1 hashing of a server secret, protocol version and
account ID. This prevents a participant choosing a preferred arm by refreshing
or repeating enrolment; it does not guarantee exact balance in small cohorts.
The source and assignment stay fixed. Control receives recorded-commitment
planning without the forecast; treatment receives the same page plus the
forecast. Both groups have the same Auto Pay form and planning acknowledgement.
Non-enrolled demo users see the feature but contribute no study observations.
Maintain the assignment secret during the study. Analyses use intention-to-treat
assignment; report exposure counts and withdrawal counts alongside denominators.

Withdrawal stops new collection while preserving the assigned planning display.
Previously consented observations remain in denominators as stated on enrolment.
Withdrawing accounts cannot re-enrol into the same study to change arms. The
operator should follow the consent and recruitment process before gathering
participants; no completed human study is represented by this implementation.

## Trusted observations

Server page routes start one planning and one recurring-payment task per
participant. Repeated visits, acknowledgement redirects and subsequent task
views share that original task without inflating denominators. The planning
acknowledgement requires an existing started task.
It measures self-acknowledged review, not tested understanding or money saved.
A recurring setup completes only after the server creates a schedule.

Ledger and schedule hooks never commit. They run inside the financial service's
transaction, so rolled-back payments cannot become successful study observations.
Resource IDs deduplicate transactions, schedule creation and execution outcomes.
There is no endpoint accepting arbitrary payment-success events. Passive
received-money entries, failed transactions, seed history before enrolment and
non-consenting sessions are excluded from initiated transaction counts.
Activity and page exposure deduplicate by Dhaka calendar day. The UI displays Dhaka dates.
Exposure is a rendered planning view; activity is an authenticated server visit.
`forecast_shown_participants` separately counts treatment participants shown an
available numerical forecast after a successful render. Unavailable placeholders
do not count as delivered forecasts. Intention-to-treat comparisons retain every
assigned participant, including treatment participants whose history or activity
is insufficient for a forecast. Report this actual delivery count with any
completion comparison; assignment alone does not establish intervention delivery.

## Defined outcomes and observation windows

The operator can review separately persisted sources with:

```powershell
python -m flask --app run:app pilot-report --source REAL
python -m flask --app run:app pilot-report --source DEMO
```

The JSON contains counts and denominators, not fabricated benchmark results.

| Outcome | Numerator | Denominator / window |
| --- | --- | --- |
| Planning task completion | Participants who acknowledged the planning task | Assigned participants in the arm (intention to treat); completion among started tasks is also shown |
| Task completion uplift | Treatment intention-to-treat completion rate minus control rate | Percentage points; unavailable if either arm has no assigned participants; the conditional started-task difference is separately labelled |
| Recurring setup completion | Started tasks linked to persisted schedule creation | Started recurring-payment tasks |
| Auto Pay completion | Due created installments linked to successful ledger transactions | Observed enabled Auto Pay installments due by the report cutoff; cancellations are reported separately and excluded |
| Day 30/60/90 retention | Participants with recorded activity on Dhaka calendar days 30–36, 60–66 or 90–96 after their enrolment date | Participants whose entire seven-day Dhaka calendar follow-up window has ended; immature participants are shown separately |
| Incremental prototype transactions | Treatment minus control mean initiated successful transactions in the first 30 days | Participants with complete 30-day observation windows in each arm |
| Support report reduction | Control minus treatment mean help issues recorded here in the first 30 days | Participants with complete 30-day observation windows in each arm |

Auto Pay execution is not the randomized intervention: both groups receive the
same execution service. Report that rate as prototype reliability evidence.
Cancellation exclusions can affect rates; report raw counts,
withdrawals and per-participant distributions in any human study analysis.
Do not infer a statistically established effect from the descriptive differences.
An empty denominator produces `null` (unavailable), not zero. A cohort with fewer
than 30 participants in either arm receives the small-cohort caveat; reaching
30 is not a statistical power calculation or a claim of significance.

## Research and impact limitations

The research form captures the highest-priority problem, usefulness, ease,
self-reported missed payments and optional comments. Recruit relevant Bangladeshi
MFS users with different income patterns and preferred languages; conduct the
same planning task in both arms and ask what they understood. Keep interview
notes and recruitment evidence outside publicly accessible prototype exports.
Agree study duration, sample size and analysis plan before collecting outcomes.

All wallet rails in this repository are simulated. A verified `REAL` designation
means a real human used the prototype; it does not make the ledger a real-money
ledger. Prototype help issues are not external call-center contacts. These
observations can support usability and reliability findings, not real transaction
growth, revenue, reduced missed bills or customer/business impact. Those require
a subsequent consented production pilot, connected payment/support data and an
appropriate controlled analysis. The report always sets
`business_impact_validated` to `false` in this prototype.
