"""複数モデルのフェイルオーバー。無料枠は 1 モデル 1 日 20 リクエスト。"""
import pytest

from app.gemini.client import (
    GeminiError,
    QuotaExceededError,
    RotatingGeminiClient,
    is_quota_error,
)


class FakeClient:
    """呼ばれた回数を数え、指定回数だけ枠切れを返す偽クライアント。"""

    def __init__(self, model, failures=0, error=None):
        self.model = model
        self.calls = 0
        self._failures = failures
        self._error = error or QuotaExceededError("429 RESOURCE_EXHAUSTED")

    def generate(self, prompt):
        self.calls += 1
        if self.calls <= self._failures:
            raise self._error
        return f"{self.model}:{prompt}"


def make_factory(**failures):
    created = {}

    def factory(model):
        created[model] = FakeClient(model, failures.get(model, 0))
        return created[model]

    return factory, created


def test_uses_only_the_first_model_while_it_works():
    factory, created = make_factory()
    client = RotatingGeminiClient(factory, ["m1", "m2", "m3"])
    assert client.generate("p") == "m1:p"
    assert client.generate("p") == "m1:p"
    assert list(created) == ["m1"]
    assert client.current_model == "m1"


def test_switches_to_the_next_model_when_quota_runs_out():
    factory, created = make_factory(m1=1)
    client = RotatingGeminiClient(factory, ["m1", "m2"])
    assert client.generate("p") == "m2:p"
    assert client.current_model == "m2"
    # 同じプロンプトが次のモデルへ再送される
    assert created["m1"].calls == 1
    assert created["m2"].calls == 1


def test_an_exhausted_model_is_never_used_again():
    factory, created = make_factory(m1=1)
    client = RotatingGeminiClient(factory, ["m1", "m2"])
    client.generate("a")
    client.generate("b")
    assert created["m1"].calls == 1
    assert created["m2"].calls == 2


def test_switch_callback_reports_the_exhausted_and_next_model():
    factory, _ = make_factory(m1=1)
    switches = []
    client = RotatingGeminiClient(factory, ["m1", "m2"], on_switch=lambda a, b: switches.append((a, b)))
    client.generate("p")
    assert switches == [("m1", "m2")]


def test_non_quota_errors_do_not_switch_models():
    """一時的な失敗は上位の再試行で解決しうる。モデルの枠を無駄にしない。"""
    def factory(model):
        return FakeClient(model, failures=1, error=GeminiError("空の応答が返りました"))

    client = RotatingGeminiClient(factory, ["m1", "m2"])
    with pytest.raises(GeminiError) as caught:
        client.generate("p")
    assert not isinstance(caught.value, QuotaExceededError)
    assert client.current_model == "m1"


def test_all_models_exhausted_raises_gemini_error():
    factory, _ = make_factory(m1=1, m2=1)
    client = RotatingGeminiClient(factory, ["m1", "m2"])
    with pytest.raises(GeminiError, match="全 2 モデルが利用枠に達しました"):
        client.generate("p")
    assert client.current_model is None


def test_empty_model_list_is_rejected():
    with pytest.raises(ValueError):
        RotatingGeminiClient(lambda model: None, [])


@pytest.mark.parametrize("message", [
    "429 RESOURCE_EXHAUSTED",
    "You exceeded your current quota",
    "Rate limit exceeded",
])
def test_is_quota_error_recognises_quota_messages(message):
    assert is_quota_error(Exception(message))


def test_is_quota_error_recognises_status_code():
    error = Exception("something")
    error.code = 429
    assert is_quota_error(error)


def test_is_quota_error_ignores_unrelated_failures():
    assert not is_quota_error(Exception("connection reset by peer"))


def test_placer_finishes_a_chunk_after_switching_models(tmp_path):
    """枠切れで切り替えた後も同じチャンクの配置が続く（結合確認）。"""
    import json

    from app.constraints.context import Context
    from app.logging.session_logger import SessionLogger
    from app.models.enums import Category, Department, Term
    from app.models.subject import Subject
    from app.models.timetable import Timetable
    from app.scheduler.gemini_stage import make_gemini_placer

    subject = Subject(
        code="A1", name="A1", base_name="A1", department=Department.MANAGEMENT,
        year=1, term=Term.SPRING, quarter=None, category=Category.REQUIRED,
        teacher="教員甲",
    )
    context = Context.from_lists([subject], [])

    class Model:
        def __init__(self, model):
            self.model = model

        def generate(self, prompt):
            if self.model == "m1":
                raise QuotaExceededError("429 RESOURCE_EXHAUSTED")
            return json.dumps({"placements": [{"code": "A1", "slots": ["月1"]}]})

    switches = []
    client = RotatingGeminiClient(Model, ["m1", "m2"], on_switch=lambda a, b: switches.append(a))
    logger = SessionLogger("rotation", log_dir=tmp_path)
    timetable = Timetable()

    assert make_gemini_placer(client, 3)(context, timetable, ["A1"], logger) == []
    assert timetable.is_placed("A1")
    assert switches == ["m1"]
    # どのモデルが処理したかログに残る
    assert any("m2" in line for line in logger.log_path.read_text(encoding="utf-8").splitlines())
