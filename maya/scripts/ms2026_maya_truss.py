# -*- coding: utf-8 -*-
"""ライブ会場用トラスのプロシージャル生成 (maya.cmds のみ。UI なし。mayapy standalone で動く)。
トラスの直線部材 1 本 (柱 1 本・梁 1 本) = SC_ ノード 1 つ = Box コライダー 1 つ。
部材内の弦・横桟・斜材は 1 メッシュに結合する。単位 cm / Y 上。長さ方向はローカル +X、断面は YZ。"""
import json
import math
import re

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
    "corner_block": True,  # 門型・パスの角に断面サイズの立方体ブロックを足す
    "brace_pattern": "zigzag",  # "zigzag" (横桟 + ジグザグの斜材) / "ladder" (横桟だけ。間隔は seg_len)
}
BRACE_PATTERNS = ("zigzag", "ladder")


def make_params(params=None):
    p = dict(DEFAULT_PARAMS)
    p.update({k: v for k, v in (params or {}).items() if k in DEFAULT_PARAMS and v is not None})
    if p["section"] <= p["chord_dia"] or p["chord_dia"] <= 0 or p["brace_dia"] <= 0 or p["seg_len"] <= 0:
        raise ValueError("トラスの寸法が不正です: {}".format(p))
    if p["brace_pattern"] not in BRACE_PATTERNS:
        raise ValueError("斜材パターンは {} のどれかです: {}".format(" / ".join(BRACE_PATTERNS), p["brace_pattern"]))
    p["chord_div"], p["brace_div"] = int(p["chord_div"]), int(p["brace_div"])
    if p["chord_div"] < 3 or p["brace_div"] < 3:
        raise ValueError("円周分割は 3 以上にしてください: {}".format(p))
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


def _clamp_x(node, half):
    """node のメッシュの頂点のうちローカル X が ±half を超えるものを ±half に寄せる (斜材・横桟の端面のはみ出し除去)。"""
    shape = cmds.listRelatives(node, shapes=True, fullPath=True, type="mesh")[0]
    sel = om.MSelectionList()
    sel.add(shape)
    fn = om.MFnMesh(sel.getDagPath(0))
    pts = fn.getPoints(om.MSpace.kObject)
    for i in range(len(pts)):
        pt = pts[i]
        if pt.x > half:
            pt.x = half
        elif pt.x < -half:
            pt.x = -half
        else:
            continue
        pts[i] = pt
    fn.setPoints(pts, om.MSpace.kObject)
    fn.updateSurface()


def build_member(name, length, params=None, parent=None, extra_boxes=()):
    """4 本弦のボックストラス部材 1 本。ローカル +X が長さ方向、ピボットは中心。
    名前は SC_<name>。ms2026_collider_shape = "box"。戻り値: transform (long 名)。
    部材端 (ローカル X = ±length/2) を超える斜材・横桟の端面はクランプして寸法を length x section x section に揃える。
    extra_boxes: [((cx, cy, cz), (sx, sy, sz)), ...] 部材ローカル空間の直方体 (角ブロック・スリーブ)。クランプの後で結合する
    (意図してはみ出す)。"""
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
    for k in range(n if p["brace_pattern"] == "zigzag" else 0):  # 斜材: 各面・各セグメントでジグザグ (ladder は無し)
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
    _clamp_x(united, length * 0.5)
    if extra_boxes:
        boxes = []
        for (cx, cy, cz), (sx, sy, sz) in extra_boxes:
            b = cmds.polyCube(width=sx, height=sy, depth=sz, name="tmpBlock", constructionHistory=False)[0]
            cmds.xform(b, ws=True, t=(cx, cy, cz))
            boxes.append(b)
        united = cmds.polyUnite([united] + boxes, constructionHistory=False, mergeUVSets=1, name="tmpMember2")[0]
        cmds.delete(united, constructionHistory=True)
        leftovers = [x for x in boxes if cmds.objExists(x)]
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
        # 角ブロックは柱の上端の内側 (柱の寸法は変えない。梁との接合部を埋める)
        blocks = [((height * 0.5 - s * 0.5, 0.0, 0.0), (s, s, s))] if p["corner_block"] else ()
        post = build_member("{}_{}".format(base, side), height, p, parent=grp, extra_boxes=blocks)
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


def _write_info(group, info):
    cmds.setAttr(group + "." + TRUSS_ATTR, json.dumps(info, ensure_ascii=False), type="string")


# ---------------------------------------------------------------- パス (点列 / カーブ)

DEFAULT_MEMBER_LEN = 200.0  # 滑らかなカーブを等分するときの部材長 (cm)


def _basis_matrix(p0, p1):
    """p0 -> p1 を X 軸、断面 Y を world Y に近づけた右手系の 4x4 行列 (cmds.xform 用 16 要素、中点に平行移動)。"""
    x = om.MVector(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]).normal()
    ref = om.MVector(0, 1, 0) if abs(x.y) <= 0.99 else om.MVector(0, 0, 1)
    y = (ref - x * (ref * x)).normal()
    z = x ^ y
    t = [(a + b) * 0.5 for a, b in zip(p0, p1)]
    return [x.x, x.y, x.z, 0.0, y.x, y.y, y.z, 0.0, z.x, z.y, z.z, 0.0, t[0], t[1], t[2], 1.0]


DEFAULT_SNAP_ANGLE = 90   # ポリライン (degree 1 / 点列 / プリセット) の既定
DEFAULT_SNAP_GRID = 10.0  # cm


def _snap_dirs(angle):
    """許可方向 (単位ベクトル)。90: ±X/±Y/±Z の 6 方向。45: それに座標平面内の 45 度対角 12 方向を足した 18 方向。"""
    dirs = []
    for a in range(3):
        for sg in (1.0, -1.0):
            v = [0.0, 0.0, 0.0]
            v[a] = sg
            dirs.append(tuple(v))
    if angle == 45:
        r = math.sqrt(0.5)
        for a, b in ((0, 1), (0, 2), (1, 2)):
            for sa in (1.0, -1.0):
                for sb in (1.0, -1.0):
                    v = [0.0, 0.0, 0.0]
                    v[a], v[b] = sa * r, sb * r
                    dirs.append(tuple(v))
    return dirs


def _round_grid(v, grid):
    return round(v / grid) * grid + 0.0  # + 0.0 で -0.0 を 0.0 にする


