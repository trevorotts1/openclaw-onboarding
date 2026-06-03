# ROSTER — Personal Finance Assistant

## Owner

| Field | Value |
|---|---|
| **Name** | {{TOKEN}} |
| **Email** | {{OWNER_EMAIL}} |
| **Timezone** | {{OWNER_TIMEZONE}} |
| **Role** | {{ROLE_TITLE}} |
| **Briefing Preference** | Weekly Money Brief every Sunday at 7 PM. 90-second readable snapshot. 3 numbers, zero judgment, one action. |
| **Flag Preference** | Urgent (overdraft risk, fraud, missed payment risk) — immediately. Important (renewal approaching, spending trend, savings rate change) — in the next scheduled brief or within 24 hours. |
| **Financial Communication Style** | Direct, clear, judgment-free. Lead with the data point, then context, then the question or action. Never use language that implies irresponsibility. |
| **Financial Pet Peeves** | Late fees that could have been prevented. Surprise bills {{TOKEN}} didn't know were coming. Being told what they "should" do with their money. Subscription price increases with no notice. |
| **Money Mindset** | Clarity over restriction. {{TOKEN}} wants to know where the money is going — not to be told where it shouldn't go. Awareness enables intention; judgment enables avoidance. |
| **Do Not Disturb** | After 10 PM and before 7 AM {{OWNER_TIMEZONE}} unless the flag is truly urgent (overdraft, fraud, payment about to be missed within 24 hours). |

---

## Financial Accounts Overview

> **Note:** This section uses placeholder references only. Actual account numbers, institution names, and balances live in {{TOKEN}}'s live systems — never in department templates. Update this roster when {{TOKEN}} opens, closes, or changes financial accounts.

| Account Type | Institution Reference | Primary Use | Access |
|---|---|---|---|
| {{PRIMARY_CHECKING}} | {{BANK_NAME_1}} | Daily spending, bill payments, direct deposit | Read balances + transaction history |
| {{SECONDARY_CHECKING}} | {{BANK_NAME_2}} | Secondary cash management, buffer account | Read balances + transaction history |
| {{PRIMARY_SAVINGS}} | {{BANK_NAME_1}} | Emergency fund, short-term savings goals | Read balances |
| {{CREDIT_CARD_1}} | {{CARD_ISSUER_1}} | Daily purchases, recurring subscriptions | Read transactions + balances |
| {{CREDIT_CARD_2}} | {{CARD_ISSUER_2}} | Business expenses, travel, reimbursable charges | Read transactions + balances |
| {{INVESTMENT_ACCOUNT}} | {{BROKERAGE_NAME}} | Long-term investments | Read balances only — no trading authority |
| {{RETIREMENT_ACCOUNT}} | {{RETIREMENT_PROVIDER}} | Tax-advantaged retirement savings | Read balances only |

### Payment Method Map

| Recurring Obligation Category | Default Payment Method | Backup |
|---|---|---|
| Utilities & Phone | {{CREDIT_CARD_1}} or auto-debit from {{PRIMARY_CHECKING}} | {{CREDIT_CARD_2}} |
| Subscriptions & Software | {{CREDIT_CARD_1}} | {{CREDIT_CARD_2}} |
| Insurance Premiums | {{CREDIT_CARD_1}} or annual invoice | {{PRIMARY_CHECKING}} |
| Professional Memberships | {{CREDIT_CARD_2}} | {{CREDIT_CARD_1}} |
| Large Annual Obligations | {{PRIMARY_CHECKING}} | Confirmed 30 days in advance |

---

## Recurring Obligations Registry

> **Note:** This is the master reference for PA-11-01 (Bill Calendar). Every obligation below must have a corresponding entry in the Bill Calendar with amount, frequency, due date, payment method, and reminder offsets. This list should be reviewed and updated weekly during Sunday reconciliation.

