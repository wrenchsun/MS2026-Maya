# -*- coding: utf-8 -*-
"""ウィンドウの「5. ディスプレイ・ライト」枠 (GUI 専用)。ms2026_maya_ui から呼ばれる。実装は ms2026_maya_layout。"""
import os

import maya.cmds as cmds

import ms2026_maya_layout as layout
import ms2026_maya_settings as settings

LIST = "MS2026LayoutJsonList"
KIND_MENU = "MS2026LayoutKindMenu"
NAME_FIELD = "MS2026LayoutNameField"
SCENE_FIELD = "MS2026LayoutSceneField"
FBX_CHECK = "MS2026LayoutFbxCheck"
OUT_LABEL = "MS2026LayoutOutLabel"


def _guard(fn, status):
    def run(*_):
        try:
            fn()
        except layout.LayoutError as e:
            first = str(e).split("\n")[0]
            status("エラー: " + first)
            cmds.warning("[MS2026] " + str(e))
        except Exception as e:  # noqa: BLE001
            status("エラー: {}".format(e))
            cmds.warning("[MS2026] {}".format(e))
    return run


def refresh():
    """JSON 一覧と出力先ラベルを更新する (フォルダ設定の変更時にも呼ばれる)。"""
    if cmds.textScrollList(LIST, exists=True):
        cmds.textScrollList(LIST, edit=True, removeAll=True)
        for f in layout.list_layout_files():
            cmds.textScrollList(LIST, edit=True, append=os.path.basename(f))
    if cmds.text(OUT_LABEL, exists=True):
        cmds.text(OUT_LABEL, edit=True, label="書き出し先: " + settings.block_out_dir())


def _sync_scene_field():
    if cmds.textField(SCENE_FIELD, exists=True):
        scene = layout.current_scene()
        if scene:
            cmds.textField(SCENE_FIELD, edit=True, text=scene)


def _import(status, path=None):
    if path is None:
        names = cmds.textScrollList(LIST, query=True, selectItem=True) or []
        if not names:
            cmds.warning("[MS2026] layout.json を一覧から選んでください。")
            status("配置の読み込み: ファイルが選択されていません")
            return
        path = os.path.join(settings.greybox_dir(), names[0])
    fbx = None
    replace = False
    if cmds.checkBox(FBX_CHECK, query=True, value=True):
        fbx = layout.find_layout_fbx(path)
        if fbx is None:
            cmds.warning("[MS2026] 対応する Greybox_<Scene>_Layout_<日付>.fbx が見つかりません。JSON だけ読み込みます。")
        elif layout.find_placeholders():
            replace = cmds.confirmDialog(
                title="MS2026 配置", message="置き物がすでにあります。FBX で置き換えますか？\n（Maya で動かした分は JSON の値で上書きされます）",
                button=["置き換える", "JSON だけ読み込む"], defaultButton="置き換える", cancelButton="JSON だけ読み込む",
                dismissString="JSON だけ読み込む") == "置き換える"
            if not replace:
                fbx = None
    res = layout.import_layout(path, fbx_path=fbx, replace=replace)
    _sync_scene_field()
    msg = "配置を読み込み: {} 更新 {} / 新規 {} / スキップ {}".format(res["scene"], res["updated"], res["created"], res["skipped"])
    if res["unmatched"]:
        msg += " / JSON に無い置き物 {}".format(len(res["unmatched"]))
    if res["warnings"]:
        msg += " / 警告 {} 件（スクリプトエディタ）".format(len(res["warnings"]))
    status(msg)


def _import_dialog(status):
    res = cmds.fileDialog2(fileMode=1, caption="layout.json を選ぶ", dir=settings.greybox_dir(),
                           fileFilter="Layout (*{})".format(layout.FILE_SUFFIX))
    if res:
        _import(status, res[0])


def _add(status):
    kind = cmds.optionMenu(KIND_MENU, query=True, value=True)
    name = cmds.textField(NAME_FIELD, query=True, text=True).strip()
    matrix = None
    sel = cmds.ls(selection=True, long=True, type="transform") or []
    if sel:  # 選択中のノードの位置に置く (回転・拡縮は引き継がない)
        t = cmds.xform(sel[0], query=True, worldSpace=True, translation=True)
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1]
    node = layout.add_placeholder(kind, name, matrix=matrix)
    cmds.select(node, replace=True)
    cmds.textField(NAME_FIELD, edit=True, text="")
    status("置き物を追加: " + node.split("|")[-1])


def _export(status):
    scene = cmds.textField(SCENE_FIELD, query=True, text=True).strip() or None
    path = layout.export_layout(scene=scene)
    n_warn = len(layout.export_layout.last_warnings)
    status("配置を書き出し: {}{}".format(path, " / 警告 {} 件（スクリプトエディタ）".format(n_warn) if n_warn else ""))


def _select_all(status):
    nodes = layout.find_placeholders()
    cmds.select(nodes, replace=True) if nodes else cmds.select(clear=True)
    status("置き物を選択: {} 個".format(len(nodes)))


def build_layout_frame(status):
    cmds.frameLayout(label="5. ディスプレイ・ライト", collapsable=True, collapse=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="Unity の仮の置き物 (DSP_ / LGT_) を動かして戻す。形は作らない", align="left")
    cmds.text(label="読み込み元: フォルダ設定の「グレーボックスFBX」", align="left")
    cmds.textScrollList(LIST, allowMultiSelection=False, numberOfRows=4)
    cmds.button(label="一覧を更新", command=_guard(lambda: refresh(), status))
    cmds.checkBox(FBX_CHECK, label="対応する Layout FBX（仮の形）も読み込む", value=False)
    cmds.button(label="選択した layout.json を読み込む", command=_guard(lambda: _import(status), status))
    cmds.button(label="ファイルを選ぶ...", command=_guard(lambda: _import_dialog(status), status))
    cmds.separator(style="in", height=6)
    cmds.text(label="新しい置き物 (名前は A-Za-z0-9_ のみ。選択中のノードの位置に置く)", align="left")
    cmds.optionMenu(KIND_MENU, label="kind")
    for kind in layout.KINDS:
        cmds.menuItem(label=kind)
    cmds.textField(NAME_FIELD, placeholderText="名前 (例: Screen_01)")
    cmds.button(label="置き物を追加", command=_guard(lambda: _add(status), status))
    cmds.button(label="置き物をすべて選択", command=_guard(lambda: _select_all(status), status))
    cmds.separator(style="in", height=6)
    cmds.text(label="scene 名 (読み込むと入る。既存の JSON があればその scene を保つ)", align="left")
    cmds.textField(SCENE_FIELD, text=layout.current_scene() or "")
    cmds.button(label="配置を書き出す (全置き物 -> <Scene>.layout.json)", command=_guard(lambda: _export(status), status))
    cmds.text(OUT_LABEL, label="書き出し先: " + settings.block_out_dir(), align="left")
    cmds.setParent("..")
    cmds.setParent("..")
    refresh()
