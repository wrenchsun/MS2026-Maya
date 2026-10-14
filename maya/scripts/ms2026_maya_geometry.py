# -*- coding: utf-8 -*-
"""ポリゴン以外のジオメトリ(NURBS 等)の検出と、NURBS サーフェスのポリゴン変換。Unity はポリゴンメッシュしか読めない。"""
import maya.cmds as cmds

NON_POLY_TYPES = ("nurbsSurface", "nurbsCurve", "bezierCurve", "subdiv")


def _short(node):
    return node.split("|")[-1]


def non_polygon_problems(transform):
    """transform が持つポリゴン以外のシェイプを [(transform, メッセージ)] で返す。"""
    out = []
    for typ in NON_POLY_TYPES:
        if cmds.listRelatives(transform, shapes=True, fullPath=True, type=typ):
            out.append((transform, "Not a polygon mesh ({}): Unity cannot import it. "
                                   "Use 'ポリゴンに変換'".format(typ)))
    return out


def _convert_one(node):
    """NURBS サーフェス 1 つをポリゴン化して同じ親・同じ名前・同じワールド位置に置く。戻り値: 新ノード(長い名前)。"""
    name = _short(node)
    parent = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    matrix = cmds.xform(node, q=True, ws=True, matrix=True)
    kids = cmds.listRelatives(node, children=True, fullPath=True, type="transform") or []
    res = cmds.nurbsToPoly(node, mnd=1, ch=0, f=3, pt=1, pc=200, chr=0.9, ft=0.01, mel=0.001,
                           d=0.1, ut=1, un=3, vt=1, vn=3, uch=0, ucr=0, cht=0.2, es=0, ntr=0,
                           mrt=0, uss=1)
    new = cmds.ls(res[0], long=True)[0]
    if parent:
        new = cmds.parent(new, parent, absolute=True)[0]
    cmds.xform(new, ws=True, matrix=matrix)
    for k in kids:
        cmds.parent(k, new, absolute=True)
    cmds.delete(node)
    new = cmds.ls(cmds.rename(new, name), long=True)[0]
    cmds.delete(new, constructionHistory=True)
    return new


def convert_to_polygons(nodes=None):
    """選択(とその子孫)の NURBS サーフェスをポリゴンメッシュにする。戻り値: [(旧名, 新名)]。カーブ等は変換しない。"""
    if nodes is None:
        nodes = cmds.ls(selection=True, long=True)
    elif isinstance(nodes, str):
        nodes = [nodes]
    todo, skipped = [], 0
    for top in nodes:
        top = cmds.ls(top, long=True)[0]
        for t in [top] + (cmds.listRelatives(top, allDescendents=True, fullPath=True, type="transform") or []):
            if t in todo:
                continue
            if cmds.listRelatives(t, shapes=True, type="nurbsSurface"):
                todo.append(t)
            elif cmds.listRelatives(t, shapes=True, type=("nurbsCurve", "bezierCurve")):
                skipped += 1
    todo.sort(key=lambda p: p.count("|"), reverse=True)  # 深い方から(親のパスが変わる前に)
    result = []
    for node in todo:
        if not cmds.objExists(node):
            continue
        result.append((node, _convert_one(node)))
    for old, new in result:
        print("[MS2026 convert] {} -> {}".format(old, new))
    if skipped:
        cmds.warning("[MS2026] 変換不可: カーブ {} 件".format(skipped))
    convert_to_polygons.skipped_curves = skipped
    return result
