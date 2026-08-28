from recourse.domain.models import CaseState


ALLOWED_TRANSITIONS: dict[CaseState, set[CaseState]] = {
    CaseState.INGESTED: {CaseState.NORMALIZED},
    CaseState.NORMALIZED: {CaseState.DIAGNOSED, CaseState.DIAGNOSIS_ABSTAINED},
    CaseState.DIAGNOSED: {CaseState.SIMULATED, CaseState.SIMULATION_FAILED},
    CaseState.DIAGNOSIS_ABSTAINED: {CaseState.ABSTAIN},
    CaseState.SIMULATED: {CaseState.CHALLENGED},
    CaseState.SIMULATION_FAILED: {CaseState.ABSTAIN},
    CaseState.CHALLENGED: {CaseState.VERIFIED, CaseState.BLOCKED, CaseState.HUMAN_REVIEW},
    CaseState.VERIFIED: {CaseState.ACTION_READY, CaseState.NO_ACTION, CaseState.HUMAN_REVIEW, CaseState.ABSTAIN},
    CaseState.BLOCKED: {CaseState.NO_ACTION, CaseState.HUMAN_REVIEW},
    CaseState.ACTION_READY: {CaseState.EXECUTING},
    CaseState.EXECUTING: {CaseState.LINK_ISSUED, CaseState.RETRY_SCHEDULED, CaseState.NUDGE_DRAFTED, CaseState.ABSTAIN},
    CaseState.LINK_ISSUED: {CaseState.RECOVERED, CaseState.NOT_RECOVERED, CaseState.EXPIRED, CaseState.CANCELLED},
    CaseState.RETRY_SCHEDULED: {CaseState.RECOVERED, CaseState.NOT_RECOVERED, CaseState.CANCELLED},
    CaseState.NUDGE_DRAFTED: {CaseState.RECOVERED, CaseState.NOT_RECOVERED, CaseState.EXPIRED, CaseState.CANCELLED},
    CaseState.RECOVERED: {CaseState.EVALUATED},
    CaseState.NOT_RECOVERED: {CaseState.EVALUATED},
    CaseState.EXPIRED: {CaseState.RECOVERED, CaseState.EVALUATED},
    CaseState.CANCELLED: {CaseState.RECOVERED, CaseState.EVALUATED},
}

TERMINAL_PRECEDENCE = {
    CaseState.CANCELLED: 1,
    CaseState.EXPIRED: 2,
    CaseState.NOT_RECOVERED: 3,
    CaseState.RECOVERED: 4,
    CaseState.EVALUATED: 5,
}


class InvalidTransition(ValueError):
    pass


def require_transition(current: CaseState, target: CaseState) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"invalid case transition: {current} -> {target}")


def reduce_terminal(current: CaseState, incoming: CaseState) -> CaseState:
    if current not in TERMINAL_PRECEDENCE:
        return incoming
    if incoming not in TERMINAL_PRECEDENCE:
        return current
    return incoming if TERMINAL_PRECEDENCE[incoming] > TERMINAL_PRECEDENCE[current] else current

