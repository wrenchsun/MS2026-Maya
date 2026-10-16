# -*- coding: utf-8 -*-
"""トラス生成の mayapy 検証。実行:
& "C:\\Program Files\\Autodesk\\Maya2026\\bin\\mayapy.exe" tests\\verify_truss.py"""
import json
import math
import os
import sys
import tempfile

import maya.standalone

maya.standalone.initialize(name="python")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "maya", "scripts"))

import maya.cmds as cmds  # noqa: E402

import ms2026_maya_settings as settings  # noqa: E402
import ms2026_maya_tools as tools  # noqa: E402
import ms2026_maya_truss as truss  # noqa: E402


def near(a, b, tol=5.0):  # 斜材の端面が部材端から数 cm はみ出す分を許容
    return abs(a - b) <= tol


def main():
    # ツール全体のリロード (standalone。ウィンドウなし) を 1 回通してから検証を続ける
    import ms2026_maya_reload
    global settings, tools, truss
    names = ms2026_maya_reload.reload_all(reopen=False)
    assert len(names) >= 1, names
    print("reload_all:", len(names), "modules")
    import ms2026_maya_settings as settings
    import ms2026_maya_tools as tools
    import ms2026_maya_truss as truss
    assert os.path.isfile(tools.manual_path()), tools.manual_path()
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    top = cmds.group(empty=True, name="SM_Bg_TrussTest", world=True)
    gate = truss.build_gate("Gate", 600, 400, parent=top)
    line = truss.build_straight("Line", 500, parent=top)
    members = sorted(m.split("|")[-1] for m in cmds.ls(top, dag=True, long=True, type="transform") if m.split("|")[-1].startswith("SC_"))
    print("members:", members)
    assert members == ["SC_Truss_Gate_Beam", "SC_Truss_Gate_PostL", "SC_Truss_Gate_PostR", "SC_Truss_Line"], members
    for m in cmds.ls(top, dag=True, long=True, type="transform"):
        if m.split("|")[-1].startswith("SC_"):
            assert len(cmds.listRelatives(m, shapes=True, type="mesh")) == 1, m

    problems = tools.check_selection([top])
    assert not problems, problems

    out = tempfile.mkdtemp(prefix="ms2026_truss_")
    settings.set_dir("block_out_dir", out)
    cmds.select(top)
    path = tools.export_block(top=top)
    assert path and os.path.isfile(path), path
    jpath = os.path.splitext(path)[0] + ".colliders.json"
    data = json.load(open(jpath, encoding="utf-8"))
    cols = data["colliders"]
    assert data["version"] == 1 and len(cols) == 4, data
    assert all(c["shape"] == "box" for c in cols), cols
    by = {c["path"].split("/")[-1]: c for c in cols}
    exp = {"SC_Truss_Gate_PostL": (400, 30, 30), "SC_Truss_Gate_PostR": (400, 30, 30),
           "SC_Truss_Gate_Beam": (540, 30, 30), "SC_Truss_Line": (500, 30, 30)}
    for k, e in exp.items():
        sz = by[k]["size"]
        print("{}: size={} center={}".format(k, [round(v, 2) for v in sz], [round(v, 2) for v in by[k]["center"]]))
        assert all(near(a, b) for a, b in zip(sz, e)), (k, sz, e)

    # 再生成: 寸法を変えて子が置き換わること
    truss.rebuild(gate, width=800, height=500)
    assert not tools.check_selection([top])
    beam = cmds.ls("*SC_Truss_Gate_Beam", long=True)
    assert len(beam) == 1, beam
    info = truss.read_info(gate)
    assert info["width"] == 800 and info["height"] == 500, info
    print("rebuild OK:", info["kind"], info["width"], info["height"])

    # 親なし (world): SM_Bg_ の外でも最上位に SM_Truss_ グループができる
    g2 = truss.build_gate("Free", 600, 400)
    l2 = truss.build_straight("FreeLine", 300)
    for g in (g2, l2):
        assert cmds.listRelatives(g, parent=True) is None, g
        assert truss.is_truss_group(g) and g.startswith("|SM_Truss_"), g
    assert sorted(c.split("|")[-1] for c in cmds.listRelatives(g2, children=True, fullPath=True)) == [
        "SC_Truss_Free_Beam", "SC_Truss_Free_PostL", "SC_Truss_Free_PostR"]
    g2 = truss.rebuild(g2, width=700)
    assert cmds.listRelatives(g2, parent=True) is None and truss.read_info(g2)["width"] == 700
    print("world parent OK:", g2, l2)

    verify_path(settings, tools)
    verify_snap(settings, tools)
    print("VERIFY OK: boxes={} (gate 3 + straight 1) out={}".format(len(cols), out))


