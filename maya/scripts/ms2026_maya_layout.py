# -*- coding: utf-8 -*-
"""ディスプレイ・ライトの配置往復 (<Scene>.layout.json、Unity LayoutFile version 1)。

Maya はディスプレイもライトもモデリングしない。Unity が書いた仮の置き物 (DSP_<kind>__<name> / LGT_<kind>__<name>) を
動かし、必要なら新しい置き物を足して、全部のワールド行列を JSON に書き戻すだけ。
仕様: MS2026 の Docs/Guides/MayaGreyboxPipeline.md §8。standalone (mayapy) でも動く (FBX 読み込みは fbxmaya を使う)。

- 属性 (保存・再読込しても残る): ms2026_id (Unity の GlobalObjectId。無ければ付けない) / ms2026_kind / ms2026_category /
  ms2026_layout_scene (読み込んだ JSON の scene)
- 置き物と見なすのは、ms2026_kind 属性を持つ transform か、名前が DSP_<kind>__<name> / LGT_<kind>__<name> の transform
"""
import glob
import json
import os
import re

import maya.cmds as cmds

import ms2026_maya_settings as settings

SUPPORTED_VERSION = 1  # Unity 側 LayoutFile.SupportedVersion と対。上げるときは Unity を同じ日に直す
FILE_SUFFIX = ".layout.json"
ROOT_NAME = "MS2026_Layout"  # FBX 無しで作る置き物の親 (原点・回転 0・スケール 1)

DISPLAY_KINDS = ("Flat", "Curved", "Ticker", "Vision", "Signboard", "SignboardCurved")
LIGHT_KINDS = ("Beam", "Laser", "LedBar", "Strobe", "MsPoint", "MsSpot")
KIND_CATEGORY = dict([(k, "display") for k in DISPLAY_KINDS] + [(k, "light") for k in LIGHT_KINDS])
KINDS = DISPLAY_KINDS + LIGHT_KINDS
CATEGORY_PREFIX = {"display": "DSP_", "light": "LGT_"}

ATTR_ID = "ms2026_id"
ATTR_KIND = "ms2026_kind"
ATTR_CATEGORY = "ms2026_category"
ATTR_SCENE = "ms2026_layout_scene"

NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
NODE_RE = re.compile(r"^(DSP|LGT)_([A-Za-z]+)__(.+)$")
FBX_RE = re.compile(r"^Greybox_(.+)_Layout_(\d{8})$")
SCENE_RE = re.compile(r'^[^\\/:*?"<>|]+$')
FBX_TOLERANCE_CM = 0.01  # FBX のノードと JSON の行列の位置差がこれを超えたら知らせる


class LayoutError(Exception):
    """入力が契約に合わない (名前・kind・JSON など)。メッセージは複数行になりうる。"""


def _short(node):
    return node.split("|")[-1].split(":")[-1]


def _log(msg):
    print("[MS2026 layout] " + msg)


# ---------------------------------------------------------------- 名前の検証

def name_problem(name):
    """置き物の <name> が契約に合うか。問題があれば理由 (str)、無ければ None。"""
    if not isinstance(name, str) or not name:
        return "名前が空です"
    if not NAME_RE.match(name):
        return "半角英数字とアンダースコア (A-Za-z0-9_) だけにしてください: '{}'".format(name)
    if "__" in name:
        return "名前に連続したアンダースコア '__' は使えません (kind との区切り): '{}'".format(name)
    return None


def category_of(kind):
    """kind から category ('display' / 'light')。未知の kind は None。"""
    return KIND_CATEGORY.get(kind)


def node_name(kind, name):
    """FBX / Maya のノード名: DSP_<kind>__<name> / LGT_<kind>__<name>。"""
    cat = category_of(kind)
    if cat is None:
        raise LayoutError("未知の kind: '{}' ({})".format(kind, ", ".join(KINDS)))
    return "{}{}__{}".format(CATEGORY_PREFIX[cat], kind, name)


