import sys
from pathlib import Path

import bpy


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


class _SyntheticUpdate:
    def __init__(
        self,
        update_id,
        *,
        geometry=False,
        transform=False,
        shading=False,
    ):
        self.id = update_id
        self.is_updated_geometry = geometry
        self.is_updated_transform = transform
        self.is_updated_shading = shading


class _SyntheticDepsgraph:
    def __init__(self, *updates):
        self.updates = updates


def make_test_curve(name):
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


def assert_auto_update_idle():
    assert not addon._pending_update_sources, addon._pending_update_sources
    assert not bpy.app.timers.is_registered(addon._process_debounced_updates)


def main():
    addon.register()
    original_create = addon.mesh_builder._create_wall_object
    create_calls = []

    def tracked_create(*args, **kwargs):
        create_calls.append(1)
        return original_create(*args, **kwargs)

    try:
        source = make_test_curve("RenderStableSource")
        props = source.pwg_settings
        props.hide_source_curve = False
        props.auto_update = True
        select_only(source)

        assert bpy.ops.profile_wall.generate() == {"FINISHED"}
        wall = addon.operators.get_linked_wall(source)
        assert wall is not None

        bpy.context.view_layer.update()
        addon._cancel_debounced_timer()
        addon._pending_update_sources.clear()
        addon.mesh_builder._create_wall_object = tracked_create

        # Rebuilding the wall writes link metadata. Those shading-only source
        # updates must not schedule another wall rebuild.
        addon.operators.generate_wall_from_source(
            bpy.context,
            source,
            props,
            existing_wall=wall,
        )
        assert len(create_calls) == 1
        bpy.context.view_layer.update()
        assert_auto_update_idle()

        # A rendered viewport can emit shading-only object evaluations. They
        # must never be treated as source geometry edits.
        create_calls.clear()
        addon.profile_wall_auto_update(
            bpy.context.scene,
            _SyntheticDepsgraph(
                _SyntheticUpdate(source, shading=True),
            ),
        )
        assert_auto_update_idle()
        assert not create_calls

        # Source transforms are real wall-path changes and must still update.
        source.location.x += 1.0
        bpy.context.view_layer.update()
        assert addon._pending_update_sources == {source.name}
        addon.flush_pending_updates()
        assert len(create_calls) == 1
        bpy.context.view_layer.update()
        assert_auto_update_idle()

        # Curve point edits must also update exactly once, then become idle.
        create_calls.clear()
        source.data.splines[0].points[1].co.x += 1.0
        source.data.update_tag()
        bpy.context.view_layer.update()
        assert addon._pending_update_sources == {source.name}
        addon.flush_pending_updates()
        assert len(create_calls) == 1
        bpy.context.view_layer.update()
        assert_auto_update_idle()

        # A camera render must not rebuild or re-queue an unchanged wall.
        create_calls.clear()
        scene = bpy.context.scene
        scene.render.resolution_x = 16
        scene.render.resolution_y = 16
        scene.render.resolution_percentage = 100
        assert bpy.ops.render.render() == {"FINISHED"}
        bpy.context.view_layer.update()
        assert not create_calls
        assert_auto_update_idle()

        print("PWG_AUTO_UPDATE_RENDER_STABILITY_OK")
    finally:
        addon.mesh_builder._create_wall_object = original_create
        addon.unregister()


if __name__ == "__main__":
    main()
