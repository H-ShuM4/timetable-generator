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


class ResultOut(BaseModel):
    status: str
    placements: list[PlacementOut]
    unplaced: list[SubjectRef]
    violations: list[ViolationOut]
    intensive: list[SubjectRef]
    error: str | None = None


class MoveIn(BaseModel):
    code: str
    slots: list[str] = Field(min_length=1)


class MoveOut(BaseModel):
    applied: bool
    violations: list[ViolationOut]