def snap_points(points, closed=False, angle=DEFAULT_SNAP_ANGLE, grid=DEFAULT_SNAP_GRID):
    """点列をグリッド (cm) と角度 (0=なし / 45 / 90) に揃える。戻り値: 新しい点列 (list of [x, y, z])。
    grid > 0: まず全点を grid に丸める。angle が 45/90: 先頭点を固定し、各スパンの方向を許可方向の最も近いものに
    置き換え、長さ (その方向への射影を grid に丸めたもの) で次の点を累積して決める。
    closed のとき最後 -> 最初のスパンは先頭点が固定なので方向が許可外になりうる (その旨を info で print)。"""
    if angle not in (0, 45, 90):
        raise ValueError("スナップ角度は 0 / 45 / 90 のどれかです: {}".format(angle))
    grid = float(grid or 0.0)
    pts = [[float(v) for v in p] for p in points]
    if grid > 0:
        pts = [[_round_grid(v, grid) for v in p] for p in pts]
    if angle == 0 or len(pts) < 2:
        return pts
    dirs = _snap_dirs(angle)
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        v = [q - r for q, r in zip(b, a)]
        d = max(dirs, key=lambda u: sum(x * y for x, y in zip(v, u)))
        run = sum(x * y for x, y in zip(v, d))  # 方向への射影 (斜めにずれた分で長さが膨らまない)
        if grid > 0:
            run = _round_grid(run, grid)
        out.append([round(p + c * run, 6) + 0.0 for p, c in zip(out[-1], d)])
    if closed and len(out) > 2:
        v = [q - r for q, r in zip(out[0], out[-1])]
        n = math.sqrt(sum(x * x for x in v))
        if n > 1e-6 and max(sum(x * y for x, y in zip(v, u)) for u in dirs) < n * (1 - 1e-6):
            print("[MS2026] info: 閉じるスパン (最後 -> 最初) は先頭点が固定のため、許可方向からずれています。"
                  "最後の点を動かして直してください。")
    return out


def preset_points(kind, width, height, plane="XY", section=0.0):
    """形プリセットの点列。戻り値: (points, closed)。原点は床面の中央 (x 方向に左右対称)、点は部材の中心線。
    kind: "line" (+X へ width) / "L" (上へ height、右へ width) / "U" (左柱 ↑ -> 梁 -> 右柱 ↓) / "rect" (閉)。
    section: 断面サイズ。XY の line / rect は部材が床にめり込まないよう点を section/2 持ち上げる
    (L / U は柱の下端 = 点が y=0 なので持ち上げない)。
    plane: "XY" 立面 (y が上、y=0..height) / "XZ" 床面に寝かせる (y=0、height は Z 方向で原点が中央)。"""
    k = str(kind)
    kind = k.upper() if k.upper() in ("L", "U") else k.lower()
    plane = str(plane).upper()
    if plane not in ("XY", "XZ"):
        raise ValueError("平面は XY / XZ です: {}".format(plane))
    if kind not in ("line", "L", "U", "rect"):
        raise ValueError("未知のプリセット: {}".format(kind))
    if width <= 0 or (kind != "line" and height <= 0):
        raise ValueError("幅・高さは正の値にしてください: {} x {}".format(width, height))
    hw = width * 0.5
    flat = {"line": [(-hw, 0), (hw, 0)],
            "L": [(-hw, 0), (-hw, height), (hw, height)],
            "U": [(-hw, 0), (-hw, height), (hw, height), (hw, 0)],
            "rect": [(-hw, 0), (-hw, height), (hw, height), (hw, 0)]}[kind]
    if plane == "XY":
        lift = section * 0.5 if kind in ("line", "rect") else 0.0
        pts = [[x, y + lift, 0.0] for x, y in flat]
    else:
        pts = [[x, 0.0, y - height * 0.5] for x, y in flat]
    return pts, kind == "rect"


def _corner_assignments(n_pts, n_spans, closed, valid):
    """角ブロックを結合する部材の割り当て。戻り値: {スパン番号: ["start" / "end", ...]}。
    頂点 k (閉パスは全頂点、開パスは両端を除く内部頂点) の角は、隣り合う 2 スパンのうち番号の若い方に付ける
    (頂点 k >= 1 はスパン k-1 の終点側、閉パスの頂点 0 はスパン 0 の始点側)。若い方が作られない (短すぎる) ときはもう一方。"""
    out = {}
    verts = range(n_pts) if closed else range(1, n_pts - 1)
    for k in verts:
        if k == 0:
            cands = [(0, "start"), (n_spans - 1, "end")]
        else:
            cands = [(k - 1, "end"), (k, "start")]
        for span, e in cands:
            if span < n_spans and valid[span]:
                out.setdefault(span, []).append(e)
                break
    return out


def _fill_path(grp, name, points, closed, params):
    pts = [tuple(float(v) for v in p) for p in points]
    if len(pts) < 2:
        raise ValueError("パスには 2 点以上が必要です")
    spans = list(zip(pts, pts[1:]))
    if closed and len(pts) > 2:
        spans.append((pts[-1], pts[0]))
    digits = max(2, len(str(len(spans))))
    base = "Truss_" + _name(name)
    out = []
    min_len = make_params(params)["section"]
    skipped = 0
    lengths = [math.sqrt(sum((q - r) ** 2 for q, r in zip(a, b))) for a, b in spans]
    mp = make_params(params)
    ends = _corner_assignments(len(pts), len(spans), closed and len(pts) > 2, [l > min_len for l in lengths])         if mp["corner_block"] else {}
    sec = mp["section"]
    for i, (a, b) in enumerate(spans):
        length = lengths[i]
        if length <= min_len:  # build_member の長さ制約未満はスキップ
            skipped += 1
            continue
        blocks = [(((-1.0 if e == "start" else 1.0) * length * 0.5, 0.0, 0.0), (sec, sec, sec)) for e in ends.get(i, ())]
        m = build_member("{}_{:0{}d}".format(base, i + 1, digits), length, params, parent=grp, extra_boxes=blocks)
        cmds.xform(m, matrix=_basis_matrix(a, b))  # 親 (グループ) のローカル空間
        out.append(m)
    if skipped:
        print("[MS2026] info: 短すぎるスパン (断面 {} 以下) を {} 本スキップしました。".format(min_len, skipped))
    if not out:
        raise ValueError("部材を 1 本も作れませんでした (全スパンが断面 {} 以下)".format(min_len))
    return out


