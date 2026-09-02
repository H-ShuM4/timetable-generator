#!/usr/bin/env python3
"""踏襲モードで「なぜ前年度どおりにならなかったのか」を数える。

結果画面で灰色（前年度踏襲）にならず緑（ソルバー）になった科目について、
理由を分類して出す。事務局が Excel を更新するたびに走らせて、増減の理由を
確かめられるようにするための道具。

    python3 tools/explain_inherit.py <セッションID>
    python3 tools/explain_inherit.py            # 最新のセッションを使う

**backend/ の下に置いていない。** make-dist.sh は backend/app と
backend/config を丸ごと配布物へ入れるため、そこへ置くと事務局に開発用の
道具まで配ってしまう。

本番と同じ関数（load_session_data → link_subjects → prelock → apply_plan）を
同じ順序で辿るので、画面で起きることとずれない。ログは一時ディレクトリへ
逃がし、backend/logs を汚さない。
"""
import collections
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.constraints.context import Context  # noqa: E402
from app.constraints.validator import check_placement  # noqa: E402
from app.ingest.pair_linking import link_subjects  # noqa: E402
from app.ingest.session_builder import load_session_data  # noqa: E402
from app.logging.session_logger import SessionLogger  # noqa: E402
from app.models.timetable import AssignmentSource  # noqa: E402
from app.scheduler.inherit import detect_retarget_codes  # noqa: E402
from app.scheduler.pipeline import release_partial_groups  # noqa: E402
from app.scheduler.prelock import prelock  # noqa: E402
from app.scheduler.solver import solve  # noqa: E402

SESSIONS = BACKEND / "data" / "sessions"


def newest_session() -> str:
    directories = [p for p in SESSIONS.glob("*") if (p / "files").is_dir()]
    if not directories:
        sys.exit(f"セッションが見つかりません: {SESSIONS}")
    return max(directories, key=lambda p: p.stat().st_mtime).name


def label(slots) -> str:
    return "".join(f"{s.day}{s.period}" for s in slots) or "-"


def main() -> None:
    session_id = sys.argv[1] if len(sys.argv) > 1 else newest_session()
    files = SESSIONS / session_id / "files"
    if not (files / "previous_curriculum.xlsx").exists():
        sys.exit(f"{session_id} は前年度のファイルを持っていません（踏襲モードではない）")

    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger("explain", log_dir=Path(tmp))
        loaded = load_session_data(
            files / "curriculum.xlsx", files / "teachers.xlsx", logger,
            previous_curriculum=files / "previous_curriculum.xlsx",
            previous_teachers=(files / "previous_teachers.xlsx"
                               if (files / "previous_teachers.xlsx").exists() else None),
        )
        logger.close()

    subjects = loaded.subjects
    link_subjects(subjects)
    context = Context.from_lists(subjects, loaded.teachers)
    previous = loaded.previous_entries
    retarget = detect_retarget_codes(
        subjects, loaded.teachers, previous, loaded.previous_teachers
    )

    prefer = {code: entry.slots for code, entry in previous.items()}
    timetable, _ = prelock(context, subjects, prefer=prefer)

    # apply_plan と同じ順序・同じ判定を辿り、戻せなかった理由を控える
    blocked = {}
    for code, entry in previous.items():
        if code in retarget:
            continue
        subject = context.subjects.get(code)
        if subject is None or timetable.is_placed(code) or subject.is_intensive:
            continue
        violations = check_placement(context, timetable, subject, entry.slots)
        if violations:
            blocked[code] = violations[0]
            continue
        timetable.place(code, entry.slots, AssignmentSource.INHERITED)

    grid = [s for s in subjects if not s.is_intensive]
    pending = [s.code for s in grid if not timetable.is_placed(s.code)]
    released = set(release_partial_groups(context, timetable, pending))
    unplaced = solve(context, timetable, sorted(set(pending) | released))

    print(f"セッション {session_id}／グリッド対象 {len(grid)} 科目")
    sources = collections.Counter(a.source.value for a in timetable.assignments.values())
    print(f"  配置元: {dict(sources)}  未配置 {len(unplaced)}")

    part_time = [c for c, a in timetable.assignments.items()
                 if a.source is AssignmentSource.PRELOCK
                 and context.subjects[c].fixed_slot is None]
    moved = [c for c in part_time
             if c in previous and tuple(timetable.slot_of(c)) != previous[c].slots]
    print(f"  非常勤の自動ロック {len(part_time)} 件のうち前年度と別のコマ {len(moved)} 件")

    solver_codes = [c for c, a in timetable.assignments.items()
                    if a.source is AssignmentSource.SOLVER]
    reasons = collections.Counter()
    for code in solver_codes:
        if code in released:
            reasons["同じコマに入るべき仲間と揃わず外された"] += 1
        elif code in blocked:
            reasons["前年度の枠が今年度の制約に触れる"] += 1
        elif code in retarget:
            reasons["組み替え対象（設計どおり）"] += 1
        elif code not in previous:
            reasons["前年度の時間割に無い科目"] += 1
        else:
            reasons["その他"] += 1

    print(f"\nソルバーが置いた {len(solver_codes)} 件の理由")
    for name, count in reasons.most_common():
        print(f"  {count:>3} 件  {name}")

    print(f"\n前年度の枠を使えなかった {len(blocked)} 件の原因")
    causes = collections.Counter()
    samples = collections.defaultdict(list)
    for code, violation in blocked.items():
        other = context.subjects.get(violation.related_code) if violation.related_code else None
        if other is None:
            key = "今年度の規則・属性が前年度と食い違う"
        elif other.code not in previous:
            key = "相手が前年度に存在しない"
        elif tuple(timetable.slot_of(other.code)) != previous[other.code].slots:
            key = "相手が前年度と別のコマへ動いた"
        else:
            key = "前年度の時間割そのものが今年度のルールで衝突している"
        causes[key] += 1
        if len(samples[key]) < 3:
            samples[key].append(
                f"[{violation.rule_id}] {context.subjects[code].name}"
                f"（前年度 {label(previous[code].slots)}）"
                + (f" ← 相手 {other.name} {label(previous[other.code].slots)}"
                   f"→{label(timetable.slot_of(other.code))}"
                   if other and other.code in previous else "")
            )
    for name, count in causes.most_common():
        print(f"  {count:>3} 件  {name}")
        for line in samples[name]:
            print(f"        {line}")

    print("\n制約ID別")
    rules = collections.Counter(v.rule_id for v in blocked.values())
    print("  " + "  ".join(f"{k} {n}" for k, n in rules.most_common()))


if __name__ == "__main__":
    main()