### Monthly Obligations
| Obligation | Category | Approximate Range | Notes |
|---|---|---|---|
| {{HOUSING_PAYMENT}} | Housing | $X — $Y | Rent or mortgage. Usually 1st of month. Highest single monthly outflow. Cash-flow anchor. |
| {{UTILITY_ELECTRIC}} | Utilities | Variable ($X — $Y) | Seasonal variation — higher in summer/winter. Check actual amount before each due date. |
| {{UTILITY_WATER}} | Utilities | Variable ($X — $Y) | Quarterly or monthly depending on provider. |
| {{UTILITY_INTERNET}} | Utilities | ~$X | Usually fixed. Watch for annual rate increases. |
| {{PHONE_SERVICE}} | Utilities — Phone | ~$X | May include device payment plan. |
| {{STREAMING_SERVICE_1}} | Entertainment | ~$X | (Populate with actual service names) |
| {{STREAMING_SERVICE_2}} | Entertainment | ~$X | |
| {{SOFTWARE_SUBSCRIPTION_1}} | Software & Tools | ~$X | |
| {{SOFTWARE_SUBSCRIPTION_2}} | Software & Tools | ~$X | |
| {{GYM_OR_WELLNESS}} | Health & Wellness | ~$X | |
| {{CLOUD_STORAGE}} | Software & Tools | ~$X | Check actual usage against plan tier quarterly. |
| {{MEMBERSHIP_1}} | Professional | ~$X | |
| {{CREDIT_CARD_1_PAYMENT}} | Debt Service | Variable | Due date may drift by 2-3 days each cycle — verify each month. |
| {{CREDIT_CARD_2_PAYMENT}} | Debt Service | Variable | Same drift risk. |

### Quarterly Obligations
| Obligation | Category | Approximate Range | Notes |
|---|---|---|---|
| {{QUARTERLY_OBLIGATION_1}} | (Populate) | ~$X | |

### Semi-Annual Obligations
| Obligation | Category | Approximate Range | Notes |
|---|---|---|---|
| {{SEMIANNUAL_OBLIGATION_1}} | (Populate) | ~$X | |

### Annual Obligations
| Obligation | Category | Approximate Range | Renewal Month | Notes |
|---|---|---|---|---|
| {{INSURANCE_AUTO}} | Insurance | ~$X | {{RENEWAL_MONTH}} | 30-day negotiation window before renewal. Competitor check: {{COMPETITOR_1}}, {{COMPETITOR_2}}. |
| {{INSURANCE_HOME_RENTERS}} | Insurance | ~$X | {{RENEWAL_MONTH}} | Often bundled with auto for discount. |
| {{INSURANCE_OTHER}} | Insurance | ~$X | {{RENEWAL_MONTH}} | |
| {{DOMAIN_REGISTRATIONS}} | Software & Tools | ~$X each | Various | (Populate with actual domains and renewal dates) |
| {{PROFESSIONAL_LICENSE}} | Professional | ~$X | {{RENEWAL_MONTH}} | |
| {{TAX_PREP_SOFTWARE}} | Software & Tools | ~$X | {{RENEWAL_MONTH}} | |
| {{ANNUAL_MEMBERSHIP_1}} | Professional | ~$X | {{RENEWAL_MONTH}} | |
| {{ANNUAL_SUBSCRIPTION_1}} | (Populate) | ~$X | {{RENEWAL_MONTH}} | |

### Irregular / Projected Obligations
| Obligation | Category | Approximate Range | Typical Timing | Notes |
|---|---|---|---|---|
| {{TAX_PAYMENT}} | Taxes | Variable | {{TAX_SEASON}} | Flag deadlines 90/60/30 days out. Coordinate with {{TOKEN}}'s CPA. |
| {{CAR_MAINTENANCE}} | Transportation | ~$X annually | As needed | Budget ~$X/month sinking fund. |
| {{HOLIDAY_GIFTS}} | Gifts & Giving | Variable | Nov-Dec | Flag in October for planning. |
| {{TRAVEL_EXPENSES}} | Travel | Variable | As planned | Flag upcoming trips for cash-flow awareness. |
| {{MEDICAL_DEDUCTIBLE}} | Healthcare | Variable | As incurred | Track against annual deductible if applicable. |

---

## Subscription Watchlist

> **Note:** This is a living list of active subscriptions — the source material for PA-11-02 audits. Update after every audit and whenever a subscription is added, cancelled, or changed.

| Service | Monthly Cost | Billed Through | Last Audit Date | Usage Status | Action from Last Audit |
|---|---|---|---|---|---|
| {{SUBSCRIPTION_1}} | ~$X | {{CREDIT_CARD_1}} | {{LAST_AUDIT_DATE}} | Active | Keep |
| {{SUBSCRIPTION_2}} | ~$X | Apple ID | {{LAST_AUDIT_DATE}} | Dormant ({{DAYS}} days) | Schedule — 30-day deadline |
| {{SUBSCRIPTION_3}} | ~$X | {{CREDIT_CARD_2}} | {{LAST_AUDIT_DATE}} | Active | Negotiate — competitor offers $X less |
| {{SUBSCRIPTION_4}} | ~$X | PayPal | {{LAST_AUDIT_DATE}} | Zero usage | Cancelled — saving $X/month |
| (Add rows as subscriptions are discovered) | | | | | |

---

## Key Contacts for Financial Matters

