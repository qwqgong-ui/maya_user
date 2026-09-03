# -*- coding: utf-8 -*-

"""
Arnold 抠图渲染层（Maya Render Setup）

用途：

    选中一个或多个模型（或模型总组），创建 Arnold Beauty 抠图层。

        目标模型：相机可见，正常渲染。
        其他模型：只关闭 primaryVisibility，
                  仍然参与阴影、反射、折射、遮挡、GI、间接照明。
        所有灯光：原样保留，不做任何覆盖。
        SkyDome ：可选只关掉相机背景，照明和反射保持不变。

Render Setup 结构：

    CUTOUT_xxx

        AR_CUTOUT_scene
            pattern = "*"，无任何覆盖。
            作用是让整个场景（几何、灯光、StandIn、Volume……）
            都留在这个渲染层里，环境保持不变。

        AR_CUTOUT_hide_others
            其他几何 Shape
            └─ primaryVisibility = 0

        AR_CUTOUT_skydome_camera
            SkyDome Shape
            └─ camera = 0（可选）

兼容目标：

    Maya 2022-2026
    MtoA
    Render Setup

版本：2.0

v2.0 修复：

    1. 集合过滤器。
       新建集合默认过滤器是 Transform，
       把 Mesh Shape 塞进去会被直接过滤掉，
       primaryVisibility 覆盖等于没写。
       现在所有集合显式设成 All。

    2. 环境完整性。
       旧版本只枚举 mesh，
       nurbsSurface / aiStandIn / aiVolume / 粒子
       因为不在任何集合里，会被整层排除，
       反射和阴影里直接消失。
       现在改用 pattern "*" 保证全场景进层，
       再单独覆盖需要隐藏的 Shape。

    3. SkyDome 的 camera 是 float 权重，不是 bool，
       覆盖值改成 0.0。
       同时去掉了 aiCamera / visibleInCamera 这两个
       aiSkyDomeLight 上根本不存在的候选属性。

v2.0 删除（无效代码）：

    _validate_hidden_mesh_shapes
    _validate_lights_not_hidden
        隐藏列表本来就是从 primaryVisibility 过滤出来的，
        灯光不可能进去，这两个检查永远不会触发。

    _scene_light_members 里对 aiAreaLight 等类型的二次扫描
        这些节点本身就是 DAG Shape，
        第一次 ls(dag=True, shapes=True) 已经全部取到。

    AR_CUTOUT_keep_lights 集合
        pattern "*" 已经把灯光包含进层，
        再建一个空覆盖的灯光集合没有作用。

    _node_uuid 去重
        ls(long=True) 返回的全路径本身唯一。

    _is_light_node 里的 nodeType(inherited=True) 分支
        与 objectType(isAType="light") 完全重复。
"""

from __future__ import absolute_import, print_function

import re

import maya.cmds as cmds
import maya.app.renderSetup.model.renderSetup as renderSetup


WINDOW_NAME = "arnoldGroupCutoutLayerWindow"
LAYER_PREFIX = "CUTOUT_"

# Render Setup 的 "All" 过滤器。
# 集合里放的是明确的节点列表，
# 用 All 可以避免 Transform / Shape 过滤器把 Shape 过滤掉。
FILTER_ALL = 0

ARNOLD_LIGHT_TYPES = (
    "aiAreaLight",
    "aiSkyDomeLight",
    "aiPhotometricLight",
    "aiMeshLight",
    "aiLightPortal",
)


# ============================================================
# 基础
# ============================================================

def _short_name(node):

    return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def _safe_name(text):

    value = re.sub(r"[^0-9A-Za-z_]+", "_", text or "")
    value = value.strip("_") or "layer"

    if value[0].isdigit():
        value = "G_" + value

    return value


def _unique(nodes):

    return sorted(set(node for node in nodes if node))


def _has_attr(node, attr):

    return cmds.objExists(node + "." + attr)


def _is_intermediate(shape):

    plug = shape + ".intermediateObject"

    if not cmds.objExists(plug):
        return False

    try:
        return bool(cmds.getAttr(plug))
    except Exception:
        return False


def _selected_roots():

    selected = cmds.ls(
        selection=True,
        long=True,
        objectsOnly=True
    ) or []

    roots = []

    for node in selected:

        if cmds.nodeType(node) != "transform":

            parents = cmds.listRelatives(
                node,
                parent=True,
                fullPath=True
            ) or []

            node = parents[0] if parents else None

        if node:
            roots.append(node)

    roots = _unique(roots)

    if not roots:

        raise RuntimeError(
            "请先选择要单独保留的模型或模型组。"
        )

    return roots


# ============================================================
# 灯光
# ============================================================

