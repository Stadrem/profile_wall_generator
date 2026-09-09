import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


def make_source(name):
    curve_data = bpy.data.curves.new(name + "Data", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (4.0, 0.0, 0.0, 1.0)
    source = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(source)
    return source


def assert_path_vertices_match_source(source, wall):
    # BASIC_MOLDING has six profile samples per source point.  With zero
    # thickness/profile offset, the first sample at each point is exact.
    profile_count = 6
    for vertex_index, point in ((0, (0.0, 0.0, 0.0)), (profile_count, (4.0, 0.0, 0.0))):
        expected = source.matrix_world @ Vector(point)
        actual = wall.matrix_world @ wall.data.vertices[vertex_index].co
        assert (actual - expected).length < 1e-5, (actual[:], expected[:])


def main():
    addon.register()
    try:
        source = make_source("TransformSource")
        for selected in list(bpy.context.selected_objects):
            selected.select_set(False)
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        props = source.pwg_settings
        props.auto_update = False
        props.hide_source_curve = False
        props.wall_thickness = 0.0
        props.offset_scale = 0.0

        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = addon.operators.get_linked_wall(source)
        assert wall is not None
        assert_path_vertices_match_source(source, wall)

        parent = bpy.data.objects.new("TransformParent", None)
        bpy.context.collection.objects.link(parent)
        parent.location = (3.0, -2.0, 1.0)
        parent.rotation_euler = (0.0, 0.0, 0.25)
        parent.scale = (1.2, 0.8, 1.0)

        source.parent = parent
        wall.parent = parent
        source.matrix_parent_inverse = Matrix.Identity(4)
        wall.matrix_parent_inverse = Matrix.Identity(4)
        source.location = (10.0, 2.0, 0.0)
        wall.location = (10.0, 2.0, 0.0)
        source.rotation_euler = (0.0, 0.0, 0.4)
        wall.rotation_euler = (0.0, 0.0, 0.4)
        source.scale = (1.5, 0.75, 1.0)
        wall.scale = (1.5, 0.75, 1.0)
        bpy.context.view_layer.update()

        addon.operators.generate_wall_from_source(
            bpy.context, source, props, existing_wall=wall
        )
        assert_path_vertices_match_source(source, wall)

        # A second update after moving both linked objects must still apply
        # the shared transform only once.
        source.location.x += 2.0
        wall.location.x += 2.0
        bpy.context.view_layer.update()
        addon.operators.generate_wall_from_source(
            bpy.context, source, props, existing_wall=wall
        )
        assert_path_vertices_match_source(source, wall)

        print("PWG_WALL_TRANSFORM_PRESERVATION_OK")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
