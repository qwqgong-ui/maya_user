# -*- coding: utf-8 -*-
"""Maya 边界圆角切角工具（单文件版）。

选择规则：
- 选择 1 个边界顶点：处理外角。
- 选择 2 条共享顶点的边界边：处理内角。

支持：固定距离、边界百分比、圆弧段数、外角方向兼容选项。
"""

import math
import re

import maya.api.OpenMaya as om
import maya.cmds as cmds

WINDOW = "mayaUserRoundChamferWindow"

OPT_MODE = "mayaUserRoundChamferMode"
OPT_DISTANCE = "mayaUserRoundChamferDistance"
OPT_PERCENT = "mayaUserRoundChamferPercent"
OPT_SEGMENTS = "mayaUserRoundChamferSegments"
OPT_FLIP = "mayaUserRoundChamferFlip"

_EPS = 1e-10


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(v):
    return math.sqrt(dot(v, v))


def normalize(v):
    l = length(v)
    if l < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / l, v[1] / l, v[2] / l)


def clamp(x, a, b):
    return max(a, min(b, x))


def position(vtx):
    return cmds.pointPosition(vtx, world=True)


def mesh_of(component):
    return component.split(".")[0]


def index_of(component, kind):
    match = re.search(r"\.%s\[(\d+)\]$" % kind, component)
    return int(match.group(1)) if match else None


def edge_vertices(edge):
    result = cmds.polyListComponentConversion(edge, fromEdge=True, toVertex=True)
    return cmds.filterExpand(result, sm=31) or []


def edge_faces(edge):
    result = cmds.polyListComponentConversion(edge, fromEdge=True, toFace=True)
    return cmds.filterExpand(result, sm=34) or []


def vertex_edges(vertex):
    result = cmds.polyListComponentConversion(vertex, fromVertex=True, toEdge=True)
    return cmds.filterExpand(result, sm=32) or []


def vertex_faces(vertex):
    result = cmds.polyListComponentConversion(vertex, fromVertex=True, toFace=True)
    return cmds.filterExpand(result, sm=34) or []


def face_edges(face):
    result = cmds.polyListComponentConversion(face, fromFace=True, toEdge=True)
    return cmds.filterExpand(result, sm=32) or []


def boundary_edges(vertex):
    return [edge for edge in vertex_edges(vertex) if len(edge_faces(edge)) == 1]


def other_vertex(edge, origin):
    others = [v for v in edge_vertices(edge) if v != origin]
    if len(others) != 1:
        cmds.error("无法读取边另一端顶点：%s" % edge)
    return others[0]


def edge_between(v1, v2):
    common = set(vertex_edges(v1)) & set(vertex_edges(v2))
    return list(common)[0] if common else None


def rotate(v, axis, angle):
    c = math.cos(angle)
    s = math.sin(angle)
    return add(
        add(mul(v, c), mul(cross(axis, v), s)),
        mul(axis, dot(axis, v) * (1.0 - c)),
    )


def get_dag(mesh):
    selection = om.MSelectionList()
    selection.add(mesh)
    return selection.getDagPath(0)


def world_to_object(mesh, p):
    dag = get_dag(mesh)
    point = om.MPoint(p[0], p[1], p[2])
    result = point * dag.inclusiveMatrixInverse()
    return (result.x, result.y, result.z)


def face_normal(mesh, face):
    dag = get_dag(mesh)
    fn = om.MFnMesh(dag)
    n = fn.getPolygonNormal(index_of(face, "f"), om.MSpace.kWorld)
    return normalize((n.x, n.y, n.z))


def polygon_normal(points):
    result = (0.0, 0.0, 0.0)
    count = len(points)
    for i in range(count):
        result = add(result, cross(points[i], points[(i + 1) % count]))
    return normalize(result)


def new_vertices(mesh, before_count):
    after_count = cmds.polyEvaluate(mesh, vertex=True)
    return ["%s.vtx[%d]" % (mesh, i) for i in range(before_count, after_count)]


def find_candidate_on_ray(candidates, origin, direction, max_length, used=None):
    used = used or set()
    tolerance = max(max_length * 1e-5, 1e-6)
    best = None
    best_t = float("inf")

    for vertex in candidates:
        if vertex in used:
            continue
        rel = sub(position(vertex), origin)
        t = dot(rel, direction)
        if t <= tolerance or t > max_length + tolerance:
            continue
        perpendicular = sub(rel, mul(direction, t))
        if length(perpendicular) > tolerance:
            continue
        if t < best_t:
            best_t = t
            best = vertex
    return best


