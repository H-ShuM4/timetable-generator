# 大学時間割自動生成システム 実装計画

**Goal:** 経営学科・会計学科・短期大学部の時間割を、事務局が管理している Excel から自動で組み立て、ブラウザ上で確認・修正し、Excel として書き出せるシステムを作る。

**Architecture:** FastAPI が API とフロントエンドの静的ファイルの両方を配信する単一プロセス。配置は 7 段階のパイプラインで進み、どの段階の出力も**同一の制約検証器**を通る。生成 AI は「配置を提案する 1 つの段階」でしかなく、失敗しても決定的なソルバーが後を引き受けるため、時間割は必ず出力される。フロントエンドはフレームワークを使わない素の HTML/CSS/JS で、SSE によるログ受信とドラッグ&ドロップ編集を担う。

**Tech Stack:** Python 3.14 / FastAPI / uvicorn / openpyxl / MarkItDown / google-genai / pytest / Playwright / 素の HTML・CSS・JavaScript

---

## この計画の読み方

タスクは下から積み上げる順に並んでいる。前のタスクが終わっていれば次のタスクは単独で着手でき、各タスクの末尾にある**検証**を通せば完了と見なせる。

設計判断の根拠は `docs/superpowers/specs/2026-08-10-timetable-generator-design.md`（以下「仕様書」）にある。制約 ID・データモデル・入力 Excel の列構成は仕様書が正で、この計画はそれを実装順に並べ直したものである。

**これは「どう建てたか」の記録である。** 全 33 タスクは完了済みで、そのあと事務局の要望で変わったところがある。いま動いているものの姿を知りたいときは、末尾の「計画のあとに変わったこと」と仕様書を見てほしい。コードから入るなら `README.md` の「7. 開発者向け」に読む順がある。

## Global Constraints

- Python は 3.14 系。仮想環境はプロジェクト直下の `.venv` を使う
- 全コマンドはプロジェクトルートから実行する。Python は `.venv/bin/python`、pytest は `.venv/bin/pytest`
- 曜日は `月 火 水 木 金` の 5 種、時限は `1〜5` の 5 種。時限 `99` は「集中」を意味しグリッド対象外
- 開講期は `前期 後期 通年`、クオーターは `前① 前② 後① 後②`
- 学科は `経営 会計 短期大学部` の 3 種、科目区分は `必修 選択必修 選択` の 3 種、教員区分は `専任 特任 非常勤 不明` の 4 種。いずれも Excel に書かれている日本語をそのまま列挙の値に使う
- 制約 ID は `H1`〜`H10`・`H12`・`H13`。**`H11` は欠番**（1 日の合計コマ数の上限として検討したが、H7 の連続制限が同じ効果を持つため設けない。番号は再利用しない）
- テストに Gemini API キーは不要。Gemini は必ずモックに差し替える
- コード内の識別子は英語、利用者向けの文字列とログメッセージは日本語
- 1 ファイル 1 責務。300 行を超えたら分割を検討する（`excel_writer.py` は 800 行に育ったため、様式を `sheet_layout.py` へ切り出した）

## 設計上の要

個別のタスクより先に、全体を貫く 6 つの決め事を置く。どれも「同じ知識が 2 箇所にあると必ず食い違う」という一点に帰着する。

**1. 制約の判定は 1 箇所にしかない。** `constraints/validator.py` が唯一の入口で、事前ロック・ソルバー・AI 配置・手動編集のすべてがここを通る。確定枠の書き込みを除き、検証を経ずに `Timetable.place` を呼ぶ経路を作らない。

**2. Excel からセッションを組み立てる手順は 1 本しかない。** `ingest/session_builder.load_session_data` が唯一の入口で、アップロードも復元もここを通る。科目同士の結び付け（合同・前後期）も `ingest/pair_linking.link_subjects` に 1 つだけ置き、パイプラインもテストのフィクスチャもここを通る。前処理が増えるたびに全呼び出し箇所を思い出さなければならない構造にしない。

**3. 結び付いた科目はまとまりで動かす。** 合同科目（H4）と前後期の対応科目（H12）は同一コマを要求されるため、片方だけ動かすことがそもそも許されない。`constraints/linking.py` が結び付きを**推移的に**たどってまとまりを返し、ソルバーも手動移動もそれを単位として扱う。移動先がまとまりのどれか 1 つでも制約に触れるなら、まとまり全体を元へ戻す（部分適用しない）。

**4. 配置の「好み」も 1 箇所にしかない。** `scheduler/preference.py` をソルバーと Gemini プロンプトの両方が使う。片方だけが好みを知っていると、モードによって時間割の性格が変わる。

**5. 生成は途中で止まらない。** Gemini のどのエラー経路も最終的にソルバーへ落ち、時間割は必ず出力される。置けなかった科目は「未配置」として画面に出し、事務局が手で置ける。

**6. 保存先のルートは差し替えられる。** セッション・ログ・設定・API キーの置き場所は `app/paths.py` が一括で決め、環境変数 `TIMETABLE_DATA_DIR` で移せる。別プロセスで起動したサーバを相手にするテストが、実運用のデータを踏まないために要る。

## File Structure

