# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョンは [SemVer](https://semver.org/lang/ja/)。
各バージョンに `### 互換性` を必ず書く（T-Drive の `docs/13_distribution.md` §6.2 の約束）。
Unity 側（MS2026 `MapExchange`）と対で読む JSON の版もここに書く。

## [Unreleased]

### 互換性
- （リリース前に記入）

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
