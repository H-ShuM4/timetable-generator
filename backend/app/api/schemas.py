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
