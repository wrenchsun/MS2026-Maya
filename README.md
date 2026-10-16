# MS2026-Maya — グレーボックス → Maya → Unity 背景パイプラインの Maya 側ツール

MS2026（Unity）のグレーボックスを Maya に渡し、Maya で作った背景メッシュ・小物を Unity に戻すためのツール（Maya 2026 / Python 3）。
2026-10-14 に MS2026 リポジトリの `Tools/Maya/` から切り出した。

- 仕様の正（命名規則・JSON の形・Unity 側の動き）: MS2026 の `Docs/Guides/MayaGreyboxPipeline.md`
- 配布・更新: T-Drive の外部ツールパッケージ（T-Drive `docs/13_distribution.md` §6）。T-Drive の更新ウィンドウから URL で追加・更新できるようになる予定。それまでは下の手動導入
- マニュアル: [docs/manual.html](docs/manual.html)（メニュー `Tools > MS2026 > マニュアル`、各ウィンドウの **マニュアル** ボタン）
- 版: [VERSION](VERSION) / [CHANGELOG.md](CHANGELOG.md)（Unity 側と対で読む JSON の版もここ）

```
maya/scripts/
  ms2026_maya_*.py          ツール本体（モジュール名は ms2026_ 接頭辞）
  ms2026_greybox/tool.py    T-Drive の殻に載せるエントリーポイント create_tool()
  userSetup_example.py      起動時に自動でメニューを作る例
tool.json                   T-Drive 向けのメタ情報（id / entry / requires）
```

## セットアップ（手動導入。T-Drive の外部ツール機能ができるまで）

`maya/scripts` を Maya の Python パスに追加する。どちらか一方でよい。

- 恒久: `Documents/maya/2026/scripts/userSetup.py` に追記
  ```python
  import sys
  sys.path.append(r"C:\Users\<あなた>\wrench\maya\MS2026-Maya\maya\scripts")
  ```
- 一時: スクリプトエディタ（Python タブ）で上の 2 行を実行

その後、スクリプトエディタ（Python タブ）で次を 1 回実行すると、メニューバーに `Tools > MS2026` ができる（既に `Tools` メニューがあればその中に追加）。

```python
import ms2026_maya_tools as t
t.install_menu()
```

起動時に自動でメニューを作るには [maya/scripts/userSetup_example.py](maya/scripts/userSetup_example.py) の内容を `userSetup.py` に書く。
シェルフが好みなら `Tools > MS2026 > シェルフを作成`（または `t.install_shelf()`）。任意。

T-Drive に載せる場合は `tool.json` の `entry`（`ms2026_greybox.tool`）の `create_tool()` を殻が呼ぶ。1 段目のタブに「MS2026 グレーボックス」が並び、作業は従来どおり `Tools > MS2026 > グレーボックス...` のウィンドウで行う。

## フォルダ設定（ウィンドウ先頭の **0. フォルダ**）

読み書きする 3 つのフォルダは固定ではなく、ウィンドウで変えられる。欄を編集するか `参照...` で選ぶとすぐ保存され、FBX / 小物の一覧も更新される。`既定に戻す` で 3 つとも既定へ戻る（欄を空にしても、その 1 つが既定に戻る）。設定は Maya の optionVar に保存され、ユーザーごとに再起動後も残る（リポジトリには入らない）。

**既定は `$TDRIVE_PROJECT/MayaWork/`（T-Drive のプロジェクトフォルダがあるとき）、無ければ `Documents/maya/MS2026-MayaWork/`。Unity 側（MS2026 の `Tools > MS2026 > Map > Exchange Folders...`、既定は MS2026 リポジトリ直下の `MayaWork/`）と必ず同じフォルダに揃える。** MS2026 リポジトリが手元にあるなら、Maya 側を MS2026 の `MayaWork/` に向けるのが簡単。

