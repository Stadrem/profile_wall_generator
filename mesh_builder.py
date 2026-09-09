import bpy
from math import exp
from mathutils import Vector

from . import path_utils
from . import profile_presets
from . import uv_utils


TOP_TRIM_BORDER_MAX_FRACTION = 0.49


def _build_profile_wall_geometry(points, closed, props, *, solid_hole=False, skip_solid_caps=False):
    """Calculate one spline entirely in memory without Blender datablocks."""
    preset = profile_presets.get_preset(props.profile_preset)
    base_profile = list(preset["profile"])
    profile = list(base_profile)
    
    # Adjust trim heights based on scales
    if getattr(props, "bottom_trim_scale", 1.0) != 1.0 or getattr(props, "top_trim_scale", 1.0) != 1.0:
        profile = _adjust_profile_trims(profile, props.bottom_trim_scale, props.top_trim_scale)
        
    profile_presets.validate_profile(profile)

    normals, miter_factors = path_utils.compute_normals(points, closed=closed, flip=props.flip_direction)
    if solid_hole:
        normals = [-normal for normal in normals]
    distances = path_utils.cumulative_lengths(points, closed=closed)
    material_keys = _material_keys_for_profile_segments(profile)

    has_thickness = props.wall_thickness > 0.0
    fill_inside = getattr(props, "fill_inside", False) and closed

    if fill_inside:
        has_thickness = False

    # Determine front/back thickness offsets based on direction setting.
    if not has_thickness:
        front_thickness = 0.0
        back_thickness = 0.0
    elif props.thickness_direction == "OUTSIDE":
        front_thickness = props.wall_thickness
        back_thickness = 0.0
    elif props.thickness_direction == "INSIDE":
        front_thickness = 0.0
        back_thickness = -props.wall_thickness
    else:  # CENTER
        front_thickness = props.wall_thickness / 2.0
        back_thickness = -props.wall_thickness / 2.0

    point_count = len(points)
    profile_count = len(profile)
    front_vert_count = point_count * profile_count

    # --- Vertex generation ---------------------------------------------------
    vertices = []
    vertex_meta = []

    def _emit_layer(thickness_offset, use_profile_offset=True):
        """Emit one full layer of vertices (front or back) with arc-length V mapping."""
        v_coords = _compute_profile_v_coords(
            profile,
            props.height_scale,
            props.offset_scale,
            use_profile_offset=use_profile_offset,
        )
        for point_index, point in enumerate(points):
            base = Vector((point.x, point.y, point.z))
            normal = normals[point_index]
            miter_factor = min(miter_factors[point_index], props.miter_limit)
            for pri, (z, offset, material_key) in enumerate(profile):
                profile_offset = offset * props.offset_scale if use_profile_offset else 0.0
                total_offset = profile_offset + thickness_offset
                co = base + normal * (total_offset * miter_factor)
                co.z = base.z + (z * props.height_scale)
                vertices.append((co.x, co.y, co.z))
                vertex_meta.append({
                    "u": distances[point_index],
                    "v": v_coords[pri],
                    "offset": total_offset,
                    "material_key": material_key,
                })

    _emit_layer(front_thickness)
    if has_thickness:
        _emit_layer(
            back_thickness,
            use_profile_offset=not getattr(props, "flat_inner_face", True),
        )

    # Index helpers
    def front_grid(pi, pri):
        return pi * profile_count + pri

    def back_grid(pi, pri):
        return front_vert_count + pi * profile_count + pri

    # --- Face generation ------------------------------------------------------
    faces = []
    face_material_keys = []
    face_uvs = []
    section_count = point_count if closed else point_count - 1

    def _uv_wall(idx):
        return (vertex_meta[idx]["u"], vertex_meta[idx]["v"])

    def _uv_cap(idx):
        return (vertex_meta[idx]["offset"], vertex_meta[idx]["v"])

    def _uv_strip(idx):
        return (vertex_meta[idx]["u"], vertex_meta[idx]["offset"])

    def _add_face(face, uv, mat_key, expected_normal):
        if _face_points_away_from_expected(face, vertices, expected_normal):
            face = list(reversed(face))
            uv = list(reversed(uv))
        faces.append(tuple(face))
        face_material_keys.append(mat_key)
        face_uvs.append(uv)

    def _add_interpolated_vertex(start_index, end_index, factor, material_key):
        start = Vector(vertices[start_index])
        end = Vector(vertices[end_index])
        co = start.lerp(end, factor)
        start_meta = vertex_meta[start_index]
        end_meta = vertex_meta[end_index]
        vertices.append((co.x, co.y, co.z))
        vertex_meta.append({
            "u": start_meta["u"] + (end_meta["u"] - start_meta["u"]) * factor,
            "v": start_meta["v"] + (end_meta["v"] - start_meta["v"]) * factor,
            "offset": start_meta["offset"]
            + (end_meta["offset"] - start_meta["offset"]) * factor,
            "material_key": material_key,
        })
        return len(vertices) - 1

    # Front faces
    for point_index in range(section_count):
        next_index = (point_index + 1) % point_count
        expected = normals[point_index] + normals[next_index]
        if expected.length == 0.0:
            expected = normals[point_index]
        for profile_index in range(profile_count - 1):
            a = front_grid(point_index, profile_index)
            b = front_grid(point_index, profile_index + 1)
            c = front_grid(next_index, profile_index + 1)
            d = front_grid(next_index, profile_index)
            _add_face(
                [a, b, c, d],
                [_uv_wall(a), _uv_wall(b), _uv_wall(c), _uv_wall(d)],
                material_keys[profile_index],
                expected,
            )

    if has_thickness:
        # Back faces (opposite expected normal direction)
        for point_index in range(section_count):
            next_index = (point_index + 1) % point_count
            expected = -(normals[point_index] + normals[next_index])
            if expected.length == 0.0:
                expected = -normals[point_index]
            for profile_index in range(profile_count - 1):
                a = back_grid(point_index, profile_index)
                b = back_grid(point_index, profile_index + 1)
                c = back_grid(next_index, profile_index + 1)
                d = back_grid(next_index, profile_index)
                _add_face(
                    [a, b, c, d],
                    [_uv_wall(a), _uv_wall(b), _uv_wall(c), _uv_wall(d)],
                    material_keys[profile_index],
                    expected,
                )

        # Top strip. Split it like an inset so both long boundary edges use
        # Trim while the center keeps the Top material.
        top_pi = profile_count - 1
        top_cross_widths = [
            (Vector(vertices[front_grid(point_index, top_pi)])
             - Vector(vertices[back_grid(point_index, top_pi)])).length
            for point_index in range(point_count)
        ]
        border_fraction = _top_trim_border_fraction(
            props,
            base_profile,
            top_cross_widths,
        )
        front_inner = None
        back_inner = None
        if border_fraction > 0.0:
            front_inner = []
            back_inner = []
            for point_index in range(point_count):
                front_index = front_grid(point_index, top_pi)
                back_index = back_grid(point_index, top_pi)
                front_inner.append(_add_interpolated_vertex(
                    front_index, back_index, border_fraction, "trim"
                ))
                back_inner.append(_add_interpolated_vertex(
                    back_index, front_index, border_fraction, "trim"
                ))

            for point_index in range(section_count):
                next_index = (point_index + 1) % point_count
                fl = front_grid(point_index, top_pi)
                fr = front_grid(next_index, top_pi)
                br = back_grid(next_index, top_pi)
                bl = back_grid(point_index, top_pi)
                fil = front_inner[point_index]
                fir = front_inner[next_index]
                bil = back_inner[point_index]
                bir = back_inner[next_index]

                _add_face(
                    [fl, fil, fir, fr],
                    [_uv_strip(fl), _uv_strip(fil), _uv_strip(fir), _uv_strip(fr)],
                    "trim",
                    Vector((0.0, 0.0, 1.0)),
                )
                _add_face(
                    [fil, bil, bir, fir],
                    [_uv_strip(fil), _uv_strip(bil), _uv_strip(bir), _uv_strip(fir)],
                    "top",
                    Vector((0.0, 0.0, 1.0)),
                )
                _add_face(
                    [bil, bl, br, bir],
                    [_uv_strip(bil), _uv_strip(bl), _uv_strip(br), _uv_strip(bir)],
                    "trim",
                    Vector((0.0, 0.0, 1.0)),
                )
        else:
            for point_index in range(section_count):
                next_index = (point_index + 1) % point_count
                fl = front_grid(point_index, top_pi)
                fr = front_grid(next_index, top_pi)
                br = back_grid(next_index, top_pi)
                bl = back_grid(point_index, top_pi)
                _add_face(
                    [fl, bl, br, fr],
                    [_uv_strip(fl), _uv_strip(bl), _uv_strip(br), _uv_strip(fr)],
                    "top",
                    Vector((0.0, 0.0, 1.0)),
                )

        # Bottom strip (connect front bottom edge to back bottom edge along path)
        for point_index in range(section_count):
            next_index = (point_index + 1) % point_count
            fl = front_grid(point_index, 0)
            fr = front_grid(next_index, 0)
            br = back_grid(next_index, 0)
            bl = back_grid(point_index, 0)
            _add_face(
                [fl, fr, br, bl],
                [_uv_strip(fl), _uv_strip(fr), _uv_strip(br), _uv_strip(bl)],
                "body",
                Vector((0.0, 0.0, -1.0)),
            )

        # Optional interior floor for a closed hollow wall. It is intentionally
        # a separate face island: the wall continues below Section Height while
        # the floor marks the usable inside area above that lower wall portion.
        if closed and getattr(props, "generate_section", False):
            import mathutils.geometry

            wall_height = max(
                0.0,
                (profile[-1][0] - profile[0][0]) * abs(props.height_scale),
            )
            section_height = min(
                max(0.0, float(getattr(props, "section_height", 0.2))),
                wall_height,
            )
            height_scale = abs(props.height_scale)
            local_height = (
                profile[0][0] + section_height / height_scale
                if height_scale > 1e-8
                else profile[0][0]
            )
            profile_offset = _profile_offset_at_height(profile, local_height)

            use_front_boundary = bool(props.flip_direction)
            if use_front_boundary:
                boundary_thickness = front_thickness
                use_profile_offset = True
            else:
                boundary_thickness = back_thickness
                use_profile_offset = not getattr(props, "flat_inner_face", True)

            section_indices = []
            for point_index, point in enumerate(points):
                base = Vector((point.x, point.y, point.z))
                miter_factor = min(miter_factors[point_index], props.miter_limit)
                total_offset = boundary_thickness
                if use_profile_offset:
                    total_offset += profile_offset * props.offset_scale
                co = base + normals[point_index] * (total_offset * miter_factor)
                co.z = base.z + profile[0][0] * props.height_scale + section_height
                section_indices.append(len(vertices))
                vertices.append((co.x, co.y, co.z))
                vertex_meta.append({
                    "u": co.x,
                    "v": co.y,
                    "offset": total_offset,
                    "material_key": "section",
                })

            section_poly_2d = [
                Vector((vertices[index][0], vertices[index][1]))
                for index in section_indices
            ]
            # Planar XY projection with a local origin keeps the floor island
            # visible near UV 0,0 while preserving object-space dimensions for
            # seamless repeating/tile textures.
            section_uv_origin = Vector((
                min(point.x for point in section_poly_2d),
                min(point.y for point in section_poly_2d),
            ))
            section_uv_scale = max(
                0.0001,
                float(getattr(props, "section_uv_scale", 1.0)),
            )
            section_tris = mathutils.geometry.tessellate_polygon([section_poly_2d])
            for tri in section_tris:
                face = [section_indices[index] for index in tri]
                uv = [
                    (
                        (vertices[index][0] - section_uv_origin.x) * section_uv_scale,
                        (vertices[index][1] - section_uv_origin.y) * section_uv_scale,
                    )
                    for index in face
                ]
                _add_face(face, uv, "section", Vector((0.0, 0.0, 1.0)))

        # End caps for open curves
        if props.cap_ends and not closed and profile_count >= 2:
            # Start cap – outward normal points opposite to first segment
            start_dir = Vector((
                points[1].x - points[0].x,
                points[1].y - points[0].y,
                0.0,
            ))
            start_expected = -start_dir if start_dir.length > 0.0 else Vector((0.0, -1.0, 0.0))
            for profile_index in range(profile_count - 1):
                fl = front_grid(0, profile_index)
                fh = front_grid(0, profile_index + 1)
                bh = back_grid(0, profile_index + 1)
                bl = back_grid(0, profile_index)
                face = [fl, bl, bh, fh]
                if front_inner is not None and profile_index == profile_count - 2:
                    face = [
                        fl,
                        bl,
                        bh,
                        back_inner[0],
                        front_inner[0],
                        fh,
                    ]
                _add_face(
                    face,
                    [_uv_cap(index) for index in face],
                    "body",
                    start_expected,
                )

            # End cap – outward normal points along last segment direction
            end_dir = Vector((
                points[-1].x - points[-2].x,
                points[-1].y - points[-2].y,
                0.0,
            ))
            end_expected = end_dir if end_dir.length > 0.0 else Vector((0.0, 1.0, 0.0))
            last = point_count - 1
            for profile_index in range(profile_count - 1):
                fl = front_grid(last, profile_index)
                fh = front_grid(last, profile_index + 1)
                bh = back_grid(last, profile_index + 1)
                bl = back_grid(last, profile_index)
                face = [fl, fh, bh, bl]
                if front_inner is not None and profile_index == profile_count - 2:
                    face = [
                        fl,
                        fh,
                        front_inner[last],
                        back_inner[last],
                        bh,
                        bl,
                    ]
                _add_face(
                    face,
                    [_uv_cap(index) for index in face],
                    "body",
                    end_expected,
                )

    elif fill_inside and not skip_solid_caps:
        import mathutils.geometry
        
        # Top cap. Solid blocks use a closed inset loop so the outer ring gets
        # Trim and only the center polygon keeps the Top material.
        top_verts_idx = [front_grid(i, profile_count - 1) for i in range(point_count)]
        top_points = [Vector(vertices[index]) for index in top_verts_idx]
        border_width = _solid_top_trim_border_width(props, base_profile, top_points)
        inset_points = _inset_closed_loop(
            top_points,
            border_width,
            props.miter_limit,
        ) if border_width > 0.0 else None

        top_center_indices = top_verts_idx
        if inset_points is not None:
            top_center_indices = []
            for outer_index, co in zip(top_verts_idx, inset_points):
                top_center_indices.append(len(vertices))
                vertices.append((co.x, co.y, co.z))
                outer_meta = vertex_meta[outer_index]
                vertex_meta.append({
                    "u": co.x,
                    "v": co.y,
                    "offset": outer_meta["offset"],
                    "material_key": "top",
                })

            for point_index in range(point_count):
                next_index = (point_index + 1) % point_count
                outer_a = top_verts_idx[point_index]
                inner_a = top_center_indices[point_index]
                inner_b = top_center_indices[next_index]
                outer_b = top_verts_idx[next_index]
                face = [outer_a, inner_a, inner_b, outer_b]
                _add_face(
                    face,
                    [(vertices[index][0], vertices[index][1]) for index in face],
                    "trim",
                    Vector((0.0, 0.0, 1.0)),
                )

        top_poly_2d = [
            Vector((vertices[index][0], vertices[index][1]))
            for index in top_center_indices
        ]
        tris = mathutils.geometry.tessellate_polygon([top_poly_2d])
        for tri in tris:
            face = [top_center_indices[i] for i in tri]
            uv = [(vertices[index][0], vertices[index][1]) for index in face]
            _add_face(face, uv, "top", Vector((0.0, 0.0, 1.0)))
            
        # Bottom cap
        bottom_verts_idx = [front_grid(i, 0) for i in range(point_count)]
        bottom_poly_2d = [Vector((vertices[idx][0], vertices[idx][1])) for idx in bottom_verts_idx]
        
        tris = mathutils.geometry.tessellate_polygon([bottom_poly_2d])
        for tri in tris:
            face = [bottom_verts_idx[i] for i in tri]
            uv = [(vertices[idx][0], vertices[idx][1]) for idx in face]
            _add_face(face, uv, "body", Vector((0.0, 0.0, -1.0)))

    elif props.cap_ends and not closed and profile_count >= 3:
        # No thickness – original flat cap behaviour for single-layer mesh.
        start_face = tuple(reversed([
            front_grid(0, profile_index)
            for profile_index in range(profile_count)
        ]))
        end_face = tuple(
            front_grid(point_count - 1, profile_index)
            for profile_index in range(profile_count)
        )
        faces.append(start_face)
        face_material_keys.append("body")
        face_uvs.append(_cap_uvs(start_face, vertex_meta))
        faces.append(end_face)
        face_material_keys.append("body")
        face_uvs.append(_cap_uvs(end_face, vertex_meta))

    return vertices, faces, face_uvs, face_material_keys


