import sys
import time
from pathlib import Path

import bpy


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


class _ObjectUpdate:
    def __init__(self, obj):
        self.id = obj


class _DepsgraphUpdates:
    def __init__(self, *objects):
        self.updates = [_ObjectUpdate(obj) for obj in objects]


def make_multispline_curve(name, spline_count=36, points_per_spline=12):
    curve_data = bpy.data.curves.new(name + "Data", "CURVE")
    curve_data.dimensions = "3D"
    for spline_index in range(spline_count):
        spline = curve_data.splines.new("POLY")
        spline.points.add(points_per_spline - 1)
        base_x = (spline_index % 6) * 5.0
        base_y = (spline_index // 6) * 4.0
        for point_index, point in enumerate(spline.points):
            point.co = (
                base_x + point_index * 0.3,
                base_y + (0.35 if point_index % 2 else 0.0),
                0.0,
                1.0,
            )
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
    original_create = addon.mesh_builder._create_wall_object
    create_calls = []

    def tracked_create(*args, **kwargs):
        create_calls.append(1)
        return original_create(*args, **kwargs)

    addon.mesh_builder._create_wall_object = tracked_create
    try:
        source = make_multispline_curve("ManySplineSource")
        source.pwg_settings.auto_update = False
        source.pwg_settings.hide_source_curve = False
        select_only(source)

        objects_before = len(bpy.data.objects)
        meshes_before = len(bpy.data.meshes)
        started = time.perf_counter()
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        generate_seconds = time.perf_counter() - started
        wall = bpy.context.active_object

        assert len(create_calls) == 1, len(create_calls)
        assert len(bpy.data.objects) == objects_before + 1
        assert len(bpy.data.meshes) == meshes_before + 1
        assert addon.operators.get_linked_wall(source) == wall

        source.pwg_settings.auto_update = True
        create_calls.clear()
        source.data.splines[0].points[1].co.x += 0.25
        source.data.update_tag()
        started = time.perf_counter()
        addon.profile_wall_auto_update(
            bpy.context.scene,
            _DepsgraphUpdates(source.data),
        )
        addon.flush_pending_updates()
        update_seconds = time.perf_counter() - started

        assert len(create_calls) == 1, len(create_calls)
        assert len(bpy.data.objects) == objects_before + 1
        assert len(bpy.data.meshes) == meshes_before + 1
        assert addon.operators.get_linked_wall(source) == wall
        print(
            "PWG_MULTISPLINE_IN_MEMORY_OK",
            "splines=36",
            f"generate_ms={generate_seconds * 1000.0:.3f}",
            f"update_ms={update_seconds * 1000.0:.3f}",
        )
    finally:
        addon.mesh_builder._create_wall_object = original_create
        addon.unregister()


if __name__ == "__main__":
    main()