def build_path(name, points, params=None, parent=None, closed=False, source_curve=None, member_len=None,
               snap_angle=DEFAULT_SNAP_ANGLE, snap_grid=DEFAULT_SNAP_GRID, extra_info=None):
    """点列 points (cm、生成先グループのローカル空間) を結ぶ部材列。2 点ごとに 1 部材 (SC_Truss_<name>_01, _02, ...)。
    closed=True なら最後と最初も結ぶ。コーナーでは部材どうしが重なってよい。
    snap_angle (0/45/90) と snap_grid (cm) で点を揃えてから作り、JSON に保存する (再生成でも適用)。戻り値: グループ (long 名)。"""
    p = make_params(params)
    snap_angle = DEFAULT_SNAP_ANGLE if snap_angle is None else int(snap_angle)
    snap_grid = DEFAULT_SNAP_GRID if snap_grid is None else float(snap_grid)
    pts = snap_points(points, bool(closed), snap_angle, snap_grid)
    dims = {"points": pts, "closed": bool(closed), "source_curve": source_curve,
            "snap_angle": snap_angle, "snap_grid": snap_grid}
    if member_len is not None:
        dims["member_len"] = float(member_len)
    if extra_info:
        dims.update(extra_info)
    grp = _new_group("path", name, dims, p, parent)
    try:
        _fill_path(grp, name, pts, bool(closed), p)
    except Exception:
        cmds.delete(grp)
        raise
    return grp


def _preset_final(kind, width, height, plane, section, snap_angle, snap_grid):
    """プリセットのスナップ済みの点列。戻り値: (points, closed, 保存する snap_grid)。build_preset とプレビューで共有。"""
    pts, closed = preset_points(kind, width, height, plane, section)
    grid = DEFAULT_SNAP_GRID if snap_grid is None else float(snap_grid)
    if grid > 0 and str(plane).upper() == "XY" and (pts[0][1] % grid) > 1e-6:
        # 持ち上げ (section/2) がグリッドの倍数でないので、グリッドは持ち上げ前の形にだけ掛ける
        # (保存する snap_grid は 0。再生成でグリッドを掛けると持ち上げ分が丸められる)
        lift = section * 0.5
        base = snap_points(preset_points(kind, width, height, plane, 0.0)[0], closed, snap_angle, grid)
        pts = [[p[0], p[1] + lift, p[2]] for p in base]
        grid = 0.0
    return pts, closed, grid


def build_preset(name, kind, width, height, params=None, parent=None, plane="XY",
                 snap_angle=DEFAULT_SNAP_ANGLE, snap_grid=DEFAULT_SNAP_GRID):
    """形プリセット ("line" / "L" / "U" / "rect") のパストラス。source_curve なし (make_edit_curve で後から編集可)。"""
    section = make_params(params)["section"]
    pts, closed, grid = _preset_final(kind, width, height, plane, section, snap_angle, snap_grid)
    return build_path(name, pts, params, parent, closed=closed, snap_angle=snap_angle, snap_grid=grid)


# ---------------------------------------------------------------- 円弧 / 円

def arc_points(radius, angle_deg, member_len, start_deg=0.0, plane="XZ", center=(0.0, 0.0, 0.0)):
    """円弧 (折れ線近似) の点列。戻り値: (points, closed)。angle_deg >= 360 は円 (closed=True、始点を重複させない)。
    分割数 = max(2, round(弧長 / member_len)) (円は 3 以上)。plane: "XZ" 床面 (y=center.y、角度は +X から +Z へ) /
    "XY" 立面 (角度は +X から +Y へ)。XY で 180 度以下の円弧 (アーチ) は頂点が真上に来て両端が床 (y=center.y) に
    なるよう、始点を 90 - angle/2 + start_deg、中心を radius*cos(angle/2) だけ下げる (start_deg はそこからの回転)。"""
    plane = str(plane).upper()
    if plane not in ("XY", "XZ"):
        raise ValueError("平面は XY / XZ です: {}".format(plane))
    if radius <= 0 or angle_deg <= 0 or member_len <= 0:
        raise ValueError("半径・角度・部材長は正の値にしてください: {} / {} / {}".format(radius, angle_deg, member_len))
    angle = min(float(angle_deg), 360.0)
    full = angle >= 360.0 - 1e-9
    n = max(2, int(round(radius * math.radians(angle) / member_len)))
    if full:
        n = max(3, n)
    cx, cy, cz = (float(v) for v in center)
    start = float(start_deg)
    if plane == "XY" and not full and angle <= 180.0:
        start += 90.0 - angle * 0.5
        cy -= radius * math.cos(math.radians(angle * 0.5))
    pts = []
    for i in range(n if full else n + 1):
        a = math.radians(start + angle * i / n)
        c, sn = radius * math.cos(a), radius * math.sin(a)
        pts.append([cx + c, cy, cz + sn] if plane == "XZ" else [cx + c, cy + sn, cz])
    return [[round(v, 6) + 0.0 for v in p] for p in pts], full


def build_arc(name, radius, angle_deg, member_len, params=None, parent=None, plane="XZ", start_deg=0.0,
              center=(0.0, 0.0, 0.0), snap_angle=0, snap_grid=DEFAULT_SNAP_GRID):
    """円弧 / 円のパストラス (arc_points + build_path)。JSON に arc: {radius, angle, member_len, plane} も保存 (情報のみ。
    形は points が正)。戻り値: グループ (long 名)。"""
    pts, closed = arc_points(radius, angle_deg, member_len, start_deg, plane, center)
    return build_path(name, pts, params, parent, closed=closed, member_len=member_len,
                      snap_angle=0 if snap_angle is None else snap_angle, snap_grid=snap_grid,
                      extra_info={"arc": {"radius": float(radius), "angle": float(angle_deg),
                                          "member_len": float(member_len), "plane": str(plane).upper()}})


# ---------------------------------------------------------------- 塔 (グランドサポート)

def _check_tower(height, params, base_size, base_thickness, sleeve_height):
    s = make_params(params)["section"]
    if height <= s or base_thickness <= 0 or sleeve_height <= 0 or base_size < s + 10:
        raise ValueError("塔の寸法が不正です: 高さ({})は断面({})より大きく、ベース幅({})は断面+10 以上、"
                         "ベース厚({})・スリーブ高({})は正の値にしてください".format(height, s, base_size, base_thickness, sleeve_height))


