# -*- coding: utf-8 -*-
"""トラス生成ウィンドウ (GUI 専用)。ms2026_maya_ui のメニューから開く。"""
import maya.cmds as cmds

WINDOW = "MS2026TrussWindow"
F_NAME, F_KIND, F_LEN, F_WIDTH, F_HEIGHT = ("MS2026TrussName", "MS2026TrussKind", "MS2026TrussLength",
                                            "MS2026TrussWidth", "MS2026TrussHeight")
F_SECTION, F_CHORD, F_SEG, STATUS = "MS2026TrussSection", "MS2026TrussChord", "MS2026TrussSeg", "MS2026TrussStatus"
F_MEMBER, F_CLOSED = "MS2026TrussMemberLen", "MS2026TrussClosed"
F_SHAPE, F_PLANE = "MS2026TrussShape", "MS2026TrussPlane"
F_ANGLE, F_GRID = "MS2026TrussSnapAngle", "MS2026TrussSnapGrid"
F_PREVIEW = "MS2026TrussPreview"
OPT_PREVIEW = "ms2026_truss_preview"

K_STRAIGHT, K_GATE, K_PATH, K_PRESET, K_POINTS = 1, 2, 3, 4, 5  # 種類メニューの選択番号
SHAPES = ("line", "L", "U", "rect")
PLANES = ("XY", "XZ")
KIND_KEYS = {K_STRAIGHT: "straight", K_GATE: "gate", K_PATH: "path", K_PRESET: "preset", K_POINTS: "points"}
HINTS = {
    K_STRAIGHT: "直線: 長さを入れて生成。原点は部材の中心",
    K_GATE: "門型: 幅（柱の外側どうし）と高さ（梁の上端）を入れる。原点は床面の中央",
    K_PATH: "パス（カーブから）: カーブを 1 本選ぶ。角のあるカーブはそのまま、滑らかなカーブは部材長で分割",
    K_PRESET: "形プリセット: 形・平面・幅・高さを選ぶ。直角にスナップされる",
    K_POINTS: "選択した点から: ロケータ等を順に選ぶ（2 個以上）",
}
ANGLES = (None, 0, 45, 90)  # 角度メニュー: 自動 / なし / 45° / 90°。自動 = None (ポリライン 90、滑らかなカーブ 0)


RELOAD_ALL = "import importlib, ms2026_maya_reload as r; importlib.reload(r); r.reload_all()"


def _reload_deferred():
    """リロードで自分のウィンドウが消えるので、コールバックを抜けてから実行する。"""
    cmds.evalDeferred(RELOAD_ALL)


def _truss():
    import ms2026_maya_truss as t
    return t


def _status(msg):
    if cmds.text(STATUS, exists=True):
        cmds.text(STATUS, edit=True, label=msg)


def _undo_chunk(name):
    """処理全体を 1 回の Ctrl+Z で戻せる Undo チャンクにする。"""
    def deco(fn):
        def wrapped(*args, **kwargs):
            cmds.undoInfo(openChunk=True, chunkName=name)
            try:
                return fn(*args, **kwargs)
            finally:
                cmds.undoInfo(closeChunk=True)
        wrapped.__name__ = fn.__name__
        wrapped.__doc__ = fn.__doc__
        return wrapped
    return deco


def _guard(fn):
    def run(*_):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _status("エラー: {}".format(e))
            cmds.warning("[MS2026] {}".format(e))
    return run


def _params():
    t = _truss()
    return {"section": cmds.floatFieldGrp(F_SECTION, q=True, value1=True),
            "chord_dia": cmds.floatFieldGrp(F_CHORD, q=True, value1=True),
            "seg_len": cmds.floatFieldGrp(F_SEG, q=True, value1=True),
            "brace_dia": t.DEFAULT_PARAMS["brace_dia"]}


def _kind():
    return cmds.optionMenu(F_KIND, q=True, select=True)


def _is_gate():
    return _kind() == K_GATE


def _is_path():
    return _kind() == K_PATH


def _is_preset():
    return _kind() == K_PRESET


def _is_points():
    return _kind() == K_POINTS


