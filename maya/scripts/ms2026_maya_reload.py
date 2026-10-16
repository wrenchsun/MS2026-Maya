# -*- coding: utf-8 -*-
"""MS2026 ツール全体のリロード (T-Drive の reload_tdrive と同じ流儀)。

`sys.modules` から `ms2026_maya_*` を捨てて読み直し、GUI ならメニューと開いていたウィンドウを作り直す。
`ms2026_greybox` パッケージ (T-Drive の殻が持つ) と、このモジュール自身は残す。
maya.cmds は GUI 部分でだけ使う (standalone でも動く)。
スクリプトエディタ用の一行:
    import importlib, ms2026_maya_reload as r; importlib.reload(r); r.reload_all()
"""
import sys

PREFIX = "ms2026_maya_"
SELF = __name__
# モジュールを捨てる前に分かるよう、ウィンドウ名はここに持つ (ui / ui_truss の WINDOW と同じ)
WINDOW_GREYBOX = "MS2026GreyboxWindow"
WINDOW_TRUSS = "MS2026TrussWindow"


def _cmds():
    try:
        import maya.cmds as cmds
    except ImportError:
        return None
    return cmds


def _is_gui(cmds):
    try:
        return cmds is not None and not cmds.about(batch=True)
    except Exception:  # noqa: BLE001
        return False


def _close_windows(cmds):
    """開いている MS2026 ウィンドウを閉じ、閉じた名前を返す。閉じ失敗は warning で続行。"""
    opened = []
    for name in (WINDOW_GREYBOX, WINDOW_TRUSS):
        try:
            if cmds.window(name, exists=True):
                opened.append(name)
                cmds.deleteUI(name)
        except Exception as e:  # noqa: BLE001
            cmds.warning("[MS2026] ウィンドウを閉じられません ({}): {}".format(name, e))
    return opened


def reload_all(reopen=True):
    """ms2026_maya_* を全部読み直す。読み直したモジュール名のリストを返す。"""
    cmds = _cmds()
    gui = _is_gui(cmds)
    opened = _close_windows(cmds) if gui else []
    if gui:
        try:  # トラス生成のプレビュー (最上位の MS2026_TrussPreviewGrp) も消す
            import ms2026_maya_truss
            ms2026_maya_truss.clear_preview()
        except Exception:  # noqa: BLE001
            pass

    dropped = [n for n in list(sys.modules) if n.startswith(PREFIX) and n != SELF]
    for n in dropped:
        del sys.modules[n]

    import importlib
    importlib.invalidate_caches()
    import ms2026_maya_tools as tools  # 依存 (settings / collision / props / ...) ごと読み直される
    names = sorted(n for n in sys.modules if n.startswith(PREFIX) and n != SELF)

    if gui:
        tools.install_menu()
        if reopen:
            if WINDOW_GREYBOX in opened:
                tools.show_window()
            if WINDOW_TRUSS in opened:
                import ms2026_maya_ui_truss
                ms2026_maya_ui_truss.show_window()
                names = sorted(set(names) | {"ms2026_maya_ui_truss"})

    print("[MS2026] リロード: {} modules (ウィンドウ: {})".format(
        len(names), ", ".join(opened) if (opened and reopen) else "なし"))
    return names
