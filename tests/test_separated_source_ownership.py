import sys
from pathlib import Path

import bpy


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def make_source_curve(name):
    curve_data = bpy.data.curves.new(name + "Data", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (2.0, 0.0, 0.0, 1.0)
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


def main():
    addon.register()
    try:
        source = make_source_curve("OwnershipSource")
        source.pwg_settings.auto_update = True
        source.pwg_settings.hide_source_curve = False
        select_only(source)
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = bpy.context.active_object
        assert addon.operators.get_linked_source(wall) == source

        # Match the important result of Curve Separate: a later object carries
        # copied settings and both forms of the original result link.
        separated = source.copy()
        separated.data = source.data.copy()
        separated.name = "OwnershipSource-2"
        bpy.context.collection.objects.link(separated)
        addon.properties.copy_settings(source.pwg_settings, separated.pwg_settings)
        separated["profile_wall_result"] = wall.name
        separated.pwg_result_ref = wall

        # Read-only link queries (including Panel.poll) must not mutate Blender
        # IDs, while the duplicate is still rejected as the wall owner.
        assert addon.operators.get_linked_wall(separated) is None
        assert separated.pwg_result_ref == wall
        assert separated["profile_wall_result"] == wall.name
        assert addon.operators.get_linked_wall(source) == wall
        assert addon.operators.get_linked_source(wall) == source
        select_only(separated)
        assert addon.panels.PROFILE_WALL_PT_materials.poll(bpy.context)
        assert addon.panels.PROFILE_WALL_PT_uv.poll(bpy.context)
        assert addon.panels.PROFILE_WALL_PT_advanced.poll(bpy.context)
        assert separated.pwg_result_ref == wall
        assert separated["profile_wall_result"] == wall.name

        # Also repair a file that was already stolen by the separated object in
        # an earlier version of the add-on.
        separated["profile_wall_result"] = wall.name
        separated.pwg_result_ref = wall
        wall["profile_wall_source"] = separated.name
        wall.pwg_source_ref = separated
        assert addon.operators.get_linked_source(wall) == source
        assert wall.pwg_source_ref == separated

        select_only(wall)
        assert bpy.ops.profile_wall.edit_source_curve() == {"FINISHED"}
        assert bpy.context.active_object == source
        assert bpy.context.mode == "EDIT_CURVE"
        assert wall.pwg_source_ref == source
        assert wall["profile_wall_source"] == source.name
        assert separated.pwg_result_ref is None
        assert "profile_wall_result" not in separated

        print("PWG_SEPARATED_SOURCE_OWNERSHIP_OK")
    finally:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()


if __name__ == "__main__":
    main()
