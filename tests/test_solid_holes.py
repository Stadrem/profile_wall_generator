"""Run with Blender --background --factory-startup --python this_file."""
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import profile_wall_generator as addon


def loop(coords, z=0):
    return [Vector((x, y, z)) for x, y in coords], True


OUTER = [(0, 0), (12, 0), (12, 12), (0, 12)]
HOLE = [(2, 2), (10, 2), (10, 10), (2, 10)]
ISLAND = [(4, 4), (6, 4), (6, 6), (4, 6)]


def check(paths, props, area, name, check_hole=True):
    source = bpy.data.objects.new(name, bpy.data.curves.new(name, 'CURVE'))
    bpy.context.collection.objects.link(source)
    obj, keys = addon.mesh_builder.build_profile_wall_paths_object(bpy.context, source, paths, props)
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        assert all(e.is_manifold for e in bm.edges), name + ': open or overlapping edges'
        assert all(e.is_contiguous for e in bm.edges), name + ': inconsistent normals'
        assert bm.calc_volume(signed=True) > 0, name + ': inside-out solid'
    finally:
        bm.free()
    upper = [p for p in mesh.polygons if p.normal.z > .99]
    actual = sum(p.area for p in upper)
    assert abs(actual - area) < 1e-4, (name, actual, area)
    assert len(keys) == len(mesh.polygons)
    assert len(mesh.uv_layers.active.data) == len(mesh.loops)
    assert {'top', 'trim'}.issubset({keys[p.index] for p in upper}), name
    for polygon in upper:
        p = polygon.center
        if check_hole and 2.01 < p.x < 9.99 and 2.01 < p.y < 9.99:
            assert 3.99 < p.x < 6.01 and 3.99 < p.y < 6.01, (name, 'hole filled', tuple(p))
    print('PASS', name, 'top area', actual)


addon.register()
try:
    props = bpy.context.scene.profile_wall_props
    props.auto_update = False
    props.fill_inside = True
    props.offset_scale = 0
    props.top_trim_scale = .25
    for reverse in (False, True):
        coords = [OUTER, HOLE, ISLAND]
        paths = [loop(list(reversed(c)) if reverse else c) for c in coords]
        check(paths, props, 84, 'island_' + str(reverse))
        check([paths[1], paths[2], paths[0]], props, 84, 'reordered_' + str(reverse))
    check([loop(OUTER), loop(HOLE[::-1])], props, 80, 'opposite_winding')
    props.offset_scale = 1
    check([loop(OUTER), loop(HOLE)], props, 86.4, 'profile_offsets', check_hole=False)
    props.offset_scale = 0
    check([loop(OUTER), loop([(1, 1), (3, 1), (3, 3), (1, 3)]),
           loop([(7, 7), (11, 7), (11, 11), (7, 11)])], props, 124,
          'multiple_holes', check_hole=False)
    # The hole almost reaches the outside: trim strips overlap locally, but
    # must not disappear from the rest of the ring or create open cap seams.
    check([loop(OUTER), loop([(.05, 2), (10, 2), (10, 10), (.05, 10)])],
          props, 64.4, 'overlapping_trim', check_hole=False)
    # Concave corner and a very short edge fold the offset strip over itself.
    check([loop(OUTER), loop([(2, 2), (10, 2), (10, 10), (6, 10),
                             (6, 5), (5.98, 5), (5.98, 10), (2, 10)])],
          props, 80.1, 'short_edge_trim', check_hole=False)
    check([loop([(0, 0), (12, 0), (12, 12), (6, 12.0000007), (0, 12)]),
           loop(HOLE)], props, 80, 'almost_collinear_boundary')

    # Separate heights must not turn independent stacked shapes into holes.
    assert addon.mesh_builder._solid_path_parents([loop(OUTER), loop(HOLE, z=3)]) == [None, None]
    # Concave outer: vertices inside alone are insufficient when an edge crosses a notch.
    concave = loop([(0, 0), (10, 0), (10, 10), (6, 10), (6, 4), (4, 4), (4, 10), (0, 10)])
    crossing = loop([(2, 2), (8, 2), (8, 8), (2, 8)])
    assert addon.mesh_builder._solid_path_parents([concave, crossing]) == [None, None]
    print('ALL_SOLID_HOLE_TESTS_PASSED')
finally:
    addon.unregister()
