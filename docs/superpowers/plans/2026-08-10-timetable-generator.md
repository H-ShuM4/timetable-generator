# 大学時間割自動生成システム 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 経営学科・会計学科・短期大学部の時間割を、既存 Excel と Google Gemini を用いて自動生成し、ブラウザ上で確認・編集・Excel 出力できるシステムを構築する。

**Architecture:** FastAPI バックエンドが Excel を構造化し、制約検証器を単一の入口として持つ。配置は「事前ロック（Python）→ Gemini によるチャンク配置 → 検証 → 差し戻し再試行 → ソルバーによるフォールバック」の段階パイプラインで行う。フロントエンドは素の HTML/CSS/JS で、SSE によるログ受信とドラッグ&ドロップ編集を担う。

**Tech Stack:** Python 3.14 / FastAPI / uvicorn / openpyxl / markitdown / google-genai / pytest / 素の HTML・CSS・JavaScript

## Global Constraints

- Python は 3.14 系。仮想環境は既存の `.venv` を使う（`/home/myarm/py_venvs/Project_3/.venv`）
- 全コマンドはプロジェクトルート `/home/myarm/py_venvs/Project_3` から実行する
- Python の実行は必ず `.venv/bin/python`、pytest は `.venv/bin/pytest` を使う
- 曜日は `月 火 水 木 金` の 5 種、時限は `1〜5` の 5 種。時限 `99` は「集中」を意味しグリッド対象外
- 開講期は `前期 後期 通年`、クオーターは `前① 前② 後① 後②`。通年はどの期間とも重なる
- 学科は `経営 会計 短期大学部` の 3 種（Excel の `学科` 列の値そのまま）
- 科目区分は `必修 選択必修 選択` の 3 種
- 教員区分は `専任 特任 非常勤 不明` の 4 種
- 制約 ID は `H1`〜`H10`。仕様書 §6 の定義と番号を厳守する
- テストに Gemini API キーは不要。Gemini は必ずモックに差し替える
- コード内の識別子は英語、ユーザー向け文字列とログメッセージは日本語
- ファイルは 1 ファイル 1 責務。300 行を超えたら分割を検討する

## File Structure

| ファイル | 責務 |
|---|---|
| `backend/app/models/enums.py` | Department / Term / Quarter / Category / TeacherKind の列挙 |
| `backend/app/models/timeslot.py` | TimeSlot（曜日 × 時限）と全スロット生成 |
| `backend/app/models/subject.py` | Subject データクラス |
| `backend/app/models/teacher.py` | Teacher データクラス |
| `backend/app/models/timetable.py` | Assignment / Timetable / AssignmentSource |
| `backend/app/constraints/period_overlap.py` | 開講期間の重なり判定（仕様書 §5.4） |
| `backend/app/constraints/context.py` | 制約評価に必要な科目・教員の索引（Context / Violation） |
| `backend/app/constraints/teacher_rules.py` | H1・H5・H6・H7（教員に関する制約） |
| `backend/app/constraints/student_rules.py` | H2・H3（学生の履修衝突に関する制約） |
| `backend/app/constraints/subject_rules.py` | H4・H8・H9・H10（科目固有の制約） |
| `backend/app/constraints/validator.py` | 制約検証器の唯一の入口 |
| `backend/app/ingest/name_normalizer.py` | 氏名の空白除去・異体字正規化 |
| `backend/app/ingest/teacher_reader.py` | 教員一覧 Excel の読み取り |
| `backend/app/ingest/curriculum_reader.py` | カリキュラム一覧 Excel の読み取り |
| `backend/app/ingest/joint_pairing.py` | 合同科目のペアリング |
| `backend/app/ingest/validators.py` | Stage 0 の警告生成 |
| `backend/app/ingest/markitdown_fallback.py` | 想定外 Excel のフォールバック読み取り |
| `backend/app/scheduler/candidates.py` | 科目 1 件が取り得るコマ集合の列挙 |
| `backend/app/scheduler/prelock.py` | Stage 1（確定枠・非常勤の事前ロック） |
| `backend/app/scheduler/solver.py` | Stage 5（バックトラッキング探索） |
| `backend/app/scheduler/gemini_stage.py` | Stage 2〜4（Gemini によるチャンク配置） |
| `backend/app/scheduler/inherit.py` | 踏襲モード（前年度踏襲と組み替え対象検出） |
| `backend/app/scheduler/pipeline.py` | Stage 0〜6 のオーケストレーション |
| `backend/app/gemini/client.py` | Gemini API クライアント |
| `backend/app/gemini/prompts.py` | プロンプト生成 |
| `backend/app/gemini/retry.py` | 再試行ループ |
| `backend/app/logging/session_logger.py` | SSE とファイルへのログ出力 |
| `backend/app/export/excel_writer.py` | 時間割表マトリクスの Excel 出力 |
| `backend/app/settings_store.py` | `.env` と `settings.json` の読み書き |
| `backend/app/session_store.py` | セッション単位の読み込みデータと生成結果の保持 |
| `backend/app/api/schemas.py` | API のリクエスト・レスポンス型 |
| `backend/app/api/upload.py` | Excel アップロードと読み込みサマリ |
| `backend/app/api/generate.py` | 生成実行と SSE ログ配信 |
| `backend/app/api/result.py` | 結果の取得と手動編集（D&D） |
| `backend/app/api/settings.py` | API キー・モデル・再試行回数 |
| `backend/app/api/export.py` | Excel 出力 |
| `backend/app/main.py` | FastAPI エントリポイント |
| `frontend/index.html` | 4 画面のマークアップ |
| `frontend/css/style.css` | スタイル |
| `frontend/js/api.js` | バックエンド呼び出し |
| `frontend/js/upload.js` | アップロード画面 |
| `frontend/js/generate.js` | 生成画面 |
| `frontend/js/logviewer.js` | ログビューア（SSE 受信） |
| `frontend/js/timetable.js` | 結果画面のグリッドと D&D |
| `frontend/js/settings.js` | 設定画面 |

---

### Task 1: プロジェクト雛形と依存関係

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/app/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_smoke.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: なし
- Produces: `.venv` に FastAPI・openpyxl・pytest 等が入り、`.venv/bin/pytest backend` が実行できる状態

- [ ] **Step 1: Git リポジトリを初期化する**

```bash
cd /home/myarm/py_venvs/Project_3
git init
```

- [ ] **Step 2: `.gitignore` を作成する**

```
.venv/
__pycache__/
*.pyc
backend/.env
backend/data/sessions/
backend/logs/
.pytest_cache/
```

- [ ] **Step 3: `backend/requirements.txt` を作成する**

```
fastapi>=0.115
uvicorn[standard]>=0.32
python-multipart>=0.0.12
openpyxl>=3.1.5
markitdown>=0.0.1
google-genai>=1.0
python-dotenv>=1.0
pytest>=8.3
httpx>=0.28
```

- [ ] **Step 4: 依存関係をインストールする**

```bash
.venv/bin/pip install -r backend/requirements.txt
```

- [ ] **Step 5: `backend/pytest.ini` を作成する**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 6: 空の `__init__.py` を 2 つ作成する**

`backend/app/__init__.py` と `backend/tests/__init__.py` を空ファイルとして作成する。

- [ ] **Step 7: スモークテストを書く**

`backend/tests/test_smoke.py`:

```python
def test_imports_work():
    import fastapi
    import openpyxl
    assert fastapi is not None
    assert openpyxl is not None
```

- [ ] **Step 8: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 9: コミットする**

```bash
git add .gitignore backend/requirements.txt backend/pytest.ini backend/app/__init__.py backend/tests/__init__.py backend/tests/test_smoke.py
git commit -m "chore: プロジェクト雛形と依存関係を追加"
```

---

### Task 2: コアモデルと開講期間の重なり判定

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/enums.py`
- Create: `backend/app/models/timeslot.py`
- Create: `backend/app/constraints/__init__.py`
- Create: `backend/app/constraints/period_overlap.py`
- Test: `backend/tests/test_models.py`
- Test: `backend/tests/test_period_overlap.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `Department`, `Term`, `Quarter`, `Category`, `TeacherKind`（すべて `str` を継承した `Enum`）
  - `TimeSlot(day: str, period: int)` — frozen dataclass、`DAYS: tuple[str, ...]`、`PERIODS: tuple[int, ...]`、`all_slots() -> list[TimeSlot]`
  - `periods_overlap(term_a, quarter_a, term_b, quarter_b) -> bool`

- [ ] **Step 1: 失敗するテストを書く（モデル）**

`backend/tests/test_models.py`:

```python
from app.models.enums import Department, Term, Quarter, Category, TeacherKind
from app.models.timeslot import TimeSlot, DAYS, PERIODS, all_slots


def test_department_values_match_excel():
    assert Department("経営") is Department.MANAGEMENT
    assert Department("会計") is Department.ACCOUNTING
    assert Department("短期大学部") is Department.JUNIOR


def test_days_and_periods():
    assert DAYS == ("月", "火", "水", "木", "金")
    assert PERIODS == (1, 2, 3, 4, 5)


def test_all_slots_has_25_entries():
    slots = all_slots()
    assert len(slots) == 25
    assert slots[0] == TimeSlot("月", 1)
    assert slots[-1] == TimeSlot("金", 5)


def test_timeslot_is_hashable_and_frozen():
    s = TimeSlot("火", 3)
    assert {s: 1}[TimeSlot("火", 3)] == 1


def test_enums_cover_categories_and_kinds():
    assert Category("必修") is Category.REQUIRED
    assert Category("選択必修") is Category.ELECTIVE_REQUIRED
    assert Category("選択") is Category.ELECTIVE
    assert Term("前期") is Term.SPRING
    assert Quarter("前①") is Quarter.Q1
    assert TeacherKind("非常勤") is TeacherKind.PART_TIME
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.models'`）

- [ ] **Step 3: 列挙を実装する**

`backend/app/models/__init__.py` は空ファイル。

`backend/app/models/enums.py`:

```python
"""Excel 上の日本語表記をそのまま値に持つ列挙。"""
from enum import Enum


class Department(str, Enum):
    MANAGEMENT = "経営"
    ACCOUNTING = "会計"
    JUNIOR = "短期大学部"


class Term(str, Enum):
    SPRING = "前期"
    FALL = "後期"
    FULL_YEAR = "通年"


class Quarter(str, Enum):
    Q1 = "前①"
    Q2 = "前②"
    Q3 = "後①"
    Q4 = "後②"


class Category(str, Enum):
    REQUIRED = "必修"
    ELECTIVE_REQUIRED = "選択必修"
    ELECTIVE = "選択"


class TeacherKind(str, Enum):
    FULL_TIME = "専任"
    SPECIAL = "特任"
    PART_TIME = "非常勤"
    UNKNOWN = "不明"
```

- [ ] **Step 4: TimeSlot を実装する**

`backend/app/models/timeslot.py`:

```python
"""曜日と時限の組。時間割グリッドの座標を表す。"""
from dataclasses import dataclass

DAYS: tuple[str, ...] = ("月", "火", "水", "木", "金")
PERIODS: tuple[int, ...] = (1, 2, 3, 4, 5)

INTENSIVE_PERIOD = 99
"""集中講義を表す時限。グリッドには含めない。"""


@dataclass(frozen=True, slots=True)
class TimeSlot:
    day: str
    period: int

    def __str__(self) -> str:
        return f"{self.day}{self.period}"


def all_slots() -> list[TimeSlot]:
    """月1 から 金5 まで、曜日を外側にした 25 スロット。"""
    return [TimeSlot(day, period) for day in DAYS for period in PERIODS]
```

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_models.py -v`
Expected: PASS（6 件）

- [ ] **Step 6: 失敗するテストを書く（開講期間の重なり）**

`backend/tests/test_period_overlap.py`:

```python
import pytest

from app.constraints.period_overlap import periods_overlap
from app.models.enums import Term, Quarter

SPRING = Term.SPRING
FALL = Term.FALL


@pytest.mark.parametrize("qa,qb,expected", [
    (None, None, True),
    (None, Quarter.Q1, True),
    (Quarter.Q1, None, True),
    (Quarter.Q1, Quarter.Q1, True),
    (Quarter.Q1, Quarter.Q2, False),
    (Quarter.Q2, Quarter.Q1, False),
    (Quarter.Q2, Quarter.Q2, True),
])
def test_within_spring(qa, qb, expected):
    assert periods_overlap(SPRING, qa, SPRING, qb) is expected


@pytest.mark.parametrize("qa,qb,expected", [
    (None, None, True),
    (Quarter.Q3, Quarter.Q4, False),
    (Quarter.Q4, Quarter.Q3, False),
    (Quarter.Q3, Quarter.Q3, True),
    (None, Quarter.Q3, True),
])
def test_within_fall(qa, qb, expected):
    assert periods_overlap(FALL, qa, FALL, qb) is expected


def test_spring_and_fall_never_overlap():
    assert periods_overlap(SPRING, None, FALL, None) is False
    assert periods_overlap(SPRING, Quarter.Q1, FALL, Quarter.Q3) is False


@pytest.mark.parametrize("term,quarter", [
    (SPRING, None),
    (SPRING, Quarter.Q1),
    (SPRING, Quarter.Q2),
    (FALL, None),
    (FALL, Quarter.Q3),
    (FALL, Quarter.Q4),
    (Term.FULL_YEAR, None),
])
def test_full_year_overlaps_everything(term, quarter):
    assert periods_overlap(Term.FULL_YEAR, None, term, quarter) is True
    assert periods_overlap(term, quarter, Term.FULL_YEAR, None) is True
```

- [ ] **Step 7: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_period_overlap.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.constraints'`）

- [ ] **Step 8: 重なり判定を実装する**

`backend/app/constraints/__init__.py` は空ファイル。

`backend/app/constraints/period_overlap.py`:

```python
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

    通年は年間を通じて開講されるため、どの期間とも重なる。
    前期と後期は常に重ならない。同一学期内では、前①と前②、
    後①と後②のみ重ならない。クオーター指定がない側は学期全体を
    占めるため、同一学期内のどのクオーターとも重なる。
    """
    if Term.FULL_YEAR in (term_a, term_b):
        return True
    if term_a != term_b:
        return False
    if quarter_a is None or quarter_b is None:
        return True
    return frozenset({quarter_a, quarter_b}) not in _EXCLUSIVE_PAIRS
```

- [ ] **Step 9: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全 19 件）

- [ ] **Step 10: コミットする**

```bash
git add backend/app/models backend/app/constraints backend/tests/test_models.py backend/tests/test_period_overlap.py
git commit -m "feat: コアモデルと開講期間の重なり判定を追加"
```

---

### Task 3: Subject / Teacher / Timetable のデータクラス

**Files:**
- Create: `backend/app/models/subject.py`
- Create: `backend/app/models/teacher.py`
- Create: `backend/app/models/timetable.py`
- Test: `backend/tests/test_timetable.py`

**Interfaces:**
- Consumes: Task 2 の `Department`, `Term`, `Quarter`, `Category`, `TeacherKind`, `TimeSlot`
- Produces:
  - `Subject` — 仕様書 §5.1 の全フィールドを持つ dataclass
  - `Teacher` — 仕様書 §5.2 の全フィールドを持つ dataclass
  - `AssignmentSource` — `PRELOCK / GEMINI / SOLVER / MANUAL / INHERITED` の Enum
  - `Assignment(subject_code: str, slots: tuple[TimeSlot, ...], source: AssignmentSource)`
  - `Timetable` — `assignments: dict[str, Assignment]` を持ち、`place(...)`, `remove(code)`, `occupied_by(slot) -> list[str]`, `slot_of(code) -> tuple[TimeSlot, ...]`, `is_placed(code) -> bool`, `placed_codes() -> set[str]` を提供

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_timetable.py`:

```python
import pytest

from app.models.timeslot import TimeSlot
from app.models.timetable import Assignment, AssignmentSource, Timetable


def test_place_and_lookup():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert t.is_placed("A001")
    assert t.slot_of("A001") == (TimeSlot("月", 1),)
    assert t.occupied_by(TimeSlot("月", 1)) == ["A001"]
    assert t.placed_codes() == {"A001"}


