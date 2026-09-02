from app.constraints.context import Context
from app.constraints.student_rules import check_h2, check_h3
from app.models.enums import Category, Department, Quarter, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make(code, category, year=1, department=Department.MANAGEMENT, base_name=None,
         courses=None, term=Term.SPRING, quarter=None, teacher="教員甲", name=None):
    return Subject(
        code=code, name=name or code, base_name=base_name or code, department=department,
        year=year, term=term, quarter=quarter, category=category,
        courses=courses or [], teacher=teacher,
    )


def place(subjects, code, slot):
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    tt.place(code, (slot,), AssignmentSource.PRELOCK)
    return ctx, tt


def test_h2_flags_two_required_in_same_department_and_year():
    a = make("A1", Category.REQUIRED)
    b = make("B1", Category.REQUIRED)
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    violations = check_h2(ctx, tt, b, (TimeSlot("月", 1),))
    assert [v.rule_id for v in violations] == ["H2"]
    assert violations[0].related_code == "A1"


def test_h2_allows_different_year():
    a = make("A1", Category.REQUIRED, year=1)
    b = make("B1", Category.REQUIRED, year=2)
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_allows_different_department():
    a = make("A1", Category.REQUIRED, department=Department.ACCOUNTING)
    b = make("B1", Category.REQUIRED, department=Department.MANAGEMENT)
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_allows_the_same_subject_taught_by_different_teachers():
    a = make("A1", Category.REQUIRED, base_name="日本語リテラシーⅠ")
    b = make("B1", Category.REQUIRED, base_name="日本語リテラシーⅠ")
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_allows_the_same_ordinary_subject_in_two_sections():
    # 英語Ⅰ・情報リテラシーⅠ・商業簿記Ⅰ のような複数クラス開講の通常科目
    a = make("A1", Category.REQUIRED, base_name="商業簿記Ⅰ", teacher="教員甲")
    b = make("B1", Category.REQUIRED, base_name="商業簿記Ⅰ", teacher="教員乙")
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_allows_retake_section_to_share_with_the_original():
    # base_name は【再】を除いた名前なので同一科目とみなされる
    a = make("A1", Category.REQUIRED, base_name="日本語リテラシーⅠ")
    b = make("B1", Category.REQUIRED, base_name="日本語リテラシーⅠ")
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_flags_two_different_subjects():
    a = make("A1", Category.REQUIRED, base_name="日本語リテラシーⅠ")
    b = make("B1", Category.REQUIRED, base_name="プレゼミナール")
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert [v.rule_id for v in check_h2(ctx, tt, b, (TimeSlot("月", 1),))] == ["H2"]


def test_h2_flags_two_different_course_names():
    a = make("A1", Category.REQUIRED, base_name="商業簿記Ⅰ")
    b = make("B1", Category.REQUIRED, base_name="工業簿記Ⅰ")
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert [v.rule_id for v in check_h2(ctx, tt, b, (TimeSlot("月", 1),))] == ["H2"]


def test_h2_allows_non_overlapping_quarters():
    a = make("A1", Category.REQUIRED, quarter=Quarter.Q1)
    b = make("B1", Category.REQUIRED, quarter=Quarter.Q2)
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_ignores_electives():
    a = make("A1", Category.ELECTIVE)
    b = make("B1", Category.REQUIRED)
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h3_flags_shared_course():
    a = make("A1", Category.ELECTIVE_REQUIRED, courses=["情報コース"])
    b = make("B1", Category.ELECTIVE_REQUIRED, courses=["情報コース", "経営コース"])
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert [v.rule_id for v in check_h3(ctx, tt, b, (TimeSlot("月", 1),))] == ["H3"]