| 欄 | optionVar | 既定（`<MayaWork>` 配下） |
|---|---|---|
| グレーボックス FBX（Unity 出力・読み込み元） | `ms2026_greybox_dir` | `Export` |
| 区画 FBX・`props.json`・`colliders.json` の出力先 | `ms2026_block_out_dir` | `Import` |
| 小物 FBX ライブラリ | `ms2026_props_dir` | `Props` |

コードからは `ms2026_maya_settings.get_dir("greybox_dir")` / `set_dir(key, path)` / `reset_dirs()`。実装は `ms2026_maya_settings.py`（ロジック）と `ms2026_maya_ui_settings.py`（枠）。

## 作業の流れ（`Tools > MS2026 > グレーボックス...` のウィンドウで行う）

1. Unity: `Tools > MS2026 > Map > Export Greybox (FBX)` → `<MayaWork>/Export/Greybox_*.fbx`
2. Maya: ウィンドウの **1. 準備 > Setup**（単位 cm・Y 上・レイヤー作成）
3. **2. 読み込み**: 一覧（新しい順）から FBX を選び **選択したFBXを読み込む**（複数可。`ファイルを選ぶ...` でダイアログも可）
   - 区画ごと（`Greybox_<Scene>_<Block>_<日付>.fbx`）に表示レイヤー `GB_<Block>` へ入る。アンカー（`_Reference`）は `GREYBOX_ANCHORS`。どれも Reference 表示。編集・移動しない
   - 同じブロックを再度読み込むと前回分は自動で置き換わる（レイヤーは残る）
   - **区画の表示** 枠で区画を選び `選択だけ表示` / `すべて表示` / `すべて非表示`。`グレーボックスを半透明` / `不透明に戻す` で GB_ レイヤーのメッシュだけ半透明マテリアル（`MS2026_GreyboxGhost`）にできる（自作メッシュは変わらない。元のマテリアルはシェイプの `ms2026_orig_sg` に記録）。レイヤーパネルの V でも同じ
4. 「区画の表示」で区画を選び **選択した区画の作業グループ SM_Bg_ を作る** を押す（グレーボックスのグループは参照用で触らない）。背景はこの `SM_Bg_<区画名>` グループの中に作る。最上位グループ名は `SM_Bg_<区画名>`（区画名はグレーボックスのグループ名と一致）。メッシュ名の接頭辞は 3 種類（「当たり判定なし」は無い。迷ったら `SC_`）
   - `SM_<内容>`: 描画 + 形どおりの当たり判定（床・壁・坂など正確さが要るもの）
   - `SC_<内容>`: 描画 + **簡易当たり判定**。箱・球・カプセルのどれにするかは **Export Block が自動で決める**（小物・装飾・柱など。調整は Unity 側）
   - `UCX_<元メッシュ名>`: 当たり判定のみ（描画しない）
   - 旧 `NC_` は `Check` が警告する。`名前を自動修正` で `SC_` になる
   - 区画内の使い回しは**インスタンス**が向く（編集 > 特殊な複製 > インスタンス）。FBX では共有メッシュとして書き出される。`Check` もインスタンスを許容する
5. 書き出す前にグループを選んで **ヒストリを削除（選択以下）**。最上位グループ `SM_Bg_<区画名>` だけは原点・回転 0・スケール 1 のまま（子やインスタンスの位置は自由）
6. **3. 検査と書き出し**: 最上位グループを選んで **Check**（詳細はスクリプトエディタ）
7. 問題なければ **Export Block** → `<MayaWork>/Import/SM_Bg_<区画名>.fbx`。`SC_` があれば隣に `SM_Bg_<区画名>.colliders.json`（簡易当たり判定の形）も出る。状態行に `簡易当たり判定 N 件 (Box a / Sphere b / Capsule c)` と出るので、おかしな内訳ならスクリプトエディタの `[MS2026 collision] <パス> -> <形>` で確認する
8. Unity: `Tools > MS2026 > Map > Import Background`

結果はウィンドウ下部のステータス行に表示される。

## NURBS・サブディビジョンは使えない

