"""CSV -> normalized DataFrame.

Output columns: date (datetime64), merchant (raw), display (clean name), amount (float,
negative = outflow), category, account. Accepts the canonical schema
(date,merchant,amount,category,account) and common bank-export variants.
"""

import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from backend.contract import DatasetInfo
from data.merchants import lookup

ALIASES = {
    "date": ["date", "transaction date", "posting date", "posted date", "trans date"],
    "merchant": ["merchant", "description", "payee", "name", "details", "memo"],
    "amount": ["amount", "transaction amount", "value"],
    "debit": ["debit", "withdrawal", "withdrawals", "money out"],
    "credit": ["credit", "deposit", "deposits", "money in"],
    "type": ["type", "transaction type", "dr/cr", "debit/credit"],
    "category": ["category"],
    "account": ["account", "account name", "account type"],
}
OUTFLOW_TYPES = {"debit", "dr", "withdrawal", "purchase", "payment", "sale"}


class CsvError(ValueError):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


@dataclass
class Ledger:
    df: pd.DataFrame
    info: DatasetInfo


def _parse_money(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    negative = s.str.startswith("(") & s.str.endswith(")")
    cleaned = s.str.replace(r"[$,()\s]", "", regex=True).replace({"": None, "nan": None})
    values = pd.to_numeric(cleaned, errors="coerce")
    return values.where(~negative, -values.abs())


def _resolve_columns(columns: list[str]) -> dict[str, str]:
    normalized = {c: re.sub(r"\s+", " ", str(c)).strip().lower() for c in columns}
    found: dict[str, str] = {}
    for key, names in ALIASES.items():
        for original, norm in normalized.items():
            if norm in names and key not in found:
                found[key] = original
    return found


def _parse_dates(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        parsed = pd.to_datetime(s, format=fmt, errors="coerce")
        if parsed.notna().all():
            return parsed
    return pd.to_datetime(s, errors="coerce")


def load_csv(content: str | bytes, name: str, source: str = "upload") -> Ledger:
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig", errors="replace")
    try:
        raw = pd.read_csv(io.StringIO(content), dtype=str, keep_default_na=False)
    except Exception as exc:  # pandas raises several parser error types
        raise CsvError("Could not read the file as CSV", [str(exc)]) from exc
    if raw.empty:
        raise CsvError("The file has no transactions")

    cols = _resolve_columns(list(raw.columns))
    missing = [k for k in ("date", "merchant") if k not in cols]
    if "amount" not in cols and not ("debit" in cols or "credit" in cols):
        missing.append("amount")
    if missing:
        raise CsvError("Missing required columns", [f"no column for {m}" for m in missing])

    df = pd.DataFrame()
    df["date"] = _parse_dates(raw[cols["date"]])
    df["merchant"] = raw[cols["merchant"]].astype(str).str.strip()

    if "amount" in cols:
        amount = _parse_money(raw[cols["amount"]])
        if "type" in cols:
            kind = raw[cols["type"]].astype(str).str.strip().str.lower()
            amount = amount.abs().where(~kind.isin(OUTFLOW_TYPES), -amount.abs())
    else:
        debit = _parse_money(raw[cols["debit"]]).fillna(0) if "debit" in cols else 0
        credit = _parse_money(raw[cols["credit"]]).fillna(0) if "credit" in cols else 0
        amount = pd.Series(credit, index=raw.index) - pd.Series(debit, index=raw.index).abs()
    df["amount"] = amount.round(2)

    bad = df["date"].isna() | df["amount"].isna() | (df["merchant"] == "")
    if bad.any():
        rows = [str(i + 2) for i in df.index[bad][:5]]
        raise CsvError(
            f"{int(bad.sum())} rows could not be read",
            [f"check row {r} (date, merchant and amount are required)" for r in rows],
        )

    looked_up = df["merchant"].map(lookup)
    df["display"] = looked_up.map(lambda x: x[0])
    given = raw[cols["category"]].astype(str).str.strip().str.lower() if "category" in cols else ""
    df["category"] = looked_up.map(lambda x: x[1])
    if "category" in cols:
        df["category"] = given.where(given != "", df["category"])
    df.loc[df["amount"] > 0, "category"] = df.loc[df["amount"] > 0, "category"].where(
        df.loc[df["amount"] > 0, "category"] != "other", "income"
    )
    df["account"] = raw[cols["account"]].astype(str).str.strip() if "account" in cols else "unknown"

    df = df.sort_values(["date", "merchant", "amount"], kind="stable").reset_index(drop=True)
    return Ledger(df=df, info=_info(df, name, source))


def load_path(path: str | Path, source: str = "fixture") -> Ledger:
    p = Path(path)
    return load_csv(p.read_bytes(), p.name, source)


def period_label(d: date | pd.Timestamp) -> str:
    return pd.Timestamp(d).strftime("%B %Y")


def _info(df: pd.DataFrame, name: str, source: str) -> DatasetInfo:
    return DatasetInfo(
        source=source,
        name=name,
        row_count=len(df),
        date_min=df["date"].min().date(),
        date_max=df["date"].max().date(),
        current_period=period_label(df["date"].max()),
    )
