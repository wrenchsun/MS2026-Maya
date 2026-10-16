# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョンは [SemVer](https://semver.org/lang/ja/)。
各バージョンに `### 互換性` を必ず書く（T-Drive の `docs/13_distribution.md` §6.2 の約束）。
Unity 側（MS2026 `MapExchange`）と対で読む JSON の版もここに書く。

## [Unreleased]

### 追加
- トラス生成が `SM_Bg_` 未選択でも使える: 生成先は `SM_Bg_` 区画 → 選択した transform（`SM_Truss_` ならその親）→ 最上位の順。ボタン名は `生成`。生成物の名前・属性は不変。`tests/verify_truss.py` に親なし（world）のケースを追加
- ツール全体のリロード `ms2026_maya_reload.reload_all(reopen=True)`: `ms2026_maya_*` を `sys.modules` から捨てて読み直し、メニューと開いていたウィンドウを作り直す。メニュー `ツールをリロード`、両ウィンドウの `リロード` ボタン、T-Drive の「ツールをリロード」（`GreyboxTool.refresh()`）から呼ぶ。従来は `refresh()` が `ms2026_maya_tools` だけ読み直しており、新しいメニュー項目が出なかった
- ライブ会場用トラスのプロシージャル生成 `ms2026_maya_truss.py`（直線 / 門型）と、ウィンドウ `ms2026_maya_ui_truss.py`（`Tools > MS2026 > トラス生成...`）。部材 1 本 = `SC_` 1 つ = Box 1 つ
- `ms2026_maya_collision.py`: ノードの文字列属性 `ms2026_collider_shape`（box/sphere/capsule）があれば自動判定より優先。属性が無いノードの挙動は不変
- `tests/verify_truss.py`（mayapy 検証。配布対象の外）

### 検証
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py`: 親なし（world）で `build_gate` / `build_straight` が最上位に `SM_Truss_` を作り、`rebuild` も最上位のまま。既存の検証も全部通過。生成先の決定（`_resolve_parent`）と GUI は未確認
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py` の先頭に `ms2026_maya_reload.reload_all(reopen=False)`（standalone）を 1 回通してから既存の検証が全部通ることを確認。GUI のメニュー / ボタン / ウィンドウ再オープンは未確認
- 2026-10-16 mayapy（Maya 2026）で `tests/verify_truss.py`: 門型（幅 600 × 高さ 400）+ 直線（長さ 500）を `SM_Bg_TrussTest` 配下に生成 → `check_selection` 問題 0 件 → `export_block` → `.colliders.json` は Box 4 件（門 3 + 直線 1）。size は PostL/PostR = 403×30×30、Beam = 543×30×30（幅 600 − 柱 2 本分 60 = 540）、Line = 503×30×30。+3 cm は斜材の端面が部材端からはみ出す分。`rebuild`（800×500）も確認

### 互換性
- JSON の形は不変（`.colliders.json` version 1 / `.props.json` version 2 のまま）。`ms2026_collider_shape` 属性は Unity 側に影響なし（Maya 側の判定にだけ使う）

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
