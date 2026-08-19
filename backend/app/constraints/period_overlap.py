"""開講期間が実際に重なるかを判定する。全制約が共通で使う。

仕様書 §5.4 の表がこの判定の唯一の定義である。

判定の土台は `active_quarters`、つまり「その科目が実際に走っている
クオーターの集合」である。2 つの期間が重なるかは、この集合が交わるか
どうかで決まる。集合を直接必要とする制約もある（H7 は 3 科目以上を
同時に見るため、互いに重ならない後①と後②を一緒に数えてはいけない）。
"""
from app.models.enums import Quarter, Term

_SPRING = frozenset({Quarter.Q1, Quarter.Q2})
_FALL = frozenset({Quarter.Q3, Quarter.Q4})
_ALL = _SPRING | _FALL


def active_quarters(term: Term, quarter: Quarter | None) -> frozenset[Quarter]:
    """その開講期間が実際に走っているクオーターの集合を返す。

    クオーター指定がなければ学期全体、つまりその学期の 2 つの
    クオーターを占める。通年は 4 つすべてを占める。
    """
    if term is Term.FULL_YEAR:
        return _ALL
    if quarter is not None:
        return frozenset({quarter})
    return _SPRING if term is Term.SPRING else _FALL


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
    return bool(
        active_quarters(term_a, quarter_a) & active_quarters(term_b, quarter_b)
    )