def calculate_distance(length1, length2, mode, distance, percent):
    if mode == "absolute":
        if distance <= 0:
            cmds.error("固定距离必须大于 0。")
        tangent = distance
    elif mode == "percent":
        if percent <= 0.0 or percent >= 1.0:
            cmds.error("边界百分比必须在 0 和 100 之间。")
        tangent = min(length1 * percent, length2 * percent)
    else:
        cmds.error('模式只能是 "absolute" 或 "percent"。')

    if tangent >= length1 or tangent >= length2:
        cmds.error("切角距离超过原边长度。")
    return tangent


def fillet_geometry(origin, u1, u2, tangent_distance, segments):
    if segments < 1:
        cmds.error("圆弧段数至少为 1。")

    u1 = normalize(u1)
    u2 = normalize(u2)
    theta = math.acos(clamp(dot(u1, u2), -1.0, 1.0))
    if theta < 1e-5:
        cmds.error("两条边夹角太小。")
    if abs(theta - math.pi) < 1e-5:
        cmds.error("两条边接近直线，无法生成圆角。")

    half = theta * 0.5
    cos_half = math.cos(half)
    if abs(cos_half) < _EPS:
        cmds.error("无法计算圆角圆心。")

    bisector = normalize(add(u1, u2))
    center = add(origin, mul(bisector, tangent_distance / cos_half))
    radius = tangent_distance * math.tan(half)
    p1 = add(origin, mul(u1, tangent_distance))
    p2 = add(origin, mul(u2, tangent_distance))

    r1 = normalize(sub(p1, center))
    r2 = normalize(sub(p2, center))
    arc_angle = math.acos(clamp(dot(r1, r2), -1.0, 1.0))
    axis = normalize(cross(r1, r2))
    if length(axis) < _EPS:
        cmds.error("无法确定圆角平面。")

    points = []
    for i in range(segments + 1):
        t = float(i) / float(segments)
        direction = rotate(r1, axis, arc_angle * t)
        points.append(add(center, mul(direction, radius)))

    return p1, p2, center, radius, points


def find_face_fan(origin, first_edge, second_edge):
    incident_edges = vertex_edges(origin)
    incident_set = set(incident_edges)
    graph = {edge: set() for edge in incident_edges}

    for face in vertex_faces(origin):
        radial = [edge for edge in face_edges(face) if edge in incident_set]
        if len(radial) < 2:
            continue
        for i in range(len(radial)):
            for j in range(i + 1, len(radial)):
                graph[radial[i]].add(radial[j])
                graph[radial[j]].add(radial[i])

    paths = []

    def walk(current, path):
        if current == second_edge:
            paths.append(list(path))
            return
        for next_edge in graph.get(current, []):
            if next_edge not in path:
                walk(next_edge, path + [next_edge])

    walk(first_edge, [first_edge])
    if not paths:
        cmds.error("无法找到两条边之间的面路径。")
    paths.sort(key=len)
    return paths[0]


def circle_ray_intersection(origin, direction, center, radius, max_length):
    oc = sub(origin, center)
    b = 2.0 * dot(direction, oc)
    c = dot(oc, oc) - radius * radius
    discriminant = b * b - 4.0 * c
    if discriminant < -1e-8:
        return None

    root = math.sqrt(max(0.0, discriminant))
    tolerance = max(max_length * 1e-5, 1e-6)
    valid = [
        s
        for s in ((-b - root) * 0.5, (-b + root) * 0.5)
        if s > tolerance and s <= max_length + tolerance
    ]
    if not valid:
        return None
    return add(origin, mul(direction, min(valid)))


