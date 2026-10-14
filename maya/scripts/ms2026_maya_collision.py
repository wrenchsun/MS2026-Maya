# -*- coding: utf-8 -*-
"""簡易当たり判定 (SC_) の形状を書き出し時に自動で選ぶ (Box / Sphere / Capsule)。
デザイナーは SC_ を付けるだけで、形の選択と寸法はここで決める。微調整は Unity の Inspector で行う。
仕様: Docs/Guides/MayaGreyboxPipeline.md §2.2 / §3"""
import json
import math
import os

import maya.api.OpenMaya as om
import maya.cmds as cmds

SIMPLE_PREFIXES = ("SC_", "NC_")  # NC_ は旧名 (当たり判定なし)。簡易当たり判定として扱う
SHAPE_BOX, SHAPE_SPHERE, SHAPE_CAPSULE = "box", "sphere", "capsule"
EPS = 1e-4

# 判定のしきい値。頂点はすべて対象ノードのローカル空間 (cm)。
SPHERE_EXTENT_RATIO = 0.9  # 3 軸の幅がこの比率以上で揃っていれば球の候補
CAPSULE_LENGTH_RATIO = 1.2  # 最長軸が 2 番目の軸のこの倍以上ならカプセルの候補
CAPSULE_ROUND_RATIO = 0.85  # 断面の 2 軸の幅がこの比率以上で揃っていればカプセルの候補
FIT_TOL = 0.15  # 「丸い」と見なす半径のずれ (半径に対する比率)
FIT_MIN_BINS = 0.6  # 角度ビンのうち頂点があるビンの最低割合 (少なすぎると判定しない)
AZIMUTH_BINS = 12
ELEVATION_BINS = 6


def _short(node):
    return node.split("|")[-1].split(":")[-1]


def is_simple_name(name):
    return name.startswith(SIMPLE_PREFIXES)


def own_meshes(node):
    """node 直下のメッシュ形状 (intermediate を除く)。"""
    return cmds.listRelatives(node, shapes=True, fullPath=True, type="mesh", noIntermediate=True) or []


def descendant_meshes(node):
    """node 以下 (自身の直下を含む) の全メッシュ形状。"""
    return cmds.listRelatives(node, allDescendents=True, fullPath=True, type="mesh", noIntermediate=True) or []


def local_vertices(root, shapes):
    """shapes の頂点を root のローカル空間 (root のワールド行列の逆で変換) に直して返す [(x, y, z)]。
    Unity 側で同じ GameObject に付ける Collider は、その Transform のローカル空間なのでこれに合わせる。"""
    root = cmds.ls(root, long=True)[0]
    inv = om.MMatrix(cmds.xform(root, q=True, ws=True, matrix=True)).inverse()
    pts = []
    for sh in shapes:
        flat = cmds.xform(sh + ".vtx[*]", q=True, ws=True, t=True) or []
        for i in range(0, len(flat), 3):
            p = om.MPoint(flat[i], flat[i + 1], flat[i + 2]) * inv
            pts.append((p.x, p.y, p.z))
    return pts


def _bounds(pts):
    mn = [min(p[i] for p in pts) for i in range(3)]
    mx = [max(p[i] for p in pts) for i in range(3)]
    center = [(mn[i] + mx[i]) * 0.5 for i in range(3)]
    size = [mx[i] - mn[i] for i in range(3)]
    return center, size


def _round_enough(values_by_bin, radius, total_bins):
    """角度ビンごとの最大距離が radius ± FIT_TOL に収まり、ビンが十分埋まっていれば True。"""
    if radius <= EPS or len(values_by_bin) < total_bins * FIT_MIN_BINS:
        return False
    tol = radius * FIT_TOL
    return all(abs(v - radius) <= tol for v in values_by_bin.values())


def _sphere_fit(pts, center, radius):
    """方位 × 仰角のビンで最大距離を取り、球面に乗っているか。立方体は角のビンが √3 倍になって落ちる。"""
    bins = {}
    for p in pts:
        d = [p[i] - center[i] for i in range(3)]
        dist = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        if dist <= EPS:
            continue
        az = int((math.atan2(d[2], d[0]) + math.pi) / (2 * math.pi) * AZIMUTH_BINS) % AZIMUTH_BINS
        el = int((math.asin(max(-1.0, min(1.0, d[1] / dist))) + math.pi / 2) / math.pi * ELEVATION_BINS)
        key = (az, min(el, ELEVATION_BINS - 1))
        bins[key] = max(bins.get(key, 0.0), dist)
    return _round_enough(bins, radius, AZIMUTH_BINS * ELEVATION_BINS)


