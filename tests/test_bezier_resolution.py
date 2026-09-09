import sys
from pathlib import Path

import bpy

ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def make_bezier_curve(name, resolution_u=16):
    curve_data = bpy.data.curves.new(name + "Data", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("BEZIER")
    spline.resolution_u = resolution_u
    spline.bezier_points.add(1)

    p0 = spline.bezier_points[0]
    p0.co = (0.0, 0.0, 0.0)
    p0.handle_right = (1.0, 0.0, 0.0)
    p0.handle_left = (-1.0, 0.0, 0.0)

    p1 = spline.bezier_points[1]
    p1.co = (3.0, 3.0, 0.0)
    p1.handle_left = (2.0, 3.0, 0.0)
    p1.handle_right = (4.0, 3.0, 0.0)

    source = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(source)
    return source


def select_only(obj):
    for selected in list(bpy.context.selected_objects):
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def main():
    addon.register()
    try:
        source = make_bezier_curve("BezierResSource", resolution_u=16)
        select_only(source)

        # 1. Default mode is CUSTOM with resolution 8 (8 samples per segment = 9 path points)
        props = source.pwg_settings
        assert props.bezier_resolution_mode == "CUSTOM"
        assert props.bezier_resolution == 8

        paths_8 = addon.path_utils.extract_paths(
            source,
            props.merge_distance,
            resolution_mode=props.bezier_resolution_mode,
            custom_resolution=props.bezier_resolution,
        )
        assert len(paths_8[0][0]) == 9

        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = addon.operators.get_linked_wall(source)
        assert wall is not None
        vert_count_8 = len(wall.data.vertices)

        # 2. Change CUSTOM resolution to 4 (4 samples per segment = 5 path points)
        props.bezier_resolution = 4
        paths_4 = addon.path_utils.extract_paths(
            source,
            props.merge_distance,
            resolution_mode=props.bezier_resolution_mode,
            custom_resolution=props.bezier_resolution,
        )
        assert len(paths_4[0][0]) == 5

        assert bpy.ops.profile_wall.update() == {"FINISHED"}
        vert_count_4 = len(wall.data.vertices)
        assert vert_count_4 < vert_count_8

        # 3. Switch to CURVE mode (reads spline.resolution_u = 16 -> 17 path points)
        props.bezier_resolution_mode = "CURVE"
        paths_curve = addon.path_utils.extract_paths(
            source,
            props.merge_distance,
            resolution_mode=props.bezier_resolution_mode,
            custom_resolution=props.bezier_resolution,
        )
        assert len(paths_curve[0][0]) == 17

        assert bpy.ops.profile_wall.update() == {"FINISHED"}
        vert_count_curve = len(wall.data.vertices)
        assert vert_count_curve > vert_count_8

        # 4. Modify spline.resolution_u on curve directly and verify extraction
        source.data.splines[0].resolution_u = 24
        paths_curve_24 = addon.path_utils.extract_paths(
            source,
            props.merge_distance,
            resolution_mode=props.bezier_resolution_mode,
            custom_resolution=props.bezier_resolution,
        )
        assert len(paths_curve_24[0][0]) == 25

        assert bpy.ops.profile_wall.update() == {"FINISHED"}
        vert_count_curve_24 = len(wall.data.vertices)
        assert vert_count_curve_24 > vert_count_curve

        print("PWG_BEZIER_RESOLUTION_OK")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
