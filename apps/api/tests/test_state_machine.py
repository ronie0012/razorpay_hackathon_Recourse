import pytest

from recourse.domain.models import CaseState
from recourse.domain.state_machine import InvalidTransition, reduce_terminal, require_transition


def test_valid_and_invalid_transitions():
    require_transition(CaseState.INGESTED, CaseState.NORMALIZED)
    with pytest.raises(InvalidTransition):
        require_transition(CaseState.NORMALIZED, CaseState.LINK_ISSUED)


def test_terminal_precedence_prevents_regression():
    assert reduce_terminal(CaseState.RECOVERED, CaseState.EXPIRED) == CaseState.RECOVERED
    assert reduce_terminal(CaseState.EXPIRED, CaseState.RECOVERED) == CaseState.RECOVERED

