import bpy

from . import material_utils
from . import mesh_builder
from . import path_utils


def settings_for_source(scene, source_obj):
    if source_obj is None:
        return None
    if source_obj is not None and hasattr(source_obj, "pwg_settings"):
        return source_obj.pwg_settings
    return getattr(scene, "profile_wall_props", None)


def props_for(context, source_obj=None):
    if source_obj is None:
        active = context.active_object
        if active is not None and active.get("profile_wall_generated"):
            source_obj = get_linked_source(active)
        else:
            source_obj = active
    return settings_for_source(context.scene, source_obj)


class PROFILE_WALL_OT_generate(bpy.types.Operator):
    bl_idname = "profile_wall.generate"
    bl_label = "Generate Wall"
    bl_description = "Generate a profile molding wall from the active curve or mesh line"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source_obj = context.active_object
        props = props_for(context, source_obj)

        if source_obj is not None and source_obj.get("profile_wall_generated"):
            self.report({"WARNING"}, "Select the source curve or mesh path, not the generated wall.")
            return {"CANCELLED"}
        if props is None:
            self.report({"ERROR"}, "Profile Wall settings are unavailable. Reload the add-on.")
            return {"CANCELLED"}

        try:
            existing_wall = get_linked_wall(source_obj)
            obj = generate_wall_from_source(
                context, source_obj, props, existing_wall=existing_wall
            )
        except path_utils.PathError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}

        ensure_object_in_view_layer(context, obj)
        context.view_layer.objects.active = obj
        obj.select_set(True)
        warning = consume_source_warning(source_obj)
        if warning:
            self.report({"WARNING"}, warning)
        elif existing_wall is not None:
            self.report({"INFO"}, "Updated existing profile wall.")
        else:
            self.report({"INFO"}, "Generated profile wall.")
        return {"FINISHED"}


class PROFILE_WALL_OT_update(bpy.types.Operator):
    bl_idname = "profile_wall.update"
    bl_label = "Update Wall"
    bl_description = "Regenerate the selected profile wall from its source curve"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active = context.active_object
        if active is None:
            self.report({"WARNING"}, "Select a generated wall or source curve.")
            return {"CANCELLED"}

        source_obj, wall_obj = find_wall_pair(active)
        if source_obj is None or wall_obj is None:
            self.report({"WARNING"}, "Select a generated wall or its linked source curve.")
            return {"CANCELLED"}

        props = props_for(context, source_obj)
        if props is None:
            self.report({"ERROR"}, "Profile Wall settings are unavailable. Reload the add-on.")
            return {"CANCELLED"}
        try:
            obj = generate_wall_from_source(context, source_obj, props, existing_wall=wall_obj)
        except path_utils.PathError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}

        warning = consume_source_warning(source_obj)
        if warning:
            self.report({"WARNING"}, warning)
        else:
            self.report({"INFO"}, "Updated profile wall.")
        return {"FINISHED"}


class PROFILE_WALL_OT_convert_to_editable(bpy.types.Operator):
    bl_idname = "profile_wall.convert_to_editable"
    bl_label = "Convert To Editable Mesh"
    bl_description = "Detach the generated wall from its source curve"
    bl_options = {"REGISTER", "UNDO"}

    apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        default=False,
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH" or not obj.get("profile_wall_generated"):
            self.report({"WARNING"}, "Select a generated mesh wall.")
            return {"CANCELLED"}

        source_obj = get_linked_source(obj)
        source_links_to_obj = bool(
            source_obj is not None
            and (
                getattr(source_obj, "pwg_result_ref", None) == obj
                or source_obj.get("profile_wall_result") == obj.name
            )
        )

        if self.apply_modifiers:
            context.view_layer.objects.active = obj
            for modifier in list(obj.modifiers):
                try:
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
                except RuntimeError:
                    self.report({"WARNING"}, "Could not apply modifier: " + modifier.name)

        for key in (
            "profile_wall_source",
            "profile_wall_generated",
            "profile_wall_preset",
            "_profile_wall_face_material_keys",
        ):
            if key in obj:
                del obj[key]

        if hasattr(obj, "pwg_source_ref"):
            obj.pwg_source_ref = None
        if source_links_to_obj:
            if "profile_wall_result" in source_obj:
                del source_obj["profile_wall_result"]
            if hasattr(source_obj, "pwg_result_ref"):
                source_obj.pwg_result_ref = None

        self.report({"INFO"}, "Wall is now editable.")
        return {"FINISHED"}


