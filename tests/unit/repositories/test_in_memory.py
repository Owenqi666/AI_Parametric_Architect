from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    AuditAction,
    AuditActorType,
    ModelAlreadyExistsError,
    ModelNotFoundError,
    ModelRevision,
    NonJsonValueError,
    RedoUnavailableError,
    RestorationPreview,
    RevisionConflictError,
    RevisionNotFoundError,
    TrustedAuditIdentity,
    UndoUnavailableError,
)
from ai_parametric_architect.repositories import InMemoryRevisionRepository

BASE_TIME = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)
AUDIT_IDENTITY = TrustedAuditIdentity(
    actor_id="repository-test",
    actor_type=AuditActorType.SYSTEM,
    trace_id="trace:repository-test",
)


class FailingDeepCopy:
    def __deepcopy__(self, _memo: dict[int, object]) -> object:
        raise RuntimeError("audit detail copy failed")


def revision(number: int, *, name: str, parent: int | None = None) -> ModelRevision:
    return ModelRevision(
        model_id="mdl_house",
        revision_number=number,
        created_at=BASE_TIME + timedelta(minutes=number),
        parent_revision=parent,
        document={"model_id": "mdl_house", "revision": number, "name": name},
    )


@pytest.fixture
def repository() -> InMemoryRevisionRepository:
    return InMemoryRevisionRepository()


def initialize(repository: InMemoryRevisionRepository) -> ModelRevision:
    return repository.initialize(
        revision(0, name="Initial"),
        provenance="human:architect-7",
        rationale="Create editing history.",
        audit_identity=AUDIT_IDENTITY,
    )


def commit(
    repository: InMemoryRevisionRepository,
    number: int,
    *,
    name: str,
    expected: int | None = None,
) -> ModelRevision:
    expected_revision = number - 1 if expected is None else expected
    return repository.commit_patch(
        revision(number, name=name, parent=expected_revision),
        expected_revision=expected_revision,
        provenance="human:architect-7",
        rationale=f"Change name to {name}.",
        details={"operation_paths": ["/name"]},
        audit_identity=AUDIT_IDENTITY,
    )


def restore(
    repository: InMemoryRevisionRepository,
    action: AuditAction,
    *,
    expected_revision: int,
    minute: int,
    rationale: str,
) -> ModelRevision:
    preview = (
        repository.preview_undo("mdl_house", expected_revision)
        if action is AuditAction.UNDO
        else repository.preview_redo("mdl_house", expected_revision)
    )
    candidate = restoration_candidate(preview, minute=minute)
    return repository.commit_restoration(
        preview,
        candidate,
        provenance="test",
        rationale=rationale,
        audit_identity=AUDIT_IDENTITY,
    )


def restoration_candidate(
    preview: RestorationPreview,
    *,
    minute: int,
    document: dict[str, Any] | None = None,
    model_id: str | None = None,
    revision_number: int | None = None,
    parent_revision: int | None = None,
) -> ModelRevision:
    candidate_document = preview.document if document is None else document
    candidate_revision = preview.head_revision + 1 if revision_number is None else revision_number
    candidate_document["revision"] = candidate_revision
    return ModelRevision(
        model_id=preview.model_id if model_id is None else model_id,
        revision_number=candidate_revision,
        created_at=BASE_TIME + timedelta(minutes=minute),
        parent_revision=(preview.head_revision if parent_revision is None else parent_revision),
        document=candidate_document,
    )


def test_initialize_creates_head_snapshot_and_audit_entry(
    repository: InMemoryRevisionRepository,
) -> None:
    source = revision(0, name="Initial")
    created = repository.initialize(
        source,
        provenance="import:test",
        rationale="Seed history.",
        audit_identity=AUDIT_IDENTITY,
    )

    source._document["name"] = "Private mutation"
    created._document["name"] = "Returned mutation"

    assert repository.head("mdl_house").document["name"] == "Initial"
    assert repository.get("mdl_house", 0).revision_number == 0
    assert [entry.to_dict() for entry in repository.audit_log("mdl_house")] == [
        {
            "sequence": 1,
            "model_id": "mdl_house",
            "action": "initialize",
            "from_revision": None,
            "to_revision": 0,
            "restored_from_revision": None,
            "created_at": "2026-07-14T09:00:00+00:00",
            "actor_id": "repository-test",
            "actor_type": "system",
            "agent_version": None,
            "trace_id": "trace:repository-test",
            "untrusted_provenance": "import:test",
            "untrusted_rationale": "Seed history.",
            "details": {},
        }
    ]


