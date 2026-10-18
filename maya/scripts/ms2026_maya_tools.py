# -*- coding: utf-8 -*-
"""MS2026 greybox -> Maya -> Unity 背景パイプライン用ツール (Maya 2026 / Python 3)。仕様: Docs/Guides/MayaGreyboxPipeline.md §2"""
import os
import re

import maya.cmds as cmds
import maya.mel as mel

import ms2026_maya_collision as collision
import ms2026_maya_layout as layout  # noqa: F401  配置往復 (layout.import_layout / export_layout / add_placeholder)
import ms2026_maya_settings as settings
from ms2026_maya_geometry import non_polygon_problems, convert_to_polygons  # noqa: F401
from ms2026_maya_ghost import set_greybox_transparent  # noqa: F401
from ms2026_maya_props import (PROP_RE, PROP_ATTR, collect_props, export_prop, export_without_props,  # noqa: F401
                               import_prop, write_props_json)

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# 既定フォルダ (実際の値は settings.get_dir で実行時に取得。ウィンドウで変更可)
EXPORT_DIR = settings.default_dir("greybox_dir")  # Unity が Greybox_*.fbx を書く場所
IMPORT_DIR = settings.default_dir("block_out_dir")  # このスクリプトが SM_Bg_*.fbx を書く場所

LAYER_REF = "GREYBOX_REF"
LAYER_ANCHORS = "GREYBOX_ANCHORS"
SOURCE_ATTR = "ms2026_greybox_source"
LAYER_PREFIX = "GB_"
NAME_RE = re.compile(r"^(SM_|UCX_|SC_)[A-Za-z0-9_]+$")  # SC_ = 簡易当たり判定(形は書き出し時に自動選択)
LEGACY_NC_RE = re.compile(r"^NC_")  # 旧「当たり判定なし」。Check で警告し、自動修正で SC_ にする
LAST_SUMMARY = ""  # 直近の export_block の簡易当たり判定の要約(UI の状態行用)
FILE_RE = re.compile(r"^Greybox_(Dev_[A-Za-z0-9]+_[A-Za-z0-9]+)_(.+)_(\d{8})$")
BLOCK_RE = re.compile(r"^SM_Bg_[A-Za-z0-9_]+$")
EPS = 1e-4


def _short(node):
    return node.split("|")[-1].split(":")[-1]


def _load_fbx_plugin():
    if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
        cmds.loadPlugin("fbxmaya")


# マップは直径約 330 m。既定の far clip (100 m) では何も映らない。
# near/far の比が大きすぎると奥行き精度が落ちて重なった面がちらつく(Z ファイティング)ので near も上げる。
NEAR_CLIP_CM = 10.0
FAR_CLIP_CM = 100000.0


def setup_scene():
    """単位 cm / Y 上 / 参照レイヤーを用意し、カメラの far clip をマップ全体が映る値にする。"""
    cmds.currentUnit(linear="cm")
    cmds.upAxis(axis="y")
    for cam in cmds.ls(type="camera") or []:
        if cmds.getAttr(cam + ".nearClipPlane") < NEAR_CLIP_CM:
            cmds.setAttr(cam + ".nearClipPlane", NEAR_CLIP_CM)
        cmds.setAttr(cam + ".farClipPlane", FAR_CLIP_CM)
    for name in (LAYER_REF, LAYER_ANCHORS):
        if not cmds.objExists(name):
            cmds.createDisplayLayer(name=name, empty=True)


def _set_layer(layer, nodes):
    """nodes をレイヤーへ入れ、Reference 表示 (displayType 2) にする。"""
    if nodes:
        cmds.editDisplayLayerMembers(layer, nodes, noRecurse=True)
    cmds.setAttr(layer + ".displayType", 2)


def block_name(key):
    """'Greybox_<Scene>_<Block>_<YYYYMMDD>' から Block を取り出す。一致しなければ key 全体。"""
    m = FILE_RE.match(key)
    return m.group(2) if m else key


def block_layer(block):
    return LAYER_PREFIX + re.sub(r"[^A-Za-z0-9_]", "_", block)