| ファイル | 責務 |
|---|---|
| `backend/app/paths.py` | セッション・ログ・設定を書き込むルート |
| `backend/app/models/enums.py` | Department / Term / Quarter / Category / TeacherKind |
| `backend/app/models/timeslot.py` | TimeSlot（曜日 × 時限）と全スロット生成 |
| `backend/app/models/subject.py` | Subject データクラス |
| `backend/app/models/teacher.py` | Teacher データクラス |
| `backend/app/models/timetable.py` | Assignment / Timetable / AssignmentSource |
| `backend/app/constraints/period_overlap.py` | 開講期間の重なり判定 |
| `backend/app/constraints/context.py` | 制約評価に必要な索引（Context / Violation） |
| `backend/app/constraints/linking.py` | 同一コマを要求される科目のまとまり |
| `backend/app/constraints/teacher_rules.py` | H1・H5・H6・H7 |
| `backend/app/constraints/student_rules.py` | H2・H3 |
| `backend/app/constraints/subject_rules.py` | H4・H8・H9・H10・H12・H13 |
| `backend/app/constraints/validator.py` | 制約検証の唯一の入口 |
| `backend/app/ingest/name_normalizer.py` | 氏名の空白除去・異体字正規化 |
| `backend/app/ingest/teacher_reader.py` | 教員一覧 Excel の読み取り |
| `backend/app/ingest/curriculum_reader.py` | カリキュラム一覧 Excel の読み取り |
| `backend/app/ingest/joint_pairing.py` | 合同科目（経営 × 会計）の対応付け |
| `backend/app/ingest/pair_linking.py` | 前期・後期にまたがる科目の対応付け |
| `backend/app/ingest/department_rules.py` | 学科・年次ごとの編成規則 |
| `backend/app/ingest/validators.py` | Stage 0 の警告生成 |
| `backend/app/ingest/session_builder.py` | Excel 4 本からセッションの中身を組み立てる |
| `backend/app/ingest/markitdown_fallback.py` | 想定外 Excel のフォールバック読み取り |
| `backend/app/scheduler/candidates.py` | 科目 1 件が取り得るコマ集合の列挙 |
| `backend/app/scheduler/preference.py` | 配置の好み（ソルバーと Gemini が共有） |
| `backend/app/scheduler/objectives.py` | 時間割の「良さ」の計測 |
| `backend/app/scheduler/prelock.py` | Stage 1（確定枠・非常勤の事前ロック） |
| `backend/app/scheduler/gemini_stage.py` | Stage 2〜4（Gemini によるチャンク配置） |
| `backend/app/scheduler/solver.py` | Stage 5（最小残余値ヒューリスティックの貪欲配置） |
| `backend/app/scheduler/repair.py` | Stage 5.5（良くなる移動の探索と適用） |
| `backend/app/scheduler/inherit.py` | 踏襲モード |
| `backend/app/scheduler/pipeline.py` | Stage 0〜6 のオーケストレーション |
| `backend/app/gemini/prompts.py` | プロンプト生成と応答解析 |
| `backend/app/gemini/client.py` | Gemini クライアントとモデル切り替え |
| `backend/app/logging/session_logger.py` | SSE とファイルへのログ出力 |
| `backend/app/export/sheet_layout.py` | Excel の様式（列の並び・幅・書体・罫線・網掛け） |
| `backend/app/export/excel_writer.py` | Excel への書き出し手順 |
| `backend/app/settings_store.py` | `.env` と `settings.json` の読み書き |
| `backend/app/session_store.py` | セッション単位の読み込みデータと生成結果 |
| `backend/app/api/schemas.py` | API のリクエスト・レスポンス型 |
| `backend/app/api/upload.py` | Excel アップロードと読み込みサマリ |
| `backend/app/api/settings.py` | API キー・モデル・再試行回数 |
| `backend/app/api/generate.py` | 生成実行と SSE ログ配信 |
| `backend/app/api/result.py` | 結果の取得と手動編集 |
| `backend/app/api/export.py` | Excel 出力 |
| `backend/app/main.py` | FastAPI エントリポイントと静的ファイル配信 |
| `backend/config/name_variants.json` | 異体字マッピング |
| `backend/config/subject_overrides.json` | 科目個別の例外 |
| `backend/config/paired_subjects.json` | 前後期の対応科目・隣接指定 |
| `backend/config/department_rules.json` | 学科・年次ごとの編成規則 |
| `frontend/index.html` | 4 画面のマークアップ |
| `frontend/css/style.css` | スタイル |
| `frontend/js/api.js` | バックエンド呼び出し |
| `frontend/js/main.js` | 画面切り替えと初期化 |
| `frontend/js/upload.js` | 読込画面とセッション復元 |
| `frontend/js/settings.js` | 設定画面 |
| `frontend/js/logviewer.js` | ログビューア（SSE 受信） |
| `frontend/js/generate.js` | 生成画面 |
| `frontend/js/timetable.js` | 結果画面のグリッドと D&D |
| `setup.bat` / `start.bat` | 事務局 PC（Windows）向けの準備と起動 |
| `start.sh` | 開発機（Linux/WSL）向けの起動 |
| `make-dist.sh` | 配布用 zip の作成 |
| `README.md` | 取扱説明書（事務局向け ＋ 開発者向け） |
| `tools/` | 開発用スクリプト。配布 zip には入らない |

---

# 第 1 部　土台：データモデルと制約

制約検証器が完成するまで、配置を書き始めない。置く仕組みより「置いてよいか」を判定する仕組みのほうが土台になる。

### Task 1: プロジェクト雛形と依存関係

**Files:** `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pytest.ini`, `backend/app/__init__.py` ほかパッケージの `__init__.py`

- 実行に要るもの（fastapi / uvicorn / python-multipart / openpyxl / markitdown[xlsx] / google-genai / pytest / httpx）を `requirements.txt` に置く
- 開発時にしか要らないもの（playwright / pytest-playwright）は `requirements-dev.txt` に分ける。`requirements.txt` は事務局 PC でそのまま展開されるため、ブラウザ一式をそこへ混ぜない
- `pytest.ini` は `testpaths = tests`、`pythonpath = .`

**検証:** `.venv/bin/pytest` が 0 件で正常終了する。

### Task 2: 列挙・コマ座標・開講期間の重なり判定

**Files:** `app/models/enums.py`, `app/models/timeslot.py`, `app/constraints/period_overlap.py`

- 列挙の値は Excel 上の日本語表記そのもの。変換表を挟むと Excel が変わったとき追随箇所が増える
- `TimeSlot` は曜日と時限の組。全 25 コマを生成する関数を持つ
- **すべての制約は「開講期間が実際に重なる場合のみ衝突」と判定する。** 判定の土台は `active_quarters(term, quarter)`＝その科目が実際に走っているクオーターの集合で、2 つの期間が重なるかはこの集合が交わるかで決まる。集合そのものを必要とする制約（H7）があるため、真偽値だけでなく集合も公開する
- 前期と後期は常に重ならない。通年はどの期間とも重なる

