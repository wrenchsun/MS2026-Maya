# -*- coding: utf-8 -*-
"""選択ノードを小物として登録する(FBX 書き出し + その場に小物インスタンスとして残す)。"""
import re

import maya.cmds as cmds

import ms2026_maya_naming as naming
import ms2026_maya_props as props
import ms2026_maya_tools as tools

_IDENT = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _short(node):
    return node.split("|")[-1].split(":")[-1]


def _is_greybox(node):
    """node かその祖先が GB_* レイヤー / GREYBOX_ANCHORS の所属か。"""
    parts = node.strip("|").split("|")
    chain = ["|" + "|".join(parts[:i + 1]) for i in range(len(parts))]
    for layer, _label in tools.list_block_layers():
        members = set(cmds.ls(cmds.editDisplayLayerMembers(layer, q=True, fullNames=True) or [], long=True))
        if members.intersection(chain):
            return True
    return False


def _pick_top(top):
    if top is None:
        sel = cmds.ls(selection=True, long=True, transforms=True) or []
        if len(sel) != 1:
            raise RuntimeError("小物にするノードを 1 つだけ選んでください(選択: {} 個)".format(len(sel)))
        top = sel[0]
    top = cmds.ls(top, long=True)[0]
    if props.BLOCK_RE.match(_short(top)):
        raise RuntimeError("SM_Bg_ グループは小物にできません: " + _short(top))
    if _is_greybox(top):
        raise RuntimeError("グレーボックス(参照)のノードは小物にできません: " + _short(top))
    return top


def _tag(node, name, collision):
    for attr, val in ((props.PROP_ATTR, name), (props.COLLIDER_ATTR, props.collision_mode(collision))):
        if not cmds.attributeQuery(attr, node=node, exists=True):
            cmds.addAttr(node, longName=attr, dataType="string")
        cmds.setAttr(node + "." + attr, val, type="string")


def _fix_descendants(node):
    """子孫の transform のうち命名規則(NAME_RE)に合わないものを sanitize する(接頭辞は保持、無ければ SM_)。"""
    pairs = []
    for n in cmds.listRelatives(node, allDescendents=True, fullPath=True, type="transform") or []:
        name = _short(n)
        if tools.NAME_RE.match(name):
            continue
        pairs.append((n, naming.fixed_name(name)))
    return naming._rename_all(pairs)


def register_prop_from_selection(collision="mesh", top=None):
    """選択ノードを小物として FBX 登録し、元ノードはその場に小物インスタンスとして残す。
    collision: "mesh"(形どおり、SM_Prop_) / "simple"(簡易、SC_Prop_)。bool(True=mesh)も受け付ける。
    戻り値: (小物名, FBX パス, 元ノードの long 名)。"""
    collision = props.collision_mode(collision)
    top = _pick_top(top)
    uid = cmds.ls(top, uuid=True)[0]
    reuse = (cmds.getAttr(top + "." + props.PROP_ATTR)
             if cmds.attributeQuery(props.PROP_ATTR, node=top, exists=True) else None)
    name = naming.sanitize(reuse) if reuse else naming.sanitize(naming.strip_prefix(_short(top)))
    cmds.rename(top, props.prop_prefix(collision) + name)
    node = cmds.ls(uid, long=True)[0]
    name = props.PROP_RE.match(_short(node)).group(2)  # 衝突で番号が付いた場合は最終名に合わせる
    cmds.delete(node, constructionHistory=True)
    _fix_descendants(node)
    node = cmds.ls(uid, long=True)[0]
    parents = cmds.listRelatives(node, parent=True, fullPath=True)
    parent = parents[0] if parents else None
    saved_matrix = cmds.xform(node, q=True, ws=True, matrix=True)
    saved_piv = {a: cmds.getAttr(node + "." + a)[0] for a in ("rotatePivot", "scalePivot")}
    try:
        if parent:
            cmds.parent(node, world=True)
        node = cmds.ls(uid, long=True)[0]
        cmds.xform(node, ws=True, matrix=_IDENT)
        for a in saved_piv:
            cmds.setAttr(node + "." + a, 0, 0, 0)
        path = props.export_prop(top=node)
    finally:
        node = cmds.ls(uid, long=True)[0]
        for a, v in saved_piv.items():
            cmds.setAttr(node + "." + a, *v)
        if parent:
            node = cmds.parent(node, parent)[0]
        cmds.xform(node, ws=True, matrix=saved_matrix)
    if not path:
        raise RuntimeError("小物の書き出しに失敗(Check の問題はスクリプトエディタ参照)")
    node = cmds.ls(uid, long=True)[0]
    _tag(node, name, collision)
    print("[MS2026] Registered prop: {} -> {}".format(name, path))
    return name, path, node