def parse_node_name(short):
    """ノード名 → (category, kind, name)。置き物の名前でなければ None。"""
    m = NODE_RE.match(short)
    if not m:
        return None
    kind = m.group(2)
    cat = category_of(kind)
    if cat is None or CATEGORY_PREFIX[cat] != m.group(1) + "_":
        return None
    return cat, kind, m.group(3)


# ---------------------------------------------------------------- 置き物ノード

def _has_attr(node, attr):
    return cmds.attributeQuery(attr, node=node, exists=True)


def _get_str(node, attr):
    if _has_attr(node, attr):
        v = cmds.getAttr(node + "." + attr)
        return v if v else None
    return None


def _set_str(node, attr, value):
    if not _has_attr(node, attr):
        cmds.addAttr(node, longName=attr, dataType="string")
    cmds.setAttr(node + "." + attr, value, type="string")


def _clear_attr(node, attr):
    if _has_attr(node, attr):
        cmds.deleteAttr(node, attribute=attr)


def _tag(node, kind, item_id=None, scene=None):
    _set_str(node, ATTR_KIND, kind)
    _set_str(node, ATTR_CATEGORY, category_of(kind))
    if item_id:
        _set_str(node, ATTR_ID, item_id)
    if scene:
        _set_str(node, ATTR_SCENE, scene)


def find_placeholders():
    """シーン中の置き物 (long name のリスト)。属性を持つか、名前が DSP_/LGT_<kind>__<name> の transform。"""
    found = []
    for n in cmds.ls(type="transform", long=True) or []:
        if _has_attr(n, ATTR_KIND) or parse_node_name(_short(n)):
            found.append(n)
    return found


def _info(node):
    """置き物ノード → 内容の dict。名前は常にノード名から読む (Maya で改名しても追従する)。"""
    short = _short(node)
    parsed = parse_node_name(short)
    attr_kind = _get_str(node, ATTR_KIND)
    return {
        "node": node,
        "short": short,
        "parsed": parsed,
        "name": parsed[2] if parsed else None,
        "kind": attr_kind or (parsed[1] if parsed else None),
        "attr_kind": attr_kind,
        "id": _get_str(node, ATTR_ID),
        "scene": _get_str(node, ATTR_SCENE),
    }


def world_matrix(node):
    return [float(v) for v in cmds.xform(node, query=True, worldSpace=True, matrix=True)]


def set_world_matrix(node, matrix):
    """JSON の 16 値をワールド行列として入れる。親が不均一スケールでもワールドは変わらない (剪断は shear に入る)。"""
    cmds.xform(node, worldSpace=True, matrix=[float(v) for v in matrix])


def current_scene():
    """置き物に記録された JSON の scene (最初に見つかった物)。無ければ None。"""
    for n in find_placeholders():
        s = _get_str(n, ATTR_SCENE)
        if s:
            return s
    return None


# ---------------------------------------------------------------- 仮の形

def _make_shape(node, kind):
    """向きが分かる仮の形 (+Z 側に円錐の目印)。ディスプレイは薄い板 100 cm、ライトは箱 50 cm。形は取り込みに影響しない。"""
    display = category_of(kind) == "display"
    if display:
        body = cmds.polyCube(width=100, height=100, depth=4, constructionHistory=False)[0]
        cone = cmds.polyCone(radius=8, height=16, axis=(0, 0, 1), constructionHistory=False)[0]
        cmds.move(0, 0, 10, cone, relative=True)
    else:
        body = cmds.polyCube(width=50, height=50, depth=50, constructionHistory=False)[0]
        cone = cmds.polyCone(radius=12, height=30, axis=(0, 0, 1), constructionHistory=False)[0]
        cmds.move(0, 0, 40, cone, relative=True)
    united = cmds.polyUnite(body, cone, constructionHistory=False)[0]
    cmds.delete(united, constructionHistory=True)
    shape = cmds.listRelatives(united, shapes=True, fullPath=True)[0]
    shape = cmds.parent(shape, node, shape=True, relative=True)[0]
    cmds.delete(united)
    shape = cmds.rename(shape, _short(node) + "Shape")
    cmds.setAttr(shape + ".overrideEnabled", 1)
    cmds.setAttr(shape + ".overrideColor", 18 if display else 17)  # 水色 / 黄色