def _fill_tower(grp, name, height, params, base_size, base_thickness, sleeve_height):
    p = make_params(params)
    _check_tower(height, p, base_size, base_thickness, sleeve_height)
    s = p["section"]
    base = "Truss_" + _name(name)
    # 柱: トラス (長さ height、ローカル +X = 上) + 上端に被せるスリーブ (断面 + 10、トラス上端を中心に高さ sleeve_height)
    sleeve = [((height * 0.5, 0.0, 0.0), (sleeve_height, s + 10.0, s + 10.0))]
    post = build_member(base + "_Post", height, p, parent=grp, extra_boxes=sleeve)
    cmds.setAttr(post + ".rotateZ", 90)
    cmds.setAttr(post + ".translate", 0, base_thickness + height * 0.5, 0)
    plate = cmds.polyCube(width=base_size, height=base_thickness, depth=base_size,
                          name="SC_" + base + "_Base", constructionHistory=False)[0]
    cmds.addAttr(plate, longName=SHAPE_ATTR, dataType="string")
    cmds.setAttr(plate + "." + SHAPE_ATTR, "box", type="string")
    plate = cmds.parent(plate, grp)[0]
    cmds.setAttr(plate + ".translate", 0, base_thickness * 0.5, 0)
    return [post, plate]


def build_tower(name, height, params=None, parent=None, base_size=100.0, base_thickness=5.0, sleeve_height=60.0):
    """グランドサポート (塔)。グループ SM_Truss_<name> の下に SC_Truss_<name>_Post (垂直トラス + 上端のスリーブ、Box 1 つ) と
    SC_Truss_<name>_Base (床のベースプレート base_size x base_thickness x base_size、y=0 から上、Box 1 つ)。
    トラスは y=base_thickness から height、スリーブはトラス上端を中心に sleeve_height (上へ半分はみ出す)。
    グループ原点は床面の中央。戻り値: グループ (long 名)。"""
    p = make_params(params)
    _check_tower(height, p, base_size, base_thickness, sleeve_height)
    grp = _new_group("tower", name, {"height": height, "base_size": base_size, "base_thickness": base_thickness,
                                     "sleeve_height": sleeve_height}, p, parent)
    try:
        _fill_tower(grp, name, height, p, base_size, base_thickness, sleeve_height)
    except Exception:
        cmds.delete(grp)
        raise
    return grp


def points_from_selection():
    """選択した transform (ロケータ等) の world 位置を選択順に並べた点列。2 点未満はエラー。"""
    pts = []
    for n in cmds.ls(selection=True, long=True, type="transform") or []:
        pts.append([float(v) for v in cmds.xform(n, q=True, ws=True, rotatePivot=True)])
    if len(pts) < 2:
        raise ValueError("点にする transform (ロケータ等) を 2 つ以上、順番に選択してください")
    return pts


def build_from_points(name, world_points, params=None, parent=None, closed=False,
                      snap_angle=DEFAULT_SNAP_ANGLE, snap_grid=DEFAULT_SNAP_GRID):
    """world の点列 (points_from_selection の結果など) から作る。parent のローカル空間へ変換して build_path。"""
    return build_path(name, _world_to_local(world_points, parent), params, parent, closed=closed,
                      snap_angle=snap_angle, snap_grid=snap_grid)


def _shape_of(curve):
    if cmds.nodeType(curve) == "nurbsCurve":
        return cmds.ls(curve, long=True)[0]
    shapes = cmds.listRelatives(curve, shapes=True, fullPath=True, type="nurbsCurve", noIntermediate=True) or []
    if not shapes:
        raise ValueError("カーブ (nurbsCurve) ではありません: {}".format(curve))
    return shapes[0]


def is_curve(node):
    try:
        return bool(node) and cmds.objExists(node) and bool(_shape_of(node))
    except ValueError:
        return False


def _world_to_local(points, node):
    """world の点列を node のローカル空間へ (node=None なら world のまま)。"""
    if not node:
        return [list(p) for p in points]
    inv = om.MMatrix(cmds.xform(node, q=True, ws=True, m=True)).inverse()
    out = []
    for p in points:
        q = om.MPoint(p[0], p[1], p[2]) * inv
        out.append([q.x, q.y, q.z])
    return out


def _local_to_world(points, node):
    if not node:
        return [list(p) for p in points]
    mat = om.MMatrix(cmds.xform(node, q=True, ws=True, m=True))
    out = []
    for p in points:
        q = om.MPoint(p[0], p[1], p[2]) * mat
        out.append([q.x, q.y, q.z])
    return out


def sample_curve(curve, seg_len=DEFAULT_MEMBER_LEN, mode="auto", space=None):
    """カーブから点列を取る。戻り値: (points, closed)。点は world、space を渡すとその transform のローカル空間。
    mode: "auto" (degree 1 なら CV、それ以外は等分) / "cv" / "divide"。seg_len = 滑らかなカーブの部材長。
    閉カーブは最後の点を重複させない。"""
    shape = _shape_of(curve)
    sel = om.MSelectionList()
    sel.add(shape)
    fn = om.MFnNurbsCurve(sel.getDagPath(0))
    closed = fn.form != om.MFnNurbsCurve.kOpen
    if mode == "cv" or (mode == "auto" and fn.degree == 1):
        pts = [[p.x, p.y, p.z] for p in fn.cvPositions(om.MSpace.kWorld)]
        if closed and len(pts) > 2 and max(abs(a - b) for a, b in zip(pts[0], pts[-1])) < 1e-4:
            pts.pop()
    else:
        if seg_len is None or seg_len <= 0:
            raise ValueError("部材長が不正です: {}".format(seg_len))
        total = fn.length()
        n = max(1, int(round(total / seg_len)))
        if closed:
            n = max(3, n)
        count = n if closed else n + 1
        pts = []
        for i in range(count):
            q = fn.getPointAtParam(fn.findParamFromLength(total * i / n), om.MSpace.kWorld)
            pts.append([q.x, q.y, q.z])
    return _world_to_local(pts, space), closed


def _curve_degree(curve):
    sel = om.MSelectionList()
    sel.add(_shape_of(curve))
    return om.MFnNurbsCurve(sel.getDagPath(0)).degree


