"""One catalog for service navigation, dashboard links and service search.

Provider names are examples for the local wallet demo; no provider is connected.
Gas distribution names checked against Petrobangla's distribution network:
https://petrobangla.org.bd/site/page/aae9ec2b-d948-4a03-85eb-f51068640980/-
LPG names: https://omeralpg.com/ and https://www.bashundharalpgas.com/
"""

MOBILE_OPERATORS = ("Grameenphone", "Robi", "Airtel", "Banglalink", "Teletalk")
RECHARGE_AMOUNTS = (20, 30, 50, 100, 150, 200, 300, 500, 750, 1000)

EDUCATION_PROVIDERS = {
    "school": ("Demo School", "Demo Dhaka School", "Demo Chattogram School", "Demo Rajshahi School", "Demo Sylhet School", "Demo Khulna School", "Demo Rangpur School", "Demo Barishal School", "Demo Cumilla School", "Demo Mymensingh School"),
    "college": ("Demo College", "Demo Dhaka College", "Demo Chattogram College", "Demo Rajshahi College", "Demo Sylhet College", "Demo Khulna College", "Demo Rangpur College", "Demo Barishal College", "Demo Cumilla College", "Demo Mymensingh College"),
    "university": ("Demo University", "Demo Dhaka University", "Demo Chattogram University", "Demo Rajshahi University", "Demo Sylhet University", "Demo Khulna University", "Demo Rangpur University", "Demo Barishal University", "Demo Cumilla University", "Demo Mymensingh University"),
}