**決め事:** 重なり判定を各制約に書き写さない。1 箇所に置いて全制約が共有する。仕様書 §5.4 の表が期待値の正。

**検証:** `tests/test_models.py`, `tests/test_period_overlap.py`（仕様書 §5.4 の全組み合わせを網羅）

### Task 3: Subject / Teacher / Timetable

**Files:** `app/models/subject.py`, `app/models/teacher.py`, `app/models/timetable.py`

- `Subject` は仕様書 §5.1、`Teacher` は §5.2 に対応する
- `Subject.base_name` は `:会`・`【再】`・先頭の `▲` を除いた正規化名。合同ペアリングと対応科目の突合に使う
- `Timetable` は配置結果を保持する唯一の状態で、制約検証・ソルバー・API がこれを共有する。`Assignment` は `source`（prelock / gemini / solver / manual / inherited）を持ち、画面での色分けに使う
- 学科 × 学期でビューを切り出せるようにする

**検証:** `tests/test_timetable.py`

### Task 4: 氏名の正規化

**Files:** `app/ingest/name_normalizer.py`, `config/name_variants.json`

- 全角・半角の空白を除去し、異体字（`籏`→`旗`、`髙`→`高` など）をマッピングで吸収する
- マッピングを JSON に置くのは、新しい揺れが出たときにコードを触らず足せるようにするため

**検証:** `tests/test_name_normalizer.py`

### Task 5: 教員一覧 Excel の読み取り

**Files:** `app/ingest/teacher_reader.py`

- シートは `大学専任` / `短大専任 `（末尾に空白あり）/ `非常勤`
- 区分の判定：`研究日` に値があれば**専任**、`出勤可能日(特任)` に値があれば**特任**、`非常勤` シートにあれば**非常勤**
- 非常勤の出勤可能日は `月2,月3,月4` 形式で、コマ単位に展開する
- 名簿に無い教員は**不明**とし、警告を出した上で配置する。生成は止めない

**決め事:** 「不明」に効かないのは H5（出勤可能日）と H6（研究日）だけ。H1（二重予約）と H7（連続コマ）は名簿の有無に関係なく適用する。名簿に載っていない教員も同時刻に二箇所へは行けない。

**検証:** `tests/test_teacher_reader.py`

### Task 6: カリキュラム一覧 Excel の読み取り

**Files:** `app/ingest/curriculum_reader.py`, `config/subject_overrides.json`

- シートは `大学(会計・経営)` と `短期大学部`。**列の見出しが異なる**（大学の `コース` と短大の `フィールド`）ため、リーダーは両方の見出しを受け入れる
- `遠隔` 列は **3 状態**。`○` = 必ず金曜、`×` = 金曜以外、空欄 = どこでも可。`×` は `○` の否定ではない
- 短大の `備考` はクオーター指定（前①・前②・後①・後②）
- **`▲` 科目は同一授業コードで 2 行**現れる。1 科目に集約し「必要コマ数 2・連続要件あり」として扱う。連続を要さない例外は `subject_overrides.json` に置く
- 曜日・時限が入力済みの行は**確定枠**。時限 `99`（集中）は集中講義としてグリッド対象外にする

**検証:** `tests/test_curriculum_reader.py`

### Task 7: 合同科目のペアリング

**Files:** `app/ingest/joint_pairing.py`

- 経営学科と会計学科で合同開講される科目を突合し、同じ `joint_id` を与える
- 突合のキーは正規化名・教員・開講期
- 合同フラグが `○` でも相手がいない科目は正常として扱い、警告を出さない。フラグは「科目が合同開講であること」を示し、ペアは教員単位で成立する
- 片方にだけフラグが付いている組は付け忘れの可能性が高いので `joint_flag_mismatch` として警告する

**検証:** `tests/test_joint_pairing.py`

### Task 8: 前期・後期の対応付けと「まとまり」

**Files:** `app/ingest/pair_linking.py`, `app/constraints/linking.py`, `config/paired_subjects.json`

- 同じ教員が前期と後期に続けて持つ対応科目（`日本語リテラシーⅠ`/`Ⅱ` など）に同じ `pair_id` を与える。対象は `paired_subjects.json` の `same_slot_across_terms`
- `linking.py` は `joint_id` と `pair_id` を**推移的に**たどって「同一コマに置かれなければならない科目のまとまり」を返す。両方を持つ科目があるため、1 つのまとまりが 4 科目になることがある
- `link_subjects` を科目の前処理の唯一の入口にする。パイプラインもテストのフィクスチャもここを通す

**検証:** `tests/test_pair_linking.py`, `tests/test_solver_linking.py`

### Task 9: 学科ごとの編成規則

**Files:** `app/ingest/department_rules.py`, `config/department_rules.json`

- Excel に現れない、事務局が定めた編成規則を持つ。現状は会計学科 1 年の 2 つ
  - **朝学習**：月・火・木・金の 1 限には授業を置かない（H13）
  - **水曜の編成**：1〜4 限に入る科目が決まっている
- 規則を JSON に置くのは、学年や学科が増えたときにコードを触らず足せるようにするため
- **ファイルが無い・壊れている場合は規則なしとして扱う。** 時間割が作れなくなるより、規則が効かないほうが害が小さい

**検証:** `tests/test_department_rules.py`

### Task 10: Stage 0 の警告と読み込み経路の一本化

**Files:** `app/ingest/validators.py`, `app/ingest/session_builder.py`

- `validators.py` は読み込み時点で分かるデータの問題を警告にする（担当科目があるのに出勤可能日が空欄、名簿に無い教員、合同フラグの不一致 など）。**警告は生成を止めない**
- `session_builder.load_session_data` が Excel 4 本（今年度カリキュラム・今年度教員・前年度カリキュラム・前年度教員）を受け取り、読み取り・正規化・結び付け・警告生成をこの順で行って、セッションの中身を組み立てる

