import bpy

from . import operators


def _source_path_kinds(source_obj):
    """Return whether the selected source contains closed and open paths."""
    if source_obj is None:
        return False, False
    if source_obj.type == "CURVE":
        states = [bool(spline.use_cyclic_u) for spline in source_obj.data.splines]
        return any(states), any(not state for state in states)
    if source_obj.type == "MESH" and source_obj.data.edges:
        degrees = {}
        for edge in source_obj.data.edges:
            for vertex_index in edge.vertices:
                degrees[vertex_index] = degrees.get(vertex_index, 0) + 1
        closed = bool(degrees) and all(degree == 2 for degree in degrees.values())
        return closed, not closed
def _has_bezier_splines(source_obj):
    """Return whether the selected source contains any Bezier splines."""
    if source_obj is not None and source_obj.type == "CURVE":
        return any(spline.type == "BEZIER" for spline in source_obj.data.splines)
    return False


def _panel_state(context):
    active = context.active_object
    source_ready = bool(
        active
        and active.type in {"CURVE", "MESH"}
        and not active.get("profile_wall_generated")
    )
    generated_ready = bool(
        active and active.type == "MESH" and active.get("profile_wall_generated")
    )
    linked_wall_ready = bool(source_ready and operators.get_linked_wall(active))
    linked_source = operators.get_linked_source(active) if generated_ready else None
    linked_source_ready = bool(linked_source)
    settings_source = active if source_ready else linked_source
    props = (
        operators.settings_for_source(context.scene, settings_source)
        if settings_source is not None
        else None
    )
    return {
        "source_ready": source_ready,
        "generated_ready": generated_ready,
        "linked_wall_ready": linked_wall_ready,
        "linked_source_ready": linked_source_ready,
        "settings_source": settings_source,
        "props": props,
    }


class PROFILE_WALL_PT_panel(bpy.types.Panel):
    bl_label = "Profile Wall Generator"
    bl_idname = "PROFILE_WALL_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "K-Quick Tools"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.label(text="", icon="MOD_SOLIDIFY")

    def draw(self, context):
        layout = self.layout
        state = _panel_state(context)
        source_ready = state["source_ready"]
        generated_ready = state["generated_ready"]
        linked_wall_ready = state["linked_wall_ready"]
        linked_source_ready = state["linked_source_ready"]
        settings_source = state["settings_source"]
        props = state["props"]

        if settings_source is not None and props is not None:
            layout.label(
                text="Settings: " + settings_source.name,
                icon="CURVE_DATA" if settings_source.type == "CURVE" else "MESH_DATA",
            )
        elif settings_source is not None:
            layout.label(text="Settings unavailable. Reload the add-on.", icon="ERROR")
        else:
            layout.label(text="Select a source or generated wall.", icon="INFO")

        # Keep the context-relevant actions visible before the long settings
        # list. Do not spend panel height on disabled operators.
        if source_ready and not linked_wall_ready:
            row = layout.row()
            row.scale_y = 1.4
            row.operator("profile_wall.generate", icon="PLAY")
        elif generated_ready or linked_wall_ready:
            row = layout.row()
            row.scale_y = 1.4
            row.operator("profile_wall.update", icon="FILE_REFRESH")

        if linked_source_ready or linked_wall_ready:
            row = layout.row(align=True)
            if linked_source_ready:
                row.operator("profile_wall.edit_source_curve", icon="CURVE_DATA")
            if linked_wall_ready:
                row.operator("profile_wall.show_generated_mesh", icon="MESH_DATA")

        if generated_ready:
            layout.operator("profile_wall.convert_to_editable", icon="MESH_DATA")

        if props is not None:
            row = layout.row(align=True)
            row.prop(props, "auto_update", text="Auto Update")
            row.prop(props, "hide_source_curve", text="Hide Source")

            has_closed_path, _has_open_path = _source_path_kinds(settings_source)
            interior_mode = props.interior_mode

            box = layout.box()
            box.use_property_split = True
            box.use_property_decorate = False
            box.label(text="Geometry", icon="MOD_BUILD")
            box.prop(props, "profile_preset")
            box.prop(props, "height_scale")
            box.prop(props, "bottom_trim_scale")
            box.prop(props, "top_trim_scale")
            box.prop(props, "offset_scale")
            box.prop(props, "flip_direction")
            if interior_mode != "SOLID":
                box.separator()
                box.label(text="Thickness")
                box.prop(props, "wall_thickness")
                if props.wall_thickness > 0.0:
                    box.prop(props, "thickness_direction", text="Direction")
                    box.prop(props, "flat_inner_face")

            box = layout.box()
            box.label(text="Interior", icon="MESH_PLANE")
            row = box.row(align=True)
            row.use_property_split = False
            row.prop(props, "interior_mode", expand=True)
            if interior_mode in {"SECTION", "SOLID"} and not has_closed_path:
                row = box.row()
                row.alert = True
                row.label(text="Closed source required", icon="ERROR")
            if interior_mode == "SECTION":
                row = box.row()
                row.enabled = props.wall_thickness > 0.0 and has_closed_path
                row.prop(props, "section_height")
                if props.wall_thickness <= 0.0:
                    row = box.row()
                    row.alert = True
                    row.label(text="Wall Thickness must be above 0", icon="ERROR")

            # Less frequently edited controls live in the collapsible child
            # panels below this main panel.