def _members(grp):
    return sorted(cmds.listRelatives(grp, children=True, fullPath=True, type="transform") or [])


def _ext(node, axis):
    bb = cmds.exactWorldBoundingBox(node)
    return bb[3 + axis] - bb[axis]


def _extent(node):
    bb = cmds.exactWorldBoundingBox(node)
    return max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])


def _export(top, tag):
    out = tempfile.mkdtemp(prefix="ms2026_truss_" + tag)
    settings.set_dir("block_out_dir", out)
    cmds.select(top)
    path = tools.export_block(top=top)
    assert path and os.path.isfile(path), path
    data = json.load(open(os.path.splitext(path)[0] + ".colliders.json", encoding="utf-8"))
    assert data["version"] == 1, data
    return data["colliders"]


def verify_path(settings, tools):
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    # --- コの字 (degree 1) -> 3 部材
    crv = cmds.curve(degree=1, point=[(-300, 0, 0), (-300, 400, 0), (300, 400, 0), (300, 0, 0)], name="uCurve")
    top = cmds.group(empty=True, name="SM_Bg_PathTest", world=True)
    grp = truss.build_from_curve("U", crv, parent=top)
    kids = _members(grp)
    names = [k.split("|")[-1] for k in kids]
    assert names == ["SC_Truss_U_01", "SC_Truss_U_02", "SC_Truss_U_03"], names
    info = truss.read_info(grp)
    assert info["kind"] == "path" and info["closed"] is False and len(info["points"]) == 4, info
    assert info["source_curve"] == cmds.ls(crv, long=True)[0], info
    assert not tools.check_selection([top]), tools.check_selection([top])
    cols = _export(top, "U")
    assert len(cols) == 3 and all(c["shape"] == "box" for c in cols), cols
    maxes = sorted(max(c["size"]) for c in cols)
    print("U boxes max axis:", [round(m, 1) for m in maxes])
    assert all(abs(a - b) <= 10 for a, b in zip(maxes, [400, 400, 600])), maxes

    # --- CV を動かして rebuild -> 1 本目 (縦) が 400 -> 500
    first = [k for k in kids if k.endswith("SC_Truss_U_01")][0]
    before = _extent(first)
    cmds.move(0, 100, 0, crv + ".cv[1]", relative=True)
    truss.rebuild(grp)
    first = [k for k in _members(grp) if k.endswith("SC_Truss_U_01")][0]
    after = _extent(first)
    print("CV move: member01 extent {:.1f} -> {:.1f}".format(before, after))
    assert after - before > 60, (before, after)
    assert len(_members(grp)) == 3 and not tools.check_selection([top])

    # --- make_edit_curve / detach_curve / curve deleted fallback
    c1 = truss.make_edit_curve(grp)
    assert cmds.objExists(c1) and cmds.listRelatives(c1, parent=True) is None, c1
    assert c1.split("|")[-1].startswith("Truss_U_Path"), c1
    info = truss.read_info(grp)
    assert info["source_curve"] == c1 and info["source_curve"] != cmds.ls(crv, long=True)[0], info
    assert truss.make_edit_curve(grp) == c1  # 既存なら選択だけ
    cmds.delete(crv)  # 元のカーブを消しても source は編集用カーブ
    cmds.move(0, 0, 100, c1 + ".cv[3]", relative=True)
    truss.rebuild(grp, snap_angle=0)  # 90 度スナップだと z のずれは消える。ここは「なし」で確認
    assert abs(truss.read_info(grp)["points"][3][2] - 100) < 1e-3
    truss.detach_curve(grp)
    assert truss.read_info(grp)["source_curve"] is None
    cmds.delete(c1)
    pts_before = truss.read_info(grp)["points"]
    truss.rebuild(grp, params={"section": 40})
    info = truss.read_info(grp)
    assert info["points"] == pts_before and len(_members(grp)) == 3 and info["params"]["section"] == 40
    # source_curve が残ったままカーブだけ消えた場合も points で動く (warning 1 行)
    c2 = truss.make_edit_curve(grp)
    cmds.delete(c2)
    truss.rebuild(grp)
    assert len(_members(grp)) == 3 and not tools.check_selection([top])
    print("edit curve / detach / fallback OK")

    # --- 円 (degree 3, 閉) -> 9 部材
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    circ = cmds.circle(radius=300, degree=3, normal=(0, 1, 0), name="ringCurve", constructionHistory=False)[0]
    top = cmds.group(empty=True, name="SM_Bg_RingTest", world=True)
    grp = truss.build_from_curve("Ring", circ, parent=top, member_len=200)
    info = truss.read_info(grp)
    n = int(round(2 * math.pi * 300 / 200))
    assert n == 9 and len(_members(grp)) == 9 and info["closed"] is True and len(info["points"]) == 9, (n, info["closed"])
    assert not tools.check_selection([top])
    cols = _export(top, "Ring")
    assert len(cols) == 9 and all(c["shape"] == "box" for c in cols), len(cols)
    print("Ring: members={} boxes={} max axis={}".format(
        len(_members(grp)), len(cols), sorted(round(max(c["size"]), 1) for c in cols)))
    assert all(150 <= max(c["size"]) <= 260 for c in cols)

    # --- 親にオフセットがあるとき: 親ローカルへ変換される / world 親でも動く
    off = cmds.group(empty=True, name="SM_Bg_Offset", world=True)
    cmds.xform(off, t=(1000, 0, 0))
    crv2 = cmds.curve(degree=1, point=[(1000, 0, 0), (1500, 0, 0)], name="offCurve")
    g3 = truss.build_from_curve("Off", crv2, parent=off)
    assert abs(truss.read_info(g3)["points"][0][0]) < 1e-3, truss.read_info(g3)["points"]
    g4 = truss.build_from_curve("Free", crv2)
    assert cmds.listRelatives(g4, parent=True) is None and abs(truss.read_info(g4)["points"][0][0] - 1000) < 1e-3
    print("path parent space OK")