Unity が読めるのはポリゴンメッシュだけ。NURBS サーフェス / カーブ・ベジェ・サブディビジョンは書き出しで黙って落ちるため、`Check` が `Not a polygon mesh (...)` で警告する。NURBS サーフェスは **3. 検査と書き出し** の `NURBS をポリゴンに変換（選択以下）` で、選択以下をまとめてポリゴン化できる（名前・親・位置は保持、履歴なし）。カーブは変換できないので「変換不可: カーブ N 件」と表示される（消すかポリゴンで作り直す）。実装は `ms2026_maya_geometry.py`。

## 命名はウィンドウで

規則を覚えなくてよい。ウィンドウの **命名（選んでから押す）** 枠で、オブジェクトやグループを選んで接頭辞ボタンを押す。

- `形どおり (SM_)` / `簡易当たり判定 (SC_)` / `当たり判定専用 (UCX_)`: 選択と中身をまとめて改名（日本語・空白・記号は `_` に直る。小物の中と `SM_Bg_` は除く）
- `小物にする: ... (SM_Prop_ / SC_Prop_)`: 選んだ最上位ノードを小物名にする
- `名前を自動修正 (選択以下)`: 規則に合わない名前を直す（接頭辞があれば保持、旧 `NC_` は `SC_` に、無ければ `SM_`。小物の中は触らない）
- `問題のノードを選択`: Check で引っかかったノードを選択する
- 結果は状態行に件数で出る（詳細はスクリプトエディタ）。実装は `ms2026_maya_naming.py` / `ms2026_maya_ui_naming.py`

## 小物（Prop）

街灯・ベンチなど使い回す部品は、区画 FBX に含めず「小物モデル + 配置データ」で Unity へ渡す。

- 名前: `SC_Prop_<名前>`（簡易当たり判定。小物 1 個に箱・球・カプセルを 1 つ自動で付ける。おすすめ）/ `SM_Prop_<名前>`（形どおり）。`<名前>` は A-Za-z0-9_。当たり判定の種類は接頭辞で決まる（旧 `NC_Prop_` は簡易扱い）
- 小物は原点・回転 0・スケール 1 で作り、Delete History しておく
- 流れ（ウィンドウ **4. 小物**）
  1. 小物を作り、最上位ノードを選んで **選択を小物として書き出す** → `<MayaWork>/Props/Prop_<名前>.fbx`
  2. 区画シーンで `SM_Bg_<区画名>` を選び、一覧から **選択した小物を配置**（何度でも置ける。前に置いた分は消えない）
  3. 動かし、**Ctrl+D（複製）またはインスタンス**で増やす。どちらも小物として数えられる
  4. **Export Block** が `SM_Bg_<区画名>.fbx` と同時に `SM_Bg_<区画名>.props.json`（名前・当たり判定の種類と形・ワールド行列）を書く
- 手早く登録: 作ったノードをアウトライナーで選び **選択を小物として登録（簡易当たり判定 / 形どおり）** を押すだけ。`SC_Prop_/SM_Prop_<元の名前>` に改名し、ヒストリ削除 → 原点・回転 0・スケール 1 の状態で `Prop_<名前>.fbx` を書き出し、元ノードは**元の位置に最初の配置インスタンスとして残る**（区画グループの中でも可）。すぐ Ctrl+D / インスタンス / 一覧から配置で増やせる。同じ名前で再登録すると FBX は上書きされる
  - 小物の原点 = 登録時のノードのローカル原点（Translate が指す点）。登録前にモデルを足元が原点になるよう作る（ピボットを足元に置く: Modify > Center Pivot や D キーで動かすのはピボットのみで、書き出し時は原点扱い）。スケールは 1 として書き出されるので、拡縮は Freeze Transformations してから登録する
- 小物のメッシュは区画 FBX に入らない。小物の中の名前は `Check` の対象外
- 小物が 1 つも無い区画では、古い `.props.json` は削除される
- Unity 側: 小物 FBX は `Tools > MS2026 > Map > Import Props`、区画は従来どおり `Import Background`

## トラス生成（ライブ会場用）

