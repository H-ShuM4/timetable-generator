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
    """前年度の時間割を読んだか。"""
    has_previous_teachers: bool = False
    """前年度の教員一覧を読んだか。

    踏襲モードは 2 本そろって初めて働く。教員一覧が無いと研究日の比較が
    「前年度＝なし」対「今年度＝あり」となって全専任が組み替え対象へ落ち、
    1 件も踏襲されない。どちらが欠けているかを画面へ届けるために分けて持つ。
    """


class UploadResponse(BaseModel):
    session_id: str
    summary: UploadSummary
    warnings: list[WarningOut]


class SessionRef(BaseModel):
    session_id: str
    created_at: str
    files: dict[str, str]
    has_result: bool


class SettingsOut(BaseModel):
    model: str
    max_retries: int
    fallback_models: list[str]
    api_key_masked: str | None
    has_api_key: bool


class SettingsIn(BaseModel):
    model: str = Field(min_length=1)
    max_retries: int = Field(ge=1, le=10)
    fallback_models: list[str] = Field(default_factory=list, max_length=10)


class ApiKeyIn(BaseModel):
    api_key: str = Field(min_length=1)


class GenerateIn(BaseModel):
    mode: str = Field(pattern="^(mock|optimize|inherit)$")
    weights: dict[str, str] = Field(default_factory=dict)
    """生成画面のスライダー。項目名 → off / normal / high。"""

    repair_effort: str = Field(default="off", pattern="^(off|short|long)$")
    """配置の見直しにかける時間。"""

    retarget_with: str = Field(default="solver", pattern="^(solver|ai)$")
    """踏襲モードで、組み替え対象を誰が配置するか。

    **既定はソルバー。** 前年度をなぞるのが踏襲モードの目的で、組み替えは
    その残りにすぎない。API キーがあるだけで Gemini に渡ると、数十分と
    無料枠を黙って使うことになる。AI に任せたいときだけ ai を送る。
    AI モードの挙動はこの設定に左右されない。
    """

    retarget_codes: list[str] | None = None
    """踏襲モードで組み替える科目。

    **空リストと未指定を区別する。** 空リストは「すべて解除した＝何も
    組み替えない」で、未指定は「自動検出に任せる」。以前は両方を同じ
    falsy として扱っていたため、すべて解除すると自動検出へ戻り、外した
    はずの科目がまとめて組み替え対象へ復活していた。
    """


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


class SubjectRef(BaseModel):
    code: str
    name: str
    teacher: str
    department: str
    year: int
    term: str
    category: str
    slots_required: int = 1
    requires_consecutive: bool = False
    """未配置科目を画面から置くとき、必要なコマ数を組み立てるのに使う。"""


class TeacherOut(BaseModel):
    name: str
    kind: str
    research_day: str | None
    available_slots: list[str]
    """非常勤のみ。空なら曜日・時限の制限なし。"""


class InheritSkipOut(BaseModel):
    """踏襲モードで前年度の枠へ戻せなかった科目と、その理由。"""

    subject: SubjectRef
    rule_id: str
    message: str
    related: SubjectRef | None = None


class ResultOut(BaseModel):
    status: str
    """done / running / pending / failed / cancelled。"""
    placements: list[PlacementOut]
    unplaced: list[SubjectRef]
    violations: list[ViolationOut]
    intensive: list[SubjectRef]
    inherit_skipped: list[InheritSkipOut] = []
    """踏襲モードのときだけ入る。なぜ灰色にならなかったかを画面で追えるように。"""
    teachers: list[TeacherOut] = []
    """教員ビューで勤務条件と照らし合わせるために返す。"""
    error: str | None = None


class MoveIn(BaseModel):
    code: str
    slots: list[str] = Field(min_length=1)


class SlotState(BaseModel):
    code: str
    slots: list[str]
    """空のリストは未配置を表す。"""


class MoveOut(BaseModel):
    applied: bool
    violations: list[ViolationOut]
    previous: list[SlotState] = []
    """移動が触れた科目の、移動前の状態。取り消しのために返す。

    合同科目と前後期の対応科目は一緒に動くため、画面側は自分が
    掴んだ 1 件しか知らない。何を戻せばよいかはサーバが答える。
    """


class UnplaceIn(BaseModel):
    code: str