def build_from_curve(name, curve, params=None, parent=None, member_len=DEFAULT_MEMBER_LEN, closed=False,
                     snap_angle=None, snap_grid=DEFAULT_SNAP_GRID):
    """カーブからパストラスを作る。カーブ名を source_curve に保存 (後から再サンプルできる)。
    snap_angle=None は自動: degree 1 は 90、滑らかなカーブは 0 (グリッドのみ)。"""
    if snap_angle is None:
        snap_angle = DEFAULT_SNAP_ANGLE if _curve_degree(curve) == 1 else 0
    pts, curve_closed = sample_curve(curve, member_len, space=parent)
    src = cmds.ls(curve, long=True)[0]
    if cmds.nodeType(src) == "nurbsCurve":
        src = cmds.listRelatives(src, parent=True, fullPath=True)[0]
    return build_path(name, pts, params, parent, closed=bool(closed or curve_closed), source_curve=src,
                      member_len=member_len, snap_angle=snap_angle, snap_grid=snap_grid)


def _path_group(group):
    if not is_truss_group(group):
        raise ValueError("トラスのグループではありません: {}".format(group))
    group = cmds.ls(group, long=True)[0]
    if read_info(group).get("kind") != "path":
        raise ValueError("パス種別のトラスではありません: {}".format(group))
    return group


def make_edit_curve(group):
    """保存した points から degree 1 のカーブ Truss_<name>_Path (最上位) を作り source_curve にする。
    既に編集用カーブが source_curve なら選択するだけ (ユーザーのカーブが source なら新規に作って差し替える)。戻り値: カーブの transform (long 名)。"""
    group = _path_group(group)
    info = read_info(group)
    cur = info.get("source_curve")
    if cur and is_curve(cur) and cur.split("|")[-1].startswith("Truss_{}_Path".format(info["name"])):
        cmds.select(cur, replace=True)  # 既に編集用カーブがある
        return cmds.ls(cur, long=True)[0]
    pts = _local_to_world(info["points"], group)
    if info.get("closed") and len(pts) > 2:
        pts = pts + [pts[0]]
    crv = cmds.curve(degree=1, point=[tuple(p) for p in pts], name="Truss_{}_Path".format(info["name"]))
    crv = cmds.ls(crv, long=True)[0]
    info["source_curve"] = crv
    _write_info(group, info)
    cmds.select(crv, replace=True)
    return crv


def detach_curve(group):
    """source_curve を null にする (以後はカーブを消しても影響しない)。"""
    group = _path_group(group)
    info = read_info(group)
    info["source_curve"] = None
    _write_info(group, info)
    return group


# ---------------------------------------------------------------- 編集用の点 (ロケータ)

EDIT_LOC_SCALE = 30.0  # ロケータの localScale の既定 (cm 相当。断面サイズに合わせる)
EDIT_COLOR = 17        # 黄
_LOC_RE = re.compile(r"_P(\d+)$")


def _edit_group_of(info):
    """info の edit_points が指す最上位グループの long 名 (存在しなければ None)。"""
    g = info.get("edit_points")
    if g and cmds.objExists(g):
        return cmds.ls(g, long=True)[0]
    return None


def edit_locators(group):
    """編集用ロケータの long 名リスト (名前の番号順)。無ければ空。"""
    egrp = _edit_group_of(read_info(group))
    if not egrp:
        return []
    kids = cmds.listRelatives(egrp, children=True, fullPath=True, type="transform") or []
    numbered = []
    for k in kids:
        m = _LOC_RE.search(k.split("|")[-1])
        if m:
            numbered.append((int(m.group(1)), k))
    return [k for _, k in sorted(numbered)]


def resolve_truss(node):
    """node (トラスのグループ / 部材 / 編集用ロケータ・Edit グループ) から親トラスの long 名。見つからなければ None。"""
    if not node or not cmds.objExists(node):
        return None
    node = cmds.ls(node, long=True)[0]
    chain = []
    cur = node
    while cur:
        chain.append(cur)
        cur = (cmds.listRelatives(cur, parent=True, fullPath=True) or [None])[0]
    for n in chain:
        if is_truss_group(n):
            return n
    for n in chain:
        short = n.split("|")[-1]
        m = re.match(r"^Truss_(.*)_(?:P\d+|Edit\d*)$", short)
        if not m:
            continue
        if _LOC_RE.search(short):
            egrp = (cmds.listRelatives(n, parent=True, fullPath=True) or [None])[0]
        else:
            egrp = n
        cands = [g for g in (cmds.ls("SM_Truss_*", long=True, type="transform") or []) if is_truss_group(g)]
        for g in cands:
            if _edit_group_of(read_info(g)) == egrp:
                return g
        for g in cands:
            if read_info(g).get("name") == m.group(1):
                return g
    return None


def _make_locator(name, world_pos, parent, scale):
    loc = cmds.spaceLocator(name=name)[0]
    loc = cmds.parent(loc, parent)[0]
    loc = cmds.ls(cmds.ls(parent, long=True)[0] + "|" + loc.split("|")[-1], long=True)[0]
    cmds.xform(loc, ws=True, t=[float(v) for v in world_pos])
    shape = cmds.listRelatives(loc, shapes=True, fullPath=True)[0]
    for ax in "XYZ":
        cmds.setAttr("{}.localScale{}".format(shape, ax), scale)
    cmds.setAttr(loc + ".overrideEnabled", 1)
    cmds.setAttr(loc + ".overrideColor", EDIT_COLOR)
    return loc


def _locator_world(loc):
    return cmds.xform(loc, q=True, ws=True, t=True)


def _renumber(egrp, name, ordered):
    """ordered (ロケータ long 名) を Truss_<name>_P01.. に振り直す (衝突しないよう 2 段階)。新しい long 名を返す。"""
    egrp = cmds.ls(egrp, long=True)[0]
    tmp = []
    for i, loc in enumerate(ordered):
        tmp.append(cmds.rename(loc, "MS2026_tmp_{}".format(i)))
    digits = max(2, len(str(len(tmp))))
    out = []
    for i, t in enumerate(tmp):
        new = cmds.rename(egrp + "|" + t.split("|")[-1], "Truss_{}_P{:0{}d}".format(name, i + 1, digits))
        out.append(cmds.ls(egrp + "|" + new.split("|")[-1], long=True)[0])
    return out


def _sync_points_from_locators(group, info, locs):
    info["points"] = _world_to_local([_locator_world(l) for l in locs], group)
    _write_info(group, info)


