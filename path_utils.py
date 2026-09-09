from mathutils import Vector


class PathError(ValueError):
    pass


def _xy_distance(a, b):
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def remove_near_duplicates(points, merge_distance):
    if not points:
        return []

    cleaned = [points[0]]
    for point in points[1:]:
        if (point - cleaned[-1]).length > merge_distance:
            cleaned.append(point)

    if len(cleaned) > 2 and (cleaned[0] - cleaned[-1]).length <= merge_distance:
        cleaned.pop()
    return cleaned


def extract_path(obj, merge_distance=0.001):
    if obj is None:
        raise PathError("Select a curve or mesh line.")
    if obj.type == "CURVE":
        return extract_curve_path(obj, merge_distance)
    if obj.type == "MESH":
        return extract_mesh_path(obj, merge_distance)
    raise PathError("Selected object must be Curve or Mesh.")


def extract_paths(obj, merge_distance=0.001, resolution_mode="CUSTOM", custom_resolution=8):
    """Return every independent path stored in a supported source object."""
    if obj is None:
        raise PathError("Select a curve or mesh line.")
    if obj.type == "CURVE":
        return extract_curve_paths(
            obj,
            merge_distance=merge_distance,
            resolution_mode=resolution_mode,
            custom_resolution=custom_resolution,
        )
    if obj.type == "MESH":
        return [extract_mesh_path(obj, merge_distance)]
    raise PathError("Selected object must be Curve or Mesh.")


def extract_curve_path(obj, merge_distance=0.001, resolution_mode="CUSTOM", custom_resolution=8):
    return extract_curve_paths(
        obj,
        merge_distance=merge_distance,
        resolution_mode=resolution_mode,
        custom_resolution=custom_resolution,
    )[0]


def extract_curve_paths(obj, merge_distance=0.001, resolution_mode="CUSTOM", custom_resolution=8):
    curve = obj.data
    if not curve.splines:
        raise PathError("Curve has no splines.")

    paths = []
    for index, spline in enumerate(curve.splines):
        try:
            paths.append(
                _extract_curve_spline_path(
                    obj,
                    spline,
                    merge_distance,
                    resolution_mode=resolution_mode,
                    custom_resolution=custom_resolution,
                )
            )
        except PathError as exc:
            raise PathError(f"Spline {index + 1}: {exc}") from exc
    return paths


def _extract_curve_spline_path(obj, spline, merge_distance, resolution_mode="CUSTOM", custom_resolution=8):
    closed = bool(spline.use_cyclic_u)

    if spline.type == "POLY":
        points = [obj.matrix_world @ point.co.xyz for point in spline.points]
    elif spline.type == "BEZIER":
        if resolution_mode == "CURVE":
            samples = max(1, getattr(spline, "resolution_u", 12))
        else:
            samples = max(1, int(custom_resolution))
        points = _sample_bezier_spline(obj, spline, samples_per_segment=samples)
    else:
        raise PathError("Only Poly and Bezier curves are supported.")

    points = remove_near_duplicates(points, merge_distance)
    if len(points) < 2:
        raise PathError("Path needs at least two points.")
    return points, closed


def _sample_bezier_spline(obj, spline, samples_per_segment=8):
    bezier_points = spline.bezier_points
    if len(bezier_points) < 2:
        return [obj.matrix_world @ p.co for p in bezier_points]

    result = []
    count = len(bezier_points)
    segment_count = count if spline.use_cyclic_u else count - 1

    for index in range(segment_count):
        p0 = bezier_points[index]
        p1 = bezier_points[(index + 1) % count]
        for step in range(samples_per_segment + 1):
            if index > 0 and step == 0:
                continue
            if spline.use_cyclic_u and index == segment_count - 1 and step == samples_per_segment:
                continue
            t = step / float(samples_per_segment)
            co = _bezier_point(p0.co, p0.handle_right, p1.handle_left, p1.co, t)
            result.append(obj.matrix_world @ co)

    return result


