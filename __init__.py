import bpy

bl_info = {
    "name": "Profile Wall Generator",
    "author": "Kim Dongsu",
    "version": (0, 6, 6),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > K-Quick Tools",
    "description": "Generate profile molding walls from curves",
    "category": "Mesh",
}

if "profile_presets" in locals():
    if "_process_debounced_updates" in locals() and bpy.app.timers.is_registered(_process_debounced_updates):
        try:
            bpy.app.timers.unregister(_process_debounced_updates)
        except ValueError:
            pass
    import importlib
    importlib.reload(profile_presets)
    importlib.reload(path_utils)
    importlib.reload(material_utils)
    importlib.reload(uv_utils)
    importlib.reload(mesh_builder)
    importlib.reload(properties)
    importlib.reload(operators)
    importlib.reload(panels)
else:
    from . import profile_presets
    from . import path_utils
    from . import material_utils
    from . import uv_utils
    from . import mesh_builder
    from . import properties
    from . import operators
    from . import panels


_is_updating = False
_pending_update_sources = set()
DEBOUNCE_DELAY = 0.08


def _source_objects_from_depsgraph_update(scene, update_id):
    if isinstance(update_id, bpy.types.Object):
        obj = update_id.original if update_id.is_evaluated else update_id
        if not obj.get("profile_wall_generated"):
            yield obj
        return

    if isinstance(update_id, (bpy.types.Curve, bpy.types.Mesh)):
        data = update_id.original if update_id.is_evaluated else update_id
        for obj in scene.objects:
            if (
                not obj.get("profile_wall_generated")
                and obj.type in {"CURVE", "MESH"}
                and obj.data == data
            ):
                yield obj


def _depsgraph_update_affects_source_geometry(update):
    """Ignore shading-only evaluations that must not rebuild generated walls."""
    update_id = update.id
    geometry_changed = getattr(update, "is_updated_geometry", None)
    transform_changed = getattr(update, "is_updated_transform", None)

    # Lightweight test doubles used by older regression tests only expose ID.
    # Real Blender DepsgraphUpdate instances always expose the update flags.
    if geometry_changed is None and transform_changed is None:
        return True

    if isinstance(update_id, bpy.types.Object):
        return bool(geometry_changed or transform_changed)
    if isinstance(update_id, (bpy.types.Curve, bpy.types.Mesh)):
        return bool(geometry_changed)
    return False


def _process_debounced_updates():
    global _is_updating, _pending_update_sources
    if _is_updating or not _pending_update_sources:
        return None

    sources_to_update = list(_pending_update_sources)
    _pending_update_sources.clear()

    _is_updating = True
    try:
        scene = bpy.context.scene
        for source_name in sources_to_update:
            try:
                source_obj = bpy.data.objects.get(source_name)
                if source_obj is None:
                    continue
                wall_obj = operators.get_linked_wall(source_obj)
                if wall_obj:
                    props = operators.settings_for_source(scene, source_obj)
                    if props is not None and props.auto_update:
                        operators.generate_wall_from_source(
                            bpy.context,
                            source_obj,
                            props,
                            existing_wall=wall_obj,
                        )
                operators.consume_source_warning(source_obj)
            except Exception as item_err:
                print(f"Profile Wall Auto-Update Error ({source_name}):", item_err)
    except Exception as e:
        print("Profile Wall Auto-Update Batch Error:", e)
    finally:
        _is_updating = False
    return None


def flush_pending_updates():
    """Immediately process any queued debounced updates."""
    _cancel_debounced_timer()
    return _process_debounced_updates()


def _schedule_debounced_update():
    _cancel_debounced_timer()
    bpy.app.timers.register(_process_debounced_updates, first_interval=DEBOUNCE_DELAY)


def _cancel_debounced_timer():
    if bpy.app.timers.is_registered(_process_debounced_updates):
        try:
            bpy.app.timers.unregister(_process_debounced_updates)
        except ValueError:
            pass


@bpy.app.handlers.persistent
def profile_wall_auto_update(scene, depsgraph):
    global _is_updating
    if _is_updating:
        return

    should_schedule = False
    for update in depsgraph.updates:
        if not _depsgraph_update_affects_source_geometry(update):
            continue
        for obj in _source_objects_from_depsgraph_update(scene, update.id):
            props = operators.settings_for_source(scene, obj)
            if (
                props is not None
                and props.auto_update
                and operators.get_linked_wall(obj) is not None
            ):
                _pending_update_sources.add(obj.name)
                should_schedule = True

    if should_schedule:
        _schedule_debounced_update()


@bpy.app.handlers.persistent
def profile_wall_load_post(_filepath):
    properties.migrate_legacy_scene_settings()


def _remove_auto_update_handlers():
    for handler in list(bpy.app.handlers.depsgraph_update_post):
        if (
            getattr(handler, "__module__", None) == __name__
            and getattr(handler, "__name__", None) == "profile_wall_auto_update"
        ):
            bpy.app.handlers.depsgraph_update_post.remove(handler)


def _remove_load_post_handlers():
    for handler in list(bpy.app.handlers.load_post):
        if (
            getattr(handler, "__module__", None) == __name__
            and getattr(handler, "__name__", None) == "profile_wall_load_post"
        ):
            bpy.app.handlers.load_post.remove(handler)


def register():
    properties.register()
    operators.register()
    panels.register()
    properties.migrate_legacy_scene_settings()
    _remove_auto_update_handlers()
    bpy.app.handlers.depsgraph_update_post.append(profile_wall_auto_update)
    _remove_load_post_handlers()
    bpy.app.handlers.load_post.append(profile_wall_load_post)


def unregister():
    _cancel_debounced_timer()
    _pending_update_sources.clear()
    _remove_auto_update_handlers()
    _remove_load_post_handlers()
    panels.unregister()
    operators.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
