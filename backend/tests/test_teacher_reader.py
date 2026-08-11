from pathlib import Path

from app.ingest.name_normalizer import normalize_name
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


def test_reads_real_workbook():
    teachers = read_teachers(TEACHER_XLSX)
    assert len(teachers) == 99  # 大学専任31 + 短大専任9 + 非常勤59


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
