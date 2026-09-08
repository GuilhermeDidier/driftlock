"""Contract engine behaviour.

The tests that matter most are the two silent killers: a source that starts
returning nothing, and a source that starts returning the same thing.
"""
from __future__ import annotations

import pytest

from contracts.engine import ContractSpec, FieldSpec, FieldType, Verdict, validate
from contracts.engine.coerce import CoercionError, parse_number


def listing_contract(**overrides) -> ContractSpec:
    defaults = dict(
        key="product_listing",
        fields=(
            FieldSpec("name", FieldType.STRING,
                      "the product title as shown on the card", max_length=200),
            FieldSpec("price", FieldType.NUMBER,
                      "the current selling price in BRL", min_value=0),
            FieldSpec("url", FieldType.URL, "link to the product page"),
            FieldSpec("in_stock", FieldType.BOOLEAN,
                      "whether the card shows availability", required=False),
        ),
        min_records=3,
        min_fill_rate={"name": 0.9, "price": 0.8, "url": 0.9},
        min_distinct_ratio={"name": 0.5, "url": 0.9},
        unique_by=("url",),
    )
    defaults.update(overrides)
    return ContractSpec(**defaults)


def rows(n: int = 5, patch: dict | None = None):
    patch = patch or {}
    out = []
    for i in range(n):
        row = {
            "name": f"Produto {i}",
            "price": f"R$ {100 + i},50",
            "url": f"https://loja.example/p/{i}",
            "in_stock": "sim",
        }
        row.update({k: (v(i) if callable(v) else v) for k, v in patch.items()})
        out.append(row)
    return out


class TestVerdicts:
    def test_clean_batch_passes(self):
        report = validate(listing_contract(), rows())
        assert report.verdict is Verdict.PASS
        assert len(report.publishable) == 5
        assert report.records[0].value["price"] == 100.5

    def test_one_dirty_row_is_quarantined_batch_still_ships(self):
        batch = rows()
        batch[2]["price"] = "-R$ 40,00"  # below the declared minimum
        report = validate(listing_contract(), batch)

        assert report.verdict is Verdict.PARTIAL
        assert len(report.quarantined) == 1
        assert report.quarantined[0].index == 2
        assert [v.code for v in report.quarantined[0].violations] == ["below_min"]
        assert len(report.publishable) == 4  # the good rows still go through


class TestSilentKillers:
    """The failures that do not raise."""

    def test_selector_returning_nothing_is_drift(self):
        # price extraction broke: every row comes back empty
        report = validate(listing_contract(), rows(patch={"price": ""}))

        assert report.verdict is Verdict.DRIFT
        codes = {v.code for v in report.batch_violations}
        assert "fill_rate_below_threshold" in codes
        assert report.fill_rates["price"] == 0.0

    def test_selector_collapsing_onto_one_element_is_drift(self):
        # classic: the selector drifted onto a header, so every row is identical
        report = validate(listing_contract(), rows(patch={"name": "Ofertas da semana"}))

        assert report.verdict is Verdict.DRIFT
        collapsed = [v for v in report.batch_violations
                     if v.code == "distinct_ratio_below_threshold"]
        assert len(collapsed) == 1
        assert collapsed[0].field == "name"
        assert report.distinct_ratios["name"] == pytest.approx(0.2)

    def test_drift_publishes_nothing_even_when_rows_look_clean(self):
        """The fail-closed guarantee.

        Every row here passes per-record validation on its own. Only the batch
        view reveals the source changed. Nothing may ship.
        """
        report = validate(listing_contract(), rows(patch={"name": "Ofertas da semana"}))

        assert report.quarantined == []          # no row is individually bad
        assert report.verdict is Verdict.DRIFT
        assert report.publishable == []          # and yet nothing ships

    def test_empty_field_reports_once_not_twice(self):
        report = validate(listing_contract(), rows(patch={"url": ""}))
        codes = [v.code for v in report.batch_violations if v.field == "url"]
        assert codes == ["fill_rate_below_threshold"]


class TestRecordRules:
    def test_required_missing(self):
        batch = rows()
        batch[0]["name"] = "   "
        report = validate(listing_contract(min_fill_rate={}), batch)
        assert [v.code for v in report.records[0].violations] == ["required_missing"]

    def test_optional_field_may_be_empty(self):
        report = validate(listing_contract(), rows(patch={"in_stock": ""}))
        assert report.verdict is Verdict.PASS

    def test_duplicates_keep_the_first(self):
        batch = rows(4)
        batch[3]["url"] = batch[1]["url"]
        report = validate(listing_contract(min_distinct_ratio={}), batch)
        assert report.records[1].ok
        assert [v.code for v in report.records[3].violations] == ["duplicate_key"]

    def test_too_few_records_is_drift(self):
        report = validate(listing_contract(), rows(2))
        assert report.verdict is Verdict.DRIFT
        assert {v.code for v in report.batch_violations} == {"too_few_records"}

    def test_unreadable_value_is_a_type_violation_not_a_crash(self):
        batch = rows()
        batch[1]["price"] = "sob consulta"
        report = validate(listing_contract(min_fill_rate={}), batch)
        assert [v.code for v in report.records[1].violations] == ["type_invalid"]


class TestCoercion:
    @pytest.mark.parametrize("raw,expected", [
        ("R$ 1.234,56", 1234.56),   # pt-BR
        ("$1,234.56", 1234.56),     # en-US
        ("1234.56", 1234.56),
        ("12,5", 12.5),
        ("1.234.567", 1234567.0),
        ("(1,234.56)", -1234.56),   # accounting negative
        ("-R$ 5,00", -5.0),
    ])
    def test_human_written_numbers(self, raw, expected):
        assert parse_number(raw) == pytest.approx(expected)

    def test_ambiguous_three_digit_group_reads_as_thousands(self):
        # documented trade-off: "1.500" is 1500, not 1.5
        assert parse_number("1.500") == 1500.0

    def test_garbage_raises_rather_than_guessing(self):
        with pytest.raises(CoercionError):
            parse_number("preço a combinar")
