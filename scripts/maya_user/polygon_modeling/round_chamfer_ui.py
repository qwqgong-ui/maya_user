# -*- coding: utf-8 -*-
import maya.cmds as cmds

from . import round_chamfer_core

WINDOW = "mayaUserRoundChamferWindow"

OPT_MODE = "mayaUserRoundChamferMode"
OPT_DISTANCE = "mayaUserRoundChamferDistance"
OPT_PERCENT = "mayaUserRoundChamferPercent"
OPT_SEGMENTS = "mayaUserRoundChamferSegments"
OPT_FLIP = "mayaUserRoundChamferFlip"


def _get_string(name, default):
    if cmds.optionVar(exists=name):
        return cmds.optionVar(q=name)
    return default


def _get_float(name, default):
    if cmds.optionVar(exists=name):
        return float(cmds.optionVar(q=name))
    return default


def _get_int(name, default):
    if cmds.optionVar(exists=name):
        return int(cmds.optionVar(q=name))
    return default


def show():
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    win = cmds.window(
        WINDOW,
        title="圆角切角 - 多边形建模",
        sizeable=False,
        widthHeight=(360, 310),
    )

    root = cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
    cmds.separator(style="none", height=4)
    cmds.text(
        label="选择 1 个边界顶点处理外角；选择 2 条共享顶点的边界边处理内角。",
        align="left",
        wordWrap=True,
        height=36,
    )

    cmds.rowLayout(
        numberOfColumns=2,
        adjustableColumn=2,
        columnWidth2=(96, 240),
        columnAlign2=("right", "left"),
    )
    cmds.text(label="模式：")
    mode_menu = cmds.optionMenu(changeCommand=lambda *_: _sync_enabled())
    cmds.menuItem(label="百分比")
    cmds.menuItem(label="固定距离")
    cmds.setParent(root)

    distance_field = cmds.floatFieldGrp(
        numberOfFields=1,
        label="固定距离：",
        value1=_get_float(OPT_DISTANCE, 0.2),
        precision=4,
        columnWidth2=(96, 240),
    )

    percent_field = cmds.floatFieldGrp(
        numberOfFields=1,
        label="边界百分比：",
        value1=_get_float(OPT_PERCENT, 25.0),
        precision=2,
        columnWidth2=(96, 240),
        annotation="按两侧边界允许值取较小值，保持严格相切圆弧。",
    )

    segments_field = cmds.intFieldGrp(
        numberOfFields=1,
        label="圆弧段数：",
        value1=max(1, _get_int(OPT_SEGMENTS, 8)),
        columnWidth2=(96, 240),
    )

    flip_check = cmds.checkBoxGrp(
        numberOfCheckBoxes=1,
        label="外角方向：",
        label1="翻转（默认）",
        value1=bool(_get_int(OPT_FLIP, 1)),
        columnWidth2=(96, 240),
        annotation="外角默认开启。标准相切圆角会优先使用拓扑确定的有效方向。",
    )

    cmds.separator(style="in", height=10)

    cmds.button(
        label="执行圆角切角",
        height=34,
        command=lambda *_: _execute(),
    )

    cmds.button(
        label="关闭",
        height=26,
        command=lambda *_: cmds.deleteUI(WINDOW),
    )

    saved_mode = _get_string(OPT_MODE, "percent")
    cmds.optionMenu(
        mode_menu,
        edit=True,
        select=1 if saved_mode == "percent" else 2,
    )

    def sync_enabled():
        mode = "percent" if cmds.optionMenu(mode_menu, q=True, select=True) == 1 else "absolute"
        cmds.floatFieldGrp(percent_field, e=True, enable=(mode == "percent"))
        cmds.floatFieldGrp(distance_field, e=True, enable=(mode == "absolute"))

    def execute():
        mode = "percent" if cmds.optionMenu(mode_menu, q=True, select=True) == 1 else "absolute"
        distance = cmds.floatFieldGrp(distance_field, q=True, value1=True)
        percent_ui = cmds.floatFieldGrp(percent_field, q=True, value1=True)
        segments = cmds.intFieldGrp(segments_field, q=True, value1=True)
        flip = cmds.checkBoxGrp(flip_check, q=True, value1=True)

        if percent_ui <= 0.0 or percent_ui >= 100.0:
            cmds.error("边界百分比必须大于 0 且小于 100。")
        if distance <= 0.0:
            cmds.error("固定距离必须大于 0。")
        if segments < 1:
            cmds.error("圆弧段数至少为 1。")

        cmds.optionVar(sv=(OPT_MODE, mode))
        cmds.optionVar(fv=(OPT_DISTANCE, distance))
        cmds.optionVar(fv=(OPT_PERCENT, percent_ui))
        cmds.optionVar(iv=(OPT_SEGMENTS, segments))
        cmds.optionVar(iv=(OPT_FLIP, int(bool(flip))))

        round_chamfer_core.chamfer_round(
            mode=mode,
            distance=distance,
            percent=percent_ui / 100.0,
            segments=segments,
            flip=flip,
        )

    global _sync_enabled
    global _execute
    _sync_enabled = sync_enabled
    _execute = execute

    sync_enabled()
    cmds.showWindow(win)
    return win