def _root():
    if not cmds.objExists(ROOT_NAME):
        cmds.group(empty=True, name=ROOT_NAME, world=True)
    return "|" + ROOT_NAME if cmds.objExists("|" + ROOT_NAME) else cmds.ls(ROOT_NAME, long=True)[0]


def _create_node(kind, name, parent=None):
    """置き物の transform と仮の形を作る。同じ名前のノードが既にあれば別のグループの下に置いて名前を保つ。"""
    full = node_name(kind, name)
    if parent is None:
        parent = _root()
        if cmds.ls(full):  # 短い名前が重なる (Unity 側に同名がある): 名前は変えず親を分ける
            parent = cmds.group(empty=True, name="dup", parent=parent)
            parent = cmds.ls(parent, long=True)[0]
    node = cmds.createNode("transform", name=full, parent=parent)
    node = cmds.ls(node, long=True)[0]
    if _short(node) != full:
        raise LayoutError("ノード名を付けられませんでした: " + full)
    _make_shape(node, kind)
    return node


# ---------------------------------------------------------------- 読み込み

def _read_json(path):
    if not os.path.isfile(path):
        raise LayoutError("ファイルがありません: " + path)
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as e:
        raise LayoutError("JSON を読めません: {} ({})".format(path, e))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise LayoutError("layout.json の形ではありません (items がありません): " + path)
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise LayoutError("version が不正です: {!r}".format(version))
    return data


def list_layout_files(folder=None):
    """フォルダ (既定: Unity の書き出し先) の *.layout.json を新しい順に。"""
    folder = folder or settings.greybox_dir()
    files = glob.glob(os.path.join(folder, "*" + FILE_SUFFIX))
    return sorted(files, key=os.path.getmtime, reverse=True)


def find_layout_fbx(json_path, scene=None):
    """JSON と同じフォルダの Greybox_<Scene>_Layout_<日付>.fbx のうち、日付が最新のもの。無ければ None。"""
    folder = os.path.dirname(os.path.abspath(json_path))
    scene = scene or os.path.basename(json_path)[:-len(FILE_SUFFIX)]
    best = None
    for f in glob.glob(os.path.join(folder, "Greybox_*_Layout_*.fbx")):
        m = FBX_RE.match(os.path.splitext(os.path.basename(f))[0])
        if m and m.group(1) == scene and (best is None or m.group(2) >= best[0]):
            best = (m.group(2), f)
    return best[1] if best else None


def _import_fbx(path):
    """FBX を読み込み、新しく入った transform (long name) を返す。"""
    if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
        cmds.loadPlugin("fbxmaya")
    import maya.mel as mel
    before = set(cmds.ls(type="transform", long=True) or [])
    mel.eval("FBXResetImport")
    mel.eval("FBXImportMode -v add")
    mel.eval("FBXImportMergeBackNullPivots -v false")
    mel.eval("FBXImportMergeAnimationLayers -v false")
    mel.eval("FBXImportFillTimeline -v false")
    mel.eval('FBXImport -f "{}"'.format(os.path.normpath(path).replace("\\", "/")))
    return [n for n in cmds.ls(type="transform", long=True) or [] if n not in before]


def _matrix_dev_cm(a, b):
    """2 つの行列の位置 (12〜14) の最大差 cm。"""
    return max(abs(a[i] - b[i]) for i in (12, 13, 14))


