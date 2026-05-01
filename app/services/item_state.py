from enum import Enum


class ItemStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    TIMEOUT = "TIMEOUT"


TERMINAL_STATUSES = frozenset({
    ItemStatus.COMPLETED,
    ItemStatus.FAILED,
    ItemStatus.SKIPPED,
    ItemStatus.TIMEOUT,
})


_ALLOWED_TRANSITIONS: dict[ItemStatus, frozenset[ItemStatus]] = {
    ItemStatus.PENDING: frozenset({
        ItemStatus.PROCESSING,
        ItemStatus.SKIPPED,
    }),
    ItemStatus.PROCESSING: frozenset({
        ItemStatus.PROCESSING,
        ItemStatus.COMPLETED,
        ItemStatus.FAILED,
        ItemStatus.SKIPPED,
        ItemStatus.TIMEOUT,
    }),
    # Phase 4-c: retry_worker가 TIMEOUT 매물을 PENDING으로 reset 가능
    ItemStatus.TIMEOUT: frozenset({
        ItemStatus.PENDING,
    }),
}


class InvalidStateTransition(Exception):
    """허용되지 않은 status 전이를 시도한 경우."""


def assert_transition(current: ItemStatus, target: ItemStatus) -> None:
    """current → target 전이 가능 여부 검증. 불가 시 InvalidStateTransition raise."""
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidStateTransition(
            f"transition not allowed: {current.value} -> {target.value}"
        )
