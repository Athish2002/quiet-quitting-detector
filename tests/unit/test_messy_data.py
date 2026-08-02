# Real-world data robustness: identity resolution and tolerant value parsing.
#
# Each case here was reproduced against the previous implementation before the
# fix was written. The three defects:
#
#   MERGE  -- "Arjun Sharma" and "Arjun Patel" both keyed to "Arjun", blending
#             two people's timelines into one.
#   SPLIT  -- "Arjun" / "arjun" / " ARJUN " keyed as three people, fragmenting
#             one person's history so no baseline could form.
#   FABRICATE -- an absent metric was written as a plausible default (0 tasks,
#             40 hours), making incomplete data indistinguishable from total
#             disengagement.

import pytest

from src.data_layer.coercion import Quality, completeness, parse_count, parse_hours
from src.data_layer.identity import IdentityResolver, normalize_name, reset_resolver
from src.data_layer.preprocessing import preprocess_employee_records


@pytest.fixture(autouse=True)
def _isolated_identity(tmp_path, monkeypatch):

    monkeypatch.setenv("IDENTITY_MAP_PATH", str(tmp_path / "idmap.json"))
    monkeypatch.setenv("IDENTITY_SALT", "test-salt-not-a-secret")
    reset_resolver()
    yield
    reset_resolver()


def _row(name, week=1, **kw):
    return {"name": name, "__week_number__": week, "__source_file__": "w", **kw}


# ---------------------------------------------------------------------------
# Name normalisation -- the variance that actually appears in exports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    [
        "Arjun Sharma",
        "arjun sharma",
        "  ARJUN   SHARMA  ",
        "Sharma, Arjun",
        "Mr. Arjun Sharma",
        "Arjun Sharma Jr.",
        "Arjun" + chr(0xA0) + "Sharma",
    ],
)
def test_name_variants_normalize_to_one_key(variant):
    assert normalize_name(variant) == "arjun sharma"


def test_accents_and_transliteration_fold_together():
    assert normalize_name("José García") == normalize_name("Jose Garcia")


def test_punctuation_variants_fold_together():
    assert normalize_name("O'Brien") == normalize_name("OBrien")


# ---------------------------------------------------------------------------
# SPLIT bug -- one person must stay one person
# ---------------------------------------------------------------------------


def test_casing_and_padding_variants_are_one_person():
    rows = [
        _row("Arjun Sharma", 1),
        _row("arjun sharma", 2),
        _row("  ARJUN SHARMA  ", 3),
    ]
    records, _ = preprocess_employee_records(rows, key_by_surrogate=True)
    assert len(records) == 1, "same person fragmented across casing variants"
    assert len(next(iter(records.values()))) == 3


def test_surrogate_id_is_stable_across_resolver_instances(tmp_path):
    """Baselines depend on keys surviving a restart."""
    p = str(tmp_path / "m.json")
    first = IdentityResolver(p).resolve({"name": "Arjun Sharma"}).surrogate_id
    second = IdentityResolver(p).resolve({"name": "arjun  sharma"}).surrogate_id
    assert first == second


# ---------------------------------------------------------------------------
# MERGE bug -- different people must stay different
# ---------------------------------------------------------------------------


def test_distinct_people_sharing_a_first_name_do_not_merge():
    rows = [
        _row("Arjun Sharma", 1, completed_tasks="20"),
        _row("Arjun Patel", 1, completed_tasks="2"),
    ]
    records, _ = preprocess_employee_records(rows, key_by_surrogate=True)
    assert len(records) == 2, "two different people merged into one timeline"


def test_employee_id_beats_name_entirely():
    """An ID column is the only key that survives a rename."""
    rows = [
        _row("Priya Nair", 1, employee_id="E-77"),
        _row("Priya Menon", 2, employee_id="E-77"),
    ]  # legal name change
    records, _ = preprocess_employee_records(rows, key_by_surrogate=True)
    assert len(records) == 1, "same employee_id must be one person despite rename"


def test_same_name_different_ids_stay_separate():
    rows = [
        _row("Arjun Sharma", 1, employee_id="E-1"),
        _row("Arjun Sharma", 1, employee_id="E-2"),
    ]
    records, _ = preprocess_employee_records(rows, key_by_surrogate=True)
    assert len(records) == 2


def test_registered_alias_preserves_history_across_rename(tmp_path):
    p = str(tmp_path / "m.json")
    r = IdentityResolver(p)
    before = r.resolve({"name": "Priya Nair", "employee_id": "E-9"}).surrogate_id
    r.register_alias("Priya Nair", "E-9")
    after = r.resolve({"name": "Priya Nair"}).surrogate_id  # later file, no ID column
    assert before == after