def _on_kind(*_):
    k = _kind()
    cmds.floatFieldGrp(F_LEN, edit=True, enable=k == K_STRAIGHT)
    cmds.floatFieldGrp(F_MEMBER, edit=True, enable=k == K_PATH)
    cmds.checkBox(F_CLOSED, edit=True, enable=k in (K_PATH, K_POINTS))
    cmds.floatFieldGrp(F_WIDTH, edit=True, enable=k in (K_GATE, K_PRESET))
    cmds.floatFieldGrp(F_HEIGHT, edit=True, enable=k in (K_GATE, K_PRESET))
    cmds.optionMenu(F_SHAPE, edit=True, enable=k == K_PRESET)
    cmds.optionMenu(F_PLANE, edit=True, enable=k == K_PRESET)
    cmds.optionMenu(F_ANGLE, edit=True, enable=k in (K_PATH, K_PRESET, K_POINTS))
    cmds.floatFieldGrp(F_GRID, edit=True, enable=k in (K_PATH, K_PRESET, K_POINTS))
    _status(HINTS.get(k, ""))
    _update_preview()


def _snap():
    """(snap_angle, snap_grid)。角度が「自動」なら None。"""
    return ANGLES[cmds.optionMenu(F_ANGLE, q=True, select=True) - 1], cmds.floatFieldGrp(F_GRID, q=True, value1=True)


def _preview_on():
    return cmds.checkBox(F_PREVIEW, q=True, value=True)


def _clear_preview():
    _truss().clear_preview()


_state = {"sel": ()}  # 直前に処理した選択 (生成直後の選択変更でプレビューを復活させない)


def _selection():
    return tuple(cmds.ls(selection=True, long=True) or [])


def _compute_preview():
    """UI の現在値から (polylines, parent_matrix, section)。生成と同じ生成先 (親) を使う。"""
    t = _truss()
    kind = _kind()
    key = KIND_KEYS[kind]
    angle, grid = _snap()
    params = _params()
    kw = dict(params=params, length=cmds.floatFieldGrp(F_LEN, q=True, value1=True),
              width=cmds.floatFieldGrp(F_WIDTH, q=True, value1=True),
              height=cmds.floatFieldGrp(F_HEIGHT, q=True, value1=True),
              shape=SHAPES[cmds.optionMenu(F_SHAPE, q=True, select=True) - 1],
              plane=PLANES[cmds.optionMenu(F_PLANE, q=True, select=True) - 1],
              member_len=cmds.floatFieldGrp(F_MEMBER, q=True, value1=True),
              closed=cmds.checkBox(F_CLOSED, q=True, value=True), snap_angle=angle, snap_grid=grid)
    if kind == K_PATH:
        curve = _selected_curve()
        if curve is None:
            raise RuntimeError("カーブを 1 本選ぶとプレビューが出ます")
        parent, _ = _resolve_parent(exclude=[curve])
        kw.update(curve=curve)
    elif kind == K_POINTS:
        kw.update(world_points=t.points_from_selection())
        parent, _ = _resolve_parent(exclude=cmds.ls(selection=True, long=True))
    else:
        parent, _ = _resolve_parent()
    kw["parent"] = parent
    return t.preview_points_for(key, **kw), t.parent_world_matrix(parent), params["section"]


def _update_preview(*_):
    """プレビューを作り直す (OFF なら消す)。失敗してもステータス行に出すだけで、生成は妨げない。"""
    try:
        if not cmds.checkBox(F_PREVIEW, exists=True):
            return
        if not _preview_on():
            _clear_preview()
            return
        try:
            polylines, matrix, section = _compute_preview()
        except Exception as e:  # noqa: BLE001
            _clear_preview()
            _status("プレビューなし: {}".format(e))
            return
        _truss().show_preview(polylines, matrix, section)
    except Exception as e:  # noqa: BLE001
        _status("プレビューのエラー: {}".format(e))
        cmds.warning("[MS2026] プレビュー: {}".format(e))


def _on_preview_toggle(*_):
    cmds.optionVar(intValue=(OPT_PREVIEW, 1 if _preview_on() else 0))
    _update_preview()