def list_block_layers():
    """表示切替の対象レイヤー [(レイヤー名, 表示名)]。GB_* と GREYBOX_ANCHORS(Anchors)。"""
    out = [(l, l[len(LAYER_PREFIX):]) for l in sorted(cmds.ls(type="displayLayer") or [])
           if l.startswith(LAYER_PREFIX)]
    if cmds.objExists(LAYER_ANCHORS):
        out.append((LAYER_ANCHORS, "Anchors"))
    return out


def show_only(layers=None):
    """layers だけ visibility=1、他の GB_/アンカーレイヤーは 0。None なら全て表示。表示した区画に視点を合わせる。"""
    shown = []
    for layer, _label in list_block_layers():
        on = layers is None or layer in layers
        cmds.setAttr(layer + ".visibility", 1 if on else 0)
        if on:
            shown += cmds.editDisplayLayerMembers(layer, q=True, fullNames=True) or []
    frame_nodes(shown)


def hide_all():
    """GB_ レイヤーと GREYBOX_ANCHORS をすべて非表示にする。"""
    show_only([])


def frame_nodes(nodes):
    """GUI なら persp を nodes に合わせる(viewFit all=True は非表示も含めてしまうので選択で合わせる)。"""
    if cmds.about(batch=True) or not nodes:
        return
    old = cmds.ls(selection=True, long=True)
    try:
        cmds.select(nodes, replace=True)
        cmds.viewFit("persp")
    finally:
        cmds.select(old, replace=True) if old else cmds.select(clear=True)


ANCHOR_LOCATOR_SIZE_CM = 300.0


def _add_anchor_locators(nodes):
    """Unity の空 GameObject は形を持たないので、見えるようにロケータ形状を足す。"""
    for n in nodes:
        if cmds.listRelatives(n, children=True) or cmds.listRelatives(n, shapes=True):
            continue
        shape = cmds.createNode("locator", parent=n, name=_short(n) + "Shape")
        for axis in "XYZ":
            cmds.setAttr("{}.localScale{}".format(shape, axis), ANCHOR_LOCATOR_SIZE_CM)


def _with_descendants(top):
    kids = cmds.listRelatives(top, allDescendents=True, fullPath=True, type="transform") or []
    return [top] + kids


def import_greybox(path=None):
    """グレーボックス FBX を読み込み、参照レイヤーへ入れる。戻り値: 取り込んだトップノード。"""
    if path is None:
        src = settings.greybox_dir()
        os.makedirs(src, exist_ok=True)
        res = cmds.fileDialog2(fileMode=1, caption="Import Greybox FBX", dir=src,
                               fileFilter="FBX (*.fbx)")
        if not res:
            return []
        path = res[0]
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        cmds.error("File not found: " + path)
    setup_scene()
    _load_fbx_plugin()
    key = os.path.splitext(os.path.basename(path))[0]
    # 冪等: 同じブロックの前回の取り込みを削除
    for node in cmds.ls(assemblies=True, long=True):
        if cmds.attributeQuery(SOURCE_ATTR, node=node, exists=True) \
                and cmds.getAttr(node + "." + SOURCE_ATTR) == key:
            cmds.delete(node)
    before = set(cmds.ls(assemblies=True, long=True))
    mel.eval("FBXResetImport")
    mel.eval("FBXImportMode -v add")
    mel.eval("FBXImportMergeBackNullPivots -v false")
    mel.eval("FBXImportMergeAnimationLayers -v false")
    mel.eval("FBXImportFillTimeline -v false")
    mel.eval('FBXImport -f "{}"'.format(path.replace("\\", "/")))
    tops = [n for n in cmds.ls(assemblies=True, long=True) if n not in before]
    block = block_name(key)
    layer = LAYER_ANCHORS if block == "Anchors" else block_layer(block)
    ref_nodes, anchor_nodes = [], []
    for top in tops:
        cmds.addAttr(top, longName=SOURCE_ATTR, dataType="string")
        cmds.setAttr(top + "." + SOURCE_ATTR, key, type="string")
        anchors = set()
        for n in _with_descendants(top):
            if _short(n) == "_Reference":
                anchors.update(_with_descendants(n))
        for n in _with_descendants(top):
            (anchor_nodes if n in anchors or layer == LAYER_ANCHORS else ref_nodes).append(n)
    if ref_nodes:
        if not cmds.objExists(layer):
            cmds.createDisplayLayer(name=layer, empty=True)
        _set_layer(layer, ref_nodes)
    _add_anchor_locators(anchor_nodes)
    _set_layer(LAYER_ANCHORS, anchor_nodes)
    frame_nodes(ref_nodes + anchor_nodes)  # 原点から遠いので読み込んだものに視点を合わせる
    print("[MS2026] Imported greybox: {} ({} ref -> {}, {} anchors)".format(path, len(ref_nodes), layer, len(anchor_nodes)))
    return tops


