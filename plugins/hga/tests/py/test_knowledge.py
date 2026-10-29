from pathlib import Path

from conftest import load

validate = load("validate_kb", "knowledge/scripts/validate_kb.py")
build_map = load("build_map", "knowledge/scripts/build_map.py")
scaffold = load("scaffold_kb", "init/scripts/scaffold_kb.py")


def page(path: Path, title: str, body: str = "", verified="2026-10-01", status="verified", extra=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{title}"\nverified_at: "{verified}"\nstatus: {status}\nreview_after_days: 30\n{extra}---\n\n{body}\n',
        encoding="utf-8",
    )


def test_fresh_scaffold_is_valid(tmp_path):
    kb = tmp_path / "kb"
    assert scaffold.main([str(kb)]) == 0
    assert (kb / "00-index.md").read_text(encoding="utf-8").count("{{DATE}}") == 0
    assert validate.main([str(kb)]) == 0
    # refuses a non-empty folder, adds only missing files with --add-missing
    assert scaffold.main([str(kb)]) == 3
    (kb / "apps" / "README.md").unlink()
    (kb / "00-index.md").write_text("mine", encoding="utf-8")
    assert scaffold.main([str(kb), "--add-missing"]) == 0
    assert (kb / "apps" / "README.md").exists()
    assert (kb / "00-index.md").read_text(encoding="utf-8") == "mine"


