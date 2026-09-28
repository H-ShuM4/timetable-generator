import tempfile
import time
from urllib.parse import quote


from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _upload_small(monkeypatch):
    """実データは大きいので、少数の科目を直接セッションに入れる。"""
    from app.models.enums import Category, Department, Term
    from app.models.subject import Subject
    from app.session_store import SessionData, store

    subjects = [
        Subject(
            code=f"A{i}", name=f"科目{i}", base_name=f"科目{i}",
            department=Department.MANAGEMENT, year=1, term=Term.SPRING, quarter=None,
            category=Category.REQUIRED, teacher=f"教員{i}",
        )
        for i in range(4)
    ]
    return store.create(SessionData(subjects=subjects, teachers={}))


def _wait_for_completion(session_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/result/{session_id}")
        if response.status_code == 200 and response.json()["status"] == "done":
            return response.json()
        time.sleep(0.1)
    raise AssertionError("生成が完了しませんでした")


def test_generate_in_mock_mode_completes(monkeypatch):
    session_id = _upload_small(monkeypatch)
    response = client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    assert response.status_code == 202

    body = _wait_for_completion(session_id)
    assert len(body["placements"]) == 4
    assert body["violations"] == []


def test_generate_returns_404_for_unknown_session():
    response = client.post("/api/generate/does-not-exist", json={"mode": "mock"})
    assert response.status_code == 404


def test_optimize_falls_back_to_mock_without_api_key(monkeypatch, tmp_path):
    import app.api.generate as generate_api
    from app.settings_store import SettingsStore

    monkeypatch.setattr(
        generate_api, "settings_store",
        SettingsStore(tmp_path / ".env", tmp_path / "settings.json"),
    )
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "optimize"})

    body = _wait_for_completion(session_id)
    assert len(body["placements"]) == 4
    assert all(p["source"] == "solver" for p in body["placements"])


def test_stream_delivers_log_events(monkeypatch):
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})

    with client.stream("GET", f"/api/generate/{session_id}/stream") as stream:
        text = "".join(chunk for chunk in stream.iter_text())
    assert "Stage 0" in text
    assert "event: done" in text


def test_export_returns_xlsx(monkeypatch):
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    _wait_for_completion(session_id)

    response = client.get(f"/api/export/{session_id}")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # xlsx は zip 形式


def test_export_uses_the_name_the_office_typed(monkeypatch):
    """打った名前が、ブラウザが保存に使う名前になる。"""
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    _wait_for_completion(session_id)

    response = client.get(f"/api/export/{session_id}", params={"name": "2026時間割"})
    assert response.status_code == 200
    # 非 ASCII は filename*=utf-8'' で百分率符号化されて載る
    disposition = response.headers["content-disposition"]
    assert quote("2026時間割.xlsx") in disposition


def test_export_without_a_name_falls_back(monkeypatch):
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    _wait_for_completion(session_id)

    response = client.get(f"/api/export/{session_id}")
    assert quote("時間割.xlsx") in response.headers["content-disposition"]


def test_a_name_cannot_break_the_header(monkeypatch):
    """改行や引用符を混ぜても、ヘッダが 2 行に割れない。"""
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    _wait_for_completion(session_id)

    response = client.get(f"/api/export/{session_id}",
                          params={"name": '時間割"\r\nX-Injected: yes'})
    assert response.status_code == 200
    assert "x-injected" not in response.headers
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition


def test_export_leaves_no_temporary_directory_behind(monkeypatch, tmp_path):
    """出力のたびに mkdtemp したままだと、書き出すほどゴミが増える。"""
    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})
    _wait_for_completion(session_id)

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert client.get(f"/api/export/{session_id}").status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_export_before_generation_returns_409(monkeypatch):
    session_id = _upload_small(monkeypatch)
    assert client.get(f"/api/export/{session_id}").status_code == 409


def test_the_mode_identifiers_stay_stable_when_labels_change():
    """画面の呼び名（AI モード）と API の識別子（optimize）は別物。

    識別子は API・設定・保存データを跨ぐので、表示名を変えても動かさない。
    """
    from app.scheduler.pipeline import GenerationMode

    assert [m.value for m in GenerationMode] == ["mock", "optimize", "inherit"]
    assert GenerationMode.OPTIMIZE.label == "AI モード"


