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
        source = make_line_curve("BevelSmoothSource")
        props = source.pwg_settings
        select_only(source)

        # 1. Default: Flat shading, No Bevel
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = addon.operators.get_linked_wall(source)
        assert wall is not None
        assert not any(poly.use_smooth for poly in wall.data.polygons)
        assert "PWG Edge Bevel" not in wall.modifiers
        assert "PWG Smooth by Angle" not in wall.modifiers

        # 2. Enable Bevel with segments = 1
        props.add_bevel = True
        props.bevel_width = 0.02
        props.bevel_segments = 1
        assert bpy.ops.profile_wall.update() == {"FINISHED"}

        bevel_mod = wall.modifiers.get("PWG Edge Bevel")
        assert bevel_mod is not None
        assert bevel_mod.type == "BEVEL"
        assert abs(bevel_mod.width - 0.02) < 1e-4
        assert bevel_mod.segments == 1

        # 3. Change Bevel Segments to 4
        props.bevel_segments = 4
        assert bpy.ops.profile_wall.update() == {"FINISHED"}
        bevel_mod = wall.modifiers.get("PWG Edge Bevel")
        assert bevel_mod is not None
        assert bevel_mod.segments == 4

        # 4. Enable Shade Smooth with Smooth by Angle and verify modifier order
        props.shade_smooth = True
        props.smooth_angle = 0.785398  # 45 degrees
        assert bpy.ops.profile_wall.update() == {"FINISHED"}

        assert all(poly.use_smooth for poly in wall.data.polygons)
        assert len(wall.modifiers) == 2
        assert wall.modifiers[0].name == "PWG Edge Bevel"
        assert wall.modifiers[1].name == "PWG Smooth by Angle"

        smooth_mod = wall.modifiers.get("PWG Smooth by Angle")
        assert smooth_mod is not None
        assert smooth_mod.type == "NODES"
        socket_id = addon.mesh_builder._find_angle_socket_identifier(smooth_mod.node_group)
        assert abs(smooth_mod[socket_id] - 0.785398) < 1e-4

        # 5. Fallback test: When Smooth by Angle node group asset is missing
        original_loader = addon.mesh_builder._get_or_load_smooth_by_angle_node_group
        addon.mesh_builder._get_or_load_smooth_by_angle_node_group = lambda: None
        try:
            assert bpy.ops.profile_wall.update() == {"FINISHED"}
            # Modifier should not exist because asset is missing
            assert "PWG Smooth by Angle" not in wall.modifiers
            # But polygons remain smooth and sharp edges are marked by set_sharp_from_angle fallback
            assert all(poly.use_smooth for poly in wall.data.polygons)
            # Sharp edges should be marked on sharp corners
            assert any(edge.use_edge_sharp for edge in wall.data.edges)
        finally:
            addon.mesh_builder._get_or_load_smooth_by_angle_node_group = original_loader

        # 6. Collision test: Empty or invalid same-named user node group
        # 6a. Dummy with Bool Angle socket instead of Float
        dummy_bool_ng = bpy.data.node_groups.new("FakeBoolSmooth", "GeometryNodeTree")
        dummy_bool_ng.interface.new_socket("Mesh", in_out="INPUT", socket_type="NodeSocketGeometry")
        dummy_bool_ng.interface.new_socket("Mesh", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        dummy_bool_ng.interface.new_socket("Angle", in_out="INPUT", socket_type="NodeSocketBool")
        try:
            assert not addon.mesh_builder._is_valid_smooth_by_angle_node_group(dummy_bool_ng)
            assert addon.mesh_builder._find_angle_socket_identifier(dummy_bool_ng) is None
        finally:
            bpy.data.node_groups.remove(dummy_bool_ng)

        # 6b. Dummy empty geometry node group that occupies the exact name 'Smooth by Angle'
        # Remove all existing Smooth by Angle node groups first
        for ng in list(bpy.data.node_groups):
            if ng.name.startswith("Smooth by Angle"):
                bpy.data.node_groups.remove(ng)

        dummy_exact_name_ng = bpy.data.node_groups.new("Smooth by Angle", "GeometryNodeTree")
        try:
            assert dummy_exact_name_ng.name == "Smooth by Angle"
            assert not addon.mesh_builder._is_valid_smooth_by_angle_node_group(dummy_exact_name_ng)
            assert addon.mesh_builder._find_angle_socket_identifier(dummy_exact_name_ng) is None

            # Generating/updating the wall must NOT attach the broken dummy node group
            assert bpy.ops.profile_wall.update() == {"FINISHED"}
            smooth_mod = wall.modifiers.get("PWG Smooth by Angle")
            if smooth_mod is not None:
                assert smooth_mod.node_group != dummy_exact_name_ng
                assert addon.mesh_builder._is_valid_smooth_by_angle_node_group(smooth_mod.node_group)
        finally:
            if dummy_exact_name_ng.name in bpy.data.node_groups:
                bpy.data.node_groups.remove(dummy_exact_name_ng)

        # 7. Disable Bevel and Shade Smooth: Modifiers removed, polygons flat
        props.add_bevel = False
        props.shade_smooth = False
        assert bpy.ops.profile_wall.update() == {"FINISHED"}

        assert not any(poly.use_smooth for poly in wall.data.polygons)
        assert "PWG Edge Bevel" not in wall.modifiers
        assert "PWG Smooth by Angle" not in wall.modifiers
        assert not any(edge.use_edge_sharp for edge in wall.data.edges)

        print("PWG_BEVEL_AND_SMOOTH_OK")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
