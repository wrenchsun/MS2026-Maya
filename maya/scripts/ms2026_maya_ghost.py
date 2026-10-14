# -*- coding: utf-8 -*-
"""グレーボックス(GB_* レイヤー)だけを半透明表示にする。マテリアル差し替え方式(モデリング中の自作メッシュには影響しない)。"""
import maya.cmds as cmds

GHOST_MAT = "MS2026_GreyboxGhost"
GHOST_SG = GHOST_MAT + "SG"
ORIG_ATTR = "ms2026_orig_sg"
LAYER_PREFIX = "GB_"
TRANSPARENCY = 0.6


def _ensure_ghost():
    if cmds.objExists(GHOST_SG):
        return
    mat = cmds.shadingNode("lambert", asShader=True, name=GHOST_MAT)
    cmds.setAttr(mat + ".color", 0.75, 0.75, 0.75, type="double3")
    cmds.setAttr(mat + ".transparency", TRANSPARENCY, TRANSPARENCY, TRANSPARENCY, type="double3")
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=GHOST_SG)
    cmds.connectAttr(mat + ".outColor", sg + ".surfaceShader", force=True)


def _gb_layers():
    return [l for l in (cmds.ls(type="displayLayer") or []) if l.startswith(LAYER_PREFIX)]


def _gb_shapes():
    shapes = []
    for layer in _gb_layers():
        for n in cmds.editDisplayLayerMembers(layer, q=True, fullNames=True) or []:
            for s in cmds.listRelatives(n, shapes=True, fullPath=True, type="mesh") or []:
                if s not in shapes:
                    shapes.append(s)
    return shapes


def _assign(shape, sg):
    cmds.sets(shape, edit=True, forceElement=sg)


def _current_sg(shape_path):
    """インスタンスごとのシェーディンググループ(listSets は DAG パス単位で返す)。"""
    sgs = cmds.listSets(object=shape_path, type=1) or []
    return sgs[0] if sgs else "initialShadingGroup"


def set_greybox_transparent(on):
    """GB_* レイヤーのメッシュを半透明マテリアルにする(on=True)/元に戻す(False)。戻り値: 変えたインスタンス数。

    Unity から来た FBX はメッシュを多数の Transform で共有(インスタンス)しているため、
    シェーディングの付け替えと元の記録は DAG パス(親 Transform)単位で行う。
    """
    if on:
        _ensure_ghost()
    saved = {l: cmds.getAttr(l + ".displayType") for l in _gb_layers()}
    count = 0
    try:
        for s in _gb_shapes():
            parent = s.rsplit("|", 1)[0]
            current = _current_sg(s)
            has_orig = cmds.attributeQuery(ORIG_ATTR, node=parent, exists=True)
            if on:
                if current == GHOST_SG:
                    continue
                if not has_orig:
                    cmds.addAttr(parent, longName=ORIG_ATTR, dataType="string")
                cmds.setAttr(parent + "." + ORIG_ATTR, current, type="string")
                target = GHOST_SG
            else:
                if current != GHOST_SG:
                    continue
                target = cmds.getAttr(parent + "." + ORIG_ATTR) if has_orig else "initialShadingGroup"
                if not cmds.objExists(target) or target == GHOST_SG:
                    target = "initialShadingGroup"
            try:
                _assign(s, target)
            except RuntimeError:
                # 参照表示(displayType 2)で拒否されたら一時的に 0 にして付け替える
                for l in saved:
                    cmds.setAttr(l + ".displayType", 0)
                _assign(s, target)
                for l, v in saved.items():
                    cmds.setAttr(l + ".displayType", v)
            count += 1
    finally:
        for l, v in saved.items():
            cmds.setAttr(l + ".displayType", v)
    return count
