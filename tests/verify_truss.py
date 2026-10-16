# -*- coding: utf-8 -*-
"""トラス生成の mayapy 検証。実行:
& "C:\\Program Files\\Autodesk\\Maya2026\\bin\\mayapy.exe" tests\\verify_truss.py"""
import json
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
    print("VERIFY OK: boxes={} (gate 3 + straight 1) out={}".format(len(cols), out))


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
