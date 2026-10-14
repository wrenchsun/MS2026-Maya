# CLAUDE.md — MS2026-Maya

MS2026（Unity、LAN 4 人対戦）のグレーボックス → Maya → Unity 背景パイプラインの **Maya 側ツール**（Maya 2026 / Python 3）。
T-Drive の外部ツールパッケージとして配布する（T-Drive `docs/13_distribution.md` §6）。

## 仕様の正

- パイプライン全体・命名規則・JSON の形: MS2026 の `Docs/Guides/MayaGreyboxPipeline.md`（`C:\Users\yamag\wrench\unity\MS2026`、読み取りのみ）。Unity 側の取り込みコード `Assets/_Project/Scripts/Editor/MapExchange/` と対で変える
- 配布・更新・エントリーポイントの約束: T-Drive の `docs/13_distribution.md` §6（`C:\Users\yamag\wrench\maya\T-Drive`、読み取りのみ）
- 使い方: [README.md](README.md)

## 守ること

- モジュール名は `ms2026_` 接頭辞（他のツールと衝突させない）。エントリーポイントは `maya/scripts/ms2026_greybox/tool.py` の `create_tool()`。`userSetup.py` は持たない
- JSON（`.props.json` / `.colliders.json`）の `version` を上げるときは Unity 側（MS2026）を同じ日に直し、CHANGELOG の `### 互換性` に書く。読めなくなる変更は MAJOR
- リリース: `VERSION` と CHANGELOG を更新して注釈付きタグ `vX.Y.Z`。**push・タグ push は明示的に指示されたときだけ**
- 検証は mayapy（`C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe`）の標準出力で行い、結果を CHANGELOG か MS2026 の `Docs/Guides/MayaGreyboxPipeline.md` §6 に書く
- Git LFS は使わない（T-Drive のインストーラーが LFS を取らないため）