def _is_light(node):

    try:
        if cmds.objectType(node, isAType="light"):
            return True
    except Exception:
        pass

    return cmds.nodeType(node) in ARNOLD_LIGHT_TYPES


def _scene_light_shapes():

    result = []

    for shape in cmds.ls(
        dag=True,
        shapes=True,
        long=True
    ) or []:

        if _is_light(shape):
            result.append(shape)

    return _unique(result)


# ============================================================
# 几何
# ============================================================

def _renderable_shapes():

    """
    场景里所有可能被相机直接看到的几何 Shape。

    判定条件只有一个：是否存在 primaryVisibility。

    这样 mesh / nurbsSurface / subdiv / aiStandIn 等都能覆盖到，
    灯光和相机会被自动排除。
    """

    result = []

    for shape in cmds.ls(
        dag=True,
        shapes=True,
        long=True
    ) or []:

        if _is_light(shape):
            continue

        if _is_intermediate(shape):
            continue

        if not _has_attr(shape, "primaryVisibility"):
            continue

        result.append(shape)

    return _unique(result)


def _split_shapes(roots, shapes):

    """
    按所选层级把 Shape 分成目标和其他。
    """

    inside = set()

    for root in roots:

        inside.add(root)

        for node in cmds.listRelatives(
            root,
            allDescendents=True,
            fullPath=True
        ) or []:

            inside.add(node)

    target = [s for s in shapes if s in inside]
    other = [s for s in shapes if s not in inside]

    return target, other


# ============================================================
# Render Setup
# ============================================================

def _unique_layer_name(render_setup, requested):

    existing = {
        layer.name()
        for layer in render_setup.getRenderLayers()
    }

    if requested not in existing:
        return requested

    index = 1

    while True:

        candidate = "{}_{:02d}".format(requested, index)

        if candidate not in existing:
            return candidate

        index += 1


def _create_collection(
    parent,
    name,
    nodes=None,
    pattern=None
):

    collection = parent.createCollection(name)

    selector = collection.getSelector()

    # 关键：默认过滤器是 Transform，
    # 不改成 All 的话 Shape 覆盖不会生效。
    try:
        selector.setFilterType(FILTER_ALL)
    except Exception:
        pass

    if pattern is not None:

        try:
            selector.setPattern(pattern)
        except Exception:
            pass

    if nodes:
        selector.staticSelection.set(list(nodes))

    return collection


def _create_override(
    collection,
    sample_node,
    attr,
    value,
    name
):

    item = collection.createAbsoluteOverride(sample_node, attr)

    item.setName(name)
    item.setAttrValue(value)

    return item


# ============================================================
# 创建
# ============================================================

def create_from_selection(
    layer_name=None,
    hide_environment=True,
    make_current=True
):

    roots = _selected_roots()

    renderable = _renderable_shapes()

    target_shapes, other_shapes = _split_shapes(
        roots,
        renderable
    )

    if not target_shapes:

        raise RuntimeError(
            "所选对象下面没有找到可渲染的几何体。"
        )

    render_setup = renderSetup.instance()

    requested = _safe_name(
        layer_name
        or (LAYER_PREFIX + _short_name(roots[0]))
    )

    actual_name = _unique_layer_name(render_setup, requested)

    layer = render_setup.createRenderLayer(actual_name)

    # ========================================================
    # 1. 整个场景进层
    #
    # 没有这一步，任何没被集合选到的节点
    # （灯光、StandIn、Volume、曲面、粒子）
    # 都会被 Render Setup 整层排除，
    # 反射和阴影会跟着一起消失。
    # ========================================================

    _create_collection(
        layer,
        "AR_CUTOUT_scene",
        pattern="*"
    )

    # ========================================================
    # 2. 其他几何只关相机可见
    #
    # 不改 visibility，不改材质，
    # 所以它们仍然真实存在于 Arnold 场景中。
    # ========================================================

    if other_shapes:

        hide_collection = _create_collection(
            layer,
            "AR_CUTOUT_hide_others",
            nodes=other_shapes
        )

        _create_override(
            hide_collection,
            other_shapes[0],
            "primaryVisibility",
            False,
            "AR_CUTOUT_primaryVisibility_off"
        )

    # ========================================================
    # 3. SkyDome 相机背景
    #
    # camera 是 float 权重，不是布尔开关。
    # 只动它，不动 intensity / exposure /
    # diffuse / specular / transmission，
    # 所以 HDRI 照明和反射完全保留。
    # ========================================================

    dome_shapes = []

    if hide_environment:

        dome_shapes = [
            dome
            for dome in _unique(
                cmds.ls(type="aiSkyDomeLight", long=True) or []
            )
            if _has_attr(dome, "camera")
        ]

        if dome_shapes:

            dome_collection = _create_collection(
                layer,
                "AR_CUTOUT_skydome_camera",
                nodes=dome_shapes
            )

            _create_override(
                dome_collection,
                dome_shapes[0],
                "camera",
                0.0,
                "AR_CUTOUT_skydome_camera_off"
            )

    # ========================================================
    # 切层
    # ========================================================

    if make_current:
        render_setup.switchToLayer(layer)

    cmds.select(roots, replace=True)

    # ========================================================
    # 日志
    # ========================================================

    light_shapes = _scene_light_shapes()

    message = (
        "已创建 Arnold 抠图层：{}\n"
        "\n"
        "目标根节点：{}\n"
        "目标几何 Shape：{}\n"
        "隐藏几何 Shape：{}\n"
        "场景灯光 Shape：{}\n"
        "关闭相机背景的 SkyDome：{}\n"
        "\n"
        "结构：\n"
        "整个场景 = 渲染层成员，无覆盖\n"
        "其他模型 = 仅 primaryVisibility = 0\n"
        "灯光 = 完全不动\n"
        "\n"
        "其他模型仍参与反射、阴影、折射和间接照明。"
    ).format(
        actual_name,
        len(roots),
        len(target_shapes),
        len(other_shapes),
        len(light_shapes),
        len(dome_shapes)
    )

    print(
        "[Arnold Cutout] " + message.replace("\n", " | ")
    )

    for light in light_shapes:

        print(
            "    保留灯光 {} [{}]".format(
                light,
                cmds.nodeType(light)
            )
        )

    cmds.confirmDialog(
        title="创建完成",
        message=message,
        button=["确定"],
        defaultButton="确定"
    )

    return actual_name