def _create_wall_object(
    context,
    source_obj,
    geometry,
    props,
    existing_obj=None,
):
    """Create/replace the final Blender mesh once after all parts are merged."""
    vertices, faces, face_uvs, face_material_keys = geometry

    # ``path_utils`` extracts source points in world space.  A regenerated
    # wall keeps its existing object transform, so those coordinates must be
    # converted back to that object's local space before replacing its mesh.
    # Compute the inverse before allocating a mesh so a singular transform
    # fails without partially replacing the existing wall.
    world_to_local = None
    if existing_obj is not None:
        world_to_local = existing_obj.matrix_world.inverted()
        vertices = [
            tuple(world_to_local @ Vector(co))
            for co in vertices
        ]

    mesh = bpy.data.meshes.new(source_obj.name + "_ProfileWallMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    _warn_on_dropped_faces(mesh, len(faces), source_obj.name, "from_pydata")

    if existing_obj is not None:
        old_mesh = existing_obj.data
        existing_obj.data = mesh
        if old_mesh and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
        obj = existing_obj
    else:
        obj = bpy.data.objects.new(source_obj.name + "_ProfileWall", mesh)
        context.collection.objects.link(obj)

    # Material slots are added later by material_utils; keep keys as custom data
    # until operators convert them into material indices.
    obj["_profile_wall_face_material_keys"] = ",".join(face_material_keys)

    uv_utils.assign_basic_uv(mesh, face_uvs, props.uv_scale_u, props.uv_scale_v)
    mesh.validate(clean_customdata=False)
    _warn_on_dropped_faces(mesh, len(faces), source_obj.name, "mesh.validate")
    mesh.update()
    return obj, face_material_keys


def build_profile_wall_object(context, source_obj, points, closed, props, existing_obj=None):
    geometry = _build_profile_wall_geometry(points, closed, props)
    return _create_wall_object(
        context,
        source_obj,
        geometry,
        props,
        existing_obj=existing_obj,
    )


def build_profile_wall_paths_object(context, source_obj, paths, props, existing_obj=None):
    """Build all Curve splines as disconnected mesh islands in one wall object."""
    if not paths:
        raise path_utils.PathError("Source object has no usable paths.")
    if getattr(props, "fill_inside", False):
        parents = _solid_path_parents(paths)
        if any(parent is not None for parent in parents):
            return _create_wall_object(
                context, source_obj, _build_nested_solid_geometry(paths, parents, props),
                props, existing_obj=existing_obj,
            )
    if len(paths) == 1:
        points, closed = paths[0]
        return build_profile_wall_object(
            context, source_obj, points, closed, props, existing_obj=existing_obj
        )

    vertices = []
    faces = []
    face_uvs = []
    face_material_keys = []

    for points, closed in paths:
        part_vertices, part_faces, part_uvs, part_keys = _build_profile_wall_geometry(
            points,
            closed,
            props,
        )
        vertex_offset = len(vertices)
        vertices.extend(part_vertices)
        faces.extend(
            tuple(vertex_offset + index for index in face)
            for face in part_faces
        )
        face_uvs.extend(part_uvs)
        face_material_keys.extend(part_keys)

    return _create_wall_object(
        context,
        source_obj,
        (vertices, faces, face_uvs, face_material_keys),
        props,
        existing_obj=existing_obj,
    )


def _point_inside_loop(point, loop):
    inside = False
    for a, b in zip(loop, loop[1:] + loop[:1]):
        if (a.y > point.y) != (b.y > point.y):
            if point.x < a.x + (b.x - a.x) * (point.y - a.y) / (b.y - a.y):
                inside = not inside
    return inside


def _loops_intersect(a, b):
    from mathutils.geometry import intersect_line_line_2d
    return any(
        intersect_line_line_2d(p.xy, q.xy, r.xy, s.xy) is not None
        for p, q in zip(a, a[1:] + a[:1])
        for r, s in zip(b, b[1:] + b[:1])
    )


def _solid_path_parents(paths):
    """Containment, independent of winding; separate elevations stay independent."""
    areas = [abs(path_utils.signed_area_xy(points)) for points, _ in paths]
    parents = [None] * len(paths)
    for i, (points, closed) in enumerate(paths):
        if not closed:
            continue
        candidates = []
        for j, (outer, outer_closed) in enumerate(paths):
            if i == j or not outer_closed or areas[j] <= areas[i]:
                continue
            if max(p.z for p in points + outer) - min(p.z for p in points + outer) > 1e-5:
                continue
            if all(_point_inside_loop(p, outer) for p in points) and not _loops_intersect(points, outer):
                candidates.append(j)
        if candidates:
            parents[i] = min(candidates, key=lambda j: areas[j])
    return parents


def _triangulate_solid_cap(vertices, loops):
    """Constrained triangles with even/odd fill, retaining boundary vertex IDs."""
    from mathutils.geometry import delaunay_2d_cdt
    indices = [index for loop in loops for index in loop]
    coords = [Vector(vertices[index]).xy for index in indices]
    edges = []
    offset = 0
    polygons = []
    constraints = []
    for loop in loops:
        count = len(loop)
        edges.extend((offset + i, offset + (i + 1) % count) for i in range(count))
        polygons.append(coords[offset:offset + count])
        polygon = list(range(offset, offset + count))
        if path_utils.signed_area_xy(polygons[-1]) < 0:
            polygon.reverse()
        constraints.append(polygon)
        offset += count
    _, _, triangles, origins, _, face_origins = delaunay_2d_cdt(coords, edges, constraints, 0, 1e-7)
    if any(len(origin) != 1 for origin in origins):
        raise path_utils.PathError("Solid boundaries touch or intersect. Separate the overlapping outlines.")
    result = []
    for tri, sources in zip(triangles, face_origins):
        if len(sources) % 2:
            result.append(tuple(indices[origins[i][0]] for i in tri))
    return result


def _build_nested_solid_geometry(paths, parents, props):
    vertices, faces, uvs, keys = [], [], [], []

    def append_geometry(geometry):
        part_vertices, part_faces, part_uvs, part_keys = geometry
        offset = len(vertices)
        vertices.extend(part_vertices)
        faces.extend(tuple(offset + i for i in face) for face in part_faces)
        uvs.extend(part_uvs)
        keys.extend(part_keys)
        return offset

    def add_cap_face(face, key, up=True):
        expected = Vector((0, 0, 1 if up else -1))
        if _face_points_away_from_expected(face, vertices, expected):
            face = tuple(reversed(face))
        faces.append(tuple(face))
        uvs.append([(vertices[i][0], vertices[i][1]) for i in face])
        keys.append(key)

    depths = []
    for i in range(len(paths)):
        depth, parent = 0, parents[i]
        while parent is not None:
            depth += 1
            parent = parents[parent]
        depths.append(depth)

    profile = list(profile_presets.get_preset(props.profile_preset)["profile"])
    profile_count = len(profile)
    for i, (points, closed) in enumerate(paths):
        if depths[i] % 2:
            continue
        holes = [j for j, parent in enumerate(parents) if parent == i]
        if not holes:
            append_geometry(_build_profile_wall_geometry(points, closed, props))
            continue
        top_loops, bottom_loops = [], []
        for j in [i] + holes:
            boundary, _ = paths[j]
            offset = append_geometry(_build_profile_wall_geometry(
                boundary, True, props, solid_hole=j != i, skip_solid_caps=True,
            ))
            top_loops.append([offset + k * profile_count + profile_count - 1 for k in range(len(boundary))])
            bottom_loops.append([offset + k * profile_count for k in range(len(boundary))])

        # Preserve the top Trim border on both the outer wall and courtyard side.
        top_points = [[Vector(vertices[index]) for index in loop] for loop in top_loops]
        width = _solid_top_trim_border_width(props, profile, top_points[0])
        cap_faces, splits = _solid_top_trim_geometry(vertices, top_loops, width, props.miter_limit)
        _split_cap_boundary_faces(faces, uvs, splits)
        for face, key in cap_faces:
            add_cap_face(face, key)
        for face in _triangulate_solid_cap(vertices, bottom_loops):
            add_cap_face(face, "body", up=False)
    return vertices, faces, uvs, keys


def _solid_top_trim_geometry(vertices, loops, width, miter_limit):
    """Union the trim strips and clip them to the solid, including narrow corners."""
    from mathutils.geometry import delaunay_2d_cdt
    if width <= 0:
        return [(face, "top") for face in _triangulate_solid_cap(vertices, loops)], {}
    coords, originals, edges, bands, boundaries = [], [], [], [], []
    for loop_index, loop in enumerate(loops):
        points = [Vector(vertices[i]) for i in loop]
        normals, miters = path_utils.compute_normals(points, closed=True)
        sign = -1 if loop_index == 0 else 1
        inset = [p + n * (sign * width * min(m, miter_limit))
                 for p, n, m in zip(points, normals, miters)]
        start, count = len(coords), len(loop)
        boundary = list(range(start, start + count))
        if path_utils.signed_area_xy(points) < 0:
            boundary.reverse()
        boundaries.append(boundary)
        coords.extend(p.xy for p in points)
        originals.extend(loop)
        coords.extend(p.xy for p in inset)
        originals.extend([None] * count)
        for i in range(count):
            j = (i + 1) % count
            edges.append((start + i, start + j))
            # Two triangles also handle a strip folded over at a short edge.
            for band in [(start+i, start+j, start+count+j),
                         (start+i, start+count+j, start+count+i)]:
                if path_utils.signed_area_xy([coords[k] for k in band]) < 0:
                    band = tuple(reversed(band))
                bands.append(band)
    out_coords, out_edges, out_faces, origins, edge_origins, face_origins = delaunay_2d_cdt(
        coords, edges, boundaries + bands, 0, 1e-7,
    )
    mapped = {}
    z = vertices[loops[0][0]][2]

    def vertex(index):
        if index not in mapped:
            source = {originals[i] for i in origins[index] if originals[i] is not None}
            if len(source) > 1:
                raise path_utils.PathError("Solid boundaries touch. Separate the overlapping outlines.")
            if source:
                mapped[index] = source.pop()
            else:
                mapped[index] = len(vertices)
                p = out_coords[index]
                vertices.append((p.x, p.y, z))
        return mapped[index]

    result = []
    for triangle, sources in zip(out_faces, face_origins):
        if sum(source < len(boundaries) for source in sources) % 2:
            is_trim = any(source >= len(boundaries) for source in sources)
            result.append((tuple(vertex(i) for i in triangle), "trim" if is_trim else "top"))

    # Clipping can insert vertices on a wall boundary. Split the adjacent side
    # face too, so the cap remains welded instead of leaving T-junctions.
    edge_vertices = {}
    for edge, sources in zip(out_edges, edge_origins):
        for source in sources:
            if source < len(edges):
                edge_vertices.setdefault(source, set()).update(edge)
    splits = {}
    for source, indices in edge_vertices.items():
        a, b = edges[source]
        delta = coords[b] - coords[a]
        if delta.length_squared <= 1e-16:
            continue
        middle = []
        for index in indices:
            t = (out_coords[index] - coords[a]).dot(delta) / delta.length_squared
            if 1e-8 < t < 1 - 1e-8:
                middle.append((t, vertex(index)))
        if middle:
            middle.sort()
            splits[(originals[a], originals[b])] = middle
            splits[(originals[b], originals[a])] = [(1-t, i) for t, i in reversed(middle)]
    return result, splits


def _split_cap_boundary_faces(faces, uvs, splits):
    if not splits:
        return
    for index, (face, uv) in enumerate(zip(faces, uvs)):
        expanded, expanded_uv = [], []
        for k, a in enumerate(face):
            n = (k + 1) % len(face)
            expanded.append(a)
            expanded_uv.append(uv[k])
            for t, vertex in splits.get((a, face[n]), []):
                expanded.append(vertex)
                expanded_uv.append(tuple(uv[k][axis] * (1-t) + uv[n][axis] * t for axis in range(2)))
        faces[index] = tuple(expanded)
        uvs[index] = expanded_uv


def apply_face_material_indices(obj, material_indices, face_material_keys):
    # The keys are positional: entry N describes polygon N. If Blender rejected
    # any face while building the mesh the two lists no longer line up, and a
    # silent zip() would paint every face after the gap with the wrong
    # material. Report it instead of shifting the whole assignment.
    polygon_count = len(obj.data.polygons)
    if polygon_count != len(face_material_keys):
        print(
            "Profile Wall Generator: face count mismatch on "
            f"'{obj.name}' ({polygon_count} faces, {len(face_material_keys)} "
            "material keys). Materials may be misassigned; check the source "
            "path for self-intersections or duplicate points."
        )
    for polygon, key in zip(obj.data.polygons, face_material_keys):
        polygon.material_index = material_indices.get(key, 0)


def add_bevel_modifier(obj, props):
    for mod in list(obj.modifiers):
        if mod.name == "PWG Edge Bevel":
            obj.modifiers.remove(mod)

    if not props.add_bevel or props.bevel_width <= 0.0:
        return None
    modifier = obj.modifiers.new("PWG Edge Bevel", "BEVEL")
    modifier.width = props.bevel_width
    modifier.segments = max(1, int(getattr(props, "bevel_segments", 1)))
    modifier.affect = "EDGES"
    try:
        modifier.limit_method = "ANGLE"
        modifier.harden_normals = True
    except AttributeError:
        pass
    return modifier


def _is_valid_smooth_by_angle_node_group(node_group):
    """Validate that a node group has the expected Geometry Nodes Smooth by Angle interface."""
    if node_group is None or getattr(node_group, "type", None) != "GEOMETRY":
        return False
    if not hasattr(node_group, "interface") or not hasattr(node_group.interface, "items_tree"):
        return False

    has_geom_input = False
    has_geom_output = False
    has_angle_input = False

    for item in node_group.interface.items_tree:
        if getattr(item, "item_type", None) != "SOCKET":
            continue
        in_out = getattr(item, "in_out", None)
        socket_type = getattr(item, "socket_type", None)
        name = getattr(item, "name", "")

        if in_out == "INPUT" and socket_type == "NodeSocketGeometry":
            has_geom_input = True
        elif in_out == "OUTPUT" and socket_type == "NodeSocketGeometry":
            has_geom_output = True
        elif in_out == "INPUT" and name == "Angle" and socket_type == "NodeSocketFloat":
            has_angle_input = True

    return has_geom_input and has_geom_output and has_angle_input


def _get_or_load_smooth_by_angle_node_group():
    # 1. Check existing node groups with matching name
    existing = bpy.data.node_groups.get("Smooth by Angle")
    if _is_valid_smooth_by_angle_node_group(existing):
        return existing

    # 2. If the exact name is taken by an invalid group, look for existing numbered variants
    for ng in bpy.data.node_groups:
        if ng.name.startswith("Smooth by Angle") and _is_valid_smooth_by_angle_node_group(ng):
            return ng

    # 3. Load from geometry_nodes_essentials.blend
    import os
    version_str = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
    essentials_path = os.path.join(
        os.path.dirname(bpy.app.binary_path),
        version_str,
        "datafiles",
        "assets",
        "nodes",
        "geometry_nodes_essentials.blend",
    )
    if os.path.isfile(essentials_path):
        try:
            with bpy.data.libraries.load(essentials_path, link=False) as (data_from, data_to):
                if "Smooth by Angle" in data_from.node_groups:
                    data_to.node_groups = ["Smooth by Angle"]
            for ng in reversed(list(bpy.data.node_groups)):
                if ng.name.startswith("Smooth by Angle") and _is_valid_smooth_by_angle_node_group(ng):
                    return ng
        except Exception:
            pass
    return None


def _find_angle_socket_identifier(node_group):
    if hasattr(node_group, "interface") and hasattr(node_group.interface, "items_tree"):
        for item in node_group.interface.items_tree:
            if (
                getattr(item, "item_type", None) == "SOCKET"
                and getattr(item, "in_out", None) == "INPUT"
                and getattr(item, "name", None) == "Angle"
                and getattr(item, "socket_type", None) == "NodeSocketFloat"
            ):
                return item.identifier
    return None


def apply_smooth_shading(obj, props):
    mesh = obj.data
    use_smooth = bool(getattr(props, "shade_smooth", False))
    angle_val = float(getattr(props, "smooth_angle", 0.523599))

    for mod in list(obj.modifiers):
        if mod.name == "PWG Smooth by Angle":
            obj.modifiers.remove(mod)

    if not use_smooth:
        if mesh.polygons:
            mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
        if mesh.edges:
            mesh.edges.foreach_set("use_edge_sharp", [False] * len(mesh.edges))
        return None

    # Enable smooth shading on polygons
    if mesh.polygons:
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))

    node_group = _get_or_load_smooth_by_angle_node_group()
    if node_group is not None:
        socket_id = _find_angle_socket_identifier(node_group)
        if socket_id is not None:
            modifier = obj.modifiers.new("PWG Smooth by Angle", "NODES")
            modifier.node_group = node_group
            try:
                modifier[socket_id] = angle_val
            except Exception:
                pass
            return modifier

    # Fallback when a valid 'Smooth by Angle' node group asset is missing or invalid
    print("Profile Wall Generator: 'Smooth by Angle' node group unavailable or invalid. Using mesh.set_sharp_from_angle fallback.")
    try:
        if hasattr(mesh, "set_sharp_from_angle"):
            mesh.set_sharp_from_angle(angle=angle_val)
        else:
            if mesh.polygons:
                mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
    except Exception as exc:
        print("Profile Wall Generator: Error in smooth fallback:", exc)
        if mesh.polygons:
            mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _warn_on_dropped_faces(mesh, expected_count, source_name, stage):
    """Report faces Blender refused, which desynchronises the per-face lists.

    ``face_uvs`` and ``face_material_keys`` are matched to faces by position,
    so a dropped face silently shifts every UV and material after it. Nothing
    here can recover the mapping, but a visible message beats a wall whose
    trim and body materials are scrambled for no apparent reason.
    """
    actual_count = len(mesh.polygons)
    if actual_count == expected_count:
        return True
    print(
        f"Profile Wall Generator: {stage} dropped "
        f"{expected_count - actual_count} of {expected_count} faces while "
        f"building the wall for '{source_name}'. UVs and materials may be "
        "misaligned; check the source path for self-intersections, duplicate "
        "points or zero-length segments."
    )
    return False