`Tools > MS2026 > トラス生成...` のウィンドウで、4 本弦のボックストラスをプロシージャルに作る（実装は `ms2026_maya_truss.py`、ウィンドウは `ms2026_maya_ui_truss.py`）。単位 cm。

### 使い方（3 ステップ）

1. **種類と寸法を入れる**。シーンに黄色のプレビュー（部材の中心線と、始点の断面の正方形）が出るので、スケールを見ながら調整する
2. **生成**。生成先は `SM_Bg_<区画>`（またはその子孫）を選んでいればその区画の下（`Export Block` のコライダーになる）、他の transform を選んでいればその下、未選択なら最上位（`SM_Truss_` を選んだ場合はそのトラスの親）。ステータス行に「生成先」が出る。後から `SM_Bg_` に入れてもそのまま書き出せる
3. **形を変えたいとき**: トラスを選んで **編集用の点を表示** → 出てきた黄色い十字を W キーで動かし、**選択したトラスを再生成**（直線・門型は自動でパスに変換される）

### 種類の説明

- **直線**: 長さ。原点は部材の中心
- **門型**: 幅（柱の外側どうし）と高さ（梁の上端）。原点は床面の中央。柱 2 + 梁 1 の 3 部材
- **パス（カーブから）**: カーブ（nurbsCurve を持つ transform）を 1 本選ぶ。degree 1 のカーブは CV をそのまま点列にしてスパンごとに 1 部材。滑らかなカーブは弧長を **部材長**（既定 200）で等分（分割数 = max(1, round(弧長 / 部材長))）。閉カーブは自動で閉じる。ポリラインを閉じたいときは **閉じる**
- **形プリセット**: 直線 / L 字 / コの字 / ロの字、平面（立面 XY / 床面 XZ）、幅・高さ。点は部材の中心線で、原点は床面の中央（左右対称）。立面 XY では直線 / ロの字を断面の半分持ち上げて床に乗せ、L 字 / コの字は柱の下端が y=0。持ち上げがグリッドの倍数でないとき、グリッドは生成時の形にだけ掛け、保存する `snap_grid` は 0。床面 XZ は y=0 で奥行き（高さ）が原点中心
- **選択した点から**: ロケータ等を作りたい順に選ぶ（2 個以上）。ロケータは区画の外にあってよく、生成後は不要
- 共通: 断面サイズ（既定 30）、弦径（5）、セグメント長（100）。横桟・斜材径は 3、円周分割は弦 8 / 斜材 6（コードの `DEFAULT_PARAMS`）
- パス系の部材は `SC_Truss_<名前>_01, _02, ...`、グループは `SM_Truss_<名前>`。断面の向きは部材ローカル Y を world Y に寄せる（垂直に近いスパンは world Z 基準）。コーナーでは部材どうしが重なる（コライダーは Box のまま）。部材が断面以下の短いスパンはスキップし、本数を print する
- スナップ（パス / プリセット / 点）: **角度**（自動 / なし / 45° / 90°）と **グリッド** cm（既定 10、0 でなし）。先頭点を固定し、各スパンを最も近い許可方向（90° は ±X/±Y/±Z、45° は座標平面内の 45° 対角も追加）に置き換え、方向への長さ（グリッドに丸める）で次の点を決める。自動 = ポリライン / プリセット / 点は 90°、滑らかなカーブは角度なし（グリッドだけ）。`ms2026_truss` JSON の `snap_angle` / `snap_grid` に保存され、再生成でも適用される。閉じるとき最後 -> 最初のスパンは先頭点が固定なので許可方向からずれうる（print で知らせる）

### プレビュー

ウィンドウ上部の **プレビュー表示**（既定 ON、`optionVar ms2026_truss_preview` に記憶）が ON の間、種類・形・平面・寸法・部材長・スナップ・閉じる・断面サイズの変更とシーンの選択変更のたびに、生成されるトラスの部材中心線を最上位の `MS2026_TrussPreviewGrp`（黄色の degree 1 カーブ `MS2026_TrussPreview[_N]`）に出す。スナップ後の点列なので生成結果と一致する。各ポリラインの始点に断面サイズの正方形が付く。
プレビューの作成・削除は Undo 履歴に乗らない。生成・再生成・パスに変換などは 1 回の Ctrl+Z で戻る。

