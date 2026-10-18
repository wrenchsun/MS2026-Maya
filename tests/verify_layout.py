# -*- coding: utf-8 -*-
"""ディスプレイ・ライト配置往復 (.layout.json) の mayapy 検証。実行:
& "C:\\Program Files\\Autodesk\\Maya2026\\bin\\mayapy.exe" tests\\verify_layout.py"""
import json
import os
import shutil
import sys
import tempfile

import maya.standalone

maya.standalone.initialize(name="python")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "maya", "scripts"))

import maya.cmds as cmds  # noqa: E402

import ms2026_maya_layout as layout  # noqa: E402
import ms2026_maya_settings as settings  # noqa: E402

TOL = 1e-3  # cm / 無次元 (JSON は小数 6 桁)


def mat_close(a, b, tol=TOL):
    return len(a) == len(b) == 16 and all(abs(x - y) <= tol for x, y in zip(a, b))


def trs(tx, ty, tz, rx=0, ry=0, rz=0, sx=1, sy=1, sz=1):
    """テスト用のワールド行列 (Maya の行優先 16 値) を、一時ノード経由で作る。"""
    t = cmds.createNode("transform")
    cmds.xform(t, translation=(tx, ty, tz), rotation=(rx, ry, rz), scale=(sx, sy, sz), worldSpace=True)
    m = cmds.xform(t, query=True, worldSpace=True, matrix=True)
    cmds.delete(t)
    return m


def write_json(path, items, scene="Dev_Test", version=1):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": version, "scene": scene, "units": "cm", "items": items}, f)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def expect_error(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except layout.LayoutError as e:
        return str(e)
    raise AssertionError("LayoutError expected: {} {}".format(args, kw))


def short_names():
    return sorted(n.split("|")[-1] for n in layout.find_placeholders())