def _compute_profile_v_coords(profile, height_scale, offset_scale, use_profile_offset=True):
    """Compute arc-length V coordinates along the vertical profile."""
    if not profile:
        return []

    base_v = profile[0][0] * height_scale
    v_coords = [base_v]
    current_v = base_v
    effective_offset_scale = offset_scale if use_profile_offset else 0.0

    for i in range(len(profile) - 1):
        z0, off0, _ = profile[i]
        z1, off1, _ = profile[i + 1]
        dz = (z1 - z0) * height_scale
        doff = (off1 - off0) * effective_offset_scale
        seg_len = (dz * dz + doff * doff) ** 0.5
        current_v += seg_len
        v_coords.append(current_v)

    return v_coords


def _adjust_profile_trims(profile, bottom_scale, top_scale):
    z_body_start = None
    z_body_end = None
    z_max = profile[-1][0]
    z_min = profile[0][0]
    
    for z, offset, mat in profile:
        if mat == "body":
            if z_body_start is None:
                z_body_start = z
            z_body_end = z
            
    if z_body_start is None or z_body_end is None:
        return profile
        
    trim_bottom_h = z_body_start - z_min
    trim_top_h = z_max - z_body_end
    body_h = z_body_end - z_body_start
    
    new_trim_bottom_h = trim_bottom_h * bottom_scale
    new_trim_top_h = trim_top_h * top_scale
    new_body_h = z_max - z_min - new_trim_bottom_h - new_trim_top_h
    
    if new_body_h <= 0.001:
        total_trim = new_trim_bottom_h + new_trim_top_h
        avail_trim = z_max - z_min - 0.001
        if total_trim > 0:
            factor = avail_trim / total_trim
            new_trim_bottom_h *= factor
            new_trim_top_h *= factor
        new_body_h = 0.001
        
    new_profile = []
    for z, offset, mat in profile:
        if z <= z_body_start:
            f = (z - z_min) / trim_bottom_h if trim_bottom_h > 0 else 0
            new_z = z_min + f * new_trim_bottom_h
        elif z >= z_body_end:
            f = (z - z_body_end) / trim_top_h if trim_top_h > 0 else 0
            new_z = z_min + new_trim_bottom_h + new_body_h + f * new_trim_top_h
        else:
            f = (z - z_body_start) / body_h if body_h > 0 else 0
            new_z = z_min + new_trim_bottom_h + f * new_body_h
            
        new_profile.append((new_z, offset, mat))
        
    return new_profile