- 選択不可（Reference 表示）。最上位にあり `MS2026_` 接頭辞で、`Check` / `Export Block` / FBX の対象にならない
- OFF にする、**生成**、ウィンドウを閉じる、**リロード** で消える。入力が不正（断面以下の寸法、カーブ / 点が未選択など）のときはプレビューが消えてステータス行に理由が出る。プレビューのエラーで生成は止まらない
- 生成先の決め方は **生成** と同じ（親の位置・回転を反映して出す）

### パスに変換

**パスに変換**（直線 / 門型のトラスを選んで押す）で、同じグループ・名前・寸法のまま `kind: "path"` に作り直す（`convert_to_path(group)`）。直線は 2 点、門型はコの字 4 点（柱 2 本は全高、梁は柱の中心線間）。パスのトラスには「すでにパスです」と出る。**手動編集は失われる**。

- 門型との違い: `build_gate` は梁を柱の内側に収める（梁の長さ = 幅 − 断面 × 2）が、パスは梁が柱の中心線間を結ぶので角で部材どうしが重なり、梁の上端は高さより断面の半分だけ上に出る。梁の長さは 幅 − 断面（600 幅・断面 30 なら 570）
- `snap_grid` は 0 で保存される（柱の中心が 10 の倍数とは限らないため）。変換後に **編集用の点を表示** で編集できる

### 再生成と編集用の点

- **編集用の点を表示**: パストラス（直線・門型を選んだときは自動でパスに変換）の角ごとに、黄色い十字のロケータ `Truss_<名前>_P01, _P02, ...` が最上位の `Truss_<名前>_Edit` の下に出る。普通のオブジェクトなので **W キーで動かす**だけ（CV モードは使わない）。動かしている間、黄色のプレビュー線が追従する（スナップ後の形）。トラスの部材やロケータを選んでいても使える
- **選択したトラスを再生成**: ロケータの位置から作り直す（ロケータを選んだままでよい）。スナップ（グリッド / 角度）が効き、ロケータも揃った位置に移る。形は保存されるので、ロケータを消しても残る。グループ内の手動編集（部材の移動・回転・削除・追加）は失われる
- **選択した点の後ろに点を追加**: 選んだ点と次の点の中点に新しい点を足して番号を振り直す（閉じたパスは最後の点なら最初との中点）。**選択した点を削除**: 点は 2 個以上残す
- **編集用の点を消す**: `Truss_<名前>_Edit` を消す。以後は保存した点から再生成する
- 編集用の点は区画の外に置かれ、`Check` / `Export Block` の対象にならない
- 点列の優先順位: 編集用の点 → `source_curve` のカーブ → 保存した `points`。カーブ方式（`make_edit_curve` / `detach_curve`）はコードから使える

### コライダーの考え方

**部材 1 本（柱 1 本、梁 1 本）= `SC_` ノード 1 つ = Box 1 つ。** トラスは中が空洞だがゲーム上は内部に入れないので、弦・横桟・斜材は 1 メッシュに結合し、部材ごとに Box を 1 つ出す。門型は柱 2 + 梁 1 の 3 Box でコの字になる。各部材には文字列属性 `ms2026_collider_shape = "box"` が付き、`Export Block` の自動判定より優先される（`ms2026_maya_collision.py`。他の `SC_` にも使える: `box` / `sphere` / `capsule`）。

構成: `SM_Bg_<区画>/SM_Truss_<名前>/SC_Truss_<名前>`（直線）、`SC_Truss_<名前>_PostL / _PostR / _Beam`（門型）。グループが `SM_Truss_` なのは `Check` が全 transform に `SM_`/`SC_`/`UCX_` を要求するため。

