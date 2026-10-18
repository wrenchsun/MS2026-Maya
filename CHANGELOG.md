# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョンは [SemVer](https://semver.org/lang/ja/)。
各バージョンに `### 互換性` を必ず書く（T-Drive の `docs/13_distribution.md` §6.2 の約束）。
Unity 側（MS2026 `MapExchange`）と対で読む JSON の版もここに書く。

## [Unreleased]

### 追加
- ディスプレイ・ライトの配置往復 `<Scene>.layout.json`（Unity `MapExchange` の `LayoutFile` / MX-3）: `ms2026_maya_layout.py`（`import_layout` / `add_placeholder` / `export_layout` / `find_placeholders`）とウィンドウの **5. ディスプレイ・ライト**（`ms2026_maya_ui_layout.py`）
  - 読み込み: JSON のワールド行列（行優先 16 値、cm）を `DSP_<kind>__<name>` / `LGT_<kind>__<name>` の置き物に入れる。`id` → 名前の順で照合、JSON に無い置き物は消さない。`Greybox_<Scene>_Layout_<日付>.fbx` を読み込んで同名のノードに対応させることもでき（無ければ向きの分かる仮の形を作る）、FBX と JSON の位置ずれを警告する
  - 追加: 12 種の kind から選び、名前は `[A-Za-z0-9_]+`・`__` なし・重複不可
  - 書き出し: 全置き物を `xform(q=True, ws=True, matrix=True)` で書き戻す（`version` 1、`id` はあれば保持、Maya で足した物には付けない、既存 JSON の `scene` を保つ）。不正な名前・未知の kind・`id` の無い同名があれば何も書かず全件を列挙して止まる
  - カスタム属性 `ms2026_id` / `ms2026_kind` / `ms2026_category` / `ms2026_layout_scene`（保存・再読込しても残る）
  - フォルダは既存の設定を流用（読み込み = グレーボックスFBX、書き出し = 区画FBX・props.json 出力先）
- `tests/verify_layout.py`（mayapy 検証。配布対象の外）
- README と `docs/manual.html` に配置往復の節。Vision（3D パネル）はパネルだけが動きスタジオは動かないこと、Maya は形を持たず置き物を動かす・足すだけであることを明記

### 検証
- mayapy（Maya 2026）で `tests/verify_layout.py` が VERIFY OK: JSON -> 世界行列と属性、保存・再読込、`id` での再読み込み（同名 2 個）、移動 + 追加 -> 書き出しの行列が `xform` と一致・`id` 保持・新規は `id` なし、不正名 / 重複 / kind 不一致の拒否、不均一スケール + 回転の親の下でも往復でワールド行列が不変、Maya が書いた FBX の読み込みと置き換え。`tests/verify_truss.py` も VERIFY OK（回帰なし）
- 2026-10-18 Unity（MS2026 `ssk_CreateMap` bdc4533、`feature/maya-simple-collision` をマージ済み）でトラスの取り込みを確認。門型 + 直線 + 円 R300 + 塔の区画 `SM_Bg_TrussTest` を `BackgroundPlacer.AddColliders` に通し、BoxCollider 15 個・MeshCollider 0 個。各 Box の world 中心とサイズは描画メッシュの bounds と差 0.0000 m（回転した円の部材を含む）、Maya の world AABB とも差 0.0000 m（X 反転・0.01 倍の前提どおり）
- 未確認: Unity が実際に書いた FBX の読み込み、Unity 側 `Import Layout` での取り込み（MX-4）、GUI の操作

### 互換性
- `.layout.json` **version 1** を新しく扱う。Unity 側 `LayoutFile.SupportedVersion` = 1 と対（`id` は version を上げない任意の追加欄）。既存の `.props.json`（version 2）/ `.colliders.json`（version 1）は不変
- 読めなくなる変更なし。VERSION は据え置き（リリース時に決める）
- 1.1.0 の「Unity 側には `.colliders.json` の取り込みがまだ無い」は誤り。取り込みは MS2026 の `feature/maya-simple-collision`（`SimpleColliderBuilder`、SupportedVersion 1）にあり、2026-10-18 に `ssk_CreateMap` へマージした（main は未マージ）。トラス用に Unity 側の追加は不要

## [1.1.0] - 2026-10-16

ライブ会場用トラスのプロシージャル生成を追加した版。

