# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョンは [SemVer](https://semver.org/lang/ja/)。
各バージョンに `### 互換性` を必ず書く（T-Drive の `docs/13_distribution.md` §6.2 の約束）。
Unity 側（MS2026 `MapExchange`）と対で読む JSON の版もここに書く。

## [Unreleased]

### 追加
- トラス生成の Undo 修正: プレビュー（`show_preview` / `clear_preview`）は `undoInfo(stateWithoutFlush=False)` で Undo 履歴に乗らず、選択も変えない。`clear_preview` は `MS2026_TrussPreview*` の最上位をすべて消す（Undo で復活 / 連番 `Grp1..` になったものも）。生成・再生成・パスに変換・パスカーブ・切り離しは 1 つの Undo チャンクで、1 回の Ctrl+Z で戻る
- トラス生成の使いやすさ: (1) 生成前プレビュー — `preview_points_for`（直線 / 門型 3 本 / パス / プリセット / 点の部材中心線をスナップ後の点列で返す）、`show_preview` / `clear_preview`（最上位 `MS2026_TrussPreviewGrp` に黄色の degree 1 カーブ、Reference 表示で選択不可、始点に断面の正方形、選択は変えない）、`parent_world_matrix`。ウィンドウに「プレビュー表示」（既定 ON、optionVar `ms2026_truss_preview`）。コントロール変更と選択変更で更新、生成・ウィンドウを閉じる・リロードで消える。(2) `convert_to_path`: 直線 -> 2 点、門型 -> コの字 4 点のパスに作り直す（ボタン「パスに変換」）。門型の梁は柱の内側ではなく柱の中心線間を結ぶ（長さ 幅 − 断面）。(3) 説明文・種類別ヒントを書き直し、README のトラス生成節を整理。`build_preset` の点列計算を `_preset_final` に共通化（挙動不変）
- トラスの直角などを簡単に作る: `snap_points`（グリッド cm + 角度 0/45/90 のスナップ。先頭点固定で累積）、形プリセット `preset_points` / `build_preset`（line / L / U / rect、平面 XY / XZ）、ロケータの選択順から作る `points_from_selection` / `build_from_points`。`build_path` / `build_from_curve` / `rebuild` が `snap_angle` / `snap_grid` を取り JSON に保存（既定 90 / 10。`build_from_curve` は角度未指定なら degree 1 = 90、滑らかなカーブ = 0）。断面以下の短いスパンはスキップして本数を print。ウィンドウに種類「形プリセット」「選択した点から」、スナップ角度 / グリッド、CV 移動は X キーのヒント。README に「おすすめの手順」
- 編集用カーブ（閉）から再生成すると終点が始点と重なって points が増える問題を修正（rebuild が重複終点を除く）
- トラス生成にパス種別（カーブから）: `build_path` / `sample_curve` / `build_from_curve`。degree 1 は CV、滑らかなカーブは部材長（既定 200）で弧長等分、閉カーブ対応。部材 `SC_Truss_<名前>_01...`、グループの `ms2026_truss` JSON は `kind: "path"`, `points`, `closed`, `source_curve`, `member_len`, `params`
- 生成後の修正: `rebuild` がパス種別に対応（`source_curve` を再サンプル、無ければ `points`。`member_len` / `closed` の上書き可）、`make_edit_curve`（最上位に編集用カーブ `Truss_<名前>_Path`）、`detach_curve`。ウィンドウに「パス（カーブから）」「部材長」「閉じる」「パスカーブを表示 / 作成」「カーブを切り離す」。再生成でグループ内の手動編集が失われる点は README に明記
- トラス生成が `SM_Bg_` 未選択でも使える: 生成先は `SM_Bg_` 区画 → 選択した transform（`SM_Truss_` ならその親）→ 最上位の順。ボタン名は `生成`。生成物の名前・属性は不変。`tests/verify_truss.py` に親なし（world）のケースを追加
- ツール全体のリロード `ms2026_maya_reload.reload_all(reopen=True)`: `ms2026_maya_*` を `sys.modules` から捨てて読み直し、メニューと開いていたウィンドウを作り直す。メニュー `ツールをリロード`、両ウィンドウの `リロード` ボタン、T-Drive の「ツールをリロード」（`GreyboxTool.refresh()`）から呼ぶ。従来は `refresh()` が `ms2026_maya_tools` だけ読み直しており、新しいメニュー項目が出なかった
- ライブ会場用トラスのプロシージャル生成 `ms2026_maya_truss.py`（直線 / 門型）と、ウィンドウ `ms2026_maya_ui_truss.py`（`Tools > MS2026 > トラス生成...`）。部材 1 本 = `SC_` 1 つ = Box 1 つ
- `ms2026_maya_collision.py`: ノードの文字列属性 `ms2026_collider_shape`（box/sphere/capsule）があれば自動判定より優先。属性が無いノードの挙動は不変
- `tests/verify_truss.py`（mayapy 検証。配布対象の外）

