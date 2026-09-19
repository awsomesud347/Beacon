"""Merchant -> (display name, category) lookup. Deterministic; the LLM never categorizes."""

import re

# (pattern matched against the upper-cased raw merchant string, display name, category)
MERCHANTS: list[tuple[str, str, str]] = [
    (r"ACME PAYROLL", "Acme Payroll", "income"),
    (r"OAKWOOD APARTMENTS", "Oakwood Apartments", "rent"),
    (r"CITY POWER", "City Power and Light", "utilities"),
    (r"METRO WATER", "Metro Water", "utilities"),
    (r"COMCAST", "Comcast Internet", "utilities"),
    (r"KROGER", "Kroger", "groceries"),
    (r"TRADER JOE", "Trader Joe's", "groceries"),
    (r"WHOLE FOODS", "Whole Foods", "groceries"),
    (r"CHIPOTLE", "Chipotle", "dining"),
    (r"CORNER BISTRO", "Corner Bistro", "dining"),
    (r"THAI SPICE", "Thai Spice", "dining"),
    (r"PANERA", "Panera", "dining"),
    (r"STARBUCKS", "Starbucks", "coffee"),
    (r"BLUE BOTTLE", "Blue Bottle Coffee", "coffee"),
    (r"UBER", "Uber", "transport"),
    (r"SHELL", "Shell", "transport"),
    (r"METRO TRANSIT", "Metro Transit", "transport"),
    (r"NETFLIX", "Netflix", "subscriptions"),
    (r"SPOTIFY", "Spotify", "subscriptions"),
    (r"APPLE\.COM/BILL|ICLOUD", "iCloud Storage", "subscriptions"),
    (r"NYTIMES|NYT DIGITAL", "New York Times", "subscriptions"),
    (r"PLANET FITNESS", "Planet Fitness", "subscriptions"),
    (r"HULU", "Hulu", "subscriptions"),
    (r"PARAMOUNT", "Paramount Plus", "subscriptions"),
    (r"AUDIBLE", "Audible", "subscriptions"),
    (r"CLOUDVAULT", "CloudVault", "subscriptions"),
    (r"AMAZON|AMZN", "Amazon", "shopping"),
    (r"TARGET", "Target", "shopping"),
    (r"BEST BUY", "Best Buy", "shopping"),
    (r"IKEA", "IKEA", "shopping"),
    (r"CVS", "CVS Pharmacy", "health"),
    (r"AMC THEATRES", "AMC Theatres", "entertainment"),
]

FALLBACK_CATEGORY = "other"

_COMPILED = [(re.compile(p), display, cat) for p, display, cat in MERCHANTS]
_NOISE = re.compile(r"(#\s*\d+|\*\S+|\s\d{3,}.*$)")


def lookup(raw: str) -> tuple[str, str]:
    """Return (display name, category) for a raw bank-statement merchant string."""
    upper = raw.upper()
    for pattern, display, category in _COMPILED:
        if pattern.search(upper):
            return display, category
    cleaned = _NOISE.sub("", raw).strip() or raw.strip()
    return cleaned.title(), FALLBACK_CATEGORY
