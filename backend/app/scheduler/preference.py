"""配置の「好み」。制約ではない。

ソルバーと Gemini プロンプトの両方がここを使う。片方だけが好みを
知っている状態にすると、モックモードと最適化モードで時間割の性格が
変わってしまう。実際、1〜4 限への集約はソルバーにしか入っておらず、
最適化モードでは効いていなかった。
"""
from app.constraints.context import Context
from app.models.enums import Department
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable


LATE_PERIOD = 5
"""できれば避けたい時限。"""

DIFFERENT_DAY_DISTANCE = 10
"""隣接させたい相手と曜日が違う場合の距離。

時限差の最大は 4 なので、同じ曜日であればどれだけ離れていても
別の曜日より望ましい、という順序になる。
"""

PREFER_EARLY_PERIODS = (
    Department.MANAGEMENT,
    Department.ACCOUNTING,
    Department.JUNIOR,
)
"""1〜4 限への集約を優先する学科。

もともとの要望は大学（経営・会計）についてであった。大学には通常の
カリキュラムに加えて教職課程の科目があり、それらは 4 限・5 限に置かれる
ことが多いため、通常科目を 1〜4 限に寄せておくと競合しにくい。

短期大学部も対象に含めているのは、大学だけを対象にすると大学が空けた
5 限へ短大が押し出されるためである。実データでは短大の 5 限が 15.8% から
45.2% に跳ね上がった。全学科を対象にすると 経営 0.8%・会計 0.9%・
短大 3.4% となり、未配置数も変わらない。短大を除外したい場合はこの
タプルから外すだけでよい。
"""


def _adjacency_distance(
    context: Context | None,
    timetable: Timetable,
    subject: Subject,
    slots: tuple[TimeSlot, ...],
) -> int:
    """隣接させたい相手からどれだけ離れているか。小さいほど望ましい。

    課題研究（3 年）と卒業研究（4 年）を同じゼミ内で隣り合う時限に置く
    ための指標である。ゼミ内で 3 年生と 4 年生が交流できるようにという
    運用上の狙いがある。

    同じ曜日で 1 時限違いなら 0。同じ曜日で離れていればその差、別の
    曜日なら一律に大きな値を返す。相手がまだ置かれていない場合や
    `adjacent_id` を持たない場合は 0 を返し、順位に影響させない。

    H1 により同一教員は同じコマに置けないので、両者が重なることはない。
    """
    if context is None or not subject.adjacent_id:
        return 0

    best = None
    for code, other in context.subjects.items():
        if code == subject.code or other.adjacent_id != subject.adjacent_id:
            continue
        for placed in timetable.slot_of(code):
            for slot in slots:
                distance = (
                    abs(placed.period - slot.period)
                    if placed.day == slot.day
                    else DIFFERENT_DAY_DISTANCE
                )
                best = distance if best is None else min(best, distance)
    return 0 if best is None else best


def placement_preference(
    timetable: Timetable,
    subject: Subject,
    slots: tuple[TimeSlot, ...],
    context: Context | None = None,
) -> tuple:
    """候補コマ集合の望ましさ。小さいほど望ましい。

    これは制約ではなく好みである。5 限しか空いていなければ 5 限に置く。
    配置可能なものを拒否することは一切しない。

    順に、(1) 避けたい時限を使う数、(2) 隣接させたい相手からの距離、
    (3) 既に置かれている科目の数、(4) 曜日・時限。(4) は同点時の
    決定性のためだけにある。

    (3) が要る理由：候補は 月1→月2→…→金5 の順に並んでいるため単純に
    先頭を採ると月曜から順に埋まる。実データでは月 162・火 171 に対して
    木 6 という偏りが出た。偏りは見た目だけの問題ではなく、同じ曜日に
    科目が集中することで教員重複や必修衝突を生み、水・木が空いているのに
    置けない科目を作る。

    1〜4 限への集約を隣接より優先するのは、5 限を避けるほうが全学の
    時間割に効くのに対し、隣接はゼミ内の都合にとどまるためである。
    """
    late = 0
    if subject.department in PREFER_EARLY_PERIODS:
        late = sum(1 for slot in slots if slot.period == LATE_PERIOD)
    return (
        late,
        _adjacency_distance(context, timetable, subject, slots),
        sum(len(timetable.occupied_by(slot)) for slot in slots),
        tuple((slot.day, slot.period) for slot in slots),
    )


def best_option(
    timetable: Timetable,
    subject: Subject,
    options: list[tuple[TimeSlot, ...]],
    context: Context | None = None,
) -> tuple[TimeSlot, ...]:
    """候補のうち最も望ましいコマ集合を返す。"""
    return min(
        options,
        key=lambda slots: placement_preference(timetable, subject, slots, context),
    )