def test_bare_first_name_shared_by_several_people_is_flagged():
    """The genuinely unresolvable case: a source supplies only "Arjun" and more
    than one Arjun exists, so their metrics cannot be told apart."""
    r = IdentityResolver()
    r.resolve({"name": "Arjun Sharma"})
    r.resolve({"name": "Arjun Patel"})
    assert r.resolve({"name": "Arjun"}).is_ambiguous


def test_full_names_sharing_a_first_name_are_not_flagged_ambiguous():
    """These resolved correctly; warning here would be crying wolf."""
    r = IdentityResolver()
    r.resolve({"name": "Arjun Sharma"})
    assert not r.resolve({"name": "Arjun Patel"}).is_ambiguous


def test_surrogate_id_contains_no_real_name():
    """Pseudonymization: storage keys must not leak identity."""
    ident = IdentityResolver().resolve({"name": "Arjun Sharma"})
    assert "arjun" not in ident.surrogate_id.lower()
    assert "sharma" not in ident.surrogate_id.lower()
    assert ident.surrogate_id.startswith("emp_")


def test_salt_changes_the_pseudonym(tmp_path, monkeypatch):
    monkeypatch.setenv("IDENTITY_SALT", "salt-a-not-a-secret")
    a = IdentityResolver(str(tmp_path / "a.json")).resolve({"name": "Ada"}).surrogate_id
    monkeypatch.setenv("IDENTITY_SALT", "salt-b-not-a-secret")
    b = IdentityResolver(str(tmp_path / "b.json")).resolve({"name": "Ada"}).surrogate_id
    assert a != b


# ---------------------------------------------------------------------------
# FABRICATE bug -- missing must never become a value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentinel",
    [
        "",
        "  ",
        "N/A",
        "n/a",
        "NULL",
        "none",
        "-",
        "unknown",
        "TBD",
        "?",
        "#N/A",
        "missing",
    ],
)
def test_sentinels_are_missing_not_zero(sentinel):
    result = parse_count(sentinel)
    assert result.value is None
    assert result.quality is Quality.MISSING


def test_absent_metric_stays_none_through_preprocessing():
    records, _ = preprocess_employee_records([_row("Ada", 1)])
    week = records["Ada"][0]
    assert week["completed_tasks"] is None, "absent count must not become 0"
    assert week["weekly_hours"] is None, "absent hours must not become 40"


def test_real_zero_is_preserved_and_distinguishable_from_missing():
    records, _ = preprocess_employee_records([_row("Ada", 1, completed_tasks="0")])
    assert records["Ada"][0]["completed_tasks"] == 0


def test_low_confidence_flag_set_on_thin_records():
    records, _ = preprocess_employee_records([_row("Ada", 1)])
    assert records["Ada"][0]["data_quality"]["low_confidence"] is True


def test_complete_record_is_not_low_confidence():
    records, _ = preprocess_employee_records(
        [
            _row(
                "Ada",
                1,
                completed_tasks="8",
                avg_response_time="1.5",
                after_hours_logins="1",
                weekly_hours="40",
            )
        ]
    )
    assert records["Ada"][0]["data_quality"]["low_confidence"] is False


# ---------------------------------------------------------------------------
# Format variance -- messy but legitimate values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("8", 8),
        (" 8 ", 8),
        ("8.0", 8),
        ("08", 8),
        ("1,234", 1234),
        ("~5", 5),
        ("12 tasks", 12),
    ],
)
def test_counts_parse_from_messy_cells(raw, expected):
    assert parse_count(raw).value == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2.5", 2.5),
        ("2.5h", 2.5),
        ("90m", 1.5),
        ("90 min", 1.5),
        ("30 minutes", 0.5),
        ("1 day", 24.0),
    ],
)
def test_durations_normalize_units(raw, expected):
    assert parse_hours(raw).value == pytest.approx(expected)


def test_unit_mismatch_rejected_rather_than_scored():
    """A source switching hours->minutes must surface, not become a signal."""
    result = parse_hours("9000")
    assert result.value is None
    assert result.quality is Quality.OUT_OF_RANGE


def test_negative_metrics_rejected():
    assert parse_count("-5").quality is Quality.OUT_OF_RANGE


def test_garbage_is_unparseable_not_zero():
    result = parse_count("hello")
    assert result.value is None
    assert result.quality is Quality.UNPARSEABLE


def test_booleans_are_not_metrics():
    assert parse_count(True).value is None


def test_completeness_summary_reports_what_failed():
    summary = completeness(
        {
            "a": parse_count("5"),
            "b": parse_count("N/A"),
            "c": parse_hours("9999"),
        }
    )
    assert summary["usable_fields"] == ["a"]
    assert set(summary["missing_or_invalid"]) == {"b", "c"}
    assert summary["completeness_ratio"] == pytest.approx(1 / 3, abs=0.01)