def _profile_offset_at_height(profile, target_height):
    if target_height <= profile[0][0]:
        return profile[0][1]
    if target_height >= profile[-1][0]:
        return profile[-1][1]

    for index in range(len(profile) - 1):
        lower_z, lower_offset, _lower_material = profile[index]
        upper_z, upper_offset, _upper_material = profile[index + 1]
        if lower_z <= target_height <= upper_z:
            span = upper_z - lower_z
            if span <= 1e-8:
                return upper_offset
            factor = (target_height - lower_z) / span
            return lower_offset + (upper_offset - lower_offset) * factor
    return profile[-1][1]


def _effective_top_trim_height(props, profile):
    """Return the generated side Top Trim height in object-space units."""
    adjusted_profile = _adjust_profile_trims(
        profile,
        max(0.0, float(getattr(props, "bottom_trim_scale", 1.0))),
        max(0.0, float(getattr(props, "top_trim_scale", 1.0))),
    )
    body_heights = [z for z, _offset, material in adjusted_profile if material == "body"]
    if not body_heights:
        return 0.0

    profile_top = max(z for z, _offset, _material in adjusted_profile)
    body_top = max(body_heights)
    return max(0.0, (profile_top - body_top) * abs(props.height_scale))


def _top_trim_border_fraction(props, profile, top_cross_widths):
    """Fit the side Trim height into a thin two-sided top strip.

    Each top strip needs two border bands. A literal one-to-one width can be
    wider than the complete wall thickness, so the physical target width is
    smoothly compressed toward half of the strip instead of being abruptly
    clipped. This keeps a small Top-material center and remains responsive to
    Top Trim Scale.
    """
    desired_width = _effective_top_trim_height(props, profile)
    positive_widths = [width for width in top_cross_widths if width > 1e-8]
    if desired_width <= 0.0 or not positive_widths:
        return 0.0

    reference_width = sum(positive_widths) / len(positive_widths)
    return TOP_TRIM_BORDER_MAX_FRACTION * (
        1.0 - exp(-desired_width / (TOP_TRIM_BORDER_MAX_FRACTION * reference_width))
    )