### 追加
- トラス生成の全体: `ms2026_maya_truss.py`（直線 / 門型）とウィンドウ `ms2026_maya_ui_truss.py`（`Tools > MS2026 > トラス生成...`）。部材 1 本 = `SC_` 1 つ = Box 1 つ。`SM_Bg_` 未選択でも使える（生成先は `SM_Bg_` 区画 → 選択した transform → 最上位）。`ms2026_maya_collision.py` はノードの文字列属性 `ms2026_collider_shape`（box/sphere/capsule）を自動判定より優先する（属性が無いノードの挙動は不変）
- パスと編集用の点: カーブから生成（`build_path` / `build_from_curve`。degree 1 は CV、滑らかなカーブは部材長で弧長等分、閉カーブ対応）。形の編集は角ごとの黄色のロケータ（`make_edit_points` / `insert_edit_point` / `delete_edit_point` / `clear_edit_points`）で行い、`rebuild` で再生成する。`convert_to_path` で直線 / 門型をパスに変換できる
- 生成前プレビュー: 黄色のカーブと断面の正方形を `MS2026_TrussPreviewGrp` に表示（Reference 表示で選択不可、Undo 履歴と選択に影響しない）。ウィンドウの「プレビュー表示」（既定 ON）
- スナップと形プリセット: グリッド / 角度（0・45・90）のスナップ、形プリセット（line / L / U / rect、平面 XY / XZ）、ロケータの選択順から作る「選択した点から」。断面以下の短いスパンはスキップ
- 円弧 / 塔 / コーナーブロック: 円弧・円 `build_arc`（`arc_points`）、塔（グランドサポート）`build_tower`（垂直トラス + スリーブ + ベース板）、門型 / パスの角に section の立方体を置く `corner_block`（既定 True）
- 詳細枠とプリセット保存: 横桟・斜材径、弦 / 斜材の円周分割、斜材パターン（ジグザグ / ラダー）。プリセットの保存 / 読み込み / 削除（`ms2026_maya_truss_presets.py`、optionVar `ms2026_truss_presets`）、組み込み 4 種（削除不可）
- ツール全体のリロード `ms2026_maya_reload.reload_all(reopen=True)`: メニュー、両ウィンドウのボタン、T-Drive の「ツールをリロード」から呼ぶ。新しいメニュー項目も反映される
- HTML マニュアル `docs/manual.html`（メニュー `Tools > MS2026 > マニュアル` と各ウィンドウの **マニュアル** ボタンから開く）
- `tests/verify_truss.py`（mayapy 検証。配布対象の外）

### 修正
- トラス生成の Undo: プレビューは Undo 履歴に乗らず選択も変えない。生成・再生成・パスに変換などは 1 回の Ctrl+Z で戻る。`clear_preview` は連番になったプレビューも全部消す
- 部材の端で斜材・横桟の端面が約 1.5 cm はみ出していた問題を、端面のクランプで修正（`.colliders.json` の size が 長さ × section × section ±1 cm になる）
- 編集用カーブの CV 編集モードに入るとプレビューが選択 / hilite を外して編集できなくなる問題を修正
- 閉カーブから再生成すると終点が始点と重なって points が増える問題を修正
- 区画外生成: `SM_Bg_` が無くても最上位に `SM_Truss_` を作れる（`rebuild` も最上位のまま）

### 検証
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py` が VERIFY OK。門型 PostL/PostR = 400 × 30 × 30、Beam = 540 × 30 × 30、直線 = 500 × 30 × 30（±1）。`.colliders.json` は門型 + 直線で Box 4 件、コの字パス（コーナーブロック ON）は 415 / 615 / 400・OFF は 400 / 600 / 400（部材 3・Box 3）。円 R300 部材長 200 = 9 部材・閉、塔 400 = Box 2 件（Post 40 × 430 × 40、Base 100 × 5 × 100）。スナップ・プリセット・プレビュー・Undo・リロード・親なし生成も通過
- 実機 Maya 2026 の GUI で確認: ツールのリロード、生成の Undo（1 回の Ctrl+Z で戻る）、ロケータでの編集と再生成、プリセットの読み込み、円弧・塔の生成

### 互換性
- JSON の形は不変: `.props.json` version 2、`.colliders.json` version 1。Unity 側（MS2026）の変更は不要
- Maya 側で追加した属性（`ms2026_truss`、`ms2026_collider_shape`）と、`ms2026_truss` JSON の任意キー（`edit_points`、`arc`、`snap_*`、`member_len`、`corner_block`）は Unity が読む JSON に影響しない
- 見た目の変更: 部材メッシュの端面がクランプされ（最大 1.5 cm 短くなる）、門型 / パスの角にブロックが付く（`corner_block` 既定 True。`rebuild` で既存トラスにも適用）
- **Unity 側には `.colliders.json` の取り込みがまだ無い**。トラスの Box コライダーを Unity で使うには Unity 側の実装が必要

## [1.0.0] - 2026-10-14

MS2026 リポジトリの `Tools/Maya/` から切り出した最初の版。機能は MS2026 の 2026-10-14 時点と同じ。

### 互換性
- Unity 側（MS2026 `MapExchange`）が読む JSON の版: `.props.json` = 2、`.colliders.json` = 1
- 旧 `NC_`（当たり判定なし）は廃止。`SC_`（簡易当たり判定）として扱う。`Check` が警告し、`名前を自動修正` で `SC_` になる
- フォルダ設定の既定が変わった: `$TDRIVE_PROJECT/MayaWork/…`（T-Drive のプロジェクトフォルダがあるとき）、無ければ `Documents/maya/MS2026-MayaWork/…`。MS2026 の `Tools > MS2026 > Map > Exchange Folders...` と同じフォルダに揃えること
- 導入方法が変わった: `sys.path` に `MS2026-Maya/maya/scripts` を足す（T-Drive の外部ツール機能ができたら URL で追加）

### 追加
- 簡易当たり判定 `SC_`（Box / Sphere / Capsule を書き出し時に自動で選ぶ。`ms2026_maya_collision.py`、`SM_Bg_<区画>.colliders.json`）
- 小物 `SC_Prop_`（簡易当たり判定。`.props.json` version 2 に `collision` と `simple` の形）
- T-Drive の殻に載せるエントリーポイント `ms2026_greybox.tool.create_tool()`（T-Drive 無しでも従来の `install_menu()` で使える）
