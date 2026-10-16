import json
from datetime import date, datetime, timedelta, timezone

from conftest import load


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


def test_breakdown_counts_the_gap_before_the_first_message(hga):
    t0 = datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc)
    m = lambda k: t0 + timedelta(minutes=k)  # noqa: E731
    entries = [(m(30), {"type": "user", "message": {"content": "back"}, "origin": {"kind": "human"}})]
    b = hga.breakdown(entries, m(0), m(40), 15)
    assert round(b["pause"] / 60) == 30 and round(b["active"] / 60) == 10
    assert b["pauses"][0][3] == "ended by a user message"
    # a window without any message is one pause
    assert round(hga.breakdown([], m(0), m(40), 15)["active"]) == 0


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


def test_config_problems_defaults_are_clean(hga):
    assert hga.config_problems(hga.load_config()) == []


def test_config_problems_catch_bad_fields(hga, tmp_path):
    write(tmp_path / "kb" / "hga.config.json", {
        "timezone": "",
        "github": {"fields": {"status": ""}, "statuses": {"done": None}},
        "labels": {"in_review": " "},
        "review": {"provider": "codex", "ask_after_rounds": 0},
        "parallel": {"max_per_repo": True},
    })
    text = "\n".join(hga.config_problems(hga.load_config()))
    assert "timezone must be" in text
    assert "github.fields.status" in text
    assert "github.statuses.done" in text and "github.statuses.todo" not in text
    assert "labels.in_review" in text and "labels.in_progress" not in text
    assert "review.ask_after_rounds" in text
    assert "parallel.max_per_repo" in text  # a boolean is not a number
    assert "review.provider" not in text


