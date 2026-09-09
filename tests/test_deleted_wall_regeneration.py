import sys
from pathlib import Path

import bpy


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def make_source_curve():
    curve_data = bpy.data.curves.new("DeletedWallSourceData", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (2.0, 0.0, 0.0, 1.0)
    source = bpy.data.objects.new("DeletedWallSource", curve_data)
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
        props = bpy.context.scene.profile_wall_props
        props.hide_source_curve = True
        source = make_source_curve()
        select_only(source)

        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        old_wall = bpy.context.active_object
        assert old_wall.get("profile_wall_generated")

        # Reproduce an Outliner deletion state where the object datablock still
        # exists but is no longer linked to the scene/view layer.
        for collection in list(old_wall.users_collection):
            collection.objects.unlink(old_wall)
        bpy.context.view_layer.update()
        assert old_wall.name not in bpy.context.view_layer.objects
        assert bpy.data.objects.get(old_wall.name) == old_wall

        select_only(source)
        assert addon.operators.get_linked_wall(source) is None

        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        new_wall = bpy.context.active_object
        assert new_wall != old_wall
        assert new_wall.name in bpy.context.view_layer.objects
        assert addon.operators.get_linked_wall(source) == new_wall

        print("PWG_DELETED_WALL_REGENERATION_OK")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