def _valid_item(it, warnings):
    """JSON の 1 項目を検査して (name, kind, id, matrix) にする。使えなければ None (理由は warnings へ)。"""
    if not isinstance(it, dict):
        warnings.append("項目がオブジェクトではありません: {!r}".format(it))
        return None
    name, kind = it.get("name"), it.get("kind")
    problem = name_problem(name)
    if problem:
        warnings.append("スキップ ({}): {}".format(name, problem))
        return None
    cat = category_of(kind)
    if cat is None:
        warnings.append("スキップ ({}): 未知の kind '{}'".format(name, kind))
        return None
    if it.get("category") not in (None, cat):
        warnings.append("スキップ ({}): category '{}' は kind '{}' と合いません (期待: {})".format(name, it.get("category"), kind, cat))
        return None
    m = it.get("matrix")
    if not (isinstance(m, list) and len(m) == 16 and all(isinstance(v, (int, float)) for v in m)):
        warnings.append("スキップ ({}): matrix は 16 個の数値が必要です".format(name))
        return None
    item_id = it.get("id") or None
    return name, kind, item_id, m


def import_layout(json_path, fbx_path=None, replace=False):
    """<Scene>.layout.json を読み、置き物を JSON のワールド行列に合わせる。

    - 既存の置き物は id → 名前の順で照合して動かす。無ければ作る (fbx_path があれば FBX のノードを使い、無ければ仮の形を作る)。
    - JSON に無い置き物は消さない (unmatched に一覧を返す)。
    - fbx_path を使うとき、すでに置き物があるなら replace=True で先に全部消す (Unity で書き出し直したとき)。
    戻り値: dict(scene, updated, created, skipped, unmatched, warnings, fbx_nodes, fbx_max_dev_cm)
    """
    data = _read_json(json_path)
    scene = data.get("scene") or ""
    warnings = []
    if data["version"] > SUPPORTED_VERSION:
        warnings.append("version {} はこのツールが知っている {} より新しいです。Maya ツールを更新してください".format(
            data["version"], SUPPORTED_VERSION))
    units = data.get("units", "cm")
    if units != "cm":
        raise LayoutError("units が cm ではありません: {!r}".format(units))

    items = []
    for raw in data["items"]:
        v = _valid_item(raw, warnings)
        if v:
            items.append(v)
    skipped = len(data["items"]) - len(items)
    names = {}
    for name, _k, _i, _m in items:
        names[name] = names.get(name, 0) + 1
    dups = sorted(n for n, c in names.items() if c > 1)
    if dups:
        warnings.append("JSON に同じ名前の項目があります (id で照合): " + ", ".join(dups))

    cmds.undoInfo(openChunk=True, chunkName="MS2026 Import Layout")
    try:
        if fbx_path and replace:
            for n in find_placeholders():
                if cmds.objExists(n):
                    cmds.delete(n)
            if cmds.objExists(ROOT_NAME) and not cmds.listRelatives(ROOT_NAME, children=True):
                cmds.delete(ROOT_NAME)
        elif fbx_path and find_placeholders():
            raise LayoutError("置き物がすでにシーンにあります。FBX も読み込むなら置き換え (replace=True) を選ぶか、JSON だけ読み込んでください")

        fbx_nodes = []
        if fbx_path:
            if not os.path.isfile(fbx_path):
                raise LayoutError("FBX がありません: " + fbx_path)
            new = _import_fbx(fbx_path)
            fbx_nodes = [n for n in new if parse_node_name(_short(n))]
            if not fbx_nodes:
                warnings.append("FBX に DSP_ / LGT_ のノードがありません: " + os.path.basename(fbx_path))

        existing = [_info(n) for n in find_placeholders()]
        used = set()
        matched = {}  # item index -> info

        def claim(idx, info):
            matched[idx] = info
            used.add(info["node"])

        # 1) id が合うもの
        by_id = {}
        for info in existing:
            if info["id"]:
                by_id.setdefault(info["id"], []).append(info)
        for idx, (name, kind, item_id, _m) in enumerate(items):
            if item_id and by_id.get(item_id):
                cand = [c for c in by_id[item_id] if c["node"] not in used]
                if cand:
                    claim(idx, cand[0])
        # 2) 名前が完全一致で 1 つだけ (id が別の物のノードは別物なので除く)
        for idx, (name, kind, item_id, _m) in enumerate(items):
            if idx in matched:
                continue
            cand = [c for c in existing if c["node"] not in used and c["name"] == name
                    and (not c["id"] or c["id"] == item_id)]
            if len(cand) == 1:
                claim(idx, cand[0])
            elif len(cand) > 1:
                warnings.append("スキップ ({}): 同じ名前の置き物が Maya に {} 個あり決められません".format(name, len(cand)))
                matched[idx] = None
        # 3) FBX の取り込みで Maya が付けた末尾の数字 (DSP_Flat__A1 → A) を外して一意に合うもの
        fbx_set = set(fbx_nodes)
        for idx, (name, kind, item_id, _m) in enumerate(items):
            if idx in matched or not fbx_nodes:
                continue
            cand = [c for c in existing if c["node"] in fbx_set and c["node"] not in used and not c["id"]
                    and c["kind"] == kind and c["name"] and re.sub(r"\d+$", "", c["name"]) == name]
            if len(cand) == 1:
                claim(idx, cand[0])

        updated = created = 0
        max_dev = 0.0
        touched = set()
        for idx, (name, kind, item_id, matrix) in enumerate(items):
            if idx in matched and matched[idx] is None:
                skipped += 1
                continue
            info = matched.get(idx)
            if info is not None:
                if info["kind"] != kind or info["attr_kind"] and info["attr_kind"] != kind:
                    warnings.append("スキップ ({}): kind が食い違います (Maya: {} / JSON: {})".format(name, info["kind"], kind))
                    skipped += 1
                    continue
                node = info["node"]
                if node in fbx_set:
                    max_dev = max(max_dev, _matrix_dev_cm(world_matrix(node), matrix))
                updated += 1
            else:
                node = _create_node(kind, name)
                created += 1
            set_world_matrix(node, matrix)
            _tag(node, kind, item_id, scene)
            touched.add(node)

        # FBX のノードで JSON に対応しないもの: タグだけ付けて残す
        used_nodes = touched
        for n in fbx_nodes:
            if cmds.objExists(n) and n not in used_nodes:
                parsed = parse_node_name(_short(n))
                warnings.append("FBX にあって JSON に無い置き物: " + _short(n))
                _tag(n, parsed[1], None, scene)

        unmatched = []
        for info in [_info(n) for n in find_placeholders()]:
            if info["node"] not in used_nodes and info["node"] not in fbx_set:
                unmatched.append(info["short"])
        if unmatched:
            _log("JSON に無い置き物 (そのまま残します): " + ", ".join(sorted(unmatched)))
    finally:
        cmds.undoInfo(closeChunk=True)

    if fbx_nodes and max_dev > FBX_TOLERANCE_CM:
        warnings.append("FBX のノードと JSON の位置が最大 {:.3f} cm ずれています (JSON の値を使いました)".format(max_dev))
    for w in warnings:
        _log("警告: " + w)
    result = {"scene": scene, "updated": updated, "created": created, "skipped": skipped,
              "unmatched": sorted(unmatched), "warnings": warnings, "fbx_nodes": len(fbx_nodes),
              "fbx_max_dev_cm": max_dev}
    _log("読み込み: {} 更新 {} / 新規 {} / スキップ {} / JSON に無い {} ({})".format(
        scene, updated, created, skipped, len(unmatched), json_path))
    return result