def test_cli_config_warns_on_problems_but_prints(hga, tmp_path, capsys):
    write(tmp_path / "kb" / "hga.config.json", {"review": {"ask_after_rounds": "5"}})
    assert hga.main(["config"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["review"]["ask_after_rounds"] == "5"
    assert "warning: configuration: review.ask_after_rounds" in captured.err


# --- metrics record ----------------------------------------------------------------------------

T0 = datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def ms(minutes):
    return int(at(minutes).timestamp() * 1000)


def reply(minutes, mid, model, out, **extra):
    return {"type": "assistant", "timestamp": at(minutes).isoformat(),
            "message": {"id": mid, "model": model, "usage": {"output_tokens": out, "input_tokens": 1}, **extra}}


def transcripts(tmp_path, hga, monkeypatch, sid="sess-1"):
    """A session with a subagent: replies in every section, one before the start, one after the end, and a
    20-minute review-wait during the review."""
    projects = tmp_path / "projects"
    monkeypatch.setattr(hga, "PROJECTS_DIR", projects)
    main = [
        {"type": "user", "timestamp": at(0).isoformat(), "message": {"content": "take #18"}, "origin": {"kind": "human"}},
        reply(-60, "m0", "claude-opus-5-5", 1000),
        reply(1, "m1", "claude-opus-5-5", 10),
        reply(20, "m2", "claude-opus-5-5", 100),
        reply(51, "m3", "claude-opus-5-5", 5, content=[
            {"type": "tool_use", "id": "w1", "name": "Bash", "input": {"command": "hga_issue.py review-wait acme/web-app 31"}}]),
        {"type": "user", "timestamp": at(71).isoformat(), "message": {"content": [{"type": "tool_result", "tool_use_id": "w1"}]}},
        reply(90, "m4", "claude-opus-5-5", 7),
        reply(120, "m5", "claude-opus-5-5", 3000),
    ]
    sub = [reply(60, "s1", "claude-sonnet-5-5", 50), reply(60, "s1", "claude-sonnet-5-5", 50)]
    p = projects / "-work-web-app" / f"{sid}.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text("\n".join(json.dumps(r) for r in main) + "\n", encoding="utf-8")
    s = projects / "-work-web-app" / sid / "subagents" / "agent-a.jsonl"
    s.parent.mkdir(parents=True)
    s.write_text("\n".join(json.dumps(r) for r in sub) + "\n", encoding="utf-8")


def step(state, start=None, end=None, evidence=""):
    out = {"state": state, "evidence": evidence}
    if start is not None:
        out["startedAt"] = ms(start)
    if end is not None:
        out["endedAt"] = ms(end)
    return out


def state_file(tmp_path, hga, monkeypatch, start=0, **over):
    monkeypatch.setattr(hga, "ISSUE_DIR", tmp_path / "issue")
    steps = [None] * 13
    steps[0] = step("done", 0, 5)
    steps[5] = step("done", 10, 40)
    steps[6] = step("skipped", None, 40, "no browser")  # skipped without an in_progress: no start
    steps[7] = step("done", 45, 50)
    steps[8] = step("done", 50, 80)
    steps[9] = step("done", 85, 86)
    steps[12] = step("done", 100, 105)
    data = {
        "issue": "acme/web-app#18", "verb": "fix", "startedAt": ms(start), "steps": steps,
        "updatedAt": ms(105), "session": "sess-1",
        "fiveHour": {"start": {"at": ms(0), "percentUsed": 21.5}, "end": {"at": ms(105), "percentUsed": 48.25}},
        **over,
    }
    write(tmp_path / "issue" / "acme-web-app-18.json", data)
    return data


def record(hga, capsys, *args):
    assert hga.main(["metrics-record", "acme/web-app", "18", *args]) == 0
    path = capsys.readouterr().out.strip()
    return path, json.loads(open(path, encoding="utf-8").read())


def test_tokens_until_is_exclusive(hga, tmp_path, monkeypatch):
    transcripts(tmp_path, hga, monkeypatch)
    files = sorted((tmp_path / "projects").rglob("*.jsonl"))
    window = hga.count_tokens(files, at(0), at(60))
    assert window["claude-opus-5-5"]["output_tokens"] == 10 + 100 + 5
    assert "claude-sonnet-5-5" not in window  # the subagent's reply is at 60: not before the end
    assert hga.count_tokens(files, None, at(0))["claude-opus-5-5"]["output_tokens"] == 1000


def test_cli_tokens_since_until(hga, tmp_path, monkeypatch, capsys):
    write(tmp_path / "kb" / "hga.config.json", {"timezone": "UTC"})
    transcripts(tmp_path, hga, monkeypatch)
    assert hga.main(["tokens", "--since", at(0).isoformat(), "--until", at(61).isoformat(), "--session", "sess-1"]) == 0
    out = capsys.readouterr().out
    assert "since 10-13 08:00 until 10-13 09:01" in out
    assert "claude-sonnet-5-5: 1 calls" in out
    assert "Report line: 4 API calls · output 165" in out


def test_metrics_record(hga, tmp_path, monkeypatch, capsys):
    write(tmp_path / "kb" / "hga.config.json", {"timezone": "UTC"})
    transcripts(tmp_path, hga, monkeypatch)
    state_file(tmp_path, hga, monkeypatch)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    path, rec = record(hga, capsys, "--difficulty", "medium", "--review-rounds", "2")
    # one file per run, named by the run's start (UTC), under metrics/<owner>/<repo>/
    assert path == str(tmp_path / "kb" / "metrics" / "acme" / "web-app" / "18-20261013T080000Z.json")
    assert rec["schema"] == 1
    assert (rec["repo"], rec["issue"], rec["verb"]) == ("acme/web-app", 18, "fix")
    # the end is step 12's end; the session comes from the state file
    assert (rec["started_at"], rec["ended_at"]) == ("2026-10-13T08:00:00+00:00", "2026-10-13T09:45:00+00:00")
    assert rec["finished"] is True
    assert rec["sessions"] == ["sess-1"]
    assert rec["transcripts"] == {"main": 1, "subagents": 1}
    assert (rec["difficulty"], rec["review_rounds"]) == ("medium", 2)

    assert rec["elapsed"]["wall_s"] == 105 * 60
    assert rec["elapsed"]["review_wait_s"] == 20 * 60
    assert rec["elapsed"]["review_wait_runs"] == 1
    # only the replies within the run: not the one before the start, not the one after the end
    assert rec["tokens"] == {"calls": 5, "output_tokens": 172, "input_tokens": 5,
                             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    assert set(rec["models"]) == {"claude-opus-5-5", "claude-sonnet-5-5"}
    assert rec["models"]["claude-sonnet-5-5"]["calls"] == 1

    # sections: contiguous windows from each section's first step time; their tokens add up to the total
    secs = {s["title"]: s for s in rec["sections"]}
    assert [s["title"] for s in rec["sections"]] == ["Prepare", "Build", "Review", "Finish"]
    assert (secs["Build"]["from"], secs["Build"]["to"]) == ("2026-10-13T08:10:00+00:00", "2026-10-13T08:45:00+00:00")
    assert secs["Finish"]["steps"] == [9, 12]
    assert [s["tokens"]["output_tokens"] for s in rec["sections"]] == [10, 100, 55, 7]
    assert sum(s["tokens"]["calls"] for s in rec["sections"]) == rec["tokens"]["calls"]
    assert sum(s["elapsed"]["wall_s"] for s in rec["sections"]) == rec["elapsed"]["wall_s"]
    assert secs["Review"]["elapsed"]["review_wait_s"] == 20 * 60
    assert set(secs["Review"]["models"]) == {"claude-opus-5-5", "claude-sonnet-5-5"}

    assert rec["steps"][6] == {"step": 6, "name": "Live test", "state": "skipped", "started_at": None,
                               "ended_at": "2026-10-13T08:40:00+00:00"}
    assert rec["steps"][3]["state"] is None
    assert rec["five_hour"] == {
        "scope": "account",
        "start": {"at": "2026-10-13T08:00:00+00:00", "percent_used": 21.5},
        "end": {"at": "2026-10-13T09:45:00+00:00", "percent_used": 48.25},
    }

    # the record validates in the knowledge base, without warnings
    validate = load("validate_kb", "knowledge/scripts/validate_kb.py")
    assert validate.check(tmp_path / "kb", date(2026, 10, 15)) == ([], [])


def test_metrics_record_reruns_keep_apart(hga, tmp_path, monkeypatch, capsys):
    (tmp_path / "kb").mkdir()
    transcripts(tmp_path, hga, monkeypatch)
    state_file(tmp_path, hga, monkeypatch)
    first, _ = record(hga, capsys)
    again, _ = record(hga, capsys)
    assert again == first  # the same run again: the same file, rewritten
    state_file(tmp_path, hga, monkeypatch, start=200)  # a later run of the same issue
    later, _ = record(hga, capsys, "--until", at(260).isoformat())
    assert later != first
    assert len(list((tmp_path / "kb" / "metrics").rglob("*.json"))) == 2


def test_metrics_record_from_an_older_state_file(hga, tmp_path, monkeypatch, capsys):
    # no step times, no five-hour snapshots, no transcript: wall clock only, still a valid record
    (tmp_path / "kb").mkdir()
    monkeypatch.setattr(hga, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(hga, "ISSUE_DIR", tmp_path / "issue")
    write(tmp_path / "issue" / "acme-web-app-18.json", {
        "issue": "acme/web-app#18", "verb": "fix", "startedAt": ms(0), "updatedAt": ms(30), "session": "gone",
        "steps": [{"state": "done", "evidence": "ok"}] + [None] * 12,
    })
    assert hga.main(["metrics-record", "acme/web-app", "18", "--until", at(30).isoformat()]) == 0
    captured = capsys.readouterr()
    assert "no transcript" in captured.err
    rec = json.loads(open(captured.out.strip(), encoding="utf-8").read())
    assert rec["finished"] is False
    assert rec["elapsed"]["wall_s"] == 30 * 60 and rec["elapsed"]["active_s"] is None
    assert rec["tokens"] is None and rec["models"] == {}
    # without step times the whole run falls into the first section
    assert [s["elapsed"]["wall_s"] for s in rec["sections"]] == [30 * 60, 0, 0, 0]
    assert rec["five_hour"] == {"scope": "account", "start": None, "end": None}


def test_metrics_record_needs_the_state_file_and_the_knowledge_base(hga, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hga, "ISSUE_DIR", tmp_path / "issue")
    assert hga.main(["metrics-record", "acme/web-app", "18"]) == 4
    assert "no issue pane state file" in capsys.readouterr().err
    state_file(tmp_path, hga, monkeypatch)
    assert hga.main(["metrics-record", "acme/web-app", "18"]) == 4
    assert "run /hga:init" in capsys.readouterr().err
    assert not (tmp_path / "kb").exists()


def test_section_bounds_clamp_out_of_order_steps(hga):
    steps = [None] * 13
    steps[5] = step("done", 50, 60)
    steps[7] = step("done", 30, 40)  # reported before the build started
    bounds = hga.section_bounds(steps, at(0), at(100))
    assert bounds == [(at(0), at(30)), (at(30), at(30)), (at(30), at(100)), (at(100), at(100))]