def round_inner_boundary(edges, mode, distance, percent, segments):
    edge1, edge2 = edges
    mesh = mesh_of(edge1)
    if mesh_of(edge2) != mesh:
        cmds.error("两条边必须属于同一 Mesh。")

    faces1 = edge_faces(edge1)
    faces2 = edge_faces(edge2)
    if len(faces1) != 1 or len(faces2) != 1:
        cmds.error("内角模式请选择两条真正的边界边。")

    common = set(edge_vertices(edge1)) & set(edge_vertices(edge2))
    if len(common) != 1:
        cmds.error("两条边必须共享一个顶点。")

    origin_vertex = list(common)[0]
    origin = position(origin_vertex)
    other1 = other_vertex(edge1, origin_vertex)
    other2 = other_vertex(edge2, origin_vertex)
    vec1 = sub(position(other1), origin)
    vec2 = sub(position(other2), origin)
    len1 = length(vec1)
    len2 = length(vec2)
    u1 = normalize(vec1)
    u2 = normalize(vec2)

    tangent_distance = calculate_distance(len1, len2, mode, distance, percent)
    p1, p2, _center, radius, arc_points = fillet_geometry(
        origin, u1, u2, tangent_distance, segments
    )

    reference_normal = face_normal(mesh, faces1[0])

    before = cmds.polyEvaluate(mesh, vertex=True)
    cmds.polySubdivideEdge([edge1, edge2], divisions=1, constructionHistory=False)
    created_by_split = new_vertices(mesh, before)
    if len(created_by_split) < 2:
        cmds.error("无法在两条边界边上创建切角点。")

    endpoint1 = find_candidate_on_ray(created_by_split, origin, u1, len1)
    if endpoint1 is None:
        cmds.error("无法定位第一侧切角点。")
    endpoint2 = find_candidate_on_ray(
        created_by_split, origin, u2, len2, used={endpoint1}
    )
    if endpoint2 is None:
        cmds.error("无法定位第二侧切角点。")

    cmds.xform(endpoint1, ws=True, t=p1)
    cmds.xform(endpoint2, ws=True, t=p2)

    p1_index = index_of(endpoint1, "vtx")
    p2_index = index_of(endpoint2, "vtx")
    origin_index = index_of(origin_vertex, "vtx")
    middle_points = arc_points[1:-1]
    local_middle = [world_to_object(mesh, p) for p in middle_points]

    append_data = [origin_index, p1_index]
    append_data.extend(local_middle)
    append_data.append(p2_index)

    normal_points = [origin, p1]
    normal_points.extend(middle_points)
    normal_points.append(p2)
    if dot(polygon_normal(normal_points), reference_normal) < 0.0:
        append_data = list(reversed(append_data))

    before_append = cmds.polyEvaluate(mesh, vertex=True)
    cmds.polyAppendVertex(mesh, append=append_data, constructionHistory=False)
    created_arc = new_vertices(mesh, before_append)

    result = [endpoint1] + created_arc + [endpoint2]
    cmds.select(result, replace=True)
    return len1, len2, tangent_distance, radius


def round_outer_boundary(vertex, mode, distance, percent, segments, flip=True):
    mesh = mesh_of(vertex)
    b_edges = boundary_edges(vertex)
    if len(b_edges) != 2:
        cmds.error("外角顶点必须正好连接两条边界边。")

    edge1, edge2 = b_edges
    if flip:
        edge1, edge2 = edge2, edge1

    origin = position(vertex)
    other1 = other_vertex(edge1, vertex)
    other2 = other_vertex(edge2, vertex)
    vec1 = sub(position(other1), origin)
    vec2 = sub(position(other2), origin)
    len1 = length(vec1)
    len2 = length(vec2)
    u1 = normalize(vec1)
    u2 = normalize(vec2)

    tangent_distance = calculate_distance(len1, len2, mode, distance, percent)
    _p1, _p2, center, radius, _arc_points = fillet_geometry(
        origin, u1, u2, tangent_distance, segments
    )

    fan = find_face_fan(vertex, edge1, edge2)
    directions = []
    lengths = []
    for edge in fan:
        other = other_vertex(edge, vertex)
        vec = sub(position(other), origin)
        directions.append(normalize(vec))
        lengths.append(length(vec))

    before_split = cmds.polyEvaluate(mesh, vertex=True)
    insert_points = [(index_of(edge, "e"), 0.5) for edge in fan]
    cmds.polySplit(mesh, insertpoint=insert_points, constructionHistory=False)
    created_by_split = new_vertices(mesh, before_split)
    if len(created_by_split) < len(fan):
        cmds.error("外角切割没有生成足够的切点。")

    base_vertices = []
    used = set()
    for direction, max_length in zip(directions, lengths):
        new_vertex = find_candidate_on_ray(
            created_by_split, origin, direction, max_length, used=used
        )
        if new_vertex is None:
            cmds.error("无法定位外角切割点。")
        used.add(new_vertex)
        base_vertices.append(new_vertex)

    ordered_points = []
    for direction, max_length in zip(directions, lengths):
        p = circle_ray_intersection(origin, direction, center, radius, max_length)
        if p is None:
            cmds.error("圆弧与当前拓扑边没有有效交点，切角距离可能过大。")
        ordered_points.append(p)

    for vertex_component, p in zip(base_vertices, ordered_points):
        cmds.xform(vertex_component, ws=True, t=p)

    interval_count = len(base_vertices) - 1
    if interval_count < 1:
        cmds.error("外角拓扑不足，无法生成圆弧。")
    if segments < interval_count:
        cmds.error(
            "圆弧段数 %d 小于当前拓扑跨越的 %d 个面；请提高圆弧段数。"
            % (segments, interval_count)
        )

    allocation = [1 for _ in range(interval_count)]
    left = segments - interval_count
    for i in range(left):
        allocation[i % interval_count] += 1

    for interval in range(interval_count):
        a_vtx = base_vertices[interval]
        b_vtx = base_vertices[interval + 1]
        pieces = allocation[interval]
        if pieces <= 1:
            continue

        edge = edge_between(a_vtx, b_vtx)
        if edge is None:
            cmds.error("无法找到外角切割边。")

        before = cmds.polyEvaluate(mesh, vertex=True)
        cmds.polySubdivideEdge(edge, divisions=pieces - 1, constructionHistory=False)
        added = new_vertices(mesh, before)
        if len(added) != pieces - 1:
            cmds.error("外角圆弧细分顶点数量异常。")

        start = position(a_vtx)
        end = position(b_vtx)
        chord = sub(end, start)
        chord_l2 = dot(chord, chord)
        if chord_l2 < _EPS:
            cmds.error("外角切割边长度异常。")
        added.sort(key=lambda v: dot(sub(position(v), start), chord) / chord_l2)

        r_start = normalize(sub(start, center))
        r_end = normalize(sub(end, center))
        angle = math.acos(clamp(dot(r_start, r_end), -1.0, 1.0))
        axis = normalize(cross(r_start, r_end))
        if length(axis) < _EPS:
            cmds.error("无法确定外角圆弧方向。")

        for j, vtx in enumerate(added, start=1):
            local_t = float(j) / float(pieces)
            p = add(center, mul(rotate(r_start, axis, angle * local_t), radius))
            cmds.xform(vtx, ws=True, t=p)

    delete_faces = vertex_faces(vertex)
    if delete_faces:
        cmds.delete(delete_faces)

    cmds.select(clear=True)
    return len1, len2, tangent_distance, radius


