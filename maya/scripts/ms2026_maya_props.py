# -*- coding: utf-8 -*-
"""MS2026 小物(Prop)の書き出し・配置・配置データ(JSON)。ms2026_maya_tools から再公開される。"""
import json
import os
import re

import maya.cmds as cmds
import maya.mel as mel

import ms2026_maya_settings as settings

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PROPS_DIR = settings.default_dir("props_dir")  # 既定。実際は settings.props_dir()
PROP_RE = re.compile(r"^(SM|SC|NC)_Prop_([A-Za-z0-9_]+)$")  # SM = 形どおり(MeshCollider) / SC = 簡易 / NC = 旧名(簡易扱い)
PROP_ATTR = "ms2026_prop"
COLLIDER_ATTR = "ms2026_prop_collider"  # "mesh" / "simple"(旧データの "1" / "0" も読める)
BLOCK_RE = re.compile(r"^SM_Bg_[A-Za-z0-9_]+$")
COLLISION_MESH, COLLISION_SIMPLE = "mesh", "simple"


def collision_mode(value):
    """True / "1" / "mesh" → mesh、それ以外 → simple。UI の bool と属性の文字列を同じ扱いにする。"""
    if value is True or value in (COLLISION_MESH, "1"):
        return COLLISION_MESH
    return COLLISION_SIMPLE


def prop_prefix(mode):
    return "SM_Prop_" if collision_mode(mode) == COLLISION_MESH else "SC_Prop_"

_EXPORT_SETTINGS = (
    "FBXExportSmoothingGroups -v true", "FBXExportTriangulate -v true",
    "FBXExportEmbeddedTextures -v false", "FBXExportInputConnections -v false",
    "FBXExportInAscii -v false", "FBXExportUpAxis y", "FBXExportScaleFactor 1",
    "FBXExportAnimationOnly -v false", "FBXExportBakeComplexAnimation -v false",
    "FBXExportCameras -v false", "FBXExportLights -v false", "FBXExportSkins -v false",
    "FBXExportShapes -v false", "FBXExportConstraints -v false",
)


def _short(node):
    return node.split("|")[-1].split(":")[-1]


def _load_fbx_plugin():
    if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
        cmds.loadPlugin("fbxmaya")


def fbx_export(path):
    """現在の選択を固定設定で FBX 書き出し(区画・小物共通)。"""
    path = os.path.normpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _load_fbx_plugin()
    mel.eval("FBXResetExport")
    for cmd in _EXPORT_SETTINGS:
        if mel.eval('exists "{}"'.format(cmd.split()[0])):  # 無い設定は読み飛ばす
            mel.eval(cmd)
        else:
            cmds.warning("FBX setting not available: " + cmd)
    mel.eval('FBXExport -f "{}" -s'.format(path.replace("\\", "/")))


def _collider_of(node):
    """名前の接頭辞から当たり判定の種類 ("mesh" / "simple")。"""
    m = PROP_RE.match(_short(node))
    return COLLISION_MESH if (m and m.group(1) == "SM") else COLLISION_SIMPLE


def _shape_ids(node):
    shapes = cmds.listRelatives(node, allDescendents=True, fullPath=True, type="mesh") or []
    shapes += cmds.listRelatives(node, shapes=True, fullPath=True, type="mesh") or []
    return frozenset(cmds.ls(shapes, uuid=True)) if shapes else frozenset()


def _has_attr(node):
    return cmds.attributeQuery(PROP_ATTR, node=node, exists=True)


def _info_from_attr(node):
    name = cmds.getAttr(node + "." + PROP_ATTR)
    if cmds.attributeQuery(COLLIDER_ATTR, node=node, exists=True):
        return name, collision_mode(cmds.getAttr(node + "." + COLLIDER_ATTR))
    return name, _collider_of(node)


def _signatures():
    """シーン中の ms2026_prop ノードの形状 uuid 集合 -> (name, collider)。インスタンス検出用。"""
    sigs = {}
    for t in cmds.ls(type="transform", long=True) or []:
        if _has_attr(t):
            ids = _shape_ids(t)
            if ids:
                sigs.setdefault(ids, _info_from_attr(t))
    return sigs


def _has_tagged_descendant(node):
    for d in cmds.listRelatives(node, allDescendents=True, fullPath=True, type="transform") or []:
        if _has_attr(d):
            return True
    return False


def collect_props(top):
    """top 配下(top 含む)の小物ノード [(node, name, collision)]。collision は "mesh" / "simple"。
    属性を持つノード(複製) か、形状を共有するノード(インスタンス)。小物の中は辿らない。"""
    top = cmds.ls(top, long=True)[0]
    sigs = _signatures()
    found = []

    def walk(node):
        if _has_attr(node):
            name, col = _info_from_attr(node)
            found.append((node, name, col))
            return
        ids = _shape_ids(node)
        # 形状の一致だけで判定すると「小物しか入っていない区画グループ」も小物に見えるので、
        # 区画グループと、属性付きの小物を子孫に持つノードは除外する(インスタンスは属性を持たない)。
        if ids and ids in sigs and not _short(node).startswith("SM_Bg_") and not _has_tagged_descendant(node):
            name, col = sigs[ids]
            found.append((node, name, col))
            return
        for c in cmds.listRelatives(node, children=True, fullPath=True, type="transform") or []:
            walk(c)

    walk(top)
    return found