def test_multiple_subjects_can_share_a_slot():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    t.place("B001", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    assert sorted(t.occupied_by(TimeSlot("月", 1))) == ["A001", "B001"]


def test_two_slot_subject_occupies_both():
    t = Timetable()
    t.place("J159", (TimeSlot("水", 2), TimeSlot("水", 3)), AssignmentSource.SOLVER)
    assert t.occupied_by(TimeSlot("水", 2)) == ["J159"]
    assert t.occupied_by(TimeSlot("水", 3)) == ["J159"]


def test_remove_clears_all_slots():
    t = Timetable()
    t.place("J159", (TimeSlot("水", 2), TimeSlot("水", 3)), AssignmentSource.SOLVER)
    t.remove("J159")
    assert not t.is_placed("J159")
    assert t.occupied_by(TimeSlot("水", 2)) == []


def test_placing_same_code_twice_raises():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    with pytest.raises(ValueError, match="A001"):
        t.place("A001", (TimeSlot("火", 1),), AssignmentSource.GEMINI)


def test_assignment_records_source():
    t = Timetable()
    t.place("A001", (TimeSlot("月", 1),), AssignmentSource.MANUAL)
    assert t.assignments["A001"] == Assignment(
        "A001", (TimeSlot("月", 1),), AssignmentSource.MANUAL
    )
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_timetable.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.models.timetable'`）

- [ ] **Step 3: Subject を実装する**

`backend/app/models/subject.py`:

```python
"""科目 1 件を表すデータクラス。仕様書 §5.1 に対応する。"""
from dataclasses import dataclass, field

from app.models.enums import Category, Department, Quarter, Term
from app.models.timeslot import TimeSlot


@dataclass(slots=True)
class Subject:
    code: str
    """授業コード。▲科目は 2 行が 1 件に集約されるため一意になる。"""

    name: str
    """Excel 上の科目名称（原文）。"""

    base_name: str
    """先頭の ▲、接尾辞の :会、【再】を除いた正規化名。

    ゼミ判定と合同ペアリングはこの値で行う。
    """

    department: Department
    year: int
    term: Term
    quarter: Quarter | None
    category: Category
    courses: list[str] = field(default_factory=list)
    teacher: str = ""
    is_remote: bool = False
    is_joint: bool = False
    """Excel の `合同(経・会)` 列が ○ か。ペアリング前の生のフラグ。"""

    joint_id: str | None = None
    """ペアリング成立後に付与される合同グループ ID。"""

    slots_required: int = 1
    requires_consecutive: bool = False
    fixed_slot: tuple[TimeSlot, ...] | None = None
    is_intensive: bool = False
    is_seminar: bool = False
```

- [ ] **Step 4: Teacher を実装する**

`backend/app/models/teacher.py`:

```python
"""教員 1 名を表すデータクラス。仕様書 §5.2 に対応する。"""
from dataclasses import dataclass, field

from app.models.enums import TeacherKind
from app.models.timeslot import TimeSlot


@dataclass(slots=True)
class Teacher:
    name: str
    """正規化済み氏名。"""

    kind: TeacherKind
    research_day: str | None = None
    """研究日。専任のみ設定される。"""

    available_days: set[str] = field(default_factory=set)
    """出勤可能曜日。特任のみ設定される。空集合なら制約なし。"""

    available_slots: set[TimeSlot] = field(default_factory=set)
    """出勤可能コマ。非常勤のみ設定される。空集合なら制約なし。"""
```

- [ ] **Step 5: Timetable を実装する**

`backend/app/models/timetable.py`:

```python
"""配置結果を保持する。制約検証・ソルバー・API が共有する唯一の状態。"""
from dataclasses import dataclass, field
from enum import Enum

from app.models.timeslot import TimeSlot


class AssignmentSource(str, Enum):
    """そのコマを誰が決めたか。フロントの色分けに使う。"""

    PRELOCK = "prelock"
    GEMINI = "gemini"
    SOLVER = "solver"
    MANUAL = "manual"
    INHERITED = "inherited"


@dataclass(frozen=True, slots=True)
class Assignment:
    subject_code: str
    slots: tuple[TimeSlot, ...]
    source: AssignmentSource


@dataclass(slots=True)
class Timetable:
    assignments: dict[str, Assignment] = field(default_factory=dict)
    _by_slot: dict[TimeSlot, list[str]] = field(default_factory=dict)

    def place(
        self, code: str, slots: tuple[TimeSlot, ...], source: AssignmentSource
    ) -> None:
        if code in self.assignments:
            raise ValueError(f"科目 {code} は既に配置されています")
        self.assignments[code] = Assignment(code, slots, source)
        for slot in slots:
            self._by_slot.setdefault(slot, []).append(code)

    def remove(self, code: str) -> None:
        assignment = self.assignments.pop(code, None)
        if assignment is None:
            return
        for slot in assignment.slots:
            holders = self._by_slot.get(slot)
            if holders and code in holders:
                holders.remove(code)

    def occupied_by(self, slot: TimeSlot) -> list[str]:
        return list(self._by_slot.get(slot, []))

    def slot_of(self, code: str) -> tuple[TimeSlot, ...]:
        assignment = self.assignments.get(code)
        return assignment.slots if assignment else ()

    def is_placed(self, code: str) -> bool:
        return code in self.assignments

    def placed_codes(self) -> set[str]:
        return set(self.assignments)
```

- [ ] **Step 6: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_timetable.py -v`
Expected: PASS（6 件）

- [ ] **Step 7: コミットする**

```bash
git add backend/app/models backend/tests/test_timetable.py
git commit -m "feat: Subject / Teacher / Timetable のデータクラスを追加"
```

---

### Task 4: 氏名の正規化

**Files:**
- Create: `backend/app/ingest/__init__.py`
- Create: `backend/app/ingest/name_normalizer.py`
- Create: `backend/config/name_variants.json`
- Test: `backend/tests/test_name_normalizer.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `normalize_name(raw: str) -> str` — 空白除去 + NFKC 正規化 + 異体字置換
  - `load_variants(path: Path | None = None) -> dict[str, str]`

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_name_normalizer.py`:

```python
from app.ingest.name_normalizer import normalize_name


def test_removes_ideographic_space():
    assert normalize_name("築　雅之") == "築雅之"


def test_removes_ascii_space():
    assert normalize_name("大嶋 伊佐雄") == "大嶋伊佐雄"


def test_same_person_written_two_ways_matches():
    assert normalize_name("髙橋 暁美") == normalize_name("髙橋　暁美")


def test_variant_kanji_is_unified():
    # 教員一覧は「降籏」、カリキュラムは「降旗」と表記が割れている
    assert normalize_name("降籏　光太郎") == normalize_name("降旗　光太郎")


def test_strips_surrounding_whitespace_and_tabs():
    assert normalize_name("  中村\t雅典 \n") == "中村雅典"


def test_empty_input_returns_empty_string():
    assert normalize_name("") == ""
    assert normalize_name(None) == ""
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_name_normalizer.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ingest'`）

- [ ] **Step 3: 異体字マッピングを作成する**

`backend/config/name_variants.json`:

```json
{
  "籏": "旗",
  "髙": "高",
  "﨑": "崎",
  "德": "徳",
  "濵": "浜",
  "邊": "辺",
  "邉": "辺",
  "齋": "斎",
  "齊": "斉",
  "澤": "沢",
  "眞": "真",
  "曻": "昇"
}
```

- [ ] **Step 4: 正規化を実装する**

`backend/app/ingest/__init__.py` は空ファイル。

`backend/app/ingest/name_normalizer.py`:

```python
"""教員氏名の表記ゆれを吸収する。

2 つの Excel は空白（全角・半角）と異体字（籏/旗、髙/高 など）で
表記が割れている。突合はすべて正規化後の値で行う。
"""
import json
import unicodedata
from functools import lru_cache
from pathlib import Path

_DEFAULT_VARIANTS_PATH = Path(__file__).resolve().parents[2] / "config" / "name_variants.json"

_WHITESPACE = "　 \t\r\n"


@lru_cache(maxsize=1)
def load_variants(path: Path | None = None) -> dict[str, str]:
    """異体字マッピングを読み込む。ファイルが無ければ空辞書を返す。"""
    target = path or _DEFAULT_VARIANTS_PATH
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def normalize_name(raw: str | None) -> str:
    """氏名を突合可能な形に正規化する。

    1. None・空文字はそのまま空文字
    2. 全角・半角の空白およびタブ・改行をすべて除去
    3. NFKC 正規化で全角英数などを揃える
    4. 異体字を代表字に置換
    """
    if not raw:
        return ""
    text = str(raw)
    for char in _WHITESPACE:
        text = text.replace(char, "")
    text = unicodedata.normalize("NFKC", text)
    for variant, canonical in load_variants().items():
        text = text.replace(variant, canonical)
    return text
```

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_name_normalizer.py -v`
Expected: PASS（6 件）

- [ ] **Step 6: 実データで衝突が起きないことを確認する**

Run:

```bash
cd /home/myarm/py_venvs/Project_3 && .venv/bin/python -c "
import sys; sys.path.insert(0, 'backend')
import openpyxl, collections
from app.ingest.name_normalizer import normalize_name
wt = openpyxl.load_workbook('教員一覧(整形済み).xlsx', data_only=True)
names = []
for sh in ['大学専任', '短大専任 ', '非常勤']:
    names += [r[0] for r in wt[sh].iter_rows(min_row=2, values_only=True) if r[0]]
c = collections.Counter(normalize_name(n) for n in names)
dupes = {k: v for k, v in c.items() if v > 1}
print('正規化後の重複:', dupes)
"
```

Expected: `正規化後の重複: {}`（別人が同一名に潰れていないこと）。重複が出た場合は `name_variants.json` から該当の異体字を削除する。

- [ ] **Step 7: コミットする**

```bash
git add backend/app/ingest backend/config/name_variants.json backend/tests/test_name_normalizer.py
git commit -m "feat: 教員氏名の正規化を追加"
```

---

### Task 5: 教員一覧 Excel の読み取り

**Files:**
- Create: `backend/app/ingest/teacher_reader.py`
- Test: `backend/tests/test_teacher_reader.py`

**Interfaces:**
- Consumes: Task 3 の `Teacher`、Task 2 の `TeacherKind` / `TimeSlot`、Task 4 の `normalize_name`
- Produces:
  - `parse_available_slots(raw: str | None) -> set[TimeSlot]` — `"月2,月3,月4"` を解析
  - `parse_days(raw: str | None) -> set[str]` — `"水,木"` を解析
  - `read_teachers(path: str | Path) -> dict[str, Teacher]` — キーは正規化済み氏名

**背景:** 教員一覧のシート名は `大学専任` / `短大専任 `（末尾に半角空白あり） / `非常勤` の 3 つ。専任シートは「氏名 / 研究日 / 出勤可能日(特任)」、非常勤シートは「氏名 / 出勤可能日（非常勤）」の列を持つ。研究日に値があれば専任、出勤可能日(特任) に値があれば特任と判定する。

- [ ] **Step 1: 失敗するテストを書く（解析関数）**

`backend/tests/test_teacher_reader.py`:

```python
from pathlib import Path

from app.ingest.teacher_reader import parse_available_slots, parse_days, read_teachers
from app.models.enums import TeacherKind
from app.models.timeslot import TimeSlot

TEACHER_XLSX = Path(__file__).resolve().parents[2] / "教員一覧(整形済み).xlsx"


def test_parse_available_slots_single():
    assert parse_available_slots("金1") == {TimeSlot("金", 1)}


def test_parse_available_slots_multiple():
    assert parse_available_slots("月2,月3,月4") == {
        TimeSlot("月", 2), TimeSlot("月", 3), TimeSlot("月", 4)
    }


def test_parse_available_slots_tolerates_spaces_and_fullwidth_comma():
    assert parse_available_slots("金1、 金2") == {TimeSlot("金", 1), TimeSlot("金", 2)}


def test_parse_available_slots_empty_is_empty_set():
    assert parse_available_slots(None) == set()
    assert parse_available_slots("") == set()


def test_parse_days():
    assert parse_days("水,木") == {"水", "木"}
    assert parse_days(None) == set()
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_teacher_reader.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ingest.teacher_reader'`）

- [ ] **Step 3: 解析関数と読み取りを実装する**

`backend/app/ingest/teacher_reader.py`:

```python
"""教員一覧 Excel を Teacher の辞書に変換する。"""
import re
from pathlib import Path

import openpyxl

from app.ingest.name_normalizer import normalize_name
from app.models.enums import TeacherKind
from app.models.teacher import Teacher
from app.models.timeslot import DAYS, TimeSlot

FULL_TIME_SHEETS = ("大学専任", "短大専任")
"""専任シートの名前。末尾に空白が付いている場合があるため前方一致で探す。"""

PART_TIME_SHEET = "非常勤"

_SEPARATORS = re.compile(r"[,、\s]+")
_SLOT_PATTERN = re.compile(r"^([月火水木金])([1-5])$")


def _split(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [token for token in _SEPARATORS.split(str(raw).strip()) if token]


def parse_available_slots(raw: str | None) -> set[TimeSlot]:
    """`月2,月3,月4` 形式を TimeSlot の集合に変換する。

    解釈できないトークンは黙って無視せず、呼び出し側が気付けるよう
    ValueError を投げる。
    """
    slots: set[TimeSlot] = set()
    for token in _split(raw):
        match = _SLOT_PATTERN.match(token)
        if not match:
            raise ValueError(f"出勤可能日の書式が不正です: {token!r}")
        slots.add(TimeSlot(match.group(1), int(match.group(2))))
    return slots


def parse_days(raw: str | None) -> set[str]:
    """`水,木` 形式を曜日の集合に変換する。"""
    days: set[str] = set()
    for token in _split(raw):
        if token not in DAYS:
            raise ValueError(f"曜日の書式が不正です: {token!r}")
        days.add(token)
    return days


def _find_sheet(workbook, prefix: str):
    for name in workbook.sheetnames:
        if name.strip() == prefix:
            return workbook[name]
    return None


def read_teachers(path: str | Path) -> dict[str, Teacher]:
    """教員一覧を読み、正規化済み氏名をキーにした辞書を返す。"""
    workbook = openpyxl.load_workbook(path, data_only=True)
    teachers: dict[str, Teacher] = {}

    for sheet_name in FULL_TIME_SHEETS:
        sheet = _find_sheet(workbook, sheet_name)
        if sheet is None:
            continue
        for row in sheet.iter_rows(min_row=2, values_only=True):
            raw_name = row[0] if row else None
            if not raw_name:
                continue
            name = normalize_name(raw_name)
            research_day = str(row[1]).strip() if len(row) > 1 and row[1] else None
            special_days = parse_days(row[2] if len(row) > 2 else None)
            kind = TeacherKind.SPECIAL if special_days else TeacherKind.FULL_TIME
            teachers[name] = Teacher(
                name=name,
                kind=kind,
                research_day=research_day,
                available_days=special_days,
            )

    sheet = _find_sheet(workbook, PART_TIME_SHEET)
    if sheet is not None:
        for row in sheet.iter_rows(min_row=2, values_only=True):
            raw_name = row[0] if row else None
            if not raw_name:
                continue
            name = normalize_name(raw_name)
            teachers[name] = Teacher(
                name=name,
                kind=TeacherKind.PART_TIME,
                available_slots=parse_available_slots(row[1] if len(row) > 1 else None),
            )

    return teachers
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_teacher_reader.py -v`
Expected: PASS（5 件）

- [ ] **Step 5: 実 Excel に対するテストを追加する**

`backend/tests/test_teacher_reader.py` の末尾に追記:

```python
def test_reads_real_workbook():
    teachers = read_teachers(TEACHER_XLSX)
    assert len(teachers) == 99  # 大学専任31 + 短大専任9 + 非常勤59

    kinds = {t.kind for t in teachers.values()}
    assert kinds == {TeacherKind.FULL_TIME, TeacherKind.SPECIAL, TeacherKind.PART_TIME}


def test_full_time_teacher_has_research_day():
    teachers = read_teachers(TEACHER_XLSX)
    assert teachers["大久保博樹"].kind is TeacherKind.FULL_TIME
    assert teachers["大久保博樹"].research_day == "火"


def test_special_teacher_has_available_days():
    teachers = read_teachers(TEACHER_XLSX)
    kumakura = teachers["熊倉浩靖"]
    assert kumakura.kind is TeacherKind.SPECIAL
    assert kumakura.available_days == {"水", "木"}


def test_part_time_teacher_has_available_slots():
    teachers = read_teachers(TEACHER_XLSX)
    konishi = teachers["小西一有"]
    assert konishi.kind is TeacherKind.PART_TIME
    assert konishi.available_slots == {
        TimeSlot("月", 2), TimeSlot("月", 3), TimeSlot("月", 4)
    }


def test_variant_kanji_teacher_is_reachable_by_normalized_name():
    teachers = read_teachers(TEACHER_XLSX)
    # 教員一覧は「降籏」、カリキュラムは「降旗」表記だが同じキーで引ける
    assert normalize_name("降旗　光太郎") in teachers
```

テスト冒頭の import に `from app.ingest.name_normalizer import normalize_name` を追加する。

- [ ] **Step 6: テストを実行する**

Run: `cd backend && ../.venv/bin/pytest tests/test_teacher_reader.py -v`
Expected: PASS（10 件）。件数が合わない場合は実データを確認し、テストの期待値を実データに合わせる。

- [ ] **Step 7: コミットする**

```bash
git add backend/app/ingest/teacher_reader.py backend/tests/test_teacher_reader.py
git commit -m "feat: 教員一覧 Excel の読み取りを追加"
```

---

### Task 6: カリキュラム一覧 Excel の読み取り

**Files:**
- Create: `backend/app/ingest/curriculum_reader.py`
- Create: `backend/config/seminar_subjects.json`
- Create: `backend/config/subject_overrides.json`
- Test: `backend/tests/test_curriculum_reader.py`

**Interfaces:**
- Consumes: Task 3 の `Subject`、Task 2 の列挙と `TimeSlot`、Task 4 の `normalize_name`
- Produces:
  - `to_base_name(name: str) -> str`
  - `read_curriculum(path: str | Path) -> list[Subject]`

**背景と設計判断:**

- ▲科目は同一授業コードで 2 行に分かれている。1 件の `Subject` に集約し `slots_required=2` とする
- `requires_consecutive` は既定で `True`。`subject_overrides.json` に列挙された `base_name` のみ `False`（現状は `プレゼミナール` のみ）
- `曜日 == "集中"` または `時限 == 99` の行は `is_intensive=True` とし、`fixed_slot` は付けない
- **コース列の見出しはシートによって異なる。**大学シートは `コース`、短大シートは `フィールド`（本学の呼称に合わせた事務局の命名）。リーダーは両方を受け入れ、どちらも `Subject.courses` に入れる
- 列が存在しない場合も落ちないこと。コース列が無ければ空リスト、`遠隔` が無ければ `False`
- 複数コースに属する科目は全角読点区切り（例：`経営、観光まちづくり`）。`_parse_courses` が読点と半角カンマの両方を扱う
- 会計学科にはコースも選択必修も存在しない（コース列は全行空）。これは設計どおりで、欠損ではない
- 短大の `備考` 列がクオーター（前①など）を持つ

- [ ] **Step 1: 設定ファイルを作成する**

`backend/config/seminar_subjects.json`:

```json
[
  "日本語リテラシーⅠ",
  "日本語リテラシーⅡ",
  "日本語リテラシーⅢ",
  "日本語リテラシーⅣ",
  "課題研究Ⅰ",
  "課題研究Ⅱ",
  "卒業研究Ⅰ",
  "卒業研究Ⅱ",
  "スタディスキルゼミナールⅠ",
  "スタディスキルゼミナールⅡ",
  "プレゼミナール",
  "専門ゼミナール",
  "卒業論文ゼミナール"
]
```

`backend/config/subject_overrides.json`:

```json
{
  "non_consecutive_double_subjects": ["プレゼミナール"]
}
```

- [ ] **Step 2: 失敗するテストを書く（base_name）**

`backend/tests/test_curriculum_reader.py`:

```python
from pathlib import Path

from app.ingest.curriculum_reader import read_curriculum, to_base_name
from app.models.enums import Category, Department, Quarter, Term
from app.models.timeslot import TimeSlot

CURRICULUM_XLSX = Path(__file__).resolve().parents[2] / "カリキュラム一覧(整形済み).xlsx"


def test_to_base_name_strips_accounting_suffix():
    assert to_base_name("日本語リテラシーⅠ:会") == "日本語リテラシーⅠ"


def test_to_base_name_strips_retake_marker():
    assert to_base_name("日本語リテラシーⅠ【再】:会") == "日本語リテラシーⅠ"


def test_to_base_name_strips_double_slot_marker():
    assert to_base_name("▲デジタル画像編集（Photoshop）") == "デジタル画像編集（Photoshop）"


def test_to_base_name_leaves_plain_name_untouched():
    assert to_base_name("経営情報管理") == "経営情報管理"
```

- [ ] **Step 3: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_curriculum_reader.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ingest.curriculum_reader'`）

- [ ] **Step 4: リーダーを実装する**

`backend/app/ingest/curriculum_reader.py`:

```python
"""カリキュラム一覧 Excel を Subject のリストに変換する。

▲科目は同一授業コードで 2 行に分かれているため 1 件へ集約する。
コース列・遠隔列は事務局側で整備中のため、存在しなくても落ちない。
"""
import json
from collections import defaultdict
from pathlib import Path

import openpyxl

from app.ingest.name_normalizer import normalize_name
from app.models.enums import Category, Department, Quarter, Term
from app.models.subject import Subject
from app.models.timeslot import INTENSIVE_PERIOD, TimeSlot

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

DOUBLE_SLOT_MARKER = "▲"
ACCOUNTING_SUFFIX = ":会"
RETAKE_MARKER = "【再】"
INTENSIVE_DAY = "集中"

COURSE_COLUMN_NAMES = ("コース", "フィールド")
"""コース列の見出し。大学は「コース」、短大は「フィールド」と呼ぶ。"""


def _load_json(filename: str, fallback):
    path = _CONFIG_DIR / filename
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def to_base_name(name: str) -> str:
    """先頭の ▲、接尾辞の :会、【再】を除いた正規化名を返す。"""
    text = str(name).strip()
    if text.startswith(DOUBLE_SLOT_MARKER):
        text = text[len(DOUBLE_SLOT_MARKER):]
    text = text.replace(ACCOUNTING_SUFFIX, "")
    text = text.replace(RETAKE_MARKER, "")
    return text.strip()


def _header_index(header_row: tuple) -> dict[str, int]:
    return {
        str(value).strip(): index
        for index, value in enumerate(header_row)
        if value is not None
    }


def _cell(row: tuple, columns: dict[str, int], key: str):
    index = columns.get(key)
    if index is None or index >= len(row):
        return None
    return row[index]


def _parse_quarter(value) -> Quarter | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return Quarter(text)
    except ValueError:
        return None


def _parse_slot(day_value, period_value) -> TimeSlot | None:
    """曜日と時限が揃っていて集中でない場合のみ TimeSlot を返す。"""
    if not day_value or period_value in (None, ""):
        return None
    day = str(day_value).strip()
    if day == INTENSIVE_DAY:
        return None
    period = int(period_value)
    if period == INTENSIVE_PERIOD:
        return None
    return TimeSlot(day, period)


def _is_intensive(day_value, period_value) -> bool:
    if day_value and str(day_value).strip() == INTENSIVE_DAY:
        return True
    if period_value in (None, ""):
        return False
    return int(period_value) == INTENSIVE_PERIOD


def _course_cell(row: tuple, columns: dict[str, int]):
    """シートごとに異なるコース列の見出しを吸収する。"""
    for name in COURSE_COLUMN_NAMES:
        if name in columns:
            return _cell(row, columns, name)
    return None


def _parse_courses(value) -> list[str]:
    if not value:
        return []
    return [token.strip() for token in str(value).replace("、", ",").split(",") if token.strip()]


def read_curriculum(path: str | Path) -> list[Subject]:
    """全シートを読み、Subject のリストを返す。"""
    seminar_names = set(_load_json("seminar_subjects.json", []))
    overrides = _load_json("subject_overrides.json", {})
    non_consecutive = set(overrides.get("non_consecutive_double_subjects", []))

    workbook = openpyxl.load_workbook(path, data_only=True)
    grouped: dict[str, list[tuple[tuple, dict[str, int]]]] = defaultdict(list)
    order: list[str] = []

    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        columns = _header_index(rows[0])
        for row in rows[1:]:
            code = _cell(row, columns, "授業コード")
            if not code:
                continue
            code = str(code).strip()
            if code not in grouped:
                order.append(code)
            grouped[code].append((row, columns))

    subjects: list[Subject] = []
    for code in order:
        entries = grouped[code]
        row, columns = entries[0]
        name = str(_cell(row, columns, "授業科目名称")).strip()
        base_name = to_base_name(name)

        slots: list[TimeSlot] = []
        intensive = False
        for entry_row, entry_columns in entries:
            day = _cell(entry_row, entry_columns, "曜日")
            period = _cell(entry_row, entry_columns, "時限")
            if _is_intensive(day, period):
                intensive = True
                continue
            slot = _parse_slot(day, period)
            if slot is not None:
                slots.append(slot)

        is_double = name.startswith(DOUBLE_SLOT_MARKER)
        slots_required = 2 if is_double else 1
        requires_consecutive = is_double and base_name not in non_consecutive

        subjects.append(
            Subject(
                code=code,
                name=name,
                base_name=base_name,
                department=Department(str(_cell(row, columns, "学科")).strip()),
                year=int(str(_cell(row, columns, "年次配当")).strip()),
                term=Term(str(_cell(row, columns, "開講期間")).strip()),
                quarter=_parse_quarter(_cell(row, columns, "備考")),
                category=Category(str(_cell(row, columns, "科目区分")).strip()),
                courses=_parse_courses(_course_cell(row, columns)),
                teacher=normalize_name(_cell(row, columns, "教員氏名")),
                is_remote=str(_cell(row, columns, "遠隔") or "").strip() == "○",
                is_joint=str(_cell(row, columns, "合同(経・会)") or "").strip() == "○",
                slots_required=slots_required,
                requires_consecutive=requires_consecutive,
                fixed_slot=tuple(slots) if len(slots) == slots_required else None,
                is_intensive=intensive,
                is_seminar=base_name in seminar_names,
            )
        )

    return subjects
```

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_curriculum_reader.py -v`
Expected: PASS（4 件）

- [ ] **Step 6: 実 Excel に対するテストを追加する**

`backend/tests/test_curriculum_reader.py` の末尾に追記:

```python
def _by_code(subjects):
    return {s.code: s for s in subjects}


def test_reads_real_workbook_and_merges_double_slot_rows():
    subjects = read_curriculum(CURRICULUM_XLSX)
    # 大学 496 行 + 短大 166 行 = 662 行。▲科目 4 件が各 2 行 → 4 件減る
    assert len(subjects) == 658
    assert len({s.code for s in subjects}) == len(subjects)


def test_double_slot_subject_requires_two_consecutive_slots():
    photoshop = _by_code(read_curriculum(CURRICULUM_XLSX))["J15901"]
    assert photoshop.slots_required == 2
    assert photoshop.requires_consecutive is True
    assert photoshop.base_name == "デジタル画像編集（Photoshop）"
    assert photoshop.quarter is Quarter.Q2


def test_pre_seminar_is_the_non_consecutive_exception():
    pre_seminar = _by_code(read_curriculum(CURRICULUM_XLSX))["J10405"]
    assert pre_seminar.slots_required == 2
    assert pre_seminar.requires_consecutive is False
    assert pre_seminar.is_seminar is True
    # 事務局が曜日・時限を空にしたため確定枠は無く、システムが配置する
    assert pre_seminar.fixed_slot is None


def test_intensive_subject_has_no_fixed_slot():
    subjects = read_curriculum(CURRICULUM_XLSX)
    intensives = [s for s in subjects if s.is_intensive]
    assert len(intensives) == 45  # 大学 26 + 短大 19
    assert all(s.fixed_slot is None for s in intensives)


def test_retake_subject_shares_base_name_with_original():
    subjects = _by_code(read_curriculum(CURRICULUM_XLSX))
    assert subjects["A50201"].base_name == "日本語リテラシーⅠ"
    assert subjects["A50206"].base_name == "日本語リテラシーⅠ"
    assert subjects["A50206"].is_seminar is True


def test_university_courses_are_read_including_multi_course_subjects():
    subjects = read_curriculum(CURRICULUM_XLSX)
    management = {
        course for s in subjects
        if s.department is Department.MANAGEMENT for course in s.courses
    }
    assert {"経営", "情報", "観光まちづくり"} <= management

    # 複数コース所属は全角読点区切りで書かれている
    multi = [s for s in subjects if len(s.courses) > 1]
    assert multi
    assert all(len(s.courses) == len(set(s.courses)) for s in multi)


def test_junior_courses_are_read_from_the_field_column():
    subjects = read_curriculum(CURRICULUM_XLSX)
    junior = {
        course for s in subjects
        if s.department is Department.JUNIOR for course in s.courses
    }
    assert {"経営", "情報デザイン", "グローバルコミュニケーション"} <= junior


def test_every_elective_required_subject_has_a_course():
    subjects = read_curriculum(CURRICULUM_XLSX)
    elective_required = [s for s in subjects if s.category is Category.ELECTIVE_REQUIRED]
    # 経営58 + 短大44（短大は生47行だが▲科目3件が各2行のため集約後44）
    assert len(elective_required) == 102
    assert all(s.courses for s in elective_required)


def test_accounting_has_no_courses_by_design():
    subjects = read_curriculum(CURRICULUM_XLSX)
    accounting = [s for s in subjects if s.department is Department.ACCOUNTING]
    assert accounting
    assert all(s.courses == [] for s in accounting)
    assert not [s for s in accounting if s.category is Category.ELECTIVE_REQUIRED]


def test_junior_remote_flag_is_read():
    subjects = read_curriculum(CURRICULUM_XLSX)
    remote = [s for s in subjects if s.department is Department.JUNIOR and s.is_remote]
    assert len(remote) == 13


def test_department_and_category_are_parsed():
    subjects = _by_code(read_curriculum(CURRICULUM_XLSX))
    academic = subjects["A50101"]
    assert academic.department is Department.ACCOUNTING
    assert academic.category is Category.REQUIRED
    assert academic.term is Term.FALL
    assert academic.fixed_slot == (TimeSlot("火", 3),)
```

- [ ] **Step 7: テストを実行する**

Run: `cd backend && ../.venv/bin/pytest tests/test_curriculum_reader.py -v`
Expected: PASS（15 件）。件数が合わない場合は実データを確認し、確認結果を報告した上で期待値を実データに合わせる。

- [ ] **Step 8: コミットする**

```bash
git add backend/app/ingest/curriculum_reader.py backend/config backend/tests/test_curriculum_reader.py
git commit -m "feat: カリキュラム一覧 Excel の読み取りを追加"
```

---

### Task 7: 合同科目のペアリング

**Files:**
- Create: `backend/app/ingest/joint_pairing.py`
- Test: `backend/tests/test_joint_pairing.py`

**Interfaces:**
- Consumes: Task 3 の `Subject`、Task 2 の `Department`
- Produces:
  - `JOINT_DEPARTMENTS: tuple[Department, ...]` — 経営・会計のみ
  - `assign_joint_ids(subjects: list[Subject]) -> list[str]` — `subjects` の `joint_id` を破壊的に設定し、**フラグの付け忘れが疑われる科目コード**のリストを返す

**背景（実データの構造）:**

合同=○ は「その科目が経営・会計の合同開講である」ことを示すフラグで、実際の対応付けは**教員単位**で成立する。対応付けの鍵は `base_name` + `teacher` + `term` の一致。

現行データでは 227 件が合同=○ で、その大半はゼミ系（課題研究Ⅰ、卒業研究Ⅰ・Ⅱ）である。同じ教員が経営・会計の両方にコマを持てばペアが成立し、片方の学科にしかコマがない教員は**単独のまま残るのが正常**。単独は警告の対象にしない。

一方で、**他学科が合同としているのに、自学科のどのクラスにもフラグが付いていない**場合は、事務局の付け忘れである可能性が高い。これだけを警告に回す。

判定を学科単位で行うのが要点である。同一学科・同一教員で複数クラスが開講され、そのうち 1 クラスだけが他学科と合同、という構造が実在する（例：`育児と介護` は経営に 2 クラスあり、`B53202` のみ会計と合同で `B53201` は単独）。この場合、経営には合同フラグの付いたクラスが存在するので付け忘れではない。「フラグの付いたクラスが 1 つも無い学科」だけを警告対象とする。

`合同(経・会)` 列は大学シートにしか存在しないため、ペアリングもフラグ不一致の検出も**経営・会計に限定**する。短期大学部の科目は同名・同教員でも対象外とする。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_joint_pairing.py`:

```python
from pathlib import Path

from app.ingest.curriculum_reader import read_curriculum
from app.ingest.joint_pairing import assign_joint_ids
from app.models.enums import Category, Department, Term
from app.models.subject import Subject

CURRICULUM_XLSX = Path(__file__).resolve().parents[2] / "カリキュラム一覧(整形済み).xlsx"


def _subject(code, base_name, department, term, teacher, is_joint=True):
    return Subject(
        code=code,
        name=base_name,
        base_name=base_name,
        department=department,
        year=2,
        term=term,
        quarter=None,
        category=Category.ELECTIVE,
        teacher=teacher,
        is_joint=is_joint,
    )


def test_matching_pair_gets_same_joint_id():
    subjects = [
        _subject("A1", "経営情報管理", Department.ACCOUNTING, Term.SPRING, "荒牧裕一"),
        _subject("B1", "経営情報管理", Department.MANAGEMENT, Term.SPRING, "荒牧裕一"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is not None
    assert subjects[0].joint_id == subjects[1].joint_id


def test_different_term_does_not_pair_and_is_not_reported():
    # マーケティングプロジェクトは会計1年前期・経営1年後期。別の授業なので正常
    subjects = [
        _subject("A2", "マーケティングプロジェクト", Department.ACCOUNTING, Term.SPRING, "増渕賢一郎"),
        _subject("B2", "マーケティングプロジェクト", Department.MANAGEMENT, Term.FALL, "増渕賢一郎"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None
    assert subjects[1].joint_id is None


def test_lone_joint_subject_is_normal():
    # その教員のコマが片方の学科にしかないゼミ。相手がいないので単独のまま
    subjects = [
        _subject("A3", "卒業研究Ⅰ", Department.ACCOUNTING, Term.SPRING, "神山直規"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None


def test_flag_mismatch_is_reported():
    # 同じ科目・教員・開講期なのに会計側だけフラグが無い＝付け忘れ
    subjects = [
        _subject("B4", "アート表現", Department.MANAGEMENT, Term.FALL, "前沢知子"),
        _subject("A4", "アート表現", Department.ACCOUNTING, Term.FALL, "前沢知子", is_joint=False),
    ]
    assert assign_joint_ids(subjects) == ["A4"]
    assert subjects[0].joint_id is None


def test_extra_section_in_the_same_department_is_not_a_mismatch():
    # 育児と介護は経営に2クラスあり、B2 のみ会計と合同。B1 は単独クラスで正常
    subjects = [
        _subject("A9", "育児と介護", Department.ACCOUNTING, Term.SPRING, "石坂公俊"),
        _subject("B1", "育児と介護", Department.MANAGEMENT, Term.SPRING, "石坂公俊",
                 is_joint=False),
        _subject("B2", "育児と介護", Department.MANAGEMENT, Term.SPRING, "石坂公俊"),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id == subjects[2].joint_id
    assert subjects[1].joint_id is None


def test_non_joint_subjects_are_ignored():
    subjects = [
        _subject("A5", "簿記論", Department.ACCOUNTING, Term.SPRING, "松田流輝", is_joint=False),
        _subject("B5", "簿記論", Department.MANAGEMENT, Term.SPRING, "松田流輝", is_joint=False),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None


def test_junior_college_is_outside_the_joint_scope():
    # 合同(経・会) 列は大学シートにしかない。短大は同名・同教員でも対象外
    subjects = [
        _subject("A6", "マーケティングプロジェクト", Department.ACCOUNTING, Term.SPRING, "増渕賢一郎"),
        _subject("J6", "マーケティングプロジェクト", Department.JUNIOR, Term.SPRING, "増渕賢一郎",
                 is_joint=False),
    ]
    assert assign_joint_ids(subjects) == []
    assert subjects[0].joint_id is None


def test_joint_ids_are_distinct_between_groups():
    subjects = [
        _subject("A7", "科目甲", Department.ACCOUNTING, Term.SPRING, "教員甲"),
        _subject("B7", "科目甲", Department.MANAGEMENT, Term.SPRING, "教員甲"),
        _subject("A8", "科目乙", Department.ACCOUNTING, Term.SPRING, "教員乙"),
        _subject("B8", "科目乙", Department.MANAGEMENT, Term.SPRING, "教員乙"),
    ]
    assign_joint_ids(subjects)
    assert subjects[0].joint_id != subjects[2].joint_id


def test_paired_members_always_span_both_departments():
    subjects = read_curriculum(CURRICULUM_XLSX)
    assign_joint_ids(subjects)

    groups: dict[str, set] = {}
    for subject in subjects:
        if subject.joint_id:
            groups.setdefault(subject.joint_id, set()).add(subject.department)
    assert groups
    assert all(
        departments == {Department.MANAGEMENT, Department.ACCOUNTING}
        for departments in groups.values()
    )


def test_real_workbook_has_no_flag_mismatch():
    subjects = read_curriculum(CURRICULUM_XLSX)
    assert assign_joint_ids(subjects) == []
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_joint_pairing.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ingest.joint_pairing'`）

- [ ] **Step 3: ペアリングを実装する**

`backend/app/ingest/joint_pairing.py`:

```python
"""経営学科と会計学科で合同開講される科目を対応付ける。

合同=○ は科目が合同開講であることを示すフラグで、実際の対応付けは
教員単位で成立する。片方の学科にしかコマがない教員は単独のままが正常。

一方、同じ鍵の科目が他学科にあるのに片方だけフラグが付いている場合は
付け忘れの可能性が高いので、その科目コードを返して警告に回す。
"""
from collections import defaultdict

from app.models.enums import Department
from app.models.subject import Subject

JOINT_DEPARTMENTS = (Department.MANAGEMENT, Department.ACCOUNTING)
"""合同開講の対象学科。合同(経・会) 列は大学シートにしか存在しない。"""


def assign_joint_ids(subjects: list[Subject]) -> list[str]:
    """合同科目に joint_id を付与し、フラグ付け忘れの科目コードを返す。

    subjects の joint_id を破壊的に書き換える。
    """
    groups: dict[tuple[str, str, str], list[Subject]] = defaultdict(list)
    for subject in subjects:
        if subject.department not in JOINT_DEPARTMENTS:
            continue
        key = (subject.base_name, subject.teacher, subject.term.value)
        groups[key].append(subject)

    mismatches: list[str] = []
    for index, key in enumerate(sorted(groups), start=1):
        members = groups[key]
        flagged_departments = {m.department for m in members if m.is_joint}
        if not flagged_departments:
            continue

        if len(flagged_departments) >= 2:
            joint_id = f"J{index:03d}"
            for member in members:
                if member.is_joint:
                    member.joint_id = joint_id

        # フラグの付いたクラスが 1 つも無い学科だけが付け忘れの疑い。
        # 同一学科に複数クラスあり片方だけ合同、という構造は正常。
        mismatches.extend(
            member.code for member in members
            if member.department not in flagged_departments
        )

    return sorted(mismatches)
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_joint_pairing.py -v`
Expected: PASS（5 件）

- [ ] **Step 5: コミットする**

```bash
git add backend/app/ingest/joint_pairing.py backend/tests/test_joint_pairing.py
git commit -m "feat: 合同科目のペアリングを追加"
```

---

### Task 8: Stage 0 の警告生成

**Files:**
- Create: `backend/app/ingest/validators.py`
- Test: `backend/tests/test_ingest_validators.py`

**Interfaces:**
- Consumes: Task 3 の `Subject` / `Teacher`、Task 7 の `assign_joint_ids`
- Produces:
  - `Warning` — frozen dataclass `(kind: str, message: str, subject_code: str | None, teacher_name: str | None)`
  - `collect_warnings(subjects, teachers, joint_flag_mismatch_codes) -> list[Warning]`

**警告の種類（`kind` の値）:**

| kind | 条件 |
|---|---|
| `unknown_teacher` | 担当教員が教員一覧に存在しない |
| `missing_availability` | 担当科目があるのに非常勤の出勤可能コマが空 |
| `joint_flag_mismatch` | 同じ科目・教員・開講期の科目が他学科にあるのに、片方だけ合同フラグが付いている |
| `missing_course` | 選択必修なのにコース列が空 |
| `partial_slot` | 曜日と時限の片方だけが入力されている |

単独の合同科目（その教員のコマが片方の学科にしかない）は正常であり、警告を出さない。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_ingest_validators.py`:

```python
from app.ingest.validators import Warning, collect_warnings
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot


def _subject(code="A1", category=Category.REQUIRED, teacher="教員甲", courses=None):
    return Subject(
        code=code,
        name="科目",
        base_name="科目",
        department=Department.MANAGEMENT,
        year=1,
        term=Term.SPRING,
        quarter=None,
        category=category,
        courses=courses or [],
        teacher=teacher,
    )


def _kinds(warnings):
    return sorted({w.kind for w in warnings})


def test_unknown_teacher_is_reported():
    warnings = collect_warnings([_subject(teacher="未登録教員")], {}, [])
    assert _kinds(warnings) == ["unknown_teacher"]
    assert warnings[0].teacher_name == "未登録教員"


def test_part_time_without_availability_is_reported():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.PART_TIME)}
    warnings = collect_warnings([_subject()], teachers, [])
    assert _kinds(warnings) == ["missing_availability"]


def test_part_time_with_availability_is_clean():
    teachers = {
        "教員甲": Teacher("教員甲", TeacherKind.PART_TIME, available_slots={TimeSlot("月", 1)})
    }
    assert collect_warnings([_subject()], teachers, []) == []


def test_full_time_without_availability_is_clean():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME, research_day="火")}
    assert collect_warnings([_subject()], teachers, []) == []


def test_joint_flag_mismatch_is_reported():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME)}
    warnings = collect_warnings([_subject(code="A9")], teachers, ["A9"])
    assert _kinds(warnings) == ["joint_flag_mismatch"]
    assert warnings[0].subject_code == "A9"


def test_elective_required_without_course_is_reported():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME)}
    subject = _subject(category=Category.ELECTIVE_REQUIRED, courses=[])
    assert _kinds(collect_warnings([subject], teachers, [])) == ["missing_course"]


def test_elective_required_with_course_is_clean():
    teachers = {"教員甲": Teacher("教員甲", TeacherKind.FULL_TIME)}
    subject = _subject(category=Category.ELECTIVE_REQUIRED, courses=["情報コース"])
    assert collect_warnings([subject], teachers, []) == []


def test_warning_is_hashable_and_comparable():
    a = Warning("unknown_teacher", "教員が見つかりません", None, "教員甲")
    b = Warning("unknown_teacher", "教員が見つかりません", None, "教員甲")
    assert a == b
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_ingest_validators.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ingest.validators'`）

- [ ] **Step 3: 警告生成を実装する**

`backend/app/ingest/validators.py`:

```python
"""Stage 0 の警告を生成する。

警告があっても生成は止めない。フロントに一覧を出し、事務局が
Excel を直すか、そのまま進めるかを判断する。
"""
from dataclasses import dataclass

from app.models.enums import Category, TeacherKind
from app.models.subject import Subject
from app.models.teacher import Teacher


@dataclass(frozen=True, slots=True)
class Warning:
    kind: str
    message: str
    subject_code: str | None = None
    teacher_name: str | None = None


def collect_warnings(
    subjects: list[Subject],
    teachers: dict[str, Teacher],
    joint_flag_mismatch_codes: list[str],
) -> list[Warning]:
    warnings: list[Warning] = []
    seen_unknown: set[str] = set()
    seen_missing_availability: set[str] = set()
    mismatches = set(joint_flag_mismatch_codes)

    for subject in subjects:
        teacher = teachers.get(subject.teacher)

        if teacher is None:
            if subject.teacher not in seen_unknown:
                seen_unknown.add(subject.teacher)
                warnings.append(Warning(
                    kind="unknown_teacher",
                    message=f"教員一覧に存在しない担当教員です: {subject.teacher}",
                    teacher_name=subject.teacher,
                ))
        elif (
            teacher.kind is TeacherKind.PART_TIME
            and not teacher.available_slots
            and teacher.name not in seen_missing_availability
        ):
            seen_missing_availability.add(teacher.name)
            warnings.append(Warning(
                kind="missing_availability",
                message=f"担当科目がありますが出勤可能日が空欄です: {teacher.name}",
                teacher_name=teacher.name,
            ))

        if subject.code in mismatches:
            warnings.append(Warning(
                kind="joint_flag_mismatch",
                message=(
                    f"他学科に同じ科目・教員・開講期の科目がありますが、"
                    f"合同フラグが付いていません: {subject.name}"
                ),
                subject_code=subject.code,
            ))

        if subject.category is Category.ELECTIVE_REQUIRED and not subject.courses:
            warnings.append(Warning(
                kind="missing_course",
                message=f"選択必修ですがコースが未設定です: {subject.name}",
                subject_code=subject.code,
            ))

    return warnings
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_ingest_validators.py -v`
Expected: PASS（8 件）

- [ ] **Step 5: `partial_slot` 警告のテストを追加する**

`backend/tests/test_ingest_validators.py` の末尾に追記:

```python
def test_partial_slot_is_reported_by_reader_level_check():
    from app.ingest.validators import check_partial_slots

    rows = [
        {"授業コード": "A1", "曜日": "月", "時限": None},
        {"授業コード": "A2", "曜日": None, "時限": 3},
        {"授業コード": "A3", "曜日": "火", "時限": 2},
        {"授業コード": "A4", "曜日": None, "時限": None},
    ]
    warnings = check_partial_slots(rows)
    assert [w.subject_code for w in warnings] == ["A1", "A2"]
    assert all(w.kind == "partial_slot" for w in warnings)
```

- [ ] **Step 6: `check_partial_slots` を実装する**

`backend/app/ingest/validators.py` の末尾に追記:

```python
def check_partial_slots(rows: list[dict]) -> list[Warning]:
    """曜日と時限の片方だけが入力されている行を検出する。

    Subject に変換すると片側だけの情報は失われるため、Excel の行を
    そのまま受け取って判定する。
    """
    warnings: list[Warning] = []
    for row in rows:
        day = row.get("曜日")
        period = row.get("時限")
        if bool(day) != (period not in (None, "")):
            warnings.append(Warning(
                kind="partial_slot",
                message=f"曜日と時限の片方だけが入力されています: {row.get('授業コード')}",
                subject_code=row.get("授業コード"),
            ))
    return warnings
```

- [ ] **Step 7: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 8: コミットする**

```bash
git add backend/app/ingest/validators.py backend/tests/test_ingest_validators.py
git commit -m "feat: Stage 0 の警告生成を追加"
```

---

### Task 9: 制約の共通基盤と教員に関する制約（H1・H5・H6・H7）

**Files:**
- Create: `backend/app/constraints/context.py`
- Create: `backend/app/constraints/teacher_rules.py`
- Test: `backend/tests/test_teacher_rules.py`

**Interfaces:**
- Consumes: Task 2〜3 のモデル、Task 2 の `periods_overlap`
- Produces:
  - `Violation(rule_id: str, subject_code: str, message: str, related_code: str | None = None)` — frozen dataclass
  - `Context(subjects: dict[str, Subject], teachers: dict[str, Teacher])` — `from_lists(subjects, teachers)` クラスメソッドを持つ
  - `others_at(context, timetable, slot, exclude_code) -> list[Subject]` — 指定コマを占める他科目のうち、開講期間が重なるものだけを返す
  - `check_h1 / check_h5 / check_h6 / check_h7` — すべて `(context, timetable, subject, slots) -> list[Violation]`
  - `TEACHER_RULES: tuple[Callable, ...]`

**すべてのルール関数の共通契約:** 「`subject` を `slots` に置いたら違反するか」を判定する。`timetable` に `subject` が既に置かれていても、その配置は無視して評価する（再配置の判定に使うため）。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_teacher_rules.py`:

```python
import pytest

from app.constraints.context import Context, Violation
from app.constraints.teacher_rules import check_h1, check_h5, check_h6, check_h7
from app.models.enums import Category, Department, Quarter, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make_subject(code, teacher="教員甲", term=Term.SPRING, quarter=None, year=1,
                 department=Department.MANAGEMENT, category=Category.REQUIRED):
    return Subject(
        code=code, name=code, base_name=code, department=department, year=year,
        term=term, quarter=quarter, category=category, teacher=teacher,
    )


def build(subjects, teachers):
    return Context.from_lists(subjects, teachers)


def test_h1_flags_same_teacher_in_same_slot():
    a, b = make_subject("A1"), make_subject("B1")
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    violations = check_h1(ctx, tt, b, (TimeSlot("月", 1),))
    assert [v.rule_id for v in violations] == ["H1"]
    assert violations[0].related_code == "A1"


