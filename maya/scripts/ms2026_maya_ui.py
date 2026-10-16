# -*- coding: utf-8 -*-
"""MS2026 Maya ツールのメニューとウィンドウ (GUI 専用)。ms2026_maya_tools から呼ばれる。"""
import glob
import os

import maya.cmds as cmds
import maya.mel as mel

import ms2026_maya_settings as settings

MENU = "MS2026Menu"
TOOLS_MENU = "MS2026ToolsMenu"
WINDOW = "MS2026GreyboxWindow"
STATUS = "MS2026StatusText"
LIST = "MS2026FbxList"
BLOCKS = "MS2026BlockList"
PROPS = "MS2026PropList"
OUT_LABEL = "MS2026OutDirLabel"
PROP_LABEL = "MS2026PropDirLabel"
RELOAD = "import importlib, ms2026_maya_tools as t; importlib.reload(t); "


RELOAD_ALL = "import importlib, ms2026_maya_reload as r; importlib.reload(r); r.reload_all()"


def _reload_deferred():
    """リロードで自分のウィンドウが消えるので、コールバックを抜けてから実行する。"""
    cmds.evalDeferred(RELOAD_ALL)


def _t():
    import ms2026_maya_tools as t
    return t


def _require_gui(name):
    if cmds.about(batch=True):
        raise RuntimeError(name + "() needs Maya GUI (not batch/standalone).")


def _find_tools_menu(main):
    """既存の Tools メニュー (自作 or 他者作) を探す。無ければ None。"""
    if cmds.menu(TOOLS_MENU, exists=True):
        return TOOLS_MENU
    for m in cmds.window(main, query=True, menuArray=True) or []:
        if cmds.menu(m, query=True, label=True) == "Tools":
            return m
    return None


def install_menu():
    """メインメニュー Tools > MS2026 を (再)作成する。GUI セッション専用。"""
    _require_gui("install_menu")
    main = mel.eval("$tmp = $gMainWindow")
    if cmds.menuItem(MENU, exists=True):
        cmds.deleteUI(MENU)
    tools = _find_tools_menu(main)
    if tools is None:
        tools = cmds.menu(TOOLS_MENU, label="Tools", parent=main, tearOff=False)
    cmds.setParent(tools, menu=True)
    cmds.menuItem(MENU, label="MS2026", subMenu=True, tearOff=False)
    cmds.menuItem(label="グレーボックス...", command=RELOAD + "t.show_window()")
    cmds.menuItem(label="フォルダ設定...", command=RELOAD + "t.show_window()")
    cmds.menuItem(label="トラス生成...",
                  command=RELOAD + "import ms2026_maya_truss, ms2026_maya_ui_truss as u; "
                                   "importlib.reload(ms2026_maya_truss); importlib.reload(u); u.show_window()")
    cmds.menuItem(divider=True)
    cmds.menuItem(label="シェルフを作成", command=RELOAD + "t.install_shelf()")
    cmds.menuItem(divider=True)
    cmds.menuItem(label="ツールをリロード", command=RELOAD_ALL)
    cmds.setParent("..", menu=True)


def _status(msg):
    if cmds.text(STATUS, exists=True):
        cmds.text(STATUS, edit=True, label=msg)


def _guard(fn):
    """ボタン処理の例外をステータス表示と warning にする。"""
    def run(*_):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _status("エラー: {}".format(e))
            cmds.warning("[MS2026] {}".format(e))
    return run


def _fbx_files():
    files = glob.glob(os.path.join(settings.greybox_dir(), "*.fbx"))
    return sorted(files, key=os.path.getmtime, reverse=True)


def _refresh():
    cmds.textScrollList(LIST, edit=True, removeAll=True)
    for f in _fbx_files():
        cmds.textScrollList(LIST, edit=True, append=os.path.basename(f))
    _status("一覧を更新: {} ファイル".format(len(_fbx_files())))