def make_edit_points(group):
    """パストラスの角ごとに黄色のロケータ Truss_<名前>_P01.. を最上位の Truss_<名前>_Edit の下に world 位置で作る。
    直線 / 門型は先に convert_to_path する。すでに編集用の点があれば作り直さず選択だけ。戻り値: ロケータの long 名リスト。"""
    if not is_truss_group(group):
        raise ValueError("トラスのグループではありません: {}".format(group))
    group = cmds.ls(group, long=True)[0]
    if read_info(group).get("kind") in ("straight", "gate"):
        convert_to_path(group)
    group = _path_group(group)
    info = read_info(group)
    locs = edit_locators(group)
    if locs:
        cmds.select(locs, replace=True)
        return locs
    stale = _edit_group_of(info)
    if stale:
        cmds.delete(stale)  # 中身が空 / 不正なら作り直す
    section = make_params(info.get("params"))["section"]
    egrp = cmds.group(empty=True, name="Truss_{}_Edit".format(info["name"]), world=True)
    egrp = cmds.ls(egrp, long=True)[0]
    world = _local_to_world(info["points"], group)
    digits = max(2, len(str(len(world))))
    locs = [_make_locator("Truss_{}_P{:0{}d}".format(info["name"], i + 1, digits), p, egrp, section)
            for i, p in enumerate(world)]
    info["edit_points"] = egrp
    _write_info(group, info)
    cmds.select(locs, replace=True)
    return locs


def clear_edit_points(group):
    """編集用の点 (Truss_<名前>_Edit) を消し、JSON の edit_points を None に。無くても安全。"""
    group = _path_group(group)
    info = read_info(group)
    egrp = _edit_group_of(info)
    if egrp:
        cmds.delete(egrp)
    if info.get("edit_points") is not None:
        info["edit_points"] = None
        _write_info(group, info)
    return group


def insert_edit_point(group, after_locator):
    """after_locator と次の点の中点に新しい点を挿入して番号を振り直す (閉パスの最後は最初との中点)。戻り値: 新しいロケータの long 名。"""
    group = _path_group(group)
    info = read_info(group)
    locs = edit_locators(group)
    after = cmds.ls(after_locator, long=True)
    if not after or after[0] not in locs:
        raise ValueError("このトラスの編集用の点ではありません: {}".format(after_locator))
    i = locs.index(after[0])
    if i + 1 < len(locs):
        nxt = locs[i + 1]
    elif info.get("closed") and len(locs) > 2:
        nxt = locs[0]
    else:
        raise ValueError("最後の点の後ろには追加できません (閉じていないパス)。最後の手前の点を選んでください")
    a, b = _locator_world(locs[i]), _locator_world(nxt)
    egrp = _edit_group_of(info)
    section = make_params(info.get("params"))["section"]
    new = _make_locator("MS2026_tmp_new", [(x + y) * 0.5 for x, y in zip(a, b)], egrp, section)
    ordered = locs[:i + 1] + [new] + locs[i + 1:]
    ordered = _renumber(egrp, info["name"], ordered)
    _sync_points_from_locators(group, info, ordered)
    return ordered[i + 1]


def delete_edit_point(group, locator):
    """locator を削除して番号を振り直す。点が 2 個未満になる削除は ValueError。戻り値: 残ったロケータの long 名リスト。"""
    group = _path_group(group)
    info = read_info(group)
    locs = edit_locators(group)
    target = cmds.ls(locator, long=True)
    if not target or target[0] not in locs:
        raise ValueError("このトラスの編集用の点ではありません: {}".format(locator))
    if len(locs) - 1 < 2:
        raise ValueError("点は 2 個以上必要です (これ以上削除できません)")
    cmds.delete(target[0])
    rest = [l for l in locs if l != target[0]]
    rest = _renumber(_edit_group_of(info), info["name"], rest)
    _sync_points_from_locators(group, info, rest)
    return rest


def edit_points_preview(group, snap_angle=None, snap_grid=None):
    """ロケータの現在位置 (スナップ適用後) の [(points, closed)] (group ローカル)。ロケータが無ければ ValueError。
    snap_angle / snap_grid が None なら JSON の値。"""
    group = _path_group(group)
    info = read_info(group)
    locs = edit_locators(group)
    if len(locs) < 2:
        raise ValueError("編集用の点がありません")
    closed = bool(info.get("closed"))
    angle = info.get("snap_angle", 0) if snap_angle is None else int(snap_angle)
    grid = info.get("snap_grid", 0) if snap_grid is None else float(snap_grid)
    pts = _world_to_local([_locator_world(l) for l in locs], group)
    return [(snap_points(pts, closed, angle, grid), closed)]


def rebuild(group, **overrides):
    """グループの ms2026_truss JSON から子を消して同じ場所に再生成する。グループ自身の位置・回転は保つ。
    overrides: length / width / height / params(dict) で寸法を差し替えられる (JSON も更新。塔は base_size / base_thickness / sleeve_height も)。
    パス種別: member_len / closed / snap_angle / snap_grid も可 (点列にスナップを適用して保存)。source_curve のカーブが残っていれば再サンプルして点列を更新、
    無ければ保存した points から再生成する (編集用の点 = edit_points のロケータがあれば最優先)。グループ内の手動編集は失われる。戻り値: グループ。"""
    if not is_truss_group(group):
        raise ValueError("トラスのグループではありません: {}".format(group))
    group = cmds.ls(group, long=True)[0]
    info = read_info(group)
    params = make_params(dict(info.get("params", {}), **(overrides.pop("params", None) or {})))
    for k in ("length", "width", "height", "base_size", "base_thickness", "sleeve_height"):
        if overrides.get(k) is not None:
            info[k] = overrides[k]
    info["params"] = params
    if info["kind"] == "path":
        if overrides.get("member_len") is not None:
            info["member_len"] = float(overrides["member_len"])
        if overrides.get("snap_angle") is not None:
            info["snap_angle"] = int(overrides["snap_angle"])
        if overrides.get("snap_grid") is not None:
            info["snap_grid"] = float(overrides["snap_grid"])
        closed = bool(info.get("closed")) if overrides.get("closed") is None else bool(overrides["closed"])
        cur = info.get("source_curve")
        locs = edit_locators(group) if _edit_group_of(info) else []
        if len(locs) >= 2:  # 編集用の点 (ロケータ) が最優先。形を保存 points に書き戻す
            info["points"] = _world_to_local([_locator_world(l) for l in locs], group)
            info["source_curve"] = None  # 後でロケータを消してもカーブに引き戻されない
        elif cur and is_curve(cur):
            pts, curve_closed = sample_curve(cur, info.get("member_len") or DEFAULT_MEMBER_LEN, space=group)
            closed = closed or curve_closed
            if closed and len(pts) > 2 and max(abs(a - b) for a, b in zip(pts[0], pts[-1])) < 1e-4:
                pts.pop()  # 編集用カーブは閉じるとき始点を終点に重ねている (form は open のまま)
            info["points"] = pts
        elif cur:
            cmds.warning("[MS2026] パスのカーブ '{}' が見つからないため、保存した points から再生成します。".format(cur))
        info["closed"] = closed
        info["points"] = snap_points(info["points"], closed, info.get("snap_angle", 0), info.get("snap_grid", 0))
    kids = cmds.listRelatives(group, children=True, fullPath=True, type="transform") or []
    if kids:
        cmds.delete(kids)
    if info["kind"] == "straight":
        _fill_straight(group, info["name"], info["length"], params)
    elif info["kind"] == "gate":
        _fill_gate(group, info["name"], info["width"], info["height"], params)
    elif info["kind"] == "path":
        _fill_path(group, info["name"], info["points"], info["closed"], params)
    elif info["kind"] == "tower":
        _fill_tower(group, info["name"], info["height"], params, info["base_size"], info["base_thickness"],
                    info["sleeve_height"])
    else:
        raise ValueError("未知のトラス種別: {}".format(info["kind"]))
    _write_info(group, info)
    if info["kind"] == "path" and _edit_group_of(info):  # ロケータをスナップ後の位置に揃える
        locs = edit_locators(group)
        world = _local_to_world(info["points"], group)
        if len(locs) == len(world):
            for l, w in zip(locs, world):
                cmds.xform(l, ws=True, t=w)
    return group