def check_selection(nodes=None):
    """命名・最上位グループの原点合わせ・履歴を検査。戻り値: [(node, message), ...]。"""
    if nodes is None:
        nodes = cmds.ls(selection=True, long=True)
    elif isinstance(nodes, str):
        nodes = [nodes]
    if not nodes:
        cmds.warning("Nothing selected.")
        return []
    tops = [cmds.ls(n, long=True)[0] for n in nodes]
    skip = set()  # 小物とその子は名前・履歴を検査しない(最上位に指定された小物自身は検査する)
    for tp in tops:
        for pn, _n, _c in collect_props(tp):
            if pn not in tops:
                skip.update(_with_descendants(pn))
    transforms = []
    for n in tops:
        for t in _with_descendants(n):
            if t not in transforms and t not in skip and cmds.nodeType(t) == "transform":
                transforms.append(t)
    # 位置合わせに必要なのは最上位グループが原点・無回転・等倍であることだけ。
    # 子の Transform は FBX がそのまま運ぶので自由(インスタンスで使い回す前提)。
    problems = []
    for t in transforms:
        name = _short(t)
        if LEGACY_NC_RE.match(name):
            problems.append((t, "Obsolete prefix NC_ in '{}' (now SC_ = simple collision; use 名前を自動修正)".format(name)))
        elif not NAME_RE.match(name):
            problems.append((t, "Bad name '{}' (use SM_/SC_/UCX_ + A-Za-z0-9_ only)".format(name)))
        if t in tops:
            for attr, ident in (("translate", 0.0), ("rotate", 0.0), ("scale", 1.0)):
                vals = cmds.getAttr("{}.{}".format(t, attr))[0]
                if any(abs(v - ident) > EPS for v in vals):
                    problems.append((t, "Top group not at identity: {} = {}".format(attr, tuple(round(v, 4) for v in vals))))
            for flag in ("rotatePivot", "scalePivot"):
                piv = cmds.xform(t, q=True, ws=True, **{flag: True})
                if any(abs(v) > EPS for v in piv):
                    problems.append((t, "Top group pivot not at origin: {} = {}".format(flag, tuple(round(v, 4) for v in piv))))
        problems.extend(non_polygon_problems(t))
        for shape in cmds.listRelatives(t, shapes=True, fullPath=True, type="mesh") or []:
            hist = cmds.listHistory(shape, pruneDagObjects=True) or []
            hist = [h for h in hist if cmds.nodeType(h) not in
                    ("shadingEngine", "groupId", "groupParts", "materialInfo")]
            if hist:
                problems.append((t, "Construction history remains: {}".format(", ".join(hist[:3]))))
    for node, msg in problems:
        print("[MS2026 check] {}: {}".format(node, msg))
    if not problems:
        print("[MS2026 check] OK ({} transforms)".format(len(transforms)))
    return problems