def test_initialize_rejects_duplicate_and_parented_revision(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)

    with pytest.raises(ModelAlreadyExistsError):
        initialize(repository)

    other = InMemoryRevisionRepository()
    with pytest.raises(ValueError, match="cannot have a parent"):
        other.initialize(
            revision(1, name="Invalid", parent=0),
            provenance="test",
            rationale="Invalid seed.",
            audit_identity=AUDIT_IDENTITY,
        )


def test_initialize_rejects_empty_audit_metadata_without_creating_history(
    repository: InMemoryRevisionRepository,
) -> None:
    with pytest.raises(ValueError, match="provenance"):
        repository.initialize(
            revision(0, name="Initial"),
            provenance="",
            rationale="Seed history.",
            audit_identity=AUDIT_IDENTITY,
        )

    with pytest.raises(ModelNotFoundError):
        repository.head("mdl_house")


def test_missing_model_and_revision_have_stable_errors(
    repository: InMemoryRevisionRepository,
) -> None:
    with pytest.raises(ModelNotFoundError):
        repository.head("missing")
    with pytest.raises(ModelNotFoundError):
        repository.audit_log("missing")

    initialize(repository)
    with pytest.raises(RevisionNotFoundError) as error:
        repository.get("mdl_house", 99)

    assert error.value.details == {"model_id": "mdl_house", "revision_number": 99}


