from pathlib import Path

p = Path('scripts/maya_user/polygon_modeling/round_chamfer.py')
s = p.read_text(encoding='utf-8')

def rep(old, new, count=1):
    global s
    found = s.count(old)
    if found < count:
        raise SystemExit('patch target missing: %r found=%d' % (old[:80], found))
    s = s.replace(old, new, count)

helpers = r'''
def quadratic_point(p1, control, p2, t):
    omt = 1.0 - t
    return add(
        add(mul(p1, omt * omt), mul(control, 2.0 * omt * t)),
        mul(p2, t * t),
    )


def edge_percent_parameter(direction, u1, u2, distance1, distance2):
    c = dot(u1, u2)
    denom = 1.0 - c * c
    if abs(denom) < _EPS:
        cmds.error("两条边夹角异常，无法计算双边百分比曲线。")

    du = dot(direction, u1)
    dv = dot(direction, u2)
    a = (du - c * dv) / denom
    b = (dv - c * du) / denom
    tolerance = 1e-8
    if a < -tolerance or b < -tolerance:
        return None
    a = max(0.0, a)
    b = max(0.0, b)
    if b <= tolerance:
        return 0.0
    if a <= tolerance:
        return 1.0

    ratio = (b * distance1) / (a * distance2)
    if ratio < 0.0:
        return None
    k = math.sqrt(ratio)
    return k / (1.0 + k)
'''
rep('\n\ndef fillet_geometry(origin, u1, u2, tangent_distance, segments):', helpers + '\n\ndef fillet_geometry(origin, u1, u2, tangent_distance, segments):')

rep(
'''    tangent_distance = calculate_distance(len1, len2, mode, distance, percent)
    _p1, _p2, center, radius, _arc_points = fillet_geometry(
        origin, u1, u2, tangent_distance, segments
    )

    fan = find_face_fan(vertex, edge1, edge2)
''',
'''    curve_p1 = None
    curve_p2 = None
    radius = None
    if mode == "edge_percent":
        if percent <= 0.0 or percent >= 1.0:
            cmds.error("双边百分比必须在 0 和 100 之间。")
        distance1 = len1 * percent
        distance2 = len2 * percent
        curve_p1 = add(origin, mul(u1, distance1))
        curve_p2 = add(origin, mul(u2, distance2))
        tangent_distance = (distance1, distance2)
    else:
        tangent_distance = calculate_distance(len1, len2, mode, distance, percent)
        _p1, _p2, center, radius, _arc_points = fillet_geometry(
            origin, u1, u2, tangent_distance, segments
        )

    fan = find_face_fan(vertex, edge1, edge2)
''')

rep(
'''    ordered_points = []
    for direction, max_length in zip(directions, lengths):
        p = circle_ray_intersection(origin, direction, center, radius, max_length)
        if p is None:
            cmds.error("圆弧与当前拓扑边没有有效交点，切角距离可能过大。")
        ordered_points.append(p)
''',
'''    ordered_points = []
    curve_parameters = []
    if mode == "edge_percent":
        distance1, distance2 = tangent_distance
        for direction, max_length in zip(directions, lengths):
            t = edge_percent_parameter(direction, u1, u2, distance1, distance2)
            if t is None:
                cmds.error("双边百分比曲线与当前拓扑边没有有效交点。")
            p = quadratic_point(curve_p1, origin, curve_p2, t)
            if length(sub(p, origin)) > max_length + max(max_length * 1e-5, 1e-6):
                cmds.error("双边百分比切点超过当前拓扑边长度。")
            curve_parameters.append(t)
            ordered_points.append(p)
    else:
        for direction, max_length in zip(directions, lengths):
            p = circle_ray_intersection(origin, direction, center, radius, max_length)
            if p is None:
                cmds.error("圆弧与当前拓扑边没有有效交点，切角距离可能过大。")
            ordered_points.append(p)
''')

rep(
'''        r_start = normalize(sub(start, center))
        r_end = normalize(sub(end, center))
        angle = math.acos(clamp(dot(r_start, r_end), -1.0, 1.0))
        axis = normalize(cross(r_start, r_end))
        if length(axis) < _EPS:
            cmds.error("无法确定外角圆弧方向。")

        for j, vtx in enumerate(added, start=1):
            local_t = float(j) / float(pieces)
            p = add(center, mul(rotate(r_start, axis, angle * local_t), radius))
            cmds.xform(vtx, ws=True, t=p)
''',
'''        if mode == "edge_percent":
            t_start = curve_parameters[interval]
            t_end = curve_parameters[interval + 1]
            for j, vtx in enumerate(added, start=1):
                local_t = float(j) / float(pieces)
                global_t = t_start + (t_end - t_start) * local_t
                p = quadratic_point(curve_p1, origin, curve_p2, global_t)
                cmds.xform(vtx, ws=True, t=p)
        else:
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
''')

rep(
'''        elif len(edges) == 2 and not vertices:
            length1, length2, tangent_distance, radius = round_inner_boundary(
''',
'''        elif len(edges) == 2 and not vertices:
            if mode == "edge_percent":
                cmds.error("双边百分比模式仅用于选择 1 个边界顶点的外角。")
            length1, length2, tangent_distance, radius = round_inner_boundary(
''')

rep(
'''        print(
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
''',
'''        if mode == "edge_percent":
            distance1, distance2 = tangent_distance
            print(
                "圆角完成 | %s | EDGE_PERCENT | edge1=%.6f | edge2=%.6f | "
                "cut1=%.6f | cut2=%.6f | segments=%d | flip=%s"
                % (corner_type, length1, length2, distance1, distance2, segments, bool(flip))
            )
        else:
            print(
                "圆角完成 | %s | %s | edge1=%.6f | edge2=%.6f | "
                "tangent=%.6f | radius=%.6f | segments=%d | flip=%s"
                % (corner_type, mode.upper(), length1, length2, tangent_distance, radius, segments, bool(flip))
            )
''')

rep(
'''    cmds.menuItem(label="百分比")
    cmds.menuItem(label="固定距离")
''',
'''    cmds.menuItem(label="百分比（统一圆弧）")
    cmds.menuItem(label="双边百分比（单顶点）")
    cmds.menuItem(label="固定距离")
''')

old_mode = '''        current_mode = (
            "percent"
            if cmds.optionMenu(mode_menu, q=True, select=True) == 1
            else "absolute"
        )'''
new_mode = '''        selected_mode = cmds.optionMenu(mode_menu, q=True, select=True)
        current_mode = "percent" if selected_mode == 1 else ("edge_percent" if selected_mode == 2 else "absolute")'''
rep(old_mode, new_mode, 1)
rep(old_mode, new_mode, 1)

rep('percent_field, e=True, enable=(current_mode == "percent")', 'percent_field, e=True, enable=(current_mode in ("percent", "edge_percent"))')
rep('if current_mode == "percent" and not (0.0 < percent_ui < 100.0):', 'if current_mode in ("percent", "edge_percent") and not (0.0 < percent_ui < 100.0):')
rep('annotation="按两侧边界允许值取较小值，保持严格相切圆弧。",', 'annotation="统一圆弧按较短侧计算；双边百分比按两条边自身长度分别计算。",')
rep(
'''    cmds.optionMenu(
        mode_menu,
        edit=True,
        select=1 if saved_mode == "percent" else 2,
    )
''',
'''    saved_select = {"percent": 1, "edge_percent": 2, "absolute": 3}.get(saved_mode, 1)
    cmds.optionMenu(mode_menu, edit=True, select=saved_select)
''')

p.write_text(s, encoding='utf-8')
