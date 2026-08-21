"""同じ曜日・時限に置かれなければならない科目のまとまり。

2 種類の結び付きがあり、どちらも「同一コマ」を要求する。

- `joint_id`（H4）：経営側と会計側に分かれた 1 つの合同授業
- `pair_id`（H12）：同じ教員が前期と後期に続けて持つ対応科目

両方を持つ科目があるため**推移的に**たどる必要がある。日本語リテラシー
Ⅱ【再】（経営）は会計側と合同であり、かつ前期のⅠ【再】と対応するので、
1 つのまとまりは 4 科目になる。

ソルバーと手動移動の両方がここを使う。片方だけが結び付きを知っている
状態にすると、ソルバーが後で詰む配置を選んでしまう。
"""
from app.constraints.context import Context
from app.models.subject import Subject

LINK_ATTRIBUTES = ("joint_id", "pair_id")


def linked_group(context: Context, subject: Subject) -> list[str]:
    """subject と同じコマに置かれるべき科目コードの一覧（subject を含む）。"""
    by_key: dict[tuple[str, str], list[str]] = {}
    for code, other in context.subjects.items():
        for attribute in LINK_ATTRIBUTES:
            value = getattr(other, attribute)
            if value:
                by_key.setdefault((attribute, value), []).append(code)

    group = {subject.code}
    queue = [subject.code]
    while queue:
        current = context.subjects[queue.pop()]
        for attribute in LINK_ATTRIBUTES:
            value = getattr(current, attribute)
            if not value:
                continue
            for code in by_key.get((attribute, value), ()):
                if code not in group:
                    group.add(code)
                    queue.append(code)
    return sorted(group)
