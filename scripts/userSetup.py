# -*- coding: utf-8 -*-
import maya.utils


def _install_maya_user_menu():
    try:
        from maya_user import menu
        menu.install_menu()
    except Exception as exc:
        print("[maya-user] 菜单安装失败: %s" % exc)


maya.utils.executeDeferred(_install_maya_user_menu)
