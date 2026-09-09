import sys
from pathlib import Path

import bpy


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def make_source_curve(name, y=0.0):
    curve_data = bpy.data.curves.new(name + "Data", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, y, 0.0, 1.0)
    spline.points[1].co = (2.0, y, 0.0, 1.0)
    source = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(source)
    return source


def select_only(obj):
    for selected in list(bpy.context.selected_objects):
        selected.select_set(False)
    obj.hide_viewport = False
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def max_coordinate(obj, axis):
    return max(vertex.co[axis] for vertex in obj.data.vertices)


class _ObjectUpdate:
    def __init__(self, obj):
        self.id = obj


class _DepsgraphUpdates:
    def __init__(self, *objects):
        self.updates = [_ObjectUpdate(obj) for obj in objects]


def main():
    addon.register()
    try:
        scene = bpy.context.scene

        # Existing linked sources receive the former Scene-wide values once.
        legacy_source = make_source_curve("LegacySource", -4.0)
        legacy_wall = bpy.data.objects.new(
            "LegacyWall", bpy.data.meshes.new("LegacyWallMesh")
        )
        bpy.context.collection.objects.link(legacy_wall)
        legacy_wall["profile_wall_generated"] = True
        legacy_source["profile_wall_result"] = legacy_wall.name
        legacy_source.pwg_result_ref = legacy_wall
        scene.profile_wall_props.height_scale = 1.75
        addon.unregister()
        addon.register()
        scene = bpy.context.scene
        assert legacy_source.pwg_settings_initialized
        assert legacy_source.pwg_settings.height_scale == 1.75

        source_a = make_source_curve("WallSourceA", 0.0)
        source_b = make_source_curve("WallSourceB", 4.0)
        top_a = bpy.data.materials.new("Top_A")
        top_b = bpy.data.materials.new("Top_B")
        section_a = bpy.data.materials.new("Section_A")
        section_b = bpy.data.materials.new("Section_B")

        source_a.pwg_settings.height_scale = 1.0
        source_a.pwg_settings.wall_thickness = 0.1
        source_a.pwg_settings.top_material = top_a
        source_a.pwg_settings.section_material = section_a
        source_a.pwg_settings.hide_source_curve = False

        source_b.pwg_settings.height_scale = 2.0
        source_b.pwg_settings.wall_thickness = 0.35
        source_b.pwg_settings.top_material = top_b
        source_b.pwg_settings.section_material = section_b
        source_b.pwg_settings.hide_source_curve = False

        select_only(source_a)
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall_a = bpy.context.active_object

        select_only(source_b)
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall_b = bpy.context.active_object

        assert source_a.pwg_settings_initialized
        assert source_b.pwg_settings_initialized
        assert abs(max_coordinate(wall_a, 2) - 3.0) < 1e-6
        assert abs(max_coordinate(wall_b, 2) - 6.0) < 1e-6
        assert wall_a.data.materials[2] == top_a
        assert wall_b.data.materials[2] == top_b
        assert wall_a.data.materials[3] == section_a
        assert wall_b.data.materials[3] == section_b
        assert source_a.pwg_settings.top_material == top_a
        assert source_b.pwg_settings.top_material == top_b
        assert source_a.pwg_settings.section_material == section_a
        assert source_b.pwg_settings.section_material == section_b
        assert source_a.pwg_settings.body_material.name == "PWG_Body"
        assert source_a.pwg_settings.trim_material.name == "PWG_Trim"

        select_only(wall_a)
        active_props = addon.operators.props_for(bpy.context)
        assert active_props.as_pointer() == source_a.pwg_settings.as_pointer()

        # Updating A must not read or overwrite B's settings.
        source_a.pwg_settings.height_scale = 1.5
        assert bpy.ops.profile_wall.update() == {"FINISHED"}
        assert abs(max_coordinate(wall_a, 2) - 4.5) < 1e-6
        assert abs(max_coordinate(wall_b, 2) - 6.0) < 1e-6

        # Auto Update is evaluated independently for each source.
        source_a.pwg_settings.auto_update = True
        source_b.pwg_settings.auto_update = False
        source_a.pwg_settings.body_material = None
        assert source_a.pwg_settings.body_material.name == "PWG_Body"
        select_only(wall_a)
        assert bpy.ops.profile_wall.edit_source_curve() == {"FINISHED"}
        assert bpy.context.active_object == source_a
        assert bpy.context.mode == "EDIT_CURVE"
        assert not wall_a.hide_get()
        source_a.pwg_settings.height_scale = 1.25
        assert abs(max_coordinate(wall_a, 2) - 3.75) < 1e-6
        source_a.data.splines[0].points[1].co.x = 3.0
        source_b.data.splines[0].points[1].co.x = 4.0
        source_a.data.update_tag()
        source_b.data.update_tag()
        bpy.context.view_layer.update()
        addon.flush_pending_updates()
        assert abs(max_coordinate(wall_a, 0) - 3.0) < 1e-6
        assert abs(max_coordinate(wall_b, 0) - 2.0) < 1e-6

        # Also cover Blender updates that contain only the Curve datablock ID.
        source_a.data.splines[0].points[1].co.x = 3.5
        source_b.data.splines[0].points[1].co.x = 4.5
        addon.profile_wall_auto_update(
            scene, _DepsgraphUpdates(source_a.data, source_b.data)
        )
        addon.flush_pending_updates()
        assert abs(max_coordinate(wall_a, 0) - 3.5) < 1e-6
        assert abs(max_coordinate(wall_b, 0) - 2.0) < 1e-6

        print("PWG_PER_SOURCE_SETTINGS_OK")
    finally:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()


if __name__ == "__main__":
    main()
