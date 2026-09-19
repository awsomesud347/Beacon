import pytest

from backend.analysis.loader import CsvError, load_csv, load_path
from data.generate import FIXTURES, generate, to_clean_csv, to_messy_csv


def test_fixtures_match_generator():
    txns = generate(42)
    assert (FIXTURES / "demo_persona.csv").read_text() == to_clean_csv(txns)
    assert (FIXTURES / "messy_bank_export.csv").read_text() == to_messy_csv(txns)
    assert (FIXTURES / "demo_persona_seed7.csv").read_text() == to_clean_csv(generate(7))


def test_messy_export_matches_clean():
    clean = load_path(FIXTURES / "demo_persona.csv").df
    messy = load_path(FIXTURES / "messy_bank_export.csv").df
    assert len(clean) == len(messy)
    assert messy["amount"].sum() == pytest.approx(clean["amount"].sum())
    by_cat = lambda df: df.groupby("category")["amount"].sum().round(2).to_dict()  # noqa: E731
    assert by_cat(messy) == by_cat(clean)
    assert (messy["date"].values == clean["date"].values).all()


def test_info():
    info = load_path(FIXTURES / "demo_persona.csv").info
    assert info.current_period == "September 2026"
    assert str(info.date_min) == "2025-08-01"
    assert info.source == "fixture"


def test_debit_credit_columns_and_parentheses():
    csv = (
        "Date,Payee,Debit,Credit\n"
        '01/05/2026,KROGER #1,"$1,020.50",\n'
        "01/06/2026,ACME PAYROLL,,100\n"
    )
    df = load_csv(csv, "x.csv").df
    assert df["amount"].tolist() == [-1020.50, 100.0]
    assert df["category"].tolist() == ["groceries", "income"]
    paren = load_csv("date,description,amount\n2026-01-01,SHOP,($12.00)\n", "p.csv").df
    assert paren["amount"].tolist() == [-12.0]


@pytest.mark.parametrize(
    "csv,message",
    [
        ("foo,bar\n1,2\n", "Missing required columns"),
        ("date,merchant,amount\n", "no transactions"),
        ("date,merchant,amount\nnot-a-date,X,1\n", "could not be read"),
    ],
)
def test_rejects_bad_files(csv, message):
    with pytest.raises(CsvError, match=message):
        load_csv(csv, "bad.csv")
