# -*- coding: utf-8 -*-
"""トラス生成ウィンドウの入力値プリセット (maya.cmds の optionVar だけ使う。mayapy standalone でも動く)。
保存先は optionVar ms2026_truss_presets (JSON 文字列 1 本。{名前: 値の dict})。
値は UI の全入力: kind (straight/gate/path/preset/points/arc/tower)、length / width / height、section / chord_dia /
seg_len / brace_dia / chord_div / brace_div / brace_pattern / corner_block、snap_angle (None=自動 / 0 / 45 / 90) /
snap_grid、plane (XY/XZ)、shape (line/L/U/rect)、radius / arc_angle / member_len、closed。"""
import copy
import json

import maya.cmds as cmds

OPT_PRESETS = "ms2026_truss_presets"

_BASE = {
    "kind": "gate", "length": 500.0, "width": 600.0, "height": 400.0,
    "section": 30.0, "chord_dia": 5.0, "seg_len": 100.0, "brace_dia": 3.0,
    "chord_div": 8, "brace_div": 6, "brace_pattern": "zigzag", "corner_block": True,
    "snap_angle": None, "snap_grid": 10.0, "plane": "XY", "shape": "U",
    "radius": 300.0, "arc_angle": 360.0, "member_len": 200.0, "closed": False,
}


def _builtin(**kw):
    d = copy.deepcopy(_BASE)
    d.update(kw)
    return d


# 削除できない組み込み (list_presets の先頭に、この順で並ぶ)
BUILTIN = {
    "標準 30cm 門型": _builtin(kind="gate", width=600.0, height=400.0),
    "大型 50cm 門型（幅 1000 高さ 600）": _builtin(kind="gate", width=1000.0, height=600.0, section=50.0,
                                           chord_dia=8.0, brace_dia=4.0, seg_len=150.0),
    "円形リング R300": _builtin(kind="arc", plane="XZ", radius=300.0, arc_angle=360.0, member_len=200.0,
                           snap_angle=0),
    "塔 400": _builtin(kind="tower", width=100.0, height=400.0),
}


def is_builtin(name):
    return name in BUILTIN


def _load_all():
    """ユーザープリセットの dict。壊れた JSON は空として扱う。"""
    if not cmds.optionVar(exists=OPT_PRESETS):
        return {}
    try:
        data = json.loads(cmds.optionVar(q=OPT_PRESETS))
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _store(data):
    cmds.optionVar(stringValue=(OPT_PRESETS, json.dumps(data, ensure_ascii=False)))


def list_presets():
    """組み込み (固定順) の後にユーザープリセット (名前順) を並べた名前のリスト。"""
    user = sorted(n for n in _load_all() if n not in BUILTIN)
    return list(BUILTIN) + user


def save_preset(name, values):
    """name で保存 (既存なら上書き)。name が空、または組み込みと同名なら ValueError。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("プリセット名を入力してください")
    if name in BUILTIN:
        raise ValueError("組み込みプリセットと同じ名前では保存できません: {}".format(name))
    if not isinstance(values, dict):
        raise ValueError("values は dict にしてください")
    data = _load_all()
    data[name] = copy.deepcopy(values)
    _store(data)
    return name


def load_preset(name):
    """値の dict (コピー)。無ければ KeyError。"""
    if name in BUILTIN:
        return copy.deepcopy(BUILTIN[name])
    data = _load_all()
    if name not in data:
        raise KeyError("プリセットがありません: {}".format(name))
    return copy.deepcopy(data[name])


def delete_preset(name):
    """ユーザープリセットを削除。組み込みは ValueError、無ければ KeyError。"""
    if name in BUILTIN:
        raise ValueError("組み込みプリセットは削除できません")
    data = _load_all()
    if name not in data:
        raise KeyError("プリセットがありません: {}".format(name))
    del data[name]
    _store(data)
