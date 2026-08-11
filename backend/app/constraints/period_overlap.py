"""開講期間が実際に重なるかを判定する。全制約が共通で使う。

仕様書 §5.4 の表がこの関数の唯一の定義である。
"""
from app.models.enums import Quarter, Term

_EXCLUSIVE_PAIRS: frozenset[frozenset[Quarter]] = frozenset({
    frozenset({Quarter.Q1, Quarter.Q2}),
    frozenset({Quarter.Q3, Quarter.Q4}),
})


def periods_overlap(
    term_a: Term,
    quarter_a: Quarter | None,
    term_b: Term,
    quarter_b: Quarter | None,
) -> bool:
    """2 つの開講期間が時間的に重なるなら True。

    前期と後期は常に重ならない。同一学期内では、前①と前②、
    後①と後②のみ重ならない。クオーター指定がない側は学期全体を
    占めるため、同一学期内のどのクオーターとも重なる。
    通年は年間を通じて開講されるため、どの期間とも重なる。
    """
    if Term.FULL_YEAR in (term_a, term_b):
        return True
    if term_a != term_b:
        return False
    if quarter_a is None or quarter_b is None:
        return True
    return frozenset({quarter_a, quarter_b}) not in _EXCLUSIVE_PAIRS