def _axis_dot(member):
    """部材の world 行列の X 軸 (単位) の、world 軸との最大 |dot|。"""
    m = cmds.xform(member, q=True, ws=True, m=True)
    x = m[0:3]
    n = math.sqrt(sum(v * v for v in x))
    return max(abs(v) for v in x) / n


def verify_snap(settings, tools):
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    # --- 少しずれたコの字 -> 軸に平行・長さ 400/600/400
    pts = [(-300, 0, 0), (-298, 402, 3), (301, 399, 0), (300, -2, 0)]
    grp = truss.build_path("Skew", pts, snap_angle=90, snap_grid=10)
    kids = _members(grp)
    assert len(kids) == 3, kids
    expect = [400, 600, 400]
    for k, e in zip(kids, expect):
        assert _axis_dot(k) > 0.999, (k, cmds.xform(k, q=True, ws=True, m=True))
        ext = _extent(k)
        print("snap U member {}: extent {:.1f} (expect {})".format(k.split("|")[-1], ext, e))
        assert abs(ext - e) <= 5, (k, ext, e)
    info = truss.read_info(grp)
    assert info["snap_angle"] == 90 and info["snap_grid"] == 10, info
    assert info["points"] == [[-300, 0, 0], [-300, 400, 0], [300, 400, 0], [300, 0, 0]], info["points"]
    # snap_points 単体: 45 度 / 角度なし / 閉じるスパン
    p45 = truss.snap_points([(0, 0, 0), (300, 310, 0), (700, 300, 0)], False, 45, 10)
    assert p45[1] == [310, 310, 0] or p45[1] == [300, 300, 0] or abs(p45[1][0] - p45[1][1]) < 1e-6, p45
    assert truss.snap_points([(3, 4, 6)], False, 0, 10) == [[0, 0, 10]]
    assert truss.snap_points([(3, 4, 5)], False, 0, 0) == [[3, 4, 5]]
    print("snap_points OK:", p45)

    # --- プリセット
    for kind, n, closed in (("line", 1, False), ("L", 2, False), ("U", 3, False), ("rect", 4, True)):
        g = truss.build_preset("P" + kind, kind, 600, 400)
        i = truss.read_info(g)
        assert len(_members(g)) == n and i["closed"] is closed and i["source_curve"] is None, (kind, i)
        print("preset {}: members={} closed={}".format(kind, n, closed))
    # 床の上に乗る: U の柱 / line / rect の最下端が y=0 付近
    gu = truss.build_preset("FloorU", "U", 600, 400)
    post = [k for k in _members(gu) if cmds.exactWorldBoundingBox(k)[4] - cmds.exactWorldBoundingBox(k)[1] > 300][0]
    ymin = cmds.exactWorldBoundingBox(post)[1]
    print("U post min y = {:.2f}".format(ymin))
    assert abs(ymin) <= 2, ymin  # 斜材の端面が部材端から約 1.5 はみ出す分を許容
    for kind in ("line", "rect"):
        gk = truss.build_preset("Floor" + kind, kind, 600, 400)
        ymin = min(cmds.exactWorldBoundingBox(k)[1] for k in _members(gk))
        print("{} min y = {:.2f}".format(kind, ymin))
        assert abs(ymin) <= 1, (kind, ymin)
    g = truss.build_preset("Ring", "rect", 600, 400, plane="XZ")
    pts = truss.read_info(g)["points"]
    assert len(_members(g)) == 4 and all(abs(p[1]) < 1e-6 for p in pts), pts
    assert truss.make_edit_curve(g) and truss.rebuild(g)  # 後から編集用カーブで再生成できる
    assert len(_members(g)) == 4 and len(truss.read_info(g)["points"]) == 4, truss.read_info(g)["points"]
    # 短すぎるスパンはスキップして続ける
    g = truss.build_path("Short", [(0, 0, 0), (0, 10, 0), (0, 410, 0)], snap_angle=90, snap_grid=10)
    assert len(_members(g)) == 1, _members(g)

    # --- ロケータの選択順
    locs = [cmds.spaceLocator(name="loc%d" % i)[0] for i in range(3)]
    want = [(500, 0, 0), (-200, 100, 50), (0, 300, -400)]
    for l, p in zip(locs, want):
        cmds.xform(l, ws=True, t=p)
    cmds.select(locs[2], locs[0], locs[1], replace=True)
    got = truss.points_from_selection()
    exp = [want[2], want[0], want[1]]
    assert all(max(abs(a - b) for a, b in zip(g_, e)) < 1e-4 for g_, e in zip(got, exp)), got
    cmds.select(locs[0], replace=True)
    try:
        truss.points_from_selection()
        raise AssertionError("1 点でエラーにならない")
    except ValueError:
        pass
    cmds.select(locs, replace=True)
    gp = truss.build_from_points("Loc", truss.points_from_selection(), snap_angle=90, snap_grid=10)
    assert truss.is_truss_group(gp) and len(_members(gp)) >= 1
    print("snap / preset / selection OK")

    # --- 生成前プレビュー
    pg = truss.preview_points_for("gate", width=600, height=400)
    assert len(pg) == 3 and all(len(pts) == 2 and not c for pts, c in pg), pg
    ps = truss.preview_points_for("straight", length=500)
    assert len(ps) == 1 and len(ps[0][0]) == 2
    pu = truss.preview_points_for("preset", shape="U", width=600, height=400, plane="XY")
    assert len(pu) == 1 and len(pu[0][0]) == 4 and not pu[0][1], pu
    pr = truss.preview_points_for("preset", shape="rect", width=600, height=400, plane="XZ")
    assert len(pr) == 1 and pr[0][1] and len(pr[0][0]) == 4, pr
    # 生成結果と一致 (プリセット U の点列 = 保存された points)
    gu = truss.build_preset("PrevU", "U", 600, 400)
    assert [list(map(float, q)) for q in truss.read_info(gu)["points"]] == [list(map(float, q)) for q in pu[0][0]]
    ck = cmds.curve(degree=1, p=[(0, 0, 0), (0, 400, 7), (500, 403, 0)], name="prevCrv")
    pc = truss.preview_points_for("path", curve=ck)
    gc = truss.build_from_curve("PrevC", ck)
    assert len(pc) == 1 and len(pc[0][0]) == 3
    assert len(_members(gc)) == len(pc[0][0]) - 1
    cmds.select(locs, replace=True)
    pp = truss.preview_points_for("points", world_points=truss.points_from_selection())
    assert len(pp) == 1 and len(pp[0][0]) == 3
    try:
        truss.preview_points_for("gate", width=40, height=400)
        raise AssertionError("不正な寸法でエラーにならない")
    except ValueError:
        pass
    truss.clear_preview()  # 無くても安全
    pv = cmds.group(empty=True, name="SM_Bg_PrevParent", world=True)
    cmds.xform(pv, ws=True, t=(100, 0, 50))
    sel_before = cmds.ls(selection=True, long=True)
    mat = truss.parent_world_matrix(pv)
    assert truss.parent_world_matrix(None) is None
    for _ in range(2):  # 2 回呼んでも増えない
        grp_p = truss.show_preview(pg, mat, 30)
    assert cmds.ls("MS2026_TrussPreviewGrp") == ["MS2026_TrussPreviewGrp"], cmds.ls("MS2026_TrussPreview*")
    assert cmds.listRelatives("MS2026_TrussPreviewGrp", parent=True) is None
    curves = cmds.listRelatives("MS2026_TrussPreviewGrp", children=True, type="transform")
    assert len(curves) == 3 + 3, curves  # 3 本 + 始点の断面 3 つ
    assert cmds.getAttr(curves[0] + ".overrideDisplayType") == 2
    first = cmds.pointPosition(curves[0] + ".cv[0]", world=True)
    assert near(first[0], 100 - 285, 0.01) and near(first[2], 50, 0.01), first  # 親の位置が反映される
    assert cmds.ls(selection=True, long=True) == sel_before
    truss.show_preview(pu, None, 30)
    assert len(cmds.listRelatives("MS2026_TrussPreviewGrp", children=True, type="transform")) == 2
    truss.clear_preview()
    assert not cmds.objExists("MS2026_TrussPreviewGrp")
    truss.clear_preview()

    # --- 直線・門型 -> パス
    cg = truss.build_gate("ConvG", 600, 400)
    cmds.xform(cg, ws=True, t=(1000, 0, 200))
    pos = cmds.xform(cg, q=True, ws=True, t=True)
    cgg = truss.convert_to_path(cg)
    info = truss.read_info(cgg)
    assert info["kind"] == "path" and cgg == cg and len(info["points"]) == 4, info
    mem = _members(cgg)
    assert len(mem) == 3, mem
    assert cg.split("|")[-1] == "SM_Truss_ConvG"
    assert all(a == b for a, b in zip(pos, cmds.xform(cgg, q=True, ws=True, t=True))), pos
    posts = [m for m in mem if abs(_ext(m, 1) - 400) <= 5]
    assert len(posts) == 2, [(m, _ext(m, 1)) for m in mem]
    beam = [m for m in mem if m not in posts][0]
    # 梁は柱の中心線間 (幅 600 - 断面 30 = 570)。+3 は斜材のはみ出し
    assert near(_ext(beam, 0), 570), _ext(beam, 0)
    try:
        truss.convert_to_path(cgg)
        raise AssertionError("パスの変換でエラーにならない")
    except ValueError:
        pass
    crv = truss.make_edit_curve(cgg)
    assert truss.is_curve(crv)
    truss.rebuild(cgg)
    assert len(_members(cgg)) == 3
    cs = truss.build_straight("ConvS", 500)
    cmds.xform(cs, ws=True, t=(0, 0, -300))
    truss.convert_to_path(cs)
    assert len(truss.read_info(cs)["points"]) == 2 and len(_members(cs)) == 1
    assert near(_ext(_members(cs)[0], 0), 500, 5)
    assert cmds.xform(cs, q=True, ws=True, t=True) == [0.0, 0.0, -300.0]

    # --- プレビューは Undo 履歴に乗らない / 連番も消す / チャンクは 1 回の Undo
    cmds.undoInfo(state=True)
    cmds.select(clear=True)
    marker = cmds.group(empty=True, name="UndoMarker")
    before = cmds.undoInfo(q=True, undoName=True)
    sel_u = cmds.ls(selection=True, long=True)
    for _ in range(3):
        truss.show_preview(pg, None, 30)
        truss.clear_preview()
    truss.show_preview(pg, None, 30)
    assert cmds.undoInfo(q=True, undoName=True) == before, (before, cmds.undoInfo(q=True, undoName=True))
    assert cmds.undoInfo(q=True, state=True) is True
    assert cmds.ls(selection=True, long=True) == sel_u
    truss.clear_preview()
    for _ in range(3):
        cmds.group(empty=True, name="MS2026_TrussPreviewGrp", world=True)
    assert len(cmds.ls("MS2026_TrussPreview*")) == 3
    truss.clear_preview()
    assert not cmds.ls("MS2026_TrussPreview*"), cmds.ls("MS2026_TrussPreview*")
    cmds.undoInfo(openChunk=True, chunkName="MS2026 test")
    try:
        ug = truss.build_gate("UndoGate", 600, 400)
    finally:
        cmds.undoInfo(closeChunk=True)
    assert cmds.objExists(ug)
    cmds.undo()
    assert not cmds.objExists(ug), "チャンクが 1 回の Undo で戻らない"
    print("preview undo OK")

    # --- コンポーネント編集 (CV モード) 中でもカーブの hilite / モードを壊さない
    cv = cmds.curve(d=1, p=[(0, 0, 0), (100, 0, 0), (100, 0, 100)], name="HlCurve")
    cv = cmds.ls(cv, long=True)[0]
    cmds.select(cv)
    cmds.selectMode(component=True)
    cmds.hilite(cv)
    cmds.select(clear=True)
    assert cv in (cmds.ls(hilite=True, long=True) or [])
    mode_before = cmds.selectMode(q=True, component=True)  # standalone では False のまま (GUI でのみ True)
    truss.show_preview(pg, None, 30)
    truss.clear_preview()
    truss.show_preview(pg, None, 30)
    assert cv in (cmds.ls(hilite=True, long=True) or []), cmds.ls(hilite=True, long=True)
    assert cmds.selectMode(q=True, component=True) == mode_before
    assert not cmds.ls(selection=True), cmds.ls(selection=True)
    truss.clear_preview()
    assert cv in (cmds.ls(hilite=True, long=True) or [])
    assert cmds.selectMode(q=True, component=True) == mode_before
    assert truss.is_component_editing()  # hilite だけ (selectMode は object のまま) でも True
    cmds.hilite(cv, unHilite=True)
    cmds.selectMode(object=True)
    assert not truss.is_component_editing()
    cmds.select(cv + ".cv[0]")
    assert truss.is_component_editing()  # コンポーネント選択
    cmds.select(clear=True)
    assert not truss.is_component_editing()
    marker2 = cmds.group(empty=True, name="ObjSelMarker")
    cmds.select(marker2)
    sel_o = cmds.ls(selection=True, long=True)
    truss.show_preview(pg, None, 30)
    assert cmds.ls(selection=True, long=True) == sel_o
    truss.clear_preview()
    assert cmds.ls(selection=True, long=True) == sel_o
    print("preview component mode OK")
    # --- 編集用の点 (ロケータ方式)
    cmds.select(clear=True)
    eg = truss.build_preset("EditU", "U", 600, 400)
    ei = truss.read_info(eg)
    locs = truss.make_edit_points(eg)
    assert len(locs) == 4, locs
    egrp = truss.read_info(eg)["edit_points"]
    assert egrp.count("|") == 1 and egrp.endswith("Truss_EditU_Edit"), egrp
    assert [l.split("|")[-1] for l in locs] == ["Truss_EditU_P0{}".format(i) for i in (1, 2, 3, 4)], locs
    assert all(l.startswith(egrp + "|") for l in locs)
    world = truss._local_to_world(ei["points"], eg)
    for l, w in zip(locs, world):
        assert max(abs(a - b) for a, b in zip(cmds.xform(l, q=True, ws=True, t=True), w)) < 0.01, (l, w)
    assert truss.make_edit_points(eg) == locs  # 作り直さない
    assert truss.resolve_truss(locs[1]) == eg and truss.resolve_truss(egrp) == eg
    def _ymax(g):
        return max(cmds.exactWorldBoundingBox(m)[4] for m in cmds.listRelatives(g, children=True, fullPath=True, type="transform"))
    y0 = _ymax(eg)
    for l in locs[1:3]:  # 上の 2 点
        cmds.xform(l, ws=True, r=True, t=(0, 100, 0))
    truss.rebuild(eg)
    y1 = _ymax(eg)
    assert abs((y1 - y0) - 100) < 1.0, (y0, y1)
    sp = truss.read_info(eg)["points"]
    assert abs(sp[1][1] - (ei["points"][1][1] + 100)) < 0.01, sp
    for l, w in zip(truss.edit_locators(eg), truss._local_to_world(sp, eg)):
        assert max(abs(a - b) for a, b in zip(cmds.xform(l, q=True, ws=True, t=True), w)) < 0.01
    # スナップ後に揃う: 少しずらして rebuild すると 10 cm グリッドに戻る
    cmds.xform(locs[0], ws=True, r=True, t=(3, 0, 0))
    truss.rebuild(eg, snap_grid=10.0)
    wx = cmds.xform(locs[0], q=True, ws=True, t=True)[0]
    assert abs(wx / 10.0 - round(wx / 10.0)) < 1e-6, wx
    print("edit points move / rebuild OK")
    nl = truss.insert_edit_point(eg, truss.edit_locators(eg)[0])
    assert len(truss.edit_locators(eg)) == 5 and nl.split("|")[-1] == "Truss_EditU_P02", nl
    assert len(truss.read_info(eg)["points"]) == 5
    truss.rebuild(eg)
    assert len([m for m in cmds.listRelatives(eg, children=True, type="transform")]) == 4
    rest = truss.delete_edit_point(eg, truss.edit_locators(eg)[1])
    assert len(rest) == 4 and len(truss.read_info(eg)["points"]) == 4
    print("edit points insert / delete OK")
    eg2 = truss.build_preset("EditRing", "rect", 600, 400)
    assert len(truss.make_edit_points(eg2)) == 4  # 閉パスでも点は重複しない
    l4 = truss.edit_locators(eg2)
    n2 = truss.insert_edit_point(eg2, l4[-1])  # 閉パスの最後 -> 最初との中点
    assert len(truss.edit_locators(eg2)) == 5
    truss.clear_edit_points(eg2)
    assert not cmds.objExists(truss.read_info(eg2).get("edit_points") or "|none") and truss.read_info(eg2)["edit_points"] is None
    truss.rebuild(eg2)
    truss.clear_edit_points(eg2)  # 無くても安全
    pts_before = truss.read_info(eg)["points"]
    truss.clear_edit_points(eg)
    assert not cmds.objExists(egrp) and truss.read_info(eg)["edit_points"] is None
    truss.rebuild(eg)
    assert truss.read_info(eg)["points"] == pts_before or all(
        max(abs(a - b) for a, b in zip(p, q)) < 0.01 for p, q in zip(truss.read_info(eg)["points"], pts_before))
    assert abs(_ymax(eg) - y1) < 1.0  # ロケータを消しても形が残る
    print("edit points clear OK")
    sg = truss.build_straight("EditLine", 500)
    sl = truss.make_edit_points(sg)
    assert truss.read_info(sg)["kind"] == "path" and len(sl) == 2, truss.read_info(sg)["kind"]
    try:
        truss.delete_edit_point(sg, sl[0])
        raise AssertionError("2 点未満になる削除が通った")
    except ValueError:
        pass
    gg = truss.build_gate("EditGate", 600, 400)
    assert len(truss.make_edit_points(gg)) == 4 and truss.read_info(gg)["kind"] == "path"
    print("edit points straight / gate OK")
    print("preview / convert_to_path OK")


ok = False
try:
    main()
    ok = True
except Exception:
    import traceback
    traceback.print_exc()
    print("VERIFY FAILED")
sys.stdout.flush()
try:
    cmds.file(new=True, force=True)  # 保存確認ダイアログ/クラッシュ保存を避ける
    maya.standalone.uninitialize()
except Exception:  # noqa: BLE001
    pass
sys.exit(0 if ok else 1)
