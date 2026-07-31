# Phase 1 exit criterion: both entrypoints produce identical output on the same
# fixture (PRODUCTION_EVOLUTION_PROMPT.md 9, blocker B6).
#
# The criterion as originally written -- "byte-identical output from both
# entrypoints" -- is unachievable while a nondeterministic LLM produces the
# score. It is met here through the deterministic fakes required by 6.3: the
# CLI (`run_pipeline.run`) and the API path (`orchestrator_agent.run_orchestrator`)
# are run over the SAME CSV fixture with `FakeRiskScorer` and `FakeTrendEnricher`
# injected, and the stored evaluations are compared week by week.
#
# This is the test that makes the domain extraction worth having. Two copies of
# the pipeline that agree today are two copies that disagree after the next
# change, and the disagreement is silent -- the CLI and the web UI would simply
# tell a manager different things about the same person.
#
# No network is touched: every LLM seam is replaced before either entrypoint runs.

import csv
import json
import os

import pytest

from src.domain import FakeRiskScorer, FakeTrendEnricher

#: Keys that represent a DECISION about a person. These must match exactly.
DECISION_KEYS = ("score", "classification", "rationale", "healthy_streak", "signals")

FIXTURE_HEADER = [
    "employee_name",
    "tasks_completed",
    "avg_response_time_hours",
    "after_hours_logins",
    "weekly_hours",
]

#: Two employees, four weeks. Priya declines steadily (a pattern that must be
#: confirmed); Ade holds steady (must never be flagged).
FIXTURE_ROWS = {
    1: [
        ("Priya Raman", 20, 1.0, 1, 40),
        ("Ade Balogun", 15, 2.0, 2, 38),
    ],
    2: [
        ("Priya Raman", 14, 1.8, 1, 34),
        ("Ade Balogun", 15, 2.0, 2, 38),
    ],
    3: [
        ("Priya Raman", 9, 2.6, 1, 27),
        ("Ade Balogun", 16, 1.9, 2, 39),
    ],
    4: [
        ("Priya Raman", 7, 3.1, 1, 25),
        ("Ade Balogun", 15, 2.1, 2, 38),
    ],
}


def _write_fixture(weekly_dir, weeks=FIXTURE_ROWS):
    os.makedirs(weekly_dir, exist_ok=True)
    for week, rows in weeks.items():
        with open(
            os.path.join(weekly_dir, f"week{week}.csv"),
            "w",
            encoding="utf-8",
            newline="",
        ) as fh:
            writer = csv.DictWriter(fh, fieldnames=FIXTURE_HEADER)
            writer.writeheader()
            for name, tasks, response, after_hours, hours in rows:
                writer.writerow(
                    {
                        "employee_name": name,
                        "tasks_completed": tasks,
                        "avg_response_time_hours": response,
                        "after_hours_logins": after_hours,
                        "weekly_hours": hours,
                    }
                )


