# -*- coding: utf-8 -*-
import maya.cmds as cmds
import maya.mel as mel

MENU_NAME = "mayaUserMainMenu"
MENU_LABEL = "Maya User"


def _main_window():
    return mel.eval("$tmpVar=$gMainWindow")


def install_menu():
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME)

    menu = cmds.menu(
        MENU_NAME,
        label=MENU_LABEL,
        parent=_main_window(),
        tearOff=True,
    )

    polygon = cmds.menuItem(
        label="多边形建模",
        subMenu=True,
        tearOff=True,
        parent=menu,
    )

    cmds.menuItem(
        label="圆角切角…",
        annotation="固定距离 / 百分比的相切圆角工具",
        parent=polygon,
        command=lambda *_: _open_round_chamfer(),
    )

    cmds.menuItem(
        label="底部枢轴 → 原点 → 冻结",
        annotation="枢轴移到当前本地轴 -Y 底部，烘焙枢轴，移到 0,0,0 并冻结变换",
        parent=polygon,
        command=lambda *_: _pivot_bottom_origin_freeze(),
    )

    cmds.setParent(menu, menu=True)
    return menu


def _open_round_chamfer():
    from maya_user.polygon_modeling import round_chamfer_ui
    round_chamfer_ui.show()


def _pivot_bottom_origin_freeze():
    from maya_user.polygon_modeling import pivot_bottom_origin_freeze
    pivot_bottom_origin_freeze.run()