def _bezier_point(p0, h0, h1, p1, t):
    inv = 1.0 - t
    return (
        (inv ** 3) * p0
        + 3.0 * (inv ** 2) * t * h0
        + 3.0 * inv * (t ** 2) * h1
        + (t ** 3) * p1
    )


def extract_mesh_path(obj, merge_distance=0.001):
    mesh = obj.data
    if len(mesh.edges) < 1:
        raise PathError("Mesh path needs at least one edge.")

    adjacency = {}
    for edge in mesh.edges:
        a, b = edge.vertices
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    endpoints = [index for index, linked in adjacency.items() if len(linked) == 1]
    closed = len(endpoints) == 0
    if closed:
        if any(len(linked) != 2 for linked in adjacency.values()):
            raise PathError("Mesh path must be one open chain or one closed loop.")
        start = next(iter(adjacency.keys()))
    elif len(endpoints) == 2:
        if any(len(linked) not in {1, 2} for linked in adjacency.values()):
            raise PathError("Mesh path must be one open chain or one closed loop.")
        start = endpoints[0]
    else:
        raise PathError("Mesh path must be one open chain or one closed loop.")

    ordered_indices = []
    previous = None
    current = start
    visited_edges = set()

    while current is not None:
        ordered_indices.append(current)
        next_vertex = None
        for candidate in adjacency[current]:
            key = tuple(sorted((current, candidate)))
            if key in visited_edges:
                continue
            if candidate == previous and len(adjacency[current]) > 1:
                continue
            next_vertex = candidate
            visited_edges.add(key)
            break
        previous, current = current, next_vertex
        if closed and current == start:
            break

    if len(visited_edges) != len(mesh.edges):
        raise PathError("Mesh path must be one connected open chain or closed loop.")

    points = [obj.matrix_world @ mesh.vertices[index].co for index in ordered_indices]
    points = remove_near_duplicates(points, merge_distance)
    if len(points) < 2:
        raise PathError("Path needs at least two points.")
    return points, closed


def signed_area_xy(points):
    area = 0.0
    count = len(points)
    for i, point in enumerate(points):
        other = points[(i + 1) % count]
        area += point.x * other.y - other.x * point.y
    return area * 0.5


def cumulative_lengths(points, closed=False):
    lengths = [0.0]
    total = 0.0
    limit = len(points) if closed else len(points) - 1
    for index in range(limit):
        a = points[index]
        b = points[(index + 1) % len(points)]
        total += _xy_distance(a, b)
        if index + 1 < len(points):
            lengths.append(total)
    return lengths


def compute_normals(points, closed=False, flip=False):
    count = len(points)
    if count < 2:
        raise PathError("Path needs at least two points.")

    area = signed_area_xy(points) if closed and count >= 3 else 0.0
    outward_sign = -1.0 if area > 0.0 else 1.0
    if not closed:
        outward_sign = 1.0
    if flip:
        outward_sign *= -1.0

    segment_normals = []
    segment_count = count if closed else count - 1
    for index in range(segment_count):
        a = points[index]
        b = points[(index + 1) % count]
        direction = Vector((b.x - a.x, b.y - a.y, 0.0))
        if direction.length == 0.0:
            normal = Vector((0.0, 1.0, 0.0))
        else:
            direction.normalize()
            normal = Vector((-direction.y, direction.x, 0.0)) * outward_sign
        segment_normals.append(normal)

    normals = []
    miter_factors = []
    for index in range(count):
        miter_factor = 1.0
        if not closed and index == 0:
            normal = segment_normals[0]
        elif not closed and index == count - 1:
            normal = segment_normals[-1]
        else:
            prev_normal = segment_normals[index - 1]
            next_normal = segment_normals[index % len(segment_normals)]
            normal = prev_normal + next_normal
            if normal.length == 0.0:
                normal = next_normal
            
            dot = prev_normal.dot(next_normal)
            dot = max(-0.999, min(1.0, dot))
            miter_factor = (2.0 / (1.0 + dot)) ** 0.5
            
        normal.normalize()
        normals.append(normal)
        miter_factors.append(miter_factor)
    return normals, miter_factors