# ---------------------------------------------------------------- 追加

def add_placeholder(kind, name, matrix=None):
    """新しい置き物を足す (id は付けない = Unity が新規作成する)。名前は [A-Za-z0-9_]+ で '__' 無し、重複不可。"""
    if category_of(kind) is None:
        raise LayoutError("未知の kind: '{}' ({})".format(kind, ", ".join(KINDS)))
    problem = name_problem(name)
    if problem:
        raise LayoutError(problem)
    taken = [i["name"] for i in (_info(n) for n in find_placeholders()) if i["name"]]
    if name in taken:
        raise LayoutError("同じ名前の置き物がすでにあります: " + name)
    cmds.undoInfo(openChunk=True, chunkName="MS2026 Add Placeholder")
    try:
        node = _create_node(kind, name)
        _tag(node, kind, None, current_scene())
        if matrix is not None:
            set_world_matrix(node, matrix)
    finally:
        cmds.undoInfo(closeChunk=True)
    _log("追加: {} ({})".format(_short(node), kind))
    return node


# ---------------------------------------------------------------- 書き出し

def collect_items():
    """全置き物 → (items, errors, warnings)。items は JSON の項目 (id は持つものだけ)。errors があれば書き出さない。"""
    items, errors, warnings = [], [], []
    infos = [_info(n) for n in find_placeholders()]
    for info in infos:
        short = info["short"]
        if not info["parsed"]:
            errors.append("名前が DSP_<kind>__<name> / LGT_<kind>__<name> の形ではありません: {}".format(short))
            continue
        cat, kind, name = info["parsed"]
        problem = name_problem(name)
        if problem:
            errors.append("{}: {}".format(short, problem))
            continue
        if info["attr_kind"] and info["attr_kind"] != kind:
            errors.append("{}: 名前の kind '{}' と属性 {} '{}' が違います".format(short, kind, ATTR_KIND, info["attr_kind"]))
            continue
        item = {}
        if info["id"]:
            item["id"] = info["id"]
        item.update({"name": name, "category": cat, "kind": kind,
                     "matrix": [round(v, 6) for v in world_matrix(info["node"])]})
        items.append(item)
    by_name = {}
    for it in items:
        by_name.setdefault(it["name"], []).append(it)
    for name, group in sorted(by_name.items()):
        if len(group) < 2:
            continue
        if all(g.get("id") for g in group):
            warnings.append("同じ名前の置き物が {} 個あります (id で照合されます): {}".format(len(group), name))
        else:
            errors.append("同じ名前の置き物が {} 個あり、id の無い物を含みます: {}".format(len(group), name))
    return items, errors, warnings


