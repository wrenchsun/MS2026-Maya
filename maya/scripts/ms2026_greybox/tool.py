# -*- coding: utf-8 -*-
"""T-Drive の殻（tdrive.shell）に載せる Tool（T-Drive docs/13 §6.2 の約束）。

殻は `create_tool()` を呼んで `register_tool` する。タブの中身は案内と「ウィンドウを開く」ボタンだけで、
作業は従来の `Tools > MS2026 > グレーボックス...` ウィンドウ（ms2026_maya_ui）で行う。
T-Drive が無い環境では使わず、ms2026_maya_tools.install_menu() を直接呼ぶ（README）。
"""
import importlib

TOOL_ID = "ms2026_greybox"
TOOL_LABEL = "MS2026 グレーボックス"


def _tools():
    import ms2026_maya_tools as t
    return t


class GreyboxTool(object):
    """tdrive.tool.Tool の約束を満たす最小のツール。シーンの出来事・Undo は殻に任せる（扱うデータを持たない）。"""

    id = TOOL_ID
    label = TOOL_LABEL

    def __init__(self):
        _tools().install_menu()  # Tools > MS2026 メニュー（殻の Tools メニューを再利用する）

    def build_widget(self):
        from PySide6 import QtWidgets  # T-Drive と同じ Qt（Maya 2026 は PySide6）

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.addWidget(QtWidgets.QLabel(
            "グレーボックス → Maya → Unity 背景パイプライン。\n"
            "作業はメニュー Tools > MS2026 > グレーボックス... のウィンドウで行います。\n"
            "仕様: MS2026 の Docs/Guides/MayaGreyboxPipeline.md"))
        button = QtWidgets.QPushButton("グレーボックスのウィンドウを開く")
        button.clicked.connect(lambda *_: _tools().show_window())
        layout.addWidget(button)
        layout.addStretch(1)
        return widget

    def on_scene_opened(self):
        pass

    def on_scene_saved(self):
        pass

    def undo(self):
        return False

    def redo(self):
        return False

    def refresh(self):
        import ms2026_maya_reload as r
        importlib.reload(r)
        r.reload_all()  # 「ツールをリロード」: ms2026_maya_* を全部読み直し、メニュー/ウィンドウも作り直す


def create_tool():
    return GreyboxTool()