def write_props_json(top, out_path):
    """配置データ JSON を書く。戻り値: 小物の数。"""
    import ms2026_maya_collision as collision
    top = cmds.ls(top, long=True)[0]
    block = _short(top)[len("SM_Bg_"):]
    props = []
    for node, n, c in collect_props(top):
        entry = {"name": n, "collision": c, "collider": c == COLLISION_MESH,
                 "matrix": [float(v) for v in cmds.xform(node, q=True, ws=True, matrix=True)]}
        if c == COLLISION_SIMPLE:
            # 簡易当たり判定は小物 1 個につき 1 つ。小物ノードのローカル空間で形を自動で決める。
            entry["simple"] = collision.classify_node(node)
        props.append(entry)
    data = {"version": 2, "block": block, "units": "cm", "props": props}
    os.makedirs(os.path.dirname(os.path.normpath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(props)


def export_without_props(top, path, prop_nodes):
    """prop_nodes を一時的に区画の外へ退避して top を書き出す(FBX は選択ノードの子を必ず含めるため)。"""
    saved = [(cmds.ls(n, uuid=True)[0], _short(n), cmds.listRelatives(n, parent=True, fullPath=True)[0])
             for n in prop_nodes]
    old_sel = cmds.ls(selection=True, long=True)
    tmp = cmds.group(empty=True, name="MS2026_TMP_PROPS", world=True)
    try:
        for uid, _n, _p in saved:
            cmds.parent(cmds.ls(uid, long=True)[0], tmp)
        cmds.select(cmds.ls(top, long=True)[0], hierarchy=True)
        fbx_export(path)
    finally:
        for uid, short, parent in saved:
            node = cmds.parent(cmds.ls(uid, long=True)[0], parent)[0]
            cmds.rename(node, short)
        cmds.delete(tmp)
        cmds.select(old_sel, replace=True) if old_sel else cmds.select(clear=True)


def export_prop(top=None, path=None):
    """選択した SM_Prop_<Name> / SC_Prop_<Name> を 小物フォルダ/Prop_<Name>.fbx へ書き出す。"""
    import ms2026_maya_tools as tools
    if top is None:
        sel = cmds.ls(selection=True, long=True)
        if len(sel) != 1:
            cmds.warning("Select exactly one SM_Prop_<Name> / SC_Prop_<Name>.")
            return None
        top = sel[0]
    top = cmds.ls(top, long=True)[0]
    if cmds.listRelatives(top, parent=True):
        cmds.warning("'{}' is not a top-level node.".format(top))
        return None
    m = PROP_RE.match(_short(top))
    if not m or m.group(1) == "NC":
        cmds.warning("Name must be SM_Prop_<Name> or SC_Prop_<Name>: '{}'".format(_short(top)))
        return None
    problems = tools.check_selection([top])
    if problems:
        cmds.warning("Export aborted: {} problem(s).".format(len(problems)))
        return None
    if path is None:
        path = os.path.join(settings.props_dir(), "Prop_{}.fbx".format(m.group(2)))
    path = os.path.normpath(path)
    old_sel = cmds.ls(selection=True, long=True)
    cmds.select(top, hierarchy=True)
    try:
        fbx_export(path)
    finally:
        cmds.select(old_sel, replace=True) if old_sel else cmds.select(clear=True)
    print("[MS2026] Exported prop: " + path)
    return path


def import_prop(path=None, parent=None):
    """小物 FBX を追加読み込みし ms2026_prop を付ける。同じ小物を何度読んでも前の分は消さない。
    増やすときは Ctrl+D(複製) でもインスタンスでもよい(collect_props が両方拾う)。"""
    if path is None:
        src = settings.props_dir()
        os.makedirs(src, exist_ok=True)
        res = cmds.fileDialog2(fileMode=1, caption="Import Prop FBX", dir=src, fileFilter="FBX (*.fbx)")
        if not res:
            return None
        path = res[0]
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        cmds.error("File not found: " + path)
    if parent is None:
        for s in cmds.ls(selection=True, long=True) or []:
            if BLOCK_RE.match(_short(s)):
                parent = s
                break
    _load_fbx_plugin()
    before = set(cmds.ls(assemblies=True, long=True))
    mel.eval("FBXResetImport")
    mel.eval("FBXImportMode -v add")
    mel.eval("FBXImportMergeBackNullPivots -v false")
    mel.eval("FBXImportMergeAnimationLayers -v false")
    mel.eval("FBXImportFillTimeline -v false")
    mel.eval('FBXImport -f "{}"'.format(path.replace("\\", "/")))
    tops = [n for n in cmds.ls(assemblies=True, long=True) if n not in before]
    base = os.path.splitext(os.path.basename(path))[0]
    name = base[len("Prop_"):] if base.startswith("Prop_") else base
    result = None
    for top in tops:
        for attr, val in ((PROP_ATTR, name), (COLLIDER_ATTR, _collider_of(top))):
            if not cmds.attributeQuery(attr, node=top, exists=True):
                cmds.addAttr(top, longName=attr, dataType="string")
            cmds.setAttr(top + "." + attr, val, type="string")
        if parent:
            top = cmds.ls(cmds.parent(top, parent)[0], long=True)[0]
        result = result or top
    print("[MS2026] Imported prop: {} -> {}".format(path, result))
    return result