def _refresh_blocks():
    if not cmds.textScrollList(BLOCKS, exists=True):
        return
    cmds.textScrollList(BLOCKS, edit=True, removeAll=True)
    for _layer, label in _t().list_block_layers():
        cmds.textScrollList(BLOCKS, edit=True, append=label)


def _do_show_selected():
    labels = cmds.textScrollList(BLOCKS, query=True, selectItem=True) or []
    if not labels:
        cmds.warning("[MS2026] 表示する区画を一覧から選んでください。")
        _status("区画の表示: 区画が選択されていません")
        return
    _t().show_only([l for l, lab in _t().list_block_layers() if lab in labels])
    _status("表示: " + ", ".join(labels))


def _do_show_all():
    _t().show_only(None)
    _status("すべての区画を表示")


def _do_refresh_blocks():
    _refresh_blocks()
    _status("区画一覧を更新: {} 件".format(len(_t().list_block_layers())))


def _do_create_work_group():
    """選択した区画ごとに背景の作業グループ SM_Bg_<区画名> を(無ければ)作って選択する。"""
    labels = [l for l in (cmds.textScrollList(BLOCKS, query=True, selectItem=True) or []) if l != "Anchors"]
    if not labels:
        cmds.warning("[MS2026] 区画を一覧から選んでください(Anchors は対象外)。")
        _status("作業グループ: 区画が選択されていません")
        return
    made, existed = [], []
    for label in labels:
        name = "SM_Bg_" + label
        if cmds.objExists(name):
            existed.append(name)
        else:
            cmds.group(empty=True, name=name, world=True)
            made.append(name)
    cmds.select(made + existed, replace=True)
    _status("作業グループ: 作成 {} / 既存 {}".format(", ".join(made) or "なし", ", ".join(existed) or "なし"))


def _do_setup():
    _t().setup_scene()
    _status("Setup 完了")


def _do_import_selected():
    names = cmds.textScrollList(LIST, query=True, selectItem=True) or []
    if not names:
        cmds.warning("[MS2026] FBX を一覧から選んでください。")
        _status("読み込み: FBX が選択されていません")
        return
    for n in names:
        _t().import_greybox(os.path.join(settings.greybox_dir(), n))
    _refresh_blocks()
    _status("読み込み: {} ファイル".format(len(names)))


def _do_import_dialog():
    tops = _t().import_greybox()
    _refresh_blocks()
    _status("読み込み: {} グループ".format(len(tops)) if tops else "読み込み: キャンセル")


def _do_check():
    problems = _t().check_selection()
    _status("Check: 問題 {} 件（スクリプトエディタ参照）".format(len(problems)))


def _do_export():
    t = _t()
    path = t.export_block()
    if path:
        _status("書き出し: {}  {}".format(path, t.LAST_SUMMARY))
    else:
        n = len(t.check_selection())
        _status("書き出し中止: 問題 {} 件".format(n) if n else "書き出し中止: 選択を確認（スクリプトエディタ参照）")


def _pdir():
    return settings.props_dir()


def _prop_files():
    files = glob.glob(os.path.join(_pdir(), "*.fbx"))
    return sorted(files, key=os.path.getmtime, reverse=True)


def _do_refresh_props():
    if not cmds.textScrollList(PROPS, exists=True):
        return
    cmds.textScrollList(PROPS, edit=True, removeAll=True)
    files = _prop_files()
    for f in files:
        cmds.textScrollList(PROPS, edit=True, append=os.path.basename(f))
    _status("小物一覧を更新: {} 件".format(len(files)))


def _do_place_props():
    names = cmds.textScrollList(PROPS, query=True, selectItem=True) or []
    if not names:
        cmds.warning("[MS2026] 小物を一覧から選んでください。")
        _status("小物の配置: 小物が選択されていません")
        return
    parent = next((s for s in cmds.ls(selection=True, long=True) or [] if _t().BLOCK_RE.match(s.split("|")[-1])), None)
    for n in names:
        _t().import_prop(os.path.join(_pdir(), n), parent=parent)
    _status("小物を配置: {} 件".format(len(names)))


