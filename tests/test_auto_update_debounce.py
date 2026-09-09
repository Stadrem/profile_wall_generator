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


def make_test_curve(name):
    curve_data = bpy.data.curves.new(name + "Data", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(3)
    coords = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]
    for pt, co in zip(spline.points, coords):
        pt.co = (co[0], co[1], co[2], 1.0)
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
        source = make_test_curve("DebounceSource")
        source.pwg_settings.auto_update = True
        source.pwg_settings.hide_source_curve = False
        select_only(source)

        # 1. Initial generation
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = addon.operators.get_linked_wall(source)
        assert wall is not None
        assert len(create_calls) == 1

        create_calls.clear()

        # 2. Simulate rapid consecutive updates (e.g. dragging vertices in Edit Mode)
        for i in range(10):
            source.data.splines[0].points[0].co.x += 0.05
            source.data.update_tag()
            addon.profile_wall_auto_update(
                bpy.context.scene,
                _DepsgraphUpdates(source.data),
            )

        # Immediate check: timer is scheduled, but regeneration hasn't run 10 times synchronously
        assert len(create_calls) == 0, f"Expected 0 immediate calls before timer, got {len(create_calls)}"
        assert addon._pending_update_sources == {source.name}

        # 3. Flush the debounced queue
        addon.flush_pending_updates()
        assert len(create_calls) == 1, f"Expected exactly 1 debounced update call, got {len(create_calls)}"
        assert len(addon._pending_update_sources) == 0

        # 4. Edge case: Deleted source in pending queue should be safely ignored without crash
        addon._pending_update_sources.add("NonExistentObject")
        addon.flush_pending_updates()
        assert len(addon._pending_update_sources) == 0

        # 5. Error isolation: An error in one source must not prevent other sources from updating
        source_b = make_test_curve("DebounceSourceB")
        source_b.pwg_settings.auto_update = True
        source_b.pwg_settings.hide_source_curve = False
        select_only(source_b)
        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall_b = addon.operators.get_linked_wall(source_b)
        assert wall_b is not None

        create_calls.clear()
        # Trigger updates for both sources, but inject an invalid state into source
        addon._pending_update_sources.add(source.name)
        addon._pending_update_sources.add(source_b.name)
        
        # Corrupt source geometry temporarily to trigger an error in source
        source.data.splines.clear()
        
        # Flush should process source_b successfully even though source fails
        addon.flush_pending_updates()
        assert len(create_calls) == 1  # only source_b successfully built
        assert len(addon._pending_update_sources) == 0

        # 6. Timer reload cleanup verification
        addon._schedule_debounced_update()
        old_timer_fn = addon._process_debounced_updates
        assert bpy.app.timers.is_registered(old_timer_fn)
        
        import importlib
        importlib.reload(addon)
        
        assert not bpy.app.timers.is_registered(old_timer_fn), "Old timer function should be unregistered on reload"
        assert not bpy.app.timers.is_registered(addon._process_debounced_updates)

        print("PWG_AUTO_UPDATE_DEBOUNCE_OK")
    finally:
        addon.mesh_builder._create_wall_object = original_create
        addon.unregister()


if __name__ == "__main__":
    main()