**決め事:** 組み立て手順をここに 1 つだけ置く。アップロードも復元もこの関数を通る（設計上の要 2）。

**検証:** `tests/test_ingest_validators.py`

### Task 11: 制約の共通基盤と教員に関する制約（H1・H5・H6・H7）

**Files:** `app/constraints/context.py`, `app/constraints/teacher_rules.py`

- `Context` は制約評価に要る索引（科目・教員・学科別年次別の索引など）をまとめる。ルール関数は必ずこれを受け取る。`Violation` は `rule_id` と人が読めるメッセージを持つ
- **H1**：同一教員が同曜日・同時限に別科目を持たない。全学科横断。同じ `joint_id` の科目同士は除外する（1 つの授業なので）
- **H5**：非常勤は出勤可能コマのみ、特任は出勤可能曜日のみ
- **H6**：専任の研究日には配置しない
- **H7**：同一教員が同一日に 4 コマ以上連続しない。判定は教員 × 曜日 × **クオーター区間**で行う。1 日の合計コマ数はこの規則が自動的に 4 コマへ抑えるため、別途の上限は設けない

**決め事:** H7 は同一教員の既存配置を毎回集め直すと重いので、直前の計算結果を 1 件だけ覚えておく。

**検証:** `tests/test_teacher_rules.py`

### Task 12: 学生の履修衝突に関する制約（H2・H3）

**Files:** `app/constraints/student_rules.py`

- **H2**：必修同士が衝突しない。判定単位は学科 × 年次。**同一科目名の複数クラスは対象外**（学生はどれか 1 つを取る）
- **H3**：選択必修同士が衝突しない。判定単位は学科 × 年次 × コース。異なるコース間は衝突してよい

**検証:** `tests/test_student_rules.py`

### Task 13: 科目固有の制約（H4・H8・H9・H10・H12・H13）と検証器の統合

**Files:** `app/constraints/subject_rules.py`, `app/constraints/validator.py`

- **H4**：合同科目のペアは同曜日・同時限
- **H8**：遠隔 `○` は金曜のみ、`×` は金曜以外、空欄はどちらでもよい
- **H9**：Excel で入力済みの確定枠は動かせない
- **H10**：必要コマ数と連続要件を満たすこと
- **H12**：前期・後期にまたがる対応科目は同曜日・同時限
- **H13**：朝学習の時間には授業を置かない。ただし担当教員の出勤可能コマがすべて朝学習に重なる場合は、置けなくなるより出勤可能日を優先する
- `validator.py` が全ルールを 1 本のリストに束ね、`check_placement`（1 件の配置が可能か）と全体検証の 2 つを公開する

**決め事:** これが**唯一の入口**。確定枠の書き込みを除き、検証を経ずに `Timetable.place` を呼ぶ経路を作らない（設計上の要 1）。

**検証:** `tests/test_subject_rules.py`, `tests/test_validator.py`

---

# 第 2 部　配置：スケジューラ

ここまでで「置いてよいか」が判定できる。次は実際に置く。AI を使わないモックモードを先に完成させ、AI は後から**差し込む**。順序が逆だと、AI が無いと何も動かないシステムになる。

### Task 14: 候補コマの列挙と配置の好み

**Files:** `app/scheduler/candidates.py`, `app/scheduler/preference.py`

- `candidates.py` は科目 1 件が取り得るコマ集合を列挙する。必要コマ数と連続要件を反映し、確定枠を持つ科目はその枠のみを返す
- `preference.py` は制約ではない「好み」を持つ。1〜4 限への集約（教職課程が使う 4・5 限との衝突を避ける）、ゼミの隣接など

**決め事:** 好みはソルバーと Gemini プロンプトの両方がここから読む。片方だけが知っている状態にすると、モードによって時間割の性格が変わる（設計上の要 4）。

**検証:** `tests/test_candidates.py`, `tests/test_preference.py`

### Task 15: Stage 1（事前ロック）

**Files:** `app/scheduler/prelock.py`

- Python だけで決定的に決まる科目を先に確定させる
  - Excel で曜日・時限が入力済みの確定枠
  - 出勤可能コマが必要コマ数と等しく、選択の余地がない非常勤の科目
- 置けなかった非常勤科目は警告に回す。**多くは実在の制約衝突であって不具合ではない**ので、生成は続ける

**検証:** `tests/test_prelock.py`

### Task 16: Stage 5（ソルバー）

**Files:** `app/scheduler/solver.py`

- 最小残余値ヒューリスティック（候補コマが少ない科目から確定させる）による決定的な貪欲配置
- 配置は `linked_group` 単位で行う。まとまりのどれか 1 つでも置けなければ、まとまりごと未配置にする（設計上の要 3）
- 候補コマの順序付けに `preference.py` を使う
- **解が無い科目は未配置として返す。** 例外を投げて生成ごと落とさない

**検証:** `tests/test_solver.py`, `tests/test_solver_incremental.py`

### Task 17: 良さの尺度と Stage 5.5（見直し）

**Files:** `app/scheduler/objectives.py`, `app/scheduler/repair.py`

- `objectives.py` は時間割の「良さ」を数える。項目は学生の空きコマ・学生の登校日数・教員の空きコマ・1〜4 限への集約・ゼミの隣接の 5 つ。**事務局が生成画面のスライダーで重みを決める**
- **項目同士は競合する。** 登校日数を詰めれば 1 日が長くなって空きコマが増えやすく、逆もまた然り。どちらを取るかは事務局が実物を見比べて決めることなので、システム側は重み付き合計で順位を付けるだけにする
- `repair.py` は置いたあとに、良くなる移動を探して適用する。**制約を満たす移動しか行わない**ので、配置済みの科目が未配置に戻ることはない
- まとまり（合同・前後期）は 1 単位として動かす
- 探索にかける時間は上限で制御する（`repair_effort`：しない / 短く / じっくり）

