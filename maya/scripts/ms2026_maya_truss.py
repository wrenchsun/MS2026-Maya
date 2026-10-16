# -*- coding: utf-8 -*-
"""ライブ会場用トラスのプロシージャル生成 (maya.cmds のみ。UI なし。mayapy standalone で動く)。
トラスの直線部材 1 本 (柱 1 本・梁 1 本) = SC_ ノード 1 つ = Box コライダー 1 つ。
部材内の弦・横桟・斜材は 1 メッシュに結合する。単位 cm / Y 上。長さ方向はローカル +X、断面は YZ。"""
import json
import math

import maya.api.OpenMaya as om
import maya.cmds as cmds

import ms2026_maya_naming as naming

TRUSS_ATTR = "ms2026_truss"  # グループに JSON (kind, name, 寸法, params) を保存
SHAPE_ATTR = "ms2026_collider_shape"

DEFAULT_PARAMS = {
    "section": 30.0,      # 断面 (正方形) の外寸
    "chord_dia": 5.0,     # 弦パイプ径
    "brace_dia": 3.0,     # 横桟・斜材径
    "seg_len": 100.0,     # セグメント長 (目安。長さを整数分割に丸める)
    "chord_div": 8,       # 弦の円周分割
    "brace_div": 6,       # 斜材・横桟の円周分割
}


def make_params(params=None):
    p = dict(DEFAULT_PARAMS)
    p.update({k: v for k, v in (params or {}).items() if k in DEFAULT_PARAMS and v is not None})
    if p["section"] <= p["chord_dia"] or p["chord_dia"] <= 0 or p["brace_dia"] <= 0 or p["seg_len"] <= 0:
        raise ValueError("トラスの寸法が不正です: {}".format(p))
    return p


def _name(base):
    return naming.sanitize(base)