def _do_export_prop():
    path = _t().export_prop()
    if path:
        _do_refresh_props()
        _status("小物を書き出し: " + path)
    else:
        _status("小物の書き出し中止: 選択と名前を確認（スクリプトエディタ参照）")


def _on_dirs_changed():
    """フォルダ設定が変わったら一覧を作り直す。"""
    if cmds.text(OUT_LABEL, exists=True):
        cmds.text(OUT_LABEL, edit=True, label="出力先: " + settings.block_out_dir())
    if cmds.text(PROP_LABEL, exists=True):
        cmds.text(PROP_LABEL, edit=True, label="保存先: " + _pdir())
    _refresh()
    _do_refresh_props()


def show_window():
    """グレーボックス作業ウィンドウを開く。GUI セッション専用。"""
    _require_gui("show_window")
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    cmds.window(WINDOW, title="MS2026 グレーボックス", widthHeight=(380, 700), sizeable=True)
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
    import ms2026_maya_ui_settings
    import ms2026_maya_ui_tools
    ms2026_maya_ui_settings.build_folder_frame(_status, _on_dirs_changed)
    cmds.frameLayout(label="1. 準備", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="単位 cm / Y 上 / 参照レイヤーを作る", align="left")
    cmds.button(label="Setup", command=_guard(_do_setup))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.frameLayout(label="2. グレーボックス読み込み", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.textScrollList(LIST, allowMultiSelection=True, numberOfRows=6)
    cmds.button(label="更新", command=_guard(_refresh))
    cmds.button(label="選択したFBXを読み込む", command=_guard(_do_import_selected))
    cmds.button(label="ファイルを選ぶ...", command=_guard(_do_import_dialog))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.frameLayout(label="区画の表示", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.textScrollList(BLOCKS, allowMultiSelection=True, numberOfRows=6)
    cmds.button(label="選択だけ表示", command=_guard(_do_show_selected))
    cmds.button(label="すべて表示", command=_guard(_do_show_all))
    ms2026_maya_ui_tools.build_display_buttons(_status)
    cmds.button(label="一覧を更新", command=_guard(_do_refresh_blocks))
    cmds.button(label="選択した区画の作業グループ SM_Bg_ を作る", command=_guard(_do_create_work_group))
    cmds.setParent("..")
    cmds.setParent("..")
    import ms2026_maya_ui_naming
    ms2026_maya_ui_naming.build_naming_frame(_status)
    cmds.frameLayout(label="3. 検査と書き出し", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="最上位グループ SM_Bg_<区画名> を選択してから", align="left")
    ms2026_maya_ui_tools.build_convert_button(_status)
    cmds.button(label="Check", command=_guard(_do_check))
    cmds.button(label="Export Block", command=_guard(_do_export))
    cmds.text(OUT_LABEL, label="出力先: " + settings.block_out_dir(), align="left")
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.frameLayout(label="4. 小物", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="SC_Prop_<名前>(簡易当たり判定・自動) / SM_Prop_<名前>(形どおり)", align="left")
    ms2026_maya_ui_tools.build_register_buttons(_status, _do_refresh_props)
    cmds.textScrollList(PROPS, allowMultiSelection=True, numberOfRows=5)
    cmds.button(label="一覧を更新", command=_guard(_do_refresh_props))
    cmds.button(label="選択した小物を配置", command=_guard(_do_place_props))
    cmds.button(label="選択を小物として書き出す", command=_guard(_do_export_prop))
    cmds.text(PROP_LABEL, label="保存先: " + _pdir(), align="left")
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.button(label="リロード", command=_guard(_reload_deferred))
    cmds.text(STATUS, label="待機中", align="left")
    cmds.showWindow(WINDOW)
    _refresh()
    _refresh_blocks()
    _do_refresh_props()
