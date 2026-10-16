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


def test_headings_ignore_case_and_accents():
    r = ichk.check(ichk.SAMPLE.replace("## Acceptance criteria", "## ACCEPTANCE CRITERIA (v1)"))
    assert r["verdict"] == "PASS", r