def _on_selection(*_):
    sel = _selection()
    if sel == _state["sel"]:
        return
    _state["sel"] = sel
    if cmds.window(WINDOW, exists=True) and _preview_on():
        _update_preview()


def _on_window_closed():
    try:
        _clear_preview()
    except Exception:  # noqa: BLE001
        pass


def _block_group():
    import ms2026_maya_tools as tools
    for s in cmds.ls(selection=True, long=True) or []:
        # 選択が区画の子孫でも、その最上位の SM_Bg_ を使う
        for part in s.strip("|").split("|"):
            if tools.BLOCK_RE.match(part):
                return "|" + part
    return None


def _selected_curve():
    """選択中の最初のカーブ (nurbsCurve shape を持つ transform)。無ければ None。"""
    t = _truss()
    for s in cmds.ls(selection=True, long=True) or []:
        if t.is_curve(s):
            return cmds.listRelatives(s, parent=True, fullPath=True)[0] if cmds.nodeType(s) == "nurbsCurve" else s
    return None


def _resolve_parent(exclude=None):
    """生成先を決める。戻り値: (親の long 名 or None=最上位, ステータス用ラベル)。
    1) 選択の祖先に SM_Bg_ があればその最上位区画  2) 選択された最初の transform
    (SM_Truss_ を選んでいたらそのトラスの親。入れ子にしない)  3) 未選択なら最上位。"""
    t = _truss()
    block = _block_group()
    if block:
        return block, block.lstrip("|")
    for s in cmds.ls(selection=True, long=True, type="transform") or []:
        if any(s == e or s.startswith(e + "|") for e in exclude or ()):
            continue  # パスのカーブ / 点にするロケータは親候補にしない
        parts = s.strip("|").split("|")
        for i in range(len(parts)):
            path = "|" + "|".join(parts[:i + 1])
            if t.is_truss_group(path):
                if i == 0:
                    return None, "最上位"
                parent = "|" + "|".join(parts[:i])
                return parent, parts[i - 1]
        return s, parts[-1]
    return None, "最上位"


def _created(grp, label):
    t = _truss()
    cmds.select(grp, replace=True)
    _status("生成: {}（生成先: {}、部材 {} 本）".format(grp, label, len(cmds.listRelatives(grp, children=True) or [])))
    return t.read_info(grp)


@_undo_chunk("MS2026 トラス生成")
def _do_create():
    _create()
    _clear_preview()  # 生成した実物と重なるので消す。選択変更ではすぐ復活させない
    _state["sel"] = _selection()


def _create():
    t = _truss()
    name = cmds.textFieldGrp(F_NAME, q=True, text=True).strip() or "Truss"
    angle, grid = _snap()
    width = cmds.floatFieldGrp(F_WIDTH, q=True, value1=True)
    height = cmds.floatFieldGrp(F_HEIGHT, q=True, value1=True)
    closed = cmds.checkBox(F_CLOSED, q=True, value=True)
    if _is_path():
        curve = _selected_curve()
        if curve is None:
            raise RuntimeError("パス生成にはカーブを選択してください")
        parent, label = _resolve_parent(exclude=[curve])
        grp = t.build_from_curve(name, curve, _params(), parent=parent,
                                 member_len=cmds.floatFieldGrp(F_MEMBER, q=True, value1=True),
                                 closed=closed, snap_angle=angle, snap_grid=grid)
        cmds.checkBox(F_CLOSED, edit=True, value=bool(_created(grp, label)["closed"]))
        return
    if _is_points():
        pts = t.points_from_selection()  # 生成先の解決より前 (選択を変えない)
        parent, label = _resolve_parent(exclude=cmds.ls(selection=True, long=True))
        grp = t.build_from_points(name, pts, _params(), parent=parent, closed=closed,
                                  snap_angle=t.DEFAULT_SNAP_ANGLE if angle is None else angle, snap_grid=grid)
        _created(grp, label)
        return
    parent, label = _resolve_parent()
    if _is_preset():
        shape = SHAPES[cmds.optionMenu(F_SHAPE, q=True, select=True) - 1]
        plane = PLANES[cmds.optionMenu(F_PLANE, q=True, select=True) - 1]
        grp = t.build_preset(name, shape, width, height, _params(), parent=parent, plane=plane,
                             snap_angle=t.DEFAULT_SNAP_ANGLE if angle is None else angle, snap_grid=grid)
    elif _is_gate():
        grp = t.build_gate(name, width, height, _params(), parent=parent)
    else:
        grp = t.build_straight(name, cmds.floatFieldGrp(F_LEN, q=True, value1=True), _params(), parent=parent)
    cmds.select(grp, replace=True)
    _status("生成: {}（生成先: {}）".format(grp, label))