# ---------------------------------------------------------------- 直線・門型 -> パス

def _gate_path_points(width, height, section):
    """門型と同じ位置のコの字 4 点 (柱の中心線 = 外側から section/2 内側、柱は全高、梁は柱の中心線間)。"""
    x = width * 0.5 - section * 0.5
    return [[-x, 0.0, 0.0], [-x, float(height), 0.0], [x, float(height), 0.0], [x, 0.0, 0.0]]


def convert_to_path(group):
    """kind が straight / gate のトラスを、同じ寸法・params の kind="path" に作り直す。
    グループの transform・名前は保つ。子は作り直す (手動編集は失われる)。直線 -> 2 点、門型 -> コの字 4 点
    (門型の梁は柱の内側に収まっていたが、パスでは柱の中心線間を結ぶので角で部材が重なる)。
    snap_grid は 0 (点は柱の中心位置で、グリッドの倍数とは限らない)。戻り値: グループ (long 名)。"""
    if not is_truss_group(group):
        raise ValueError("トラスのグループではありません: {}".format(group))
    group = cmds.ls(group, long=True)[0]
    info = read_info(group)
    kind = info.get("kind")
    p = make_params(info.get("params"))
    if kind == "straight":
        half = info["length"] * 0.5
        pts = [[-half, 0.0, 0.0], [half, 0.0, 0.0]]
    elif kind == "gate":
        pts = _gate_path_points(info["width"], info["height"], p["section"])
    elif kind == "path":
        raise ValueError("すでにパスです: {}".format(group))
    elif kind == "tower":
        raise ValueError("塔はパスに変換できません: {}".format(group))
    else:
        raise ValueError("未知のトラス種別: {}".format(kind))
    new = {"kind": "path", "name": info["name"], "points": pts, "closed": False, "source_curve": None,
           "snap_angle": DEFAULT_SNAP_ANGLE, "snap_grid": 0.0, "params": p}
    kids = cmds.listRelatives(group, children=True, fullPath=True, type="transform") or []
    if kids:
        cmds.delete(kids)
    _fill_path(group, new["name"], pts, False, p)
    _write_info(group, new)
    return group


# ---------------------------------------------------------------- 生成前プレビュー

PREVIEW_GROUP = "MS2026_TrussPreviewGrp"
PREVIEW_NAME = "MS2026_TrussPreview"
PREVIEW_COLOR = 17  # 黄
PREVIEW_KINDS = ("straight", "gate", "path", "preset", "points", "arc", "tower")


def preview_points_for(kind, params=None, length=500.0, width=600.0, height=400.0, shape="U", plane="XY",
                       curve=None, member_len=DEFAULT_MEMBER_LEN, world_points=None, closed=False,
                       snap_angle=None, snap_grid=DEFAULT_SNAP_GRID, parent=None,
                       radius=300.0, angle=360.0, base_size=100.0, base_thickness=5.0, sleeve_height=60.0):
    """生成したときの部材中心線を [(points, closed), ...] で返す (点は parent のローカル空間、スナップ適用済み)。
    kind: "straight" (1 本) / "gate" (柱 2 + 梁 1 の 3 本) / "path" (curve から) / "preset" (shape, plane) /
    "points" (world_points を parent のローカルへ) / "arc" (radius, angle, member_len, plane) /
    "tower" (height の柱の中心線 1 本 + base_size のベースの正方形)。snap_angle=None は自動 (path は degree 1 なら 90、滑らかなら 0。
    preset / points は 90)。生成と同じ検証をして、不正なら ValueError。"""
    p = make_params(params)
    s = p["section"]
    if kind == "straight":
        if length <= s:
            raise ValueError("長さ({})は断面({})より長くしてください".format(length, s))
        return [([[-length * 0.5, 0.0, 0.0], [length * 0.5, 0.0, 0.0]], False)]
    if kind == "gate":
        if width <= 2 * s or height <= s:
            raise ValueError("門型の幅({})は断面の 2 倍({})より、高さ({})は断面より大きくしてください".format(width, 2 * s, height))
        x = width * 0.5 - s * 0.5  # build_gate の柱の位置
        return [([[-x, 0.0, 0.0], [-x, float(height), 0.0]], False),
                ([[x, 0.0, 0.0], [x, float(height), 0.0]], False),
                ([[-(width * 0.5 - s), height - s * 0.5, 0.0], [width * 0.5 - s, height - s * 0.5, 0.0]], False)]
    if kind == "tower":
        _check_tower(height, p, base_size, base_thickness, sleeve_height)
        hb = base_size * 0.5
        return [([[0.0, base_thickness, 0.0], [0.0, base_thickness + float(height), 0.0]], False),
                ([[-hb, 0.0, -hb], [hb, 0.0, -hb], [hb, 0.0, hb], [-hb, 0.0, hb]], True)]
    grid = DEFAULT_SNAP_GRID if snap_grid is None else float(snap_grid)
    if kind == "arc":
        pts, c = arc_points(radius, angle, member_len, plane="XZ" if plane is None else plane)
        return [(snap_points(pts, c, 0 if snap_angle is None else int(snap_angle), grid), c)]
    if kind == "path":
        if curve is None:
            raise ValueError("カーブを選択してください")
        angle = (DEFAULT_SNAP_ANGLE if _curve_degree(curve) == 1 else 0) if snap_angle is None else int(snap_angle)
        pts, curve_closed = sample_curve(curve, member_len, space=parent)
        c = bool(closed or curve_closed)
        return [(snap_points(pts, c, angle, grid), c)]
    angle = DEFAULT_SNAP_ANGLE if snap_angle is None else int(snap_angle)
    if kind == "preset":
        pts, c, _ = _preset_final(shape, width, height, plane, s, angle, grid)
        return [(pts, c)]
    if kind == "points":
        if not world_points or len(world_points) < 2:
            raise ValueError("点にする transform (ロケータ等) を 2 つ以上、順番に選択してください")
        return [(snap_points(_world_to_local(world_points, parent), bool(closed), angle, grid), bool(closed))]
    raise ValueError("未知の種類: {}".format(kind))


