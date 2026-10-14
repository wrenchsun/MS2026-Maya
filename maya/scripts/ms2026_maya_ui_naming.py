# -*- coding: utf-8 -*-
"""ウィンドウの「命名」枠 (GUI 専用)。ms2026_maya_ui から呼ばれる。"""
import maya.cmds as cmds


def _n():
    import ms2026_maya_naming as n
    return n


def _sel():
    return cmds.ls(selection=True, long=True) or []


def _report(label, res, status_fn):
    d = sum(1 for old, _new in res if _n().looks_default(old))
    status_fn("{}: 改名 {} 件（既定名 {} 件を含む）".format(label, len(res), d))


def _guard(fn, status_fn):
    def run(*_):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            status_fn("エラー: {}".format(e))
            cmds.warning("[MS2026] {}".format(e))
    return run


def _prefix(prefix, status_fn):
    sel = _sel()
    if not sel:
        status_fn("命名: 先にオブジェクトを選んでください")
        return
    n = _n()
    _report(prefix, n.apply_prefix(n.expand_targets(sel), prefix), status_fn)


def _prop(collision, status_fn):
    sel = _sel()
    if not sel:
        status_fn("命名: 先にオブジェクトを選んでください")
        return
    _report("小物", _n().make_prop(sel, collision), status_fn)


def _each_top(fn, status_fn):
    sel = _sel()
    if not sel:
        status_fn("命名: 先にグループを選んでください")
        return None
    return [fn(t) for t in _n().top_level(sel)]


def _auto(status_fn):
    res = _each_top(_n().auto_fix, status_fn)
    if res is not None:
        _report("自動修正", [p for r in res for p in r], status_fn)


def _problems(status_fn):
    res = _each_top(_n().select_problems, status_fn)
    if res is not None:
        c = sum(len(r) for r in res)
        status_fn("問題のノード {} 件を選択しました".format(c) if c else "名前・履歴などの問題はありません")


def build_naming_frame(status_fn):
    """命名の枠を現在の親レイアウトに作る。"""
    def g(f):
        return _guard(f, status_fn)
    cmds.frameLayout(label="命名（選んでから押す）", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="SM_ 形どおりの当たり判定 / SC_ 簡易当たり判定(箱・球・カプセルを書き出し時に自動選択)\n"
                    "UCX_ 当たり判定のみ(描画しない)   小物: SM_Prop_ / SC_Prop_   区画: SM_Bg_<区画名>\n"
                    "迷ったら SC_(壁・床など正確さが要るものだけ SM_)。旧 NC_ は自動修正で SC_ になる\n"
                    "グループを選ぶと中身もまとめて改名(小物の中と SM_Bg_ は除く)", align="left")
    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1)
    cmds.button(label="形どおり (SM_)", command=g(lambda: _prefix("SM_", status_fn)))
    cmds.button(label="簡易当たり判定 (SC_)", command=g(lambda: _prefix("SC_", status_fn)))
    cmds.button(label="当たり判定専用 (UCX_)", command=g(lambda: _prefix("UCX_", status_fn)))
    cmds.setParent("..")
    cmds.button(label="小物にする: 形どおりの当たり判定 (SM_Prop_)", command=g(lambda: _prop("mesh", status_fn)))
    cmds.button(label="小物にする: 簡易当たり判定 (SC_Prop_)", command=g(lambda: _prop("simple", status_fn)))
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
    cmds.button(label="名前を自動修正 (選択以下)", command=g(lambda: _auto(status_fn)))
    cmds.button(label="問題のノードを選択", command=g(lambda: _problems(status_fn)))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
