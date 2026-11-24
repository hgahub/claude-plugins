from conftest import load

ichk = load("intent_check", "intent/scripts/intent_check.py")


def test_self_test():
    ichk.self_test()


def test_exit_codes_and_json(tmp_path, capsys):
    f = tmp_path / "intent.md"
    f.write_text(ichk.SAMPLE, encoding="utf-8")
    assert ichk.main([str(f)]) == 0
    assert ichk.main([str(f), "--json"]) == 0
    assert '"verdict": "PASS"' in capsys.readouterr().out
    f.write_text(ichk.SAMPLE.replace(" (edge case)", "").replace(" (origin/main `4a81922`)", ""), encoding="utf-8")
    assert ichk.main([str(f)]) == 1
    f.write_text("# no intent\n", encoding="utf-8")
    assert ichk.main([str(f)]) == 2
    assert ichk.main([]) == 64


def test_code_is_not_a_placeholder():
    body = (
        "1. The `<button>` gets a tooltip.\n"
        "2. `</div>`, `<input type=\"text\">`, `<UserCard />`, `Map<K, V>`, `fn(...)` and `TODO` stay as they are.\n"
        "```html\n<dialog open>…</dialog>\n```\n"
    )
    r = ichk.check(ichk.SAMPLE.replace("1. The column appears.\n2. Without a source it is empty.\n", body))
    assert r["verdict"] == "PASS", r
    assert r["sections"]["criteria"] == "done"


def test_placeholders_still_block():
    for old, new in [
        ("`4a81922`", "`<sha>`"),
        ("origin/main", "origin/<default-branch>"),
        ("1. The column appears.", "1. <a statement checkable on its own>"),
        ("1. The column appears.", "1. `<the author's name>` decides"),
        ("1. The column appears.", "1. The column appears ..."),
        ("1. The column appears.", "1. TBD"),
    ]:
        r = ichk.check(ichk.SAMPLE.replace(old, new))
        assert r["verdict"] == "BLOCK" and any("E_PLACEHOLDER" in e for e in r["errors"]), (new, r)


def test_headings_ignore_case_and_accents():
    r = ichk.check(ichk.SAMPLE.replace("## Acceptance criteria", "## ACCEPTANCE CRITERIA (v1)"))
    assert r["verdict"] == "PASS", r