# ============================================================
# UI
# ============================================================

def _fill_name_from_selection(*_):

    try:

        roots = _selected_roots()

        cmds.textFieldGrp(
            "arnoldCutoutLayerNameField",
            edit=True,
            text=(
                LAYER_PREFIX
                + _safe_name(_short_name(roots[0]))
            )
        )

        if len(roots) == 1:
            label = "当前目标：{}".format(roots[0])
        else:
            label = "当前目标：{} 个对象，首个 {}".format(
                len(roots),
                _short_name(roots[0])
            )

        cmds.text(
            "arnoldCutoutTargetLabel",
            edit=True,
            label=label
        )

    except RuntimeError as exc:

        cmds.warning(str(exc))


def _create_from_ui(*_):

    try:

        layer_name = cmds.textFieldGrp(
            "arnoldCutoutLayerNameField",
            query=True,
            text=True
        ).strip()

        hide_environment = cmds.checkBox(
            "arnoldCutoutHideEnvironment",
            query=True,
            value=True
        )

        make_current = cmds.checkBox(
            "arnoldCutoutMakeCurrent",
            query=True,
            value=True
        )

        create_from_selection(
            layer_name=layer_name or None,
            hide_environment=hide_environment,
            make_current=make_current
        )

    except Exception as exc:

        cmds.confirmDialog(
            title="无法创建",
            message=str(exc),
            button=["确定"],
            defaultButton="确定",
            icon="critical"
        )

        raise


def show():

    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    window = cmds.window(
        WINDOW_NAME,
        title="Arnold 抠图渲染层",
        sizeable=False,
        widthHeight=(470, 265)
    )

    cmds.columnLayout(
        adjustableColumn=True,
        rowSpacing=9
    )

    cmds.separator(height=5, style="none")

    cmds.text(
        label="选中模型，创建保持完整场景光照的透明 Beauty 图层",
        align="center",
        height=25
    )

    cmds.text(
        "arnoldCutoutTargetLabel",
        label="当前目标：尚未读取选择",
        align="left",
        height=22
    )

    cmds.button(
        label="读取当前选择",
        height=30,
        command=_fill_name_from_selection
    )

    cmds.textFieldGrp(
        "arnoldCutoutLayerNameField",
        label="渲染层名称",
        text="",
        columnWidth2=(90, 355),
        adjustableColumn=2
    )

    cmds.checkBox(
        "arnoldCutoutHideEnvironment",
        label="隐藏 SkyDome 相机背景（保留照明和反射）",
        value=True
    )

    cmds.checkBox(
        "arnoldCutoutMakeCurrent",
        label="创建后切换到新渲染层",
        value=True
    )

    cmds.separator(height=8, style="in")

    cmds.button(
        label="创建抠图 Beauty 渲染层",
        height=42,
        backgroundColor=(0.24, 0.48, 0.31),
        command=_create_from_ui
    )

    cmds.separator(height=5, style="none")

    cmds.showWindow(window)

    try:
        _fill_name_from_selection()
    except Exception:
        pass

    return window


show()
