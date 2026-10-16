import json
from datetime import date, datetime, timedelta, timezone


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_defaults_without_any_configuration(hga, tmp_path):
    c = hga.load_config()
    assert c["review"]["provider"] == "local"
    assert c["github"]["project"] is None
    assert c["slack"] is None
    assert c["labels"] == {"in_progress": "in-progress", "in_review": "in-review"}
    assert c["sources"] == {"team": None, "user": None}
    assert c["knowledge_dir"] == str(tmp_path / "kb")


def test_user_overrides_team_overrides_defaults(hga, tmp_path):
    write(tmp_path / "kb" / "hga.config.json", {
        "language": "hu",
        "github": {"project": "Engineering", "fields": {"status": "Stage"}},
        "review": {"provider": "codex"},
    })
    write(tmp_path / "user.json", {"review": {"provider": "copilot"}, "knowledge_dir": "/ignored/by/env"})
    c = hga.load_config()
    assert c["language"] == "hu"
    assert c["github"]["project"] == "Engineering"
    # deep merge keeps the other default fields
    assert c["github"]["fields"] == {"status": "Stage", "iteration": "Iteration", "priority": "Priority", "effort": "Effort"}
    assert c["review"] == {"provider": "copilot", "ask_after_rounds": 5}
    assert c["sources"]["team"].endswith("hga.config.json")


def test_knowledge_dir_from_user_config(hga, tmp_path, monkeypatch):
    monkeypatch.delenv("HGA_KNOWLEDGE_DIR")
    write(tmp_path / "user.json", {"knowledge_dir": str(tmp_path / "elsewhere")})
    write(tmp_path / "elsewhere" / "hga.config.json", {"language": "de"})
    c = hga.load_config()
    assert c["knowledge_dir"] == str(tmp_path / "elsewhere")
    assert c["language"] == "de"


def test_configured_time_zone(hga, tmp_path):
    write(tmp_path / "kb" / "hga.config.json", {"timezone": "UTC"})
    assert datetime(2026, 1, 1, tzinfo=hga.local_tz()).utcoffset() == timedelta(0)


def test_canonical_status(hga):
    assert hga.canonical_status("In Progress") == "in_progress"
    assert hga.canonical_status("todo") == "todo"
    assert hga.canonical_status("Done") == "done"


def test_label_status(hga):
    assert hga.label_status(set()) == "Todo"
    assert hga.label_status({"in-progress"}) == "In Progress"
    assert hga.label_status({"in-progress", "in-review"}) == "Done"
    assert hga.label_status({"done"}) == "Todo"


def test_is_done_is_the_closed_state(hga):
    assert hga.is_done({"state": "CLOSED", "stateReason": "COMPLETED"})
    assert hga.is_done({"state": "CLOSED", "stateReason": "NOT_PLANNED"})
    # a label does not close an issue
    assert not hga.is_done({"state": "OPEN", "labels": {"nodes": [{"name": "done"}]}})


def test_print_deps_flags_prerequisites_closed_without_completion(hga, capsys):
    deps = {
        "blockedBy": {"nodes": [
            {"number": 1, "title": "a", "state": "CLOSED", "stateReason": "COMPLETED"},
            {"number": 2, "title": "b", "state": "CLOSED", "stateReason": "NOT_PLANNED"},
            {"number": 3, "title": "c", "state": "OPEN", "stateReason": None},
        ]},
        "blocking": {"nodes": []},
    }
    assert hga.print_deps("acme/web-app", 9, deps) == [3]
    out = capsys.readouterr().out
    assert "#1 [closed · COMPLETED] a" in out and "#3 [open] c" in out
    assert "CLOSED WITHOUT COMPLETION: #2" in out
    assert "OPEN PREREQUISITE: #3" in out


def issue(n, labels=(), blockers=(), board=None):
    return {
        "number": n,
        "title": f"t{n}",
        "labels": {"nodes": [{"name": x} for x in labels]},
        "blockedBy": {"nodes": [{"number": b, "state": "OPEN"} for b in blockers]},
        "projectItems": {"nodes": [] if board is None else [{"project": {"title": "Eng"}, "fieldValueByName": {"name": board}}]},
    }


def test_buckets_from_labels(hga):
    buckets, off = hga.bucket_issues([
        issue(1, ["ready-for-agent"]),
        issue(2, ["ready-for-agent"], blockers=[9]),
        issue(3, ["ready-for-human"]),
        issue(4, ["needs-info"]),
        issue(5, ["in-progress"]),
        issue(6, ["in-review"]),
        issue(7),
    ], None)
    assert [r["number"] for r in buckets["ready"]] == [1]
    assert buckets["blocked"] == [{"number": 2, "title": "t2", "blockers": [9]}]
    assert [r["number"] for r in buckets["needs_human"]] == [3]
    assert [r["number"] for r in buckets["needs_info"]] == [4]
    assert [r["number"] for r in buckets["in_progress"]] == [5]
    assert [r["number"] for r in buckets["in_review"]] == [6]
    assert [r["number"] for r in buckets["untriaged"]] == [7]
    assert off == 0