**決め事:** 順位付けは**影響範囲だけを数える**。候補コマごとに時間割全体を計測すると現実的な時間で終わらない。1 つの科目群を動かして値が変わるのは、その科目の学科×年次×学期、担当教員、隣接相手だけで、他は比較の際に相殺される。

**決め事:** 重みがすべて 0 なら何も動かさない。

**検証:** `tests/test_repair.py`

### Task 18: セッションロガー

**Files:** `app/logging/session_logger.py`

- 生成セッション単位のログ。フロントへの SSE 配信とファイル保存を兼ねる
- レベルは INFO / WARN / ERROR。各イベントは Stage 名を持つ
- ワーカースレッドから呼ばれるためロックで守る。購読キューを通して SSE へ流す
- **残すのは直近 20 ファイル。** 古いものから消す。放置すると際限なく増える

**検証:** `tests/test_session_logger.py`

### Task 19: パイプラインとモックモード

**Files:** `app/scheduler/pipeline.py`

段階は次の通り。

| Stage | 内容 |
|---|---|
| 0 | 読み込みと警告、集中講義のグリッド除外 |
| 1 | 事前ロック |
| 2 | Gemini：必修 |
| 3 | Gemini：選択必修 |
| 4 | Gemini：選択 |
| 5 | ソルバーによる補完 |
| 5.5 | 見直し（repair） |
| 6 | 最終検証 |

- モードは `mock`（Gemini を使わない）/ `optimize`（AI モード）/ `inherit`（踏襲）の 3 つ。Gemini の配置役は**差し込み可能**にし、モックモードでは Stage 2〜4 を飛ばす
- **AI が中途半端に置いたまとまりは解放する。** Gemini がまとまりの一部だけを置いた場合、残りを置く場所が無く詰むので、まとまりごと外してソルバーに委ねる

**検証:** `tests/test_pipeline.py`, `tests/test_partial_groups.py`

### Task 20: 踏襲モード

**Files:** `app/scheduler/inherit.py`

- 前年度の時間割をそのまま引き継ぎ、**組み替えが要る科目だけ**を再配置する
- 組み替え対象の検出理由：前年度に存在しない新規科目 / 担当教員の変更 / 研究日の変更 / 担当が非専任（非常勤・特任）
- 前年度の教員一覧も入力に取り、研究日の差分を見る
- 検出結果は画面に一覧で出し、事務局がチェックボックスで増減できる

**検証:** `tests/test_inherit.py`

---

# 第 3 部　外との接点：Gemini・永続化・API

### Task 21: 保存先のルートと設定の永続化

**Files:** `app/paths.py`, `app/settings_store.py`

- `paths.py` は保存先のルートを 1 箇所で決める。既定は `backend/`、環境変数 `TIMETABLE_DATA_DIR` で差し替えられる
- API キーは `backend/.env` の `GEMINI_API_KEY`、モデル名・予備モデル・再試行回数は `backend/data/settings.json`
- **API キーの全文はフロントへ返さない。** 先頭数文字だけを残してマスクし、短いキーでも末尾が必ず隠れるようにする
- `settings.json` が壊れている場合は既定値へ落とす。設定が読めないだけでシステムが起動しなくなるのは割に合わない

**検証:** `tests/test_paths.py`, `tests/test_settings_store.py`

### Task 22: Gemini のプロンプトと応答解析

**Files:** `app/gemini/prompts.py`

- 科目をチャンクへ分けて投げる。チャンクのキーは**学科 × 開講期 × 年次**。年次を入れないと 1 チャンクが大きくなりすぎて応答品質が落ちる
- プロンプトには制約と `preference.py` の好みを日本語で書き、応答は JSON スキーマで受け取る
- 応答解析は自分が要求したコードだけを引く。想定外のコードが混ざっても無視する

**検証:** `tests/test_prompts.py`

### Task 23: Gemini クライアントとモデルの切り替え

**Files:** `app/gemini/client.py`

- 失敗はすべて `GeminiError` に包む。呼び出し側は SDK の例外型に依存しない
- **枠切れ（`QuotaExceededError`）と混雑（`ModelBusyError`）を区別する。** 判定は SDK の例外型ではなく応答中の語（`RESOURCE_EXHAUSTED` / `quota` / `rate limit`、`UNAVAILABLE` / `high demand` / `overloaded`）で行う
- 1 回の呼び出しに 90 秒の上限を置く。混雑したモデルを待ち続けない
- `RotatingGeminiClient` は枠切れ・混雑を検出するたびに**次の予備モデルへ移って同じリクエストを再送**する。使い切ったモデルは以後使わない。全モデルが尽きたら `GeminiError` となり、既存の経路でソルバーへ落ちる
- それ以外の失敗ではモデルを切り替えない。一時的な失敗であり、通常の再試行で解決しうる
- どのチャンクをどのモデルが処理したかはログに残す。**応答を受け取った後に読む**（送信前の名前は切り替えが起きると食い違う）

**決め事:** ラウンドロビンではなくフェイルオーバーにする。確認したいのは「AI が全科目を割り振った時間割」であってモデルの比較ではない。チャンクごとに品質の違うモデルが混ざると、何の結果なのか読み解けなくなる。予備モデルの既定は空で、そのときは 1 モデルだけを使う。

**検証:** `tests/test_gemini_rotation.py`

### Task 24: Stage 2〜4（Gemini によるチャンク配置）

**Files:** `app/scheduler/gemini_stage.py`

- チャンクごとに配置を提案させ、**1 件ずつ検証器に通す**。違反した科目だけを理由付きで差し戻して再試行する
- 再試行の上限に達した科目はソルバーへ回す
- 例外はチャンク単位で捕まえる。1 チャンクの失敗で生成全体を落とさない

**検証:** `tests/test_gemini_stage.py`

### Task 25: Excel 出力と MarkItDown フォールバック

**Files:** `app/export/excel_writer.py`, `app/ingest/markitdown_fallback.py`

