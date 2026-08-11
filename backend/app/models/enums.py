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
