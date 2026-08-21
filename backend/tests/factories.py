"""テスト用の Subject を組み立てる。

同じ寄せ集めの dict が 8 つのテストファイルに写し取られており、
`Subject` にフィールドが増えるたびに 8 箇所を直すことになっていた。
実際この 1 か月で pair_id・adjacent_id・is_remote_prohibited の
3 回起きている。既定値をここに 1 つ置く。

学科や年次を変えたいときは、テスト側でそのままキーワードを足せばよい。
"""
from app.models.enums import Category, Department, Term
from app.models.subject import Subject


def subject(code: str, **overrides) -> Subject:
    """既定は「経営 1 年・前期・必修・教員甲」の単コマ科目。"""
    fields = dict(
        name=code,
        base_name=code,
        department=Department.MANAGEMENT,
        year=1,
        term=Term.SPRING,
        quarter=None,
        category=Category.REQUIRED,
        teacher="教員甲",
    )
    fields.update(overrides)
    return Subject(code=code, **fields)


def subject_with_own_teacher(code: str, **overrides) -> Subject:
    """科目ごとに別の教員を持たせる。H1 を避けて配置だけを見たいとき用。"""
    return subject(code, **{"teacher": f"教員{code}", **overrides})