def test_scaffold_dry_run_lists_missing_files_without_writing(tmp_path, capsys):
    kb = tmp_path / "kb"
    assert scaffold.main([str(kb), "--dry-run"]) == 0
    assert not kb.exists()
    assert "would write 00-index.md" in capsys.readouterr().out
    assert scaffold.main([str(kb)]) == 0
    (kb / "apps" / "README.md").unlink()
    capsys.readouterr()
    assert scaffold.main([str(kb), "--add-missing", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would write apps/README.md" in out
    assert "1 file(s) missing" in out
    assert not (kb / "apps" / "README.md").exists()


def test_frontmatter_errors(tmp_path):
    (tmp_path / "no-front.md").write_text("# x\n", encoding="utf-8")
    page(tmp_path / "bad.md", "Bad", verified="31/01/2026", status="done")
    (tmp_path / "README.md").write_text("# exempt\n", encoding="utf-8")
    errors, _w = validate.check(tmp_path, validate.date(2026, 10, 15))
    text = "\n".join(errors)
    assert "no-front.md:1: missing frontmatter" in text
    assert "verified_at `31/01/2026` is not YYYY-MM-DD" in text
    assert "status `done` is not one of" in text
    assert "README.md" not in text


def test_links_and_wikilinks(tmp_path):
    page(tmp_path / "notes" / "web-app-1-a.md", "A", "See [b](b.md), [[web-app-2-b]], [[missing-note]], [ext](https://x.test).\n\n```\n[[in-code]] [c](nope.md)\n```\n`[[inline]]`")
    page(tmp_path / "notes" / "web-app-2-b.md", "B")
    errors, _w = validate.check(tmp_path, validate.date(2026, 10, 15))
    text = "\n".join(errors)
    assert "broken link: b.md" in text
    assert "broken wikilink: [[missing-note]]" in text
    assert "web-app-2-b" not in text
    assert "in-code" not in text and "nope.md" not in text and "inline" not in text


def test_secrets_are_errors_even_in_code(tmp_path):
    page(tmp_path / "s.md", "S", "```\nGITHUB_TOKEN=ghp_" + "a" * 36 + "\n```\npassword: hunter22hunter\napi_key: <your key>\nThe key name is DB_PASSWORD.")
    errors, _w = validate.check(tmp_path, validate.date(2026, 10, 15))
    text = "\n".join(errors)
    assert "GitHub token" in text
    assert "(password)" in text
    assert text.count("looks like a secret") == 2


def test_review_due_is_a_warning(tmp_path):
    page(tmp_path / "old.md", "Old", verified="2026-01-01")
    errors, warnings = validate.check(tmp_path, validate.date(2026, 10, 15))
    assert errors == []
    assert warnings and "due for review" in warnings[0]


def test_app_of():
    apps = ["web-app", "web", "api"]
    assert build_map.app_of("web-app-142-csv-export", apps) == ("web-app", 142)
    assert build_map.app_of("web-7-x", apps) == ("web", 7)
    assert build_map.app_of("api-caching", apps) == ("api", None)
    assert build_map.app_of("billing-12-fix", apps) == ("billing", 12)
    assert build_map.app_of("misc", apps) == ("misc", None)


def test_map_relations_and_cleanup(tmp_path):
    page(tmp_path / "apps" / "web-app.md", "web-app")
    page(tmp_path / "notes" / "web-app-142-export.md", "web-app #142: export", "Follows up #151.")
    page(tmp_path / "notes" / "web-app-151-filter.md", "web-app #151: filter")
    page(tmp_path / "notes" / "web-app-cache.md", "Cache notes", "See [[web-app-142-export]].")
    page(tmp_path / "notes" / "api-151-other.md", "api #151: unrelated")
    (tmp_path / "map").mkdir()
    (tmp_path / "map" / "gone.md").write_text(build_map.MARKER + "\nold\n", encoding="utf-8")
    (tmp_path / "map" / "README.md").write_text("# map\n", encoding="utf-8")
    assert build_map.main([str(tmp_path)]) == 0
    web = (tmp_path / "map" / "web-app.md").read_text(encoding="utf-8")
    row142 = next(ln for ln in web.splitlines() if ln.startswith("| [[web-app-142-export]]"))
    assert "#142" in row142
    assert "[[web-app-151-filter]]" in row142 and "[[web-app-cache]]" in row142
    assert "api-151-other" not in web
    assert (tmp_path / "map" / "api.md").exists()
    assert not (tmp_path / "map" / "gone.md").exists()
    assert (tmp_path / "map" / "README.md").exists()
    # the generated map validates (wikilinks resolve, map/ is exempt from frontmatter)
    errors, _w = validate.check(tmp_path, validate.date(2026, 10, 15))
    assert errors == []


def test_default_root_follows_the_machine_config(tmp_path, monkeypatch):
    import kb_common
    monkeypatch.delenv("HGA_KNOWLEDGE_DIR", raising=False)
    cfg = tmp_path / "config.json"
    monkeypatch.setenv("HGA_USER_CONFIG", str(cfg))
    assert kb_common.default_root() == "~/.hga/knowledge"
    cfg.write_text('{"knowledge_dir": "/srv/kb"}', encoding="utf-8")
    assert kb_common.default_root() == "/srv/kb"
    monkeypatch.setenv("HGA_KNOWLEDGE_DIR", "/env/kb")
    assert kb_common.default_root() == "/env/kb"


GUIDE = Path(__file__).resolve().parents[2] / "skills" / "init" / "templates" / "guide.md"
GUIDE_FIELDS = {"DATE", "KNOWLEDGE_DIR", "REMOTE", "LANGUAGE", "PROJECT", "LABEL_IN_PROGRESS", "LABEL_IN_REVIEW",
                "SLACK_CHANNEL", "REVIEW_PROVIDER", "ASK_AFTER_ROUNDS", "MAX_PER_REPO", "USAGE_CEILING_PCT",
                "RISK_HIGH_PATHS", "RISK_HIGH_LABEL", "RISK_LOW_PATHS", "RISK_REPO_OVERRIDES", "CLOSING_LABEL", "BROWSER",
                "REPO_OVERRIDES"}


def test_guide_template_fills_into_a_valid_page(tmp_path):
    import re
    text = GUIDE.read_text(encoding="utf-8")
    assert set(re.findall(r"\{\{(\w+)\}\}", text)) == GUIDE_FIELDS
    # what /hga:init does: drop the instructions comment, fill the values, keep the matching variant lines
    page_text = text.split("-->\n", 1)[1].replace("{{DATE}}", "2026-10-16")
    page_text = re.sub(r"\{\{\w+\}\}", "x", page_text)
    page_text = re.sub(r"\[(remote|local only|board|no board|slack|no slack|bot|local|closing label|github closing|repos)\] ", "", page_text)
    assert page_text.startswith("---\n")
    kb = tmp_path / "kb"
    assert scaffold.main([str(kb)]) == 0
    (kb / "workflow" / "hga-guide.md").write_text(page_text, encoding="utf-8")
    errors, _w = validate.check(kb, validate.date(2026, 10, 16))
    assert errors == []


def test_metrics_records_are_data_not_pages(tmp_path, capsys):
    rec = tmp_path / "metrics" / "acme" / "web-app"
    rec.mkdir(parents=True)
    (rec / "18-20261013T080000Z.json").write_text('{"schema": 1, "tokens": {"output_tokens": 5}}\n', encoding="utf-8")
    (tmp_path / "metrics" / "README.md").write_text("# metrics/\n", encoding="utf-8")
    # a valid record: no frontmatter demanded, no error, no warning; counted apart from the pages
    assert validate.check(tmp_path, validate.date(2026, 10, 15)) == ([], [])
    assert validate.main([str(tmp_path)]) == 0
    assert "1 page(s) · 1 metrics record(s) · 0 error(s) · 0 warning(s)" in capsys.readouterr().out
    # the map reads only notes/: the records do not show up there
    page(tmp_path / "notes" / "web-app-18-x.md", "web-app #18: x")
    assert build_map.main([str(tmp_path)]) == 0
    assert "metrics" not in (tmp_path / "map" / "web-app.md").read_text(encoding="utf-8")


def test_broken_metrics_records_are_errors(tmp_path):
    rec = tmp_path / "metrics" / "acme" / "web-app"
    rec.mkdir(parents=True)
    (rec / "1-a.json").write_text('{"schema": 1,\n', encoding="utf-8")
    (rec / "2-a.json").write_text('{"issue": 2}\n', encoding="utf-8")
    (rec / "3-a.json").write_text('{"schema": 1,\n "note": "ghp_' + "a" * 36 + '"}\n', encoding="utf-8")
    errors, warnings = validate.check(tmp_path, validate.date(2026, 10, 15))
    text = "\n".join(errors)
    assert "metrics/acme/web-app/1-a.json:2: invalid JSON" in text
    assert "metrics/acme/web-app/2-a.json:1: a metrics record needs an integer `schema`" in text
    assert "metrics/acme/web-app/3-a.json:2: looks like a secret (GitHub token)" in text
    assert len(errors) == 3 and warnings == []
