"""Run with Blender --background --factory-startup --python this_file.

Regression cover for source-input handling:
  * panel state for a source that holds no usable path
  * rejection of paths without horizontal extent, whole or per segment
  * end-point preservation on open paths
  * refusal to publish a mesh whose faces Blender rejected, leaving any
    existing wall untouched
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

    # A vertical run inside an otherwise horizontal path is equally unusable:
    # compute_normals has no direction there and emits inverted, zero-area
    # faces. The whole-path extent check alone does not see it.
    mid_vertical = make_poly_curve(
        "MidVertical", [(0, 0, 0), (4, 0, 0), (4, 0, 3), (8, 0, 3)], False
    )
    expect_path_error(
        "Segment 2 is vertical",
        lambda: path_utils.extract_paths(mid_vertical, 0.001),
    )

    lead_vertical = make_poly_curve(
        "LeadVertical", [(0, 0, 0), (0, 0, 2), (4, 0, 2)], False
    )
    expect_path_error(
        "Segment 1 is vertical",
        lambda: path_utils.extract_paths(lead_vertical, 0.001),
    )

    # A closed path must have its wrap-around segment checked too.
    closed_vertical = make_poly_curve(
        "ClosedVertical", [(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 0, 2)], True
    )
    expect_path_error(
        "Segment 4 is vertical",
        lambda: path_utils.extract_paths(closed_vertical, 0.001),
    )

    # A spline that only tilts out of plane stays valid.
    sloped = make_poly_curve("Sloped", [(0, 0, 0), (4, 0, 1), (8, 0, 2)], False)
    points, closed = path_utils.extract_paths(sloped, 0.001)[0]
    assert len(points) == 3 and not closed

    # A small but real horizontal step must not be mistaken for a vertical one.
    small_step = make_poly_curve(
        "SmallStep", [(0, 0, 0), (4, 0, 0), (4.0005, 0, 1), (8, 0, 1)], False
    )
    points, _closed = path_utils.extract_paths(small_step, 0.001)[0]
    assert len(points) == 4, len(points)
    print("PASS vertical paths and vertical segments rejected")

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

    # --- A mesh with rejected faces is never published ----------------------
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

    good_mesh = wall.data
    good_faces = len(good_mesh.polygons)
    good_name = good_mesh.name

    # The second face repeats a vertex, so mesh.validate() removes it. Anything
    # built from this geometry would carry UVs and materials shifted by one
    # face from that point on.
    bad_geometry = (
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        [(0, 1, 2, 3), (0, 1, 1, 2)],
        [[(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 0), (1, 0), (1, 1), (0, 1)]],
        ["body", "trim"],
    )

    mesh_count_before = len(bpy.data.meshes)
    expect_path_error(
        "Blender rejected",
        lambda: mesh_builder._create_wall_object(
            bpy.context, source, bad_geometry, props, existing_obj=wall
        ),
    )

    # The existing wall must survive the cancelled rebuild untouched...
    assert wall.data is good_mesh, "existing wall mesh was replaced"
    assert wall.data.name == good_name
    assert len(wall.data.polygons) == good_faces, len(wall.data.polygons)
    # ...and the rejected mesh must not be left behind in the file.
    assert len(bpy.data.meshes) == mesh_count_before, (
        "orphan mesh datablock leaked", mesh_count_before, len(bpy.data.meshes)
    )

    # The same guard applies to a first-time generation, which must not link a
    # half-built object into the scene.
    object_count_before = len(bpy.data.objects)
    expect_path_error(
        "Blender rejected",
        lambda: mesh_builder._create_wall_object(
            bpy.context, source, bad_geometry, props
        ),
    )
    assert len(bpy.data.objects) == object_count_before
    print("PASS rejected mesh is never published")

    print("ALL_INPUT_VALIDATION_TESTS_PASSED")
finally:
    addon.unregister()