def test_h1_allows_different_teachers():
    a = make_subject("A1", teacher="教員甲")
    b = make_subject("B1", teacher="教員乙")
    ctx = build([a, b], [
        Teacher("教員甲", TeacherKind.FULL_TIME),
        Teacher("教員乙", TeacherKind.FULL_TIME),
    ])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h1(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h1_allows_non_overlapping_quarters():
    a = make_subject("A1", term=Term.SPRING, quarter=Quarter.Q1)
    b = make_subject("B1", term=Term.SPRING, quarter=Quarter.Q2)
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h1(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h1_exempts_joint_pairs():
    # 合同ペアは物理的に1つの授業。H4 が同一コマを要求するため H1 は無視する
    a = make_subject("A1", department=Department.ACCOUNTING)
    b = make_subject("B1", department=Department.MANAGEMENT)
    a.joint_id = b.joint_id = "J001"
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    assert check_h1(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h1_still_flags_a_different_joint_group():
    a = make_subject("A1", department=Department.ACCOUNTING)
    b = make_subject("B1", department=Department.MANAGEMENT)
    a.joint_id = "J001"
    b.joint_id = "J002"
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    assert [v.rule_id for v in check_h1(ctx, tt, b, (TimeSlot("月", 1),))] == ["H1"]


def test_h1_ignores_the_subjects_own_existing_placement():
    a = make_subject("A1")
    ctx = build([a], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h1(ctx, tt, a, (TimeSlot("月", 1),)) == []


def test_h5_part_time_must_use_available_slots():
    a = make_subject("A1", teacher="非常勤甲")
    teacher = Teacher("非常勤甲", TeacherKind.PART_TIME,
                      available_slots={TimeSlot("月", 2), TimeSlot("月", 3)})
    ctx = build([a], [teacher])
    tt = Timetable()
    assert check_h5(ctx, tt, a, (TimeSlot("月", 2),)) == []
    assert [v.rule_id for v in check_h5(ctx, tt, a, (TimeSlot("火", 2),))] == ["H5"]


def test_h5_part_time_without_availability_is_unconstrained():
    a = make_subject("A1", teacher="非常勤甲")
    ctx = build([a], [Teacher("非常勤甲", TeacherKind.PART_TIME)])
    assert check_h5(ctx, Timetable(), a, (TimeSlot("火", 2),)) == []


def test_h5_special_teacher_is_constrained_by_day_only():
    a = make_subject("A1", teacher="特任甲")
    teacher = Teacher("特任甲", TeacherKind.SPECIAL, available_days={"水", "木"})
    ctx = build([a], [teacher])
    tt = Timetable()
    assert check_h5(ctx, tt, a, (TimeSlot("水", 5),)) == []
    assert [v.rule_id for v in check_h5(ctx, tt, a, (TimeSlot("金", 1),))] == ["H5"]


def test_h6_blocks_research_day():
    a = make_subject("A1", teacher="専任甲")
    ctx = build([a], [Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")])
    tt = Timetable()
    assert [v.rule_id for v in check_h6(ctx, tt, a, (TimeSlot("火", 1),))] == ["H6"]
    assert check_h6(ctx, tt, a, (TimeSlot("水", 1),)) == []


def test_h6_ignores_teacher_without_research_day():
    a = make_subject("A1", teacher="特任甲")
    ctx = build([a], [Teacher("特任甲", TeacherKind.SPECIAL, available_days={"火"})])
    assert check_h6(ctx, Timetable(), a, (TimeSlot("火", 1),)) == []


def test_h7_blocks_three_consecutive_periods():
    a, b, c = make_subject("A1"), make_subject("A2"), make_subject("A3")
    ctx = build([a, b, c], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    tt.place("A2", (TimeSlot("月", 2),), AssignmentSource.PRELOCK)
    assert [v.rule_id for v in check_h7(ctx, tt, c, (TimeSlot("月", 3),))] == ["H7"]


def test_h7_allows_two_consecutive_periods():
    a, b = make_subject("A1"), make_subject("A2")
    ctx = build([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert check_h7(ctx, tt, b, (TimeSlot("月", 2),)) == []


def test_h7_allows_gap():
    a, b, c = make_subject("A1"), make_subject("A2"), make_subject("A3")
    ctx = build([a, b, c], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    tt.place("A2", (TimeSlot("月", 2),), AssignmentSource.PRELOCK)
    assert check_h7(ctx, tt, c, (TimeSlot("月", 4),)) == []


def test_h7_allows_double_slot_subject_occupying_two_periods():
    double = make_subject("J1")
    double.slots_required = 2
    double.requires_consecutive = True
    ctx = build([double], [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    assert check_h7(ctx, tt, double, (TimeSlot("水", 2), TimeSlot("水", 3))) == []


def test_unknown_teacher_is_unconstrained():
    a = make_subject("A1", teacher="未登録")
    ctx = build([a], [])
    tt = Timetable()
    assert check_h5(ctx, tt, a, (TimeSlot("金", 1),)) == []
    assert check_h6(ctx, tt, a, (TimeSlot("金", 1),)) == []
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_teacher_rules.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.constraints.context'`）

- [ ] **Step 3: Context と Violation を実装する**

`backend/app/constraints/context.py`:

```python
"""制約評価に必要な索引をまとめる。ルール関数は必ずこれを受け取る。"""
from dataclasses import dataclass

from app.constraints.period_overlap import periods_overlap
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable


@dataclass(frozen=True, slots=True)
class Violation:
    rule_id: str
    subject_code: str
    message: str
    related_code: str | None = None


@dataclass(slots=True)
class Context:
    subjects: dict[str, Subject]
    teachers: dict[str, Teacher]

    @classmethod
    def from_lists(
        cls, subjects: list[Subject], teachers: list[Teacher] | dict[str, Teacher]
    ) -> "Context":
        teacher_map = (
            teachers if isinstance(teachers, dict)
            else {teacher.name: teacher for teacher in teachers}
        )
        return cls({s.code: s for s in subjects}, teacher_map)


def others_at(
    context: Context, timetable: Timetable, slot: TimeSlot, exclude_code: str
) -> list[Subject]:
    """slot を占める他科目のうち、exclude_code の科目と開講期間が重なるもの。"""
    target = context.subjects[exclude_code]
    result: list[Subject] = []
    for code in timetable.occupied_by(slot):
        if code == exclude_code:
            continue
        other = context.subjects.get(code)
        if other is None:
            continue
        if periods_overlap(target.term, target.quarter, other.term, other.quarter):
            result.append(other)
    return result
```

- [ ] **Step 4: 教員に関する制約を実装する**

`backend/app/constraints/teacher_rules.py`:

```python
"""教員に関する制約 H1・H5・H6・H7。

すべて「subject を slots に置いたら違反するか」を返す。timetable 上の
subject 自身の既存配置は無視する。
"""
from app.constraints.context import Context, Violation, others_at
from app.constraints.period_overlap import periods_overlap
from app.models.enums import TeacherKind
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

MAX_CONSECUTIVE = 2
"""同一教員が同一日に連続してよいコマ数の上限。"""


def check_h1(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """同一教員が同曜日・同時限に別科目を持たない（全学科横断）。

    合同ペアは 2 行に分かれていても物理的に 1 つの授業で、担当教員も
    同一である。H4 が同一コマへの配置を要求するため、joint_id が一致
    する相手は衝突とみなさない。除外しないと H1 と H4 が矛盾し、
    合同科目を一切配置できなくなる。
    """
    violations: list[Violation] = []
    for slot in slots:
        for other in others_at(context, timetable, slot, subject.code):
            if subject.joint_id and other.joint_id == subject.joint_id:
                continue
            if other.teacher and other.teacher == subject.teacher:
                violations.append(Violation(
                    rule_id="H1",
                    subject_code=subject.code,
                    message=(
                        f"{subject.teacher} が {slot} に "
                        f"{other.name} と重複しています"
                    ),
                    related_code=other.code,
                ))
    return violations


def check_h5(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """非常勤は出勤可能コマのみ、特任は出勤可能曜日のみ。"""
    teacher = context.teachers.get(subject.teacher)
    if teacher is None:
        return []

    violations: list[Violation] = []
    if teacher.kind is TeacherKind.PART_TIME and teacher.available_slots:
        for slot in slots:
            if slot not in teacher.available_slots:
                violations.append(Violation(
                    rule_id="H5",
                    subject_code=subject.code,
                    message=f"{teacher.name} は {slot} に出勤できません",
                ))
    if teacher.kind is TeacherKind.SPECIAL and teacher.available_days:
        for slot in slots:
            if slot.day not in teacher.available_days:
                violations.append(Violation(
                    rule_id="H5",
                    subject_code=subject.code,
                    message=f"{teacher.name} は {slot.day}曜日に出勤できません",
                ))
    return violations


def check_h6(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """専任の研究日には配置しない。"""
    teacher = context.teachers.get(subject.teacher)
    if teacher is None or not teacher.research_day:
        return []
    return [
        Violation(
            rule_id="H6",
            subject_code=subject.code,
            message=f"{teacher.name} の研究日（{teacher.research_day}曜日）です",
        )
        for slot in slots
        if slot.day == teacher.research_day
    ]


def _periods_on_day(
    context: Context, timetable: Timetable, subject: Subject, day: str
) -> set[int]:
    """その日に subject の担当教員が持つ時限。subject 自身の既存配置は除く。"""
    periods: set[int] = set()
    if not subject.teacher:
        return periods
    for code, assignment in timetable.assignments.items():
        if code == subject.code:
            continue
        other = context.subjects.get(code)
        if other is None or other.teacher != subject.teacher:
            continue
        if not periods_overlap(subject.term, subject.quarter, other.term, other.quarter):
            continue
        periods.update(slot.period for slot in assignment.slots if slot.day == day)
    return periods


def check_h7(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """同一教員が同一日に 3 コマ以上連続しない。"""
    violations: list[Violation] = []
    for day in {slot.day for slot in slots}:
        occupied = _periods_on_day(context, timetable, subject, day)
        occupied.update(slot.period for slot in slots if slot.day == day)

        run = 0
        for period in sorted(occupied):
            run = run + 1 if (period - 1) in occupied else 1
            if run > MAX_CONSECUTIVE:
                violations.append(Violation(
                    rule_id="H7",
                    subject_code=subject.code,
                    message=(
                        f"{subject.teacher} の {day}曜日が "
                        f"{MAX_CONSECUTIVE + 1} コマ以上連続します"
                    ),
                ))
                break
    return violations


TEACHER_RULES = (check_h1, check_h5, check_h6, check_h7)
```

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_teacher_rules.py -v`
Expected: PASS（14 件）

- [ ] **Step 6: コミットする**

```bash
git add backend/app/constraints/context.py backend/app/constraints/teacher_rules.py backend/tests/test_teacher_rules.py
git commit -m "feat: 制約の共通基盤と教員に関する制約 H1/H5/H6/H7 を追加"
```

---

### Task 10: 学生の履修衝突に関する制約（H2・H3）

**Files:**
- Create: `backend/app/constraints/student_rules.py`
- Test: `backend/tests/test_student_rules.py`

**Interfaces:**
- Consumes: Task 9 の `Context` / `Violation` / `others_at`
- Produces: `check_h2`, `check_h3`, `STUDENT_RULES: tuple[Callable, ...]`（シグネチャは Task 9 と同一）

**判定の詳細:**

- **H2（必修）**: 双方が必修で、学科と年次が一致し、同一コマで開講期間が重なるなら違反。ただし **`base_name` が同一**の場合は違反としない。担当教員ごとにクラスが分かれていても学生はそのうち一つを履修するため、同一コマに集約してよい。ゼミ科目に限らず、英語Ⅰ・情報リテラシーⅠ・商業簿記Ⅰ のように複数クラス開講される通常科目も対象
- **H3（選択必修）**: 双方が選択必修で、学科と年次が一致し、**コースが 1 つ以上共通**していれば違反。どちらかのコースが空の場合は判定不能として違反としない（Stage 0 で `missing_course` 警告済み）

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_student_rules.py`:

```python
from app.constraints.context import Context
from app.constraints.student_rules import check_h2, check_h3
from app.models.enums import Category, Department, Quarter, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make(code, category, year=1, department=Department.MANAGEMENT, base_name=None,
         courses=None, is_seminar=False, term=Term.SPRING, quarter=None, teacher="教員甲"):
    return Subject(
        code=code, name=code, base_name=base_name or code, department=department,
        year=year, term=term, quarter=quarter, category=category,
        courses=courses or [], teacher=teacher, is_seminar=is_seminar,
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


def test_h2_allows_same_seminar_with_different_teachers():
    a = make("A1", Category.REQUIRED, base_name="日本語リテラシーⅠ", is_seminar=True)
    b = make("B1", Category.REQUIRED, base_name="日本語リテラシーⅠ", is_seminar=True)
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_allows_same_non_seminar_course_with_different_teachers():
    # 英語Ⅰ・情報リテラシーⅠ・商業簿記Ⅰ のような複数クラス開講の通常科目
    a = make("A1", Category.REQUIRED, base_name="商業簿記Ⅰ", teacher="教員甲")
    b = make("B1", Category.REQUIRED, base_name="商業簿記Ⅰ", teacher="教員乙")
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_allows_retake_section_to_share_with_the_original():
    # base_name は【再】を除いた名前なので同一科目とみなされる
    a = make("A1", Category.REQUIRED, base_name="日本語リテラシーⅠ", is_seminar=True)
    b = make("B1", Category.REQUIRED, base_name="日本語リテラシーⅠ", is_seminar=False)
    ctx, tt = place([a, b], "A1", TimeSlot("月", 1))
    assert check_h2(ctx, tt, b, (TimeSlot("月", 1),)) == []


def test_h2_flags_two_different_seminars():
    a = make("A1", Category.REQUIRED, base_name="日本語リテラシーⅠ", is_seminar=True)
    b = make("B1", Category.REQUIRED, base_name="プレゼミナール", is_seminar=True)
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
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_student_rules.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.constraints.student_rules'`）

- [ ] **Step 3: 学生の履修衝突制約を実装する**

`backend/app/constraints/student_rules.py`:

```python
"""学生の履修衝突に関する制約 H2・H3。

選択科目（Category.ELECTIVE）には学生側の衝突制約をかけない。
これは仕様上の決定であり、実装漏れではない。
"""
from app.constraints.context import Context, Violation, others_at
from app.models.enums import Category
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable


def _same_cohort(a: Subject, b: Subject) -> bool:
    return a.department is b.department and a.year == b.year


def check_h2(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """必修同士が衝突しない（学科 × 年次）。同一科目の複数クラスは除外。

    担当教員ごとにクラスが分かれていても、学生が履修するのはそのうち
    一つなので同一コマに集約してよい。ゼミ科目に限らず、英語Ⅰや
    商業簿記Ⅰ のような複数クラス開講の通常科目も同じ扱いになる。
    """
    if subject.category is not Category.REQUIRED:
        return []

    violations: list[Violation] = []
    for slot in slots:
        for other in others_at(context, timetable, slot, subject.code):
            if other.category is not Category.REQUIRED:
                continue
            if not _same_cohort(subject, other):
                continue
            if subject.base_name == other.base_name:
                continue
            violations.append(Violation(
                rule_id="H2",
                subject_code=subject.code,
                message=(
                    f"{subject.department.value}{subject.year}年の必修同士が "
                    f"{slot} で重複しています（{other.name}）"
                ),
                related_code=other.code,
            ))
    return violations


def check_h3(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """選択必修同士が衝突しない（学科 × 年次 × コース）。

    どちらかのコースが未設定の場合は判定不能として違反にしない。
    Stage 0 で missing_course 警告を出しているため見落としにはならない。
    """
    if subject.category is not Category.ELECTIVE_REQUIRED or not subject.courses:
        return []

    own_courses = set(subject.courses)
    violations: list[Violation] = []
    for slot in slots:
        for other in others_at(context, timetable, slot, subject.code):
            if other.category is not Category.ELECTIVE_REQUIRED or not other.courses:
                continue
            if not _same_cohort(subject, other):
                continue
            shared = own_courses & set(other.courses)
            if not shared:
                continue
            violations.append(Violation(
                rule_id="H3",
                subject_code=subject.code,
                message=(
                    f"{'・'.join(sorted(shared))} の選択必修同士が "
                    f"{slot} で重複しています（{other.name}）"
                ),
                related_code=other.code,
            ))
    return violations


STUDENT_RULES = (check_h2, check_h3)
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_student_rules.py -v`
Expected: PASS（11 件）

- [ ] **Step 5: コミットする**

```bash
git add backend/app/constraints/student_rules.py backend/tests/test_student_rules.py
git commit -m "feat: 学生の履修衝突に関する制約 H2/H3 を追加"
```

---

### Task 11: 科目固有の制約（H4・H8・H9・H10）と検証器の統合

**Files:**
- Create: `backend/app/constraints/subject_rules.py`
- Create: `backend/app/constraints/validator.py`
- Test: `backend/tests/test_subject_rules.py`
- Test: `backend/tests/test_validator.py`

**Interfaces:**
- Consumes: Task 9・10 のルール群
- Produces:
  - `check_h4`, `check_h8`, `check_h9`, `check_h10`, `SUBJECT_RULES`
  - `ALL_RULES: tuple[Callable, ...]`
  - `check_placement(context, timetable, subject, slots) -> list[Violation]`
  - `is_allowed(context, timetable, subject, slots) -> bool`
  - `validate_all(context, timetable) -> list[Violation]`

**判定の詳細:**

- **H4**: 同じ `joint_id` の科目が既に配置されているなら、候補のコマ集合が完全に一致しなければ違反
- **H8**: 短期大学部かつ `is_remote` の科目は全コマが金曜でなければ違反。大学（経営・会計）は現時点で制約なし（金曜配置は自動的にリモート扱い）。将来の切り替え用に `UNIVERSITY_REMOTE_ONLY_ON_FRIDAY` フラグを用意し、既定は `False`
- **H9**: `fixed_slot` を持つ科目は、そのコマ集合と完全に一致しなければ違反
- **H10**: コマ数が `slots_required` と一致しなければ違反。`requires_consecutive` なら同一曜日の連続時限でなければ違反。コマの重複も違反

- [ ] **Step 1: 失敗するテストを書く（科目固有の制約）**

`backend/tests/test_subject_rules.py`:

```python
from app.constraints.context import Context
from app.constraints.subject_rules import check_h4, check_h8, check_h9, check_h10
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make(code, department=Department.MANAGEMENT, **kwargs):
    base = dict(
        name=code, base_name=code, department=department, year=1, term=Term.SPRING,
        quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_h4_requires_identical_slots_for_joint_pair():
    a = make("A1", department=Department.ACCOUNTING, joint_id="J001")
    b = make("B1", department=Department.MANAGEMENT, joint_id="J001")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    assert check_h4(ctx, tt, b, (TimeSlot("月", 1),)) == []
    assert [v.rule_id for v in check_h4(ctx, tt, b, (TimeSlot("火", 1),))] == ["H4"]


def test_h4_ignores_subject_without_joint_id():
    a = make("A1")
    ctx = Context.from_lists([a], [])
    assert check_h4(ctx, Timetable(), a, (TimeSlot("月", 1),)) == []


def test_h8_junior_remote_must_be_friday():
    subject = make("J1", department=Department.JUNIOR, is_remote=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h8(ctx, tt, subject, (TimeSlot("金", 1),)) == []
    assert [v.rule_id for v in check_h8(ctx, tt, subject, (TimeSlot("木", 1),))] == ["H8"]


def test_h8_junior_non_remote_is_unconstrained():
    subject = make("J2", department=Department.JUNIOR, is_remote=False)
    ctx = Context.from_lists([subject], [])
    assert check_h8(ctx, Timetable(), subject, (TimeSlot("木", 1),)) == []


def test_h8_university_is_unconstrained_by_default():
    subject = make("A1", department=Department.ACCOUNTING, is_remote=False)
    ctx = Context.from_lists([subject], [])
    assert check_h8(ctx, Timetable(), subject, (TimeSlot("金", 1),)) == []
    assert check_h8(ctx, Timetable(), subject, (TimeSlot("月", 1),)) == []


def test_h9_fixed_slot_must_match():
    subject = make("A1", fixed_slot=(TimeSlot("火", 3),))
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h9(ctx, tt, subject, (TimeSlot("火", 3),)) == []
    assert [v.rule_id for v in check_h9(ctx, tt, subject, (TimeSlot("水", 3),))] == ["H9"]


def test_h9_without_fixed_slot_is_unconstrained():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    assert check_h9(ctx, Timetable(), subject, (TimeSlot("水", 3),)) == []


def test_h10_slot_count_must_match():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert [v.rule_id for v in check_h10(ctx, tt, subject, (TimeSlot("水", 2),))] == ["H10"]


def test_h10_consecutive_pair_is_valid():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h10(ctx, tt, subject, (TimeSlot("水", 2), TimeSlot("水", 3))) == []


def test_h10_rejects_non_consecutive_when_required():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    slots = (TimeSlot("水", 2), TimeSlot("水", 4))
    assert [v.rule_id for v in check_h10(ctx, tt, subject, slots)] == ["H10"]


def test_h10_rejects_different_days_when_consecutive_required():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    slots = (TimeSlot("水", 2), TimeSlot("木", 3))
    assert [v.rule_id for v in check_h10(ctx, tt, subject, slots)] == ["H10"]


def test_h10_allows_separate_days_when_not_consecutive_required():
    subject = make("J10405", slots_required=2, requires_consecutive=False)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert check_h10(ctx, tt, subject, (TimeSlot("火", 2), TimeSlot("木", 2))) == []


def test_h10_rejects_duplicate_slots():
    subject = make("J1", slots_required=2, requires_consecutive=False)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    slots = (TimeSlot("火", 2), TimeSlot("火", 2))
    assert [v.rule_id for v in check_h10(ctx, tt, subject, slots)] == ["H10"]
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_subject_rules.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.constraints.subject_rules'`）

- [ ] **Step 3: 科目固有の制約を実装する**

`backend/app/constraints/subject_rules.py`:

```python
"""科目固有の制約 H4・H8・H9・H10。"""
from app.constraints.context import Context, Violation
from app.models.enums import Department
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

FRIDAY = "金"

UNIVERSITY_REMOTE_ONLY_ON_FRIDAY = False
"""True にすると、大学は遠隔=○ の科目のみ金曜に配置可能になる。

現時点の運用は「金曜に置かれた科目を自動的にリモート扱いする」ため
False。将来の切り替え用に残してある。
"""


def check_h4(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """合同科目のペアは同曜日・同時限。"""
    if not subject.joint_id:
        return []

    candidate = set(slots)
    violations: list[Violation] = []
    for code, other in context.subjects.items():
        if code == subject.code or other.joint_id != subject.joint_id:
            continue
        placed = timetable.slot_of(code)
        if not placed:
            continue
        if set(placed) != candidate:
            violations.append(Violation(
                rule_id="H4",
                subject_code=subject.code,
                message=(
                    f"合同科目 {other.name} は "
                    f"{'・'.join(str(s) for s in placed)} に配置されています"
                ),
                related_code=code,
            ))
    return violations


def check_h8(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """短大の遠隔=○ は必ず金曜。大学は既定で制約なし。"""
    if subject.department is Department.JUNIOR:
        if not subject.is_remote:
            return []
        return [
            Violation(
                rule_id="H8",
                subject_code=subject.code,
                message=f"遠隔科目のため金曜に配置してください（候補: {slot}）",
            )
            for slot in slots
            if slot.day != FRIDAY
        ]

    if UNIVERSITY_REMOTE_ONLY_ON_FRIDAY and not subject.is_remote:
        return [
            Violation(
                rule_id="H8",
                subject_code=subject.code,
                message=f"遠隔不可の科目は金曜に配置できません（候補: {slot}）",
            )
            for slot in slots
            if slot.day == FRIDAY
        ]
    return []


def check_h9(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """Excel で入力済みの確定枠は動かせない。"""
    if subject.fixed_slot is None:
        return []
    if set(slots) == set(subject.fixed_slot):
        return []
    fixed = "・".join(str(s) for s in subject.fixed_slot)
    return [Violation(
        rule_id="H9",
        subject_code=subject.code,
        message=f"確定枠（{fixed}）から動かすことはできません",
    )]


def check_h10(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """コマ数と連続要件を満たすこと。"""
    if len(slots) != subject.slots_required:
        return [Violation(
            rule_id="H10",
            subject_code=subject.code,
            message=f"必要コマ数は {subject.slots_required} ですが {len(slots)} が指定されました",
        )]

    if len(set(slots)) != len(slots):
        return [Violation(
            rule_id="H10",
            subject_code=subject.code,
            message="同じコマが重複して指定されました",
        )]

    if not subject.requires_consecutive:
        return []

    days = {slot.day for slot in slots}
    periods = sorted(slot.period for slot in slots)
    is_consecutive = len(days) == 1 and all(
        periods[i] + 1 == periods[i + 1] for i in range(len(periods) - 1)
    )
    if is_consecutive:
        return []
    return [Violation(
        rule_id="H10",
        subject_code=subject.code,
        message="▲科目のため同一曜日の連続コマに配置してください",
    )]


SUBJECT_RULES = (check_h4, check_h8, check_h9, check_h10)
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_subject_rules.py -v`
Expected: PASS（13 件）

- [ ] **Step 5: 検証器のテストを書く**

`backend/tests/test_validator.py`:

```python
from app.constraints.context import Context
from app.constraints.validator import ALL_RULES, check_placement, is_allowed, validate_all
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_all_rules_covers_h1_through_h10():
    assert len(ALL_RULES) == 10


def test_check_placement_aggregates_multiple_rule_violations():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [Teacher("教員甲", TeacherKind.FULL_TIME, research_day="月")])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    ids = sorted(v.rule_id for v in check_placement(ctx, tt, b, (TimeSlot("月", 1),)))
    assert ids == ["H1", "H2", "H6"]


def test_is_allowed_is_false_when_any_rule_fires():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert is_allowed(ctx, tt, b, (TimeSlot("月", 1),)) is False
    assert is_allowed(ctx, tt, b, (TimeSlot("火", 1),)) is True


def test_validate_all_finds_violations_in_a_finished_timetable():
    # H2 だけを見たいので担当教員は別にする。同じ教員にすると H1 も同時に立つ
    a, b = make("A1", teacher="教員甲"), make("B1", teacher="教員乙")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    tt.place("B1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)

    violations = validate_all(ctx, tt)
    assert {v.rule_id for v in violations} == {"H2"}
    # 双方向で報告されるため 2 件
    assert len(violations) == 2


def test_h1_applies_even_when_the_teacher_is_absent_from_the_roster():
    # 名簿外教員の「制約なし」は H5・H6 の例外であって、二重予約は許されない
    a, b = make("A1", teacher="名簿外教員"), make("B1", teacher="名簿外教員")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)

    assert "H1" in {v.rule_id for v in check_placement(ctx, tt, b, (TimeSlot("月", 1),))}


def test_validate_all_returns_empty_for_clean_timetable():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
    tt.place("B1", (TimeSlot("火", 1),), AssignmentSource.GEMINI)
    assert validate_all(ctx, tt) == []
```

- [ ] **Step 6: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_validator.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.constraints.validator'`）

- [ ] **Step 7: 検証器を実装する**

`backend/app/constraints/validator.py`:

```python
"""制約検証の唯一の入口。

Gemini の応答検証、ソルバーの枝刈り、フロントの D&D 編集判定は
すべてこのモジュールを経由する。ここを通らない検証を書いてはならない。
"""
from app.constraints.context import Context, Violation
from app.constraints.student_rules import STUDENT_RULES
from app.constraints.subject_rules import SUBJECT_RULES
from app.constraints.teacher_rules import TEACHER_RULES
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import Timetable

ALL_RULES = TEACHER_RULES + STUDENT_RULES + SUBJECT_RULES


def check_placement(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> list[Violation]:
    """subject を slots に置いた場合の違反をすべて返す。

    timetable 上の subject 自身の既存配置は評価から除外される。
    """
    violations: list[Violation] = []
    for rule in ALL_RULES:
        violations.extend(rule(context, timetable, subject, slots))
    return violations


def is_allowed(
    context: Context, timetable: Timetable, subject: Subject, slots: tuple[TimeSlot, ...]
) -> bool:
    """1 件でも違反があれば False。ソルバーの枝刈りに使う。"""
    for rule in ALL_RULES:
        if rule(context, timetable, subject, slots):
            return False
    return True


def validate_all(context: Context, timetable: Timetable) -> list[Violation]:
    """完成した時間割を通しで検証する。違反は関係する両科目から報告される。"""
    violations: list[Violation] = []
    for code, assignment in timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None:
            continue
        violations.extend(check_placement(context, timetable, subject, assignment.slots))
    return violations
```

- [ ] **Step 8: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 9: コミットする**

```bash
git add backend/app/constraints backend/tests/test_subject_rules.py backend/tests/test_validator.py
git commit -m "feat: 科目固有の制約 H4/H8/H9/H10 と検証器の統合入口を追加"
```

---

### Task 12: 候補コマ集合の列挙と Stage 1（事前ロック）

**Files:**
- Create: `backend/app/scheduler/__init__.py`
- Create: `backend/app/scheduler/candidates.py`
- Create: `backend/app/scheduler/prelock.py`
- Test: `backend/tests/test_candidates.py`
- Test: `backend/tests/test_prelock.py`

**Interfaces:**
- Consumes: Task 11 の `is_allowed`、Task 9 の `Context`
- Produces:
  - `candidate_slot_sets(subject) -> list[tuple[TimeSlot, ...]]` — 制約を見ずに構造だけで取り得るコマ集合を列挙
  - `feasible_slot_sets(context, timetable, subject) -> list[tuple[TimeSlot, ...]]` — 上記のうち `is_allowed` を通るもの
  - `prelock(context, subjects) -> tuple[Timetable, list[str]]` — 事前ロック済みの時間割と、ロックできなかった非常勤科目のコードを返す

**事前ロックの対象と順序:**

1. `fixed_slot` を持つ科目（`is_intensive` は対象外）
2. 非常勤教員の担当科目。候補数の少ない科目から順に確定させる

**特任教員は対象外**（仕様書 §7 Stage 1）。曜日しか定まらないため Stage 2〜4 で扱う。

- [ ] **Step 1: 失敗するテストを書く（候補列挙）**

`backend/tests/test_candidates.py`:

```python
from app.constraints.context import Context
from app.models.enums import Category, Department, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import candidate_slot_sets, feasible_slot_sets


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_single_slot_subject_has_25_candidates():
    assert len(candidate_slot_sets(make("A1"))) == 25


def test_fixed_slot_subject_has_exactly_one_candidate():
    subject = make("A1", fixed_slot=(TimeSlot("火", 3),))
    assert candidate_slot_sets(subject) == [(TimeSlot("火", 3),)]


def test_consecutive_double_subject_has_20_candidates():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    candidates = candidate_slot_sets(subject)
    # 5 曜日 × 連続ペア 4 通り
    assert len(candidates) == 20
    assert (TimeSlot("月", 1), TimeSlot("月", 2)) in candidates
    assert (TimeSlot("月", 1), TimeSlot("月", 3)) not in candidates


def test_non_consecutive_double_subject_enumerates_all_pairs():
    subject = make("J2", slots_required=2, requires_consecutive=False)
    candidates = candidate_slot_sets(subject)
    assert len(candidates) == 300  # 25 から 2 つ選ぶ組合せ
    assert (TimeSlot("火", 2), TimeSlot("木", 2)) in candidates


def test_intensive_subject_has_no_candidates():
    assert candidate_slot_sets(make("A1", is_intensive=True)) == []


def test_feasible_filters_by_constraints():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    feasible = feasible_slot_sets(ctx, tt, b)
    assert (TimeSlot("月", 1),) not in feasible
    assert (TimeSlot("月", 2),) in feasible
    assert len(feasible) == 24
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_candidates.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.scheduler'`）

- [ ] **Step 3: 候補列挙を実装する**

`backend/app/scheduler/__init__.py` は空ファイル。

`backend/app/scheduler/candidates.py`:

```python
"""科目 1 件が取り得るコマ集合を列挙する。

構造だけを見る candidate_slot_sets と、制約検証を通した
feasible_slot_sets の 2 段構えにしている。前者は科目ごとに一度
計算すれば使い回せるため、探索の内側で再計算しない。
"""
from itertools import combinations

from app.constraints.context import Context
from app.constraints.validator import is_allowed
from app.models.subject import Subject
from app.models.timeslot import DAYS, PERIODS, TimeSlot
from app.models.timetable import Timetable


def candidate_slot_sets(subject: Subject) -> list[tuple[TimeSlot, ...]]:
    """制約を見ずに、コマ数と連続要件だけから候補を列挙する。"""
    if subject.is_intensive:
        return []
    if subject.fixed_slot is not None:
        return [tuple(subject.fixed_slot)]

    all_slots = [TimeSlot(day, period) for day in DAYS for period in PERIODS]

    if subject.slots_required == 1:
        return [(slot,) for slot in all_slots]

    if subject.requires_consecutive:
        result: list[tuple[TimeSlot, ...]] = []
        for day in DAYS:
            for start in PERIODS[: len(PERIODS) - subject.slots_required + 1]:
                result.append(tuple(
                    TimeSlot(day, start + offset)
                    for offset in range(subject.slots_required)
                ))
        return result

    return [tuple(combo) for combo in combinations(all_slots, subject.slots_required)]


def feasible_slot_sets(
    context: Context, timetable: Timetable, subject: Subject
) -> list[tuple[TimeSlot, ...]]:
    """現在の配置状況で実際に置ける候補だけを返す。"""
    return [
        slots for slots in candidate_slot_sets(subject)
        if is_allowed(context, timetable, subject, slots)
    ]
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_candidates.py -v`
Expected: PASS（6 件）

- [ ] **Step 5: 事前ロックのテストを書く**

`backend/tests/test_prelock.py`:

```python
from app.constraints.context import Context
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource
from app.scheduler.prelock import prelock


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_fixed_slot_subject_is_locked():
    subject = make("A1", fixed_slot=(TimeSlot("火", 3),))
    ctx = Context.from_lists([subject], [])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.slot_of("A1") == (TimeSlot("火", 3),)
    assert timetable.assignments["A1"].source is AssignmentSource.PRELOCK
    assert unplaced == []


def test_intensive_subject_is_not_placed():
    subject = make("A1", is_intensive=True)
    ctx = Context.from_lists([subject], [])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.placed_codes() == set()
    assert unplaced == []


def test_part_time_subject_is_placed_in_available_slot():
    subject = make("A1", teacher="非常勤甲")
    teacher = Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)})
    ctx = Context.from_lists([subject], [teacher])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.slot_of("A1") == (TimeSlot("金", 1),)
    assert unplaced == []


def test_full_time_and_special_subjects_are_left_for_later_stages():
    a = make("A1", teacher="専任甲")
    b = make("B1", teacher="特任甲")
    ctx = Context.from_lists([a, b], [
        Teacher("専任甲", TeacherKind.FULL_TIME, research_day="月"),
        Teacher("特任甲", TeacherKind.SPECIAL, available_days={"水"}),
    ])
    timetable, unplaced = prelock(ctx, [a, b])
    assert timetable.placed_codes() == set()
    assert unplaced == []


def test_part_time_without_availability_is_left_for_later_stages():
    subject = make("A1", teacher="非常勤甲")
    ctx = Context.from_lists([subject], [Teacher("非常勤甲", TeacherKind.PART_TIME)])
    timetable, unplaced = prelock(ctx, [subject])
    assert timetable.placed_codes() == set()
    assert unplaced == []


def test_conflicting_part_time_subjects_report_the_leftover():
    # 同一非常勤が同じ 1 コマしか出勤できないのに担当科目が 2 件
    a = make("A1", teacher="非常勤甲")
    b = make("B1", teacher="非常勤甲")
    teacher = Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)})
    ctx = Context.from_lists([a, b], [teacher])
    timetable, unplaced = prelock(ctx, [a, b])
    assert len(timetable.placed_codes()) == 1
    assert len(unplaced) == 1


def test_most_constrained_part_time_subject_is_placed_first():
    # A1 は 1 コマだけ、B1 は 2 コマ選べる。A1 を先に確定させれば両方置ける
    a = make("A1", teacher="非常勤甲")
    b = make("B1", teacher="非常勤乙")
    ctx = Context.from_lists([a, b], [
        Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)}),
        Teacher("非常勤乙", TeacherKind.PART_TIME,
                available_slots={TimeSlot("金", 1), TimeSlot("金", 2)}),
    ])
    timetable, unplaced = prelock(ctx, [b, a])
    assert timetable.slot_of("A1") == (TimeSlot("金", 1),)
    assert unplaced == []
```

- [ ] **Step 6: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_prelock.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.scheduler.prelock'`）

- [ ] **Step 7: 事前ロックを実装する**

`backend/app/scheduler/prelock.py`:

```python
"""Stage 1: Python だけで決定的に配置できる科目を確定させる。

ここで確定した配置は Gemini に渡らず、占有済みマップとしてのみ
参照される。トークン削減と、確定枠が動かされないことの保証を兼ねる。
"""
from app.constraints.context import Context
from app.models.enums import TeacherKind
from app.models.subject import Subject
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets


def _is_part_time_with_availability(context: Context, subject: Subject) -> bool:
    teacher = context.teachers.get(subject.teacher)
    return (
        teacher is not None
        and teacher.kind is TeacherKind.PART_TIME
        and bool(teacher.available_slots)
    )


def prelock(context: Context, subjects: list[Subject]) -> tuple[Timetable, list[str]]:
    """確定枠と非常勤の担当科目を配置し、置けなかったコードを返す。

    特任教員は曜日しか定まらないため対象外とし、Stage 2〜4 に委ねる。
    """
    timetable = Timetable()
    unplaced: list[str] = []

    targets = [s for s in subjects if not s.is_intensive]

    for subject in [s for s in targets if s.fixed_slot is not None]:
        timetable.place(subject.code, tuple(subject.fixed_slot), AssignmentSource.PRELOCK)

    part_time = [
        s for s in targets
        if s.fixed_slot is None and _is_part_time_with_availability(context, s)
    ]
    # 候補が少ない科目から確定させる（最小残余値ヒューリスティック）
    part_time.sort(key=lambda s: len(feasible_slot_sets(context, timetable, s)))

    for subject in part_time:
        options = feasible_slot_sets(context, timetable, subject)
        if not options:
            unplaced.append(subject.code)
            continue
        timetable.place(subject.code, options[0], AssignmentSource.PRELOCK)

    return timetable, unplaced
```

- [ ] **Step 8: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_prelock.py -v`
Expected: PASS（7 件）

- [ ] **Step 9: コミットする**

```bash
git add backend/app/scheduler backend/tests/test_candidates.py backend/tests/test_prelock.py
git commit -m "feat: 候補コマ列挙と Stage 1 の事前ロックを追加"
```

---

### Task 13: Stage 5（ソルバーによるフォールバック）

**Files:**
- Create: `backend/app/scheduler/solver.py`
- Test: `backend/tests/test_solver.py`

**Interfaces:**
- Consumes: Task 12 の `feasible_slot_sets` / `candidate_slot_sets`、Task 11 の `is_allowed`
- Produces: `solve(context, timetable, codes, *, node_limit=200_000) -> list[str]` — `timetable` を破壊的に埋め、配置できなかったコードのリストを返す

**アルゴリズム:** 最小残余値ヒューリスティックによる貪欲配置。各ステップで「実行可能な候補が最も少ない科目」を選び、その最初の候補に確定させる。候補が 1 つも無い科目はその場で未配置として記録し、残りの処理を続ける。反復回数が `node_limit` を超えたら打ち切り、残りを未配置として返す。**必ず有限時間で終了し、部分解を返す**ことがこの関数の契約である。

**バックトラッキングを採用しない理由**：実測すると 1 ステップあたり 0.21 秒（残り全科目の候補再計算）かかり、443 科目規模ではバックトラッキング探索が現実的な時間で終わらない（`node_limit=200_000` なら最悪 11 時間）。貪欲配置なら 90 秒で 443 科目中 435 科目を配置でき、制約違反は 0 だった。未配置の 8 科目は候補が 1 つも無いもので、バックトラッキングでも配置できない。

配置順の決定性を保つため、候補数が同じ科目は授業コードの昇順で選ぶ。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_solver.py`:

```python
from app.constraints.context import Context
from app.constraints.validator import validate_all
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.solver import solve


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher=f"教員{code}",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_places_a_single_subject():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert solve(ctx, tt, ["A1"]) == []
    assert tt.is_placed("A1")


def test_result_has_no_violations():
    subjects = [make(f"A{i}", teacher="教員甲") for i in range(5)]
    ctx = Context.from_lists(subjects, [Teacher("教員甲", TeacherKind.FULL_TIME)])
    tt = Timetable()
    assert solve(ctx, tt, [s.code for s in subjects]) == []
    assert validate_all(ctx, tt) == []


def test_reports_unplaced_when_no_solution_exists():
    # 同一教員・同一学科年次の必修が 26 件。25 コマしかないので 1 件は置けない
    subjects = [make(f"A{i}", teacher="教員甲") for i in range(26)]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    unplaced = solve(ctx, tt, [s.code for s in subjects])
    assert len(unplaced) >= 1
    assert len(tt.placed_codes()) + len(unplaced) == 26
    assert validate_all(ctx, tt) == []


def test_respects_existing_placements():
    a, b = make("A1", teacher="教員甲"), make("B1", teacher="教員甲")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    assert solve(ctx, tt, ["B1"]) == []
    assert tt.slot_of("B1") != (TimeSlot("月", 1),)
    assert tt.assignments["A1"].source is AssignmentSource.PRELOCK


def test_marks_source_as_solver():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    solve(ctx, tt, ["A1"])
    assert tt.assignments["A1"].source is AssignmentSource.SOLVER


def test_places_consecutive_double_slot_subject():
    subject = make("J1", slots_required=2, requires_consecutive=True)
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    assert solve(ctx, tt, ["J1"]) == []
    slots = tt.slot_of("J1")
    assert len(slots) == 2
    assert slots[0].day == slots[1].day
    assert abs(slots[0].period - slots[1].period) == 1


def test_solves_tightly_constrained_pair():
    # 非常勤甲は金1のみ。必修同士なので同じコマには置けない。
    # 候補の少ない A1 を先に確定させないと解けない配置
    a = make("A1", teacher="非常勤甲")
    b = make("B1", teacher="非常勤乙")
    ctx = Context.from_lists([a, b], [
        Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 1)}),
        Teacher("非常勤乙", TeacherKind.PART_TIME,
                available_slots={TimeSlot("金", 1), TimeSlot("金", 2)}),
    ])
    tt = Timetable()
    assert solve(ctx, tt, ["B1", "A1"]) == []
    assert tt.slot_of("A1") == (TimeSlot("金", 1),)
    assert tt.slot_of("B1") == (TimeSlot("金", 2),)


def test_terminates_on_node_limit():
    subjects = [make(f"A{i}", teacher="教員甲") for i in range(26)]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    unplaced = solve(ctx, tt, [s.code for s in subjects], node_limit=50)
    assert len(tt.placed_codes()) + len(unplaced) == 26


def test_stops_at_node_limit_and_reports_the_rest():
    # 反復上限に達したら、残りは未配置として返す
    subjects = [make(f"A{i}") for i in range(10)]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    unplaced = solve(ctx, tt, [s.code for s in subjects], node_limit=3)
    assert len(tt.placed_codes()) == 3
    assert len(unplaced) == 7


def test_a_subject_with_no_options_does_not_block_the_others():
    # 候補ゼロの科目があっても、残りは配置される
    blocked = make("A1", teacher="非常勤甲")
    other = make("A2", teacher="教員乙")
    teacher = Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("月", 1)})
    ctx = Context.from_lists([blocked, other], [teacher])
    tt = Timetable()
    tt.place("A2", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)
    # 非常勤甲は月1しか出勤できないが、そこは A2 が必修で埋めている
    unplaced = solve(ctx, tt, ["A1"])
    assert unplaced == ["A1"]
    assert tt.is_placed("A2")


def test_result_is_deterministic():
    subjects = [make(f"A{i}") for i in range(8)]
    codes = [s.code for s in subjects]

    def run(order):
        ctx = Context.from_lists(subjects, [])
        tt = Timetable()
        solve(ctx, tt, order)
        return {c: tt.slot_of(c) for c in codes}

    assert run(codes) == run(list(reversed(codes)))
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_solver.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.scheduler.solver'`）

- [ ] **Step 3: ソルバーを実装する**

`backend/app/scheduler/solver.py`:

```python
"""Stage 5: 最小残余値ヒューリスティックによる決定的な貪欲配置。

Gemini が収束しなかった科目を確実に埋めるための最終手段。
候補の少ない科目から順に確定させ、置けない科目は未配置として記録して
先へ進む。必ず有限時間で終わり、部分解を返す。
"""
from app.constraints.context import Context
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.candidates import feasible_slot_sets

DEFAULT_NODE_LIMIT = 200_000


def solve(
    context: Context,
    timetable: Timetable,
    codes: list[str],
    *,
    node_limit: int = DEFAULT_NODE_LIMIT,
) -> list[str]:
    """codes を timetable に配置し、置けなかったコードを返す。

    既存の配置は動かさない。毎回「候補が最も少ない科目」を選んで確定
    させるため、出勤可能コマが 1 つしかない非常勤の科目などが先に決まる。
    候補が 1 つも無い科目は未配置として記録し、残りの処理を続ける。
    反復回数が node_limit に達した場合は、そこまでの結果を返す。
    """
    targets = [
        code for code in codes
        if code in context.subjects
        and not context.subjects[code].is_intensive
        and not timetable.is_placed(code)
    ]

    unplaced: list[str] = []
    remaining = list(targets)
    steps = 0

    while remaining and steps < node_limit:
        steps += 1
        options_by_code = {
            code: feasible_slot_sets(context, timetable, context.subjects[code])
            for code in remaining
        }
        # 候補数が同じ場合は授業コード順にして結果を決定的にする
        code = min(remaining, key=lambda c: (len(options_by_code[c]), c))
        remaining.remove(code)

        options = options_by_code[code]
        if not options:
            unplaced.append(code)
            continue
        timetable.place(code, options[0], AssignmentSource.SOLVER)

    unplaced.extend(remaining)
    return unplaced
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_solver.py -v`
Expected: PASS（11 件）

- [ ] **Step 5: 実データ規模で完走することを確認する**

Run:

```bash
cd backend && ../.venv/bin/python -c "
import time
from app.constraints.context import Context
from app.constraints.validator import validate_all
from app.ingest.curriculum_reader import read_curriculum
from app.ingest.joint_pairing import assign_joint_ids
from app.ingest.teacher_reader import read_teachers
from app.scheduler.prelock import prelock
from app.scheduler.solver import solve

subjects = read_curriculum('../カリキュラム一覧(整形済み).xlsx')
assign_joint_ids(subjects)
teachers = read_teachers('../教員一覧(整形済み).xlsx')
ctx = Context.from_lists(subjects, teachers)

start = time.time()
tt, leftover = prelock(ctx, subjects)
codes = [s.code for s in subjects if not s.is_intensive and not tt.is_placed(s.code)]
unplaced = solve(ctx, tt, codes)
print(f'所要 {time.time() - start:.1f}秒 / 配置 {len(tt.placed_codes())} / 未配置 {len(unplaced)}')
print('残存違反', len(validate_all(ctx, tt)))
"
```

Expected: 90 秒前後で終了し、配置 605 件・未配置 8 件・**残存違反 0** となること。未配置の 8 件は候補が 1 つも無い科目で、非常勤教員の学期内担当コマ数が出勤可能コマ数を超えているという事務局側のデータ課題に起因する。件数が多少ずれても構わないが、**残存違反が 0 であること**と**有限時間で終わること**は必須である。

- [ ] **Step 6: コミットする**

```bash
git add backend/app/scheduler/solver.py backend/tests/test_solver.py
git commit -m "feat: Stage 5 のバックトラッキングソルバーを追加"
```

---

### Task 14: セッションロガー

**Files:**
- Create: `backend/app/logging/__init__.py`
- Create: `backend/app/logging/session_logger.py`
- Test: `backend/tests/test_session_logger.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `LogEvent(level: str, message: str, timestamp: str, stage: str | None)` — frozen dataclass、`to_dict() -> dict`
  - `SessionLogger(session_id: str, log_dir: Path | None = None)`
    - `.info(message, stage=None)` / `.warn(...)` / `.error(...)`
    - `.events -> list[LogEvent]`
    - `.subscribe() -> queue.SimpleQueue` — SSE 配信用。以降のイベントが流れる
    - `.close()` — 購読者に終了を示す `None` を送り、ファイルを閉じる
    - `.log_path -> Path`

**設計上の注意:** 生成処理は FastAPI のワーカースレッドで動くため、イベントの追加はロックで保護する。購読者への配信は `queue.SimpleQueue`（スレッドセーフ）を使う。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_session_logger.py`:

```python
import json

from app.logging.session_logger import LogEvent, SessionLogger


def test_records_events_in_order(tmp_path):
    logger = SessionLogger("s1", log_dir=tmp_path)
    logger.info("開始", stage="Stage 0")
    logger.warn("教員が見つかりません")
    logger.error("API キーが無効です")

    assert [e.level for e in logger.events] == ["INFO", "WARN", "ERROR"]
    assert logger.events[0].stage == "Stage 0"
    assert logger.events[1].stage is None
    logger.close()


def test_writes_to_file(tmp_path):
    logger = SessionLogger("s2", log_dir=tmp_path)
    logger.info("テスト行")
    logger.close()

    assert logger.log_path.exists()
    content = logger.log_path.read_text(encoding="utf-8")
    assert "テスト行" in content
    assert "INFO" in content


def test_subscriber_receives_later_events(tmp_path):
    logger = SessionLogger("s3", log_dir=tmp_path)
    logger.info("購読前")
    stream = logger.subscribe()
    logger.info("購読後")

    received = stream.get(timeout=1)
    assert received.message == "購読後"
    logger.close()


def test_close_sends_sentinel_to_subscribers(tmp_path):
    logger = SessionLogger("s4", log_dir=tmp_path)
    stream = logger.subscribe()
    logger.close()
    assert stream.get(timeout=1) is None


def test_event_to_dict_is_json_serializable(tmp_path):
    logger = SessionLogger("s5", log_dir=tmp_path)
    logger.info("メッセージ", stage="Stage 2")
    payload = logger.events[0].to_dict()
    assert json.loads(json.dumps(payload))["message"] == "メッセージ"
    assert set(payload) == {"level", "message", "timestamp", "stage"}
    logger.close()


def test_timestamp_is_iso_format(tmp_path):
    from datetime import datetime

    logger = SessionLogger("s6", log_dir=tmp_path)
    logger.info("x")
    datetime.fromisoformat(logger.events[0].timestamp)
    logger.close()
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_session_logger.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.logging'`）

- [ ] **Step 3: ロガーを実装する**

`backend/app/logging/__init__.py` は空ファイル。

`backend/app/logging/session_logger.py`:

```python
"""生成セッション単位のログ。フロントへの SSE 配信とファイル保存を兼ねる。

不具合の原因追跡を目的とするため、どの Stage で何が起きたかを
必ず残す。イベントの追加はワーカースレッドから呼ばれるためロックで守る。
"""
import queue
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


@dataclass(frozen=True, slots=True)
class LogEvent:
    level: str
    message: str
    timestamp: str
    stage: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class SessionLogger:
    """1 回の生成に対応するロガー。"""

    def __init__(self, session_id: str, log_dir: Path | None = None) -> None:
        self.session_id = session_id
        directory = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.log_path = directory / f"{stamp}_{session_id}.log"

        self._events: list[LogEvent] = []
        self._subscribers: list[queue.SimpleQueue] = []
        self._lock = threading.Lock()
        self._file = self.log_path.open("a", encoding="utf-8")

    @property
    def events(self) -> list[LogEvent]:
        with self._lock:
            return list(self._events)

    def subscribe(self) -> queue.SimpleQueue:
        """以降のイベントを受け取るキューを返す。close() で None が届く。"""
        stream: queue.SimpleQueue = queue.SimpleQueue()
        with self._lock:
            self._subscribers.append(stream)
        return stream

    def log(self, level: str, message: str, *, stage: str | None = None) -> None:
        event = LogEvent(
            level=level,
            message=message,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            stage=stage,
        )
        with self._lock:
            self._events.append(event)
            subscribers = list(self._subscribers)
            prefix = f"[{event.timestamp}] {level:<5}"
            suffix = f" ({stage})" if stage else ""
            self._file.write(f"{prefix} {message}{suffix}\n")
            self._file.flush()
        for stream in subscribers:
            stream.put(event)

    def info(self, message: str, *, stage: str | None = None) -> None:
        self.log("INFO", message, stage=stage)

    def warn(self, message: str, *, stage: str | None = None) -> None:
        self.log("WARN", message, stage=stage)

    def error(self, message: str, *, stage: str | None = None) -> None:
        self.log("ERROR", message, stage=stage)

    def close(self) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
            if not self._file.closed:
                self._file.close()
        for stream in subscribers:
            stream.put(None)
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_session_logger.py -v`
Expected: PASS（6 件）

- [ ] **Step 5: コミットする**

```bash
git add backend/app/logging backend/tests/test_session_logger.py
git commit -m "feat: セッションロガーを追加"
```

---

### Task 15: パイプラインとモックモード

**Files:**
- Create: `backend/app/scheduler/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 8 の `collect_warnings`、Task 12 の `prelock`、Task 13 の `solve`、Task 11 の `validate_all`、Task 14 の `SessionLogger`
- Produces:
  - `GenerationMode` — `MOCK = "mock"` / `OPTIMIZE = "optimize"` / `INHERIT = "inherit"`
  - `GenerationResult` — `timetable`, `unplaced: list[str]`, `violations: list[Violation]`, `warnings: list[Warning]`, `intensive_codes: list[str]`
  - `run_pipeline(subjects, teachers, mode, logger, *, gemini_placer=None, inherit_plan=None) -> GenerationResult`

**`gemini_placer` の契約:** `(context, timetable, codes, logger) -> list[str]`（配置できなかったコードを返す）。Task 17 で実装を差し込む。`None` の場合は Stage 2〜4 を丸ごと飛ばす。この注入により、パイプラインのテストに Gemini は不要になる。

**Stage 2〜4 の対象科目の順序:** 必修 → 選択必修 → 選択。同一区分の中では学科・開講期でまとめる。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_pipeline.py`:

```python
from app.constraints.validator import validate_all
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource
from app.logging.session_logger import SessionLogger
from app.scheduler.pipeline import GenerationMode, run_pipeline


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher=f"教員{code}",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_mock_mode_places_everything_with_solver(tmp_path):
    subjects = [make(f"A{i}") for i in range(5)]
    logger = SessionLogger("t1", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert result.unplaced == []
    assert result.violations == []
    assert len(result.timetable.placed_codes()) == 5
    assert all(
        a.source is AssignmentSource.SOLVER for a in result.timetable.assignments.values()
    )
    logger.close()


def test_intensive_subjects_are_excluded_from_grid(tmp_path):
    subjects = [make("A1"), make("A2", is_intensive=True)]
    logger = SessionLogger("t2", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert result.intensive_codes == ["A2"]
    assert result.timetable.placed_codes() == {"A1"}
    logger.close()


def test_fixed_slot_subject_keeps_prelock_source(tmp_path):
    subjects = [make("A1", fixed_slot=(TimeSlot("火", 3),))]
    logger = SessionLogger("t3", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert result.timetable.slot_of("A1") == (TimeSlot("火", 3),)
    assert result.timetable.assignments["A1"].source is AssignmentSource.PRELOCK
    logger.close()


def test_warnings_are_collected_but_do_not_stop_generation(tmp_path):
    subjects = [make("A1", teacher="未登録教員")]
    logger = SessionLogger("t4", log_dir=tmp_path)
    result = run_pipeline(subjects, [], GenerationMode.MOCK, logger)

    assert [w.kind for w in result.warnings] == ["unknown_teacher"]
    assert result.timetable.is_placed("A1")
    logger.close()


def test_optimize_mode_uses_gemini_placer_then_solver(tmp_path):
    subjects = [make("A1"), make("A2")]
    calls = []

    def fake_placer(context, timetable, codes, logger):
        calls.append(list(codes))
        timetable.place("A1", (TimeSlot("月", 1),), AssignmentSource.GEMINI)
        return ["A2"]  # A2 は収束しなかったことにする

    logger = SessionLogger("t5", log_dir=tmp_path)
    result = run_pipeline(
        subjects, [], GenerationMode.OPTIMIZE, logger, gemini_placer=fake_placer
    )

    assert calls  # Gemini 段階が呼ばれた
    assert result.timetable.assignments["A1"].source is AssignmentSource.GEMINI
    assert result.timetable.assignments["A2"].source is AssignmentSource.SOLVER
    assert result.unplaced == []
    logger.close()


def test_gemini_placer_is_called_by_category_in_order(tmp_path):
    subjects = [
        make("E1", category=Category.ELECTIVE),
        make("R1", category=Category.REQUIRED),
        make("S1", category=Category.ELECTIVE_REQUIRED, courses=["情報コース"]),
    ]
    seen = []

    def fake_placer(context, timetable, codes, logger):
        seen.append(sorted(codes))
        return list(codes)

    logger = SessionLogger("t6", log_dir=tmp_path)
    run_pipeline(subjects, [], GenerationMode.OPTIMIZE, logger, gemini_placer=fake_placer)

    assert seen == [["R1"], ["S1"], ["E1"]]
    logger.close()


def test_falls_back_to_solver_when_gemini_places_nothing(tmp_path):
    subjects = [make("A1"), make("A2")]

    def failing_placer(context, timetable, codes, logger):
        return list(codes)

    logger = SessionLogger("t7", log_dir=tmp_path)
    result = run_pipeline(
        subjects, [], GenerationMode.OPTIMIZE, logger, gemini_placer=failing_placer
    )

    assert len(result.timetable.placed_codes()) == 2
    assert result.violations == []
    logger.close()


def test_logger_records_each_stage(tmp_path):
    logger = SessionLogger("t8", log_dir=tmp_path)
    run_pipeline([make("A1")], [], GenerationMode.MOCK, logger)
    stages = {e.stage for e in logger.events}
    assert {"Stage 0", "Stage 1", "Stage 5", "Stage 6"} <= stages
    logger.close()


def test_part_time_subject_is_prelocked(tmp_path):
    subjects = [make("A1", teacher="非常勤甲")]
    teachers = [Teacher("非常勤甲", TeacherKind.PART_TIME, available_slots={TimeSlot("金", 2)})]
    logger = SessionLogger("t9", log_dir=tmp_path)
    result = run_pipeline(subjects, teachers, GenerationMode.MOCK, logger)

    assert result.timetable.slot_of("A1") == (TimeSlot("金", 2),)
    assert result.timetable.assignments["A1"].source is AssignmentSource.PRELOCK
    logger.close()
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.scheduler.pipeline'`）

- [ ] **Step 3: パイプラインを実装する**

`backend/app/scheduler/pipeline.py`:

```python
"""Stage 0〜6 のオーケストレーション。

Gemini 段階は gemini_placer として注入する。注入しなければ
モックモードと同じ経路になるため、テストに API キーは要らない。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

from app.constraints.context import Context, Violation
from app.constraints.validator import validate_all
from app.ingest.joint_pairing import assign_joint_ids
from app.ingest.validators import Warning, collect_warnings
from app.logging.session_logger import SessionLogger
from app.models.enums import Category
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timetable import Timetable
from app.scheduler.prelock import prelock
from app.scheduler.solver import solve

STAGE_ORDER: tuple[tuple[str, Category], ...] = (
    ("Stage 2", Category.REQUIRED),
    ("Stage 3", Category.ELECTIVE_REQUIRED),
    ("Stage 4", Category.ELECTIVE),
)


class GenerationMode(str, Enum):
    MOCK = "mock"
    OPTIMIZE = "optimize"
    INHERIT = "inherit"


class GeminiPlacer(Protocol):
    def __call__(
        self,
        context: Context,
        timetable: Timetable,
        codes: list[str],
        logger: SessionLogger,
    ) -> list[str]:
        """配置できなかった科目コードを返す。"""


@dataclass(slots=True)
class GenerationResult:
    timetable: Timetable
    unplaced: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    intensive_codes: list[str] = field(default_factory=list)


def run_pipeline(
    subjects: list[Subject],
    teachers: list[Teacher] | dict[str, Teacher],
    mode: GenerationMode,
    logger: SessionLogger,
    *,
    gemini_placer: GeminiPlacer | None = None,
    inherit_plan: "InheritPlan | None" = None,
) -> GenerationResult:
    logger.info(f"生成を開始します（モード: {mode.value}）", stage="Stage 0")

    joint_mismatches = assign_joint_ids(subjects)
    context = Context.from_lists(subjects, teachers)
    warnings = collect_warnings(subjects, context.teachers, joint_mismatches)
    for warning in warnings:
        logger.warn(warning.message, stage="Stage 0")
    logger.info(
        f"科目 {len(subjects)} 件、教員 {len(context.teachers)} 名を読み込みました",
        stage="Stage 0",
    )

    intensive_codes = [s.code for s in subjects if s.is_intensive]
    if intensive_codes:
        logger.info(
            f"集中講義 {len(intensive_codes)} 件をグリッド対象外にしました", stage="Stage 0"
        )

    timetable, leftover = prelock(context, subjects)
    logger.info(f"事前ロック {len(timetable.placed_codes())} 件", stage="Stage 1")
    for code in leftover:
        logger.warn(f"非常勤の出勤可能コマに空きがありません: {code}", stage="Stage 1")

    if mode is GenerationMode.INHERIT and inherit_plan is not None:
        apply_inherit_plan(context, timetable, inherit_plan, logger)

    pending = [
        s.code for s in subjects
        if not s.is_intensive and not timetable.is_placed(s.code)
    ]

    if mode is not GenerationMode.MOCK and gemini_placer is not None:
        for stage_name, category in STAGE_ORDER:
            codes = [c for c in pending if context.subjects[c].category is category]
            if not codes:
                continue
            logger.info(f"{category.value} {len(codes)} 件を配置します", stage=stage_name)
            failed = gemini_placer(context, timetable, codes, logger)
            placed = len(codes) - len(failed)
            logger.info(f"{placed} 件を配置、{len(failed)} 件が未確定", stage=stage_name)
            pending = [c for c in pending if not timetable.is_placed(c)]

    if pending:
        logger.info(f"ソルバーで {len(pending)} 件を補完します", stage="Stage 5")
    unplaced = solve(context, timetable, pending)
    for code in unplaced:
        logger.warn(f"配置できませんでした: {code}", stage="Stage 5")

    violations = validate_all(context, timetable)
    level = logger.error if violations else logger.info
    level(
        f"検証完了: 配置 {len(timetable.placed_codes())} 件 / "
        f"未配置 {len(unplaced)} 件 / 違反 {len(violations)} 件",
        stage="Stage 6",
    )
    for violation in violations:
        logger.error(f"[{violation.rule_id}] {violation.message}", stage="Stage 6")

    return GenerationResult(
        timetable=timetable,
        unplaced=unplaced,
        violations=violations,
        warnings=warnings,
        intensive_codes=intensive_codes,
    )
```

- [ ] **Step 4: 踏襲モードの空実装を追加する**

Task 16 で中身を実装するが、パイプラインが import できるよう `pipeline.py` の末尾に置く。

```python
def apply_inherit_plan(context, timetable, inherit_plan, logger) -> None:
    """踏襲モードで前年度の配置を反映する。Task 16 で実装を差し替える。"""
    from app.scheduler.inherit import apply_plan

    apply_plan(context, timetable, inherit_plan, logger)
```

また、`pipeline.py` の import 節に次を追加する。

```python
from app.scheduler.inherit import InheritPlan
```

Task 16 を実装するまではこの import が失敗するため、**Task 16 を先に読み、`inherit.py` の `InheritPlan` と `apply_plan` を先に空実装として作成しておく**こと。具体的には次の内容で `backend/app/scheduler/inherit.py` を作成する。

```python
"""踏襲モード。Task 16 で本実装する。"""
from dataclasses import dataclass, field


@dataclass(slots=True)
class InheritPlan:
    previous_slots: dict[str, tuple] = field(default_factory=dict)
    retarget_codes: set[str] = field(default_factory=set)


def apply_plan(context, timetable, plan, logger) -> None:
    raise NotImplementedError
```

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS（9 件）

- [ ] **Step 6: 全テストを実行する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 7: コミットする**

```bash
git add backend/app/scheduler/pipeline.py backend/app/scheduler/inherit.py backend/tests/test_pipeline.py
git commit -m "feat: 生成パイプラインとモックモードを追加"
```

---

### Task 16: 踏襲モード

**Files:**
- Modify: `backend/app/scheduler/inherit.py`（Task 15 で作った空実装を本実装に置き換える）
- Test: `backend/tests/test_inherit.py`

**Interfaces:**
- Consumes: Task 6 の `read_curriculum`、Task 5 の `read_teachers`、Task 11 の `is_allowed`
- Produces:
  - `PreviousEntry(slots: tuple[TimeSlot, ...], teacher: str)`
  - `read_previous_timetable(path) -> dict[str, PreviousEntry]`
  - `detect_retarget_codes(subjects, teachers, previous_entries, previous_teachers) -> set[str]`
  - `InheritPlan(previous_slots: dict[str, PreviousEntry], retarget_codes: set[str])`
  - `apply_plan(context, timetable, plan, logger) -> None`

**組み替え対象の判定（仕様書 §7）:**

| 条件 | 説明 |
|---|---|
| 非専任 | 今年度の教員区分が `非常勤` または `特任` |
| 研究日変更 | 前年度と今年度で `research_day` が異なる専任 |
| 新規科目 | 前年度の時間割に授業コードが無い |
| 担当変更 | 前年度と今年度で担当教員が異なる |

**`apply_plan` の挙動:** 組み替え対象**でない**科目のうち、前年度の配置があり、かつ現在の制約を満たすものを `AssignmentSource.INHERITED` で配置する。制約を満たさない場合は配置せず WARN を出し、以降のステージに委ねる。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_inherit.py`:

```python
from app.constraints.context import Context
from app.logging.session_logger import SessionLogger
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.inherit import (
    InheritPlan,
    PreviousEntry,
    apply_plan,
    detect_retarget_codes,
)


def make(code, teacher="専任甲", **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher=teacher,
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_part_time_and_special_teachers_are_always_retargeted():
    subjects = [make("A1", teacher="非常勤甲"), make("A2", teacher="特任甲")]
    teachers = {
        "非常勤甲": Teacher("非常勤甲", TeacherKind.PART_TIME),
        "特任甲": Teacher("特任甲", TeacherKind.SPECIAL, available_days={"水"}),
    }
    previous = {
        "A1": PreviousEntry((TimeSlot("月", 1),), "非常勤甲"),
        "A2": PreviousEntry((TimeSlot("水", 1),), "特任甲"),
    }
    assert detect_retarget_codes(subjects, teachers, previous, teachers) == {"A1", "A2"}


def test_changed_research_day_is_retargeted():
    subjects = [make("A1", teacher="専任甲")]
    current = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="水")}
    previous_teachers = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")}
    previous = {"A1": PreviousEntry((TimeSlot("月", 1),), "専任甲")}
    assert detect_retarget_codes(subjects, current, previous, previous_teachers) == {"A1"}


def test_unchanged_full_time_teacher_is_not_retargeted():
    subjects = [make("A1", teacher="専任甲")]
    teachers = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")}
    previous = {"A1": PreviousEntry((TimeSlot("月", 1),), "専任甲")}
    assert detect_retarget_codes(subjects, teachers, previous, teachers) == set()


def test_new_subject_is_retargeted():
    subjects = [make("A9", teacher="専任甲")]
    teachers = {"専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火")}
    assert detect_retarget_codes(subjects, teachers, {}, teachers) == {"A9"}


def test_changed_teacher_is_retargeted():
    subjects = [make("A1", teacher="専任乙")]
    teachers = {
        "専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="火"),
        "専任乙": Teacher("専任乙", TeacherKind.FULL_TIME, research_day="火"),
    }
    previous = {"A1": PreviousEntry((TimeSlot("月", 1),), "専任甲")}
    assert detect_retarget_codes(subjects, teachers, previous, teachers) == {"A1"}


def test_apply_plan_places_non_retargeted_subjects(tmp_path):
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    plan = InheritPlan({"A1": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, set())
    logger = SessionLogger("i1", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.slot_of("A1") == (TimeSlot("木", 4),)
    assert tt.assignments["A1"].source is AssignmentSource.INHERITED
    logger.close()


def test_apply_plan_skips_retargeted_subjects(tmp_path):
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    tt = Timetable()
    plan = InheritPlan({"A1": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, {"A1"})
    logger = SessionLogger("i2", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.placed_codes() == set()
    logger.close()


def test_apply_plan_skips_when_previous_slot_now_violates(tmp_path):
    # 前年度は木曜だったが、今年度は研究日が木曜に変わった
    subject = make("A1", teacher="専任甲")
    teachers = [Teacher("専任甲", TeacherKind.FULL_TIME, research_day="木")]
    ctx = Context.from_lists([subject], teachers)
    tt = Timetable()
    plan = InheritPlan({"A1": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, set())
    logger = SessionLogger("i3", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.placed_codes() == set()
    assert any(e.level == "WARN" for e in logger.events)
    logger.close()


def test_apply_plan_ignores_codes_absent_from_this_year(tmp_path):
    ctx = Context.from_lists([], [])
    tt = Timetable()
    plan = InheritPlan({"Z9": PreviousEntry((TimeSlot("木", 4),), "専任甲")}, set())
    logger = SessionLogger("i4", log_dir=tmp_path)

    apply_plan(ctx, tt, plan, logger)
    assert tt.placed_codes() == set()
    logger.close()
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_inherit.py -v`
Expected: FAIL（`ImportError: cannot import name 'PreviousEntry'`）

- [ ] **Step 3: 踏襲モードを実装する**

`backend/app/scheduler/inherit.py` の内容を次で置き換える:

```python
"""踏襲モード。

前年度の配置をそのまま使える科目はロックし、組み替えが必要な科目だけを
Stage 2〜5 に流す。事務局の確認負担を減らすことが目的。
"""
from dataclasses import dataclass, field
from pathlib import Path

from app.constraints.context import Context
from app.constraints.validator import is_allowed
from app.ingest.curriculum_reader import read_curriculum
from app.logging.session_logger import SessionLogger
from app.models.enums import TeacherKind
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable

RETARGET_KINDS = (TeacherKind.PART_TIME, TeacherKind.SPECIAL)
"""非専任。出勤可能日が年度で変動するため常に組み替え対象。"""


@dataclass(frozen=True, slots=True)
class PreviousEntry:
    slots: tuple[TimeSlot, ...]
    teacher: str


@dataclass(slots=True)
class InheritPlan:
    previous_slots: dict[str, PreviousEntry] = field(default_factory=dict)
    retarget_codes: set[str] = field(default_factory=set)


def read_previous_timetable(path: str | Path) -> dict[str, PreviousEntry]:
    """前年度の時間割（カリキュラム一覧と同形式）を読む。

    曜日・時限が埋まっている科目だけを対象とする。集中講義は無視する。
    """
    entries: dict[str, PreviousEntry] = {}
    for subject in read_curriculum(path):
        if subject.is_intensive or subject.fixed_slot is None:
            continue
        entries[subject.code] = PreviousEntry(
            slots=tuple(subject.fixed_slot), teacher=subject.teacher
        )
    return entries


def detect_retarget_codes(
    subjects: list[Subject],
    teachers: dict[str, Teacher],
    previous_entries: dict[str, PreviousEntry],
    previous_teachers: dict[str, Teacher],
) -> set[str]:
    """組み替えが必要な科目コードを返す。"""
    retarget: set[str] = set()
    for subject in subjects:
        if subject.is_intensive:
            continue

        teacher = teachers.get(subject.teacher)
        if teacher is not None and teacher.kind in RETARGET_KINDS:
            retarget.add(subject.code)
            continue

        previous = previous_entries.get(subject.code)
        if previous is None:
            retarget.add(subject.code)
            continue

        if previous.teacher != subject.teacher:
            retarget.add(subject.code)
            continue

        before = previous_teachers.get(subject.teacher)
        after = teachers.get(subject.teacher)
        before_day = before.research_day if before else None
        after_day = after.research_day if after else None
        if before_day != after_day:
            retarget.add(subject.code)

    return retarget


def apply_plan(
    context: Context, timetable: Timetable, plan: InheritPlan, logger: SessionLogger
) -> None:
    """組み替え対象でない科目を前年度と同じコマに配置する。"""
    inherited = 0
    for code, previous in plan.previous_slots.items():
        if code in plan.retarget_codes:
            continue
        subject = context.subjects.get(code)
        if subject is None or timetable.is_placed(code):
            continue
        if not is_allowed(context, timetable, subject, previous.slots):
            logger.warn(
                f"前年度の配置が今年度の制約に合いません: {subject.name}",
                stage="Stage 1",
            )
            continue
        timetable.place(code, previous.slots, AssignmentSource.INHERITED)
        inherited += 1

    logger.info(f"前年度から {inherited} 件を踏襲しました", stage="Stage 1")
    logger.info(f"組み替え対象は {len(plan.retarget_codes)} 件です", stage="Stage 1")
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_inherit.py -v`
Expected: PASS（9 件）

- [ ] **Step 5: 全テストを実行する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 6: コミットする**

```bash
git add backend/app/scheduler/inherit.py backend/tests/test_inherit.py
git commit -m "feat: 踏襲モードを追加"
```

---

### Task 17: 設定の永続化（API キー・モデル・再試行回数）

**Files:**
- Create: `backend/app/settings_store.py`
- Test: `backend/tests/test_settings_store.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `AppSettings(model: str, max_retries: int)` — dataclass、`to_dict()`
  - `DEFAULT_MODEL = "gemini-2.5-flash"`、`DEFAULT_MAX_RETRIES = 3`
  - `SettingsStore(env_path: Path, settings_path: Path)`
    - `.load() -> AppSettings`
    - `.save(settings: AppSettings) -> None`
    - `.get_api_key() -> str | None`
    - `.set_api_key(key: str) -> None`
    - `.delete_api_key() -> None`
    - `.masked_api_key() -> str | None` — `"AIza****"` 形式。全文は絶対に返さない

**API キーの扱い:** `.env` の `GEMINI_API_KEY` に保存する。フロントへ返すのは `masked_api_key()` の結果のみ。`.env` は Task 1 で `.gitignore` に登録済み。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_settings_store.py`:

```python
from app.settings_store import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    AppSettings,
    SettingsStore,
)


def build(tmp_path):
    return SettingsStore(tmp_path / ".env", tmp_path / "settings.json")


def test_load_returns_defaults_when_no_file(tmp_path):
    settings = build(tmp_path).load()
    assert settings.model == DEFAULT_MODEL
    assert settings.max_retries == DEFAULT_MAX_RETRIES


def test_save_then_load_roundtrip(tmp_path):
    store = build(tmp_path)
    store.save(AppSettings(model="gemini-2.5-pro", max_retries=5))
    loaded = store.load()
    assert loaded.model == "gemini-2.5-pro"
    assert loaded.max_retries == 5


def test_api_key_is_absent_by_default(tmp_path):
    store = build(tmp_path)
    assert store.get_api_key() is None
    assert store.masked_api_key() is None


def test_set_and_get_api_key(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyEXAMPLE1234567890")
    assert store.get_api_key() == "AIzaSyEXAMPLE1234567890"


def test_masked_api_key_hides_the_secret(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyEXAMPLE1234567890")
    masked = store.masked_api_key()
    assert masked == "AIzaSy****"
    assert "EXAMPLE" not in masked


def test_delete_api_key(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyEXAMPLE1234567890")
    store.delete_api_key()
    assert store.get_api_key() is None


def test_set_api_key_preserves_other_env_entries(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER_VAR=keep-me\n", encoding="utf-8")
    store = SettingsStore(env, tmp_path / "settings.json")
    store.set_api_key("AIzaSyNEW")
    content = env.read_text(encoding="utf-8")
    assert "OTHER_VAR=keep-me" in content
    assert "GEMINI_API_KEY=AIzaSyNEW" in content


def test_replacing_api_key_does_not_duplicate_the_line(tmp_path):
    store = build(tmp_path)
    store.set_api_key("AIzaSyOLD")
    store.set_api_key("AIzaSyNEW")
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert content.count("GEMINI_API_KEY=") == 1
    assert "AIzaSyNEW" in content


def test_max_retries_is_clamped_to_at_least_one(tmp_path):
    store = build(tmp_path)
    store.save(AppSettings(model=DEFAULT_MODEL, max_retries=0))
    assert store.load().max_retries == 1
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_settings_store.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.settings_store'`）

- [ ] **Step 3: 設定ストアを実装する**

`backend/app/settings_store.py`:

```python
"""API キーと生成設定の永続化。

API キーは .env、それ以外は data/settings.json に置く。
フロントへ返すのはマスク済みの文字列だけで、全文は返さない。
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

API_KEY_NAME = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_RETRIES = 3
VISIBLE_PREFIX_LENGTH = 6

_BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = _BACKEND_DIR / ".env"
DEFAULT_SETTINGS_PATH = _BACKEND_DIR / "data" / "settings.json"


@dataclass(slots=True)
class AppSettings:
    model: str = DEFAULT_MODEL
    max_retries: int = DEFAULT_MAX_RETRIES

    def to_dict(self) -> dict:
        return asdict(self)


class SettingsStore:
    def __init__(
        self, env_path: Path | None = None, settings_path: Path | None = None
    ) -> None:
        self.env_path = Path(env_path) if env_path else DEFAULT_ENV_PATH
        self.settings_path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_PATH

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings()
        raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        return AppSettings(
            model=raw.get("model", DEFAULT_MODEL) or DEFAULT_MODEL,
            max_retries=max(1, int(raw.get("max_retries", DEFAULT_MAX_RETRIES))),
        )

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = settings.to_dict()
        payload["max_retries"] = max(1, int(payload["max_retries"]))
        self.settings_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_env_lines(self) -> list[str]:
        if not self.env_path.exists():
            return []
        return self.env_path.read_text(encoding="utf-8").splitlines()

    def get_api_key(self) -> str | None:
        for line in self._read_env_lines():
            if line.startswith(f"{API_KEY_NAME}="):
                value = line.split("=", 1)[1].strip()
                return value or None
        return None

    def set_api_key(self, key: str) -> None:
        lines = [
            line for line in self._read_env_lines()
            if not line.startswith(f"{API_KEY_NAME}=")
        ]
        lines.append(f"{API_KEY_NAME}={key.strip()}")
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def delete_api_key(self) -> None:
        lines = [
            line for line in self._read_env_lines()
            if not line.startswith(f"{API_KEY_NAME}=")
        ]
        if not self.env_path.exists() and not lines:
            return
        self.env_path.write_text(
            ("\n".join(lines) + "\n") if lines else "", encoding="utf-8"
        )

    def masked_api_key(self) -> str | None:
        key = self.get_api_key()
        if not key:
            return None
        return f"{key[:VISIBLE_PREFIX_LENGTH]}****"
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_settings_store.py -v`
Expected: PASS（9 件）

- [ ] **Step 5: コミットする**

```bash
git add backend/app/settings_store.py backend/tests/test_settings_store.py
git commit -m "feat: API キーと生成設定の永続化を追加"
```

---

### Task 18: Gemini のプロンプト生成と応答解析

**Files:**
- Create: `backend/app/gemini/__init__.py`
- Create: `backend/app/gemini/prompts.py`
- Test: `backend/tests/test_prompts.py`

**Interfaces:**
- Consumes: Task 12 の `feasible_slot_sets`、Task 9 の `Context`
- Produces:
  - `RESPONSE_SCHEMA: dict` — 構造化出力用の JSON スキーマ
  - `slot_label(slot: TimeSlot) -> str` — `TimeSlot("月", 1)` → `"月1"`
  - `parse_slot_label(label: str) -> TimeSlot`
  - `build_placement_prompt(context, timetable, codes, *, feedback=None) -> str`
  - `parse_placement_response(text: str) -> dict[str, tuple[TimeSlot, ...]]`

**プロンプト設計の要点:**

- 科目ごとに**実行可能な候補コマを列挙して渡す**。AI は候補の中から選ぶだけでよくなり、違反率が大きく下がる
- 占有済みマップは「教員別の使用済みコマ」だけを渡す。全科目の配置を渡すとトークンが膨らむため
- 差し戻し時は `feedback`（違反した科目コードと理由）だけを追記し、成功済みの配置は再送しない
- 応答は `{"placements": [{"code": "...", "slots": ["月1"]}]}` の形に固定する

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_prompts.py`:

```python
import json

import pytest

from app.constraints.context import Context
from app.gemini.prompts import (
    RESPONSE_SCHEMA,
    build_placement_prompt,
    parse_placement_response,
    parse_slot_label,
    slot_label,
)
from app.models.enums import Category, Department, TeacherKind, Term
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def test_slot_label_roundtrip():
    assert slot_label(TimeSlot("月", 1)) == "月1"
    assert parse_slot_label("金5") == TimeSlot("金", 5)


def test_parse_slot_label_rejects_garbage():
    with pytest.raises(ValueError):
        parse_slot_label("土1")
    with pytest.raises(ValueError):
        parse_slot_label("月9")


def test_prompt_lists_target_subjects():
    subject = make("A1", name="経営学入門")
    ctx = Context.from_lists([subject], [])
    prompt = build_placement_prompt(ctx, Timetable(), ["A1"])
    assert "A1" in prompt
    assert "経営学入門" in prompt


def test_prompt_includes_feasible_candidates():
    a, b = make("A1"), make("B1")
    ctx = Context.from_lists([a, b], [])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    prompt = build_placement_prompt(ctx, tt, ["B1"])
    assert "月2" in prompt
    # 月1 は A1 と同教員・同学科年次のため候補から外れる
    assert "月1" not in prompt.split("候補", 1)[1].split("\n")[0]


def test_prompt_includes_teacher_occupancy():
    a, b = make("A1"), make("B1", teacher="教員乙")
    ctx = Context.from_lists([a, b], [
        Teacher("教員甲", TeacherKind.FULL_TIME),
        Teacher("教員乙", TeacherKind.FULL_TIME),
    ])
    tt = Timetable()
    tt.place("A1", (TimeSlot("月", 1),), AssignmentSource.PRELOCK)

    prompt = build_placement_prompt(ctx, tt, ["B1"])
    assert "教員甲" in prompt


def test_prompt_includes_feedback_when_given():
    subject = make("A1")
    ctx = Context.from_lists([subject], [])
    prompt = build_placement_prompt(
        ctx, Timetable(), ["A1"], feedback=["A1: [H1] 教員甲が月1で重複しています"]
    )
    assert "前回の配置には次の違反がありました" in prompt
    assert "[H1]" in prompt


def test_parse_response_returns_slots_by_code():
    payload = json.dumps({
        "placements": [
            {"code": "A1", "slots": ["月1"]},
            {"code": "J1", "slots": ["水2", "水3"]},
        ]
    })
    parsed = parse_placement_response(payload)
    assert parsed == {
        "A1": (TimeSlot("月", 1),),
        "J1": (TimeSlot("水", 2), TimeSlot("水", 3)),
    }


def test_parse_response_tolerates_markdown_code_fence():
    payload = '```json\n{"placements": [{"code": "A1", "slots": ["火4"]}]}\n```'
    assert parse_placement_response(payload) == {"A1": (TimeSlot("火", 4),)}


def test_parse_response_raises_on_invalid_json():
    with pytest.raises(ValueError, match="JSON"):
        parse_placement_response("これは JSON ではありません")


def test_parse_response_raises_on_invalid_slot_label():
    payload = json.dumps({"placements": [{"code": "A1", "slots": ["土1"]}]})
    with pytest.raises(ValueError):
        parse_placement_response(payload)


def test_response_schema_declares_placements():
    assert RESPONSE_SCHEMA["type"] == "object"
    assert "placements" in RESPONSE_SCHEMA["properties"]
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_prompts.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.gemini'`）

- [ ] **Step 3: プロンプト生成と解析を実装する**

`backend/app/gemini/__init__.py` は空ファイル。

`backend/app/gemini/prompts.py`:

```python
"""Gemini へ渡すプロンプトと、応答の解析。

科目ごとに実行可能な候補コマを列挙して渡すことで、AI は候補から
選ぶだけでよくなり、制約違反が大きく減る。占有済みの情報は教員別に
絞って渡し、トークンを節約する。
"""
import json
import re

from app.constraints.context import Context
from app.models.timeslot import DAYS, PERIODS, TimeSlot
from app.models.timetable import Timetable
from app.scheduler.candidates import feasible_slot_sets

MAX_CANDIDATES_SHOWN = 25
"""1 科目あたりプロンプトに載せる候補数の上限。"""

_LABEL_PATTERN = re.compile(r"^([月火水木金])([1-5])$")
_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "placements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "slots": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["code", "slots"],
            },
        }
    },
    "required": ["placements"],
}


def slot_label(slot: TimeSlot) -> str:
    return f"{slot.day}{slot.period}"


def parse_slot_label(label: str) -> TimeSlot:
    match = _LABEL_PATTERN.match(str(label).strip())
    if not match:
        raise ValueError(f"コマの表記が不正です: {label!r}")
    day, period = match.group(1), int(match.group(2))
    if day not in DAYS or period not in PERIODS:
        raise ValueError(f"コマの表記が不正です: {label!r}")
    return TimeSlot(day, period)


def _slots_label(slots: tuple[TimeSlot, ...]) -> str:
    return "+".join(slot_label(slot) for slot in slots)


def _teacher_occupancy(context: Context, timetable: Timetable) -> list[str]:
    used: dict[str, list[str]] = {}
    for code, assignment in timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None or not subject.teacher:
            continue
        used.setdefault(subject.teacher, []).extend(
            slot_label(slot) for slot in assignment.slots
        )
    return [
        f"- {teacher}: {', '.join(sorted(slots))}"
        for teacher, slots in sorted(used.items())
    ]


def build_placement_prompt(
    context: Context,
    timetable: Timetable,
    codes: list[str],
    *,
    feedback: list[str] | None = None,
) -> str:
    lines: list[str] = [
        "あなたは大学の時間割を作成する担当者です。",
        "以下の科目を、指定された候補の中から 1 つ選んで配置してください。",
        "",
        "## 制約",
        "- 候補として挙げたコマ以外は選ばないでください。",
        "- この依頼の中で配置する科目同士も、同じ教員が同じコマに重ならないようにしてください。",
        "- 同じ学科・同じ年次の必修科目同士を同じコマに置かないでください。",
        "- 同じ教員が同じ曜日に 3 コマ以上連続しないようにしてください。",
        "",
        "## 配置対象",
    ]

    for code in codes:
        subject = context.subjects.get(code)
        if subject is None:
            continue
        options = feasible_slot_sets(context, timetable, subject)[:MAX_CANDIDATES_SHOWN]
        candidates = ", ".join(_slots_label(slots) for slots in options) or "なし"
        quarter = f"/{subject.quarter.value}" if subject.quarter else ""
        lines.append(
            f"- {code} | {subject.name} | {subject.department.value}"
            f"{subject.year}年 | {subject.term.value}{quarter} | "
            f"{subject.category.value} | 担当: {subject.teacher} | "
            f"候補: {candidates}"
        )

    occupancy = _teacher_occupancy(context, timetable)
    if occupancy:
        lines += ["", "## 既に埋まっている教員のコマ", *occupancy]

    if feedback:
        lines += [
            "",
            "## 前回の配置には次の違反がありました。これらを避けて配置し直してください。",
            *[f"- {item}" for item in feedback],
        ]

    lines += [
        "",
        "## 出力形式",
        "次の JSON だけを出力してください。説明文は不要です。",
        '{"placements": [{"code": "科目コード", "slots": ["月1"]}]}',
        "2 コマ必要な科目は slots に 2 件入れてください。",
    ]
    return "\n".join(lines)


def parse_placement_response(text: str) -> dict[str, tuple[TimeSlot, ...]]:
    """応答 JSON を科目コード → コマ集合の辞書に変換する。"""
    cleaned = _FENCE_PATTERN.sub("", str(text)).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(f"応答を JSON として解釈できません: {error}") from error

    placements = payload.get("placements")
    if not isinstance(placements, list):
        raise ValueError("応答に placements 配列がありません")

    result: dict[str, tuple[TimeSlot, ...]] = {}
    for item in placements:
        code = str(item.get("code", "")).strip()
        slots = item.get("slots") or []
        if not code or not isinstance(slots, list):
            raise ValueError(f"placements の要素が不正です: {item!r}")
        result[code] = tuple(parse_slot_label(label) for label in slots)
    return result
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_prompts.py -v`
Expected: PASS（11 件）

- [ ] **Step 5: コミットする**

```bash
git add backend/app/gemini backend/tests/test_prompts.py
git commit -m "feat: Gemini のプロンプト生成と応答解析を追加"
```

---

### Task 19: Gemini クライアントと Stage 2〜4 の配置ループ

**Files:**
- Create: `backend/app/gemini/client.py`
- Create: `backend/app/scheduler/gemini_stage.py`
- Test: `backend/tests/test_gemini_stage.py`

**Interfaces:**
- Consumes: Task 18 のプロンプト群、Task 11 の `check_placement`、Task 14 の `SessionLogger`
- Produces:
  - `GeminiError(Exception)`
  - `GeminiClient(Protocol)` — `generate(prompt: str) -> str`
  - `RealGeminiClient(api_key: str, model: str)` — `google-genai` を使う実装
  - `chunk_codes(context, codes) -> list[tuple[str, list[str]]]` — `(チャンク名, コード一覧)`
  - `make_gemini_placer(client, max_retries) -> GeminiPlacer` — Task 15 の `gemini_placer` に渡す

**チャンク分割の鍵:** `(学科, 開講期, ソートしたコース一覧)`。必修と選択はコースが空なので自然に「学科 × 開講期」になり、選択必修だけコースで細分される。

**再試行ループ:** 1 チャンクにつき最大 `max_retries` 回。違反した科目だけを次回の対象に残し、違反理由を `feedback` として渡す。API 例外・JSON 解析失敗も 1 回分の試行として数える。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_gemini_stage.py`:

```python
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


def test_placer_ignores_codes_not_in_the_request(tmp_path):
    subjects = [make("A1")]
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    client = ScriptedClient([response(A1=["月1"], Z9=["火1"])])
    logger = SessionLogger("g6", log_dir=tmp_path)

    make_gemini_placer(client, max_retries=2)(ctx, tt, ["A1"], logger)
    assert tt.placed_codes() == {"A1"}
    logger.close()
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_gemini_stage.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.gemini.client'`）

- [ ] **Step 3: クライアントを実装する**

`backend/app/gemini/client.py`:

```python
"""Gemini API クライアント。

失敗はすべて GeminiError に包む。呼び出し側は再試行するだけでよく、
SDK の例外型に依存しない。
"""
from typing import Protocol

from app.gemini.prompts import RESPONSE_SCHEMA


class GeminiError(Exception):
    """Gemini 呼び出しに関するあらゆる失敗。"""


class GeminiClient(Protocol):
    def generate(self, prompt: str) -> str:
        """プロンプトを送り、応答テキストを返す。"""


class RealGeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                },
            )
        except Exception as error:  # SDK の例外型に依存しない
            raise GeminiError(str(error)) from error

        text = getattr(response, "text", None)
        if not text:
            raise GeminiError("空の応答が返りました")
        return text
```

- [ ] **Step 4: 配置ループを実装する**

`backend/app/scheduler/gemini_stage.py`:

```python
"""Stage 2〜4: Gemini にチャンク単位で配置させ、検証して差し戻す。

成功済みの配置は再送しない。差し戻すのは違反した科目だけなので、
再試行してもトークンが線形に膨らまない。
"""
import time
from collections import defaultdict

from app.constraints.context import Context
from app.constraints.validator import check_placement
from app.gemini.client import GeminiClient, GeminiError
from app.gemini.prompts import build_placement_prompt, parse_placement_response
from app.logging.session_logger import SessionLogger
from app.models.timetable import AssignmentSource, Timetable


def chunk_codes(context: Context, codes: list[str]) -> list[tuple[str, list[str]]]:
    """学科 × 開講期 × コースでチャンクに割る。"""
    groups: dict[tuple, list[str]] = defaultdict(list)
    for code in codes:
        subject = context.subjects.get(code)
        if subject is None:
            continue
        key = (
            subject.department.value,
            subject.term.value,
            tuple(sorted(subject.courses)),
        )
        groups[key].append(code)

    chunks: list[tuple[str, list[str]]] = []
    for key in sorted(groups):
        department, term, courses = key
        label = f"{department}・{term}"
        if courses:
            label += f"・{'/'.join(courses)}"
        chunks.append((label, groups[key]))
    return chunks


def make_gemini_placer(client: GeminiClient, max_retries: int):
    """pipeline.run_pipeline に渡す gemini_placer を組み立てる。"""

    def place(
        context: Context, timetable: Timetable, codes: list[str], logger: SessionLogger
    ) -> list[str]:
        unplaced: list[str] = []
        for label, chunk in chunk_codes(context, codes):
            unplaced.extend(_place_chunk(context, timetable, chunk, label, logger))
        return unplaced

    def _place_chunk(
        context: Context,
        timetable: Timetable,
        chunk: list[str],
        label: str,
        logger: SessionLogger,
    ) -> list[str]:
        remaining = [c for c in chunk if not timetable.is_placed(c)]
        feedback: list[str] = []

        for attempt in range(1, max_retries + 1):
            if not remaining:
                break

            prompt = build_placement_prompt(context, timetable, remaining, feedback=feedback)
            logger.info(
                f"{label}: {len(remaining)} 件を送信（{attempt}/{max_retries} 回目、"
                f"{len(prompt)} 文字）",
                stage="Gemini",
            )

            started = time.monotonic()
            try:
                text = client.generate(prompt)
            except GeminiError as error:
                logger.warn(f"{label}: 呼び出しに失敗しました（{error}）", stage="Gemini")
                continue
            logger.info(
                f"{label}: 応答を受信（{time.monotonic() - started:.1f}秒）", stage="Gemini"
            )

            try:
                parsed = parse_placement_response(text)
            except ValueError as error:
                logger.warn(f"{label}: 応答を解釈できません（{error}）", stage="Gemini")
                feedback = ["応答が指定の JSON 形式ではありませんでした"]
                continue

            feedback = []
            for code in list(remaining):
                slots = parsed.get(code)
                if not slots:
                    feedback.append(f"{code}: 配置が返りませんでした")
                    continue
                subject = context.subjects[code]
                violations = check_placement(context, timetable, subject, slots)
                if violations:
                    for violation in violations:
                        feedback.append(
                            f"{code}: [{violation.rule_id}] {violation.message}"
                        )
                    continue
                timetable.place(code, slots, AssignmentSource.GEMINI)

            remaining = [c for c in remaining if not timetable.is_placed(c)]
            if remaining:
                logger.warn(
                    f"{label}: {len(remaining)} 件が違反のため差し戻します", stage="Gemini"
                )

        return remaining

    return place
```

- [ ] **Step 5: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_gemini_stage.py -v`
Expected: PASS（8 件）

- [ ] **Step 6: 全テストを実行する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 7: コミットする**

```bash
git add backend/app/gemini/client.py backend/app/scheduler/gemini_stage.py backend/tests/test_gemini_stage.py
git commit -m "feat: Gemini クライアントと Stage 2〜4 の配置ループを追加"
```

---

### Task 20: Excel 出力

**Files:**
- Create: `backend/app/export/__init__.py`
- Create: `backend/app/export/excel_writer.py`
- Test: `backend/tests/test_excel_writer.py`

**Interfaces:**
- Consumes: Task 9 の `Context`、Task 15 の `GenerationResult`
- Produces:
  - `SHEET_PLAN: tuple[tuple[str, Department, Term], ...]` — 6 シートの定義
  - `write_timetable_excel(context, result, path) -> Path`

**シート構成（仕様書 §9）:** `経営・前期` / `経営・後期` / `会計・前期` / `会計・後期` / `短大・前期` / `短大・後期` と、集中講義の一覧シート `集中講義`。学年での分割はしない。

**セルの中身:** 同じコマに複数科目が入る場合は改行で併記する。1 科目あたり `科目名 / 教員名 / 年次・科目区分`。短大のクオーター科目は科目名の後ろに `[前①]` を付ける。

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_excel_writer.py`:

```python
import openpyxl

from app.constraints.context import Context
from app.export.excel_writer import SHEET_PLAN, write_timetable_excel
from app.models.enums import Category, Department, Quarter, Term
from app.models.subject import Subject
from app.models.timeslot import TimeSlot
from app.models.timetable import AssignmentSource, Timetable
from app.scheduler.pipeline import GenerationResult


def make(code, **kwargs):
    base = dict(
        name=code, base_name=code, department=Department.MANAGEMENT, year=1,
        term=Term.SPRING, quarter=None, category=Category.REQUIRED, teacher="教員甲",
    )
    base.update(kwargs)
    return Subject(code=code, **base)


def build(subjects, placements, intensive_codes=()):
    ctx = Context.from_lists(subjects, [])
    tt = Timetable()
    for code, slots in placements.items():
        tt.place(code, slots, AssignmentSource.GEMINI)
    return ctx, GenerationResult(timetable=tt, intensive_codes=list(intensive_codes))


def test_creates_all_seven_sheets(tmp_path):
    ctx, result = build([make("A1")], {"A1": (TimeSlot("月", 1),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    workbook = openpyxl.load_workbook(path)
    assert len(SHEET_PLAN) == 6
    assert workbook.sheetnames == [name for name, _, _ in SHEET_PLAN] + ["集中講義"]


def test_grid_has_day_headers_and_period_labels(tmp_path):
    ctx, result = build([make("A1")], {"A1": (TimeSlot("月", 1),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["経営・前期"]
    assert [sheet.cell(row=1, column=c).value for c in range(2, 7)] == list("月火水木金")
    assert [sheet.cell(row=r, column=1).value for r in range(2, 7)] == [
        "1限", "2限", "3限", "4限", "5限"
    ]


def test_subject_appears_in_correct_cell(tmp_path):
    subject = make("A1", name="経営学入門", teacher="築雅之")
    ctx, result = build([subject], {"A1": (TimeSlot("水", 3),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["経営・前期"]
    cell = sheet.cell(row=4, column=4).value  # 3限 × 水曜
    assert "経営学入門" in cell
    assert "築雅之" in cell


def test_multiple_subjects_share_a_cell(tmp_path):
    a = make("A1", name="科目甲", year=1)
    b = make("A2", name="科目乙", year=2)
    ctx, result = build([a, b], {
        "A1": (TimeSlot("月", 1),),
        "A2": (TimeSlot("月", 1),),
    })
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    cell = openpyxl.load_workbook(path)["経営・前期"].cell(row=2, column=2).value
    assert "科目甲" in cell and "科目乙" in cell
    assert "\n" in cell


def test_quarter_is_annotated(tmp_path):
    subject = make(
        "J1", name="デジタルデザイン", department=Department.JUNIOR, quarter=Quarter.Q1
    )
    ctx, result = build([subject], {"J1": (TimeSlot("火", 2),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    cell = openpyxl.load_workbook(path)["短大・前期"].cell(row=3, column=3).value
    assert "[前①]" in cell


def test_double_slot_subject_appears_in_both_cells(tmp_path):
    subject = make("J1", name="動画制作", department=Department.JUNIOR,
                   slots_required=2, requires_consecutive=True)
    ctx, result = build([subject], {"J1": (TimeSlot("水", 2), TimeSlot("水", 3))})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["短大・前期"]
    assert "動画制作" in sheet.cell(row=3, column=4).value
    assert "動画制作" in sheet.cell(row=4, column=4).value


def test_intensive_sheet_lists_intensive_subjects(tmp_path):
    subject = make("A9", name="集中講義甲", is_intensive=True)
    ctx, result = build([subject], {}, intensive_codes=["A9"])
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    sheet = openpyxl.load_workbook(path)["集中講義"]
    assert sheet.cell(row=1, column=1).value == "授業コード"
    assert sheet.cell(row=2, column=1).value == "A9"
    assert sheet.cell(row=2, column=2).value == "集中講義甲"


def test_fall_subject_goes_to_fall_sheet(tmp_path):
    subject = make("A1", name="後期科目", term=Term.FALL)
    ctx, result = build([subject], {"A1": (TimeSlot("月", 1),)})
    path = write_timetable_excel(ctx, result, tmp_path / "out.xlsx")

    workbook = openpyxl.load_workbook(path)
    assert workbook["経営・前期"].cell(row=2, column=2).value in (None, "")
    assert "後期科目" in workbook["経営・後期"].cell(row=2, column=2).value
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_excel_writer.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.export'`）

- [ ] **Step 3: Excel 出力を実装する**

`backend/app/export/__init__.py` は空ファイル。

`backend/app/export/excel_writer.py`:

```python
"""生成結果を時間割表マトリクスの Excel として書き出す。

学科 × 学期で 6 シート。集中講義は別シートに一覧で出す。
"""
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font

from app.constraints.context import Context
from app.models.enums import Department, Term
from app.models.timeslot import DAYS, PERIODS, TimeSlot

SHEET_PLAN: tuple[tuple[str, Department, Term], ...] = (
    ("経営・前期", Department.MANAGEMENT, Term.SPRING),
    ("経営・後期", Department.MANAGEMENT, Term.FALL),
    ("会計・前期", Department.ACCOUNTING, Term.SPRING),
    ("会計・後期", Department.ACCOUNTING, Term.FALL),
    ("短大・前期", Department.JUNIOR, Term.SPRING),
    ("短大・後期", Department.JUNIOR, Term.FALL),
)

INTENSIVE_SHEET = "集中講義"
_HEADER_FONT = Font(bold=True)
_CELL_ALIGNMENT = Alignment(wrap_text=True, vertical="top")


def _describe(subject) -> str:
    quarter = f"[{subject.quarter.value}]" if subject.quarter else ""
    return (
        f"{subject.name}{quarter}\n"
        f"{subject.teacher}\n"
        f"{subject.year}年・{subject.category.value}"
    )


def _write_grid(sheet, context: Context, timetable, department: Department, term: Term) -> None:
    sheet.cell(row=1, column=1, value="").font = _HEADER_FONT
    for column, day in enumerate(DAYS, start=2):
        cell = sheet.cell(row=1, column=column, value=day)
        cell.font = _HEADER_FONT
        sheet.column_dimensions[cell.column_letter].width = 28

    for row, period in enumerate(PERIODS, start=2):
        sheet.cell(row=row, column=1, value=f"{period}限").font = _HEADER_FONT
        sheet.row_dimensions[row].height = 72
        for column, day in enumerate(DAYS, start=2):
            entries = []
            for code in timetable.occupied_by(TimeSlot(day, period)):
                subject = context.subjects.get(code)
                if subject is None:
                    continue
                if subject.department is department and subject.term is term:
                    entries.append(_describe(subject))
            cell = sheet.cell(row=row, column=column, value="\n\n".join(entries))
            cell.alignment = _CELL_ALIGNMENT


def _write_intensive(sheet, context: Context, codes: list[str]) -> None:
    headers = ("授業コード", "科目名", "学科", "年次", "開講期", "科目区分", "教員")
    for column, title in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column, value=title)
        cell.font = _HEADER_FONT
        sheet.column_dimensions[cell.column_letter].width = 20

    for row, code in enumerate(codes, start=2):
        subject = context.subjects.get(code)
        if subject is None:
            continue
        values = (
            subject.code, subject.name, subject.department.value, subject.year,
            subject.term.value, subject.category.value, subject.teacher,
        )
        for column, value in enumerate(values, start=1):
            sheet.cell(row=row, column=column, value=value)


def write_timetable_excel(context: Context, result, path: str | Path) -> Path:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    for name, department, term in SHEET_PLAN:
        sheet = workbook.create_sheet(name)
        _write_grid(sheet, context, result.timetable, department, term)

    _write_intensive(
        workbook.create_sheet(INTENSIVE_SHEET), context, list(result.intensive_codes)
    )

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return target
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_excel_writer.py -v`
Expected: PASS（8 件）

- [ ] **Step 5: コミットする**

```bash
git add backend/app/export backend/tests/test_excel_writer.py
git commit -m "feat: 時間割表マトリクスの Excel 出力を追加"
```

---

### Task 21: MarkItDown フォールバックとダミーデータ生成

**Files:**
- Create: `backend/app/ingest/markitdown_fallback.py`
- Create: `backend/tests/fixtures/__init__.py`
- Create: `backend/tests/fixtures/make_dummy_data.py`
- Test: `backend/tests/test_markitdown_fallback.py`
- Test: `backend/tests/test_dummy_data.py`

**Interfaces:**
- Consumes: Task 6 の `read_curriculum`
- Produces:
  - `REQUIRED_COLUMNS: frozenset[str]`
  - `has_expected_columns(path) -> bool`
  - `convert_to_markdown(path) -> str`
  - `read_curriculum_with_fallback(path, logger) -> list[Subject]`
  - `make_dummy_curriculum(source, destination) -> Path` — 現行 Excel にコース列・遠隔列・合同フラグを補って書き出す

**フォールバックの方針:** `has_expected_columns` が `False` の場合、MarkItDown で Markdown 化し、その内容をログに残した上で `ValueError` を送出する。Markdown からの自動復元までは行わない。**想定外の形式を黙って誤読するより、内容を見せて止める方が安全**という判断である。

**ダミーデータ:** 合同フラグとコース列が未整備のため、検証用に次の規則で埋める。

- コース: 経営学科は授業コード末尾の数字を 3 で割った余りで 3 コースに割り当て、会計学科は空、短大は同様に 3 フィールドへ割り当て
- 短大の遠隔: 授業コード末尾が `1` の科目を `○`
- 合同フラグ: 既存の `合同(経・会)` 列をそのまま使う

- [ ] **Step 1: 失敗するテストを書く（フォールバック）**

`backend/tests/test_markitdown_fallback.py`:

```python
from pathlib import Path

import openpyxl
import pytest

from app.ingest.markitdown_fallback import (
    REQUIRED_COLUMNS,
    convert_to_markdown,
    has_expected_columns,
    read_curriculum_with_fallback,
)
from app.logging.session_logger import SessionLogger

CURRICULUM_XLSX = Path(__file__).resolve().parents[2] / "カリキュラム一覧(整形済み).xlsx"


def _write_broken_workbook(path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["適当な列", "別の列"])
    sheet.append(["値1", "値2"])
    workbook.save(path)
    return path


def test_required_columns_are_declared():
    assert {"授業コード", "授業科目名称", "学科", "科目区分"} <= REQUIRED_COLUMNS


def test_real_workbook_has_expected_columns():
    assert has_expected_columns(CURRICULUM_XLSX) is True


def test_broken_workbook_lacks_expected_columns(tmp_path):
    path = _write_broken_workbook(tmp_path / "broken.xlsx")
    assert has_expected_columns(path) is False


def test_fallback_reads_normal_workbook(tmp_path):
    logger = SessionLogger("m1", log_dir=tmp_path)
    subjects = read_curriculum_with_fallback(CURRICULUM_XLSX, logger)
    assert len(subjects) == 658
    logger.close()


def test_fallback_raises_and_logs_for_broken_workbook(tmp_path):
    path = _write_broken_workbook(tmp_path / "broken.xlsx")
    logger = SessionLogger("m2", log_dir=tmp_path)

    with pytest.raises(ValueError, match="想定外"):
        read_curriculum_with_fallback(path, logger)

    assert any(e.level == "ERROR" for e in logger.events)
    logger.close()


def test_convert_to_markdown_returns_text(tmp_path):
    path = _write_broken_workbook(tmp_path / "broken.xlsx")
    markdown = convert_to_markdown(path)
    assert isinstance(markdown, str)
    assert "値1" in markdown
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_markitdown_fallback.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ingest.markitdown_fallback'`）

- [ ] **Step 3: フォールバックを実装する**

`backend/app/ingest/markitdown_fallback.py`:

```python
"""想定外の列構成をした Excel が投入されたときの経路。

MarkItDown で Markdown 化して中身をログに残し、処理は止める。
黙って誤読するより、事務局に形式の違いを見せる方が安全と判断した。
"""
from pathlib import Path

import openpyxl

from app.ingest.curriculum_reader import read_curriculum
from app.logging.session_logger import SessionLogger
from app.models.subject import Subject

REQUIRED_COLUMNS = frozenset({
    "授業コード", "授業科目名称", "学科", "年次配当", "開講期間", "科目区分", "教員氏名",
})

MARKDOWN_PREVIEW_CHARS = 2000


def has_expected_columns(path: str | Path) -> bool:
    """いずれかのシートが必須列をすべて備えているか。"""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(min_row=1, max_row=1, values_only=True):
                headers = {str(v).strip() for v in row if v is not None}
                if REQUIRED_COLUMNS <= headers:
                    return True
        return False
    finally:
        workbook.close()


def convert_to_markdown(path: str | Path) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(str(path)).text_content


def read_curriculum_with_fallback(
    path: str | Path, logger: SessionLogger
) -> list[Subject]:
    if has_expected_columns(path):
        return read_curriculum(path)

    logger.error(
        f"想定外の列構成の Excel です: {Path(path).name}。"
        f"必須列: {'、'.join(sorted(REQUIRED_COLUMNS))}",
        stage="Stage 0",
    )
    try:
        preview = convert_to_markdown(path)[:MARKDOWN_PREVIEW_CHARS]
        logger.info(f"MarkItDown による内容プレビュー:\n{preview}", stage="Stage 0")
    except Exception as error:
        logger.error(f"MarkItDown での変換にも失敗しました: {error}", stage="Stage 0")

    raise ValueError(f"想定外の列構成の Excel です: {Path(path).name}")
```

- [ ] **Step 4: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_markitdown_fallback.py -v`
Expected: PASS（6 件）

- [ ] **Step 5: ダミーデータ生成のテストを書く**

`backend/tests/test_dummy_data.py`:

```python
from pathlib import Path

from app.ingest.curriculum_reader import read_curriculum
from app.models.enums import Category, Department
from tests.fixtures.make_dummy_data import make_dummy_curriculum

CURRICULUM_XLSX = Path(__file__).resolve().parents[2] / "カリキュラム一覧(整形済み).xlsx"


def test_dummy_fills_courses_for_elective_required(tmp_path):
    path = make_dummy_curriculum(CURRICULUM_XLSX, tmp_path / "dummy.xlsx")
    subjects = read_curriculum(path)

    elective_required = [
        s for s in subjects
        if s.category is Category.ELECTIVE_REQUIRED
        and s.department is not Department.ACCOUNTING
    ]
    assert elective_required
    assert all(s.courses for s in elective_required)


def test_dummy_uses_three_courses_per_department(tmp_path):
    path = make_dummy_curriculum(CURRICULUM_XLSX, tmp_path / "dummy.xlsx")
    subjects = read_curriculum(path)

    management = {
        c for s in subjects if s.department is Department.MANAGEMENT for c in s.courses
    }
    assert management == {"経営コース", "情報コース", "観光まちづくりコース"}


def test_dummy_marks_some_junior_subjects_as_remote(tmp_path):
    path = make_dummy_curriculum(CURRICULUM_XLSX, tmp_path / "dummy.xlsx")
    subjects = read_curriculum(path)

    junior_remote = [
        s for s in subjects if s.department is Department.JUNIOR and s.is_remote
    ]
    assert junior_remote


def test_dummy_keeps_subject_count(tmp_path):
    path = make_dummy_curriculum(CURRICULUM_XLSX, tmp_path / "dummy.xlsx")
    assert len(read_curriculum(path)) == len(read_curriculum(CURRICULUM_XLSX))
```

- [ ] **Step 6: ダミーデータ生成を実装する**

`backend/tests/fixtures/__init__.py` は空ファイル。

`backend/tests/fixtures/make_dummy_data.py`:

```python
"""検証用のダミーデータを作る。

コース列と短大の遠隔列は事務局側で整備中のため、現行 Excel から
機械的に埋めた版を生成して開発とテストに使う。
"""
import re
from pathlib import Path

import openpyxl

COURSES = {
    "経営": ("経営コース", "情報コース", "観光まちづくりコース"),
    "短期大学部": (
        "経営フィールド", "情報デザインフィールド", "グローバルコミュニケーションフィールド"
    ),
}

_DIGITS = re.compile(r"(\d+)")


def _code_number(code: str) -> int:
    match = _DIGITS.search(str(code))
    return int(match.group(1)) if match else 0


def make_dummy_curriculum(source: str | Path, destination: str | Path) -> Path:
    workbook = openpyxl.load_workbook(source)

    for sheet in workbook.worksheets:
        headers = {
            str(cell.value).strip(): cell.column
            for cell in sheet[1] if cell.value is not None
        }
        next_column = sheet.max_column + 1

        course_column = headers.get("コース")
        if course_column is None:
            course_column = next_column
            sheet.cell(row=1, column=course_column, value="コース")
            next_column += 1

        remote_column = headers.get("遠隔")
        if remote_column is None:
            remote_column = next_column
            sheet.cell(row=1, column=remote_column, value="遠隔")

        for row in range(2, sheet.max_row + 1):
            code = sheet.cell(row=row, column=headers["授業コード"]).value
            if not code:
                continue
            department = str(sheet.cell(row=row, column=headers["学科"]).value).strip()
            number = _code_number(code)

            options = COURSES.get(department)
            if options:
                sheet.cell(
                    row=row, column=course_column, value=options[number % len(options)]
                )

            if department == "短期大学部" and number % 10 == 1:
                sheet.cell(row=row, column=remote_column, value="○")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return target
```

- [ ] **Step 7: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 8: ダミーデータでパイプライン全体が完走することを確認する**

Run:

```bash
cd backend && ../.venv/bin/python -c "
import sys
from app.ingest.curriculum_reader import read_curriculum
from app.ingest.teacher_reader import read_teachers
from app.logging.session_logger import SessionLogger
from app.scheduler.pipeline import GenerationMode, run_pipeline
from tests.fixtures.make_dummy_data import make_dummy_curriculum

path = make_dummy_curriculum('../カリキュラム一覧(整形済み).xlsx', 'data/dummy.xlsx')
subjects = read_curriculum(path)
teachers = read_teachers('../教員一覧(整形済み).xlsx')
logger = SessionLogger('dummy')
result = run_pipeline(subjects, teachers, GenerationMode.MOCK, logger)
logger.close()
print(f'配置 {len(result.timetable.placed_codes())} / 未配置 {len(result.unplaced)} / 違反 {len(result.violations)} / 警告 {len(result.warnings)}')
print('ログ:', logger.log_path)
"
```

Expected: 違反 0 件で完走すること。未配置が出るのは制約が厳しいためで、この時点では許容する。

- [ ] **Step 9: コミットする**

```bash
git add backend/app/ingest/markitdown_fallback.py backend/tests/fixtures backend/tests/test_markitdown_fallback.py backend/tests/test_dummy_data.py
git commit -m "feat: MarkItDown フォールバックとダミーデータ生成を追加"
```

---

### Task 22: セッションストアとアップロード・設定 API

**Files:**
- Create: `backend/app/session_store.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/schemas.py`
- Create: `backend/app/api/upload.py`
- Create: `backend/app/api/settings.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api_upload.py`
- Test: `backend/tests/test_api_settings.py`

**Interfaces:**
- Consumes: Task 21 の `read_curriculum_with_fallback`、Task 5 の `read_teachers`、Task 17 の `SettingsStore`
- Produces:
  - `SessionData` — `subjects`, `teachers`, `previous_entries`, `previous_teachers`, `warnings`, `result`, `logger`
  - `SessionStore` — `create(...) -> str`、`get(session_id) -> SessionData`、`save_result(session_id) -> Path`
  - FastAPI アプリ `app`（`backend/app/main.py`）
  - エンドポイント: `POST /api/upload`、`GET /api/settings`、`PUT /api/settings`、`PUT /api/settings/api-key`、`DELETE /api/settings/api-key`

**API 仕様:**

| メソッド | パス | 内容 |
|---|---|---|
| `POST` | `/api/upload` | multipart。`curriculum`（必須）、`teachers`（必須）、`previous_curriculum`（任意）、`previous_teachers`（任意）。応答は `session_id` と読み込みサマリ・警告一覧 |
| `GET` | `/api/settings` | `model` / `max_retries` / `api_key_masked` / `has_api_key` |
| `PUT` | `/api/settings` | `model` / `max_retries` を保存 |
| `PUT` | `/api/settings/api-key` | `{"api_key": "..."}` を `.env` に保存 |
| `DELETE` | `/api/settings/api-key` | `.env` から削除 |

- [ ] **Step 1: 失敗するテストを書く（アップロード）**

`backend/tests/test_api_upload.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
CURRICULUM = ROOT / "カリキュラム一覧(整形済み).xlsx"
TEACHERS = ROOT / "教員一覧(整形済み).xlsx"

client = TestClient(app)


def _upload():
    with CURRICULUM.open("rb") as curriculum, TEACHERS.open("rb") as teachers:
        return client.post(
            "/api/upload",
            files={
                "curriculum": ("c.xlsx", curriculum, "application/vnd.ms-excel"),
                "teachers": ("t.xlsx", teachers, "application/vnd.ms-excel"),
            },
        )


def test_upload_returns_session_id_and_summary():
    response = _upload()
    assert response.status_code == 200
    body = response.json()

    assert body["session_id"]
    assert body["summary"]["subject_count"] == 658
    assert body["summary"]["teacher_count"] == 99
    assert body["summary"]["intensive_count"] == 45


def test_upload_summary_breaks_down_by_department_and_category():
    body = _upload().json()
    assert body["summary"]["by_department"]["経営"] == 262
    assert body["summary"]["by_category"]["必修"] > 0
    assert body["summary"]["quarter_count"] == 50


def test_upload_returns_warnings():
    body = _upload().json()
    kinds = {w["kind"] for w in body["warnings"]}
    assert "missing_course" in kinds


def test_upload_rejects_broken_workbook(tmp_path):
    import openpyxl

    broken = tmp_path / "broken.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append(["適当な列"])
    workbook.save(broken)

    with broken.open("rb") as bad, TEACHERS.open("rb") as teachers:
        response = client.post(
            "/api/upload",
            files={
                "curriculum": ("b.xlsx", bad, "application/vnd.ms-excel"),
                "teachers": ("t.xlsx", teachers, "application/vnd.ms-excel"),
            },
        )
    assert response.status_code == 400
    assert "想定外" in response.json()["detail"]


def test_upload_accepts_previous_year_files():
    with (
        CURRICULUM.open("rb") as curriculum,
        TEACHERS.open("rb") as teachers,
        CURRICULUM.open("rb") as previous_curriculum,
        TEACHERS.open("rb") as previous_teachers,
    ):
        response = client.post(
            "/api/upload",
            files={
                "curriculum": ("c.xlsx", curriculum, "application/vnd.ms-excel"),
                "teachers": ("t.xlsx", teachers, "application/vnd.ms-excel"),
                "previous_curriculum": ("pc.xlsx", previous_curriculum, "application/vnd.ms-excel"),
                "previous_teachers": ("pt.xlsx", previous_teachers, "application/vnd.ms-excel"),
            },
        )
    assert response.status_code == 200
    assert response.json()["summary"]["has_previous_year"] is True
```

- [ ] **Step 2: 失敗するテストを書く（設定）**

`backend/tests/test_api_settings.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings_store import SettingsStore


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """テストが実際の .env を書き換えないよう差し替える。"""
    import app.api.settings as settings_api

    store = SettingsStore(tmp_path / ".env", tmp_path / "settings.json")
    monkeypatch.setattr(settings_api, "store", store)
    return store


client = TestClient(app)


def test_get_settings_returns_defaults():
    body = client.get("/api/settings").json()
    assert body["model"] == "gemini-2.5-flash"
    assert body["max_retries"] == 3
    assert body["has_api_key"] is False
    assert body["api_key_masked"] is None


def test_put_settings_persists_values():
    client.put("/api/settings", json={"model": "gemini-2.5-pro", "max_retries": 5})
    body = client.get("/api/settings").json()
    assert body["model"] == "gemini-2.5-pro"
    assert body["max_retries"] == 5


def test_put_api_key_then_get_returns_masked_only():
    client.put("/api/settings/api-key", json={"api_key": "AIzaSyEXAMPLE1234567890"})
    body = client.get("/api/settings").json()
    assert body["has_api_key"] is True
    assert body["api_key_masked"] == "AIzaSy****"
    assert "EXAMPLE" not in str(body)


def test_delete_api_key():
    client.put("/api/settings/api-key", json={"api_key": "AIzaSyEXAMPLE1234567890"})
    assert client.delete("/api/settings/api-key").status_code == 200
    assert client.get("/api/settings").json()["has_api_key"] is False


def test_put_settings_rejects_zero_retries():
    response = client.put("/api/settings", json={
        "model": "gemini-2.5-flash", "max_retries": 0
    })
    assert response.status_code == 422
```

- [ ] **Step 3: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_api_upload.py tests/test_api_settings.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.main'`）

- [ ] **Step 4: セッションストアを実装する**

`backend/app/session_store.py`:

```python
"""読み込んだデータと生成結果をセッション単位で保持する。

生成結果は data/sessions/<id>.json にも書き出し、サーバを再起動しても
中身を目視で確認できるようにする。
"""
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.constraints.context import Context
from app.ingest.validators import Warning
from app.logging.session_logger import SessionLogger
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.scheduler.inherit import PreviousEntry
from app.scheduler.pipeline import GenerationResult

SESSIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "sessions"


@dataclass(slots=True)
class SessionData:
    subjects: list[Subject]
    teachers: dict[str, Teacher]
    warnings: list[Warning] = field(default_factory=list)
    previous_entries: dict[str, PreviousEntry] = field(default_factory=dict)
    previous_teachers: dict[str, Teacher] = field(default_factory=dict)
    result: GenerationResult | None = None
    logger: SessionLogger | None = None
    running: bool = False

    @property
    def context(self) -> Context:
        return Context.from_lists(self.subjects, self.teachers)


class SessionStore:
    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._sessions: dict[str, SessionData] = {}
        self._dir = Path(sessions_dir) if sessions_dir else SESSIONS_DIR

    def create(self, data: SessionData) -> str:
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = data
        return session_id

    def get(self, session_id: str) -> SessionData | None:
        return self._sessions.get(session_id)

    def save_result(self, session_id: str) -> Path | None:
        data = self._sessions.get(session_id)
        if data is None or data.result is None:
            return None

        payload = {
            "session_id": session_id,
            "assignments": [
                {
                    "code": code,
                    "slots": [f"{s.day}{s.period}" for s in assignment.slots],
                    "source": assignment.source.value,
                }
                for code, assignment in data.result.timetable.assignments.items()
            ],
            "unplaced": data.result.unplaced,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "subject_code": v.subject_code,
                    "message": v.message,
                    "related_code": v.related_code,
                }
                for v in data.result.violations
            ],
            "intensive": data.result.intensive_codes,
        }
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{session_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


store = SessionStore()
```

- [ ] **Step 5: API のスキーマを実装する**

`backend/app/api/schemas.py`:

```python
"""API のリクエスト・レスポンス型。"""
from pydantic import BaseModel, Field


class WarningOut(BaseModel):
    kind: str
    message: str
    subject_code: str | None = None
    teacher_name: str | None = None


class UploadSummary(BaseModel):
    subject_count: int
    teacher_count: int
    intensive_count: int
    quarter_count: int
    by_department: dict[str, int]
    by_category: dict[str, int]
    by_teacher_kind: dict[str, int]
    has_previous_year: bool


class UploadResponse(BaseModel):
    session_id: str
    summary: UploadSummary
    warnings: list[WarningOut]


class SettingsOut(BaseModel):
    model: str
    max_retries: int
    api_key_masked: str | None
    has_api_key: bool


class SettingsIn(BaseModel):
    model: str = Field(min_length=1)
    max_retries: int = Field(ge=1, le=10)


class ApiKeyIn(BaseModel):
    api_key: str = Field(min_length=1)
```

- [ ] **Step 6: アップロード API を実装する**

`backend/app/api/__init__.py` は空ファイル。

`backend/app/api/upload.py`:

```python
"""Excel のアップロードと読み込みサマリ。"""
import collections
import dataclasses
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import UploadResponse, UploadSummary, WarningOut
from app.ingest.joint_pairing import assign_joint_ids
from app.ingest.markitdown_fallback import read_curriculum_with_fallback
from app.ingest.teacher_reader import read_teachers
from app.ingest.validators import collect_warnings
from app.logging.session_logger import SessionLogger
from app.scheduler.inherit import read_previous_timetable
from app.session_store import SessionData, store

router = APIRouter(prefix="/api", tags=["upload"])


def _persist(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.xlsx").suffix or ".xlsx"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    handle.write(upload.file.read())
    handle.close()
    return Path(handle.name)


@router.post("/upload", response_model=UploadResponse)
async def upload(
    curriculum: UploadFile = File(...),
    teachers: UploadFile = File(...),
    previous_curriculum: UploadFile | None = File(None),
    previous_teachers: UploadFile | None = File(None),
) -> UploadResponse:
    logger = SessionLogger("upload")
    try:
        subjects = read_curriculum_with_fallback(_persist(curriculum), logger)
    except ValueError as error:
        logger.close()
        raise HTTPException(status_code=400, detail=str(error)) from error

    teacher_map = read_teachers(_persist(teachers))
    joint_mismatches = assign_joint_ids(subjects)
    warnings = collect_warnings(subjects, teacher_map, joint_mismatches)

    previous_entries = {}
    previous_teacher_map = {}
    if previous_curriculum is not None:
        previous_entries = read_previous_timetable(_persist(previous_curriculum))
    if previous_teachers is not None:
        previous_teacher_map = read_teachers(_persist(previous_teachers))
    logger.close()

    data = SessionData(
        subjects=subjects,
        teachers=teacher_map,
        warnings=warnings,
        previous_entries=previous_entries,
        previous_teachers=previous_teacher_map,
    )
    session_id = store.create(data)

    summary = UploadSummary(
        subject_count=len(subjects),
        teacher_count=len(teacher_map),
        intensive_count=sum(1 for s in subjects if s.is_intensive),
        quarter_count=sum(1 for s in subjects if s.quarter is not None),
        by_department=dict(
            collections.Counter(s.department.value for s in subjects)
        ),
        by_category=dict(collections.Counter(s.category.value for s in subjects)),
        by_teacher_kind=dict(
            collections.Counter(t.kind.value for t in teacher_map.values())
        ),
        has_previous_year=bool(previous_entries),
    )
    return UploadResponse(
        session_id=session_id,
        summary=summary,
        warnings=[WarningOut(**dataclasses.asdict(w)) for w in warnings],
    )
```

- [ ] **Step 7: 設定 API を実装する**

`backend/app/api/settings.py`:

```python
"""API キーと生成設定の読み書き。API キーの全文は返さない。"""
from fastapi import APIRouter

from app.api.schemas import ApiKeyIn, SettingsIn, SettingsOut
from app.settings_store import AppSettings, SettingsStore

router = APIRouter(prefix="/api/settings", tags=["settings"])

store = SettingsStore()


def _current() -> SettingsOut:
    settings = store.load()
    masked = store.masked_api_key()
    return SettingsOut(
        model=settings.model,
        max_retries=settings.max_retries,
        api_key_masked=masked,
        has_api_key=masked is not None,
    )


@router.get("", response_model=SettingsOut)
async def get_settings() -> SettingsOut:
    return _current()


@router.put("", response_model=SettingsOut)
async def put_settings(payload: SettingsIn) -> SettingsOut:
    store.save(AppSettings(model=payload.model, max_retries=payload.max_retries))
    return _current()


@router.put("/api-key", response_model=SettingsOut)
async def put_api_key(payload: ApiKeyIn) -> SettingsOut:
    store.set_api_key(payload.api_key)
    return _current()


@router.delete("/api-key", response_model=SettingsOut)
async def delete_api_key() -> SettingsOut:
    store.delete_api_key()
    return _current()
```

- [ ] **Step 8: FastAPI アプリを実装する**

`backend/app/main.py`:

```python
"""FastAPI エントリポイント。フロントエンドの静的ファイルも配信する。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import settings, upload

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="時間割自動生成システム")
app.include_router(upload.router)
app.include_router(settings.router)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
```

- [ ] **Step 9: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_api_upload.py tests/test_api_settings.py -v`
Expected: PASS（10 件）

- [ ] **Step 10: サーバが起動することを確認する**

Run: `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000 &` を実行し、`curl -s localhost:8000/api/settings` が JSON を返すことを確認してからプロセスを停止する。

- [ ] **Step 11: コミットする**

```bash
git add backend/app/session_store.py backend/app/api backend/app/main.py backend/tests/test_api_upload.py backend/tests/test_api_settings.py
git commit -m "feat: セッションストアとアップロード・設定 API を追加"
```

---

### Task 23: 生成・結果・出力 API

**Files:**
- Create: `backend/app/api/generate.py`
- Create: `backend/app/api/result.py`
- Create: `backend/app/api/export.py`
- Modify: `backend/app/api/schemas.py`（型を追記）
- Modify: `backend/app/main.py`（ルータを追加）
- Test: `backend/tests/test_api_generate.py`
- Test: `backend/tests/test_api_result.py`

**Interfaces:**
- Consumes: Task 15 の `run_pipeline`、Task 19 の `make_gemini_placer`、Task 16 の `detect_retarget_codes`、Task 20 の `write_timetable_excel`
- Produces:

| メソッド | パス | 内容 |
|---|---|---|
| `GET` | `/api/retarget/{session_id}` | 踏襲モードの組み替え対象候補（コードと理由） |
| `POST` | `/api/generate/{session_id}` | `{"mode": "mock\|optimize\|inherit", "retarget_codes": [...]}`。生成をバックグラウンドで開始 |
| `GET` | `/api/generate/{session_id}/stream` | SSE でログを配信。完了時に `event: done` を送る |
| `GET` | `/api/result/{session_id}` | 配置一覧・未配置・違反・集中講義・科目メタ情報 |
| `POST` | `/api/result/{session_id}/move` | `{"code": "...", "slots": ["月1"]}`。制約違反があれば適用せず違反理由を返す |
| `GET` | `/api/export/{session_id}` | 生成結果の Excel ファイル |

**モードの自動切り替え:** `optimize` または `inherit` が指定されても API キーが無い場合はモックモードに切り替え、その旨を WARN でログに出す（仕様書 §7）。

- [ ] **Step 1: スキーマを追記する**

`backend/app/api/schemas.py` の末尾に追記:

```python
class GenerateIn(BaseModel):
    mode: str = Field(pattern="^(mock|optimize|inherit)$")
    retarget_codes: list[str] = Field(default_factory=list)


class RetargetItem(BaseModel):
    code: str
    name: str
    teacher: str
    reason: str


class ViolationOut(BaseModel):
    rule_id: str
    subject_code: str
    message: str
    related_code: str | None = None


class PlacementOut(BaseModel):
    code: str
    name: str
    teacher: str
    department: str
    year: int
    term: str
    quarter: str | None
    category: str
    slots: list[str]
    source: str


class ResultOut(BaseModel):
    status: str
    placements: list[PlacementOut]
    unplaced: list[str]
    violations: list[ViolationOut]
    intensive: list[str]


class MoveIn(BaseModel):
    code: str
    slots: list[str] = Field(min_length=1)


class MoveOut(BaseModel):
    applied: bool
    violations: list[ViolationOut]
```

- [ ] **Step 2: 失敗するテストを書く（生成 API）**

`backend/tests/test_api_generate.py`:

```python
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
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


def test_export_before_generation_returns_409(monkeypatch):
    session_id = _upload_small(monkeypatch)
    assert client.get(f"/api/export/{session_id}").status_code == 409
```

- [ ] **Step 3: 失敗するテストを書く（結果・編集 API）**

`backend/tests/test_api_result.py`:

```python
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _prepare():
    from app.models.enums import Category, Department, TeacherKind, Term
    from app.models.subject import Subject
    from app.models.teacher import Teacher
    from app.session_store import SessionData, store

    subjects = [
        Subject(
            code="A1", name="科目甲", base_name="科目甲", department=Department.MANAGEMENT,
            year=1, term=Term.SPRING, quarter=None, category=Category.REQUIRED,
            teacher="専任甲",
        ),
        Subject(
            code="A2", name="科目乙", base_name="科目乙", department=Department.MANAGEMENT,
            year=1, term=Term.SPRING, quarter=None, category=Category.REQUIRED,
            teacher="専任乙",
        ),
    ]
    teachers = {
        "専任甲": Teacher("専任甲", TeacherKind.FULL_TIME, research_day="水"),
        "専任乙": Teacher("専任乙", TeacherKind.FULL_TIME),
    }
    session_id = store.create(SessionData(subjects=subjects, teachers=teachers))
    client.post(f"/api/generate/{session_id}", json={"mode": "mock"})

    deadline = time.time() + 20
    while time.time() < deadline:
        if client.get(f"/api/result/{session_id}").json()["status"] == "done":
            return session_id
        time.sleep(0.1)
    raise AssertionError("生成が完了しませんでした")


def test_result_includes_subject_metadata():
    session_id = _prepare()
    placements = client.get(f"/api/result/{session_id}").json()["placements"]
    entry = next(p for p in placements if p["code"] == "A1")
    assert entry["name"] == "科目甲"
    assert entry["teacher"] == "専任甲"
    assert entry["department"] == "経営"
    assert len(entry["slots"]) == 1


def test_move_to_free_slot_is_applied():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "A1", "slots": ["金5"]}
    )
    assert response.status_code == 200
    assert response.json()["applied"] is True

    placements = client.get(f"/api/result/{session_id}").json()["placements"]
    entry = next(p for p in placements if p["code"] == "A1")
    assert entry["slots"] == ["金5"]
    assert entry["source"] == "manual"


def test_move_onto_research_day_is_rejected():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "A1", "slots": ["水1"]}
    )
    body = response.json()
    assert body["applied"] is False
    assert [v["rule_id"] for v in body["violations"]] == ["H6"]

    placements = client.get(f"/api/result/{session_id}").json()["placements"]
    assert next(p for p in placements if p["code"] == "A1")["slots"] != ["水1"]


def test_move_rejects_unknown_code():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "Z9", "slots": ["月1"]}
    )
    assert response.status_code == 404


def test_move_rejects_bad_slot_label():
    session_id = _prepare()
    response = client.post(
        f"/api/result/{session_id}/move", json={"code": "A1", "slots": ["土1"]}
    )
    assert response.status_code == 400
```

- [ ] **Step 4: テストを実行して失敗することを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_api_generate.py tests/test_api_result.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.api.generate'`）

- [ ] **Step 5: 生成 API を実装する**

`backend/app/api/generate.py`:

```python
"""生成の実行と、SSE によるログ配信。

生成は別スレッドで動かし、ログはロガーの購読キューを通して流す。
"""
import json
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import GenerateIn, RetargetItem
from app.gemini.client import RealGeminiClient
from app.logging.session_logger import SessionLogger
from app.scheduler.gemini_stage import make_gemini_placer
from app.scheduler.inherit import InheritPlan, detect_retarget_codes
from app.scheduler.pipeline import GenerationMode, run_pipeline
from app.session_store import store
from app.settings_store import SettingsStore

router = APIRouter(prefix="/api", tags=["generate"])

settings_store = SettingsStore()


def _require_session(session_id: str):
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return data


@router.get("/retarget/{session_id}", response_model=list[RetargetItem])
async def get_retarget(session_id: str) -> list[RetargetItem]:
    data = _require_session(session_id)
    codes = detect_retarget_codes(
        data.subjects, data.teachers, data.previous_entries, data.previous_teachers
    )
    items: list[RetargetItem] = []
    for subject in data.subjects:
        if subject.code not in codes:
            continue
        teacher = data.teachers.get(subject.teacher)
        if teacher is not None and teacher.kind.value in ("非常勤", "特任"):
            reason = f"非専任（{teacher.kind.value}）"
        elif subject.code not in data.previous_entries:
            reason = "前年度に存在しない新規科目"
        elif data.previous_entries[subject.code].teacher != subject.teacher:
            reason = "担当教員の変更"
        else:
            reason = "研究日の変更"
        items.append(RetargetItem(
            code=subject.code, name=subject.name, teacher=subject.teacher, reason=reason
        ))
    return items


@router.post("/generate/{session_id}", status_code=202)
async def start_generation(session_id: str, payload: GenerateIn) -> dict:
    data = _require_session(session_id)
    if data.running:
        raise HTTPException(status_code=409, detail="生成が既に実行中です")

    settings = settings_store.load()
    api_key = settings_store.get_api_key()
    mode = GenerationMode(payload.mode)

    logger = SessionLogger(session_id)
    if mode is not GenerationMode.MOCK and not api_key:
        logger.warn("API キーが未設定のためモックモードで実行します", stage="Stage 0")
        mode = GenerationMode.MOCK

    placer = None
    if mode is not GenerationMode.MOCK:
        placer = make_gemini_placer(
            RealGeminiClient(api_key, settings.model), settings.max_retries
        )

    inherit_plan = None
    if mode is GenerationMode.INHERIT:
        retarget = set(payload.retarget_codes) or detect_retarget_codes(
            data.subjects, data.teachers, data.previous_entries, data.previous_teachers
        )
        inherit_plan = InheritPlan(data.previous_entries, retarget)

    data.logger = logger
    data.result = None
    data.running = True

    def worker() -> None:
        try:
            data.result = run_pipeline(
                data.subjects, data.teachers, mode, logger,
                gemini_placer=placer, inherit_plan=inherit_plan,
            )
            store.save_result(session_id)
        except Exception as error:  # 生成を止めず、必ずログに残す
            logger.error(f"生成中に予期しないエラーが発生しました: {error}", stage="Stage 6")
        finally:
            data.running = False
            logger.close()

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "started", "mode": mode.value}


@router.get("/generate/{session_id}/stream")
async def stream_logs(session_id: str) -> StreamingResponse:
    data = _require_session(session_id)
    if data.logger is None:
        raise HTTPException(status_code=409, detail="まだ生成が開始されていません")

    logger = data.logger
    backlog = logger.events
    queue = logger.subscribe()

    def events():
        for event in backlog:
            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        while True:
            event = queue.get()
            if event is None:
                yield "event: done\ndata: {}\n\n"
                return
            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
```

- [ ] **Step 6: 結果 API を実装する**

`backend/app/api/result.py`:

```python
"""生成結果の取得と、ドラッグ&ドロップによる手動編集。

編集の可否判定は constraints.validator を通す。AI 経由と手動編集で
判定がずれないことがこの設計の要点。
"""
from fastapi import APIRouter, HTTPException

from app.api.schemas import MoveIn, MoveOut, PlacementOut, ResultOut, ViolationOut
from app.constraints.validator import check_placement, validate_all
from app.gemini.prompts import parse_slot_label, slot_label
from app.models.timetable import AssignmentSource
from app.session_store import store

router = APIRouter(prefix="/api/result", tags=["result"])


def _require_session(session_id: str):
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return data


def _to_violation(violation) -> ViolationOut:
    return ViolationOut(
        rule_id=violation.rule_id,
        subject_code=violation.subject_code,
        message=violation.message,
        related_code=violation.related_code,
    )


@router.get("/{session_id}", response_model=ResultOut)
async def get_result(session_id: str) -> ResultOut:
    data = _require_session(session_id)
    if data.result is None:
        return ResultOut(
            status="running" if data.running else "pending",
            placements=[], unplaced=[], violations=[], intensive=[],
        )

    context = data.context
    placements = []
    for code, assignment in data.result.timetable.assignments.items():
        subject = context.subjects.get(code)
        if subject is None:
            continue
        placements.append(PlacementOut(
            code=code,
            name=subject.name,
            teacher=subject.teacher,
            department=subject.department.value,
            year=subject.year,
            term=subject.term.value,
            quarter=subject.quarter.value if subject.quarter else None,
            category=subject.category.value,
            slots=[slot_label(s) for s in assignment.slots],
            source=assignment.source.value,
        ))

    return ResultOut(
        status="done",
        placements=placements,
        unplaced=data.result.unplaced,
        violations=[_to_violation(v) for v in data.result.violations],
        intensive=data.result.intensive_codes,
    )


@router.post("/{session_id}/move", response_model=MoveOut)
async def move(session_id: str, payload: MoveIn) -> MoveOut:
    data = _require_session(session_id)
    if data.result is None:
        raise HTTPException(status_code=409, detail="まだ生成が完了していません")

    context = data.context
    subject = context.subjects.get(payload.code)
    if subject is None:
        raise HTTPException(status_code=404, detail="科目が見つかりません")

    try:
        slots = tuple(parse_slot_label(label) for label in payload.slots)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    timetable = data.result.timetable
    violations = check_placement(context, timetable, subject, slots)
    if violations:
        return MoveOut(applied=False, violations=[_to_violation(v) for v in violations])

    timetable.remove(payload.code)
    timetable.place(payload.code, slots, AssignmentSource.MANUAL)
    data.result.violations = validate_all(context, timetable)
    store.save_result(session_id)

    return MoveOut(applied=True, violations=[])
```

- [ ] **Step 7: 出力 API を実装する**

`backend/app/api/export.py`:

```python
"""生成結果を Excel ファイルとして返す。"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.export.excel_writer import write_timetable_excel
from app.session_store import store

router = APIRouter(prefix="/api/export", tags=["export"])

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("/{session_id}")
async def export_excel(session_id: str) -> FileResponse:
    data = store.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    if data.result is None:
        raise HTTPException(status_code=409, detail="まだ生成が完了していません")

    directory = Path(tempfile.mkdtemp())
    path = write_timetable_excel(data.context, data.result, directory / "時間割.xlsx")
    return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename="時間割.xlsx")
```

- [ ] **Step 8: ルータを登録する**

`backend/app/main.py` の import 節と登録を次に置き換える。

```python
from app.api import export, generate, result, settings, upload

app = FastAPI(title="時間割自動生成システム")
app.include_router(upload.router)
app.include_router(settings.router)
app.include_router(generate.router)
app.include_router(result.router)
app.include_router(export.router)
```

`StaticFiles` のマウントは**すべてのルータ登録より後**に置くこと。先に置くと `/api/...` が静的ファイル配信に飲まれる。

- [ ] **Step 9: テストを実行して通ることを確認する**

Run: `cd backend && ../.venv/bin/pytest tests/test_api_generate.py tests/test_api_result.py -v`
Expected: PASS（11 件）

- [ ] **Step 10: 全テストを実行する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 11: コミットする**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_api_generate.py backend/tests/test_api_result.py
git commit -m "feat: 生成・結果・出力 API を追加"
```

---

### Task 24: フロントエンドの骨組み・アップロード画面・設定画面

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/css/style.css`
- Create: `frontend/js/api.js`
- Create: `frontend/js/upload.js`
- Create: `frontend/js/settings.js`
- Create: `frontend/js/main.js`

**Interfaces:**
- Consumes: Task 22・23 の API
- Produces:
  - `api.js` — `uploadFiles`, `getSettings`, `putSettings`, `putApiKey`, `deleteApiKey`, `getRetarget`, `startGeneration`, `getResult`, `moveSubject`, `exportUrl`, `streamUrl`
  - `window.appState` — `{ sessionId: string | null }`
  - `initUpload()`, `initSettings()`（`main.js` から呼ばれる）

**画面遷移:** 単一ページ。上部のタブで `#view-upload` / `#view-generate` / `#view-result` / `#view-settings` を切り替える。アップロード完了までは生成・結果タブを無効にする。

- [ ] **Step 1: `frontend/index.html` を作成する**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>時間割自動生成システム</title>
  <link rel="stylesheet" href="/css/style.css">
</head>
<body>
  <header>
    <h1>時間割自動生成システム</h1>
    <nav id="tabs">
      <button data-view="upload" class="active">① ファイル読込</button>
      <button data-view="generate" disabled>② 生成</button>
      <button data-view="result" disabled>③ 結果</button>
      <button data-view="settings">④ 設定</button>
    </nav>
  </header>

  <main>
    <section id="view-upload" class="view active">
      <h2>Excel ファイルの読み込み</h2>
      <div id="dropzone">
        <p>カリキュラム一覧・教員一覧の Excel をここにドラッグ&amp;ドロップ</p>
        <p class="hint">踏襲モードを使う場合は前年度のファイルも一緒に投入してください</p>
        <input type="file" id="file-input" multiple accept=".xlsx">
      </div>
      <div id="file-assign"></div>
      <button id="upload-button" disabled>読み込む</button>
      <div id="upload-summary"></div>
      <div id="upload-warnings"></div>
    </section>

    <section id="view-generate" class="view">
      <h2>時間割の生成</h2>
      <div id="mode-select">
        <label><input type="radio" name="mode" value="mock" checked> モックモード</label>
        <label><input type="radio" name="mode" value="optimize"> 最適化モード</label>
        <label><input type="radio" name="mode" value="inherit"> 踏襲モード</label>
      </div>
      <div id="retarget-panel" hidden>
        <h3>組み替え対象</h3>
        <div id="retarget-list"></div>
      </div>
      <button id="generate-button">生成を開始</button>
      <div id="generate-status"></div>
    </section>

    <section id="view-result" class="view">
      <h2>生成結果</h2>
      <div id="result-tabs"></div>
      <div id="timetable-grid"></div>
      <aside id="result-side">
        <h3>未配置科目</h3>
        <ul id="unplaced-list"></ul>
        <h3>集中講義</h3>
        <ul id="intensive-list"></ul>
        <h3>制約違反</h3>
        <ul id="violation-list"></ul>
      </aside>
      <button id="export-button">Excel として出力</button>
    </section>

    <section id="view-settings" class="view">
      <h2>Gemini の設定</h2>
      <div class="field">
        <label for="api-key">API キー</label>
        <input type="password" id="api-key" placeholder="AIza...">
        <span id="api-key-status"></span>
        <button id="save-key">保存</button>
        <button id="delete-key">削除</button>
      </div>
      <div class="field">
        <label for="model">モデル</label>
        <input list="model-options" id="model">
        <datalist id="model-options">
          <option value="gemini-2.5-flash"></option>
          <option value="gemini-2.5-pro"></option>
          <option value="gemini-2.5-flash-lite"></option>
        </datalist>
      </div>
      <div class="field">
        <label for="max-retries">再試行回数</label>
        <input type="number" id="max-retries" min="1" max="10">
      </div>
      <button id="save-settings">設定を保存</button>
      <div id="settings-status"></div>
    </section>
  </main>

  <div id="log-panel" class="collapsed">
    <div id="log-header">
      <span>ログ</span>
      <div>
        <select id="log-filter">
          <option value="ALL">すべて</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
        <button id="log-toggle">▲</button>
      </div>
    </div>
    <div id="log-body"></div>
  </div>

  <script src="/js/api.js"></script>
  <script src="/js/upload.js"></script>
  <script src="/js/settings.js"></script>
  <script src="/js/logviewer.js"></script>
  <script src="/js/generate.js"></script>
  <script src="/js/timetable.js"></script>
  <script src="/js/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: `frontend/css/style.css` を作成する**

```css
:root {
  --bg: #f6f7f9;
  --panel: #ffffff;
  --border: #d5d9e0;
  --text: #1f2430;
  --muted: #6b7280;
  --accent: #2563eb;
  --warn: #b45309;
  --error: #b91c1c;
  --prelock: #e0e7ff;
  --gemini: #dcfce7;
  --solver: #fef3c7;
  --manual: #fae8ff;
  --inherited: #e0f2fe;
  --log-height: 15rem;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: "Hiragino Sans", "Noto Sans JP", sans-serif;
  background: var(--bg);
  color: var(--text);
  padding-bottom: 3rem;
}

header { padding: 1rem 1.5rem; background: var(--panel); border-bottom: 1px solid var(--border); }
header h1 { margin: 0 0 0.75rem; font-size: 1.25rem; }

#tabs button {
  padding: 0.5rem 1rem;
  margin-right: 0.5rem;
  border: 1px solid var(--border);
  background: var(--panel);
  border-radius: 0.375rem;
  cursor: pointer;
}
#tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
#tabs button:disabled { opacity: 0.4; cursor: not-allowed; }

main { padding: 1.5rem; }
.view { display: none; }
.view.active { display: block; }

#dropzone {
  border: 2px dashed var(--border);
  border-radius: 0.5rem;
  padding: 2.5rem;
  text-align: center;
  background: var(--panel);
}
#dropzone.dragover { border-color: var(--accent); background: #eff6ff; }
.hint { color: var(--muted); font-size: 0.875rem; }

button {
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--panel);
  cursor: pointer;
}
button:disabled { opacity: 0.4; cursor: not-allowed; }

.field { margin-bottom: 1rem; }
.field label { display: inline-block; min-width: 8rem; }

table.timetable { border-collapse: collapse; width: 100%; background: var(--panel); }
table.timetable th, table.timetable td {
  border: 1px solid var(--border);
  padding: 0.25rem;
  vertical-align: top;
  min-width: 9rem;
  height: 5.5rem;
}
table.timetable td.dragover { background: #eff6ff; }

.card {
  border-radius: 0.25rem;
  padding: 0.25rem 0.375rem;
  margin-bottom: 0.25rem;
  font-size: 0.75rem;
  cursor: grab;
  border: 1px solid var(--border);
}
.card.source-prelock { background: var(--prelock); }
.card.source-gemini { background: var(--gemini); }
.card.source-solver { background: var(--solver); }
.card.source-manual { background: var(--manual); }
.card.source-inherited { background: var(--inherited); }
.card.violating { outline: 2px solid var(--error); }

#log-panel {
  position: fixed;
  left: 0; right: 0; bottom: 0;
  background: #111827;
  color: #e5e7eb;
  font-family: monospace;
  font-size: 0.75rem;
}
#log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.375rem 0.75rem;
  background: #1f2937;
}
#log-body { height: var(--log-height); overflow-y: auto; padding: 0.5rem 0.75rem; }
#log-panel.collapsed #log-body { display: none; }
.log-INFO { color: #d1d5db; }
.log-WARN { color: #fbbf24; }
.log-ERROR { color: #f87171; }
```

- [ ] **Step 3: `frontend/js/api.js` を作成する**

```javascript
"use strict";

window.appState = { sessionId: null };

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_) { /* JSON でない応答はそのまま */ }
    throw new Error(detail);
  }
  return response.json();
}

const api = {
  uploadFiles(formData) {
    return request("/api/upload", { method: "POST", body: formData });
  },
  getSettings() {
    return request("/api/settings");
  },
  putSettings(payload) {
    return request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  putApiKey(apiKey) {
    return request("/api/settings/api-key", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
  },
  deleteApiKey() {
    return request("/api/settings/api-key", { method: "DELETE" });
  },
  getRetarget(sessionId) {
    return request(`/api/retarget/${sessionId}`);
  },
  startGeneration(sessionId, mode, retargetCodes) {
    return request(`/api/generate/${sessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, retarget_codes: retargetCodes || [] }),
    });
  },
  getResult(sessionId) {
    return request(`/api/result/${sessionId}`);
  },
  moveSubject(sessionId, code, slots) {
    return request(`/api/result/${sessionId}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, slots }),
    });
  },
  streamUrl(sessionId) {
    return `/api/generate/${sessionId}/stream`;
  },
  exportUrl(sessionId) {
    return `/api/export/${sessionId}`;
  },
};
```

- [ ] **Step 4: `frontend/js/upload.js` を作成する**

```javascript
"use strict";

const ROLE_LABELS = {
  curriculum: "カリキュラム一覧（今年度）",
  teachers: "教員一覧（今年度）",
  previous_curriculum: "前年度の時間割（任意）",
  previous_teachers: "前年度の教員一覧（任意）",
};

let selectedFiles = [];

function guessRole(name, used) {
  const isPrevious = /前年度|previous|昨年/.test(name);
  const isTeacher = /教員|teacher/.test(name);
  const candidates = isPrevious
    ? (isTeacher ? ["previous_teachers"] : ["previous_curriculum"])
    : (isTeacher ? ["teachers"] : ["curriculum"]);
  const fallback = ["curriculum", "teachers", "previous_curriculum", "previous_teachers"];
  return candidates.concat(fallback).find((role) => !used.has(role)) || "curriculum";
}

function renderFileAssignment() {
  const container = document.getElementById("file-assign");
  container.innerHTML = "";
  const used = new Set();

  selectedFiles.forEach((entry, index) => {
    entry.role = entry.role || guessRole(entry.file.name, used);
    used.add(entry.role);

    const row = document.createElement("div");
    row.className = "field";
    const select = document.createElement("select");
    Object.entries(ROLE_LABELS).forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === entry.role;
      select.appendChild(option);
    });
    select.addEventListener("change", () => { selectedFiles[index].role = select.value; });

    row.append(document.createTextNode(entry.file.name + " → "), select);
    container.appendChild(row);
  });

  const roles = new Set(selectedFiles.map((entry) => entry.role));
  document.getElementById("upload-button").disabled =
    !(roles.has("curriculum") && roles.has("teachers"));
}

function addFiles(fileList) {
  Array.from(fileList).forEach((file) => selectedFiles.push({ file, role: null }));
  renderFileAssignment();
}

function renderSummary(summary) {
  const entries = [
    ["科目数", summary.subject_count],
    ["教員数", summary.teacher_count],
    ["集中講義", summary.intensive_count],
    ["クオーター科目", summary.quarter_count],
  ];
  const byDept = Object.entries(summary.by_department)
    .map(([key, value]) => `${key} ${value}`).join(" / ");
  const byCat = Object.entries(summary.by_category)
    .map(([key, value]) => `${key} ${value}`).join(" / ");
  const byKind = Object.entries(summary.by_teacher_kind)
    .map(([key, value]) => `${key} ${value}`).join(" / ");

  document.getElementById("upload-summary").innerHTML = `
    <h3>読み込み結果</h3>
    <ul>
      ${entries.map(([k, v]) => `<li>${k}: ${v}</li>`).join("")}
      <li>学科別: ${byDept}</li>
      <li>科目区分別: ${byCat}</li>
      <li>教員区分別: ${byKind}</li>
      <li>前年度データ: ${summary.has_previous_year ? "あり" : "なし"}</li>
    </ul>`;
}

function renderWarnings(warnings) {
  const container = document.getElementById("upload-warnings");
  if (!warnings.length) {
    container.innerHTML = "<p>警告はありません。</p>";
    return;
  }
  container.innerHTML = `
    <h3>警告 ${warnings.length} 件</h3>
    <ul>${warnings.map((w) => `<li>[${w.kind}] ${w.message}</li>`).join("")}</ul>`;
}

async function submitFiles() {
  const button = document.getElementById("upload-button");
  button.disabled = true;
  const formData = new FormData();
  selectedFiles.forEach((entry) => formData.append(entry.role, entry.file));

  try {
    const body = await api.uploadFiles(formData);
    window.appState.sessionId = body.session_id;
    renderSummary(body.summary);
    renderWarnings(body.warnings);
    document.querySelector('#tabs button[data-view="generate"]').disabled = false;
  } catch (error) {
    document.getElementById("upload-summary").innerHTML =
      `<p class="log-ERROR">読み込みに失敗しました: ${error.message}</p>`;
  } finally {
    button.disabled = false;
  }
}

function initUpload() {
  const dropzone = document.getElementById("dropzone");
  const input = document.getElementById("file-input");

  ["dragenter", "dragover"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    dropzone.addEventListener(name, () => dropzone.classList.remove("dragover"));
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  });
  input.addEventListener("change", () => addFiles(input.files));
  document.getElementById("upload-button").addEventListener("click", submitFiles);
}
```

- [ ] **Step 5: `frontend/js/settings.js` を作成する**

```javascript
"use strict";

function applySettings(body) {
  document.getElementById("model").value = body.model;
  document.getElementById("max-retries").value = body.max_retries;
  document.getElementById("api-key-status").textContent =
    body.has_api_key ? `保存済み（${body.api_key_masked}）` : "未設定";
}

function showStatus(message, isError) {
  const element = document.getElementById("settings-status");
  element.textContent = message;
  element.className = isError ? "log-ERROR" : "";
}

async function initSettings() {
  try {
    applySettings(await api.getSettings());
  } catch (error) {
    showStatus(`設定の読み込みに失敗しました: ${error.message}`, true);
  }

  document.getElementById("save-key").addEventListener("click", async () => {
    const input = document.getElementById("api-key");
    if (!input.value.trim()) {
      showStatus("API キーを入力してください", true);
      return;
    }
    try {
      applySettings(await api.putApiKey(input.value.trim()));
      input.value = "";
      showStatus("API キーを保存しました");
    } catch (error) {
      showStatus(`保存に失敗しました: ${error.message}`, true);
    }
  });

  document.getElementById("delete-key").addEventListener("click", async () => {
    try {
      applySettings(await api.deleteApiKey());
      showStatus("API キーを削除しました");
    } catch (error) {
      showStatus(`削除に失敗しました: ${error.message}`, true);
    }
  });

  document.getElementById("save-settings").addEventListener("click", async () => {
    try {
      applySettings(await api.putSettings({
        model: document.getElementById("model").value.trim(),
        max_retries: Number(document.getElementById("max-retries").value),
      }));
      showStatus("設定を保存しました");
    } catch (error) {
      showStatus(`保存に失敗しました: ${error.message}`, true);
    }
  });
}
```

- [ ] **Step 6: `frontend/js/main.js` を作成する**

```javascript
"use strict";

function switchView(name) {
  document.querySelectorAll("#tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  if (name === "result") renderTimetable();
  if (name === "generate") onEnterGenerateView();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("#tabs button").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  initUpload();
  initSettings();
  initLogViewer();
  initGenerate();
  initTimetable();
});
```

- [ ] **Step 7: サーバを起動して手動確認する**

Run: `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000`

ブラウザで `http://localhost:8000/` を開き、次を確認する。

1. 4 つのタブが表示され、「② 生成」「③ 結果」が無効になっている
2. 「④ 設定」タブでモデル `gemini-2.5-flash`、再試行回数 `3` が表示される
3. API キーに適当な文字列を入れて保存すると「保存済み（AIza****）」のようにマスク表示される。削除すると「未設定」に戻る
4. カリキュラム一覧と教員一覧をドロップすると、それぞれの役割が自動で割り当てられ「読み込む」が有効になる
5. 読み込むと科目数 658・教員数 99 のサマリと警告一覧が出て、「② 生成」タブが有効になる

Task 25・26 が未実装のため、`main.js` が呼ぶ `initLogViewer` / `initGenerate` / `initTimetable` / `renderTimetable` / `onEnterGenerateView` は未定義で、コンソールにエラーが出る。**この段階では 1〜5 が動けばよい。** Task 25・26 の完了後に再確認する。

- [ ] **Step 8: コミットする**

```bash
git add frontend/index.html frontend/css frontend/js/api.js frontend/js/upload.js frontend/js/settings.js frontend/js/main.js
git commit -m "feat: フロントエンドの骨組みとアップロード・設定画面を追加"
```

---

### Task 25: 生成画面とログビューア

**Files:**
- Create: `frontend/js/logviewer.js`
- Create: `frontend/js/generate.js`

**Interfaces:**
- Consumes: `api.streamUrl`, `api.startGeneration`, `api.getRetarget`, `api.getResult`
- Produces:
  - `initLogViewer()`, `connectLogStream(sessionId)`, `appendLog(event)`
  - `initGenerate()`, `onEnterGenerateView()`

**ログビューアの仕様（仕様書 §8.2）:** 画面下部の折りたたみパネル。`▲` / `▼` ボタンで開閉。レベルで絞り込める。SSE の `done` イベントで接続を閉じ、結果タブを有効にする。

- [ ] **Step 1: `frontend/js/logviewer.js` を作成する**

```javascript
"use strict";

let logSource = null;
let logFilter = "ALL";
const logEntries = [];

function renderLogEntries() {
  const body = document.getElementById("log-body");
  body.innerHTML = logEntries
    .filter((entry) => logFilter === "ALL" || entry.level === logFilter)
    .map((entry) => {
      const stage = entry.stage ? `[${entry.stage}] ` : "";
      return `<div class="log-${entry.level}">${entry.timestamp} ${entry.level} ${stage}${escapeHtml(entry.message)}</div>`;
    })
    .join("");
  body.scrollTop = body.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function appendLog(event) {
  logEntries.push(event);
  renderLogEntries();
}

function clearLog() {
  logEntries.length = 0;
  renderLogEntries();
}

function openLogPanel() {
  document.getElementById("log-panel").classList.remove("collapsed");
  document.getElementById("log-toggle").textContent = "▼";
}

function connectLogStream(sessionId, onDone) {
  if (logSource) logSource.close();
  logSource = new EventSource(api.streamUrl(sessionId));

  logSource.onmessage = (message) => {
    if (!message.data || message.data === "{}") return;
    appendLog(JSON.parse(message.data));
  };
  logSource.addEventListener("done", () => {
    logSource.close();
    logSource = null;
    if (onDone) onDone();
  });
  logSource.onerror = () => {
    appendLog({
      level: "ERROR",
      message: "ログ配信が切断されました",
      timestamp: new Date().toISOString().slice(0, 19),
      stage: null,
    });
    if (logSource) logSource.close();
    logSource = null;
  };
}

function initLogViewer() {
  document.getElementById("log-toggle").addEventListener("click", () => {
    const panel = document.getElementById("log-panel");
    panel.classList.toggle("collapsed");
    document.getElementById("log-toggle").textContent =
      panel.classList.contains("collapsed") ? "▲" : "▼";
  });
  document.getElementById("log-filter").addEventListener("change", (event) => {
    logFilter = event.target.value;
    renderLogEntries();
  });
}
```

- [ ] **Step 2: `frontend/js/generate.js` を作成する**

```javascript
"use strict";

let retargetItems = [];

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function renderRetargetList() {
  const container = document.getElementById("retarget-list");
  if (!retargetItems.length) {
    container.innerHTML = "<p>組み替え対象はありません。前年度ファイルを読み込んでください。</p>";
    return;
  }
  container.innerHTML = retargetItems
    .map((item) => `
      <label class="field">
        <input type="checkbox" value="${item.code}" checked>
        ${item.code} ${item.name}（${item.teacher}） — ${item.reason}
      </label>`)
    .join("");
}

async function onEnterGenerateView() {
  const isInherit = selectedMode() === "inherit";
  document.getElementById("retarget-panel").hidden = !isInherit;
  if (!isInherit || !window.appState.sessionId) return;

  try {
    retargetItems = await api.getRetarget(window.appState.sessionId);
    renderRetargetList();
  } catch (error) {
    document.getElementById("retarget-list").innerHTML =
      `<p class="log-ERROR">組み替え対象の取得に失敗しました: ${error.message}</p>`;
  }
}

function checkedRetargetCodes() {
  return Array.from(
    document.querySelectorAll("#retarget-list input:checked")
  ).map((input) => input.value);
}

function setStatus(message, isError) {
  const element = document.getElementById("generate-status");
  element.textContent = message;
  element.className = isError ? "log-ERROR" : "";
}

async function startGeneration() {
  const sessionId = window.appState.sessionId;
  if (!sessionId) {
    setStatus("先にファイルを読み込んでください", true);
    return;
  }

  const button = document.getElementById("generate-button");
  button.disabled = true;
  clearLog();
  openLogPanel();
  setStatus("生成中です…");

  try {
    const body = await api.startGeneration(
      sessionId, selectedMode(), checkedRetargetCodes()
    );
    if (body.mode !== selectedMode()) {
      setStatus(`API キーが未設定のため ${body.mode} モードで実行します`);
    }
    connectLogStream(sessionId, async () => {
      button.disabled = false;
      const result = await api.getResult(sessionId);
      setStatus(
        `完了: 配置 ${result.placements.length} 件 / ` +
        `未配置 ${result.unplaced.length} 件 / 違反 ${result.violations.length} 件`
      );
      document.querySelector('#tabs button[data-view="result"]').disabled = false;
    });
  } catch (error) {
    button.disabled = false;
    setStatus(`生成を開始できませんでした: ${error.message}`, true);
  }
}

function initGenerate() {
  document.getElementById("generate-button").addEventListener("click", startGeneration);
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", onEnterGenerateView);
  });
}
```

- [ ] **Step 3: 手動確認する**

Run: `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000`

ブラウザで次を確認する。

1. ファイルを読み込んでから「② 生成」タブへ移動し、モックモードのまま「生成を開始」を押す
2. 画面下部のログパネルが自動で開き、`Stage 0` から `Stage 6` までのログが流れる
3. 完了後に「完了: 配置 … / 未配置 … / 違反 …」が表示され、「③ 結果」タブが有効になる
4. ログのレベル絞り込みで `WARN` を選ぶと警告だけが残る
5. `▼` ボタンでログパネルが閉じ、`▲` で再び開く
6. 「踏襲モード」を選ぶと組み替え対象パネルが表示される（前年度ファイル未投入なら「組み替え対象はありません」）

Task 26 が未実装のため、「③ 結果」タブは空のままでよい。

- [ ] **Step 4: コミットする**

```bash
git add frontend/js/logviewer.js frontend/js/generate.js
git commit -m "feat: 生成画面とログビューアを追加"
```

---

### Task 26: 結果画面（グリッド表示とドラッグ&ドロップ編集）

**Files:**
- Create: `frontend/js/timetable.js`

**Interfaces:**
- Consumes: `api.getResult`, `api.moveSubject`, `api.exportUrl`
- Produces: `initTimetable()`, `renderTimetable()`

**仕様（仕様書 §8.1 ③）:**

- 学科タブ × 学期タブでグリッドを切り替える（縦 1〜5 限 × 横 月〜金）
- 科目カードをドラッグして別のコマへドロップすると `POST /api/result/{id}/move` を呼ぶ
- 移動先が制約違反なら適用せず、違反理由をアラートで表示してカードを元の位置に戻す
- `source` ごとにカードを色分けする（事前ロック / AI / ソルバー / 手動 / 踏襲）
- 違反に関係する科目カードに赤枠を付ける
- 未配置科目・集中講義・制約違反をサイドに一覧表示する
- 「Excel として出力」で `/api/export/{id}` をダウンロードする

**複数コマ科目の扱い:** ▲科目は 2 コマを占める。ドロップ時は「掴んだコマからの相対位置」を保って全コマを移動する。連続要件は `H10` がサーバ側で判定するため、フロントは移動先を組み立てるだけでよい。

- [ ] **Step 1: `frontend/js/timetable.js` を作成する**

```javascript
"use strict";

const DAYS = ["月", "火", "水", "木", "金"];
const PERIODS = [1, 2, 3, 4, 5];
const SOURCE_LABELS = {
  prelock: "事前ロック",
  gemini: "AI 配置",
  solver: "ソルバー補完",
  manual: "手動編集",
  inherited: "前年度踏襲",
};

let resultData = null;
let currentDepartment = "経営";
let currentTerm = "前期";

function parseSlot(label) {
  return { day: label.slice(0, 1), period: Number(label.slice(1)) };
}

function violatingCodes() {
  if (!resultData) return new Set();
  const codes = new Set();
  resultData.violations.forEach((violation) => {
    codes.add(violation.subject_code);
    if (violation.related_code) codes.add(violation.related_code);
  });
  return codes;
}

function renderTabs() {
  const departments = ["経営", "会計", "短期大学部"];
  const terms = ["前期", "後期"];
  document.getElementById("result-tabs").innerHTML = `
    <div>
      ${departments.map((d) => `
        <button class="dept-tab${d === currentDepartment ? " active" : ""}"
                data-dept="${d}">${d}</button>`).join("")}
    </div>
    <div>
      ${terms.map((t) => `
        <button class="term-tab${t === currentTerm ? " active" : ""}"
                data-term="${t}">${t}</button>`).join("")}
    </div>`;

  document.querySelectorAll(".dept-tab").forEach((button) => {
    button.addEventListener("click", () => {
      currentDepartment = button.dataset.dept;
      renderTimetable();
    });
  });
  document.querySelectorAll(".term-tab").forEach((button) => {
    button.addEventListener("click", () => {
      currentTerm = button.dataset.term;
      renderTimetable();
    });
  });
}

function cardHtml(placement, grabbedLabel, isViolating) {
  const quarter = placement.quarter ? `[${placement.quarter}]` : "";
  return `
    <div class="card source-${placement.source}${isViolating ? " violating" : ""}"
         draggable="true"
         data-code="${placement.code}"
         data-grabbed="${grabbedLabel}"
         title="${SOURCE_LABELS[placement.source] || placement.source}">
      <strong>${placement.name}${quarter}</strong><br>
      ${placement.teacher}<br>
      ${placement.year}年・${placement.category}
    </div>`;
}

function renderGrid() {
  const violating = violatingCodes();
  const visible = resultData.placements.filter(
    (p) => p.department === currentDepartment && p.term === currentTerm
  );

  const rows = PERIODS.map((period) => {
    const cells = DAYS.map((day) => {
      const label = `${day}${period}`;
      const cards = visible
        .filter((p) => p.slots.includes(label))
        .map((p) => cardHtml(p, label, violating.has(p.code)))
        .join("");
      return `<td data-slot="${label}">${cards}</td>`;
    }).join("");
    return `<tr><th>${period}限</th>${cells}</tr>`;
  }).join("");

  document.getElementById("timetable-grid").innerHTML = `
    <table class="timetable">
      <thead><tr><th></th>${DAYS.map((d) => `<th>${d}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  attachDragHandlers();
}

function renderSide() {
  const byCode = Object.fromEntries(resultData.placements.map((p) => [p.code, p]));
  const describe = (code) => (byCode[code] ? `${code} ${byCode[code].name}` : code);

  document.getElementById("unplaced-list").innerHTML =
    resultData.unplaced.map((c) => `<li>${describe(c)}</li>`).join("") || "<li>なし</li>";
  document.getElementById("intensive-list").innerHTML =
    resultData.intensive.map((c) => `<li>${describe(c)}</li>`).join("") || "<li>なし</li>";
  document.getElementById("violation-list").innerHTML =
    resultData.violations
      .map((v) => `<li class="log-ERROR">[${v.rule_id}] ${v.message}</li>`)
      .join("") || "<li>違反はありません</li>";
}

function attachDragHandlers() {
  document.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", JSON.stringify({
        code: card.dataset.code,
        grabbed: card.dataset.grabbed,
      }));
    });
  });

  document.querySelectorAll("#timetable-grid td").forEach((cell) => {
    cell.addEventListener("dragover", (event) => {
      event.preventDefault();
      cell.classList.add("dragover");
    });
    cell.addEventListener("dragleave", () => cell.classList.remove("dragover"));
    cell.addEventListener("drop", async (event) => {
      event.preventDefault();
      cell.classList.remove("dragover");
      const payload = JSON.parse(event.dataTransfer.getData("text/plain"));
      await moveCard(payload.code, payload.grabbed, cell.dataset.slot);
    });
  });
}

function shiftedSlots(placement, grabbedLabel, targetLabel) {
  const grabbed = parseSlot(grabbedLabel);
  const target = parseSlot(targetLabel);
  const dayIndex = DAYS.indexOf(target.day) - DAYS.indexOf(grabbed.day);
  const periodShift = target.period - grabbed.period;

  return placement.slots.map((label) => {
    const slot = parseSlot(label);
    const day = DAYS[DAYS.indexOf(slot.day) + dayIndex];
    const period = slot.period + periodShift;
    return day && period >= 1 && period <= 5 ? `${day}${period}` : null;
  });
}

async function moveCard(code, grabbedLabel, targetLabel) {
  const placement = resultData.placements.find((p) => p.code === code);
  if (!placement) return;

  const slots = shiftedSlots(placement, grabbedLabel, targetLabel);
  if (slots.some((slot) => slot === null)) {
    window.alert("移動先が時間割の範囲外です");
    return;
  }

  try {
    const body = await api.moveSubject(window.appState.sessionId, code, slots);
    if (!body.applied) {
      const reasons = body.violations
        .map((v) => `[${v.rule_id}] ${v.message}`).join("\n");
      window.alert(`この位置には配置できません:\n${reasons}`);
      return;
    }
    await renderTimetable();
  } catch (error) {
    window.alert(`移動に失敗しました: ${error.message}`);
  }
}

async function renderTimetable() {
  if (!window.appState.sessionId) return;
  try {
    resultData = await api.getResult(window.appState.sessionId);
  } catch (error) {
    document.getElementById("timetable-grid").innerHTML =
      `<p class="log-ERROR">結果の取得に失敗しました: ${error.message}</p>`;
    return;
  }
  if (resultData.status !== "done") {
    document.getElementById("timetable-grid").innerHTML = "<p>まだ生成が完了していません。</p>";
    return;
  }
  renderTabs();
  renderGrid();
  renderSide();
}

function initTimetable() {
  document.getElementById("export-button").addEventListener("click", () => {
    if (!window.appState.sessionId) return;
    window.location.href = api.exportUrl(window.appState.sessionId);
  });
}
```

- [ ] **Step 2: 全体を通して手動確認する**

Run: `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000`

ブラウザで、実データのカリキュラム一覧・教員一覧を読み込み、モックモードで生成してから次を確認する。

1. 「③ 結果」タブに学科タブ（経営 / 会計 / 短期大学部）と学期タブ（前期 / 後期）が出る
2. グリッドが縦 1〜5 限・横 月〜金で表示され、科目カードに科目名・教員名・年次・科目区分が出る
3. カードの色が配置元ごとに違う（事前ロックは青、ソルバーは黄など）
4. カードを別のコマにドラッグ&ドロップすると位置が変わり、色が「手動編集」の色になる
5. 教員の研究日にあたるコマへドロップすると、`[H6] … の研究日（…曜日）です` というアラートが出て移動しない
6. サイドに未配置科目・集中講義・制約違反の一覧が出る
7. 「Excel として出力」で `時間割.xlsx` がダウンロードされ、7 シート（6 つの時間割表＋集中講義）が入っている

- [ ] **Step 3: コンソールにエラーが出ていないことを確認する**

ブラウザの開発者ツールを開き、Console タブに赤いエラーが出ていないことを確認する。Task 24 の Step 7 で出ていた未定義関数のエラーも解消しているはずである。

- [ ] **Step 4: 全テストを実行する**

Run: `cd backend && ../.venv/bin/pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 5: コミットする**

```bash
git add frontend/js/timetable.js
git commit -m "feat: 結果画面とドラッグ&ドロップ編集を追加"
```

---

## 完了時の確認

すべてのタスクが終わったら、次を実行して仕様書の要件が満たされていることを確認する。

- [ ] `cd backend && ../.venv/bin/pytest tests/ -v` が全件 PASS する
- [ ] モックモードで実データを生成し、残存違反が 0 件である
- [ ] 生成ログが `backend/logs/` に日付別ファイルとして残っている
- [ ] 生成結果が `backend/data/sessions/<id>.json` に保存されている
- [ ] Excel 出力に 7 シート（経営・会計・短大 × 前期・後期＋集中講義）が含まれる
- [ ] API キーを設定して最適化モードを実行し、Gemini が実際に呼ばれてログにトークン数と応答時間が出る
- [ ] 前年度ファイルを投入して踏襲モードを実行し、組み替え対象一覧が表示される
