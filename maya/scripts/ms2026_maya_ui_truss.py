# -*- coding: utf-8 -*-
"""トラス生成ウィンドウ (GUI 専用)。ms2026_maya_ui のメニューから開く。"""
import maya.cmds as cmds

WINDOW = "MS2026TrussWindow"
F_NAME, F_KIND, F_LEN, F_WIDTH, F_HEIGHT = ("MS2026TrussName", "MS2026TrussKind", "MS2026TrussLength",
                                            "MS2026TrussWidth", "MS2026TrussHeight")
F_SECTION, F_CHORD, F_SEG, STATUS = "MS2026TrussSection", "MS2026TrussChord", "MS2026TrussSeg", "MS2026TrussStatus"


def _truss():
    import ms2026_maya_truss as t
    return t


def _status(msg):
    if cmds.text(STATUS, exists=True):
        cmds.text(STATUS, edit=True, label=msg)


def _guard(fn):
    def run(*_):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _status("エラー: {}".format(e))
            cmds.warning("[MS2026] {}".format(e))
    return run


def _params():
    t = _truss()
    return {"section": cmds.floatFieldGrp(F_SECTION, q=True, value1=True),
            "chord_dia": cmds.floatFieldGrp(F_CHORD, q=True, value1=True),
            "seg_len": cmds.floatFieldGrp(F_SEG, q=True, value1=True),
            "brace_dia": t.DEFAULT_PARAMS["brace_dia"]}


def _is_gate():
    return cmds.optionMenu(F_KIND, q=True, select=True) == 2


def _on_kind(*_):
    gate = _is_gate()
    cmds.floatFieldGrp(F_LEN, edit=True, enable=not gate)
    cmds.floatFieldGrp(F_WIDTH, edit=True, enable=gate)
    cmds.floatFieldGrp(F_HEIGHT, edit=True, enable=gate)


def _block_group():
    import ms2026_maya_tools as tools
    for s in cmds.ls(selection=True, long=True) or []:
        # 選択が区画の子孫でも、その最上位の SM_Bg_ を使う
        for part in s.strip("|").split("|"):
            if tools.BLOCK_RE.match(part):
                return "|" + part
    return None


def _do_create():
    parent = _block_group()
    if parent is None:
        _status("エラー: 先に SM_Bg_<区画> グループを選択してください")
        cmds.warning("[MS2026] 先に SM_Bg_<区画> グループを選択してください。")
        return
    t = _truss()
    name = cmds.textField(F_NAME, q=True, text=True).strip() or "Truss"
    if _is_gate():
        grp = t.build_gate(name, cmds.floatFieldGrp(F_WIDTH, q=True, value1=True),
                           cmds.floatFieldGrp(F_HEIGHT, q=True, value1=True), _params(), parent=parent)
    else:
        grp = t.build_straight(name, cmds.floatFieldGrp(F_LEN, q=True, value1=True), _params(), parent=parent)
    cmds.select(grp, replace=True)
    _status("生成: {}".format(grp))


def _selected_truss():
    t = _truss()
    for s in cmds.ls(selection=True, long=True) or []:
        node = s
        while node:
            if t.is_truss_group(node):
                return node
            node = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    return None


def _do_rebuild():
    grp = _selected_truss()
    if grp is None:
        _status("エラー: 再生成するトラスのグループ（または部材）を選択してください")
        cmds.warning("[MS2026] 再生成するトラスを選択してください。")
        return
    t = _truss()
    info = t.read_info(grp)
    kw = {"params": _params()}
    if info["kind"] == "gate":
        kw.update(width=cmds.floatFieldGrp(F_WIDTH, q=True, value1=True), height=cmds.floatFieldGrp(F_HEIGHT, q=True, value1=True))
    else:
        kw.update(length=cmds.floatFieldGrp(F_LEN, q=True, value1=True))
    grp = t.rebuild(grp, **kw)
    cmds.select(grp, replace=True)
    _status("再生成: {}".format(grp))


def show_window():
    """トラス生成ウィンドウを開く。GUI セッション専用。"""
    if cmds.about(batch=True):
        raise RuntimeError("show_window() needs Maya GUI (not batch/standalone).")
    t = _truss()
    d = t.DEFAULT_PARAMS
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    cmds.window(WINDOW, title="MS2026 トラス生成", widthHeight=(340, 380), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4, columnOffset=("both", 6))
    cmds.text(label="部材 1 本（柱 1 本・梁 1 本）= SC_ 1 つ = Box コライダー 1 つ\n"
                    "SM_Bg_<区画> を選んで「生成」。単位 cm", align="left")
    cmds.textFieldGrp(F_NAME, label="名前", text="Truss", columnWidth2=(110, 200))
    cmds.optionMenu(F_KIND, label="種類", changeCommand=_on_kind)
    cmds.menuItem(label="直線")
    cmds.menuItem(label="門型")
    cmds.floatFieldGrp(F_LEN, label="長さ（直線）", value1=500.0, columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_WIDTH, label="幅（門型・柱の外側）", value1=600.0, columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_HEIGHT, label="高さ（門型）", value1=400.0, columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_SECTION, label="断面サイズ", value1=d["section"], columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_CHORD, label="弦径", value1=d["chord_dia"], columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_SEG, label="セグメント長", value1=d["seg_len"], columnWidth2=(130, 80))
    cmds.button(label="生成（選択中の SM_Bg_ グループ配下）", command=_guard(_do_create))
    cmds.button(label="選択したトラスを再生成", command=_guard(_do_rebuild))
    cmds.text(STATUS, label="待機中", align="left")
    cmds.showWindow(WINDOW)
    _on_kind()
