"""Offline demonstration destinations and prices, never live financial integrations."""

from decimal import Decimal


DEMO_BANKS = (
    "Demo Bank 01 — Dhaka", "Demo Bank 02 — Chattogram",
    "Demo Bank 03 — Sylhet", "Demo Bank 04 — Rajshahi",
    "Demo Bank 05 — Khulna", "Demo Bank 06 — Barishal",
    "Demo Bank 07 — Rangpur", "Demo Bank 08 — Mymensingh",
    "Demo Bank 09 — Cumilla", "Demo Bank 10 — Gazipur",
    "Demo Bank 11 — Narayanganj", "Demo Bank 12 — Bogura",
)

DEMO_ATMS = {
    "ATM-DHAKA-01": "Demo ATM — Gulshan, Dhaka",
    "ATM-DHAKA-02": "Demo ATM — Banani, Dhaka",
    "ATM-DHAKA-03": "Demo ATM — Dhanmondi, Dhaka",
    "ATM-DHAKA-04": "Demo ATM — Motijheel, Dhaka",
    "ATM-DHAKA-05": "Demo ATM — Mirpur, Dhaka",
    "ATM-CTG-01": "Demo ATM — Agrabad, Chattogram",
    "ATM-SYLHET-01": "Demo ATM — Zindabazar, Sylhet",
    "ATM-RAJSHAHI-01": "Demo ATM — Shaheb Bazar, Rajshahi",
    "ATM-KHULNA-01": "Demo ATM — Sonadanga, Khulna",
    "ATM-BARISHAL-01": "Demo ATM — Sadar Road, Barishal",
    "ATM-RANGPUR-01": "Demo ATM — Jahaj Company, Rangpur",
    "ATM-MYMENSINGH-01": "Demo ATM — Ganginarpar, Mymensingh",
}

CASH_OUT_RATES = {"AGENT": Decimal("0.015"), "ATM": Decimal("0.01")}
BANK_TRANSFER_FEES = {"NPSB": Decimal("10.00"), "BEFTN": Decimal("0.00")}
VISA_TRANSFER_RATE = Decimal("0.01")
ATM_INCREMENT = Decimal("500.00")
ATM_LIMIT = Decimal("20000.00")
