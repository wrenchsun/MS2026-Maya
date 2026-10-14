# -*- coding: utf-8 -*-
"""MS2026 命名の補助。接頭辞を付ける / 不正な名前を直す / 問題のノードを選ぶ。ルールは ms2026_maya_tools.NAME_RE。"""
import re

import maya.cmds as cmds

# 長いものを先に判定する。NC_ は旧名(当たり判定なし)で、自動修正で SC_(簡易当たり判定)にする
KNOWN_PREFIXES = ("SM_Prop_", "SC_Prop_", "NC_Prop_", "SM_Bg_", "UCX_", "SM_", "SC_", "NC_")
LEGACY_PREFIXES = {"NC_Prop_": "SC_Prop_", "NC_": "SC_"}
_DEFAULT_RE = re.compile(
    r"^(p(Cube|Sphere|Cylinder|Cone|Plane|Torus|Pipe|Prism|Pyramid|Helix|Disc|Platonic|Solid)"
    r"|polySurface|group|transform|null|nurbs[A-Za-z]*|pasted__.*)\d*$")
_BAD_CHAR_RE = re.compile(r"[^A-Za-z0-9_]")


def _short(node):
    return node.split("|")[-1].split(":")[-1]


def _depth(node):
    return node.count("|")


def known_prefix(name):
    """name が先頭に持つ既知の接頭辞。無ければ None。"""
    return next((p for p in KNOWN_PREFIXES if name.startswith(p)), None)


def strip_prefix(name):
    p = known_prefix(name)
    return name[len(p):] if p else name


def sanitize(base):
    """A-Za-z0-9_ 以外を _ にし、連続 _ をまとめ、前後の _ を取る。空は Mesh、数字始まりは M を付ける。"""
    s = re.sub(r"_+", "_", _BAD_CHAR_RE.sub("_", base)).strip("_")
    if not s:
        return "Mesh"
    return "M" + s if s[0].isdigit() else s


def fixed_name(name):
    """規則に合う名前に直す。接頭辞があれば保持(旧 NC_ は SC_ に置き換え)、無ければ SM_ を付ける。"""
    p = known_prefix(name)
    if p is None:
        return "SM_" + sanitize(name)
    return LEGACY_PREFIXES.get(p, p) + sanitize(name[len(p):])


def looks_default(name):
    """pCube1 / polySurface3 / group2 / pasted__x のような Maya 既定名か。"""
    return bool(_DEFAULT_RE.match(strip_prefix(_short(name))))


def _prop_subtree(top):
    """top 配下の小物ノード(自身を含む)とその子孫の long 名集合。"""
    import ms2026_maya_tools as t
    skip = set()
    for pn, _n, _c in t.collect_props(top):
        skip.update(t._with_descendants(pn))
    return skip


def _rename_one(node, new):
    """node を new にして新しい long 名を返す。メッシュ形状も <new>Shape にする。"""
    got = cmds.rename(node, new)
    long_new = cmds.ls(got, long=True)[0]
    for sh in cmds.listRelatives(long_new, shapes=True, fullPath=True, noIntermediate=True) or []:
        try:
            cmds.rename(sh, _short(long_new) + "Shape")
        except RuntimeError:
            pass  # インスタンス等で改名できない形状は放置
    return long_new


def _rename_all(pairs):
    """pairs=[(long, 新しい短い名前)] を uuid 経由で深い順に改名。戻り値 [(old短名, new短名)]。"""
    entries = []
    for node, new in pairs:
        u = cmds.ls(node, uuid=True)
        if u:
            entries.append((u[0], _depth(node), new))
    entries.sort(key=lambda e: -e[1])
    out = []
    for u, _d, new in entries:
        cur = cmds.ls(u, long=True)
        if not cur:
            continue
        old = _short(cur[0])
        new_long = _rename_one(cur[0], new)
        out.append((old, _short(new_long)))
    return out


def apply_prefix(nodes, prefix, keep_base=True):
    """nodes の各 transform を prefix + sanitize(接頭辞を除いた名前) にする。戻り値 [(old, new)]。"""
    pairs = []
    for n in nodes:
        lng = cmds.ls(n, long=True)
        if not lng or cmds.nodeType(lng[0]) != "transform":
            continue
        short = _short(lng[0])
        base = sanitize(strip_prefix(short)) if keep_base else "Mesh"
        new = prefix + base
        if short != new:
            pairs.append((lng[0], new))
    res = _rename_all(pairs)
    for old, new in res:
        print("[MS2026 naming] {} -> {}".format(old, new))
    return res


def top_level(nodes):
    """選択のうち、他の選択ノードの子孫ではないものだけ。"""
    longs = [cmds.ls(n, long=True)[0] for n in nodes]
    return [n for n in longs if not any(n != o and n.startswith(o + "|") for o in longs)]


def make_prop(nodes, collision):
    """最上位の選択ノードだけを SM_Prop_(形どおり) / SC_Prop_(簡易) にする。collision は "mesh" / "simple" / bool。"""
    import ms2026_maya_props as props
    return apply_prefix(top_level(nodes), props.prop_prefix(collision))


def expand_targets(selected):
    """選択 + 子孫の transform。小物の中・SM_Bg_ グループ・カメラは除く。"""
    import ms2026_maya_tools as t
    out, skip = [], set()
    for top in top_level(selected):
        skip |= _prop_subtree(top)
        for n in t._with_descendants(top):
            if n in out or n in skip or cmds.nodeType(n) != "transform":
                continue
            if t.BLOCK_RE.match(_short(n)) or cmds.listRelatives(n, shapes=True, type="camera"):
                continue
            out.append(n)
    return out


def auto_fix(top):
    """top 以下で規則に合わない名前を直す(小物の中は触らない)。戻り値 [(old, new)]。"""
    import ms2026_maya_tools as t
    top = cmds.ls(top, long=True)[0]
    skip = _prop_subtree(top)
    pairs = []
    for n in t._with_descendants(top):
        if n in skip or cmds.nodeType(n) != "transform":
            continue
        name = _short(n)
        if t.NAME_RE.match(name):
            continue
        pairs.append((n, fixed_name(name)))
    res = _rename_all(pairs)
    for old, new in res:
        print("[MS2026 naming] {} -> {}".format(old, new))
    return res


def select_problems(top):
    """check_selection の問題ノードを選択して返す。"""
    import ms2026_maya_tools as t
    problems = t.check_selection([top])
    nodes = []
    for n, _m in problems:
        if n not in nodes:
            nodes.append(n)
    if nodes:
        cmds.select(nodes, replace=True)
    return nodes