def _selected_truss():
    t = _truss()
    for s in cmds.ls(selection=True, long=True) or []:
        node = s
        while node:
            if t.is_truss_group(node):
                return node
            node = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    return None


@_undo_chunk("MS2026 トラス再生成")
def _do_rebuild():
    grp = _selected_truss()
    if grp is None:
        _status("エラー: 再生成するトラスのグループ（または部材）を選択してください")
        cmds.warning("[MS2026] 再生成するトラスを選択してください。")
        return
    t = _truss()
    info = t.read_info(grp)
    kw = {"params": _params()}
    if info["kind"] == "path":
        kw.update(member_len=cmds.floatFieldGrp(F_MEMBER, q=True, value1=True))
        angle, grid = _snap()
        kw.update(snap_grid=grid)
        if angle is not None:  # 自動 = 保存済みの角度を保つ
            kw.update(snap_angle=angle)
        if cmds.checkBox(F_CLOSED, q=True, value=True):
            kw.update(closed=True)  # 未チェックは保存済みの closed を保つ
    elif info["kind"] == "gate":
        kw.update(width=cmds.floatFieldGrp(F_WIDTH, q=True, value1=True), height=cmds.floatFieldGrp(F_HEIGHT, q=True, value1=True))
    else:
        kw.update(length=cmds.floatFieldGrp(F_LEN, q=True, value1=True))
    grp = t.rebuild(grp, **kw)
    cmds.select(grp, replace=True)
    _status("再生成: {}".format(grp))


def _selected_path_truss():
    grp = _selected_truss()
    if grp is None or _truss().read_info(grp).get("kind") != "path":
        raise RuntimeError("パス種別のトラスのグループ（または部材）を選択してください")
    return grp


@_undo_chunk("MS2026 パスカーブ")
def _do_edit_curve():
    crv = _truss().make_edit_curve(_selected_path_truss())
    _status("パスカーブ: {}（CV を動かして「選択したトラスを再生成」。トラスを選び直す）".format(crv))


@_undo_chunk("MS2026 パスに変換")
def _do_convert():
    grp = _selected_truss()
    if grp is None:
        raise RuntimeError("パスに変換するトラスのグループ（または部材）を選択してください")
    t = _truss()
    if t.read_info(grp).get("kind") == "path":
        _status("すでにパスです: {}".format(grp))
        return
    grp = t.convert_to_path(grp)
    cmds.select(grp, replace=True)
    _status("パスに変換: {}（『パスカーブを表示 / 作成』で形を編集できます）".format(grp))


@_undo_chunk("MS2026 カーブ切り離し")
def _do_detach():
    grp = _selected_path_truss()
    _truss().detach_curve(grp)
    _status("カーブを切り離しました: {}".format(grp))