class PROFILE_WALL_OT_edit_source_curve(bpy.types.Operator):
    bl_idname = "profile_wall.edit_source_curve"
    bl_label = "Edit Source Curve"
    bl_description = "Show the linked source and enter Edit Mode while keeping the wall visible when Auto Update is enabled"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active = context.active_object
        source_obj, wall_obj = find_wall_pair(active)
        if source_obj is None:
            self.report({"WARNING"}, "No source curve is linked to this wall.")
            return {"CANCELLED"}

        props = settings_for_source(context.scene, source_obj)
        if context.object is not None and context.object.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError as exc:
                self.report({"WARNING"}, "Could not leave the current mode: " + str(exc))
                return {"CANCELLED"}

        if wall_obj:
            _repair_wall_source_owner(wall_obj, source_obj)
            wall_obj.hide_set(not (props is not None and props.auto_update))
        ensure_object_in_view_layer(context, source_obj)
        for selected in list(context.selected_objects):
            selected.select_set(False)
        source_obj.hide_viewport = False
        source_obj.hide_set(False)
        source_obj.select_set(True)
        context.view_layer.objects.active = source_obj
        try:
            bpy.ops.object.mode_set(mode="EDIT")
        except RuntimeError as exc:
            self.report({"WARNING"}, "Could not enter Edit Mode: " + str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, "Editing source curve.")
        return {"FINISHED"}


class PROFILE_WALL_OT_show_generated_mesh(bpy.types.Operator):
    bl_idname = "profile_wall.show_generated_mesh"
    bl_label = "Show Generated Mesh"
    bl_description = "Hide the source curve and show/select the generated wall"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active = context.active_object
        source_obj, wall_obj = find_wall_pair(active)
        if wall_obj is None:
            self.report({"WARNING"}, "No generated wall is linked to this curve.")
            return {"CANCELLED"}

        # Switching away from an edited source must leave Blender in Object
        # Mode first.  Merely changing the active object leaves the source in
        # Edit Mode in Blender 5.1, which makes the UI state and subsequent
        # source edits disagree.
        if context.object is not None and context.object.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError as exc:
                self.report({"WARNING"}, "Could not leave the current mode: " + str(exc))
                return {"CANCELLED"}

        if source_obj is not None:
            props = settings_for_source(context.scene, source_obj)
            if props is not None and props.auto_update:
                # Edit-mode changes may still be waiting in the debounce queue
                # when the user switches back to the generated wall.  Flush
                # only that existing queue; Auto Update OFF remains manual.
                from . import flush_pending_updates

                flush_pending_updates()
                wall_obj = get_linked_wall(source_obj) or wall_obj

        ensure_object_in_view_layer(context, wall_obj)
        if source_obj is not None:
            ensure_object_in_view_layer(context, source_obj)
        for selected in list(context.selected_objects):
            selected.select_set(False)
        wall_obj.hide_viewport = False
        wall_obj.hide_set(False)
        wall_obj.select_set(True)
        if source_obj:
            source_obj.select_set(False)
            if props is None or props.hide_source_curve:
                source_obj.hide_viewport = False
                source_obj.hide_set(True)
        context.view_layer.objects.active = wall_obj
        self.report({"INFO"}, "Generated wall is visible.")
        return {"FINISHED"}


def find_wall_pair(obj):
    if obj is None:
        return None, None

    if obj.get("profile_wall_generated"):
        return get_linked_source(obj), obj

    wall_obj = get_linked_wall(obj)
    if wall_obj is not None:
        return obj, wall_obj

    return obj, None