| Person / Role | What to Consult Them For | Contact Method |
|---|---|---|
| {{TOKEN}} | All financial decisions. Inform, never decide without authorization. | {{MESSAGING_TOOL}} |
| {{TOKEN}}'s CPA / Tax Preparer | Tax deadlines, estimated payment amounts, document requirements | {{CONTACT_METHOD}} |
| {{TOKEN}}'s Financial Advisor (if applicable) | Investment questions, retirement contributions, long-term planning context | {{CONTACT_METHOD}} |
| {{INSURANCE_AGENT}} | Policy changes, coverage questions, bundling opportunities | {{CONTACT_METHOD}} |
| Specialist 1 — Executive Assistant | {{TOKEN}}'s current priorities, major upcoming expenses, sensitive timing | Inter-department coordination |
| Specialist 2 — Calendar & Scheduling | Time-block awareness for bill due dates and negotiation calls | Inter-department |
| Specialist 4 — Task & Priority Manager | Route financial action items as tracked tasks | Inter-department |
| Specialist 6 — Research & Answers | Competitor pricing research for renewal negotiations | Inter-department |
| Specialist 14 — Life-Admin Archivist | Financial document filing, insurance policies, tax documents, receipts | Inter-department |

---

## Owner-Specific Financial Preferences

### Renewal Negotiation Style
- {{TOKEN}} prefers: (Populate — self-negotiation with script / agent-authorized negotiation / review-only without negotiation)
- Authorization level for agent-handled negotiations: (Populate — full authorization with preset limits / case-by-case approval / never)
- Negotiation tone preference: Professional and firm. "I'd prefer to stay with you — can you match this competitor rate?" over aggressive or confrontational approaches.

### Spending Awareness Thresholds
- Single expense flag threshold: (Populate — e.g., any purchase above $X gets a same-day check)
- Category spike threshold: 30%+ above weekly average triggers a note in the Money Brief
- Cash withdrawal tracking: Any ATM withdrawal above $X triggers a 48-hour follow-up if purpose isn't logged

### Savings & Cash-Flow Preferences
- Safety threshold for primary checking: (Populate — e.g., flag when balance drops below $X)
- Savings rate target: (Populate — e.g., 10-20% of income)
- Emergency fund target: (Populate — e.g., 3-6 months of essential expenses)

### Financial Calendar Preferences
- Bill payment style: (Populate — auto-pay preferred / manual payment preferred / mix)
- Reminder lead time preference: 30 days for annual obligations, 7 days + 1 day for monthly bills
- Fiscal year reference: (Populate — calendar year / fiscal year ending {{MONTH}})

### Topics {{TOKEN}} Always Wants Flagged
- Any bill increase over 10% without prior notice
- Subscription price changes (up or down)
- Unrecognized or suspicious charges
- Upcoming large outflows (>$X) within the next 14 days
- Bank balance approaching or below safety threshold
- Savings rate trends (positive or negative) over 2+ consecutive months
- Annual obligations approaching within 30 days

### Topics to Handle with Extra Care
- Tax-related matters — inform and coordinate, never advise
- Investment account balances — report without commentary
- Large discretionary purchases — present the cash-flow impact, not an opinion on the purchase itself
- Shared or joint account activity — be especially careful to attribute spending accurately and never assume

---

## Maintenance Notes

- **Weekly:** Review and update the Recurring Obligations Registry during Sunday reconciliation. Any bill amount that changed, any new obligation added, any obligation that ended — capture it immediately.
- **Monthly:** After the Monthly Deep Dive, review the Subscription Watchlist for any services approaching their "Schedule" deadline. Update usage statuses.
- **Quarterly:** After the Subscription Audit (PA-11-02), fully refresh the Subscription Watchlist. Remove cancelled services, add newly discovered ones, update all pricing.
- **Annually:** Full review of this roster with {{TOKEN}}. Have any accounts changed? Any new recurring obligations? Any preferences shifted? Any new contacts to add?
- **On any account change:** When {{TOKEN}} opens, closes, or modifies a financial account, update the Financial Accounts Overview section immediately. The Bill Calendar depends on accurate payment method mapping.
- **On any preference change:** If {{TOKEN}} expresses a new preference about how financial information is communicated — format, frequency, tone, thresholds — capture it here immediately. This roster is your operating manual for how {{TOKEN}} wants to interact with their financial information.

---

*This roster is a living document. The better you know {{TOKEN}}'s financial world — the accounts, the obligations, the preferences, the people — the more invisible and valuable your work becomes. {{TOKEN}} shouldn't have to think about the system; they should just feel its effects: clarity, control, and the quiet confidence that nothing is falling through the cracks.*

— The Personal Finance Department, Specialist 11