BILL_CATEGORIES = {
    "electricity": {
        "label": "Electricity", "icon": "💡", "group": "payment",
        "providers": ("DESCO Electricity", "DPDC Electricity", "Demo Dhaka North Electricity", "Demo Dhaka South Electricity", "Demo Chattogram Electricity", "Demo Rajshahi Electricity", "Demo Khulna Electricity", "Demo Sylhet Electricity", "Demo Rangpur Electricity", "Demo Rural Electricity"),
        "account_label": "Customer / Meter Number",
        "description": "Pay an electricity bill using your customer or meter number.",
    },
    "gas": {
        "label": "Gas", "icon": "🔥", "group": "payment",
        "providers": ("Titas Gas", "Karnaphuli Gas", "Bakhrabad Gas", "Jalalabad Gas", "Pashchimanchal Gas", "Sundarban Gas", "Omera LPG", "Bashundhara LP Gas", "Demo Local LPG Refill", "Demo Commercial LPG Supply"),
        "account_label": "Customer / Account Number",
        "description": "Choose a gas company or LPG invoice provider and enter your customer account.",
    },
    "internet": {
        "label": "Internet", "icon": "🌐", "group": "payment",
        "providers": ("Demo Broadband", "Demo Fiber Internet", "Demo Dhaka Internet", "Demo Chattogram Internet", "Demo Rajshahi Internet", "Demo Sylhet Internet", "Demo Khulna Internet", "Demo Rangpur Internet", "Demo Rural Broadband", "Demo Business Internet"),
        "account_label": "Subscriber / Customer ID",
        "description": "Record a demo broadband or internet subscription payment.",
    },
    "water": {
        "label": "Water", "icon": "💧", "group": "payment",
        "providers": ("Demo Water Utility", "Demo Dhaka Water", "Demo Chattogram Water", "Demo Khulna Water", "Demo Rajshahi Water", "Demo Sylhet Water", "Demo Rangpur Water", "Demo Barishal Water", "Demo Cumilla Water", "Demo Mymensingh Water"),
        "account_label": "Customer / Bill Number",
        "description": "Pay a water utility bill with your customer or bill number.",
    },
    "tv": {
        "label": "TV Bill", "icon": "📺", "group": "payment",
        "providers": ("Demo Cable TV", "Demo Satellite TV", "Demo Dhaka Cable", "Demo Chattogram Cable", "Demo Khulna Cable", "Demo Sylhet Cable", "Demo Rajshahi Cable", "Demo Digital TV", "Demo Family TV Package", "Demo Premium TV Package"),
        "account_label": "Subscriber / Smart Card Number",
        "description": "Record a demo cable or satellite TV subscription payment.",
    },
    "credit-card": {
        "label": "Credit Card", "icon": "💳", "group": "financial",
        "providers": ("Demo Bank Credit Card", "Demo Classic Card", "Demo Gold Card", "Demo Platinum Card", "Demo Student Card", "Demo Corporate Card", "Demo Travel Card", "Demo Shopping Card", "Demo Rewards Card", "Demo Secured Card"),
        "account_label": "Statement / Payment Reference",
        "description": "Pay a demo card statement using a payment reference.",
    },
    "education": {
        "label": "Education", "icon": "🎓", "group": "payment",
        "providers": ("Demo School", "Demo College", "Demo University", "Demo School Admission", "Demo School Tuition", "Demo College Admission", "Demo College Tuition", "Demo University Admission", "Demo University Tuition", "Demo Examination Fees"),
        "account_label": "Student / Invoice Number",
        "description": "Choose education fees or open the dedicated School, College and University services.",
    },
    "traffic-fine": {
        "label": "Traffic Fine", "icon": "🚦", "group": "other",
        "providers": ("Demo Traffic Authority", "Demo Dhaka Traffic Fine", "Demo Chattogram Traffic Fine", "Demo Rajshahi Traffic Fine", "Demo Khulna Traffic Fine", "Demo Sylhet Traffic Fine", "Demo Rangpur Traffic Fine", "Demo Barishal Traffic Fine", "Demo Highway Traffic Fine", "Demo Vehicle Violation"),
        "account_label": "Fine / Case Reference",
        "description": "Pay a demo traffic fine using its case reference.",
    },
    "toll": {
        "label": "Toll Payment", "icon": "🛣️", "group": "other",
        "providers": ("Demo Bridge Toll", "Demo Expressway Toll", "Demo River Bridge Toll", "Demo City Expressway Toll", "Demo Highway Toll", "Demo Tunnel Toll", "Demo Truck Toll", "Demo Bus Toll", "Demo Private Car Toll", "Demo Toll Pass Renewal"),
        "account_label": "Vehicle / Toll Reference",
        "description": "Record a bridge or expressway toll payment.",
    },
    "government": {
        "label": "Government Payment", "icon": "🏛️", "group": "other",
        "providers": ("Demo Government Fee", "Demo Tax Payment", "Demo Passport Fee", "Demo Birth Registration", "Demo Trade License", "Demo Driving License", "Demo Vehicle Registration", "Demo Land Service Fee", "Demo Application Fee", "Demo Treasury Challan"),
        "account_label": "Application / Challan Number",
        "description": "Record a government fee or tax payment with its reference.",
    },
    "insurance": {
        "label": "Insurance", "icon": "🛡️", "group": "financial",
        "providers": ("Demo Life Insurance", "Demo General Insurance", "Demo Health Insurance", "Demo Motor Insurance", "Demo Home Insurance", "Demo Travel Insurance", "Demo Education Insurance", "Demo Accident Insurance", "Demo Family Insurance", "Demo Business Insurance"),
        "account_label": "Policy / Premium Reference",
        "description": "Record a demo insurance premium payment.",
    },
    "donation": {
        "label": "Donation", "icon": "🤝", "group": "other",
        "providers": ("Demo Community Fund", "Demo Relief Fund", "Demo Education Fund", "Demo Healthcare Fund", "Demo Food Assistance", "Demo Flood Relief", "Demo Winter Support", "Demo Orphan Support", "Demo Disability Support", "Demo Clean Water Fund"),
        "account_label": "Donation / Campaign Reference",
        "description": "Record a demo donation to a community or relief campaign.",
    },
    "ticket": {
        "label": "Ticket", "icon": "🎫", "group": "other",
        "providers": ("Demo Transport Tickets", "Demo Event Tickets", "Demo Bus Booking", "Demo Train Booking", "Demo Ferry Booking", "Demo Flight Booking", "Demo Cinema Booking", "Demo Concert Booking", "Demo Sports Event", "Demo Museum Ticket"),
        "account_label": "Booking / Ticket Reference",
        "description": "Pay for an existing demo transport or event booking.",
    },
    "hotel": {
        "label": "Hotel", "icon": "🏨", "group": "other",
        "providers": ("Demo Hotel Booking", "Demo Dhaka Hotel", "Demo Chattogram Hotel", "Demo Coxs Bazar Hotel", "Demo Sylhet Hotel", "Demo Khulna Hotel", "Demo Rajshahi Hotel", "Demo Rangpur Hotel", "Demo Resort Booking", "Demo Guest House Booking"),
        "account_label": "Booking / Invoice Reference",
        "description": "Record payment for an existing demo hotel reservation.",
    },
}

