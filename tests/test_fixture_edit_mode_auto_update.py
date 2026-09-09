import sys
from pathlib import Path

import bpy
import bmesh


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


addon.register()
try:
    solid_source = bpy.data.objects["A1"]
    solid_wall = addon.operators.get_linked_wall(solid_source)
    assert solid_wall is not None
    solid_source.pwg_settings.fill_inside = True
    solid_source.pwg_settings.top_trim_scale = 2.3
    addon.operators.generate_wall_from_source(
        bpy.context,
        solid_source,
        solid_source.pwg_settings,
        existing_wall=solid_wall,
    )
    solid_upward_materials = {
        polygon.material_index
        for polygon in solid_wall.data.polygons
        if polygon.normal.z > 0.9
    }
    assert {1, 2}.issubset(solid_upward_materials)
    solid_bm = bmesh.new()
    solid_bm.from_mesh(solid_wall.data)
    try:
        assert all(edge.is_manifold for edge in solid_bm.edges)
    finally:
        solid_bm.free()

    # The same closed source can switch to a hollow wall with an interior
    # Section floor at Z +0.2 and its own material slot.
    solid_source.pwg_settings.fill_inside = False
    solid_source.pwg_settings.generate_section = True
    solid_source.pwg_settings.section_height = 0.2
    addon.operators.generate_wall_from_source(
        bpy.context,
        solid_source,
        solid_source.pwg_settings,
        existing_wall=solid_wall,
    )
    section_keys = solid_wall.get("_profile_wall_face_material_keys", "").split(",")
    section_faces = [
        polygon
        for polygon, key in zip(solid_wall.data.polygons, section_keys)
        if key == "section"
    ]
    assert section_faces
    assert all(polygon.material_index == 3 for polygon in section_faces)
    assert all(
        abs(solid_wall.data.vertices[index].co.z - 0.2) < 1e-6
        for polygon in section_faces
        for index in polygon.vertices
    )
    section_uv_layer = solid_wall.data.uv_layers.get("ProfileWallUV")
    assert section_uv_layer is not None
    section_uvs = [
        tuple(section_uv_layer.data[loop_index].uv)
        for polygon, key in zip(solid_wall.data.polygons, section_keys)
        if key == "section"
        for loop_index in polygon.loop_indices
    ]
    assert section_uvs
    assert abs(min(uv[0] for uv in section_uvs)) < 1e-5
    assert abs(min(uv[1] for uv in section_uvs)) < 1e-5
    assert max(uv[0] for uv in section_uvs) > 0.1
    assert max(uv[1] for uv in section_uvs) > 0.1

    source = bpy.data.objects["BézierCurve"]
    wall = addon.operators.get_linked_wall(source)
    assert wall is not None
    source.pwg_settings.auto_update = True
    source.pwg_settings.interior_mode = "HOLLOW"
    source.pwg_settings.top_trim_scale = 2.3
    wall.hide_set(False)
    addon.operators.generate_wall_from_source(
        bpy.context,
        source,
        source.pwg_settings,
        existing_wall=wall,
    )

    upward_materials = {
        polygon.material_index
        for polygon in wall.data.polygons
        if polygon.normal.z > 0.9
    }
    assert {1, 2}.issubset(upward_materials)
    bm = bmesh.new()
    bm.from_mesh(wall.data)
    try:
        assert all(edge.is_manifold for edge in bm.edges)
    finally:
        bm.free()

    before = [tuple(vertex.co) for vertex in wall.data.vertices]
    for selected in list(bpy.context.selected_objects):
        selected.select_set(False)
    wall.hide_set(False)
    wall.select_set(True)
    bpy.context.view_layer.objects.active = wall

    assert bpy.ops.profile_wall.edit_source_curve() == {"FINISHED"}
    assert bpy.context.active_object == source
    assert bpy.context.mode == "EDIT_CURVE"
    for spline in source.data.splines:
        if spline.type != "BEZIER":
            continue
        for point in spline.bezier_points:
            point.select_control_point = False
            point.select_left_handle = False
            point.select_right_handle = False
        spline.bezier_points[-1].select_control_point = True
    bpy.ops.transform.translate(value=(1.0, 0.0, 0.0))
    bpy.context.view_layer.update()
    addon.flush_pending_updates()

    after = [tuple(vertex.co) for vertex in wall.data.vertices]
    assert before != after
    assert bpy.context.mode == "EDIT_CURVE"

    print("PWG_FIXTURE_EDIT_MODE_AUTO_UPDATE_OK")
finally:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    addon.unregister()
