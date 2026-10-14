# -*- coding: utf-8 -*-
"""ウィンドウ先頭の「0. フォルダ」枠 (GUI 専用)。ms2026_maya_ui から呼ばれる。"""
import maya.cmds as cmds

import ms2026_maya_settings as settings

FIELD_PREFIX = "MS2026DirField_"


def _field(key):
    return FIELD_PREFIX + key


def _apply(key, path, status, on_changed):
    eff = settings.set_dir(key, path)
    cmds.textField(_field(key), edit=True, text=eff)
    status("フォルダ設定: {} = {}".format(settings.KEYS[key][2], eff))
    on_changed()


def _browse(key, status, on_changed):
    res = cmds.fileDialog2(fileMode=3, caption=settings.KEYS[key][2], dir=settings.get_dir(key))
    if res:
        _apply(key, res[0], status, on_changed)


def _reset(status, on_changed):
    settings.reset_dirs()
    for key in settings.KEYS:
        cmds.textField(_field(key), edit=True, text=settings.get_dir(key))
    status("フォルダ設定: 既定に戻した")
    on_changed()


def build_folder_frame(status, on_changed):
    """3 フォルダの編集欄。変更は即 optionVar に保存し on_changed() で一覧を更新する。"""
    cmds.frameLayout(label="0. フォルダ", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    for key, (_var, default, label) in settings.KEYS.items():
        cmds.text(label=label, align="left")
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnAttach=[(1, "right", 2), (2, "left", 2)])
        cmds.textField(_field(key), text=settings.get_dir(key), annotation="既定: " + default,
                       changeCommand=lambda v, k=key: _apply(k, v, status, on_changed))
        cmds.button(label="参照...", command=lambda *_, k=key: _browse(k, status, on_changed))
        cmds.setParent("..")
    cmds.button(label="既定に戻す", command=lambda *_: _reset(status, on_changed))
    cmds.setParent("..")
    cmds.setParent("..")