for education_type, providers in EDUCATION_PROVIDERS.items():
    BILL_CATEGORIES[f"education-{education_type}"] = {
        "label": education_type.title(), "icon": "🎓", "group": "payment", "providers": providers,
        "account_label": "Student / Invoice Number",
        "description": f"Pay demo {education_type} admission, tuition or examination fees.",
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
    _service("cash-out", "Cash Out", "🏧", "wallet.cash_out", "financial", "Withdraw demo wallet funds through an agent or ATM, with a fee preview.", ("withdraw", "agent", "ATM", "cash")),
    _service("pay-bill", "Pay Bill", "🧾", "payments.pay_bill", "payment", "Choose a bill category and its matching provider.", ("bills", "utility", "payment")),
    _service("add-money", "Add Money", "➕", "wallet.add_money", "financial", "Top up your wallet from a demo bank, card or transfer.", ("top up", "deposit", "balance", "bank", "card")),
    _service("savings", "Savings", "🏦", "payments.savings", "financial", "Save a fixed monthly plan and estimate maturity at a demo 10% annual rate.", ("save", "monthly", "calculator", "plan", "tenure", "interest", "10%")),
    _service("pay-later", "Pay Later", "🛍️", "payments.pay_later", "financial", "Track a deferred demo purchase and repay it from your wallet.", ("credit", "repay", "deferred", "buy now", "due")),
    _service("auto-pay", "Auto Pay", "↻", "operations.schedules", "financial", "Schedule one-time or monthly demo payments for the next two months.", ("schedule", "scheduled", "automatic", "future", "one-time", "monthly", "prepay")),
    _service("fund-transfer", "Transfer Money", "🔁", "wallet.transfer_money", "financial", "Record a demo NPSB / BEFTN bank transfer or a Visa card transfer.", ("bank", "NPSB", "BFTN", "BEFTN", "Visa", "card", "account", "transfer")),
    _service("request-money", "Request Money", "💬", "payments.request_money", "financial", "Prepare a money request message to share yourself.", ("request", "collect", "receive")),
    *(
        _service(slug, category["label"], category["icon"], "payments.pay_bill", category["group"], category["description"], ("bill", "bills", "payment", *category["providers"]), category=slug)
        for slug, category in BILL_CATEGORIES.items()
    ),
    _service("history", "Report", "🕘", "wallet.history", "other", "Review transactions, download receipts and export filtered reports.", ("report", "history", "records", "statement", "receipt", "transactions", "export")),
    _service("profile", "Profile", "👤", "profile.index", "other", "Update your name and contact details.", ("account", "name", "email", "settings")),
)


def get_service(service_id):
    return next((service for service in SERVICES if service["id"] == service_id), None)


def services_for_group(group):
    # The generic Pay Bill entry belongs in search and quick links, not its own hub.
    return tuple(service for service in SERVICES if service["category"] == group and service["id"] not in {"pay-bill", "profile"})