def test_h3_allows_disjoint_courses():
    a = make("A1", Category.ELECTIVE_REQUIRED, courses=["情報コース"])
    b = make("B1", Category.ELECTIVE_REQUIRED, courses=["観光まちづくりコース"])
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h3(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h3_skips_when_course_is_unknown():
    a = make("A1", Category.ELECTIVE_REQUIRED, courses=[])
    b = make("B1", Category.ELECTIVE_REQUIRED, courses=["情報コース"])
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h3(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h3_allows_different_year():
    a = make("A1", Category.ELECTIVE_REQUIRED, year=1, courses=["情報コース"])
    b = make("B1", Category.ELECTIVE_REQUIRED, year=2, courses=["情報コース"])
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h3(ctx, tt, b, (TimeSlot("月", 1),)) == []


# ------------------------------------------------- クラス分けと再履修クラス


def test_h2_allows_two_classes_of_the_same_subject():
    """英語Ⅰ【A】と英語Ⅰ【B】は 1 科目の複数クラス。

    学生が履修するのはそのうち一つなので、同一コマに集約してよい。
    担当教員が同じ場合は H1 が別に弾くので、ここでは見なくてよい。
    """
    placed = make("E1", Category.REQUIRED, name="英語Ⅰ【A】", base_name="英語Ⅰ【A】",
                  teacher="金沢智")
    moving = make("E2", Category.REQUIRED, name="英語Ⅰ【B】", base_name="英語Ⅰ【B】",
                  teacher="柳沢順一")
    ctx, tt = place([placed, moving], "E1", TimeSlot("月", 1))

    assert check_h2(ctx, tt, moving, (TimeSlot("月", 1),)) == []


def test_h2_still_flags_two_genuinely_different_subjects():
    """緩めすぎていないことの網。クラス記号が無ければ従来どおり衝突する。"""
    placed = make("A1", Category.REQUIRED, name="簿記論", base_name="簿記論")
    moving = make("A2", Category.REQUIRED, name="経済学入門", base_name="経済学入門",
                  teacher="教員乙")
    ctx, tt = place([placed, moving], "A1", TimeSlot("月", 1))

    assert len(check_h2(ctx, tt, moving, (TimeSlot("月", 1),))) == 1


def test_h2_lets_a_retake_class_overlap_the_year_it_is_listed_under():
    """【再】は 1 年次に落単した学生の再履修クラス。

    配当年次は 1 年でも実際に受けるのは 2 年生以降なので、その年次の
    集団には属さない。同じ年次の他の必修と被って構わない。
    """
    regular = make("R1", Category.REQUIRED, name="情報処理Ⅰ", base_name="情報処理Ⅰ")
    retake = make("R2", Category.REQUIRED, name="日本語リテラシーⅠ【再】",
                  base_name="日本語リテラシーⅠ", teacher="金弘錫")
    ctx, tt = place([regular, retake], "R1", TimeSlot("月", 1))

    assert check_h2(ctx, tt, retake, (TimeSlot("月", 1),)) == []


def test_h2_still_flags_two_different_retake_classes():
    """【再】同士は従来どおり衝突する。

    2 科目を同時に再履修する学生がいるため、重ねると片方を落とすことになる。
    """
    first = make("R1", Category.REQUIRED, name="日本語リテラシーⅠ【再】",
                 base_name="日本語リテラシーⅠ", teacher="金弘錫")
    second = make("R2", Category.REQUIRED, name="商業簿記Ⅰ【再】",
                  base_name="商業簿記Ⅰ", teacher="神山直規")
    ctx, tt = place([first, second], "R1", TimeSlot("月", 1))

    assert len(check_h2(ctx, tt, second, (TimeSlot("月", 1),))) == 1


def test_h3_allows_two_classes_of_the_same_elective_required_subject():
    """選択必修でも同じ理屈。H2 と揃えない理由が無い。"""
    placed = make("S1", Category.ELECTIVE_REQUIRED, name="ゼミ入門【A】",
                  base_name="ゼミ入門【A】", courses=["情報"])
    moving = make("S2", Category.ELECTIVE_REQUIRED, name="ゼミ入門【B】",
                  base_name="ゼミ入門【B】", courses=["情報"], teacher="教員乙")
    ctx, tt = place([placed, moving], "S1", TimeSlot("月", 1))

    assert check_h3(ctx, tt, moving, (TimeSlot("月", 1),)) == []