class PROFILE_WALL_PT_materials(bpy.types.Panel):
    bl_label = "Materials"
    bl_idname = "PROFILE_WALL_PT_materials"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "K-Quick Tools"
    bl_parent_id = "PROFILE_WALL_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    @classmethod
    def poll(cls, context):
        return _panel_state(context)["props"] is not None

    def draw_header(self, context):
        self.layout.label(text="", icon="MATERIAL")

    def draw(self, context):
        props = _panel_state(context)["props"]
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(props, "body_material")
        layout.prop(props, "trim_material")
        layout.prop(props, "top_material")
        if props.interior_mode == "SECTION":
            layout.prop(props, "section_material")


class PROFILE_WALL_PT_uv(bpy.types.Panel):
    bl_label = "UV"
    bl_idname = "PROFILE_WALL_PT_uv"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "K-Quick Tools"
    bl_parent_id = "PROFILE_WALL_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 2

    @classmethod
    def poll(cls, context):
        return _panel_state(context)["props"] is not None

    def draw_header(self, context):
        self.layout.label(text="", icon="GROUP_UVS")

    def draw(self, context):
        props = _panel_state(context)["props"]
        row = self.layout.row(align=True)
        row.prop(props, "uv_scale_u")
        row.prop(props, "uv_scale_v")
        if props.interior_mode == "SECTION":
            self.layout.prop(props, "section_uv_scale")


class PROFILE_WALL_PT_advanced(bpy.types.Panel):
    bl_label = "Advanced"
    bl_idname = "PROFILE_WALL_PT_advanced"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "K-Quick Tools"
    bl_parent_id = "PROFILE_WALL_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 3

    @classmethod
    def poll(cls, context):
        return _panel_state(context)["props"] is not None

    def draw_header(self, context):
        self.layout.label(text="", icon="PREFERENCES")

    def draw(self, context):
        state = _panel_state(context)
        props = state["props"]
        _has_closed_path, has_open_path = _source_path_kinds(state["settings_source"])
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        if has_open_path:
            layout.prop(props, "cap_ends")
        layout.prop(props, "miter_limit")
        layout.prop(props, "merge_distance")
        if _has_bezier_splines(state["settings_source"]):
            layout.prop(props, "bezier_resolution_mode", text="Resolution")
            if props.bezier_resolution_mode == "CUSTOM":
                layout.prop(props, "bezier_resolution", text="Segments")
        layout.prop(props, "shade_smooth")
        if props.shade_smooth:
            layout.prop(props, "smooth_angle")
        layout.prop(props, "add_bevel")
        if props.add_bevel:
            layout.prop(props, "bevel_width")
            layout.prop(props, "bevel_segments")


classes = (
    PROFILE_WALL_PT_panel,
    PROFILE_WALL_PT_materials,
    PROFILE_WALL_PT_uv,
    PROFILE_WALL_PT_advanced,
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
