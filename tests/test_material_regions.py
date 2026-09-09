import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def assert_material_regions(obj, face_keys):
    slot_names = [slot.name for slot in obj.data.materials]
    assert slot_names == ["PWG_Body", "PWG_Trim", "PWG_Top", "PWG_Section"], slot_names
    assert "cap" not in face_keys

    top_faces = []
    end_faces = []
    for polygon, key in zip(obj.data.polygons, face_keys):
        if polygon.normal.z > 0.9:
            top_faces.append((polygon, key))
        if abs(polygon.normal.x) > 0.9:
            end_faces.append((polygon, key))

    assert top_faces, "No upward-facing top surfaces were generated."
    assert {key for _polygon, key in top_faces} == {"top", "trim"}
    assert all(
        polygon.material_index == (2 if key == "top" else 1)
        for polygon, key in top_faces
    )
    assert end_faces, "No end-cap surfaces were generated."
    assert all(key == "body" and polygon.material_index == 0 for polygon, key in end_faces)


def upward_material_area(obj, face_keys, material_key):
    return sum(
        polygon.area
        for polygon, key in zip(obj.data.polygons, face_keys)
        if polygon.normal.z > 0.9 and key == material_key
    )


def main():
    addon.register()
    try:
        props = bpy.context.scene.profile_wall_props
        assert abs(props.wall_thickness - 0.5) < 1e-6
        assert abs(props.bottom_trim_scale - 0.25) < 1e-6
        assert abs(props.top_trim_scale - 0.25) < 1e-6
        assert abs(props.offset_scale - 0.0) < 1e-6
        props.profile_preset = "BASIC_MOLDING"
        props.wall_thickness = 0.1
        props.cap_ends = True
        props.add_bevel = False

        # The new three-state UI remains backed by the legacy booleans so old
        # saved files retain their topology mode without migration.
        props.fill_inside = False
        props.generate_section = False
        assert props.interior_mode == "HOLLOW"
        props.interior_mode = "SECTION"
        assert not props.fill_inside and props.generate_section
        props.interior_mode = "SOLID"
        assert props.fill_inside and not props.generate_section
        props.interior_mode = "HOLLOW"
        assert not props.fill_inside and not props.generate_section

        source = bpy.data.objects.new("MaterialRegionSource", None)
        bpy.context.collection.objects.link(source)
        points = [Vector((0.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0))]

        obj, face_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, points, False, props
        )
        indices = addon.material_utils.prepare_materials(bpy.context, obj, props)
        addon.mesh_builder.apply_face_material_indices(obj, indices, face_keys)
        assert props.body_material == bpy.data.materials["PWG_Body"]
        assert props.trim_material == bpy.data.materials["PWG_Trim"]
        assert props.top_material == bpy.data.materials["PWG_Top"]
        assert props.section_material == bpy.data.materials["PWG_Section"]
        for material_name, hex_rgba in addon.material_utils.DEFAULT_BASE_COLORS.items():
            material = bpy.data.materials[material_name]
            principled = next(
                node for node in material.node_tree.nodes
                if node.type == "BSDF_PRINCIPLED"
            )
            expected_color = addon.material_utils.hex_rgba_to_scene_linear(hex_rgba)
            actual_color = tuple(principled.inputs["Base Color"].default_value)
            assert all(
                abs(actual - expected) < 1e-6
                for actual, expected in zip(actual_color, expected_color)
            ), (material_name, actual_color, expected_color)
            assert material[addon.material_utils.DEFAULT_COLOR_MARKER] == hex_rgba
        section_material = props.section_material
        assert section_material.use_nodes
        section_image_node = section_material.node_tree.nodes.get(
            addon.material_utils.SECTION_IMAGE_NODE_NAME
        )
        assert section_image_node is not None
        assert section_image_node.image is not None
        assert Path(bpy.path.abspath(section_image_node.image.filepath)).resolve() == (
            ADDONS_DIR
            / "profile_wall_generator"
            / "Textures"
            / "Mat_Stripes_Base_color.png"
        ).resolve()
        section_principled = next(
            node
            for node in section_material.node_tree.nodes
            if node.type == "BSDF_PRINCIPLED"
        )
        base_color_links = section_principled.inputs["Base Color"].links
        assert len(base_color_links) == 1
        assert base_color_links[0].from_node == section_image_node

        # Once the default was established, later Generate/Update calls must
        # preserve a user color edit instead of continually resetting it.
        body_principled = next(
            node for node in props.body_material.node_tree.nodes
            if node.type == "BSDF_PRINCIPLED"
        )
        edited_body_color = (0.1, 0.2, 0.3, 1.0)
        body_principled.inputs["Base Color"].default_value = edited_body_color
        addon.material_utils.prepare_materials(bpy.context, obj, props)
        addon.mesh_builder.apply_face_material_indices(obj, indices, face_keys)
        assert all(
            abs(actual - expected) < 1e-6
            for actual, expected in zip(
                body_principled.inputs["Base Color"].default_value,
                edited_body_color,
            )
        )
        assert_material_regions(obj, face_keys)
        trim_area_scale_1 = upward_material_area(obj, face_keys, "trim")

        props.top_trim_scale = 2.0
        wide_obj, wide_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, points, False, props
        )
        wide_trim_area = upward_material_area(wide_obj, wide_keys, "trim")
        assert wide_trim_area > trim_area_scale_1

        props.top_trim_scale = 0.0
        no_border_obj, no_border_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, points, False, props
        )
        assert addon.mesh_builder._top_trim_border_fraction(
            props,
            addon.profile_presets.get_preset(props.profile_preset)["profile"],
            [props.wall_thickness],
        ) == 0.0
        assert (
            upward_material_area(no_border_obj, no_border_keys, "top")
            > upward_material_area(obj, face_keys, "top")
        )

        props.top_trim_scale = 1.0

        # The legacy single-layer cap path must also use Body.
        props.wall_thickness = 0.0
        props.offset_scale = 1.0
        flat_obj, flat_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, points, False, props
        )
        flat_indices = addon.material_utils.prepare_materials(bpy.context, flat_obj, props)
        addon.mesh_builder.apply_face_material_indices(flat_obj, flat_indices, flat_keys)
        flat_end_faces = [
            (polygon, key)
            for polygon, key in zip(flat_obj.data.polygons, flat_keys)
            if abs(polygon.normal.x) > 0.9
        ]
        assert len(flat_end_faces) == 2
        assert all(key == "body" and polygon.material_index == 0 for polygon, key in flat_end_faces)

        # Closed walls keep the inset border connected around mitered corners.
        props.offset_scale = 0.0
        props.wall_thickness = 0.1
        props.fill_inside = False
        props.generate_section = False
        props.section_height = 0.2
        closed_points = [
            Vector((0.0, 0.0, 0.0)),
            Vector((2.0, 0.0, 0.0)),
            Vector((2.0, 2.0, 0.0)),
            Vector((0.0, 2.0, 0.0)),
        ]
        closed_obj, closed_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, closed_points, True, props
        )
        closed_top_keys = {
            key
            for polygon, key in zip(closed_obj.data.polygons, closed_keys)
            if polygon.normal.z > 0.9
        }
        assert {"top", "trim"}.issubset(closed_top_keys)
        bm = bmesh.new()
        bm.from_mesh(closed_obj.data)
        try:
            assert all(edge.is_manifold for edge in bm.edges)
        finally:
            bm.free()

        # Section is an independent interior floor at the requested height.
        props.generate_section = True
        props.section_height = 2.0
        section_obj, section_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, closed_points, True, props
        )
        section_indices = addon.material_utils.prepare_materials(
            bpy.context, section_obj, props
        )
        addon.mesh_builder.apply_face_material_indices(
            section_obj, section_indices, section_keys
        )
        section_faces = [
            polygon
            for polygon, key in zip(section_obj.data.polygons, section_keys)
            if key == "section"
        ]
        assert section_faces
        assert all(polygon.material_index == 3 for polygon in section_faces)
        assert all(
            abs(section_obj.data.vertices[index].co.z - 2.0) < 1e-6
            for polygon in section_faces
            for index in polygon.vertices
        )
        section_uv_layer = section_obj.data.uv_layers.get("ProfileWallUV")
        assert section_uv_layer is not None
        section_uvs = [
            tuple(section_uv_layer.data[loop_index].uv)
            for polygon, key in zip(section_obj.data.polygons, section_keys)
            if key == "section"
            for loop_index in polygon.loop_indices
        ]
        assert section_uvs
        assert abs(min(uv[0] for uv in section_uvs)) < 1e-6
        assert abs(min(uv[1] for uv in section_uvs)) < 1e-6
        assert max(uv[0] for uv in section_uvs) - min(uv[0] for uv in section_uvs) > 1.9
        assert max(uv[1] for uv in section_uvs) - min(uv[1] for uv in section_uvs) > 1.9

        props.section_uv_scale = 2.0
        scaled_section_obj, scaled_section_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, closed_points, True, props
        )
        scaled_uv_layer = scaled_section_obj.data.uv_layers.get("ProfileWallUV")
        scaled_section_uvs = [
            tuple(scaled_uv_layer.data[loop_index].uv)
            for polygon, key in zip(scaled_section_obj.data.polygons, scaled_section_keys)
            if key == "section"
            for loop_index in polygon.loop_indices
        ]
        assert max(uv[0] for uv in scaled_section_uvs) > 3.9
        assert max(uv[1] for uv in scaled_section_uvs) > 3.9
        props.section_uv_scale = 1.0

        # One Curve object may contain several disconnected closed splines.
        # Every closed island gets its own non-degenerate local planar UVs,
        # including when the existing generated object is updated in place.
        second_closed_points = [
            Vector((4.0, 0.0, 0.0)),
            Vector((6.0, 0.0, 0.0)),
            Vector((6.0, 2.0, 0.0)),
            Vector((4.0, 2.0, 0.0)),
        ]
        multi_paths = [
            (closed_points, True),
            (second_closed_points, True),
            ([Vector((0.0, 4.0, 0.0)), Vector((2.0, 4.0, 0.0))], False),
        ]
        multi_obj, multi_keys = addon.mesh_builder.build_profile_wall_paths_object(
            bpy.context, source, multi_paths, props
        )
        multi_obj, multi_keys = addon.mesh_builder.build_profile_wall_paths_object(
            bpy.context, source, multi_paths, props, existing_obj=multi_obj
        )
        multi_section_faces = [
            polygon
            for polygon, key in zip(multi_obj.data.polygons, multi_keys)
            if key == "section"
        ]
        assert len(multi_section_faces) == 4, len(multi_section_faces)
        multi_uv_layer = multi_obj.data.uv_layers.get("ProfileWallUV")
        assert multi_uv_layer is not None
        for polygon in multi_section_faces:
            triangle_uvs = [
                Vector(multi_uv_layer.data[loop_index].uv)
                for loop_index in polygon.loop_indices
            ]
            uv_area = abs(
                (triangle_uvs[1] - triangle_uvs[0]).cross(
                    triangle_uvs[2] - triangle_uvs[0]
                )
            )
            assert uv_area > 1e-8, uv_area

        # A closed solid block's filled upper surface uses Top as well.
        props.fill_inside = True
        solid_obj, solid_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, closed_points, True, props
        )
        solid_indices = addon.material_utils.prepare_materials(bpy.context, solid_obj, props)
        addon.mesh_builder.apply_face_material_indices(solid_obj, solid_indices, solid_keys)
        solid_top_faces = [
            (polygon, key)
            for polygon, key in zip(solid_obj.data.polygons, solid_keys)
            if polygon.normal.z > 0.9
        ]
        assert solid_top_faces
        assert {key for _polygon, key in solid_top_faces} == {"top", "trim"}
        assert "section" not in solid_keys
        assert all(
            polygon.material_index == (2 if key == "top" else 1)
            for polygon, key in solid_top_faces
        )
        bm = bmesh.new()
        bm.from_mesh(solid_obj.data)
        try:
            assert all(edge.is_manifold for edge in bm.edges)
        finally:
            bm.free()

        props.top_trim_scale = 2.0
        solid_wide_obj, solid_wide_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, closed_points, True, props
        )
        solid_border_width = addon.mesh_builder._solid_top_trim_border_width(
            props,
            addon.profile_presets.get_preset(props.profile_preset)["profile"],
            closed_points,
        )
        assert abs(solid_border_width - 0.6) < 1e-6, solid_border_width
        assert (
            upward_material_area(solid_wide_obj, solid_wide_keys, "top")
            < upward_material_area(solid_obj, solid_keys, "top")
        )

        props.top_trim_scale = 0.0
        solid_plain_obj, solid_plain_keys = addon.mesh_builder.build_profile_wall_object(
            bpy.context, source, closed_points, True, props
        )
        assert addon.mesh_builder._solid_top_trim_border_width(
            props,
            addon.profile_presets.get_preset(props.profile_preset)["profile"],
            [Vector((0.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0))],
        ) == 0.0
        assert (
            upward_material_area(solid_plain_obj, solid_plain_keys, "top")
            > upward_material_area(solid_obj, solid_keys, "top")
        )

        print("PWG_MATERIAL_REGIONS_OK")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
