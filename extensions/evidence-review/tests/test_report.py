import json
import re
from html.parser import HTMLParser

import pytest

from evidence_wiki.report import render_report


def embedded_report(document):
    data = re.search(r'<script id="report-data" type="application/json">(.*?)</script>',
                     document, re.DOTALL)
    assert data is not None
    return json.loads(data.group(1))


def test_preserves_single_inspection_and_review_history(tmp_path):
    report = {"schema_version": 1, "workspace_name": "Sample", "claims": [{
        "id": "retention", "review_state": "needs_review", "eligibility": "blocked",
        "decisions": [{"action": "approve", "actor": "synthetic-reviewer", "basis": "old-basis"}],
        "evidence": [{"path": "source.md", "start_line": 2, "end_line": 3,
                      "expected_text": "30 days", "actual_text": "90 days"}]}]}
    output = tmp_path / "nested" / "report.html"
    render_report(report, output)
    document = output.read_text(encoding="utf-8")
    assert embedded_report(document) == report
    assert 'lang="ko"' in document
    assert "근거가 바뀌면, 검토도 다시." in document
    assert "When evidence changes, review again." in document
    assert "Current reuse eligibility" in document
    assert "Decision history" in document
    assert "does not block native LLM Wiki approvals or answers" in document


def test_escapes_html_script_boundaries_and_unicode_separators(tmp_path):
    attack = '</script><script>alert("injected")</script>&<img src=x onerror=alert(1)>\u2028\u2029'
    report = {"workspace_name": attack, "claims": [{"id": attack, "title": attack}]}
    output = tmp_path / "report.html"
    render_report(report, output)
    document = output.read_text(encoding="utf-8")
    assert embedded_report(document) == report
    assert attack not in document
    assert '\\u003c/script\\u003e' in document
    assert '\\u2028\\u2029' in document
    assert "\u2028" not in document and "\u2029" not in document
    assert "innerHTML" not in document and "document.write" not in document
    assert ".textContent" in document


def test_demo_keeps_recorded_stages_and_labels_them_as_snapshots(tmp_path):
    stages = [{"id": label, "label_ko": label, "label_en": label,
               "inspection": {"observed_at": f"2026-11-03T12:00:0{index}Z",
                              "claims": [{"id": "retention", "value": index}]}}
              for index, label in enumerate(["approved", "source-changed", "rule-failed", "reviewed"])]
    report = {"schema_version": 1, "demo": True, "stages": stages}
    output = tmp_path / "report.html"
    render_report(report, output, language="en")
    document = output.read_text(encoding="utf-8")
    assert embedded_report(document) == report
    assert 'lang="en"' in document
    assert "실행 기록" in document and "Execution records" in document
    assert "Synthetic demo" in document
    assert "does not monitor file changes in real time" in document


class ResourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.resources = []

    def handle_starttag(self, tag, attributes):
        self.resources.extend(value for name, value in attributes if name in {"src", "href", "srcset"})


def test_report_has_no_external_or_file_resources(tmp_path):
    output = tmp_path / "report.html"
    render_report({"claims": []}, output)
    document = output.read_text(encoding="utf-8")
    parser = ResourceParser()
    parser.feed(document)
    assert parser.resources == []
    assert "fetch(" not in document and "XMLHttpRequest" not in document
    assert "@import" not in document and "url(" not in document
    assert "default-src 'none'" in document


@pytest.mark.parametrize("language", ["de", "<script>", ""])
def test_rejects_unsupported_language_without_creating_file(tmp_path, language):
    output = tmp_path / "report.html"
    with pytest.raises(ValueError, match="language"):
        render_report({}, output, language=language)
    assert not output.exists()
