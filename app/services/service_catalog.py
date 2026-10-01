"""One catalog for service navigation, dashboard links and service search.

Provider names are examples for the local wallet demo; no provider is connected.
Gas names checked against titasgas.gov.bd and kgdcl.gov.bd.
"""

MOBILE_OPERATORS = ("Grameenphone", "Robi", "Airtel", "Banglalink", "Teletalk")

BILL_CATEGORIES = {
    "electricity": {
        "label": "Electricity", "icon": "💡", "group": "payment",
        "providers": ("DESCO Electricity", "DPDC Electricity"),
        "account_label": "Customer / Meter Number",
        "description": "Pay an electricity bill using your customer or meter number.",
    },
    "gas": {
        "label": "Gas", "icon": "🔥", "group": "payment",
        "providers": ("Titas Gas", "Karnaphuli Gas"),
        "account_label": "Customer / Account Number",
        "description": "Choose your gas company and enter your customer account.",
    },
    "internet": {
        "label": "Internet", "icon": "🌐", "group": "payment",
        "providers": ("Demo Broadband", "Demo Fiber Internet"),
        "account_label": "Subscriber / Customer ID",
        "description": "Record a demo broadband or internet subscription payment.",
    },
    "water": {
        "label": "Water", "icon": "💧", "group": "payment",
        "providers": ("Demo Water Utility",),
        "account_label": "Customer / Bill Number",
        "description": "Pay a water utility bill with your customer or bill number.",
    },
    "tv": {
        "label": "TV Bill", "icon": "📺", "group": "payment",
        "providers": ("Demo Cable TV", "Demo Satellite TV"),
        "account_label": "Subscriber / Smart Card Number",
        "description": "Record a demo cable or satellite TV subscription payment.",
    },
    "credit-card": {
        "label": "Credit Card", "icon": "💳", "group": "financial",
        "providers": ("Demo Bank Credit Card",),
        "account_label": "Statement / Payment Reference",
        "description": "Pay a demo card statement using a payment reference.",
    },
    "education": {
        "label": "Education", "icon": "🎓", "group": "payment",
        "providers": ("Demo School", "Demo College", "Demo University"),
        "account_label": "Student / Invoice Number",
        "description": "Record school, college or university fee payments.",
    },
    "traffic-fine": {
        "label": "Traffic Fine", "icon": "🚦", "group": "other",
        "providers": ("Demo Traffic Authority",),
        "account_label": "Fine / Case Reference",
        "description": "Pay a demo traffic fine using its case reference.",
    },
    "toll": {
        "label": "Toll Payment", "icon": "🛣️", "group": "other",
        "providers": ("Demo Bridge Toll", "Demo Expressway Toll"),
        "account_label": "Vehicle / Toll Reference",
        "description": "Record a bridge or expressway toll payment.",
    },
    "government": {
        "label": "Government Payment", "icon": "🏛️", "group": "other",
        "providers": ("Demo Government Fee", "Demo Tax Payment"),
        "account_label": "Application / Challan Number",
        "description": "Record a government fee or tax payment with its reference.",
    },
    "insurance": {
        "label": "Insurance", "icon": "🛡️", "group": "financial",
        "providers": ("Demo Life Insurance", "Demo General Insurance"),
        "account_label": "Policy / Premium Reference",
        "description": "Record a demo insurance premium payment.",
    },
    "donation": {
        "label": "Donation", "icon": "🤝", "group": "other",
        "providers": ("Demo Community Fund", "Demo Relief Fund"),
        "account_label": "Donation / Campaign Reference",
        "description": "Record a demo donation to a community or relief campaign.",
    },
    "ticket": {
        "label": "Ticket", "icon": "🎫", "group": "other",
        "providers": ("Demo Transport Tickets", "Demo Event Tickets"),
        "account_label": "Booking / Ticket Reference",
        "description": "Pay for an existing demo transport or event booking.",
    },
    "hotel": {
        "label": "Hotel", "icon": "🏨", "group": "other",
        "providers": ("Demo Hotel Booking",),
        "account_label": "Booking / Invoice Reference",
        "description": "Record payment for an existing demo hotel reservation.",
    },
}

SERVICE_GROUPS = {
    "payment": {"label": "Payments", "description": "Recharge and everyday utility or education bills."},
    "financial": {"label": "Financial Services", "description": "Manage your demo wallet, plan savings and prepare money requests."},
    "other": {"label": "Other Services", "description": "Government fees, travel, donations and your wallet records."},
}


def _service(service_id, label, icon, endpoint, group, description, keywords=(), **params):
    return {
        "id": service_id, "label": label, "title": label, "icon": icon,
        "endpoint": endpoint, "params": params, "category": group,
        "description": description, "keywords": tuple(keywords),
    }


SERVICES = (
    _service("send-money", "Send Money", "💸", "wallet.send_money", "financial", "Transfer demo money to another registered wallet.", ("transfer", "mobile", "wallet")),
    _service("recharge", "Mobile Recharge", "📱", "payments.recharge", "payment", "Recharge a Bangladeshi mobile number using demo balance.", ("phone", "prepaid", *MOBILE_OPERATORS)),
    _service("cash-out", "Cash Out", "🏧", "wallet.cash_out", "financial", "Withdraw demo balance through an agent with the displayed fee.", ("withdraw", "agent", "cash")),
    _service("pay-bill", "Pay Bill", "🧾", "payments.pay_bill", "payment", "Choose a bill category and its matching provider.", ("bills", "utility", "payment")),
    _service("add-money", "Add Money", "➕", "wallet.add_money", "financial", "Top up your wallet from a demo bank, card or transfer.", ("top up", "deposit", "balance", "bank", "card")),
    _service("savings", "Savings", "🏦", "payments.savings", "financial", "Calculate a monthly savings plan without moving money.", ("save", "monthly", "calculator", "plan")),
    _service("fund-transfer", "Fund Transfer", "🔁", "wallet.send_money", "financial", "Transfer demo funds to a registered wallet.", ("send money", "transfer")),
    _service("request-money", "Request Money", "💬", "payments.request_money", "financial", "Prepare a money request message to share yourself.", ("request", "collect", "receive")),
    *(
        _service(slug, category["label"], category["icon"], "payments.pay_bill", category["group"], category["description"], ("bill", "bills", "payment", *category["providers"]), category=slug)
        for slug, category in BILL_CATEGORIES.items()
    ),
    _service("history", "Transaction History", "🕘", "wallet.history", "other", "Review your wallet transactions and payment references.", ("history", "records", "statement", "receipt", "transactions")),
    _service("profile", "Profile", "👤", "profile.index", "other", "Update your name and contact details.", ("account", "name", "email", "settings")),
)


def get_service(service_id):
    return next((service for service in SERVICES if service["id"] == service_id), None)


def services_for_group(group):
    # The generic Pay Bill entry belongs in search and quick links, not its own hub.
    return tuple(service for service in SERVICES if service["category"] == group and service["id"] not in {"pay-bill", "fund-transfer"})
