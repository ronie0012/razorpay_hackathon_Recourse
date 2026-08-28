from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from recourse.domain.models import Action
from recourse.domain.value import conservative_value, deterministic_futures, incremental_value, rounded_subunits


def test_bankers_rounding_at_subunit_boundary():
    assert rounded_subunits(Decimal("2.5")) == 2
    assert rounded_subunits(Decimal("3.5")) == 4


def test_formula_and_baseline_value():
    assert incremental_value(amount_subunits=10000, action_probability=.6, no_action_probability=.2,
                             direct_cost_subunits=100, downstream_cost_subunits=200) == 3700
    no_action = deterministic_futures(10000)[0]
    assert no_action.action == Action.NO_ACTION
    assert no_action.expected_incremental_value_subunits == 0
    assert no_action.conservative_incremental_value_subunits == 0


@given(cost=st.integers(min_value=0, max_value=1_000_000), increase=st.integers(min_value=0, max_value=1_000_000))
def test_increasing_cost_never_increases_value(cost, increase):
    lower = conservative_value(amount_subunits=50000, uplift_lower=.3,
                               direct_cost_subunits=cost, downstream_cost_subunits=0)
    higher = conservative_value(amount_subunits=50000, uplift_lower=.3,
                                direct_cost_subunits=cost + increase, downstream_cost_subunits=0)
    assert higher <= lower


@given(
    amount=st.integers(min_value=0, max_value=100_000_000),
    action_probability=st.floats(min_value=0, max_value=1, allow_nan=False),
    baseline_a=st.floats(min_value=0, max_value=1, allow_nan=False),
    baseline_b=st.floats(min_value=0, max_value=1, allow_nan=False),
)
def test_higher_baseline_cannot_increase_action_value(amount, action_probability, baseline_a, baseline_b):
    low, high = sorted((baseline_a, baseline_b))
    low_baseline_value = incremental_value(
        amount_subunits=amount, action_probability=action_probability, no_action_probability=low,
        direct_cost_subunits=0, downstream_cost_subunits=0,
    )
    high_baseline_value = incremental_value(
        amount_subunits=amount, action_probability=action_probability, no_action_probability=high,
        direct_cost_subunits=0, downstream_cost_subunits=0,
    )
    assert high_baseline_value <= low_baseline_value
