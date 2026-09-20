"""What this ledger actually contains: categories and merchants, plus the everyday words
people use for them.

Both the pattern router and the model parser resolve subjects through here, so a question
can only ever be about something that exists in the data. "How much on pets?" with no pet
spending resolves to nothing and gets an honest answer, never a guess.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from backend.contract import Subject, SubjectKind

# Everyday word -> canonical category. Only ever consulted for categories present in the data.
SYNONYMS = {
    "eating out": "dining", "restaurants": "dining", "restaurant": "dining",
    "takeout": "dining", "take out": "dining", "food out": "dining", "meals": "dining",
    "eat out": "dining", "eating": "dining", "lunch": "dining", "dinner": "dining",
    "food shopping": "groceries", "grocery": "groceries", "supermarket": "groceries",
    "food": "groceries", "shopping for food": "groceries",
    "gas": "transport", "fuel": "transport", "petrol": "transport", "commute": "transport",
    "travel": "transport", "rides": "transport", "transportation": "transport",
    "streaming": "subscriptions", "subscription": "subscriptions", "subs": "subscriptions",
    "memberships": "subscriptions", "membership": "subscriptions",
    "bills": "utilities", "utility": "utilities", "power": "utilities",
    "electricity": "utilities", "water": "utilities", "internet": "utilities",
    "housing": "rent", "mortgage": "rent", "apartment": "rent",
    "coffee shops": "coffee", "cafe": "coffee", "cafes": "coffee",
    "medical": "health", "pharmacy": "health", "doctor": "health", "medicine": "health",
    "fun": "entertainment", "movies": "entertainment", "cinema": "entertainment",
    "salary": "income", "paycheck": "income", "pay": "income", "wages": "income",
    "earnings": "income", "deposits": "income",
    "stuff": "shopping", "purchases": "shopping", "retail": "shopping",
}

_WORD = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class Vocabulary:
    categories: tuple[str, ...] = ()
    merchants: tuple[str, ...] = ()
    # merchant display name -> total spend, used to order the parser prompt by prominence
    merchant_spend: dict[str, float] = field(default_factory=dict)

    def top_merchants(self, n: int = 25) -> list[str]:
        return sorted(self.merchants, key=lambda m: -self.merchant_spend.get(m, 0.0))[:n]

    def resolve(self, text: str) -> Subject | None:
        """Exact, then synonym, then substring, then token overlap. No fuzzy guessing."""
        q = " ".join(_WORD.findall(text.lower())).strip()
        if not q:
            return None

        for category in self.categories:
            if q == category.lower():
                return Subject(kind=SubjectKind.category, value=category)
        for merchant in self.merchants:
            if q == merchant.lower():
                return Subject(kind=SubjectKind.merchant, value=merchant)

        canonical = SYNONYMS.get(q)
        if canonical and canonical in self.categories:
            return Subject(kind=SubjectKind.category, value=canonical)

        for merchant in sorted(self.merchants, key=len, reverse=True):
            name = merchant.lower()
            if name in q or q in name:
                return Subject(kind=SubjectKind.merchant, value=merchant)
        for category in self.categories:
            if category.lower() in q:
                return Subject(kind=SubjectKind.category, value=category)
        for phrase, cat in SYNONYMS.items():
            if cat in self.categories and phrase in q:
                return Subject(kind=SubjectKind.category, value=cat)

        tokens = set(_WORD.findall(q))
        for merchant in self.merchants:
            if tokens & set(_WORD.findall(merchant.lower())):
                return Subject(kind=SubjectKind.merchant, value=merchant)
        return None

    def validate(self, subject: Subject) -> Subject | None:
        """Accept a subject only if it names something really in the ledger."""
        if subject.kind == SubjectKind.all:
            return Subject()
        if not subject.value:
            return None
        pool = self.categories if subject.kind == SubjectKind.category else self.merchants
        for known in pool:
            if known.lower() == subject.value.lower():
                return Subject(kind=subject.kind, value=known)
        return self.resolve(subject.value)


@lru_cache(maxsize=4)
def _build(digest: str, categories: tuple[str, ...], merchants: tuple[str, ...],
           spend: tuple[tuple[str, float], ...]) -> Vocabulary:
    return Vocabulary(categories=categories, merchants=merchants, merchant_spend=dict(spend))


def build(df: pd.DataFrame, digest: str = "") -> Vocabulary:
    categories = tuple(sorted(df["category"].dropna().unique()))
    spend = (
        df[df["amount"] < 0].groupby("display")["amount"].sum().abs().sort_values(ascending=False)
    )
    merchants = tuple(str(m) for m in spend.index)
    totals = tuple((str(k), float(v)) for k, v in spend.items())
    return _build(digest, categories, merchants, totals)
