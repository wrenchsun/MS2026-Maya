# -*- coding: utf-8 -*-
"""Documents/maya/2026/scripts/userSetup.py に書く例。Maya 起動時に Tools > MS2026 メニューを作る。
T-Drive の外部ツールとして入れた場合は不要（殻が create_tool() を呼ぶ）。"""
import sys

import maya.utils

sys.path.append(r"C:\Users\<あなた>\wrench\maya\MS2026-Maya\maya\scripts")


def _ms2026_menu():
    import ms2026_maya_tools as t
    t.install_menu()


maya.utils.executeDeferred(_ms2026_menu)