def show_window():
    """トラス生成ウィンドウを開く。GUI セッション専用。"""
    if cmds.about(batch=True):
        raise RuntimeError("show_window() needs Maya GUI (not batch/standalone).")
    t = _truss()
    d = t.DEFAULT_PARAMS
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    cmds.window(WINDOW, title="MS2026 トラス生成", widthHeight=(380, 760), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4, columnOffset=("both", 6))
    cmds.text(label="① 種類と寸法を入れる（黄色のプレビューがシーンに出る）→ ② 生成\n"
                    "③ 形を変えるなら『パスカーブを表示 / 作成』で出るカーブの CV を X キー押しながら動かし、\n"
                    "    トラスを選んで『選択したトラスを再生成』。直線・門型は『パスに変換』してから\n"
                    "部材 1 本 = SC_ 1 つ = Box コライダー 1 つ。SM_Bg_ 配下に作ると Export Block の対象。単位 cm", align="left")
    cmds.checkBox(F_PREVIEW, label="プレビュー表示（黄色の線 = 部材の中心線、正方形 = 断面）",
                  value=bool(cmds.optionVar(q=OPT_PREVIEW)) if cmds.optionVar(exists=OPT_PREVIEW) else True,
                  changeCommand=_on_preview_toggle)
    cmds.textFieldGrp(F_NAME, label="名前", text="Truss", columnWidth2=(110, 200))
    cmds.optionMenu(F_KIND, label="種類", changeCommand=_on_kind)
    cmds.menuItem(label="直線")
    cmds.menuItem(label="門型")
    cmds.menuItem(label="パス（カーブから）")
    cmds.menuItem(label="形プリセット")
    cmds.menuItem(label="選択した点から")
    cmds.optionMenu(F_SHAPE, label="形（プリセット）", changeCommand=_update_preview)
    for lbl in ("直線", "L 字", "コの字", "ロの字"):
        cmds.menuItem(label=lbl)
    cmds.optionMenu(F_PLANE, label="平面（プリセット）", changeCommand=_update_preview)
    cmds.menuItem(label="立面 XY")
    cmds.menuItem(label="床面 XZ")
    cmds.floatFieldGrp(F_LEN, changeCommand=_update_preview, label="長さ（直線）", value1=500.0, columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_WIDTH, changeCommand=_update_preview, label="幅（門型・プリセット）", value1=600.0, columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_HEIGHT, changeCommand=_update_preview, label="高さ（門型・プリセット）", value1=400.0, columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_MEMBER, changeCommand=_update_preview, label="部材長（パス）", value1=t.DEFAULT_MEMBER_LEN, columnWidth2=(130, 80))
    cmds.checkBox(F_CLOSED, label="閉じる（パス・点から）", value=False, changeCommand=_update_preview)
    cmds.optionMenu(F_ANGLE, label="スナップ角度（パス系）", changeCommand=_update_preview)
    for lbl in ("自動（ポリライン 90°・曲線はなし）", "なし", "45°", "90°"):
        cmds.menuItem(label=lbl)
    cmds.floatFieldGrp(F_GRID, changeCommand=_update_preview, label="グリッド cm（0 = なし）", value1=t.DEFAULT_SNAP_GRID, columnWidth2=(130, 80))
    cmds.text(label="CV 移動は X キー（グリッドスナップ）を押しながら。再生成でスナップが効く", align="left")
    cmds.floatFieldGrp(F_SECTION, changeCommand=_update_preview, label="断面サイズ", value1=d["section"], columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_CHORD, label="弦径", value1=d["chord_dia"], columnWidth2=(130, 80))
    cmds.floatFieldGrp(F_SEG, label="セグメント長", value1=d["seg_len"], columnWidth2=(130, 80))
    cmds.button(label="生成", command=_guard(_do_create))
    cmds.button(label="選択したトラスを再生成", command=_guard(_do_rebuild))
    cmds.button(label="パスに変換（直線・門型 → パス）", command=_guard(_do_convert))
    cmds.button(label="パスカーブを表示 / 作成", command=_guard(_do_edit_curve))
    cmds.button(label="カーブを切り離す", command=_guard(_do_detach))
    cmds.button(label="リロード", command=_guard(_reload_deferred))
    cmds.text(STATUS, label="待機中", align="left")
    cmds.showWindow(WINDOW)
    # ウィンドウが消えたらプレビューも消す。scriptJob は parent=WINDOW でウィンドウと運命を共にする
    cmds.scriptJob(uiDeleted=[WINDOW, _on_window_closed], runOnce=True)
    cmds.scriptJob(event=["SelectionChanged", _on_selection], parent=WINDOW)
    _state["sel"] = _selection()
    _on_kind()  # ヒント表示とプレビュー更新