def export_layout(out_dir=None, scene=None, path=None):
    """全置き物を <Scene>.layout.json に書く (version 1 / units cm / ワールド行列)。書いたパスを返す。

    scene は引数 → 置き物に記録された値 の順。書き出し先に既存の JSON があれば、その scene の値を保つ。
    名前・kind・重複に問題があれば何も書かず LayoutError (全件を列挙)。
    """
    items, errors, warnings = collect_items()
    scene = (scene or current_scene() or "").strip()
    if path is None:
        if not scene:
            errors.append("scene 名が分かりません。JSON を読み込むか、scene 名を指定してください")
        elif not SCENE_RE.match(scene):
            errors.append("scene 名にファイル名として使えない文字があります: " + scene)
        if not errors:
            path = os.path.join(out_dir or settings.block_out_dir(), scene + FILE_SUFFIX)
    if not items and not errors:
        errors.append("書き出す置き物がありません")
    if errors:
        raise LayoutError("書き出し中止: {} 件の問題\n".format(len(errors)) + "\n".join(errors))

    file_scene = scene
    if os.path.isfile(path):
        try:
            old = _read_json(path)
            file_scene = old.get("scene") or scene  # 既存の scene の値を保つ
        except LayoutError:
            pass
    out = {"version": SUPPORTED_VERSION, "scene": file_scene or scene, "units": "cm", "items": items}
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=True, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    for w in warnings:
        _log("警告: " + w)
    _log("書き出し: {} 個 -> {}".format(len(items), path))
    export_layout.last_warnings = warnings
    return path


export_layout.last_warnings = []