def get_linked_source(wall_obj):
    if wall_obj is None:
        return None
    source_obj = _raw_linked_source(wall_obj)

    # Curve Separate duplicates the source's custom properties. If the copied
    # object already stole ownership in an older add-on version, the generated
    # wall name still usually identifies the original source. Repair that
    # conflict before returning the source used by Edit Source Curve.
    expected_source = _source_from_generated_wall_name(wall_obj)
    if (
        expected_source is not None
        and expected_source != source_obj
        and _source_claims_wall(expected_source, wall_obj)
    ):
        source_obj = expected_source
    elif (
        source_obj is not None
        and not wall_obj.name.startswith(source_obj.name + "_ProfileWall")
    ):
        # Also cover renamed walls/sources. The global candidate scan is only
        # needed for this suspicious name mismatch, not during normal redraws.
        candidates = _sources_claiming_wall(wall_obj)
        if len(candidates) > 1:
            source_obj = _resolve_wall_source_conflict(wall_obj)
    return source_obj


def get_linked_wall(source_obj):
    if source_obj is None:
        return None

    candidates = []
    pointer_wall = getattr(source_obj, "pwg_result_ref", None)
    if pointer_wall is not None:
        candidates.append(pointer_wall)

    wall_name = source_obj.get("profile_wall_result")
    named_wall = bpy.data.objects.get(wall_name) if wall_name else None
    if named_wall is not None and all(named_wall != item for item in candidates):
        candidates.append(named_wall)

    for wall_obj in candidates:
        if _is_valid_wall_link(source_obj, wall_obj):
            return wall_obj

    # This function is also called from Panel.poll(), where Blender forbids ID
    # writes. Leave stale duplicate/deleted links untouched here; operators that
    # actually mutate the wall repair them in a writable execution context.
    return None


def _is_valid_wall_link(source_obj, wall_obj):
    try:
        if bpy.data.objects.get(wall_obj.name) != wall_obj:
            return False
        if not wall_obj.get("profile_wall_generated"):
            return False
        owner = _raw_linked_source(wall_obj)
        if owner is not None and owner != source_obj:
            owner = _resolve_wall_source_conflict(wall_obj, source_obj)
            if owner != source_obj:
                return False
        return any(
            source_scene == wall_scene
            for source_scene in source_obj.users_scene
            for wall_scene in wall_obj.users_scene
        )
    except ReferenceError:
        return False


def _raw_linked_source(wall_obj):
    source_obj = getattr(wall_obj, "pwg_source_ref", None)
    if source_obj is None:
        source_name = wall_obj.get("profile_wall_source")
        source_obj = bpy.data.objects.get(source_name) if source_name else None
    return source_obj


def _source_claims_wall(source_obj, wall_obj):
    if source_obj is None or source_obj.get("profile_wall_generated"):
        return False
    try:
        return (
            getattr(source_obj, "pwg_result_ref", None) == wall_obj
            or source_obj.get("profile_wall_result") == wall_obj.name
        )
    except ReferenceError:
        return False


def _source_from_generated_wall_name(wall_obj):
    marker = "_ProfileWall"
    if marker not in wall_obj.name:
        return None
    source_name = wall_obj.name.split(marker, 1)[0]
    source_obj = bpy.data.objects.get(source_name)
    return source_obj if _source_claims_wall(source_obj, wall_obj) else None


def _sources_claiming_wall(wall_obj):
    candidates = []
    owner = _raw_linked_source(wall_obj)
    if owner is not None:
        candidates.append(owner)
    for obj in bpy.data.objects:
        if _source_claims_wall(obj, wall_obj) and obj not in candidates:
            candidates.append(obj)
    return candidates


def _resolve_wall_source_conflict(wall_obj, requested_source=None):
    candidates = _sources_claiming_wall(wall_obj)
    if len(candidates) <= 1:
        return candidates[0] if candidates else _raw_linked_source(wall_obj)

    expected_source = _source_from_generated_wall_name(wall_obj)
    if expected_source in candidates:
        return expected_source

    # The original object precedes a newly separated object in bpy.data.objects.
    # Use that stable order only for an actual duplicated-link conflict.
    order = {obj: index for index, obj in enumerate(bpy.data.objects)}
    source_obj = min(candidates, key=lambda obj: order.get(obj, len(order)))
    return source_obj


