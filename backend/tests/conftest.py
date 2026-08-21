"""実データを読む重いフィクスチャ。セッション内で 1 度だけ読み込む。"""
from pathlib import Path

import pytest

from app.constraints.context import Context
from app.ingest.curriculum_reader import read_curriculum
from app.ingest.pair_linking import link_subjects
from app.ingest.teacher_reader import read_teachers

_ROOT = Path(__file__).resolve().parents[2]
CURRICULUM_XLSX = _ROOT / "カリキュラム一覧(整形済み).xlsx"
TEACHERS_XLSX = _ROOT / "教員一覧(整形済み).xlsx"


@pytest.fixture(scope="session")
def real_context() -> Context:
    """本番と同じ読み込み経路を通す。

    以前はここで前処理を並べ直しており、`assign_pair_ids` を足したとき
    呼び忘れて本番と違う条件でテストが走った。link_subjects を通せば
    その取りこぼしが起きない。
    """
    subjects = read_curriculum(CURRICULUM_XLSX)
    link_subjects(subjects)
    return Context.from_lists(subjects, read_teachers(TEACHERS_XLSX))


@pytest.fixture(scope="session")
def real_gemini_codes(real_context) -> list[str]:
    """Gemini に投げる対象。曜日時限が確定済みの科目と集中講義は除く。"""
    return [
        subject.code
        for subject in real_context.subjects.values()
        if not subject.fixed_slot and not subject.is_intensive
    ]


# ---------------------------------------------------------------- フロント

JS_DIR = Path(__file__).parent / "js"


@pytest.fixture(scope="session")
def run_js():
    """tests/js のドライバを node で走らせ、標準出力の JSON を返す。

    ブラウザ操作は自動検証の外にあり、実機でしか見つからない不具合が
    続いた。ブラウザ全体を用意せずとも、DOM のスタブ上で「何を書き出し
    たか」「どの要素が有効になったか」は確かめられる。
    """
    import json
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node が無い環境ではフロントの検証を飛ばす")

    cache: dict[str, dict] = {}

    def run(script: str) -> dict:
        if script not in cache:
            result = subprocess.run(
                ["node", str(JS_DIR / script)],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, result.stderr
            cache[script] = json.loads(result.stdout)
        return cache[script]

    return run
