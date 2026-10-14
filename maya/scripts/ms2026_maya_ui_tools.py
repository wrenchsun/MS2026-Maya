# -*- coding: utf-8 -*-
"""ウィンドウの表示切替ボタン・NURBS 変換ボタン (GUI 専用)。ms2026_maya_ui から呼ばれる。"""
import maya.cmds as cmds


def _t():
    import ms2026_maya_tools as t
    return t


def _guard(fn, status):
    def run(*_):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            status("エラー: {}".format(e))
            cmds.warning("[MS2026] {}".format(e))
    return run


def _ghost(on, status):
    n = _t().set_greybox_transparent(on)
    status(("グレーボックスを半透明にした: {} 個".format(n)) if on else "不透明に戻した: {} 個".format(n))


def _hide_all(status):
    _t().hide_all()
    status("すべての区画を非表示")


def _convert(status):
    fn = _t().convert_to_polygons
    res = fn()
    curves = getattr(fn, "skipped_curves", 0)
    status("変換 {} 件".format(len(res)) + ("（変換不可: カーブ {} 件）".format(curves) if curves else ""))


def build_display_buttons(status):
    """「区画の表示」枠に足すボタン(非表示・半透明)。"""
    cmds.button(label="すべて非表示", command=_guard(lambda: _hide_all(status), status))
    cmds.button(label="グレーボックスを半透明", command=_guard(lambda: _ghost(True, status), status))
    cmds.button(label="不透明に戻す", command=_guard(lambda: _ghost(False, status), status))


def _delete_history(status):
    sel = cmds.ls(selection=True, long=True)
    if not sel:
        cmds.warning("[MS2026] ヒストリを消す対象を選んでください。")
        status("ヒストリ削除: 何も選択されていません")
        return
    cmds.delete(sel, constructionHistory=True)
    status("ヒストリを削除: {} 個の選択以下".format(len(sel)))


def build_convert_button(status):
    cmds.button(label="NURBS をポリゴンに変換（選択以下）", command=_guard(lambda: _convert(status), status))
    cmds.button(label="ヒストリを削除（選択以下）", command=_guard(lambda: _delete_history(status), status))


def _register(collision, status, refresh):
    import ms2026_maya_register as reg
    name, path, _node = reg.register_prop_from_selection(collision=collision)
    refresh()
    status("小物を登録: {} → {}（そのまま配置済み）".format(name, path))


def build_register_buttons(status, refresh):
    """「4. 小物」枠の一覧の上に置く登録ボタン。"""
    cmds.button(label="選択を小物として登録（簡易当たり判定・おすすめ）",
                command=_guard(lambda: _register("simple", status, refresh), status))
    cmds.button(label="選択を小物として登録（形どおりの当たり判定）",
                command=_guard(lambda: _register("mesh", status, refresh), status))