### 検証
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py` に Undo の検証を追加: show/clear_preview を繰り返しても undoName 不変・選択不変、連番グループが `clear_preview` で全消去、openChunk/closeChunk で包んだ `build_gate` が `cmds.undo()` 1 回で消える。VERIFY OK（既存の全検証も通過）
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py` にプレビューとパス変換を追加: `preview_points_for` が gate 3 本（各 2 点）/ straight 2 点 / preset U 4 点 / XZ rect closed / path・points の部材数と一致、不正寸法は ValueError。`show_preview` は最上位に `MS2026_TrussPreviewGrp` を 1 つだけ作り（2 回呼んでも増えない、親の位置を反映、選択不変）、`clear_preview` で消え、無くても安全。`convert_to_path`: 門型（600 × 400）-> path・部材 3 本・柱の高さ 403・梁 573（570 + 斜材のはみ出し 3）、直線（500）-> 2 点 1 部材、グループの位置保持、パスの再変換はエラー、`make_edit_curve` -> `rebuild` で 3 本。既存の検証も全部通過。GUI（ウィンドウ・scriptJob・プレビューの実表示）は未確認
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py`: 親なし（world）で `build_gate` / `build_straight` が最上位に `SM_Truss_` を作り、`rebuild` も最上位のまま。既存の検証も全部通過。生成先の決定（`_resolve_parent`）と GUI は未確認
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py` の先頭に `ms2026_maya_reload.reload_all(reopen=False)`（standalone）を 1 回通してから既存の検証が全部通ることを確認。GUI のメニュー / ボタン / ウィンドウ再オープンは未確認
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py`: 門型（幅 600 × 高さ 400）+ 直線（長さ 500）を `SM_Bg_TrussTest` 配下に生成 → `check_selection` 問題 0 件 → `export_block` → `.colliders.json` は Box 4 件（門 3 + 直線 1）。size は PostL/PostR = 403×30×30、Beam = 543×30×30（幅 600 − 柱 2 本分 60 = 540）、Line = 503×30×30。+3 cm は斜材の端面が部材端からはみ出す分。`rebuild`（800×500）も確認
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py` にパス生成を追加: コの字 degree 1 カーブ（4 点）→ 部材 3 本、`check_selection` 問題 0 件、`export_block` で Box 3 件（最大軸 403 / 403 / 603）。CV を 1 つ動かして `rebuild` → 1 本目 403 → 503。`make_edit_curve`（最上位・`source_curve` 差し替え）/ `detach_curve`（null）/ カーブ削除後の `rebuild`（points にフォールバック）を確認。`cmds.circle(radius=300, degree=3)` を部材長 200 → 9 部材・閉・Box 9 件。親のオフセット（親ローカルへの変換）と world 親も確認。GUI（ウィンドウ・ボタン）は未確認
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py` にスナップを追加: ずれたコの字 4 点（snap 90 / grid 10）→ 3 部材すべて軸平行（|dot| > 0.999）、長さ 403 / 603 / 403（斜材のはみ出し +3 込みで 400 / 600 / 400 ±5）。プリセット line / L / U / rect = 1 / 2 / 3 / 4 部材（rect は closed）、XZ の rect は全点 y=0、`make_edit_curve` -> `rebuild` で 4 点のまま。短いスパンのスキップ、ロケータ 3 個の選択順どおりの `points_from_selection`（1 点はエラー）。既存の検証も全部通過。GUI（ウィンドウ・X キースナップ）は未確認

### 互換性
- JSON の形は不変（`.colliders.json` version 1 / `.props.json` version 2 のまま）。パス種別の追加・スナップ設定（`snap_angle` / `snap_grid`）は Maya 側のグループ属性 `ms2026_truss` だけに入り、Unity 側が読む JSON には影響しない。`ms2026_collider_shape` 属性は Unity 側に影響なし（Maya 側の判定にだけ使う）

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