- 学科 × 学期の 6 シートを書き出す（当初はマトリクス形式だったが、のちに事務局の様式へ作り替えた。仕様書 §9.1 を見ること）
- 1 セルに複数科目が入る場合は改行で併記し、科目名・教員名・年次・科目区分を書く。クオーター科目は `前①` などを添える
- `markitdown_fallback.py` は想定外の列構成の Excel が投入されたときの経路。警告を出したうえで読めるだけ読む

**検証:** `tests/test_excel_writer.py`, `tests/test_markitdown_fallback.py`

### Task 26: セッションストア

**Files:** `app/session_store.py`

- 読み込んだデータと生成結果をセッション単位で保持する。**メモリ上の辞書だけでは足りない。** AI モードは数十分かかり無料枠も消費するため、サーバの再起動やブラウザの再読み込みで結果が消えると、事務局はアップロードからやり直すことになる
- アップロードされた Excel を `data/sessions/<id>/files/` に保存し、結果は同じディレクトリの `result.json` に書く
- **復元は保存した Excel を同じ読み込み処理に通し直してから結果を重ねる。** 科目や教員を別形式でもう一度持つより、読み込み経路が 1 本のままで済む
- 制約違反は保存値を使わず再計算する。保存後に制約を変えた場合、古い判定を見せるほうが害が大きい
- Excel が差し替わって消えた科目コードは黙って捨てる
- 保持は最新 `MAX_SESSIONS` 件で、古い順に削除する。ただし**生成中のセッションは削除しない**

**検証:** `tests/test_session_persistence.py`

### Task 27: API 層