def chamfer_round(
    mode="percent",
    distance=0.2,
    percent=0.25,
    segments=8,
    flip=True,
):
    selection = cmds.ls(sl=True, fl=True) or []
    vertices = cmds.filterExpand(selection, sm=31) or []
    edges = cmds.filterExpand(selection, sm=32) or []

    cmds.undoInfo(openChunk=True)
    try:
        if len(vertices) == 1 and not edges:
            length1, length2, tangent_distance, radius = round_outer_boundary(
                vertices[0], mode, distance, percent, segments, flip=flip
            )
            corner_type = "OUTER"
        elif len(edges) == 2 and not vertices:
            length1, length2, tangent_distance, radius = round_inner_boundary(
                edges, mode, distance, percent, segments
            )
            corner_type = "INNER"
        else:
            cmds.error(
                "选择 1 个边界顶点处理外角，或选择 2 条共享顶点的边界边处理内角。"
            )
            return

        print(
            "圆角完成 | %s | %s | edge1=%.6f | edge2=%.6f | "
            "tangent=%.6f | radius=%.6f | segments=%d | flip=%s"
            % (
                corner_type,
                mode.upper(),
                length1,
                length2,
                tangent_distance,
                radius,
                segments,
                bool(flip),
            )
        )
    finally:
        cmds.undoInfo(closeChunk=True)


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
    mode_menu = cmds.optionMenu()
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
        annotation="仅影响外角拓扑遍历方向；默认开启。",
    )

    cmds.separator(style="in", height=10)

    def sync_enabled(*_):
        current_mode = (
            "percent"
            if cmds.optionMenu(mode_menu, q=True, select=True) == 1
            else "absolute"
        )
        cmds.floatFieldGrp(
            percent_field, e=True, enable=(current_mode == "percent")
        )
        cmds.floatFieldGrp(
            distance_field, e=True, enable=(current_mode == "absolute")
        )

    def execute(*_):
        current_mode = (
            "percent"
            if cmds.optionMenu(mode_menu, q=True, select=True) == 1
            else "absolute"
        )
        distance = cmds.floatFieldGrp(distance_field, q=True, value1=True)
        percent_ui = cmds.floatFieldGrp(percent_field, q=True, value1=True)
        segments = cmds.intFieldGrp(segments_field, q=True, value1=True)
        flip = cmds.checkBoxGrp(flip_check, q=True, value1=True)

        if current_mode == "percent" and not (0.0 < percent_ui < 100.0):
            cmds.error("边界百分比必须大于 0 且小于 100。")
        if current_mode == "absolute" and distance <= 0.0:
            cmds.error("固定距离必须大于 0。")
        if segments < 1:
            cmds.error("圆弧段数至少为 1。")

        cmds.optionVar(sv=(OPT_MODE, current_mode))
        cmds.optionVar(fv=(OPT_DISTANCE, distance))
        cmds.optionVar(fv=(OPT_PERCENT, percent_ui))
        cmds.optionVar(iv=(OPT_SEGMENTS, segments))
        cmds.optionVar(iv=(OPT_FLIP, int(bool(flip))))

        chamfer_round(
            mode=current_mode,
            distance=distance,
            percent=percent_ui / 100.0,
            segments=segments,
            flip=flip,
        )

    cmds.optionMenu(mode_menu, e=True, changeCommand=sync_enabled)
    cmds.button(label="执行圆角切角", height=34, command=execute)
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

    sync_enabled()
    cmds.showWindow(win)
    return win


if __name__ == "__main__":
    show()
