"""Run in factory-startup Blender; writes only to a temporary directory."""
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import profile_wall_generator as addon


def pair():
    source = bpy.data.objects['PersistenceSource']
    wall = addon.operators.get_linked_wall(source)
    assert wall is not None
    assert addon.operators.get_linked_source(wall) == source
    return source, wall


def max_z(wall):
    return max((wall.matrix_world @ vertex.co).z for vertex in wall.data.vertices)


def main():
    addon.register()
    try:
        data = bpy.data.curves.new('PersistenceCurve', 'CURVE')
        data.dimensions = '3D'
        spline = data.splines.new('POLY')
        spline.points.add(1)
        spline.points[0].co = (0, 0, 0, 1)
        spline.points[1].co = (4, 0, 0, 1)
        source = bpy.data.objects.new('PersistenceSource', data)
        bpy.context.collection.objects.link(source)
        for obj in list(bpy.context.selected_objects):
            obj.select_set(False)
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        source.pwg_settings.height_scale = 1.5
        source.pwg_settings.auto_update = True
        assert bpy.ops.profile_wall.generate() == {'FINISHED'}
        source, wall = pair()
        source.location.x = wall.location.x = 10
        bpy.context.view_layer.update()
        addon.flush_pending_updates()
        material_names = [mat.name for mat in wall.data.materials]
        vertices = [tuple(wall.matrix_world @ v.co) for v in wall.data.vertices]
        with tempfile.TemporaryDirectory(prefix='pwg_persistence_') as folder:
            path = str(Path(folder) / 'roundtrip.blend')
            assert bpy.ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
            assert bpy.ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
            source, wall = pair()
            assert source.pwg_settings.height_scale == 1.5
            assert source.pwg_settings.auto_update
            assert [mat.name for mat in wall.data.materials] == material_names
            assert [tuple(wall.matrix_world @ v.co) for v in wall.data.vertices] == vertices
            assert bpy.ops.profile_wall.edit_source_curve() == {'FINISHED'}
            assert bpy.ops.profile_wall.show_generated_mesh() == {'FINISHED'}
            assert source.mode == 'OBJECT'
            assert bpy.context.active_object == wall
            print('PWG_SAVE_REOPEN_OK')

            # Background execution needs explicit checkpoints; these exercise
            # Blender's undo stack, not interactive keyboard/UI undo timing.
            bpy.context.preferences.edit.use_global_undo = True
            assert bpy.ops.ed.undo_push(message='PWG before setting') == {'FINISHED'}
            source.pwg_settings.height_scale = 2.0
            assert abs(max_z(wall) - 6) < 1e-5
            assert bpy.ops.ed.undo_push(message='PWG after setting') == {'FINISHED'}
            assert bpy.ops.ed.undo() == {'FINISHED'}
            source, wall = pair()
            assert source.pwg_settings.height_scale == 1.5
            assert abs(max_z(wall) - 4.5) < 1e-5
            assert bpy.ops.ed.redo() == {'FINISHED'}
            source, wall = pair()
            assert source.pwg_settings.height_scale == 2.0
            assert abs(max_z(wall) - 6) < 1e-5
            print('PWG_UNDO_REDO_CHECKPOINT_OK')

            wall_name = wall.name
            bpy.context.view_layer.objects.active = wall
            assert bpy.ops.ed.undo_push(message='PWG before detach') == {'FINISHED'}
            assert bpy.ops.profile_wall.convert_to_editable() == {'FINISHED'}
            assert not wall.get('profile_wall_generated')
            assert addon.operators.get_linked_wall(source) is None
            assert bpy.ops.ed.undo_push(message='PWG after detach') == {'FINISHED'}
            assert bpy.ops.ed.undo() == {'FINISHED'}
            source, wall = pair()
            assert wall.name == wall_name
            assert wall.get('profile_wall_generated')
            assert bpy.ops.ed.redo() == {'FINISHED'}
            source = bpy.data.objects['PersistenceSource']
            wall = bpy.data.objects[wall_name]
            assert not wall.get('profile_wall_generated')
            assert addon.operators.get_linked_wall(source) is None
            assert abs(max_z(wall) - 6) < 1e-5
            print('PWG_DETACH_UNDO_REDO_CHECKPOINT_OK')
    finally:
        addon.unregister()


if __name__ == '__main__':
    main()