def _capsule_fit(pts, center, axis, radius):
    """軸まわりの方位ビンで最大半径距離を取り、断面が丸いか。角柱は角のビンが √2 倍になって落ちる。"""
    u, v = [i for i in range(3) if i != axis]
    bins = {}
    for p in pts:
        du, dv = p[u] - center[u], p[v] - center[v]
        dist = math.sqrt(du * du + dv * dv)
        if dist <= EPS:
            continue
        az = int((math.atan2(dv, du) + math.pi) / (2 * math.pi) * AZIMUTH_BINS) % AZIMUTH_BINS
        bins[az] = max(bins.get(az, 0.0), dist)
    return _round_enough(bins, radius, AZIMUTH_BINS)


def classify(pts):
    """頂点 (ローカル空間 cm) から簡易当たり判定を決める。戻り値は JSON にそのまま書ける dict。
    center / size は常に AABB。sphere は radius、capsule は radius / height / direction (0=X 1=Y 2=Z) を足す。"""
    if len(pts) < 4:
        center, size = _bounds(pts) if pts else ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        return {"shape": SHAPE_BOX, "center": center, "size": size}
    center, size = _bounds(pts)
    ext = sorted(((size[i], i) for i in range(3)), reverse=True)
    (a, ia), (b, _ib), (c, _ic) = ext
    entry = {"shape": SHAPE_BOX, "center": center, "size": size}
    if a <= EPS:
        return entry
    if b / a >= SPHERE_EXTENT_RATIO and c / a >= SPHERE_EXTENT_RATIO:
        radius = (a + b + c) / 6.0
        if _sphere_fit(pts, center, radius):
            entry.update(shape=SHAPE_SPHERE, radius=radius)
            return entry
    if b > EPS and a >= b * CAPSULE_LENGTH_RATIO and c / b >= CAPSULE_ROUND_RATIO:
        radius = (b + c) / 4.0
        if _capsule_fit(pts, center, ia, radius):
            entry.update(shape=SHAPE_CAPSULE, radius=radius, height=a, direction=ia)
            return entry
    return entry


def classify_node(node, shapes=None):
    """node のローカル空間で簡易当たり判定を決める。shapes 省略で node 以下の全メッシュ (小物用)。"""
    node = cmds.ls(node, long=True)[0]
    if shapes is None:
        shapes = descendant_meshes(node)
    return classify(local_vertices(node, shapes))


def relative_path(top, node):
    """top から node までの短い名前を '/' で繋いだパス (Unity の Transform.Find 用)。"""
    top = cmds.ls(top, long=True)[0]
    node = cmds.ls(node, long=True)[0]
    rel = node[len(top):].strip("|") if node.startswith(top + "|") else _short(node)
    return "/".join(_short(n) for n in rel.split("|"))


def collect_block_colliders(top, skip=()):
    """top 以下の SC_ (旧 NC_) メッシュごとに簡易当たり判定を決めて [entry] を返す。
    対象は自分の直下にメッシュを持つ transform だけ (Unity の MeshFilter 単位と合わせる)。skip は小物の中など。"""
    top = cmds.ls(top, long=True)[0]
    skip = set(skip)
    entries = []
    for node in cmds.listRelatives(top, allDescendents=True, fullPath=True, type="transform") or []:
        if node in skip or not is_simple_name(_short(node)):
            continue
        shapes = own_meshes(node)
        if not shapes:
            continue
        entry = classify_node(node, shapes)
        entry["path"] = relative_path(top, node)
        entries.append(entry)
    return entries


def write_colliders_json(top, entries, out_path):
    """SM_Bg_<Block>.colliders.json を書く。"""
    block = _short(cmds.ls(top, long=True)[0])[len("SM_Bg_"):]
    data = {"version": 1, "block": block, "units": "cm",
            "colliders": [{"path": e["path"], "shape": e["shape"], "center": e["center"], "size": e["size"],
                           "radius": e.get("radius", 0.0), "height": e.get("height", 0.0),
                           "direction": e.get("direction", 1)} for e in entries]}
    os.makedirs(os.path.dirname(os.path.normpath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def summary(entries):
    """'Box 3 / Sphere 1 / Capsule 2' の形の要約。"""
    counts = {SHAPE_BOX: 0, SHAPE_SPHERE: 0, SHAPE_CAPSULE: 0}
    for e in entries:
        counts[e["shape"]] = counts.get(e["shape"], 0) + 1
    return "Box {} / Sphere {} / Capsule {}".format(counts[SHAPE_BOX], counts[SHAPE_SPHERE], counts[SHAPE_CAPSULE])
