import pytest

from app.constraints.period_overlap import periods_overlap
from app.models.enums import Term, Quarter

SPRING = Term.SPRING
FALL = Term.FALL


@pytest.mark.parametrize("qa,qb,expected", [
    (None, None, True),
    (None, Quarter.Q1, True),
    (Quarter.Q1, None, True),
    (Quarter.Q1, Quarter.Q1, True),
    (Quarter.Q1, Quarter.Q2, False),
    (Quarter.Q2, Quarter.Q1, False),
    (Quarter.Q2, Quarter.Q2, True),
])
def test_within_spring(qa, qb, expected):
    assert periods_overlap(SPRING, qa, SPRING, qb) is expected


@pytest.mark.parametrize("qa,qb,expected", [
    (None, None, True),
    (Quarter.Q3, Quarter.Q4, False),
    (Quarter.Q4, Quarter.Q3, False),
    (Quarter.Q3, Quarter.Q3, True),
    (None, Quarter.Q3, True),
])
def test_within_fall(qa, qb, expected):
    assert periods_overlap(FALL, qa, FALL, qb) is expected


def test_spring_and_fall_never_overlap():
    assert periods_overlap(SPRING, None, FALL, None) is False
    assert periods_overlap(SPRING, Quarter.Q1, FALL, Quarter.Q3) is False