def test_buckets_from_board(hga):
    buckets, off = hga.bucket_issues([
        issue(1, ["ready-for-agent"], board="Todo"),
        issue(2, board="In Progress"),
        issue(3, board="Done"),
        issue(4),
        issue(5, board="Backlog"),
    ], "Eng")
    assert [r["number"] for r in buckets["ready"]] == [1]
    assert [r["number"] for r in buckets["in_progress"]] == [2]
    assert [r["number"] for r in buckets["in_review"]] == [3]
    assert off == 1


def test_current_iteration(hga):
    its = [
        {"id": "a", "title": "Sprint 1", "startDate": "2026-10-01", "duration": 14},
        {"id": "b", "title": "Sprint 2", "startDate": "2026-10-15", "duration": 14},
    ]
    assert hga.current_iteration(its, date(2026, 10, 14))["title"] == "Sprint 1"
    assert hga.current_iteration(its, date(2026, 10, 15))["title"] == "Sprint 2"
    assert hga.current_iteration(its, date(2026, 11, 30)) is None


def test_severity(hga):
    assert hga.severity_of("**<sub><sub>![P1 Badge](https://x)</sub></sub>  Fix it**") == "P1"
    assert hga.severity_of("**logic:** off by one") == "logic"
    assert hga.severity_of("Consider renaming this") == "—"
    assert hga.finding_title("**<sub>![P2 Badge](u)</sub> Title here**\nbody") == "Title here"


def test_fmt_tokens(hga):
    assert hga.fmt_tokens(950) == "950"
    assert hga.fmt_tokens(12_400) == "12k"
    assert hga.fmt_tokens(3_250_000) == "3.2M"


def test_count_tokens_deduplicates_and_respects_since(hga, tmp_path):
    t0 = datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc)
    rows = [
        {"type": "assistant", "timestamp": t0.isoformat(), "message": {"id": "m1", "model": "x", "usage": {"output_tokens": 10, "input_tokens": 5}}},
        {"type": "assistant", "timestamp": t0.isoformat(), "message": {"id": "m1", "model": "x", "usage": {"output_tokens": 10, "input_tokens": 5}}},
        {"type": "assistant", "timestamp": (t0 + timedelta(hours=1)).isoformat(), "message": {"id": "m2", "model": "x", "usage": {"output_tokens": 7}}},
        {"type": "user", "timestamp": t0.isoformat(), "message": {"content": "hi"}},
    ]
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    all_ = hga.count_tokens([f], None)["x"]
    assert all_["calls"] == 2 and all_["output_tokens"] == 17
    later = hga.count_tokens([f], t0 + timedelta(minutes=30))["x"]
    assert later["calls"] == 1 and later["output_tokens"] == 7


def test_breakdown_review_wait_and_pause(hga):
    t0 = datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc)
    m = lambda k: t0 + timedelta(minutes=k)  # noqa: E731
    entries = [
        (m(0), {"type": "user", "message": {"content": "go"}, "origin": {"kind": "human"}}),
        (m(1), {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "w1", "name": "Bash", "input": {"command": "python3 hga_issue.py review-wait a/b 1"}}]}}),
        (m(21), {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "w1"}]}}),
        (m(22), {"type": "assistant", "message": {"content": [{"type": "text", "text": "fixing"}]}}),
        (m(52), {"type": "user", "message": {"content": "back"}, "origin": {"kind": "human"}}),
    ]
    b = hga.breakdown(entries, m(0), m(60), 15)
    assert round(b["review_idle"] / 60) == 20
    assert b["review_runs"] == 1
    assert round(b["pause"] / 60) == 30
    assert b["pauses"][0][3] == "ended by a user message"
    assert round(b["active"] / 60) == 10


def test_scopes(hga):
    text = "  - Token scopes: 'gist', 'project', 'read:org', 'repo'"
    assert hga._scopes(text) == {"gist", "project", "read:org", "repo"}


def test_cli_config_and_now(hga, capsys):
    assert hga.main(["config"]) == 0
    assert json.loads(capsys.readouterr().out)["review"]["provider"] == "local"
    assert hga.main(["now"]) == 0
    assert datetime.fromisoformat(capsys.readouterr().out.strip()).tzinfo is not None


def test_review_commands_refuse_local_provider(hga, capsys):
    assert hga.main(["review-wait", "a/b", "1"]) == 4
    assert "local" in capsys.readouterr().out


def test_triage_labels_dropped_only_when_work_starts(hga):
    labels = {"bug", "ready-for-agent", "in-progress"}
    assert hga.triage_labels_to_drop("in_progress", labels) == ["ready-for-agent"]
    assert hga.triage_labels_to_drop("done", labels) == []
    assert hga.triage_labels_to_drop("todo", labels) == []


def test_doctor_before_init_is_not_a_failure(hga, capsys):
    # no user configuration and no knowledge base yet: /hga:init is the fix, not an error
    hga.main(["doctor"])
    out = capsys.readouterr().out
    assert "not set up yet — run /hga:init" in out
    assert "MISSING] knowledge base" not in out


def test_doctor_after_init_requires_the_knowledge_base(hga, tmp_path, capsys):
    write(tmp_path / "user.json", {"knowledge_dir": str(tmp_path / "kb")})
    hga.main(["doctor"])
    assert "MISSING] knowledge base" in capsys.readouterr().out