def _repair_wall_source_owner(wall_obj, source_obj, candidates=None):
    if wall_obj.get("profile_wall_source") != source_obj.name:
        wall_obj["profile_wall_source"] = source_obj.name
    if (
        hasattr(wall_obj, "pwg_source_ref")
        and wall_obj.pwg_source_ref != source_obj
    ):
        wall_obj.pwg_source_ref = source_obj

    if candidates is None:
        candidates = _sources_claiming_wall(wall_obj)
    for candidate in candidates:
        if candidate != source_obj:
            _clear_source_wall_link(candidate, wall_obj)
    return source_obj


def _clear_source_wall_link(source_obj, wall_obj=None):
    if source_obj is None:
        return
    pointer_wall = getattr(source_obj, "pwg_result_ref", None)
    named_wall = source_obj.get("profile_wall_result")
    if wall_obj is None or pointer_wall == wall_obj:
        if hasattr(source_obj, "pwg_result_ref"):
            source_obj.pwg_result_ref = None
    if wall_obj is None or named_wall == wall_obj.name:
        if "profile_wall_result" in source_obj:
            del source_obj["profile_wall_result"]


def ensure_object_in_view_layer(context, obj):
    """Make an existing generated wall selectable from the active View Layer."""
    if obj.name in context.view_layer.objects:
        return
    if obj.name not in context.collection.objects:
        context.collection.objects.link(obj)
    context.view_layer.update()


def consume_source_warning(source_obj):
    if source_obj is None:
        return None
    warning = source_obj.get("_profile_wall_warning")
    if warning and "_profile_wall_warning" in source_obj:
        del source_obj["_profile_wall_warning"]
    return warning


def generate_wall_from_source(context, source_obj, props, existing_wall=None):
    if source_obj is None:
        raise path_utils.PathError("Select a curve or mesh line.")

    paths = path_utils.extract_paths(
        source_obj,
        props.merge_distance,
        resolution_mode=getattr(props, "bezier_resolution_mode", "CUSTOM"),
        custom_resolution=getattr(props, "bezier_resolution", 8),
    )
    obj, face_material_keys = mesh_builder.build_profile_wall_paths_object(
        context, source_obj, paths, props, existing_obj=existing_wall
    )
    material_indices = material_utils.prepare_materials(context, obj, props)
    mesh_builder.apply_face_material_indices(obj, material_indices, face_material_keys)
    mesh_builder.add_bevel_modifier(obj, props)
    mesh_builder.apply_smooth_shading(obj, props)

    if not obj.get("profile_wall_generated"):
        obj["profile_wall_generated"] = True
    if obj.get("profile_wall_source") != source_obj.name:
        obj["profile_wall_source"] = source_obj.name
    if obj.get("profile_wall_preset") != props.profile_preset:
        obj["profile_wall_preset"] = props.profile_preset
    if source_obj.get("profile_wall_result") != obj.name:
        source_obj["profile_wall_result"] = obj.name
    if hasattr(obj, "pwg_source_ref") and obj.pwg_source_ref != source_obj:
        obj.pwg_source_ref = source_obj
    if (
        hasattr(source_obj, "pwg_result_ref")
        and source_obj.pwg_result_ref != obj
    ):
        source_obj.pwg_result_ref = obj
    _repair_wall_source_owner(obj, source_obj)
    if (
        hasattr(source_obj, "pwg_settings")
        and props.as_pointer() == source_obj.pwg_settings.as_pointer()
        and not source_obj.pwg_settings_initialized
    ):
        source_obj.pwg_settings_initialized = True

    if existing_wall is None:
        obj.select_set(True)
        source_obj.select_set(False)
        if props.hide_source_curve:
            source_obj.hide_viewport = False
            source_obj.hide_set(True)

    return obj


classes = (
    PROFILE_WALL_OT_generate,
    PROFILE_WALL_OT_update,
    PROFILE_WALL_OT_convert_to_editable,
    PROFILE_WALL_OT_edit_source_curve,
    PROFILE_WALL_OT_show_generated_mesh,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
