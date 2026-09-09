import sys
from pathlib import Path

import bpy

ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def make_line_curve(name):
    curve_data = bpy.data.curves.new(name + "Data", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (4.0, 0.0, 0.0, 1.0)

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
        source = make_line_curve("ArcLengthUVSource")
        props = source.pwg_settings
        props.profile_preset = "BASIC_MOLDING"
        props.height_scale = 1.0
        props.offset_scale = 1.0
        props.bottom_trim_scale = 1.0
        props.top_trim_scale = 1.0
        props.wall_thickness = 0.5
        props.flat_inner_face = True
        select_only(source)

        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = addon.operators.get_linked_wall(source)
        assert wall is not None

        # Calculate expected arc-length for BASIC_MOLDING
        # (0.00, 0.08), (0.20, 0.08), (0.30, 0.00), (2.70, 0.00), (2.80, 0.08), (3.00, 0.08)
        expected_front_arc_len = (
            0.20
            + (0.10**2 + 0.08**2) ** 0.5
            + 2.40
            + (0.10**2 + 0.08**2) ** 0.5
            + 0.20
        )
        expected_back_flat_len = 3.00

        uv_layer = wall.data.uv_layers.get("ProfileWallUV")
        assert uv_layer is not None

        # Inspect front and back face UV coordinates
        # Basic Molding has 5 vertical face segments along the front and 5 along the back.
        # Front faces have normal.y > 0 (pointing outward along +Y for a line along +X), back has normal.y < 0
        front_v_coords = []
        back_v_coords = []
        for poly in wall.data.polygons:
            if abs(poly.normal.z) > 0.5 or abs(poly.normal.x) > 0.5:
                continue  # ignore top/bottom/caps
            for loop_idx in poly.loop_indices:
                uv = uv_layer.data[loop_idx].uv
                if poly.normal.y > 0.5:
                    front_v_coords.append(uv[1])
                elif poly.normal.y < -0.5:
                    back_v_coords.append(uv[1])

        assert front_v_coords and back_v_coords

        max_front_v = max(front_v_coords)
        max_back_v = max(back_v_coords)

        # 1. Front V should match arc length (approx 3.0561 > 3.00)
        assert abs(max_front_v - expected_front_arc_len) < 1e-4, f"Front V {max_front_v} != {expected_front_arc_len}"

        # 2. Back V (Flat Inner Face) should match pure vertical height (3.00)
        assert abs(max_back_v - expected_back_flat_len) < 1e-4, f"Back V {max_back_v} != {expected_back_flat_len}"

        # 3. Disable Flat Inner Face: Back V should now also match arc length
        props.flat_inner_face = False
        assert bpy.ops.profile_wall.update() == {"FINISHED"}

        uv_layer = wall.data.uv_layers.get("ProfileWallUV")
        back_v_coords_molded = [
            uv_layer.data[loop_idx].uv[1]
            for poly in wall.data.polygons
            if poly.normal.y < -0.5
            for loop_idx in poly.loop_indices
        ]
        assert abs(max(back_v_coords_molded) - expected_front_arc_len) < 1e-4

        # 4. Set Offset Scale = 0: Both front and back should equal 3.00
        props.offset_scale = 0.0
        assert bpy.ops.profile_wall.update() == {"FINISHED"}

        uv_layer = wall.data.uv_layers.get("ProfileWallUV")
        all_wall_v = [
            uv_layer.data[loop_idx].uv[1]
            for poly in wall.data.polygons
            if abs(poly.normal.y) > 0.5
            for loop_idx in poly.loop_indices
        ]
        assert abs(max(all_wall_v) - 3.00) < 1e-4

        print("PWG_ARC_LENGTH_UV_OK")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
