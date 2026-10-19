"""Seam 1: loading and validating a mapping spec."""

from __future__ import annotations

from pathlib import Path

from relay_engine.mapping import load_mapping

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def test_valid_spec_loads() -> None:
    spec = load_mapping(EXAMPLES / "chantiers.yaml")
    assert spec.entity == "chantiers"
    assert spec.source.table == "chantiers_legacy"
    assert spec.match_key == ["chantier_id"]
    assert spec.target_columns() == [
        "chantier_id", "libelle", "montant_marche", "date_ouverture",
        "rue", "code_postal", "ville",
    ]


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "mapping.yaml"
    path.write_text(body)
    return path


def test_missing_match_key_is_reported_readably(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    path = _write(tmp_path, """
version: 1
entity: sites
source: {table: anc_sites}
target: {table: sites}
columns:
  - {source: nom, target: nom, type: string}
""")
    with pytest.raises(MappingError) as exc:
        load_mapping(path)
    assert "match_key" in str(exc.value)
    assert "required" in str(exc.value)


CHANTIERS_SOURCE = ["chantier", "lib", "mnt_marche", "dt_ouv", "adresse_complete"]
CHANTIERS_TARGET = ["chantier_id", "libelle", "montant_marche", "date_ouverture",
                    "rue", "code_postal", "ville"]


def test_uncovered_target_column_is_reported() -> None:
    import pytest

    from relay_engine.mapping import MappingError, validate_mapping

    spec = load_mapping(EXAMPLES / "chantiers.yaml")
    with pytest.raises(MappingError) as exc:
        validate_mapping(spec, CHANTIERS_SOURCE, CHANTIERS_TARGET + ["statut"])
    assert "statut" in str(exc.value)
    assert "not mapped" in str(exc.value)


def test_reference_mapping_matches_generated_schemas() -> None:
    from relay_engine.mapping import validate_mapping

    spec = load_mapping(EXAMPLES / "chantiers.yaml")
    validate_mapping(spec, CHANTIERS_SOURCE, CHANTIERS_TARGET)


def test_unknown_source_column_is_reported() -> None:
    import pytest

    from relay_engine.mapping import MappingError, validate_mapping

    spec = load_mapping(EXAMPLES / "chantiers.yaml")
    source_without_lib = [c for c in CHANTIERS_SOURCE if c != "lib"]
    with pytest.raises(MappingError) as exc:
        validate_mapping(spec, source_without_lib, CHANTIERS_TARGET)
    assert "source column 'lib'" in str(exc.value)
    assert "does not exist" in str(exc.value)


def test_match_key_must_be_a_mapped_target_column(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError, validate_mapping

    path = _write(tmp_path, """
version: 1
entity: chantiers
source: {table: chantiers_legacy}
target: {table: chantiers_target}
match_key: [numero_chantier]
columns:
  - {source: chantier, target: chantier_id, type: string}
""")
    with pytest.raises(MappingError) as exc:
        validate_mapping(load_mapping(path), ["chantier"], ["chantier_id"])
    assert "match_key 'numero_chantier'" in str(exc.value)


def test_split_without_separator_is_rejected(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    path = _write(tmp_path, """
version: 1
entity: sites
source: {table: anc_sites}
target: {table: sites}
match_key: [rue]
columns:
  - {source: adresse_complete, target: [rue, ville], transform: split}
""")
    with pytest.raises(MappingError) as exc:
        load_mapping(path)
    assert "columns.0" in str(exc.value)
    assert "requires a separator" in str(exc.value)
    assert "Value error" not in str(exc.value)


def test_unknown_type_is_rejected(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    path = _write(tmp_path, """
version: 1
entity: sites
source: {table: anc_sites}
target: {table: sites}
match_key: [prix]
columns:
  - {source: prix, target: prix, type: money}
""")
    with pytest.raises(MappingError) as exc:
        load_mapping(path)
    assert "unknown type 'money'" in str(exc.value)


def test_inconsistent_entry_shapes_are_rejected(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    path = _write(tmp_path, """
version: 1
entity: sites
source: {table: anc_sites}
target: {table: sites}
match_key: [nom]
columns:
  - {source: [rue, ville], target: adresse, transform: split, separator: ", "}
  - {source: rue, target: adresse, transform: concat, separator: ", "}
  - {source: [a, b], target: nom}
  - {source: code, exclude: true, target: code}
""")
    with pytest.raises(MappingError) as exc:
        load_mapping(path)
    message = str(exc.value)
    assert "columns.0: split takes one source column and several targets" in message
    assert "columns.1: concat takes several source columns and one target" in message
    assert "columns.2: a plain mapping takes one source column and one target" in message
    assert "columns.3: an excluded column must not declare a target" in message


FACTURES_SOURCE = ["facture", "chantier", "mnt_ht", "dt"]
FACTURES_TARGET = ["facture_id", "chantier_id", "montant_hors_taxes", "date_facture"]


def test_references_load_and_validate() -> None:
    from relay_engine.mapping import validate_mapping

    spec = load_mapping(EXAMPLES / "factures.yaml")
    assert [(r.column, r.table, r.key) for r in spec.references] == [
        ("chantier_id", "chantiers_target", "chantier_id")
    ]
    validate_mapping(
        spec, FACTURES_SOURCE, FACTURES_TARGET,
        referenced_columns={"chantiers_target": CHANTIERS_TARGET},
    )


def test_broken_references_are_reported() -> None:
    import pytest

    from relay_engine.mapping import MappingError, validate_mapping

    spec = load_mapping(EXAMPLES / "factures.yaml").model_copy(deep=True)
    spec.references[0].column = "id_chantier"
    with pytest.raises(MappingError) as exc:
        validate_mapping(spec, FACTURES_SOURCE, FACTURES_TARGET, referenced_columns={})
    message = str(exc.value)
    assert "references.0: column 'id_chantier' is not a target column" in message
    assert "references.0: table 'chantiers_target' does not exist" in message


def test_reference_to_unknown_key_is_reported() -> None:
    import pytest

    from relay_engine.mapping import MappingError, validate_mapping

    spec = load_mapping(EXAMPLES / "factures.yaml")
    with pytest.raises(MappingError) as exc:
        validate_mapping(
            spec, FACTURES_SOURCE, FACTURES_TARGET,
            referenced_columns={"chantiers_target": ["id"]},
        )
    assert "references.0: key 'chantier_id' does not exist in 'chantiers_target'" in str(
        exc.value
    )


def test_unknown_normalize_rule_is_rejected(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    path = _write(tmp_path, """
version: 1
entity: items
source: {table: a}
target: {table: b}
match_key: [prix]
columns:
  - {source: prix, target: prix, type: decimal(12,2), normalize: [decimal_coma]}
""")
    with pytest.raises(MappingError) as exc:
        load_mapping(path)
    assert "unknown normalize rule 'decimal_coma'" in str(exc.value)
    assert "decimal_comma" in str(exc.value)


def test_max_duplicate_share_defaults_to_five_percent_and_stays_within_0_and_1(
    tmp_path: Path,
) -> None:
    from decimal import Decimal

    import pytest

    from relay_engine.mapping import MappingError

    body = """
version: 1
entity: sites
source: {table: anc_sites}
target: {table: sites}
match_key: [code]
columns:
  - {source: code, target: code, type: string}
"""
    assert load_mapping(_write(tmp_path, body)).max_duplicate_share == Decimal("0.05")
    assert load_mapping(
        _write(tmp_path, body + "max_duplicate_share: 0.1\n")
    ).max_duplicate_share == Decimal("0.1")
    for wrong in ("1.5", "-0.1"):
        with pytest.raises(MappingError) as exc:
            load_mapping(_write(tmp_path, body + f"max_duplicate_share: {wrong}\n"))
        assert "max_duplicate_share" in str(exc.value)


TARGET_ONLY = """
version: 1
entity: sites
source: {table: anc_sites}
target: {table: sites}
match_key: [code]
columns:
  - {source: code, target: code, type: string}
  - target: statut
    target_only: true
    reason: "field created by the new ERP"
"""


def test_a_target_only_column_is_covered_but_not_produced(tmp_path: Path) -> None:
    from relay_engine.mapping import validate_mapping

    spec = load_mapping(_write(tmp_path, TARGET_ONLY))
    assert spec.target_columns() == ["code"]
    assert list(spec.entries_by_target()) == ["code", "statut"]
    validate_mapping(spec, ["code"], ["code", "statut"])


def test_a_target_only_column_takes_nothing_but_a_reason(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    for extra in ("source: statut", "type: string", "normalize: [trim]", "exclude: true"):
        flag = "    target_only: true\n"
        body = TARGET_ONLY.replace(flag, f"{flag}    {extra}\n")
        with pytest.raises(MappingError) as exc:
            load_mapping(_write(tmp_path, body))
        assert "a target-only column declares only its target and a reason" in str(exc.value)


def test_an_entry_without_source_points_to_target_only(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    body = TARGET_ONLY.replace("    target_only: true\n", "")
    with pytest.raises(MappingError) as exc:
        load_mapping(_write(tmp_path, body))
    assert "columns.1: source is required; a target column without source is declared " \
        "with target_only: true" in str(exc.value)


def test_target_only_columns_are_checked_against_the_target(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError, validate_mapping

    spec = load_mapping(_write(tmp_path, TARGET_ONLY.replace("match_key: [code]",
                                                             "match_key: [statut]")))
    with pytest.raises(MappingError) as exc:
        validate_mapping(spec, ["code"], ["code"])
    assert exc.value.problems == [
        "target column 'statut' does not exist in the target data",
        "match_key 'statut' is a target-only column: it has no source to match",
    ]


def test_a_date_format_needs_a_date_column_and_a_readable_pattern(tmp_path: Path) -> None:
    import pytest

    from relay_engine.mapping import MappingError

    def load(entry: str) -> None:
        load_mapping(_write(tmp_path, f"""
version: 1
entity: sites
source: {{table: anc_sites}}
target: {{table: sites}}
match_key: [code]
columns:
  - {{source: code, target: code, type: string}}
  - {{source: cree, target: cree, {entry}}}
"""))

    load("type: date, source_format: '%d/%m/%Y', target_format: '%d/%m/%Y %H:%M'")
    load("type: string, normalize: [date_only], source_format: '%d/%m/%Y'")
    for entry, problem in (
        ("type: string, source_format: '%d/%m/%Y'",
         "source_format applies to a date or datetime column"),
        ("type: date, target_format: '%Q'",
         "target_format '%Q' cannot read back the dates it writes"),
        ("type: date, source_format: 'jj/mm/aaaa'",
         "source_format 'jj/mm/aaaa' cannot read back the dates it writes"),
    ):
        with pytest.raises(MappingError) as exc:
            load(entry)
        assert problem in str(exc.value), entry