コードから: `build_straight` / `build_gate` / `build_path` / `build_from_curve` / `build_preset` / `build_from_points` / `rebuild` / `make_edit_points` / `clear_edit_points` / `insert_edit_point` / `delete_edit_point` / `edit_locators` / `resolve_truss` / `make_edit_curve` / `detach_curve` / `convert_to_path` / `snap_points` / `preset_points` / `points_from_selection` / `sample_curve` / `preview_points_for` / `show_preview` / `clear_preview`。検証は `tests/verify_truss.py`（mayapy）。

## リロード

コードを更新したあと Maya を再起動せずに反映する。`ms2026_maya_*` を全部読み直し、メニューを作り直し、開いていたウィンドウ（グレーボックス / トラス生成）も開き直す。

- メニュー `Tools > MS2026 > ツールをリロード`
- グレーボックス / トラス生成の各ウィンドウの **リロード** ボタン
- T-Drive の「ツールをリロード」でも同じ処理（`GreyboxTool.refresh()` から呼ぶ）
- スクリプトエディタ（Python）用の一行: `import importlib, ms2026_maya_reload as r; importlib.reload(r); r.reload_all()`

## 関数

| 関数 | 内容 |
|---|---|
| `setup_scene()` | 単位 cm / Y 上 / 表示レイヤー作成 |
| `import_greybox(path=None)` | FBX 読み込み（追加モード・アニメなし）。区画ごとに `GB_<Block>` レイヤーへ。`path` 省略でダイアログ |
| `list_block_layers()` / `show_only(layers=None)` | 区画レイヤーの一覧 / 指定だけ表示（None で全表示） |
| `hide_all()` | 区画レイヤーをすべて非表示（`show_only([])` と同じ） |
| `convert_to_polygons(nodes=None)` | NURBS サーフェスをポリゴン化し `[(旧名, 新名)]` を返す |
| `set_greybox_transparent(on)` | GB_ レイヤーのメッシュを半透明マテリアルにする / 戻す |
| `check_selection(nodes=None)` | 命名・最上位グループの原点合わせ・履歴を検査し `[(node, msg)]` を返す |
| `export_block(path=None, top=None, force=False)` | 固定設定で FBX 書き出し。問題があると中止（`force=True` で続行）。`SC_` の簡易当たり判定を `.colliders.json` に書き、要約を `LAST_SUMMARY` に残す |
| `export_prop(top=None, path=None)` / `import_prop(path=None, parent=None)` | 小物の書き出し / 配置（`ms2026_maya_props.py`） |
| `register_prop_from_selection(collision="mesh", top=None)` | 選択を小物として登録し、元ノードを配置済みインスタンスとして残す（`ms2026_maya_register.py`）。`collision` は `"simple"` / `"mesh"` |
| `classify_node(node)` / `collect_block_colliders(top)` | 簡易当たり判定の自動判定（`ms2026_maya_collision.py`。しきい値は同ファイル先頭） |
| `collect_props(top)` / `write_props_json(top, out_path)` | 配下の小物（複製・インスタンス込み）を集める / 配置データ JSON を書く |
| `install_menu()` | メニューバーに `Tools > MS2026` を作成（GUI のみ） |
| `show_window()` | 作業ウィンドウを開く（GUI のみ） |
| `install_shelf()` | シェルフ作成（任意・GUI のみ） |

UI 実装は `ms2026_maya_ui.py`、小物は `ms2026_maya_props.py`、簡易当たり判定は `ms2026_maya_collision.py`。ツールを更新したら Maya を再起動するか `importlib.reload(t)`。

## リリース（開発者）

1. `VERSION` と `CHANGELOG.md`（`### 互換性` に JSON の版と壊す変更）を更新
2. Unity 側（MS2026 `MapExchange` の `SupportedVersion` と `Docs/Guides/MayaGreyboxPipeline.md` §0.1）を同じ日に合わせる
3. 注釈付きタグ `vX.Y.Z` を push（T-Drive の更新ウィンドウはタグだけを見る）
