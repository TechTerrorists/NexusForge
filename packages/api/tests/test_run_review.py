from __future__ import annotations

import uuid

import pytest

from app.models import ExecutionStatus, WorkflowRun
from app.routers.tasks import _apply_run_review


def make_run() -> WorkflowRun:
    return WorkflowRun(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        status=ExecutionStatus.NEEDS_REVIEW,
        output_data={"branch": "nexusforge/run-test", "summary": "Ready"},
    )


def test_approve_run_records_review_and_marks_complete() -> None:
    run = make_run()
    reviewer_id = uuid.uuid4()

    output = _apply_run_review(
        run,
        approved=True,
        feedback="README contents verified.",
        reviewer_id=reviewer_id,
    )

    assert run.status == ExecutionStatus.COMPLETED
    assert output["branch"] == "nexusforge/run-test"
    assert output["review"]["decision"] == "approved"
    assert output["review"]["reviewed_by"] == str(reviewer_id)


def test_reject_run_requires_feedback() -> None:
    run = make_run()

    with pytest.raises(ValueError, match="Feedback is required"):
        _apply_run_review(
            run,
            approved=False,
            feedback="  ",
            reviewer_id=uuid.uuid4(),
        )

    assert run.status == ExecutionStatus.NEEDS_REVIEW


def test_reject_run_records_feedback_and_closes_as_cancelled() -> None:
    run = make_run()

    output = _apply_run_review(
        run,
        approved=False,
        feedback="The generated output did not modify the repository.",
        reviewer_id=uuid.uuid4(),
    )

    assert run.status == ExecutionStatus.CANCELLED
    assert output["review"]["decision"] == "rejected"
    assert output["review"]["feedback"] == (
        "The generated output did not modify the repository."
    )