def test_cancel_without_a_running_generation_returns_409(monkeypatch):
    session_id = _upload_small(monkeypatch)
    response = client.post(f"/api/generate/{session_id}/cancel")
    assert response.status_code == 409


def test_cancel_for_an_unknown_session_returns_404():
    assert client.post("/api/generate/nope/cancel").status_code == 404


def test_a_cancelled_run_is_not_reported_as_a_failure(real_context):
    """中止は事務局が自分で止めたもの。原因を探すメッセージは出さない。

    実データを使うのは、中止を挟める長さの生成が要るため。ソルバーは
    反復ごとに中止を見るので、押せばすぐ止まる。むしろ完走より速い。
    """
    from app.session_store import SessionData, store

    session_id = store.create(SessionData(
        subjects=list(real_context.subjects.values()),
        teachers=dict(real_context.teachers),
    ))
    assert client.post(f"/api/generate/{session_id}", json={"mode": "mock"}).status_code == 202
    assert client.post(f"/api/generate/{session_id}/cancel").status_code == 202

    deadline = time.time() + 60
    while time.time() < deadline:
        body = client.get(f"/api/result/{session_id}").json()
        if body["status"] not in ("running", "pending"):
            break
        time.sleep(0.05)

    assert body["status"] == "cancelled"
    assert body["error"] is None
    assert body["placements"] == [], "中止したら結果は残さない"


from app.scheduler.inherit import PreviousEntry  # noqa: E402


def _inherit_session(monkeypatch):
    """前年度の配置を持つ小さなセッション。"""
    from app.models.enums import Category, Department, Term
    from app.models.subject import Subject
    from app.models.timeslot import TimeSlot
    from app.session_store import SessionData, store

    subjects = [
        Subject(
            code=f"A{i}", name=f"科目{i}", base_name=f"科目{i}",
            department=Department.MANAGEMENT, year=1, term=Term.SPRING, quarter=None,
            category=Category.REQUIRED, teacher=f"専任{i}",
        )
        for i in range(3)
    ]
    previous = {
        f"A{i}": PreviousEntry((TimeSlot("木", i + 1),), f"専任{i}") for i in range(3)
    }
    return store.create(SessionData(
        subjects=subjects, teachers={}, previous_entries=previous,
    ))


def test_inherit_still_inherits_without_an_api_key(monkeypatch, tmp_path):
    """踏襲モードは Gemini を要らない。API キーが無いだけで捨てない。

    実データで起きた：キー未設定のまま踏襲モードを選ぶと、モックへ落とされて
    inherit_plan が組まれず、1 件も引き継がれないまま普通の生成になっていた。
    ログには「モックモードで実行します」としか出ないので気づけない。
    """
    import app.api.generate as generate_api
    from app.settings_store import SettingsStore

    monkeypatch.setattr(
        generate_api, "settings_store",
        SettingsStore(tmp_path / ".env", tmp_path / "settings.json"),
    )
    session_id = _inherit_session(monkeypatch)
    response = client.post(
        f"/api/generate/{session_id}", json={"mode": "inherit", "retarget_codes": []}
    )
    assert response.status_code == 202
    assert response.json()["mode"] == "inherit", "踏襲モードのまま走ること"

    body = _wait_for_completion(session_id)
    sources = {p["code"]: p["source"] for p in body["placements"]}
    assert sources == {"A0": "inherited", "A1": "inherited", "A2": "inherited"}


def _inherit_session_with_a_part_timer(monkeypatch):
    """自動検出が 1 件を組み替え対象にするセッション。

    A0 の担当を非常勤にしておく。こうしないと自動検出も空になり、
    「すべて解除」との違いが観測できない。
    """
    from app.models.enums import TeacherKind
    from app.models.teacher import Teacher
    from app.models.timeslot import TimeSlot
    from app.session_store import store

    session_id = _inherit_session(monkeypatch)
    data = store.get(session_id)
    data.subjects[0].teacher = "非常勤甲"
    data.teachers["非常勤甲"] = Teacher(
        "非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("木", 1)}
    )
    data.previous_entries["A0"] = PreviousEntry((TimeSlot("木", 1),), "非常勤甲")
    return session_id


