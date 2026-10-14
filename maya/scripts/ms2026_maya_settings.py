# -*- coding: utf-8 -*-
"""MS2026 Maya ツールのフォルダ設定 (Maya optionVar に保存。ユーザーごと・再起動後も残る)。"""
import os

import maya.cmds as cmds

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # このツールのリポジトリ


def default_work_root():
    """MayaWork の既定の親。T-Drive のプロジェクトフォルダ ($TDRIVE_PROJECT) があればそこ、無ければ Documents/maya/MS2026-MayaWork。
    Unity 側 (MS2026 の Exchange Folders...) と同じフォルダに揃えること。ツール自身のリポジトリには置かない。"""
    project = os.environ.get("TDRIVE_PROJECT", "").strip()
    if project:
        return os.path.join(os.path.normpath(project), "MayaWork")
    return os.path.join(os.path.expanduser("~"), "Documents", "maya", "MS2026-MayaWork")


_WORK = default_work_root()
# key -> (optionVar 名, 既定フォルダ, 表示名)
KEYS = {
    "greybox_dir": ("ms2026_greybox_dir", os.path.join(_WORK, "Export"), "グレーボックスFBX (Unity出力)"),
    "block_out_dir": ("ms2026_block_out_dir", os.path.join(_WORK, "Import"), "区画FBX・props.json 出力先"),
    "props_dir": ("ms2026_props_dir", os.path.join(_WORK, "Props"), "小物FBXライブラリ"),
}


def _check(key):
    if key not in KEYS:
        raise KeyError("Unknown folder key '{}' (use one of {})".format(key, ", ".join(KEYS)))


def default_dir(key):
    _check(key)
    return KEYS[key][1]


def get_dir(key):
    """optionVar が設定済みで空でなければその値、無ければ既定フォルダ。"""
    _check(key)
    var = KEYS[key][0]
    if cmds.optionVar(exists=var):
        val = cmds.optionVar(q=var)
        if isinstance(val, str) and val.strip():
            return val
    return KEYS[key][1]


def set_dir(key, path):
    """正規化して保存する。空文字なら optionVar を削除して既定に戻す。戻り値: 有効なフォルダ。"""
    _check(key)
    var = KEYS[key][0]
    path = (path or "").strip().strip('"')
    if not path:
        if cmds.optionVar(exists=var):
            cmds.optionVar(remove=var)
        return KEYS[key][1]
    path = os.path.normpath(os.path.expanduser(path))
    cmds.optionVar(sv=(var, path))
    return path


def reset_dirs():
    """3 つとも既定に戻す。"""
    for key in KEYS:
        set_dir(key, "")


def greybox_dir():
    return get_dir("greybox_dir")


def block_out_dir():
    return get_dir("block_out_dir")


def props_dir():
    return get_dir("props_dir")
