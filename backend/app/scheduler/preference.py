"""配置の「好み」。制約ではない。

ソルバーと Gemini プロンプトの両方がここを使う。片方だけが好みを
知っている状態にすると、モックモードと最適化モードで時間割の性格が
変わってしまう。実際、1〜4 限への集約はソルバーにしか入っておらず、
最適化モードでは効いていなかった。
"""
from app.models.enums import Department
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable


LATE_PERIOD = 5
"""できれば避けたい時限。"""

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


def placement_preference(
    timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> tuple:
    """候補コマ集合の望ましさ。小さいほど望ましい。

    これは制約ではなく好みである。5 限しか空いていなければ 5 限に置く。
    配置可能なものを拒否することは一切しない。

    順に、(1) 避けたい時限を使う数、(2) 既に置かれている科目の数、
    (3) 曜日・時限。(3) は同点時の決定性のためだけにある。

    (2) が要る理由：候補は 月1→月2→…→金5 の順に並んでいるため単純に
    先頭を採ると月曜から順に埋まる。実データでは月 162・火 171 に対して
    木 6 という偏りが出た。偏りは見た目だけの問題ではなく、同じ曜日に
    科目が集中することで教員重複や必修衝突を生み、水・木が空いているのに
    置けない科目を作る。
    """
    late = 0
    if subject.department in PREFER_EARLY_PERIODS:
        late = sum(1 for slot in slots if slot.period == LATE_PERIOD)
    return (
        late,
        sum(len(timetable.occupied_by(slot)) for slot in slots),
        tuple((slot.day, slot.period) for slot in slots),
    )


def best_option(
    timetable: Timetable, subject: Subject, options: list[tuple[TimeSlot, ...]]
) -> tuple[TimeSlot, ...]:
    """候補のうち最も望ましいコマ集合を返す。"""
    return min(options, key=lambda slots: placement_preference(timetable, subject, slots))