@pytest.mark.parametrize("value", [False, 0.0, -1])
def test_public_revision_arguments_require_non_negative_integers(
    repository: InMemoryRevisionRepository, value: object
) -> None:
    initialize(repository)

    with pytest.raises(ValueError, match="non-negative integer"):
        repository.get("mdl_house", cast(Any, value))
    with pytest.raises(ValueError, match="non-negative integer"):
        repository.commit_patch(
            revision(1, name="Invalid", parent=0),
            expected_revision=cast(Any, value),
            provenance="test",
            rationale="Reject invalid revision type.",
            details={},
            audit_identity=AUDIT_IDENTITY,
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        repository.preview_undo("mdl_house", cast(Any, value))
    with pytest.raises(ValueError, match="non-negative integer"):
        repository.preview_redo("mdl_house", cast(Any, value))

    assert repository.head("mdl_house").revision_number == 0
    assert len(repository.audit_log("mdl_house")) == 1


def test_commit_advances_head_and_appends_audit(repository: InMemoryRevisionRepository) -> None:
    initialize(repository)

    created = commit(repository, 1, name="Edited")

    assert created.parent_revision == 0
    assert repository.head("mdl_house").document["name"] == "Edited"
    entries = repository.audit_log("mdl_house")
    assert [entry.action for entry in entries] == [AuditAction.INITIALIZE, AuditAction.PATCH]
    assert entries[-1].sequence == 2
    assert entries[-1].details == {"operation_paths": ["/name"]}


@pytest.mark.parametrize(
    "candidate",
    [
        revision(2, name="Skipped", parent=0),
        revision(1, name="Wrong parent", parent=None),
    ],
)
def test_commit_rejects_invalid_revision_chain_without_mutating_history(
    repository: InMemoryRevisionRepository, candidate: ModelRevision
) -> None:
    initialize(repository)

    with pytest.raises(ValueError):
        repository.commit_patch(
            candidate,
            expected_revision=0,
            provenance="test",
            rationale="Invalid chain.",
            details={},
            audit_identity=AUDIT_IDENTITY,
        )

    assert repository.head("mdl_house").revision_number == 0
    assert len(repository.audit_log("mdl_house")) == 1


def test_stale_commit_is_rejected_without_history_change(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="Winner")

    with pytest.raises(RevisionConflictError) as error:
        repository.commit_patch(
            revision(2, name="Stale", parent=0),
            expected_revision=0,
            provenance="test",
            rationale="Stale edit.",
            details={},
            audit_identity=AUDIT_IDENTITY,
        )

    assert error.value.details == {"model_id": "mdl_house", "expected": 0, "actual": 1}
    assert repository.head("mdl_house").document["name"] == "Winner"
    assert len(repository.audit_log("mdl_house")) == 2


def test_audit_construction_failure_is_atomic(repository: InMemoryRevisionRepository) -> None:
    initialize(repository)

    with pytest.raises(NonJsonValueError):
        repository.commit_patch(
            revision(1, name="Must not commit", parent=0),
            expected_revision=0,
            provenance="test",
            rationale="Inject audit failure.",
            details={"failure": FailingDeepCopy()},
            audit_identity=AUDIT_IDENTITY,
        )

    assert repository.head("mdl_house").revision_number == 0
    assert len(repository.audit_log("mdl_house")) == 1
    with pytest.raises(UndoUnavailableError):
        repository.preview_undo("mdl_house", 0)


def test_undo_and_redo_create_monotonic_compensating_revisions(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    commit(repository, 2, name="Second")

    undone = restore(
        repository,
        AuditAction.UNDO,
        expected_revision=2,
        minute=3,
        rationale="Undo second edit.",
    )
    redone = restore(
        repository,
        AuditAction.REDO,
        expected_revision=3,
        minute=4,
        rationale="Redo second edit.",
    )

    assert (undone.revision_number, undone.parent_revision, undone.document["name"]) == (
        3,
        2,
        "First",
    )
    assert (redone.revision_number, redone.parent_revision, redone.document["name"]) == (
        4,
        3,
        "Second",
    )
    assert repository.get("mdl_house", 2).document["name"] == "Second"
    entries = repository.audit_log("mdl_house")
    assert [entry.action for entry in entries] == [
        AuditAction.INITIALIZE,
        AuditAction.PATCH,
        AuditAction.PATCH,
        AuditAction.UNDO,
        AuditAction.REDO,
    ]
    assert entries[3].restored_from_revision == 1
    assert entries[4].restored_from_revision == 2


def test_restoration_preview_and_candidate_are_verified_before_state_change(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    preview = repository.preview_undo("mdl_house", 1)

    preview._document["name"] = "Tampered preview"
    with pytest.raises(ValueError, match="preview document"):
        repository.commit_restoration(
            preview,
            restoration_candidate(preview, minute=2),
            provenance="test",
            rationale="Reject a mutated preview.",
            audit_identity=AUDIT_IDENTITY,
        )

    fresh_preview = repository.preview_undo("mdl_house", 1)
    forged_document = fresh_preview.document
    forged_document["name"] = "Forged candidate"
    with pytest.raises(ValueError, match="target snapshot"):
        repository.commit_restoration(
            fresh_preview,
            restoration_candidate(fresh_preview, minute=2, document=forged_document),
            provenance="test",
            rationale="Reject a forged candidate.",
            audit_identity=AUDIT_IDENTITY,
        )

    assert repository.head("mdl_house").revision_number == 1
    assert len(repository.audit_log("mdl_house")) == 2
    assert (
        restore(
            repository,
            AuditAction.UNDO,
            expected_revision=1,
            minute=2,
            rationale="Valid retry remains available.",
        ).revision_number
        == 2
    )


def test_stale_restoration_preview_conflicts_after_intervening_patch(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    preview = repository.preview_undo("mdl_house", 1)
    candidate = restoration_candidate(preview, minute=2)
    commit(repository, 2, name="Second")

    with pytest.raises(RevisionConflictError):
        repository.commit_restoration(
            preview,
            candidate,
            provenance="test",
            rationale="Stale restoration.",
            audit_identity=AUDIT_IDENTITY,
        )

    assert repository.head("mdl_house").document["name"] == "Second"
    assert len(repository.audit_log("mdl_house")) == 3


def test_restoration_preview_must_match_current_stack_top(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    commit(repository, 2, name="Second")
    target_zero = repository.get("mdl_house", 0)
    forged_preview = RestorationPreview(
        model_id="mdl_house",
        action=AuditAction.UNDO,
        head_revision=2,
        target_revision=0,
        document=target_zero.document,
    )

    with pytest.raises(ValueError, match="history stack"):
        repository.commit_restoration(
            forged_preview,
            restoration_candidate(forged_preview, minute=3),
            provenance="test",
            rationale="Reject skipped undo target.",
            audit_identity=AUDIT_IDENTITY,
        )

    assert repository.head("mdl_house").revision_number == 2


def test_restoration_candidate_chain_and_identity_are_enforced(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    preview = repository.preview_undo("mdl_house", 1)
    target = preview.document
    candidates = [
        restoration_candidate(
            preview,
            minute=2,
            document={"model_id": "other", "revision": 0, "name": "Initial"},
            model_id="other",
        ),
        restoration_candidate(preview, minute=3, revision_number=3),
        restoration_candidate(preview, minute=2, parent_revision=0),
    ]

    for candidate in candidates:
        with pytest.raises(ValueError):
            repository.commit_restoration(
                preview,
                candidate,
                provenance="test",
                rationale="Reject invalid restoration chain.",
                audit_identity=AUDIT_IDENTITY,
            )

    assert target["revision"] == 0
    assert repository.head("mdl_house").revision_number == 1


def test_compare_and_swap_allows_only_one_concurrent_restoration(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    preview = repository.preview_undo("mdl_house", 1)
    candidate = restoration_candidate(preview, minute=2)
    barrier = Barrier(2)

    def write() -> str:
        barrier.wait()
        try:
            repository.commit_restoration(
                preview,
                candidate,
                provenance="concurrency-test",
                rationale="Competing restoration.",
                audit_identity=AUDIT_IDENTITY,
            )
        except RevisionConflictError:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: write(), range(2)))

    assert sorted(outcomes) == ["committed", "conflict"]
    assert repository.head("mdl_house").revision_number == 2
    assert len(repository.audit_log("mdl_house")) == 3


def test_multiple_undo_and_redo_follow_stack_order(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    commit(repository, 2, name="Second")

    first_undo = restore(
        repository,
        AuditAction.UNDO,
        expected_revision=2,
        minute=3,
        rationale="Undo.",
    )
    second_undo = restore(
        repository,
        AuditAction.UNDO,
        expected_revision=3,
        minute=4,
        rationale="Undo again.",
    )
    first_redo = restore(
        repository,
        AuditAction.REDO,
        expected_revision=4,
        minute=5,
        rationale="Redo.",
    )
    second_redo = restore(
        repository,
        AuditAction.REDO,
        expected_revision=5,
        minute=6,
        rationale="Redo again.",
    )

    assert [item.document["name"] for item in (first_undo, second_undo)] == [
        "First",
        "Initial",
    ]
    assert [item.document["name"] for item in (first_redo, second_redo)] == [
        "First",
        "Second",
    ]


def test_undo_redo_availability_and_conflict_do_not_append_audit(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)

    with pytest.raises(UndoUnavailableError):
        repository.preview_undo("mdl_house", 0)
    with pytest.raises(RedoUnavailableError):
        repository.preview_redo("mdl_house", 0)
    with pytest.raises(RevisionConflictError):
        repository.preview_undo("mdl_house", 9)

    assert len(repository.audit_log("mdl_house")) == 1


def test_successful_patch_after_undo_clears_redo(repository: InMemoryRevisionRepository) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    restore(
        repository,
        AuditAction.UNDO,
        expected_revision=1,
        minute=2,
        rationale="Undo.",
    )
    commit(repository, 3, name="Alternative", expected=2)

    with pytest.raises(RedoUnavailableError):
        repository.preview_redo("mdl_house", 3)


def test_failed_commit_after_undo_preserves_redo(repository: InMemoryRevisionRepository) -> None:
    initialize(repository)
    commit(repository, 1, name="First")
    restore(
        repository,
        AuditAction.UNDO,
        expected_revision=1,
        minute=2,
        rationale="Undo.",
    )

    with pytest.raises(ValueError):
        repository.commit_patch(
            revision(4, name="Invalid", parent=2),
            expected_revision=2,
            provenance="test",
            rationale="Invalid.",
            details={},
            audit_identity=AUDIT_IDENTITY,
        )

    restored = restore(
        repository,
        AuditAction.REDO,
        expected_revision=2,
        minute=3,
        rationale="Redo remains available.",
    )
    assert restored.document["name"] == "First"


def test_audit_log_returns_defensive_details_copy(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    commit(repository, 1, name="First")

    first_read = repository.audit_log("mdl_house")
    cast(dict[str, object], first_read[-1]._details)["operation_paths"] = []

    assert repository.audit_log("mdl_house")[-1].details == {"operation_paths": ["/name"]}


def test_compare_and_swap_allows_only_one_concurrent_writer(
    repository: InMemoryRevisionRepository,
) -> None:
    initialize(repository)
    barrier = Barrier(2)

    def write(name: str) -> str:
        barrier.wait()
        try:
            repository.commit_patch(
                revision(1, name=name, parent=0),
                expected_revision=0,
                provenance="concurrency-test",
                rationale="Competing write.",
                details={},
                audit_identity=AUDIT_IDENTITY,
            )
        except RevisionConflictError:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, ("A", "B")))

    assert sorted(outcomes) == ["committed", "conflict"]
    assert repository.head("mdl_house").revision_number == 1
    assert len(repository.audit_log("mdl_house")) == 2