**Files:** `app/api/schemas.py`, `upload.py`, `settings.py`, `generate.py`, `result.py`, `export.py`, `app/main.py`

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/upload` | Excel 1〜4 本を受け取り、読み込みサマリと警告を返す |
| GET | `/api/sessions` | セッション一覧 |
| GET | `/api/sessions/{id}` | セッションの復元 |
| GET/PUT | `/api/settings` | モデル・再試行回数・予備モデル |
| PUT/DELETE | `/api/settings/api-key` | API キーの保存・削除 |
| GET | `/api/retarget/{id}` | 踏襲モードの組み替え対象一覧 |
| POST | `/api/generate/{id}` | 生成開始（202） |
| GET | `/api/generate/{id}/stream` | SSE によるログ配信 |
| GET | `/api/result/{id}` | 生成結果 |
| POST | `/api/result/{id}/move` | コマの移動 |
| POST | `/api/result/{id}/unplace` | 配置を外す |
| GET | `/api/export/{id}` | Excel 出力 |

- 生成は別スレッドで動かし、ログは購読キューを通して SSE で流す。無通信が続く場合は定期的にコメントを送って、間に挟まる機器に切られないようにする
- 読み取り失敗は**どのファイルが原因か分かる 400** に変換する。最大 4 本を一度に投入するため、それが分からないと直しようがない。スタックトレースは返さない
- **移動はまとまり単位で適用する。** どれか 1 つでも制約に触れるならまとまり全体を元のコマ・元の `source` へ戻す（部分適用しない）。応答は「触れた科目とその移動前のコマ」を返し、画面はそれを積んで取り消しに使う
- `move` はまだ置かれていない科目コードも受け付ける（未配置科目を画面から置けるようにするため）
- 生成が失敗した場合は `status = failed` として返す。**成功として見せない**
- `main.py` は API を束ね、`frontend/` を静的配信する。静的ファイルには **`Cache-Control: no-cache`** を付ける。付けないとブラウザが Last-Modified から鮮度を推測して再検証せず、HTML だけ新しく JS・CSS が古いまま残る（「新機能を足したのに画面に出ない」という形で現れる）。`no-cache` は「保存してよいが使う前に必ず確認せよ」の意味で、変更が無ければ 304 が返るだけなので転送量は増えない

**検証:** `tests/test_api_upload.py`, `test_api_settings.py`, `test_api_generate.py`, `test_api_result.py`, `test_smoke.py`

---

# 第 4 部　画面

事務局が毎日触る業務画面である。情報密度・操作性・視認性を落とさずに作る。

### Task 28: 骨組み・読込画面・設定画面

**Files:** `frontend/index.html`, `css/style.css`, `js/api.js`, `js/main.js`, `js/upload.js`, `js/settings.js`

- タブは「① ファイル読込 → ② 生成 → ③ 結果」と「設定」。**番号は実際に順序のある場所にだけ置く。** 読込→生成→結果は順序だが設定は順序ではないので、設定は右端の独立したユーティリティとして分ける
- 読込画面は Excel をドラッグ&ドロップで受け取り、ファイル名から役割を推測して割り当てる。利用者は必要なら手で直せる。カリキュラムと教員が揃って初めて読み込める
- 読み込み後に科目数・教員数・集中講義数・クオーター科目数と、学科別・科目区分別・教員区分別の内訳、警告一覧を出す
- **セッション ID を `localStorage` に置き、起動時に復元を試みる。** 失敗すれば保存期間を過ぎたものとみなして忘れる。続けて結果の有無を見て、あれば結果タブも開けるようにする（結果タブが生成完了時にしか有効にならないと、復元してもサーバ上の結果へ辿り着けない）
- 設定画面は API キー・モデル・再試行回数と、折りたたんだ「開発者向け：予備モデル」

**画面デザインの決め事:**

- **色は意味に結び付ける。** 地は薄い紙色、構造と操作は**藍**、**制約違反だけを朱**にする。朱を違反以外に一切使わないので、画面のどこに朱があっても意味が一つに定まる。手で触ったもの（手動編集・警告）は山吹
- **年次は色相ではなく藍の濃淡 4 段で表す。** 年次は順序のあるデータなので濃淡のほうが意味に合う。色相を 4 つ足すと画面が騒がしくなる
- **Web フォントを読まない。** 配布先がオフラインやプロキシ配下だと、読み込み待ちで表示が遅れるか別の書体に化ける。Windows 10/11 に同梱される **BIZ UDPGothic / BIZ UDGothic** を先頭に置き、無ければ游ゴシック・メイリオへ落とす。授業コードや時限の数字は等幅にして桁を揃える
- 文字色は主要な組み合わせで WCAG AA（4.5:1）を満たすこと
- **利用者が入力した文字列や Excel 由来の文字列は、属性値の中も含めて必ずエスケープする**

### Task 29: 生成画面とログビューア

**Files:** `frontend/js/generate.js`, `frontend/js/logviewer.js`

- モード選択（モック / AI / 踏襲）。踏襲を選んだときだけ組み替え対象の一覧を出し、チェックボックスで増減できる
- 重み付けのスライダー 5 本（気にしない / 標準 / 重視）と、見直しにかける時間（しない / 短く / じっくり）。選択は `localStorage` に残す
- ログビューアは画面下部の折りたたみパネル。SSE で受信し、レベルで絞り込める
- 生成が終わったらログを畳んで結果タブへ自動で移る。失敗・切断のときは移らず、理由を出す
- API キーが未設定で AI モードを選んだ場合、サーバが実際に走らせたモードを**日本語のラベル**で伝える

### Task 30: 結果画面

**Files:** `frontend/js/timetable.js`

- 学科タブ × 学期タブでグリッド表示（縦 1〜5 限 × 横 月〜金）。曜日ヘッダーと時限の列は固定する
- **各コマの中は 1 年→2 年→3 年→4 年の順**に並べる。同じ年次の中は科目名、さらに授業コード順。移動のたびにサーバから取り直して並べ直すので順序は保たれる
- **学科別と教員別を切り替えられる。** H1・H5・H6・H7 は教員単位で判定するのに、その姿を人が見る手段が無いと違反の理由が追えない。教員別ではその教員のコマを学科をまたいで集め、担当コマ数・曜日ごとの偏り・区分・研究日・出勤可能コマ数を並べる。カードは担当が固定されているので教員名の代わりに学科を出す
- **期間レール**：カード左端の 3px の縦線が 2 つの事実を同時に表す。**色** = 配置元（墨＝事前ロック、深緑＝AI、淡緑＝ソルバー、山吹＝手動、灰＝前年度踏襲）、**高さ** = 開講期間（全高＝学期全体、上半分＝前①/後①、下半分＝前②/後②）。配置元を背景色で示すと、1 コマに 9 科目入るセルで密度が上がるほど読みにくくなる。レールなら地が白のまま残る。緑系統にしたのは年次チップが藍系だからで、レールも藍だと境目が読み取りにくい。違反時はレールの色を朱に差し替える。**形でしか伝わらないので、同じ内容を `title` に言葉でも持たせる**
- ドラッグ&ドロップで移動する。制約に反する場所へ落とすと理由を示して断る
- **移動を取り消せる。** まとまりは最大 4 科目が同時に動くため手戻りが大きい。`Ctrl+Z` と「元に戻す」ボタンのどちらでも戻せる
- 脇は件数付きの折りたたみで、制約違反・未配置科目・集中講義を並べる。違反 0 件のときに場所を取らないようにする
- **未配置科目はドラッグでグリッドへ置ける。** 置く手段が画面に無いと、自動配置できなかった科目に事務局が手出しできない
- Excel 出力ボタン。保存するファイル名は事務局が入れられるようにする（年度や学科を名前に入れて保管するため）

---

# 第 5 部　検証と配布

### Task 31: フロントエンドの自動検証

**Files:** `backend/tests/js/dom_stub.js`, `restore_session.js`, `timetable_render.js`, `settings_models.js`, `backend/tests/test_frontend_*.py`

- ブラウザ全体を用意しなくても、「何を書き出したか」「どの要素が有効になったか」は確かめられる。`dom_stub.js` は `innerHTML` を文字列として持つだけの最小限の DOM
- ドライバが結果を JSON で標準出力に書き、pytest が読む。`node` が無い環境では自動的に飛ばす
- 対象は、セッション復元でどのタブが有効になるか / 学年順の並び・複数コマの移動・未配置科目の配置・HTML エスケープ / 予備モデルの表示と並び順・ログパネルの開閉

**決め事:** ハーネスを `frontend/` ではなく `backend/tests/` に置く。`make-dist.sh` は `tests` という名前のディレクトリを配布物に見つけるとビルドを中止するため。

### Task 32: 実ブラウザによる E2E

**Files:** `backend/tests/e2e/conftest.py`, `test_full_flow.py`, `.mcp.json`

- DOM スタブでは fetch の往復・SSE・HTML5 ドラッグ&ドロップ・ダウンロードが検証できない。ここだけは uvicorn を別プロセスで起こし、Chromium から触る
- 「読込 → モック生成 → 結果描画 → コマの移動 → Excel 出力」を 1 本通す
- **モックモードで走らせる。** AI モードは無料枠を消費し数十分かかる。モックなら同じ経路を無料かつ 10 秒ほどで決定的に通せる
- **`live_server` は `TIMETABLE_DATA_DIR` を渡す。** 別プロセスのサーバには `tests/conftest.py` の monkeypatch が届かないため、渡さないと実運用のセッション（`session_store.MAX_SESSIONS` 件まで）とログを実行のたびに追い出す
- 遅く Chromium を要するので、`pytest.ini` の `addopts = -m "not e2e"` により通常の実行では走らない。`-m e2e` で明示する
- 移動の検証は「ドラッグがサーバまで届くこと」を見る。落とし先が制約に触れるかはデータ次第なので、空きコマの妥当性に結果を委ねるとテストが日替わりになる。配置の可否そのものは制約のテストが受け持つ
- `.mcp.json` は Playwright MCP の登録。開発中に画面を直接操作して確かめるために使う。**バージョンは固定する。** 最新を取りに行く設定にすると、起動のたびに未レビューのコードが走り、要求される Chromium のリビジョンが上がった瞬間に黙って起動失敗する

**環境:** Chromium は `npx playwright install` で入れる。Linux では共有ライブラリ（libnss3・libnspr4・libasound2・libxcomposite1・libxdamage1・libxfixes3・libxrandr2 ほか）が要り、無いと起動時に `error while loading shared libraries` で即死する。`playwright install-deps chromium` を root で 1 度実行する。ヘッドレスで動かすので Xvfb は要らない。

### Task 33: 配布物

**Files:** `setup.bat`, `start.bat`, `start.sh`, `make-dist.sh`, `README.md`

- `setup.bat` は事務局 PC で 1 度だけ実行し、仮想環境を作って `requirements.txt` を入れる。Python が無い・3.11 より古い・別 OS の `.venv` が紛れている場合は、それぞれ何をすればよいか日本語で示して止まる
- `start.bat` / `start.sh` はサーバを起動してブラウザを開く。ポートが使用中なら別の番号を渡せることを伝えて止まる
- `make-dist.sh` は配布用 zip を作る。**入れるのはアプリ・設定・フロントエンド・起動スクリプト・README だけ**で、仮想環境・テスト・ドキュメント・API キー・実行時に生成される一切を除く。`.env`・`.venv`・`data`・`logs`・`tests` のどれかが混ざっていたらビルドを中止する
- `README.md` は取扱説明書。前半は事務局向けで、専門用語を使わず、黒い画面のメッセージから対処を引けるようにする。後半（§7）は中を直す人向けに、生成の流れ・全体を貫く決め事・読む順を置く

---

## 完了時の確認

```bash
cd backend && ../.venv/bin/pytest -q            # ユニットテスト
cd backend && ../.venv/bin/pytest -m e2e -q     # 実ブラウザの E2E
./make-dist.sh                                  # 配布物が作れる
```

加えて実データ（`カリキュラム一覧.xlsx`・`教員一覧.xlsx`。**教員の実名を含むため追跡していない**）で次を確かめる。

- 3 モードすべてが完走し、Stage 6 の最終検証で違反 0 件になる
- 未配置科目が出た場合、その理由が画面から読み取れる（多くは非常勤の出勤可能コマ数に対して担当科目が多すぎるという、時間割の組み替えでは解消できない事情である）
- 結果画面のスクリーンショットを撮って**実際に見る**。テストが緑でも白紙描画は起こりうる

---

## 計画のあとに変わったこと

全 33 タスクを終えたあと、事務局に実際に使ってもらって分かったことで作り替えた部分がある。**上のタスクは建てた順の記録なので、いま動いているものと食い違う場合はこちらが正しい。** 判断の根拠は仕様書に書いてある。

### Excel 出力を事務局の様式に作り替えた（仕様書 §9.1）

当初はマトリクス形式（縦 1〜5 限 × 横 月〜金、1 セルに改行で併記）で出していた。しかし事務局が長年 Excel で管理してきた形とかけ離れており、受け取ってからの手直しが前提になっていた。**紙の形を変えさせるのではなく、こちらが紙に合わせた。**

曜日を横に並べ、時限と年次で縦に区切る。集中講義は別シートをやめ、各シートの中へ入れた。教室・抽選・人数の欄は、元になるデータが無いので枠だけ用意して空で出す（事務局が手で埋める）。

### PDF 出力をやめた（仕様書 §9）

一時期は画面を印刷して PDF にする道も持っていた。§8.2 の情報設計（レールの色と塗り分け、年次の濃淡）を紙に残すためである。しかし上の作り替えで配布に要る体裁が Excel でそろい、**形を選ばせる必要がなくなったので経路ごと畳んだ。** 選択肢が 1 つしか無いプルダウン、画面に隠した印刷用の DOM、`@media print` の一式が丸ごと不要になった。PDF が要るときは Excel から印刷すればよい。

### 【再】とクラス分けを学生の衝突から外した（仕様書 §5.1）

H2・H3 は「同じ学科・同じ年次の学生が同時に受けられない」を見る。ところが次の 2 つは、学生が実際に受けるのは一方だけなので衝突しない。

- **【再】が付いた再履修クラス。** 1 年次に落とした人が受け直すもので、受けるのは 2 年生以降。配当年次は 1 年でも同じ年次の集団には属さない
- **英語Ⅰ【A】〜【E】のようなクラス分け。** 1 科目を教員ごとに割ったもの

この 2 つを外したことで、衝突とみなす組み合わせが 1347 対から 1043 対に減った。

### 踏襲モードを足した（仕様書 §7.3）

前年度の時間割をそのまま引き継ぎ、組み替えが必要な科目だけを組み直すモード。事前ロックにも前年度のコマを「希望」として渡すので、去年と同じ場所に着く。踏襲できなかった科目は理由（どの制約に触れたか・相手は誰か）とともに画面へ出す。

組み替え対象を誰が置くか（このパソコンか AI か）は事務局が選ぶ。**API キーがあるだけで AI に渡さない。** 黙って渡すと数十分と無料枠を消費してしまう。

### 生成を止められるようにした

AI モードは数十分かかる。止める手だてが画面に無いと、間違えて始めた生成が終わるまで事務局は何もできない。段の変わり目で中止を確かめる（段の途中では止めない。AI はチャンクの応答を捨てると無料枠が無駄になり、ソルバーと見直しは自前で中断点を持つ）。

**中止したら結果は残さない。** 半端な時間割を「結果」として見せると、どこまでが確定なのか事務局には判別できない。

### 検証を厚くした

E2E は 1 本（通し）から 39 本へ増やした。画面の不具合には**実ブラウザでしか捕まらない層**がある。DOM スタブは「何を書き出したか」までしか見ないので、要素の生成順やリスナの付け忘れは素通りする。実際、未配置科目がドラッグに反応しない不具合がその形で入り込み、単体テストは全部緑のままだった。

書いたテストが本当に機能しているかは、**わざと壊して落ちることを確かめる**ようにした。壊れたままでも通ってしまうテストが実際に 2 度見つかっている（どちらも非同期の描画・例外を待たずに検べていた）。
