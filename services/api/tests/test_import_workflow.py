"""The shape of the Import region workflow (ADR 033, decision 8). It cannot run here, so these
tests only keep its ordering and its retry rules from being edited away by accident."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "import-region.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_geofabrik_is_checked_before_the_slow_package_install() -> None:
    text = _text()
    importer = text.index("- name: Install the importer")
    check = text.index("- name: Check that Geofabrik can be reached")
    tools = text.index("- name: Install tools")
    assert importer < check < tools


def test_only_a_network_failure_is_tried_again_and_at_most_three_times() -> None:
    text = _text()
    retry = text[text.index("\n  retry:") :]
    assert "needs: import" in retry and "actions: write" in retry
    assert "needs.import.outputs.network_failed == 'true'" in retry
    assert "fromJSON(inputs.attempt) < 3" in retry
    assert 'attempt="$NEXT_ATTEMPT"' in retry and 'job_id="$JOB_ID"' in retry
    assert "steps.geofabrik.outcome == 'failure'" in text
    assert "steps.region.outputs.download_failed == 'true'" in text
    # the importer's exit code for a failed download is the one the workflow looks for
    assert '"$status" -eq 75' in text


def test_the_attempt_input_defaults_to_one_so_the_app_need_not_send_it() -> None:
    text = _text()
    block = text[text.index("      attempt:") : text.index("permissions:")]
    assert 'default: "1"' in block and "required: false" in block


def test_no_expression_uses_arithmetic() -> None:
    """GitHub rejects the whole file (a failed run with no jobs) for ``${{ x + 1 }}``: workflow
    expressions have no arithmetic. That happened on 2026-11-19; do the sum in the shell."""
    for expression in re.findall(r"\$\{\{(.*?)\}\}", _text(), flags=re.DOTALL):
        assert "+" not in expression, expression
