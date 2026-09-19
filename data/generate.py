"""Seeded synthetic ledger: 14 months for one persona, with five anomalies planted in the
current month (September 2026). Run `uv run python -m data.generate` to rewrite fixtures."""

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from data.merchants import lookup

START = date(2025, 8, 1)
END = date(2026, 9, 30)
CURRENT_MONTH = (2026, 9)
FIXTURES = Path(__file__).resolve().parent / "fixtures"

SALARY = 2841.50
RENT = 1450.00
# raw merchant, amount, day of month, account
SUBSCRIPTIONS = [
    ("NETFLIX.COM", 15.49, 7, "credit"),
    ("SPOTIFY USA", 11.99, 12, "credit"),
    ("APPLE.COM/BILL ICLOUD", 2.99, 3, "credit"),
    ("NYTIMES DIGITAL", 17.00, 22, "credit"),
    ("PLANET FITNESS #1123", 24.99, 5, "checking"),
    ("HULU 877-8244858", 7.99, 18, "credit"),
]

# What the analysis engine must find in the current month (see tests/test_rules.py).
PLANTED = {
    "new_recurring": {
        "raw": [("PARAMOUNT+ SUBSCRIPTION", 12.99, 9), ("AUDIBLE*MEMBERSHIP", 15.99, 14),
                ("CLOUDVAULT BACKUP", 18.02, 21)],
        "merchants": ["Paramount Plus", "Audible", "CloudVault"],
        "count": 3,
        "total": 47.00,
    },
    "duplicate_charge": {"raw": "CORNER BISTRO", "merchant": "Corner Bistro", "amount": 38.50,
                         "days": (12, 13)},
    "amount_drift": {"merchant": "Netflix", "previous_amount": 15.49, "amount": 17.99},
    "missing_recurring": {"merchant": "Planet Fitness", "amount": 24.99},
    "category_outlier": {"category": "dining"},
}


@dataclass
class Txn:
    day: date
    merchant: str
    amount: float
    account: str

    @property
    def category(self) -> str:
        return lookup(self.merchant)[1]