def _cyl_between(p0, p1, dia, div, name):
    """p0-p1 を結ぶ円柱 (ワールド座標)。戻り値: transform。"""
    v = om.MVector(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    length = v.length()
    tr = cmds.polyCylinder(radius=dia * 0.5, height=length, subdivisionsX=div, subdivisionsY=1,
                           subdivisionsCaps=1, axis=(0, 1, 0), name=name, constructionHistory=False)[0]
    rot = om.MQuaternion(om.MVector(0, 1, 0), v.normal()).asEulerRotation()
    cmds.xform(tr, ws=True, t=[(a + b) * 0.5 for a, b in zip(p0, p1)],
               ro=[math.degrees(rot.x), math.degrees(rot.y), math.degrees(rot.z)])
    return tr


def build_member(name, length, params=None, parent=None):
    """4 本弦のボックストラス部材 1 本。ローカル +X が長さ方向、ピボットは中心。
    名前は SC_<name>。ms2026_collider_shape = "box"。戻り値: transform (long 名)。"""
    p = make_params(params)
    if length <= p["section"]:
        raise ValueError("長さ({})は断面({})より長くしてください".format(length, p["section"]))
    s, cd, bd = p["section"], p["chord_dia"], p["brace_dia"]
    h = s * 0.5 - cd * 0.5  # 弦の中心位置 (外形が section ぴったりになる)
    corners = [(-h, -h), (h, -h), (h, h), (-h, h)]  # (y, z) を周回
    n = max(1, int(round(length / p["seg_len"])))
    x0, step = -length * 0.5, length / n
    parts = []
    for i, (y, z) in enumerate(corners):
        parts.append(_cyl_between((x0, y, z), (x0 + length, y, z), cd, p["chord_div"], "tmpChord%d" % i))
    for k in range(n + 1):  # 横桟: 各ステーションで四角い輪
        x = x0 + step * k
        for i in range(4):
            (ya, za), (yb, zb) = corners[i], corners[(i + 1) % 4]
            parts.append(_cyl_between((x, ya, za), (x, yb, zb), bd, p["brace_div"], "tmpRung"))
    for k in range(n):  # 斜材: 各面・各セグメントでジグザグ
        xa, xb = x0 + step * k, x0 + step * (k + 1)
        for i in range(4):
            (ya, za), (yb, zb) = corners[i], corners[(i + 1) % 4]
            if (k + i) % 2 == 0:
                a, b = (xa, ya, za), (xb, yb, zb)
            else:
                a, b = (xa, yb, zb), (xb, ya, za)
            parts.append(_cyl_between(a, b, bd, p["brace_div"], "tmpDiag"))
    united = cmds.polyUnite(parts, constructionHistory=False, mergeUVSets=1, name="tmpMember")[0]
    cmds.delete(united, constructionHistory=True)
    leftovers = [x for x in parts if cmds.objExists(x)]
    if leftovers:
        cmds.delete(leftovers)
    cmds.xform(united, ws=True, pivots=(0, 0, 0))
    node = cmds.rename(united, "SC_" + _name(name))
    cmds.addAttr(node, longName=SHAPE_ATTR, dataType="string")
    cmds.setAttr(node + "." + SHAPE_ATTR, "box", type="string")
    if parent:
        node = cmds.parent(node, parent)[0]
    return cmds.ls(node, long=True)[0]


def _new_group(kind, name, dims, params, parent):
    gname = "SM_Truss_" + _name(name)  # check_selection は全 transform に SM_/SC_/UCX_ を要求するためグループは SM_
    grp = cmds.group(empty=True, name=gname, **({"parent": parent} if parent else {"world": True}))
    cmds.addAttr(grp, longName=TRUSS_ATTR, dataType="string")
    info = {"kind": kind, "name": _name(name)}
    info.update(dims)
    info["params"] = params
    cmds.setAttr(grp + "." + TRUSS_ATTR, json.dumps(info, ensure_ascii=False), type="string")
    return cmds.ls(grp, long=True)[0]


def _fill_straight(grp, name, length, params):
    base = "Truss_" + _name(name)
    return [build_member(base, length, params, parent=grp)]


def _fill_gate(grp, name, width, height, params):
    p = make_params(params)
    s = p["section"]
    if width <= 2 * s or height <= s:
        raise ValueError("門型の幅({})は断面の 2 倍({})より、高さ({})は断面より大きくしてください".format(width, 2 * s, height))
    base = "Truss_" + _name(name)
    out = []
    for side, sign in (("PostL", -1), ("PostR", 1)):
        post = build_member("{}_{}".format(base, side), height, p, parent=grp)
        cmds.setAttr(post + ".rotateZ", 90)
        cmds.setAttr(post + ".translate", sign * (width * 0.5 - s * 0.5), height * 0.5, 0)
        out.append(post)
    beam = build_member(base + "_Beam", width - 2 * s, p, parent=grp)
    cmds.setAttr(beam + ".translate", 0, height - s * 0.5, 0)
    out.append(beam)
    return out


def build_straight(name, length, params=None, parent=None):
    """グループ SM_Truss_<name> の下に部材 1 本 SC_Truss_<name>。戻り値: グループ (long 名)。"""
    p = make_params(params)
    grp = _new_group("straight", name, {"length": length}, p, parent)
    _fill_straight(grp, name, length, p)
    return grp


def build_gate(name, width, height, params=None, parent=None):
    """グループ SM_Truss_<name> の下に PostL / PostR / Beam の 3 部材。グループ原点は床面の中央。
    width は柱の外側どうしの幅、height は全高 (梁の上端)。戻り値: グループ (long 名)。"""
    p = make_params(params)
    grp = _new_group("gate", name, {"width": width, "height": height}, p, parent)
    _fill_gate(grp, name, width, height, p)
    return grp


def is_truss_group(node):
    return bool(node) and cmds.objExists(node) and cmds.attributeQuery(TRUSS_ATTR, node=node, exists=True)


def read_info(group):
    return json.loads(cmds.getAttr("{}.{}".format(group, TRUSS_ATTR)))


def rebuild(group, **overrides):
    """グループの ms2026_truss JSON から子を消して同じ場所に再生成する。
    overrides: length / width / height / params(dict) で寸法を差し替えられる (JSON も更新)。戻り値: グループ。"""
    if not is_truss_group(group):
        raise ValueError("トラスのグループではありません: {}".format(group))
    group = cmds.ls(group, long=True)[0]
    info = read_info(group)
    params = make_params(dict(info.get("params", {}), **(overrides.pop("params", None) or {})))
    for k in ("length", "width", "height"):
        if overrides.get(k) is not None:
            info[k] = overrides[k]
    info["params"] = params
    kids = cmds.listRelatives(group, children=True, fullPath=True, type="transform") or []
    if kids:
        cmds.delete(kids)
    if info["kind"] == "straight":
        _fill_straight(group, info["name"], info["length"], params)
    elif info["kind"] == "gate":
        _fill_gate(group, info["name"], info["width"], info["height"], params)
    else:
        raise ValueError("未知のトラス種別: {}".format(info["kind"]))
    cmds.setAttr(group + "." + TRUSS_ATTR, json.dumps(info, ensure_ascii=False), type="string")
    return group