def main():
    tmp = tempfile.mkdtemp(prefix="ms2026_layout_")
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")

    # --- 名前の検証
    assert layout.name_problem("Screen_01") is None
    for bad in ("", "画面", "A B", "A:B", "A__B", "A-B", None):
        assert layout.name_problem(bad), bad
    assert layout.parse_node_name("DSP_Flat__Main") == ("display", "Flat", "Main")
    assert layout.parse_node_name("LGT_MsSpot__Key_1") == ("light", "MsSpot", "Key_1")
    assert layout.parse_node_name("LGT_Flat__X") is None  # 接頭辞と kind が合わない
    assert layout.parse_node_name("DSP_Nope__X") is None
    assert len(layout.KINDS) == 12 and layout.category_of("Beam") == "light"
    print("names OK")

    # --- 1. 読み込み: JSON -> ワールド行列と属性
    m_flat = trs(100, 200, 300, 10, 20, 30, 16, 9, 1)
    m_beam = trs(-50, 400, 0, 90, 0, 0, 1, 1, 1)
    m_dup1 = trs(1, 2, 3)
    m_dup2 = trs(4, 5, 6)
    gid1, gid2, gid3, gid4 = ("GlobalObjectId_V1-2-aaaa-%d-0" % i for i in range(1, 5))
    jpath = os.path.join(tmp, "Dev_Test.layout.json")
    write_json(jpath, [
        {"id": gid1, "name": "Main", "category": "display", "kind": "Flat", "matrix": m_flat},
        {"id": gid2, "name": "Key", "category": "light", "kind": "Beam", "matrix": m_beam},
        {"name": "NoId", "category": "display", "kind": "Vision", "matrix": m_flat},
        {"id": gid3, "name": "Twin", "category": "light", "kind": "Strobe", "matrix": m_dup1},
        {"id": gid4, "name": "Twin", "category": "light", "kind": "Strobe", "matrix": m_dup2},
        {"name": "日本語", "category": "display", "kind": "Flat", "matrix": m_flat},      # 不正な名前: スキップ
        {"name": "BadKind", "category": "display", "kind": "Banana", "matrix": m_flat},  # 未知の kind: スキップ
        {"name": "ShortM", "category": "display", "kind": "Flat", "matrix": [0] * 15},    # matrix 不正: スキップ
    ])
    res = layout.import_layout(jpath)
    assert (res["created"], res["updated"], res["skipped"]) == (5, 0, 3), res
    assert res["scene"] == "Dev_Test"
    assert short_names() == ["DSP_Flat__Main", "DSP_Vision__NoId", "LGT_Beam__Key", "LGT_Strobe__Twin", "LGT_Strobe__Twin"], short_names()
    main_n = cmds.ls("DSP_Flat__Main", long=True)[0]
    assert mat_close(layout.world_matrix(main_n), m_flat), layout.world_matrix(main_n)
    assert abs(layout.world_matrix(main_n)[12] - 100) < TOL and abs(layout.world_matrix(main_n)[14] - 300) < TOL
    assert cmds.getAttr(main_n + ".ms2026_id") == gid1
    assert cmds.getAttr(main_n + ".ms2026_kind") == "Flat"
    assert cmds.getAttr(main_n + ".ms2026_category") == "display"
    assert cmds.getAttr(main_n + ".ms2026_layout_scene") == "Dev_Test"
    noid = cmds.ls("DSP_Vision__NoId", long=True)[0]
    assert not cmds.attributeQuery("ms2026_id", node=noid, exists=True)
    assert cmds.listRelatives(main_n, shapes=True), "仮の形がある"
    print("import OK:", res["created"], "created,", res["skipped"], "skipped")

    # --- 保存して開き直しても属性が残る
    scene_file = os.path.join(tmp, "layout_test.ma")
    cmds.file(rename=scene_file)
    cmds.file(save=True, type="mayaAscii")
    cmds.file(new=True, force=True)
    cmds.file(scene_file, open=True, force=True)
    main_n = cmds.ls("DSP_Flat__Main", long=True)[0]
    assert cmds.getAttr(main_n + ".ms2026_id") == gid1 and cmds.getAttr(main_n + ".ms2026_kind") == "Flat"
    assert mat_close(layout.world_matrix(main_n), m_flat)
    print("save/reload OK")

    # --- 同名ノードを含む再読み込み (更新) : id で照合され増えない
    m_flat2 = trs(5, 6, 7, 0, 45, 0, 2, 2, 2)
    write_json(jpath, [
        {"id": gid1, "name": "Renamed_In_Unity", "category": "display", "kind": "Flat", "matrix": m_flat2},
        {"id": gid3, "name": "Twin", "category": "light", "kind": "Strobe", "matrix": m_dup1},
        {"id": gid4, "name": "Twin", "category": "light", "kind": "Strobe", "matrix": m_dup2},
    ])
    res = layout.import_layout(jpath)
    assert (res["created"], res["updated"]) == (0, 3), res
    assert mat_close(layout.world_matrix(main_n), m_flat2)
    assert sorted(res["unmatched"]) == ["DSP_Vision__NoId", "LGT_Beam__Key"], res["unmatched"]  # 消さない
    assert len(layout.find_placeholders()) == 5
    twins = [n for n in layout.find_placeholders() if n.endswith("LGT_Strobe__Twin")]
    ids = sorted(cmds.getAttr(n + ".ms2026_id") for n in twins)
    assert ids == [gid3, gid4], ids
    for n in twins:  # id ごとに正しい行列
        want = m_dup1 if cmds.getAttr(n + ".ms2026_id") == gid3 else m_dup2
        assert mat_close(layout.world_matrix(n), want)
    print("re-import (id match, duplicate names) OK")

    # --- 2. 動かす + 追加 -> 書き出し
    beam_n = cmds.ls("LGT_Beam__Key", long=True)[0]
    cmds.xform(beam_n, worldSpace=True, translation=(10, 20, 30))
    cmds.xform(main_n, worldSpace=True, rotation=(0, 90, 0))
    new_n = layout.add_placeholder("MsSpot", "Added_1", matrix=trs(7, 8, 9, 0, 0, 45, 2, 2, 2))
    assert short_names().count("LGT_MsSpot__Added_1") == 1
    assert not cmds.attributeQuery("ms2026_id", node=new_n, exists=True)
    assert cmds.getAttr(new_n + ".ms2026_category") == "light"
    for bad_name in ("Added_1", "x__y", "日本", "a b", ""):  # 重複 / 不正
        expect_error(layout.add_placeholder, "Flat", bad_name)
    expect_error(layout.add_placeholder, "Nope", "Fine")
    assert len(layout.find_placeholders()) == 6
    out_dir = os.path.join(tmp, "out")
    outp = layout.export_layout(out_dir=out_dir)
    assert outp == os.path.join(out_dir, "Dev_Test.layout.json"), outp
    data = read_json(outp)
    assert data["version"] == 1 and data["scene"] == "Dev_Test" and data["units"] == "cm"
    assert len(data["items"]) == 6
    by = {}
    for it in data["items"]:
        by.setdefault(it["name"], []).append(it)
    for n in layout.find_placeholders():
        short = n.split("|")[-1]
        _cat, _kind, name = layout.parse_node_name(short)
        want = layout.world_matrix(n)
        sid = cmds.getAttr(n + ".ms2026_id") if cmds.attributeQuery("ms2026_id", node=n, exists=True) else None
        hit = [it for it in by[name] if it.get("id") == sid]
        assert len(hit) == 1, (name, sid)
        assert mat_close(hit[0]["matrix"], want), (name, hit[0]["matrix"], want)
        assert hit[0]["kind"] == _kind and hit[0]["category"] == _cat
    # id: Maya でノード名が Main のままでも id は保持 (名前はノード名から)
    assert [it["id"] for it in by["Main"]] == [gid1]
    assert [it["id"] for it in by["Key"]] == [gid2]
    assert sorted(it["id"] for it in by["Twin"]) == [gid3, gid4]
    for nm in ("Added_1", "NoId"):
        assert "id" not in by[nm][0], by[nm][0]
    assert abs(by["Key"][0]["matrix"][12] - 10) < TOL and abs(by["Key"][0]["matrix"][14] - 30) < TOL
    assert len(by["Added_1"][0]["matrix"]) == 16
    print("export OK:", len(data["items"]), "items")

    # --- 書き出した JSON をもう一度読んでも変わらない (往復)
    before = {n: layout.world_matrix(n) for n in layout.find_placeholders()}
    res = layout.import_layout(outp)
    assert (res["created"], res["updated"]) == (0, 6), res
    for n, m in before.items():
        assert mat_close(layout.world_matrix(n), m), n
    print("round trip OK")

    # --- 既存 JSON の scene の値を保つ
    exist = os.path.join(out_dir, "Other.layout.json")
    write_json(exist, [], scene="KeepMe")
    layout.export_layout(path=exist)
    assert read_json(exist)["scene"] == "KeepMe"
    print("keep scene OK")

    # --- 3. 不正な名前・重複・未知 kind は書き出しを拒否する
    cmds.select(clear=True)
    bad_out = os.path.join(tmp, "bad")
    cmds.createNode("transform", name="NotAPlaceholder")  # 属性だけ持つ (名前が置き物の形でない)
    cmds.addAttr("NotAPlaceholder", longName="ms2026_kind", dataType="string")
    cmds.setAttr("NotAPlaceholder.ms2026_kind", "Flat", type="string")
    msg = expect_error(layout.export_layout, out_dir=bad_out)
    assert "NotAPlaceholder" in msg and not os.path.exists(bad_out), msg
    cmds.delete("NotAPlaceholder")
    dupn = cmds.createNode("transform", name="DSP_Flat__Main", parent=cmds.group(empty=True, name="other"))  # 同名 (Main) を id 無しで作る
    dupn = cmds.ls(dupn, long=True)[0]
    msg = expect_error(layout.export_layout, out_dir=bad_out)
    assert "Main" in msg and not os.path.exists(bad_out), msg
    cmds.delete(cmds.ls(dupn, long=True))
    n_kind = cmds.createNode("transform", name="DSP_Flat__KindClash")
    cmds.addAttr(n_kind, longName="ms2026_kind", dataType="string")
    cmds.setAttr(n_kind + ".ms2026_kind", "Beam", type="string")
    msg = expect_error(layout.export_layout, out_dir=bad_out)
    assert "KindClash" in msg, msg
    cmds.delete(n_kind)
    nj = cmds.createNode("transform", name="DSP_Flat__Jp")
    cmds.delete(nj)  # (日本語・記号は Maya の rename 自体が拒否する。name_problem は上で検証済み)
    nj = cmds.createNode("transform", name="DSP_Flat__a__b")  # '__' を含む
    msg = expect_error(layout.export_layout, out_dir=bad_out)
    assert "a__b" in msg, msg
    cmds.delete(nj)
    assert not os.path.exists(bad_out)
    layout.export_layout(out_dir=bad_out)  # 直したら書ける
    print("invalid rejected OK")

    # --- 4. 親が不均一スケール (+ 回転) でもワールド行列が往復で変わらない
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    par = cmds.group(empty=True, name="NonUniformParent")
    cmds.xform(par, translation=(100, -20, 50), rotation=(0, 30, 0), scale=(1, 3, 0.5))
    m_world = trs(11, 22, 33, 25, 40, 15, 2, 4, 1)
    pj = os.path.join(tmp, "Par.layout.json")
    write_json(pj, [{"id": "GlobalObjectId_V1-2-par-1-0", "name": "Under", "category": "display", "kind": "Curved",
                     "matrix": m_world}], scene="Par")
    res = layout.import_layout(pj)
    node = layout.find_placeholders()[0]
    cmds.parent(node, par)  # 不均一スケールの親の下へ (ワールドを保つ)
    node = cmds.ls("DSP_Curved__Under", long=True)[0]
    layout.set_world_matrix(node, m_world)
    got = layout.world_matrix(node)
    assert mat_close(got, m_world, 1e-3), (got, m_world)
    outp = layout.export_layout(out_dir=os.path.join(tmp, "par"))
    it = read_json(outp)["items"][0]
    assert mat_close(it["matrix"], m_world, 1e-3), (it["matrix"], m_world)
    assert it["id"] == "GlobalObjectId_V1-2-par-1-0"
    # 親のスケールを変えたあと、JSON を取り込み直すと元のワールドに戻る
    cmds.xform(par, scale=(2, 1, 4))
    res = layout.import_layout(outp)
    assert res["updated"] == 1 and res["created"] == 0, res
    assert mat_close(layout.world_matrix(node), m_world, 1e-3)
    print("non-uniform parent OK; shear/scale local:", [round(v, 3) for v in cmds.getAttr(node + ".scale")[0]])

    # --- 5. FBX も読み込む (Maya で作った FBX を使う。Unity 実機書き出しではない)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    mw = trs(300, 100, -200, 0, 33, 0, 10, 5, 1)
    ml = trs(0, 500, 0, 90, 0, 0, 1, 1, 1)
    fbx_dir = os.path.join(tmp, "Export")
    os.makedirs(fbx_dir)
    jf = os.path.join(fbx_dir, "FbxScene.layout.json")
    write_json(jf, [
        {"id": "GlobalObjectId_V1-2-f-1-0", "name": "Screen", "category": "display", "kind": "Flat", "matrix": mw},
        {"id": "GlobalObjectId_V1-2-f-2-0", "name": "Lamp", "category": "light", "kind": "Beam", "matrix": ml},
        {"name": "OnlyJson", "category": "light", "kind": "LedBar", "matrix": ml},
    ], scene="FbxScene")
    # FBX 側: Unity の書き出しを模す (ルート _Layout の下に DSP_/LGT_ ノード、JSON と少し違う位置、JSON に無いノードも)
    root = cmds.group(empty=True, name="_Layout")
    for nm, m in (("DSP_Flat__Screen", trs(300, 100, -200, 0, 33, 0, 10, 5, 1)), ("LGT_Beam__Lamp", ml), ("DSP_Flat__Extra", mw)):
        cube = cmds.polyCube(name=nm, constructionHistory=False)[0]
        cmds.parent(cube, root)
        cmds.xform(cube, worldSpace=True, matrix=m)
    fbx = os.path.join(fbx_dir, "Greybox_FbxScene_Layout_20261018.fbx")
    old = os.path.join(fbx_dir, "Greybox_FbxScene_Layout_20260101.fbx")
    cmds.loadPlugin("fbxmaya", quiet=True)
    cmds.select(root)
    import maya.mel as mel
    mel.eval("FBXResetExport")
    mel.eval('FBXExport -f "{}" -s'.format(fbx.replace("\\", "/")))
    shutil.copy(fbx, old)
    assert layout.find_layout_fbx(jf) == fbx, layout.find_layout_fbx(jf)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    res = layout.import_layout(jf, fbx_path=fbx)
    assert res["fbx_nodes"] == 3 and res["updated"] == 2 and res["created"] == 1, res
    assert res["fbx_max_dev_cm"] < 0.01, res
    scr = cmds.ls("*DSP_Flat__Screen", long=True)
    assert len(scr) == 1 and mat_close(layout.world_matrix(scr[0]), mw, 0.01)
    assert cmds.getAttr(scr[0] + ".ms2026_id") == "GlobalObjectId_V1-2-f-1-0"
    assert any("DSP_Flat__Extra" in w for w in res["warnings"]), res["warnings"]
    expect_error(layout.import_layout, jf, fbx_path=fbx)  # 置き物がある -> 置き換え指定が要る
    res = layout.import_layout(jf, fbx_path=fbx, replace=True)
    assert len(layout.find_placeholders()) == 4 and res["created"] == 1, (res, short_names())
    print("fbx import OK:", short_names())

    shutil.rmtree(tmp, ignore_errors=True)
    print("VERIFY OK: layout")


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
    cmds.file(new=True, force=True)
    maya.standalone.uninitialize()
except Exception:  # noqa: BLE001
    pass
sys.exit(0 if ok else 1)