def parent_world_matrix(parent):
    """parent の world 行列 (16 要素)。parent が無ければ None。"""
    return list(cmds.xform(parent, q=True, ws=True, m=True)) if parent else None


def is_component_editing():
    """CV などコンポーネント編集中か。F8 のコンポーネントモード、右クリックメニューの hilite 方式、
    コンポーネントの選択 (名前に '.' を含む) のいずれか。"""
    if cmds.selectMode(q=True, component=True):
        return True
    if cmds.ls(hilite=True):
        return True
    return any("." in n for n in (cmds.ls(selection=True) or []))


def _restore_selection(saved_sel, saved_hl):
    """選択と hilite (コンポーネント編集中のオブジェクト) を、変わっているときだけ元に戻す。"""
    saved_sel = [n for n in saved_sel if cmds.objExists(n)]
    saved_hl = [n for n in saved_hl if cmds.objExists(n)]
    if (cmds.ls(selection=True, long=True) or []) != saved_sel:
        if saved_sel:
            cmds.select(saved_sel, replace=True)
        else:
            cmds.select(clear=True)
    now_hl = cmds.ls(hilite=True, long=True) or []
    if now_hl != saved_hl:
        if saved_hl:
            cmds.hilite(saved_hl, replace=True)
        elif now_hl:
            cmds.hilite(now_hl, unHilite=True)


def _no_undo(fn):
    """プレビュー処理を Undo 履歴に乗せず、選択 / hilite も変えない (CV 編集中のカーブを外さない)。"""
    def wrapped(*args, **kwargs):
        old_state = cmds.undoInfo(q=True, state=True)
        saved_sel = cmds.ls(selection=True, long=True) or []
        saved_hl = cmds.ls(hilite=True, long=True) or []
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            return fn(*args, **kwargs)
        finally:
            try:
                _restore_selection(saved_sel, saved_hl)
            finally:
                cmds.undoInfo(stateWithoutFlush=bool(old_state))
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


@_no_undo
def clear_preview():
    """プレビューを全部消す (Undo で復活した / 連番になった MS2026_TrussPreviewGrp1.. も)。無くても安全。Undo 履歴に乗らない。"""
    for n in cmds.ls(PREVIEW_NAME + "*", long=True, type="transform") or []:
        if n.count("|") == 1 and cmds.objExists(n):  # 最上位のみ (子は親と一緒に消える)
            cmds.delete(n)


def _preview_curve(points, name, parent):
    """degree 1 のカーブを作って parent の下へ。戻り値: transform の long 名。"""
    tr = cmds.curve(d=1, p=[list(q) for q in points], name=name)
    tr = cmds.parent(tr, parent)[0]
    tr = (cmds.ls(parent, long=True)[0] + "|" + tr.split("|")[-1])
    shape = cmds.listRelatives(tr, shapes=True, fullPath=True)[0]
    cmds.setAttr(shape + ".lineWidth", 3)
    cmds.setAttr(tr + ".overrideEnabled", 1)
    cmds.setAttr(tr + ".overrideColor", PREVIEW_COLOR)
    cmds.setAttr(tr + ".overrideDisplayType", 2)  # Reference: 選択不可
    return tr


@_no_undo
def show_preview(polylines, parent_matrix=None, section=30.0):
    """polylines ([(points, closed), ...]、親ローカル) を最上位の MS2026_TrussPreviewGrp に黄色の degree 1 カーブで出す。
    parent_matrix (16 要素) があれば world へ変換。各ポリラインの始点に section x section の正方形を添える。
    既存のプレビューは先に全部消す。選択は変えない。Undo 履歴に乗らない。戻り値: グループの long 名。"""
    clear_preview()
    mat = om.MMatrix(parent_matrix) if parent_matrix else None
    grp = cmds.group(empty=True, name=PREVIEW_GROUP, world=True)
    grp = cmds.ls(grp, long=True)[0]
    h = section * 0.5
    for i, (points, closed) in enumerate(polylines):
        pts = [list(q) for q in points]
        if mat is not None:
            pts = [[w.x, w.y, w.z] for w in (om.MPoint(*q) * mat for q in pts)]
        line = pts + [pts[0]] if closed and len(pts) > 2 else pts
        suffix = "" if len(polylines) == 1 else "_{}".format(i + 1)
        _preview_curve(line, PREVIEW_NAME + suffix, grp)
        if len(pts) >= 2 and section > 0:
            m = _basis_matrix(pts[0], pts[1])  # 1 スパン目の向きで YZ 断面を始点に置く
            o = om.MPoint(*pts[0])
            ys, zs = om.MVector(*m[4:7]), om.MVector(*m[8:11])
            sq = []
            for a, b in ((-h, -h), (h, -h), (h, h), (-h, h), (-h, -h)):
                q = o + ys * a + zs * b
                sq.append([q.x, q.y, q.z])
            _preview_curve(sq, "{}_Section{}".format(PREVIEW_NAME, i + 1), grp)
    return grp