def _months() -> list[tuple[int, int]]:
    out, y, m = [], START.year, START.month
    while (y, m) <= (END.year, END.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _mondays():
    d = START - timedelta(days=START.weekday())
    while d <= END:
        yield d
        d += timedelta(days=7)


def _money(x: float) -> float:
    return round(float(x), 2)


def _lognormal(rng: np.random.Generator, mean: float, sigma: float) -> float:
    return _money(rng.lognormal(np.log(mean), sigma))


def _is_current(d: date) -> bool:
    return (d.year, d.month) == CURRENT_MONTH


def generate(seed: int = 42) -> list[Txn]:
    rng = np.random.default_rng(seed)
    txns: list[Txn] = []
    add = txns.append

    # Biweekly salary with slight date jitter.
    payday = START
    while payday <= END:
        add(Txn(payday - timedelta(days=int(rng.integers(0, 2))), "ACME PAYROLL", SALARY,
                "checking"))
        payday += timedelta(days=14)

    for y, m in _months():
        winter = {12: 70, 1: 70, 2: 60, 11: 35, 3: 30}.get(m, 0)
        add(Txn(date(y, m, 1 + int(rng.integers(0, 3))), "OAKWOOD APARTMENTS", -RENT, "checking"))
        add(Txn(date(y, m, 15), "CITY POWER & LIGHT", -_money(85 + winter + rng.normal(0, 8)),
                "checking"))
        add(Txn(date(y, m, 20), "METRO WATER DEPT", -_money(38 + rng.normal(0, 5)), "checking"))
        add(Txn(date(y, m, 10), "COMCAST CABLE COMM", -69.99, "checking"))
        for raw, amount, dom, account in SUBSCRIPTIONS:
            add(Txn(date(y, m, dom), raw, -amount, account))
        for _ in range(int(rng.integers(1, 4))):
            add(Txn(date(y, m, int(rng.integers(1, 29))), "AMAZON MKTPLACE PMTS",
                    -_lognormal(rng, 35, 0.5), "credit"))
        for _ in range(int(rng.integers(1, 3))):
            add(Txn(date(y, m, int(rng.integers(1, 29))), "TARGET T-1432",
                    -_lognormal(rng, 45, 0.4), "credit"))
        if rng.random() < 0.8:
            add(Txn(date(y, m, int(rng.integers(1, 29))), "CVS/PHARMACY #0921",
                    -_lognormal(rng, 20, 0.4), "credit"))
        if rng.random() < 0.7:
            add(Txn(date(y, m, int(rng.integers(1, 29))), "AMC THEATRES 0412",
                    -_lognormal(rng, 28, 0.2), "credit"))
        if m == 12:  # holiday spike
            for _ in range(int(rng.integers(6, 11))):
                add(Txn(date(y, m, int(rng.integers(1, 24))),
                        str(rng.choice(["AMAZON MKTPLACE PMTS", "TARGET T-1432"])),
                        -_lognormal(rng, 85, 0.5), "credit"))

    # Occasional large purchases, 1-2 per quarter, never in the current month.
    quarters = sorted({(y, (m - 1) // 3) for y, m in _months()})
    for y, q in quarters:
        for _ in range(int(rng.integers(1, 3))):
            m = q * 3 + int(rng.integers(1, 4))
            if (y, m) == CURRENT_MONTH or date(y, m, 1) < START or date(y, m, 1) > END:
                continue
            add(Txn(date(y, m, int(rng.integers(1, 29))),
                    str(rng.choice(["BEST BUY 00412", "IKEA SEATTLE"])),
                    -_money(rng.uniform(300, 1200)), "credit"))

    weekend_heavy = np.array([1, 1, 1, 1, 1.5, 2.5, 2.5])
    weekday_heavy = np.array([2, 2, 2, 2, 2, 1, 1])

    def weekly(lo: int, hi: int, weights: np.ndarray, merchants: list[str], mean: float,
               sigma: float, account: str = "credit") -> None:
        for monday in _mondays():
            n = int(rng.integers(lo, hi + 1))
            offsets = rng.choice(7, size=n, replace=False, p=weights / weights.sum())
            for off in sorted(offsets):
                d = monday + timedelta(days=int(off))
                if START <= d <= END:
                    add(Txn(d, str(rng.choice(merchants)), -_lognormal(rng, mean, sigma),
                            account))

    weekly(1, 2, weekend_heavy, ["KROGER #412", "TRADER JOE'S #551", "WHOLE FOODS MKT"], 72, 0.2)
    weekly(2, 4, weekday_heavy, ["STARBUCKS #2231", "BLUE BOTTLE COFFEE"], 5.5, 0.15)
    weekly(1, 3, weekend_heavy, ["CHIPOTLE 1123", "THAI SPICE", "PANERA BREAD #601"], 22, 0.25)
    weekly(0, 2, weekend_heavy, ["UBER *TRIP"], 18, 0.3)
    weekly(3, 5, weekday_heavy, ["METRO TRANSIT"], 2.75, 0.0, "checking")
    gas = START + timedelta(days=int(rng.integers(0, 7)))
    while gas <= END:
        add(Txn(gas, "SHELL OIL 5741", -_lognormal(rng, 42, 0.1), "credit"))
        gas += timedelta(days=int(rng.integers(8, 13)))

    _plant(txns, rng)
    txns.sort(key=lambda t: (t.day, t.account, t.merchant, t.amount))
    return txns


def _plant(txns: list[Txn], rng: np.random.Generator) -> None:
    y, m = CURRENT_MONTH

    # 1. Three brand-new subscriptions totalling $47.
    for raw, amount, dom in PLANTED["new_recurring"]["raw"]:
        txns.append(Txn(date(y, m, dom), raw, -amount, "credit"))

    # 2. Duplicate charge within 48 hours.
    dup = PLANTED["duplicate_charge"]
    for dom in dup["days"]:
        txns.append(Txn(date(y, m, dom), dup["raw"], -dup["amount"], "credit"))

    # 3. Netflix price increase (+16.1%).
    # 4. Planet Fitness stops.
    for i, t in enumerate(list(txns)):
        if not _is_current(t.day):
            continue
        if t.merchant == "NETFLIX.COM":
            txns[i] = Txn(t.day, t.merchant, -PLANTED["amount_drift"]["amount"], t.account)
        elif t.merchant.startswith("PLANET FITNESS"):
            txns[i] = Txn(t.day, "__DROP__", 0, t.account)
    txns[:] = [t for t in txns if t.merchant != "__DROP__"]

    # 5. Dining spike: push the month total to trailing-6-month mean + 3 sigma.
    def dining_total(yy: int, mm: int) -> float:
        return -sum(t.amount for t in txns
                    if t.category == "dining" and (t.day.year, t.day.month) == (yy, mm))

    trailing = []
    yy, mm = y, m
    for _ in range(6):
        yy, mm = (yy - 1, 12) if mm == 1 else (yy, mm - 1)
        trailing.append(dining_total(yy, mm))
    target = float(np.mean(trailing) + 3 * np.std(trailing, ddof=1))
    while dining_total(y, m) < target:
        dom = int(rng.integers(1, 31))
        txns.append(Txn(date(y, m, dom), str(rng.choice(["THAI SPICE", "CHIPOTLE 1123"])),
                        -_lognormal(rng, 32, 0.3), "credit"))


def to_clean_csv(txns: list[Txn]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "merchant", "amount", "category", "account"])
    for t in txns:
        w.writerow([t.day.isoformat(), t.merchant, f"{t.amount:.2f}", t.category, t.account])
    return buf.getvalue()


def to_messy_csv(txns: list[Txn]) -> str:
    """A realistic bank export: renamed columns, MM/DD/YYYY, $ amounts, debit/credit column."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Transaction Date", "Description ", "Amount", "Transaction Type"])
    for t in reversed(txns):
        kind = "CREDIT" if t.amount > 0 else "DEBIT"
        w.writerow([t.day.strftime("%m/%d/%Y"), t.merchant, f"${abs(t.amount):,.2f}", kind])
    return buf.getvalue()


def write_fixtures() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    main = generate(42)
    files = {
        "demo_persona.csv": to_clean_csv(main),
        "demo_persona_seed7.csv": to_clean_csv(generate(7)),
        "messy_bank_export.csv": to_messy_csv(main),
    }
    for name, text in files.items():
        (FIXTURES / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {FIXTURES / name} ({text.count(chr(10)) - 1} rows)")


if __name__ == "__main__":
    write_fixtures()