def export_block(path=None, top=None, force=False):
    """選択中の SM_Bg_<Block> グループを固定設定で FBX 書き出し。戻り値: 出力パス or None。"""
    if top is None:
        sel = cmds.ls(selection=True, long=True)
        if len(sel) != 1:
            cmds.warning("Select exactly one top-level SM_Bg_<Block> group.")
            return None
        top = sel[0]
    top = cmds.ls(top, long=True)[0]
    if cmds.listRelatives(top, parent=True):
        cmds.warning("'{}' is not a top-level node.".format(top))
        return None
    name = _short(top)
    if not BLOCK_RE.match(name):
        cmds.warning("Group name must be SM_Bg_<Block>: '{}'".format(name))
        return None
    problems = check_selection([top])
    if problems and not force:
        cmds.warning("Export aborted: {} problem(s). Fix them or use force=True.".format(len(problems)))
        return None
    if path is None:
        path = os.path.join(settings.block_out_dir(), name + ".fbx")
    path = os.path.normpath(path)
    json_path = os.path.splitext(path)[0] + ".props.json"
    props = collect_props(top)
    if props:
        write_props_json(top, json_path)
        print("[MS2026] Exported props: {} ({} items)".format(json_path, len(props)))
    elif os.path.isfile(json_path):
        os.remove(json_path)  # 古い配置データを残さない
    _export_simple_colliders(top, path, props)
    export_without_props(top, path, [pn for pn, _n, _c in props])
    print("[MS2026] Exported: " + path)
    return path


def _export_simple_colliders(top, fbx_path, props):
    """SC_ メッシュの簡易当たり判定を自動で決めて <区画>.colliders.json に書く(小物の中は除く)。"""
    global LAST_SUMMARY
    skip = set()
    for pn, _n, _c in props:
        skip.update(_with_descendants(pn))
    entries = collision.collect_block_colliders(top, skip)
    json_path = os.path.splitext(fbx_path)[0] + ".colliders.json"
    if entries:
        collision.write_colliders_json(top, entries, json_path)
        for e in entries:
            print("[MS2026 collision] {} -> {}".format(e["path"], e["shape"]))
        LAST_SUMMARY = "簡易当たり判定 {} 件 ({})".format(len(entries), collision.summary(entries))
        print("[MS2026] Exported colliders: {} ({})".format(json_path, LAST_SUMMARY))
    else:
        LAST_SUMMARY = "簡易当たり判定なし"
        if os.path.isfile(json_path):
            os.remove(json_path)  # 古い当たり判定データを残さない


def install_shelf():
    """シェルフタブ MS2026 を (再)作成する。GUI セッション専用。"""
    if cmds.about(batch=True):
        raise RuntimeError("install_shelf() needs Maya GUI (not batch/standalone).")
    name = "MS2026"
    top = mel.eval("$tmp = $gShelfTopLevel")
    if cmds.shelfLayout(name, exists=True):
        cmds.deleteUI(name)
    cmds.shelfLayout(name, parent=top)
    for label, fn in (("Setup", "setup_scene"), ("Import Greybox", "import_greybox"),
                      ("Check", "check_selection"), ("Export Block", "export_block"),
                      ("Window", "show_window")):
        cmds.shelfButton(parent=name, label=label, annotation=label, imageOverlayLabel=label[:6],
                         style="textOnly", sourceType="python",
                         command="import importlib, ms2026_maya_tools as t; importlib.reload(t); t.{}()".format(fn))
    cmds.tabLayout(top, edit=True, selectTab=name)


def manual_path():
    """HTML マニュアル (docs/manual.html) の絶対パス。"""
    return os.path.join(REPO_ROOT, "docs", "manual.html")


def open_manual():
    """HTML マニュアルを既定のブラウザで開く。無ければ RuntimeError。"""
    path = manual_path()
    if not os.path.isfile(path):
        raise RuntimeError("マニュアルが見つかりません: " + path)
    url = "file:///" + path.replace("\\", "/")
    try:
        cmds.launch(webPage=url)
    except Exception:  # noqa: BLE001  standalone など launch が使えない環境
        import webbrowser
        webbrowser.open(url)
    return path


def install_menu():
    """トップメニュー MS2026 を作成する (実装は ms2026_maya_ui)。GUI 専用。"""
    import importlib
    import ms2026_maya_ui as ui
    importlib.reload(ui)
    ui.install_menu()


def show_window():
    """グレーボックス作業ウィンドウを開く (実装は ms2026_maya_ui)。GUI 専用。"""
    import importlib
    import ms2026_maya_ui as ui
    importlib.reload(ui)
    ui.show_window()
