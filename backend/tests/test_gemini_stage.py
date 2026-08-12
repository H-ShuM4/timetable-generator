import json

from app.constraints.context import Context
from app.gemini.client import GeminiError
from app.logging.session_logger import SessionLogger
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.gemini_stage import chunk_codes, make_gemini_placer


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher=f"教員{code}",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


class ScriptedClient:
    """あらかじめ決めた応答を順に返すテスト用クライアント。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if not self.responses:
            raise GeminiError("応答が尽きました")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def response(**code_to_labels):
    return json.dumps({
        "placements": [
            {"code": code, "slots": list(labels)}
            for code, labels in code_to_labels.items()
        ]
    })


def test_chunk_codes_groups_by_department_and_term():
    subjects = [
        make("A1", department=Department.MANAGEMENT, term=Term.SPRING),
        make("A2", department=Department.MANAGEMENT, term=Term.SPRING),
        make("A3", department=Department.MANAGEMENT, term=Term.FALL),
        make("A4", department=Department.ACCOUNTING, term=Term.SPRING),
    ]
    ctx = Context.from_lists(subjects, [])
    chunks = chunk_codes(ctx, [s.code for s in subjects])
    assert len(chunks) == 3
    assert sorted(chunks[0][1]) == ["A1", "A2"]


def test_chunk_codes_splits_by_year():
    # H2/H3 は 学科 × 年次 で衝突を判定するので、年次が違えば別チャンク
    subjects = [
        make("A1", year=1),
        make("A2", year=1),
        make("A3", year=2),
    ]
    ctx = Context.from_lists(subjects, [])
    chunks = chunk_codes(ctx, [s.code for s in subjects])
    assert len(chunks) == 2
    by_size = sorted(chunks, key=lambda c: -len(c[1]))
    assert sorted(by_size[0][1]) == ["A1", "A2"]
    assert "1年" in by_size[0][0]


def test_chunk_codes_splits_elective_required_by_course():
    subjects = [
        make("S1", category=Category.ELECTIVE_REQUIRED, courses=["情報コース"]),
        make("S2", category=Category.ELECTIVE_REQUIRED, courses=["経営コース"]),
    ]
    ctx = Context.from_lists(subjects, [])
    assert len(chunk_codes(ctx, ["S1", "S2"])) == 2


def test_placer_places_valid_response(tmp_path):
    subjects = [make("A1"), make("A2")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    client = ScriptedClient([response(A1=["月1"], A2=["火2"])])
    logger = SessionLogger("g1", log_dir=tmp_path)

    placer = make_gemini_placer(client, max_retries=3)
    failed = placer(ctx, tt, ["A1", "A2"], logger)

    assert failed == []
    assert tt.slot_of("A1") == (TimeSlot("月", 1),)
    assert tt.assignments["A1"].source is AssignmentSource.GEMINI
    logger.close()


def test_placer_retries_only_the_violating_subject(tmp_path):
    subjects = [make("A1"), make("A2")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    # 1 回目: A2 が A1 と同じコマで H2 違反。2 回目で A2 だけ直す
    client = ScriptedClient([
        response(A1=["月1"], A2=["月1"]),
        response(A2=["火1"]),
    ])
    logger = SessionLogger("g2", log_dir=tmp_path)

    failed = make_gemini_placer(client, max_retries=3)(ctx, tt, ["A1", "A2"], logger)

    assert failed == []
    assert tt.slot_of("A1") == (TimeSlot("月", 1),)
    assert tt.slot_of("A2") == (TimeSlot("火", 1),)
    assert "A2" in client.prompts[1]
    assert "A1" not in client.prompts[1].split("## 配置対象")[1].split("##")[0]
    logger.close()


def test_placer_returns_unplaced_after_exhausting_retries(tmp_path):
    subjects = [make("A1"), make("A2")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    client = ScriptedClient([
        response(A1=["月1"], A2=["月1"]),
        response(A2=["月1"]),
    ])
    logger = SessionLogger("g3", log_dir=tmp_path)

    failed = make_gemini_placer(client, max_retries=2)(ctx, tt, ["A1", "A2"], logger)

    assert failed == ["A2"]
    assert not tt.is_placed("A2")
    logger.close()


def test_placer_survives_api_error(tmp_path):
    subjects = [make("A1")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    client = ScriptedClient([GeminiError("レート制限"), response(A1=["月1"])])
    logger = SessionLogger("g4", log_dir=tmp_path)

    failed = make_gemini_placer(client, max_retries=3)(ctx, tt, ["A1"], logger)

    assert failed == []
    assert any(e.level == "WARN" and "レート制限" in e.message for e in logger.events)
    logger.close()


def test_placer_survives_broken_json(tmp_path):
    subjects = [make("A1")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    client = ScriptedClient(["これは JSON ではない", response(A1=["月1"])])
    logger = SessionLogger("g5", log_dir=tmp_path)

    failed = make_gemini_placer(client, max_retries=3)(ctx, tt, ["A1"], logger)

    assert failed == []
    assert tt.is_placed("A1")
    logger.close()


def test_placer_survives_an_unexpected_exception(tmp_path):
    # 差し替え可能なクライアントが別種の例外を投げても生成全体を止めない
    subjects = [make("A1")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    client = ScriptedClient([RuntimeError("想定外"), response(A1=["月1"])])
    logger = SessionLogger("g7", log_dir=tmp_path)

    failed = make_gemini_placer(client, max_retries=3)(ctx, tt, ["A1"], logger)

    assert failed == []
    assert tt.is_placed("A1")
    assert any(e.level == "ERROR" for e in logger.events)
    logger.close()


def test_placer_ignores_codes_not_in_the_request(tmp_path):
    subjects = [make("A1")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    client = ScriptedClient([response(A1=["月1"], Z9=["火1"])])
    logger = SessionLogger("g6", log_dir=tmp_path)

    make_gemini_placer(client, max_retries=2)(ctx, tt, ["A1"], logger)
    assert tt.placed_codes() == {"A1"}
    logger.close()
