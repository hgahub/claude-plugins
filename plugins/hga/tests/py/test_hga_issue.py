import json
from datetime import date, datetime, timedelta, timezone

import pytest
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


def issue(n, labels=(), blockers=(), board=None, assignees=()):
    return {
        "number": n,
        "title": f"t{n}",
        "assignees": {"nodes": [{"login": x} for x in assignees]},
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
    assert buckets["blocked"] == [{"number": 2, "title": "t2", "blockers": [9], "assignees": []}]
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


def test_next_lists_assignees(hga, monkeypatch, capsys):
    # the triage's second claim signal: an assigned ready issue shows who has it (older JSON had no field)
    old = issue(2, ["ready-for-agent"])
    del old["assignees"]
    page = {"pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [issue(1, ["ready-for-agent"], assignees=["bob"]), old]}
    monkeypatch.setattr(hga, "gql", lambda q, **v: {"repository": {"issues": page}})
    assert hga.main(["next", "acme/web-app"]) == 0
    out = capsys.readouterr().out
    assert "#1 t1  [assigned: bob]" in out
    assert "#2 t2\n" in out


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


HEAD = "abc1234" + "0" * 33
COPILOT = {"login": "copilot-pull-request-reviewer[bot]", "type": "Bot"}


def fake_review_api(hga, monkeypatch, reviews, inline=()):
    """review-wait against canned GitHub answers (Copilot)."""
    def gh(*args):
        if args[:2] == ("pr", "view"):
            return json.dumps({"headRefOid": HEAD})
        path = args[1]
        if path.endswith("/reviews"):
            return json.dumps(reviews)
        if path.startswith("repos/a/b/pulls/") and path.endswith("/comments"):
            return json.dumps(list(inline))
        return "[]"
    monkeypatch.setattr(hga, "gh", gh)
    monkeypatch.setattr(hga.time, "sleep", lambda s: None)


def review(state, commit=HEAD, user=COPILOT, rid=7, body=""):
    return {"id": rid, "state": state, "commit_id": commit, "user": user, "body": body, "html_url": "u"}


def wait(hga, timeout="0.001"):
    return hga.main(["review-wait", "a/b", "1", "--provider", "copilot", "--timeout-min", timeout, "--interval", "0"])


def test_review_wait_clean_comment_review(hga, monkeypatch, capsys):
    fake_review_api(hga, monkeypatch, [review("COMMENTED")])
    assert wait(hga, "1") == 0
    assert "no significant findings" in capsys.readouterr().out


def test_review_wait_changes_requested_without_inline_is_a_finding(hga, monkeypatch, capsys):
    fake_review_api(hga, monkeypatch, [review("CHANGES_REQUESTED", body="Missing null check in export.")])
    assert wait(hga, "1") == 1
    out = capsys.readouterr().out
    assert "changes requested" in out and "Missing null check" in out and "👍" not in out


def test_review_wait_ignores_dismissed_and_other_commits(hga, monkeypatch, capsys):
    other = "abc1234" + "f" * 33  # same 7-character prefix, another commit
    fake_review_api(hga, monkeypatch, [review("DISMISSED"), review("COMMENTED", commit=other, rid=8)])
    assert wait(hga) == 2
    assert "timeout" in capsys.readouterr().out


def test_review_wait_ignores_people_named_like_the_bot(hga, monkeypatch, capsys):
    fake_review_api(hga, monkeypatch, [review("COMMENTED", user={"login": "someone-copilot-unrelated", "type": "User"})])
    assert wait(hga) == 2


def test_review_wait_lists_inline_findings(hga, monkeypatch, capsys):
    fake_review_api(hga, monkeypatch, [review("COMMENTED")],
                    inline=[{"id": 3, "pull_request_review_id": 7, "path": "x.py", "line": 4, "body": "**high** Bug"}])
    assert wait(hga, "1") == 1
    assert "1 inline finding(s)" in capsys.readouterr().out


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


# --- metrics aggregate -------------------------------------------------------------------------


def tok(inp, out, cw=0, cr=0, calls=1):
    return {"calls": calls, "output_tokens": out, "input_tokens": inp,
            "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def a_record(repo="acme/web-app", issue=7, started="2026-10-01T09:00:00+02:00", **over):
    opus = tok(1_000_000, 100_000, 200_000, 2_000_000, calls=40)
    sonnet = tok(500_000, 50_000, calls=10)
    rec = {
        "schema": 1, "repo": repo, "issue": issue, "verb": "fix", "started_at": started,
        "ended_at": "2026-10-01T10:30:00+02:00", "finished": True, "difficulty": "hard", "review_rounds": 3,
        "elapsed": {"wall_s": 5400, "active_s": 4000, "review_wait_s": 600, "review_wait_runs": 1, "pause_s": 800,
                    "pauses": []},
        "tokens": tok(1_500_000, 150_000, 200_000, 2_000_000, calls=50),
        "models": {"claude-opus-5-5": opus, "claude-sonnet-5-5": sonnet},
        "sections": [
            {"title": "Prepare", "steps": [0, 4], "elapsed": {"wall_s": 600, "active_s": 500},
             "tokens": tok(0, 0, calls=0), "models": {}},
            {"title": "Build", "steps": [5, 6], "elapsed": {"wall_s": 3000, "active_s": 2500},
             "tokens": opus, "models": {"claude-opus-5-5": opus}},
            {"title": "Review", "steps": [7, 8], "elapsed": {"wall_s": 1500, "active_s": 800, "review_wait_s": 600},
             "tokens": sonnet, "models": {"claude-sonnet-5-5": sonnet}},
            {"title": "Finish", "steps": [9, 12], "elapsed": {"wall_s": 300, "active_s": 200},
             "tokens": tok(0, 0, calls=0), "models": {}},
        ],
        "steps": [],
        "five_hour": {"scope": "account", "start": {"at": started, "percent_used": 10},
                      "end": {"at": "2026-10-01T10:30:00+02:00", "percent_used": 35.5}},
    }
    rec.update(over)
    return rec


def metrics_kb(tmp_path):
    m = tmp_path / "kb" / "metrics"
    write(m / "acme" / "web-app" / "7-20261001T070000Z.json", a_record())
    write(m / "acme" / "web-app" / "9-20261005T070000Z.json",
          a_record(issue=9, started="2026-10-05T09:00:00+02:00", tokens=None, models={}, difficulty=None))
    write(m / "acme" / "api" / "3-20260920T070000Z.json", a_record(repo="acme/api", issue=3,
                                                                     started="2026-09-20T09:00:00+02:00"))
    write(m / "acme" / "api" / "4-20260921T070000Z.json", {"schema": 2, "repo": "acme/api"})
    (m / "acme" / "api" / "5-20260922T070000Z.json").write_text("{not json", encoding="utf-8")
    write(tmp_path / "kb" / "metrics" / "README.md", {})  # not a record: ignored by name
    return m


def metrics_out(hga, capsys, *args):
    assert hga.main(["metrics", *args]) == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


def test_api_cost_from_the_price_table(hga):
    # longest prefix wins: Opus 5.5 is not priced as Opus 5, dated or suffixed ids still match
    assert hga.api_price("claude-opus-5-5") == (4.0, 20.0, 5.0, 0.2)
    assert hga.api_price("claude-opus-5") == (5.0, 25.0, 6.25, 0.5)
    assert hga.api_price("claude-sonnet-4-5-20250929") == (3.0, 15.0, 3.75, 0.3)
    assert hga.api_price("<synthetic>") is None
    # 1M input × $4 + 0.1M output × $20 + 0.2M cache write × $5 + 2M cache read × $0.20
    assert hga.api_cost("claude-opus-5-5", tok(1_000_000, 100_000, 200_000, 2_000_000)) == pytest.approx(7.4)
    assert hga.api_cost("unknown-model", tok(1, 1)) is None


def test_metrics_rows_per_run_section_and_model(hga, tmp_path, capsys):
    metrics_kb(tmp_path)
    rows, err = metrics_out(hga, capsys, "--repo", "ACME/Web-App", "--cost")
    assert {r["repo"] for r in rows} == {"acme/web-app"}
    runs = [r for r in rows if r["kind"] == "run"]
    assert [r["issue"] for r in runs] == [7, 9]  # by start
    run = runs[0]
    assert run["run"] == "acme/web-app/7-20261001T070000Z"
    assert (run["date"], run["difficulty"], run["review_rounds"], run["finished"]) == ("2026-10-01", "hard", 3, True)
    assert (run["wall_s"], run["active_s"], run["review_wait_s"], run["pause_s"]) == (5400, 4000, 600, 800)
    assert run["total_tokens"] == 1_500_000 + 150_000 + 200_000 + 2_000_000
    assert (run["five_hour_start_pct"], run["five_hour_end_pct"]) == (10, 35.5)
    assert run["section"] is None and run["model"] is None
    # the run's estimate is the sum of its models': Opus 7.4 + Sonnet (0.5 × 2 + 0.05 × 10) 1.5
    assert run["api_cost_usd_est"] == 8.9

    secs = [r for r in rows if r["kind"] == "section" and r["issue"] == 7]
    assert [(s["section"], s["section_index"]) for s in secs] == [("Prepare", 0), ("Build", 1), ("Review", 2), ("Finish", 3)]
    assert [s["wall_s"] for s in secs] == [600, 3000, 1500, 300]
    assert [s["api_cost_usd_est"] for s in secs] == [None, 7.4, 1.5, None]
    assert secs[2]["review_wait_s"] == 600 and secs[0]["review_wait_s"] is None
    assert secs[0]["five_hour_start_pct"] is None  # account context only on the run row

    models = [r for r in rows if r["kind"] == "model" and r["issue"] == 7]
    assert [(m["section"], m["model"], m["api_cost_usd_est"]) for m in models] == [
        ("Build", "claude-opus-5-5", 7.4), ("Review", "claude-sonnet-5-5", 1.5)]
    assert models[0]["wall_s"] is None and models[0]["calls"] == 40

    # a run without a transcript: no tokens, no estimate, still a row
    no_tok = runs[1]
    assert no_tok["total_tokens"] is None and no_tok["api_cost_usd_est"] is None
    assert "API list prices" in err and "not what a Claude subscription costs" in err


def test_metrics_skips_unknown_schemas_and_bad_files(hga, tmp_path, capsys):
    metrics_kb(tmp_path)
    rows, err = metrics_out(hga, capsys)
    assert {r["run"] for r in rows if r["kind"] == "run"} == {
        "acme/api/3-20260920T070000Z", "acme/web-app/7-20261001T070000Z", "acme/web-app/9-20261005T070000Z"}
    assert "skipped 1 record(s) with an unknown schema (2)" in err
    assert "5-20260922T070000Z.json" in err
    assert "api_cost_usd_est" not in rows[0]  # the estimate only on request
    assert "API list prices" not in err


def test_metrics_period_filter(hga, tmp_path, capsys):
    metrics_kb(tmp_path)
    rows, _ = metrics_out(hga, capsys, "--since", "2026-10-01", "--until", "2026-10-01")
    assert {r["run"] for r in rows} == {"acme/web-app/7-20261001T070000Z"}
    rows, _ = metrics_out(hga, capsys, "--until", "2026-09-30")
    assert {r["repo"] for r in rows} == {"acme/api"}
    with pytest.raises(SystemExit, match="YYYY-MM-DD"):
        hga.main(["metrics", "--since", "1 October"])


def test_metrics_csv(hga, tmp_path, capsys):
    metrics_kb(tmp_path)
    assert hga.main(["metrics", "--format", "csv", "--cost", "--repo", "acme/api"]) == 0
    lines = capsys.readouterr().out.splitlines()
    header = lines[0].split(",")
    assert header[:3] == ["kind", "run", "repo"] and header[-1] == "api_cost_usd_est"
    first = dict(zip(header, lines[1].split(",")))
    assert (first["kind"], first["finished"], first["section"], first["api_cost_usd_est"]) == ("run", "true", "", "8.9")
    assert len(lines) == 1 + 1 + 4 + 2  # header, run, sections, section × model


def test_metrics_empty_and_without_knowledge_base(hga, tmp_path, capsys):
    assert hga.main(["metrics"]) == 4
    assert "run /hga:init" in capsys.readouterr().err
    (tmp_path / "kb").mkdir()
    assert metrics_out(hga, capsys)[0] == []
    assert hga.main(["metrics", "--format", "csv"]) == 0
    assert capsys.readouterr().out.startswith("kind,run,repo,")


def test_metrics_reads_what_metrics_record_writes(hga, tmp_path, monkeypatch, capsys):
    write(tmp_path / "kb" / "hga.config.json", {"timezone": "UTC"})
    transcripts(tmp_path, hga, monkeypatch)
    state_file(tmp_path, hga, monkeypatch)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    record(hga, capsys, "--difficulty", "medium", "--review-rounds", "2")
    rows, _ = metrics_out(hga, capsys, "--cost")
    run = rows[0]
    assert (run["kind"], run["run"], run["wall_s"], run["calls"]) == ("run", "acme/web-app/18-20261013T080000Z", 6300, 5)
    sections = [r for r in rows if r["kind"] == "section"]
    models = [r for r in rows if r["kind"] == "model"]
    assert sum(s["calls"] for s in sections) == sum(m["calls"] for m in models) == run["calls"]
    assert sum(s["api_cost_usd_est"] or 0 for s in sections) == pytest.approx(run["api_cost_usd_est"])
    assert sum(m["api_cost_usd_est"] for m in models) == pytest.approx(run["api_cost_usd_est"])


# --- claim check ---------------------------------------------------------------------------------


def comment(cid, minutes, body, user="bot-account"):
    return {"id": cid, "created_at": at(minutes).isoformat().replace("+00:00", "Z"), "body": body, "user": user,
            "url": f"https://github.com/acme/web-app/issues/18#issuecomment-{cid}"}


def claims(hga, *comments):
    return hga.parse_claims(list(comments))


def check(hga, *, status="Todo", assignees=(), me="bot-account", cl=(), tag="aaaa1111", now=0, verb="fix",
          since=None):
    return hga.claim_check(status=status, assignees=list(assignees), me=me, claims=list(cl), tag=tag, now=at(now),
                           verb=verb, since=None if since is None else at(since))


def test_parse_claims_reads_the_session_tag_and_skips_withdrawn(hga):
    cl = claims(hga,
                comment(3, 5, "Claimed · fix · agent · session bbbb2222\nmore"),
                comment(2, 5, "Claimed · fix · agent · session aaaa1111-and-the-rest"),
                comment(1, 1, "Withdrawn · fix · agent · session cccc3333 — earlier claim: …"),
                comment(4, 9, "a reply that mentions Claimed · fix"),
                comment(5, 10, "claimed · implement · a person"))
    # oldest first; the same second is ordered by GitHub's comment id
    assert [(c["id"], c["session"]) for c in cl] == [(2, "aaaa1111"), (3, "bbbb2222"), (5, None)]


def test_claim_check_free(hga):
    code, lines = check(hga, assignees=["bot-account"], cl=claims(
        hga, comment(1, -60 * 30, "Claimed · fix · old run · session dddd4444")))
    # assigned to this very account (parallel sessions share it), and a claim older than a day: still free
    assert code == 0
    assert lines[-1].startswith("Verdict: free")
    assert "Session: aaaa1111" in lines
    assert f"Read back from: {at(-1).timestamp():.0f} " in "\n".join(lines)


@pytest.mark.parametrize("kw, reason", [
    ({"status": "In Progress"}, "Status In Progress"),
    ({"status": "in progress"}, "Status in progress"),
    ({"status": "Done"}, "only verify / re-verify"),
    ({"assignees": ["alice", "bot-account"]}, "assigned to alice"),
    ({"cl": "recent"}, "claimed by bot-account"),
])
def test_claim_check_taken(hga, kw, reason):
    if kw.get("cl") == "recent":  # yesterday evening, outside a Slack read of today: still taken
        kw["cl"] = claims(hga, comment(1, -60 * 14, "Claimed · fix · agent · session bbbb2222"))
    code, lines = check(hga, **kw)
    assert code == 5
    assert lines[-1].startswith("Verdict: taken") and reason in lines[-1]


def test_claim_check_done_is_free_for_a_verification(hga):
    assert check(hga, status="Done", verb="re-verify")[0] == 0


def test_claim_check_configured_status_names(hga, tmp_path):
    write(tmp_path / "kb" / "hga.config.json", {"github": {"statuses": {"in_progress": "Doing", "done": "Shipped"}}})
    hga.CFG = {}
    code, lines = check(hga, status="Doing")
    assert code == 5 and "Status Doing" in lines[-1]
    assert check(hga, status="Shipped")[0] == 5
    assert check(hga, status="Shipped", verb="verify")[0] == 0
    # the label path keeps its fixed names
    assert check(hga, status="In Progress")[0] == 5


def test_claim_check_own_latest_claim_continues(hga):
    code, lines = check(hga, status="In Progress", cl=claims(hga, comment(1, -5, "Claimed · fix · a · session aaaa1111")))
    assert code == 0 and lines[-1].startswith("Verdict: yours")


def test_claim_check_resumed_run_that_lost_the_race_withdraws(hga):
    other = comment(1, -6, "Claimed · fix · agent · session bbbb2222")
    mine = comment(2, -5, "Claimed · fix · agent · session aaaa1111")
    # this session's claim is the latest, but the other session posted first: it won
    code, lines = check(hga, status="In Progress", cl=claims(hga, other, mine))
    assert code == 5 and lines[-1].startswith("Verdict: later") and "session bbbb2222" in lines[1]
    # a later claim of another session does not take it from the first one
    later = comment(3, -4, "Claimed · fix · agent · session bbbb2222")
    assert check(hga, status="In Progress", cl=claims(hga, mine, later))[0] == 0
    # a claim more than a day before this session's is a dead run's: it does not count
    stale = comment(0, -60 * 30, "Claimed · fix · agent · session cccc3333")
    assert check(hga, status="In Progress", cl=claims(hga, stale, mine))[0] == 0


def test_claim_read_back_first_and_later(hga):
    mine = comment(10, 2, "Claimed · fix · agent · session aaaa1111")
    other = comment(11, 2, "Claimed · fix · agent · session bbbb2222")
    old = comment(5, -30, "Claimed · fix · agent · session cccc3333")  # before the window: the check saw it
    # this session posted first (same second, lower id): it keeps the issue
    code, lines = check(hga, cl=claims(hga, old, mine, other), since=0)
    assert code == 0 and lines[-1].startswith("Verdict: first")
    assert lines[0] == f"Your claim: {mine['url']} (comment id 10)"
    # the other session was first: this one withdraws
    code, lines = check(hga, tag="bbbb2222", cl=claims(hga, old, mine, other), since=0)
    assert code == 5
    assert lines[1].startswith("Earlier claim: ") and "session aaaa1111" in lines[1]
    assert lines[-1].startswith("Verdict: later")
    # a claim without a session tag (a person, an older plugin) counts as another session's
    hand = comment(9, 1, "Claimed · fix · a person")
    assert check(hga, cl=claims(hga, hand, mine), since=0)[0] == 5


def test_claim_read_back_needs_the_own_claim(hga):
    code, lines = check(hga, cl=claims(hga, comment(1, 2, "Claimed · fix · x · session bbbb2222")), since=0)
    assert code == 4 and "post it first" in lines[-1]
    assert check(hga, tag=None, cl=[], since=0)[0] == 4


def fake_claim_api(hga, monkeypatch, comments, assignees=(), board=None, me="bot-account"):
    def gh(*args):
        if args[:2] == ("api", "user"):
            return me + "\n"
        if args[1] == "--paginate":
            return "".join(json.dumps(c) + "\n" for c in comments)
        return json.dumps(list(assignees))
    monkeypatch.setattr(hga, "gh", gh)
    monkeypatch.setattr(hga, "issue_items", lambda repo, num: {"title": "t18", "state": "OPEN", **issue(18, board=board)})
    monkeypatch.setattr(hga.time, "sleep", lambda s: None)


def test_cli_claim_check_before_and_after(hga, monkeypatch, capsys):
    write(hga.Path(hga.cfg()["knowledge_dir"]) / "hga.config.json", {"github": {"project": "Eng"}})
    hga.CFG = {}
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "aaaa1111-2222-3333")
    fake_claim_api(hga, monkeypatch, [], board="In Progress")
    assert hga.main(["claim-check", "acme/web-app", "18"]) == 5
    assert "Verdict: taken — Status In Progress" in capsys.readouterr().out

    now = datetime.now(timezone.utc)
    mine = {"id": 7, "created_at": now.isoformat(), "body": "Claimed · fix · agent · session aaaa1111",
            "user": "bot-account", "url": "u7"}
    fake_claim_api(hga, monkeypatch, [mine], board="Todo")
    since = f"{(now - timedelta(minutes=1)).timestamp():.0f}"
    assert hga.main(["claim-check", "acme/web-app", "18", "--since", since]) == 0
    out = capsys.readouterr().out
    assert out.startswith("acme/web-app#18: t18 · issue: OPEN")
    assert "Your claim: u7 (comment id 7)" in out and "Verdict: first" in out
    assert hga.main(["claim-check", "acme/web-app", "18", "--since", (now - timedelta(minutes=1)).isoformat()]) == 0


# --- run start marker and outcomes ---------------------------------------------------------------


def test_metrics_start_marker_is_replaced_by_the_record(hga, tmp_path, monkeypatch, capsys):
    write(tmp_path / "kb" / "hga.config.json", {"timezone": "UTC"})
    transcripts(tmp_path, hga, monkeypatch)
    state_file(tmp_path, hga, monkeypatch)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert hga.main(["metrics-start", "acme/web-app", "18"]) == 0
    path = capsys.readouterr().out.strip()
    marker = json.loads(open(path, encoding="utf-8").read())
    assert (marker["schema"], marker["stage"], marker["finished"], marker["ended_at"]) == (1, "started", False, None)
    assert (marker["started_at"], marker["sessions"], marker["verb"]) == ("2026-10-13T08:00:00+00:00", ["sess-1"], "fix")
    validate = load("validate_kb", "knowledge/scripts/validate_kb.py")
    assert validate.check(tmp_path / "kb", date(2026, 10, 15)) == ([], [])

    # the record lands on the same file; a later marker call does not undo it
    rec_path, rec = record(hga, capsys)
    assert rec_path == path and rec["stage"] == "recorded"
    assert hga.main(["metrics-start", "acme/web-app", "18"]) == 0
    assert "already exists" in capsys.readouterr().err
    assert json.loads(open(path, encoding="utf-8").read())["stage"] == "recorded"
    assert len(list((tmp_path / "kb" / "metrics").rglob("*.json"))) == 1


def test_metrics_start_needs_the_state_file(hga, tmp_path, monkeypatch, capsys):
    (tmp_path / "kb").mkdir()
    monkeypatch.setattr(hga, "ISSUE_DIR", tmp_path / "issue")
    assert hga.main(["metrics-start", "acme/web-app", "18"]) == 4
    assert "no issue pane state file" in capsys.readouterr().err
    assert not (tmp_path / "kb" / "metrics").exists()


def a_marker(issue, started, sessions=("s-x",)):
    return {"schema": 1, "stage": "started", "repo": "acme/web-app", "issue": issue, "verb": "fix",
            "started_at": started, "ended_at": None, "finished": False, "recorded_at": started,
            "sessions": list(sessions)}


def test_metrics_outcomes_and_abort_rate(hga, tmp_path, capsys):
    m = metrics_kb(tmp_path)  # three records from before the markers: no outcome
    d = m / "acme" / "web-app"
    write(d / "20-20261010T070000Z.json", a_record(issue=20, started="2026-10-10T09:00:00+02:00", stage="recorded",
                                                    sessions=["s-20"]))
    write(d / "21-20261011T070000Z.json", a_record(issue=21, started="2026-10-11T09:00:00+02:00", stage="recorded",
                                                    finished=False, sessions=["s-21"]))
    write(d / "22-20261012T070000Z.json", a_marker(22, "2026-10-12T09:00:00+02:00"))  # never recorded
    write(d / "23-20261015T230000Z.json", a_marker(23, "2026-10-16T01:00:00+02:00"))  # young: may still run
    # the marker of a run whose record landed under another start (same issue, same session): counted once
    write(d / "20-20261010T065959Z.json", a_marker(20, "2026-10-10T08:59:59+02:00", sessions=["s-20"]))

    now = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    rows, warnings = hga.collect_metrics(tmp_path / "kb", None, None, None, False, now=now)
    assert warnings[-1].startswith("skipped 1 record(s) with an unknown schema")
    runs = {r["issue"]: r for r in rows if r["kind"] == "run"}
    assert {i: r["outcome"] for i, r in runs.items()} == {
        3: None, 7: None, 9: None, 20: "finished", 21: "unfinished", 22: "aborted", 23: "open"}
    assert runs[22]["wall_s"] is None and runs[22]["total_tokens"] is None
    assert not [r for r in rows if r["issue"] == 22 and r["kind"] != "run"]  # a marker has no sections
    assert {r["outcome"] for r in rows if r["issue"] == 20} == {"finished"}  # sections carry it too
    assert hga.outcome_summary(rows, 24) == (
        "runs with a start marker: 1 finished, 1 unfinished, 1 aborted, 1 open · abort rate 33% of 3 "
        "(aborted = no record 24 h after the start; open = younger, not counted)")
    # a longer threshold keeps the four-day-old run open
    rows, _ = hga.collect_metrics(tmp_path / "kb", None, None, None, False, now=now, stale_hours=100)
    assert {r["issue"]: r["outcome"] for r in rows if r["kind"] == "run"}[22] == "open"
    assert hga.outcome_summary([r for r in rows if r["outcome"] is None], 24) is None


def test_cli_metrics_prints_the_abort_rate(hga, tmp_path, capsys):
    d = tmp_path / "kb" / "metrics" / "acme" / "web-app"
    write(d / "22-20261012T070000Z.json", a_marker(22, "2026-10-12T09:00:00+02:00"))
    assert hga.main(["metrics", "--format", "csv"]) == 0
    captured = capsys.readouterr()
    header, row = captured.out.splitlines()
    assert dict(zip(header.split(","), row.split(",")))["outcome"] == "aborted"
    assert "abort rate 100% of 1" in captured.err
