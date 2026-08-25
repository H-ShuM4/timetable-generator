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


class ResultOut(BaseModel):
    status: str
    placements: list[PlacementOut]
    unplaced: list[SubjectRef]
    violations: list[ViolationOut]
    intensive: list[SubjectRef]
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
