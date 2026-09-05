# -*- coding: utf-8 -*-
import maya.cmds as cmds
import maya.mel as mel


def run():
    """Center pivot first, move it to local -Y bottom, bake it, move to origin, then freeze transforms."""
    selection = cmds.ls(sl=True, long=True, type="transform") or []
    if not selection:
        cmds.warning("[maya-user] 请先选择至少一个模型。")
        return []

    processed = []

    for obj in selection:
        if not cmds.objExists(obj):
            continue

        cmds.select(obj, r=True)

        # 先把枢轴还原到模型中心，避免沿用旧的自定义枢轴位置。
        cmds.xform(obj, centerPivots=True)

        bbox = cmds.xform(obj, q=True, bb=True, os=True)
        pivot = cmds.xform(obj, q=True, rp=True, os=True)

        # 保持当前本地轴方向，把枢轴沿本地 -Y 放到模型底部。
        cmds.xform(
            obj,
            os=True,
            pivots=(pivot[0], bbox[1], pivot[2]),
        )

        # Maya: Modify > Bake Pivot
        mel.eval("BakeCustomPivot;")

        # 移到世界原点。
        cmds.xform(obj, ws=True, translation=(0.0, 0.0, 0.0))

        # 冻结位移、旋转、缩放。
        cmds.makeIdentity(
            obj,
            apply=True,
            translate=True,
            rotate=True,
            scale=True,
            normal=False,
        )

        processed.append(obj)

    if processed:
        cmds.select(processed, r=True)

    return processed
