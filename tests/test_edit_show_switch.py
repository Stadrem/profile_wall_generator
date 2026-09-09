import sys
from pathlib import Path

import bpy


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def make_source(name):
    data = bpy.data.curves.new(name + "Data", "CURVE")
    data.dimensions = "3D"
    spline = data.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (2.0, 0.0, 0.0, 1.0)
    source = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(source)
    return source


def select_only(obj):
    for selected in list(bpy.context.selected_objects):
        selected.select_set(False)
    obj.hide_viewport = False
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def max_x(wall):
    return max(vertex.co.x for vertex in wall.data.vertices)


def assert_wall_active_and_source_deselected(source, wall):
    assert bpy.context.mode == "OBJECT"
    assert source.mode == "OBJECT"
    assert wall.mode == "OBJECT"
    assert bpy.context.active_object == wall
    assert wall.select_get()
    assert not source.select_get()
    assert set(bpy.context.selected_objects) == {wall}


def main():
    addon.register()
    try:
        source = make_source("EditShowSwitchSource")
        props = source.pwg_settings
        select_only(source)
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = addon.operators.get_linked_wall(source)
        assert wall is not None

        # Exercise all combinations while repeatedly crossing the Edit/Object
        # boundary.  Auto Update uses the real depsgraph handler and debounce
        # queue; the test does not inject an internal pending-update entry.
        for index, (auto_update, hide_source) in enumerate(
            ((False, False), (False, True), (True, False), (True, True)),
            start=1,
        ):
            props.auto_update = auto_update
            props.hide_source_curve = hide_source
            old_max_x = max_x(wall)
            select_only(wall)
            assert bpy.ops.profile_wall.edit_source_curve() == {"FINISHED"}
            assert bpy.context.mode == "EDIT_CURVE"
            assert source.mode == "EDIT"

            for point in source.data.splines[0].points:
                point.select = False
            source.data.splines[0].points[1].select = True
            delta = 0.5 * index
            bpy.ops.transform.translate(value=(delta, 0.0, 0.0))
            bpy.context.view_layer.update()

            assert bpy.ops.profile_wall.show_generated_mesh() == {"FINISHED"}
            assert_wall_active_and_source_deselected(source, wall)
            assert source.hide_get() is hide_source
            if auto_update:
                assert max_x(wall) > old_max_x
            else:
                assert max_x(wall) == old_max_x

        print("PWG_EDIT_SHOW_SWITCH_OK")
    finally:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()


if __name__ == "__main__":
    main()
