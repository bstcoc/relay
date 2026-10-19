"""The scenario contract of the real-data oracle."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from relay_engine.oracle.scenario import Expectation, ScenarioError, load_scenario


def test_tier1_scenario_loads(demo_scenario: Callable[..., Path]) -> None:
    scenario = load_scenario(demo_scenario())
    assert scenario.tier == 1
    assert scenario.intents == []
    assert scenario.target_table == "shop"
    assert scenario.mapping.entity == "shops"
    assert scenario.migrate.name == "migrate.py"


def test_missing_files_are_listed_at_once(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError) as error:
        load_scenario(tmp_path)
    assert error.value.problems == [
        "mapping.yaml is missing", "sources.yaml is missing", "migrate.py is missing",
    ]


@pytest.mark.parametrize(
    "line", ["import relay_engine", "from relay_engine.layers.silver import conform"]
)
def test_migration_that_imports_relay_is_refused(
    demo_scenario: Callable[..., Path], line: str
) -> None:
    root = demo_scenario(migrate=f"{line}\n")
    with pytest.raises(ScenarioError) as error:
        load_scenario(root)
    assert error.value.problems == [
        "migrate.py imports relay_engine: the migration must not know Relay"
    ]


def test_a_comment_naming_relay_is_allowed(demo_scenario: Callable[..., Path]) -> None:
    root = demo_scenario(migrate="# written without relay_engine on purpose\n")
    assert load_scenario(root).tier == 1


def test_target_must_be_sqlite_read_from_the_oracle_variable(
    demo_scenario: Callable[..., Path],
) -> None:
    root = demo_scenario()
    sources = root / "sources.yaml"
    sources.write_text(sources.read_text().replace("${RELAY_ORACLE_TARGET}", "/tmp/fixed.db"))
    with pytest.raises(ScenarioError) as error:
        load_scenario(root)
    assert error.value.problems == [
        "sources.yaml: target table shops_target must be read from "
        "database: sqlite:///${RELAY_ORACLE_TARGET}"
    ]


def test_intents_make_a_tier2_scenario(demo_scenario: Callable[..., Path]) -> None:
    root = demo_scenario(intents="""\
intents:
  - name: upper_city
    why: "cities written in capitals"
    expects:
      column: city
      rule: value differs
""")
    scenario = load_scenario(root)
    assert scenario.tier == 2
    assert [i.name for i in scenario.intents] == ["upper_city"]


def test_an_intent_must_expect_something(demo_scenario: Callable[..., Path]) -> None:
    root = demo_scenario(intents="""\
intents:
  - name: vague
    why: "no expectation"
    expects: {}
""")
    with pytest.raises(ScenarioError) as error:
        load_scenario(root)
    assert len(error.value.problems) == 1
    assert error.value.problems[0].startswith("intents.yaml: intents.0.expects")
    assert "at least one of check, column or rule" in error.value.problems[0]


def test_an_invalid_mapping_is_reported(demo_scenario: Callable[..., Path]) -> None:
    root = demo_scenario(mapping="version: 1\nentity: shops\n")
    with pytest.raises(ScenarioError) as error:
        load_scenario(root)
    assert error.value.problems
    assert all(p.startswith("mapping.yaml: ") for p in error.value.problems)


def test_expectation_matches_on_every_declared_field() -> None:
    expects = Expectation(column="city", rule="value differs")
    assert expects.matches("fidelity", "city", "value differs")
    assert not expects.matches("fidelity", "name", "value differs")
    assert not expects.matches("fidelity", "city", "value lost in target")
    assert Expectation(check="completeness").matches("completeness", None, "anything")


@pytest.mark.parametrize(
    "extra",
    [
        "business_rules:\n  - name: positive\n    check: \"city <> ''\"\n",
        "references:\n  - column: city\n    table: cities\n    key: name\n",
    ],
)
def test_rules_and_references_are_out_of_scope_in_v1(
    demo_scenario: Callable[..., Path], extra: str
) -> None:
    from conftest import DEMO_MAPPING

    with pytest.raises(ScenarioError) as error:
        load_scenario(demo_scenario(mapping=DEMO_MAPPING + extra))
    assert error.value.problems == [
        "mapping.yaml: business_rules and references are not supported by the oracle yet"
    ]
