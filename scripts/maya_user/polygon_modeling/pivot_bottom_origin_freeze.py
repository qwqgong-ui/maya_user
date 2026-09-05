# -*- coding: utf-8 -*-
import maya.cmds as cmds
import maya.mel as mel


def run():
    """Move the pivot to local -Y bottom, bake it, move to origin, then freeze transforms."""
    selection = cmds.ls(sl=True, long=True, type="transform") or []
    if not selection:
        cmds.warning("[maya-user] 请先选择至少一个模型。")
        return []

    processed = []

    for obj in selection:
        if not cmds.objExists(obj):
            continue

        bbox = cmds.xform(obj, q=True, bb=True, os=True)
        pivot = cmds.xform(obj, q=True, rp=True, os=True)

        cmds.select(obj, r=True)

        # 当前本地轴 -Y 的最底部；保持枢轴本地 X/Z 不变。
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