def _solid_top_trim_border_width(props, profile, top_points):
    desired_width = _effective_top_trim_height(props, profile)
    if desired_width <= 0.0 or len(top_points) < 3:
        return 0.0

    spans = []
    for index, point in enumerate(top_points):
        edge = top_points[(index + 1) % len(top_points)] - point
        edge_2d = Vector((edge.x, edge.y))
        if edge_2d.length <= 1e-8:
            continue
        edge_2d.normalize()
        normal = Vector((-edge_2d.y, edge_2d.x))
        projections = [candidate.x * normal.x + candidate.y * normal.y for candidate in top_points]
        span = max(projections) - min(projections)
        if span > 1e-8:
            spans.append(span)
    if not spans:
        return 0.0

    # Solid fills have only one outer border, so they can use the same physical
    # width as the vertical Top Trim. Limit it only when the whole polygon is
    # too narrow to leave a valid Top center.
    return min(desired_width, min(spans) * 0.45)


def _inset_closed_loop(points, width, miter_limit):
    if width <= 0.0:
        return None
    outward_normals, miter_factors = path_utils.compute_normals(
        points,
        closed=True,
        flip=False,
    )
    inset = []
    for point, normal, miter_factor in zip(points, outward_normals, miter_factors):
        co = point - normal * (width * min(miter_factor, miter_limit))
        co.z = point.z
        inset.append(co)

    outer_area = path_utils.signed_area_xy(points)
    inset_area = path_utils.signed_area_xy(inset)
    if (
        abs(inset_area) <= 1e-8
        or outer_area * inset_area <= 0.0
        or abs(inset_area) >= abs(outer_area)
    ):
        return None
    return inset


def _material_keys_for_profile_segments(profile):
    keys = []
    for index in range(len(profile) - 1):
        lower_key = profile[index][2]
        upper_key = profile[index + 1][2]
        if lower_key == "trim" or upper_key == "trim":
            keys.append("trim")
        elif lower_key == upper_key:
            keys.append(lower_key)
        else:
            keys.append(lower_key)
    return keys


def _cap_uvs(face, vertex_meta):
    return [
        (vertex_meta[index]["offset"], vertex_meta[index]["v"])
        for index in face
    ]


def _face_points_away_from_expected(face, vertices, expected_normal):
    if expected_normal.length == 0.0:
        return False
    expected = expected_normal.normalized()
    p0 = Vector(vertices[face[0]])
    p1 = Vector(vertices[face[1]])
    p2 = Vector(vertices[face[2]])
    normal = (p1 - p0).cross(p2 - p1)
    if normal.length == 0.0:
        return False
    return normal.normalized().dot(expected) < 0.0