def _read_evaluations(memory_dir) -> dict[str, dict]:
    """Every stored evaluation, keyed by filename, decision fields only."""
    out: dict[str, dict] = {}
    if not os.path.isdir(memory_dir):
        return out
    for name in sorted(os.listdir(memory_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(memory_dir, name), encoding="utf-8") as fh:
            record = json.load(fh)
        out[name] = {k: record.get(k) for k in DECISION_KEYS}
    return out


@pytest.fixture
def deterministic(monkeypatch, tmp_path):
    """Replace every nondeterministic seam. Nothing here reaches a network."""
    from src.data_layer import identity

    monkeypatch.setattr(identity, "IDENTITY_MAP_PATH", str(tmp_path / "idmap.json"))
    monkeypatch.setenv("IDENTITY_SALT", "parity-fixed-salt")
    identity.reset_resolver()

    import src.manager_briefing_agent as briefing_mod
    import src.orchestrator_agent as orch_mod
    import src.risk_scorer_agent as risk_mod
    import src.trend_detector_agent as trend_mod

    monkeypatch.setattr(risk_mod, "DEFAULT_SCORER", FakeRiskScorer())
    monkeypatch.setattr(trend_mod, "DEFAULT_ENRICHER", FakeTrendEnricher())

    def _fake_briefing(first_name, signals, risk_data, memory_dir=None):
        return f"Check in with {first_name}. Supportive, non-disciplinary."

    # The name is bound into the orchestrator's namespace at import time, so the
    # definition module alone is not enough.
    monkeypatch.setattr(briefing_mod, "generate_briefing", _fake_briefing)
    monkeypatch.setattr(orch_mod, "generate_briefing", _fake_briefing)

    # run_orchestrator ends by asking the LLM for a cohort summary. Left alone it
    # builds a real GenAI client and attempts a request -- which fails without a
    # key, but only after a timeout, and 6.3 says CI must never call a real LLM
    # at all. Stubbed so the assertion "no network is touched" is literally true.
    def _no_llm(*args, **kwargs):
        raise AssertionError(
            "a parity run attempted a live LLM call -- every seam must be faked"
        )

    monkeypatch.setattr(orch_mod, "run_agent_sync", _no_llm)
    monkeypatch.setattr(briefing_mod, "run_agent_sync", _no_llm)
    monkeypatch.setattr(risk_mod, "run_agent_sync", _no_llm)
    monkeypatch.setattr(trend_mod, "run_agent_sync", _no_llm)

    yield

    identity.reset_resolver()


def _run_cli(tmp_path, monkeypatch, weeks=FIXTURE_ROWS) -> dict[str, dict]:
    """Drive run_pipeline.run() with cwd-relative paths under tmp_path."""
    root = tmp_path / "cli"
    _write_fixture(root / "data" / "weekly", weeks)
    os.makedirs(root / "data" / "memory", exist_ok=True)
    monkeypatch.chdir(root)

    import run_pipeline

    run_pipeline.run()
    return _read_evaluations(root / "data" / "memory")


def _run_api(tmp_path, weeks=FIXTURE_ROWS) -> dict[str, dict]:
    """Drive orchestrator_agent.run_orchestrator() with explicit paths."""
    root = tmp_path / "api"
    _write_fixture(root / "data" / "weekly", weeks)
    memory_dir = root / "data" / "memory"
    os.makedirs(memory_dir, exist_ok=True)

    from src.orchestrator_agent import run_orchestrator

    run_orchestrator(
        weekly_folder=str(root / "data" / "weekly"),
        memory_folder=str(memory_dir),
    )
    return _read_evaluations(memory_dir)


def test_both_entrypoints_reach_the_same_decisions(
    tmp_path, monkeypatch, deterministic
):
    api = _run_api(tmp_path)
    cli = _run_cli(tmp_path, monkeypatch)

    assert cli, "the CLI produced no evaluations -- the fixture never ran"
    assert set(cli) == set(api), (
        f"different weeks were evaluated:\n  cli={sorted(cli)}\n  api={sorted(api)}"
    )

    differences = {
        name: {"cli": cli[name], "api": api[name]}
        for name in sorted(cli)
        if cli[name] != api[name]
    }
    assert not differences, (
        "the CLI and API paths disagree about the same person -- blocker B6 has "
        f"returned:\n{json.dumps(differences, indent=2, default=str)}"
    )


def test_the_fixture_actually_exercises_detection(tmp_path, monkeypatch, deterministic):
    """A parity test over a fixture that flags nobody proves nothing."""
    cli = _run_cli(tmp_path, monkeypatch)

    priya = [v for k, v in cli.items() if k.startswith("priya")]
    ade = [v for k, v in cli.items() if k.startswith("ade")]
    assert priya and ade, f"expected both employees, got {sorted(cli)}"

    assert any(v["signals"] for v in priya), (
        "the declining trajectory produced no confirmed signal"
    )
    assert max(v["score"] for v in priya) > min(v["score"] for v in priya), (
        "risk never moved across four weeks of steady decline"
    )
    assert all(v["classification"] == "Healthy" for v in ade), (
        "a steady employee was flagged -- this is the false positive that "
        "matters most, because the person has done nothing wrong"
    )


def test_runs_are_reproducible(tmp_path, monkeypatch, deterministic):
    """Same fixture, same seed, same output -- twice."""
    first = _run_api(tmp_path / "a")
    second = _run_api(tmp_path / "b")
    assert first == second


def test_a_missing_week_cannot_change_a_risk_decision(
    tmp_path, monkeypatch, deterministic
):
    """CONTEXT.md rule 3, proven across both entrypoints.

    The API path appends a MISSING_DATA_GAP marker that the CLI path does not --
    a real, known difference in what is REPORTED. It must remain a difference in
    reporting only: the marker is carried as wellbeing-only, so it cannot move a
    score. If that ever changes, an absent CSV row starts making people look
    disengaged, which is the exact failure this rule exists to prevent.
    """
    gapped = {w: rows for w, rows in FIXTURE_ROWS.items() if w != 3}

    api = _run_api(tmp_path, gapped)
    cli = _run_cli(tmp_path, monkeypatch, gapped)

    assert set(cli) == set(api)
    for name in sorted(cli):
        assert cli[name]["score"] == api[name]["score"], name
        assert cli[name]["classification"] == api[name]["classification"], name

    api_signal_names = {
        s.get("signal") or s.get("signal_name")
        for record in api.values()
        for s in (record["signals"] or [])
    }
    assert "MISSING_DATA_GAP" in api_signal_names, (
        "the API path stopped reporting the data gap -- a gap must be visible to "
        "the manager, not silently absorbed"
    )
