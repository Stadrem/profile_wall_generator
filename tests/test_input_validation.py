"""Run with Blender --background --factory-startup --python this_file.

Regression cover for source-input handling:
  * panel state for a source that holds no usable path
  * rejection of paths without horizontal extent
  * end-point preservation on open paths
  * detection of faces dropped while building the mesh
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import profile_wall_generator as addon
from profile_wall_generator import mesh_builder, panels, path_utils


def make_poly_curve(name, coords, cyclic):
    curve = bpy.data.curves.new(name, "CURVE")
    spline = curve.splines.new("POLY")
    spline.points.add(len(coords) - 1)
    for index, (x, y, z) in enumerate(coords):
        spline.points[index].co = (x, y, z, 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    return obj


def make_mesh(name, coords, edges):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(coords, edges, [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def expect_path_error(fragment, call):
    try:
        call()
    except path_utils.PathError as exc:
        assert fragment in str(exc), (fragment, str(exc))
        return
    raise AssertionError("expected PathError containing " + repr(fragment))


addon.register()
try:
    # --- A source without edges must not break the panel -------------------
    loose = make_mesh("LooseVerts", [(0, 0, 0), (1, 0, 0)], [])
    closed_flag, open_flag = panels._source_path_kinds(loose)
    assert (closed_flag, open_flag) == (False, False), (closed_flag, open_flag)

    empty_mesh = make_mesh("EmptyMesh", [], [])
    assert panels._source_path_kinds(empty_mesh) == (False, False)
    assert panels._source_path_kinds(None) == (False, False)

    # The real cases must keep reporting the right kind of path.
    assert panels._source_path_kinds(
        make_poly_curve("OpenCurve", [(0, 0, 0), (4, 0, 0)], False)
    ) == (False, True)
    assert panels._source_path_kinds(
        make_poly_curve("ClosedCurve", [(0, 0, 0), (4, 0, 0), (4, 4, 0)], True)
    ) == (True, False)
    assert panels._source_path_kinds(
        make_mesh("MeshLoop", [(0, 0, 0), (4, 0, 0), (4, 4, 0)],
                  [(0, 1), (1, 2), (2, 0)])
    ) == (True, False)

    # The panel reads the state of whatever is active, including the loose
    # source above; unpacking it must not raise.
    bpy.context.view_layer.objects.active = loose
    state = panels._panel_state(bpy.context)
    assert state["props"] is not None
    assert panels._source_path_kinds(state["settings_source"]) == (False, False)
    print("PASS panel state for sources without paths")

    # --- Paths without horizontal extent are rejected ----------------------
    vertical = make_poly_curve("Vertical", [(0, 0, 0), (0, 0, 3)], False)
    expect_path_error(
        "horizontal extent",
        lambda: path_utils.extract_paths(vertical, 0.001),
    )

    vertical_mesh = make_mesh(
        "VerticalMesh", [(2, 2, 0), (2, 2, 1), (2, 2, 2)], [(0, 1), (1, 2)]
    )
    expect_path_error(
        "horizontal extent",
        lambda: path_utils.extract_paths(vertical_mesh, 0.001),
    )

    # A spline that only tilts out of plane stays valid.
    sloped = make_poly_curve("Sloped", [(0, 0, 0), (4, 0, 1), (8, 0, 2)], False)
    points, closed = path_utils.extract_paths(sloped, 0.001)[0]
    assert len(points) == 3 and not closed
    print("PASS vertical paths rejected, sloped paths accepted")

    # --- Open paths keep both end points -----------------------------------
    ring_coords = [(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 0, 0)]

    open_ring = make_poly_curve("OpenRing", ring_coords, False)
    points, closed = path_utils.extract_paths(open_ring, 0.001)[0]
    assert not closed
    assert len(points) == 4, len(points)
    assert (points[0] - points[-1]).length < 1e-6, "coincident end point lost"

    closed_ring = make_poly_curve("ClosedRing", ring_coords, True)
    points, closed = path_utils.extract_paths(closed_ring, 0.001)[0]
    assert closed
    assert len(points) == 3, len(points)

    # Genuine consecutive duplicates are still merged on an open path.
    dupes = make_poly_curve(
        "Dupes", [(0, 0, 0), (4, 0, 0), (4, 0, 0), (4, 4, 0)], False
    )
    points, _closed = path_utils.extract_paths(dupes, 0.001)[0]
    assert len(points) == 3, len(points)
    print("PASS open path end points preserved")

    # --- Dropped faces are detected ----------------------------------------
    source = make_poly_curve(
        "Wall", [(0, 0, 0), (6, 0, 0), (6, 4, 0), (0, 4, 0)], True
    )
    props = source.pwg_settings
    props.auto_update = False
    paths = path_utils.extract_paths(source, props.merge_distance)
    wall, keys = mesh_builder.build_profile_wall_paths_object(
        bpy.context, source, paths, props
    )
    assert len(keys) == len(wall.data.polygons), (len(keys), len(wall.data.polygons))
    assert mesh_builder._warn_on_dropped_faces(
        wall.data, len(wall.data.polygons), source.name, "test"
    )
    assert not mesh_builder._warn_on_dropped_faces(
        wall.data, len(wall.data.polygons) + 1, source.name, "test"
    )
    print("PASS dropped-face detection")

    print("ALL_INPUT_VALIDATION_TESTS_PASSED")
finally:
    addon.unregister()