def test_clearing_every_retarget_box_inherits_everything(monkeypatch, tmp_path):
    """「すべて解除」したら、何も組み替えずに前年度どおりにする。

    以前は空リストが falsy だったため自動検出へ戻り、外したはずの科目が
    まとめて組み替え対象へ復活していた。実データでは 189 件全部が戻る。
    """
    import app.api.generate as generate_api
    from app.settings_store import SettingsStore

    monkeypatch.setattr(
        generate_api, "settings_store",
        SettingsStore(tmp_path / ".env", tmp_path / "settings.json"),
    )
    session_id = _inherit_session_with_a_part_timer(monkeypatch)
    client.post(f"/api/generate/{session_id}",
                json={"mode": "inherit", "retarget_codes": []})

    body = _wait_for_completion(session_id)
    # 「組み替えられていない」の実質はコマ。非常勤は Stage 1 で確定するので
    # 配置元は prelock になるが、コマは前年度のままでなければならない。
    assert _slots_of(body) == {"A0": ["木1"], "A1": ["木2"], "A2": ["木3"]}


def test_omitting_the_retarget_list_falls_back_to_auto_detection(monkeypatch, tmp_path):
    """指定しなかった場合は従来どおり自動検出する。

    空リスト（すべて解除）と、指定なしを区別する必要がある。
    """
    import app.api.generate as generate_api
    from app.settings_store import SettingsStore

    monkeypatch.setattr(
        generate_api, "settings_store",
        SettingsStore(tmp_path / ".env", tmp_path / "settings.json"),
    )
    session_id = _inherit_session_with_a_part_timer(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "inherit"})

    body = _wait_for_completion(session_id)
    sources = {p["code"]: p["source"] for p in body["placements"]}
    assert sources["A0"] != "inherited", "自動検出では非常勤が組み替え対象になる"
    assert sources["A1"] == "inherited"


def _slots_of(body):
    return {p["code"]: p["slots"] for p in body["placements"]}


def _with_api_key(monkeypatch, tmp_path):
    """API キーが設定されている状態を作る。"""
    import app.api.generate as generate_api
    from app.settings_store import SettingsStore

    store = SettingsStore(tmp_path / ".env", tmp_path / "settings.json")
    store.set_api_key("AIzaTESTKEY")
    monkeypatch.setattr(generate_api, "settings_store", store)


def test_inherit_uses_the_solver_unless_the_office_asks_for_ai(monkeypatch, tmp_path):
    """踏襲モードで組み替えを誰にやらせるかは、事務局が決める。

    キーがあるだけで Gemini に渡ると、数十分と無料枠を黙って使う。
    前年度をなぞるのが目的なので、既定はソルバー。
    """
    import app.api.generate as generate_api

    _with_api_key(monkeypatch, tmp_path)
    built = []
    monkeypatch.setattr(generate_api, "make_gemini_placer",
                        lambda *a, **k: built.append(True) or (lambda *x: []))

    session_id = _inherit_session(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "inherit"})
    _wait_for_completion(session_id)

    assert built == [], "頼んでいないのに Gemini を組み立てている"


def test_inherit_hands_the_retargets_to_ai_when_asked(monkeypatch, tmp_path):
    import app.api.generate as generate_api

    _with_api_key(monkeypatch, tmp_path)
    built = []
    monkeypatch.setattr(generate_api, "make_gemini_placer",
                        lambda *a, **k: built.append(True) or (lambda *x: []))

    session_id = _inherit_session(monkeypatch)
    client.post(f"/api/generate/{session_id}",
                json={"mode": "inherit", "retarget_with": "ai"})
    _wait_for_completion(session_id)

    assert built == [True], "AI を頼んだのに使われていない"


def test_ai_mode_always_uses_ai(monkeypatch, tmp_path):
    """AI モードの意味は変えない。retarget_with は踏襲モードだけの設定。"""
    import app.api.generate as generate_api

    _with_api_key(monkeypatch, tmp_path)
    built = []
    monkeypatch.setattr(generate_api, "make_gemini_placer",
                        lambda *a, **k: built.append(True) or (lambda *x: []))

    session_id = _upload_small(monkeypatch)
    client.post(f"/api/generate/{session_id}", json={"mode": "optimize"})
    _wait_for_completion(session_id)

    assert built == [True]
