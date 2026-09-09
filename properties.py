import bpy
from contextlib import contextmanager

from . import profile_presets


SETTING_FIELDS = (
    "profile_preset",
    "wall_thickness",
    "thickness_direction",
    "height_scale",
    "bottom_trim_scale",
    "top_trim_scale",
    "offset_scale",
    "flat_inner_face",
    "miter_limit",
    "fill_inside",
    "generate_section",
    "section_height",
    "flip_direction",
    "cap_ends",
    "merge_distance",
    "uv_scale_u",
    "uv_scale_v",
    "section_uv_scale",
    "bezier_resolution_mode",
    "bezier_resolution",
    "shade_smooth",
    "smooth_angle",
    "add_bevel",
    "bevel_width",
    "bevel_segments",
    "auto_update",
    "hide_source_curve",
    "body_material",
    "trim_material",
    "top_material",
    "section_material",
)


_suspend_setting_updates = False
_setting_update_in_progress = False


@contextmanager
def suspend_setting_updates():
    """Temporarily prevent property assignments from rebuilding the wall."""
    global _suspend_setting_updates
    previous_value = _suspend_setting_updates
    _suspend_setting_updates = True
    try:
        yield
    finally:
        _suspend_setting_updates = previous_value


def _get_interior_mode(self):
    # Derive the UI mode from the existing stored booleans so older .blend
    # files keep their Fill Inside / Generate Section state automatically.
    if self.fill_inside:
        return 2
    if self.generate_section:
        return 1
    return 0


def _set_interior_mode(self, value):
    global _suspend_setting_updates
    previous_value = _suspend_setting_updates
    _suspend_setting_updates = True
    try:
        self.fill_inside = value == 2
        self.generate_section = value == 1
    finally:
        _suspend_setting_updates = previous_value

    if not previous_value:
        _auto_update_setting(self, bpy.context)


def _auto_update_setting(self, context):
    global _setting_update_in_progress
    if _suspend_setting_updates or _setting_update_in_progress:
        return

    source_obj = getattr(self, "id_data", None)
    if not isinstance(source_obj, bpy.types.Object):
        return
    if source_obj.get("profile_wall_generated") or not self.auto_update:
        return

    from . import operators

    wall_obj = operators.get_linked_wall(source_obj)
    if wall_obj is None:
        return

    _setting_update_in_progress = True
    try:
        operators.generate_wall_from_source(
            context or bpy.context,
            source_obj,
            self,
            existing_wall=wall_obj,
        )
    except Exception as exc:
        source_obj["_profile_wall_warning"] = str(exc)
        print("Profile Wall Setting Auto-Update Error:", exc)
    finally:
        _setting_update_in_progress = False


class PWG_Properties(bpy.types.PropertyGroup):
    interior_mode: bpy.props.EnumProperty(
        name="Interior",
        items=(
            ("HOLLOW", "Hollow", "Generate a hollow wall without an interior floor"),
            ("SECTION", "Section", "Generate a hollow wall with an interior Section floor"),
            ("SOLID", "Solid", "Fill a closed curve as a solid block"),
        ),
        get=_get_interior_mode,
        set=_set_interior_mode,
    )
    profile_preset: bpy.props.EnumProperty(
        name="Preset",
        items=profile_presets.enum_items(),
        default="BASIC_MOLDING",
        description="Wall profile preset",
        update=_auto_update_setting,
    )
    wall_thickness: bpy.props.FloatProperty(
        name="Wall Thickness",
        default=0.5,
        min=0.0,
        soft_max=1.0,
        unit="LENGTH",
        description="Wall thickness generated as double-sided mesh",
        update=_auto_update_setting,
    )
    thickness_direction: bpy.props.EnumProperty(
        name="Thickness Direction",
        items=(
            ("OUTSIDE", "Outside", "Solidify outward"),
            ("INSIDE", "Inside", "Solidify inward"),
            ("CENTER", "Center", "Solidify around the profile surface"),
        ),
        default="OUTSIDE",
        update=_auto_update_setting,
    )
    height_scale: bpy.props.FloatProperty(
        name="Height Scale",
        default=1.0,
        min=0.001,
        soft_max=5.0,
        update=_auto_update_setting,
    )
    bottom_trim_scale: bpy.props.FloatProperty(
        name="Bottom Trim Scale",
        default=0.25,
        min=0.0,
        soft_max=5.0,
        description="Scale the height of the bottom trim",
        update=_auto_update_setting,
    )
    top_trim_scale: bpy.props.FloatProperty(
        name="Top Trim Scale",
        default=0.25,
        min=0.0,
        soft_max=5.0,
        description="Scale the height of the top trim",
        update=_auto_update_setting,
    )
    offset_scale: bpy.props.FloatProperty(
        name="Offset Scale",
        default=0.0,
        min=0.0,
        soft_max=5.0,
        update=_auto_update_setting,
    )
    flat_inner_face: bpy.props.BoolProperty(
        name="Flat Inner Face",
        default=True,
        description="Keep the back side of the wall flat while applying the molding profile only to the visible side",
        update=_auto_update_setting,
    )
    miter_limit: bpy.props.FloatProperty(
        name="Miter Limit",
        default=3.0,
        min=1.0,
        soft_max=10.0,
        description="Limit the extent of the miter corner offset",
        update=_auto_update_setting,
    )
    fill_inside: bpy.props.BoolProperty(
        name="Fill Inside (Solid Block)",
        default=False,
        description="For closed curves, generate a solid block by capping the top and bottom instead of generating a hollow wall",
        update=_auto_update_setting,
    )
    generate_section: bpy.props.BoolProperty(
        name="Generate Section",
        default=False,
        description="For closed hollow walls, generate an interior floor section",
        update=_auto_update_setting,
    )
    section_height: bpy.props.FloatProperty(
        name="Section Z Offset",
        default=0.2,
        min=0.0,
        soft_max=10.0,
        unit="LENGTH",
        description="Height of the Section floor above the bottom of the wall",
        update=_auto_update_setting,
    )
    flip_direction: bpy.props.BoolProperty(
        name="Flip Direction",
        default=False,
        description="Reverse profile offset direction",
        update=_auto_update_setting,
    )
    cap_ends: bpy.props.BoolProperty(
        name="Cap Ends",
        default=True,
        description="Fill both ends for open curves",
        update=_auto_update_setting,
    )
    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        default=0.001,
        min=0.0,
        precision=4,
        unit="LENGTH",
        update=_auto_update_setting,
    )
    uv_scale_u: bpy.props.FloatProperty(
        name="U Scale",
        default=1.0,
        min=0.0001,
        soft_max=10.0,
        update=_auto_update_setting,
    )
    uv_scale_v: bpy.props.FloatProperty(
        name="V Scale",
        default=1.0,
        min=0.0001,
        soft_max=10.0,
        update=_auto_update_setting,
    )
    section_uv_scale: bpy.props.FloatProperty(
        name="Section UV Scale",
        default=1.0,
        min=0.0001,
        soft_max=10.0,
        description="Additional uniform UV scale applied only to the Section floor",
        update=_auto_update_setting,
    )
    bezier_resolution_mode: bpy.props.EnumProperty(
        name="Resolution Mode",
        items=(
            ("CUSTOM", "Custom", "Use custom segment sampling resolution"),
            ("CURVE", "Use Curve", "Use resolution_u from the source curve"),
        ),
        default="CUSTOM",
        update=_auto_update_setting,
    )
    bezier_resolution: bpy.props.IntProperty(
        name="Resolution",
        default=8,
        min=1,
        soft_max=64,
        max=256,
        description="Sampling resolution per Bezier spline segment",
        update=_auto_update_setting,
    )
    shade_smooth: bpy.props.BoolProperty(
        name="Shade Smooth",
        default=False,
        description="Enable angle-based smooth shading on the generated wall",
        update=_auto_update_setting,
    )
    smooth_angle: bpy.props.FloatProperty(
        name="Smooth Angle",
        default=0.523599,  # 30 degrees
        min=0.0,
        max=3.141593,
        subtype="ANGLE",
        unit="ROTATION",
        description="Maximum angle between face normals to treat as smooth",
        update=_auto_update_setting,
    )
    add_bevel: bpy.props.BoolProperty(
        name="Add Bevel",
        default=False,
        description="Add an optional angle-limited bevel modifier",
        update=_auto_update_setting,
    )
    bevel_width: bpy.props.FloatProperty(
        name="Bevel Width",
        default=0.01,
        min=0.0,
        soft_max=0.2,
        unit="LENGTH",
        update=_auto_update_setting,
    )
    bevel_segments: bpy.props.IntProperty(
        name="Bevel Segments",
        default=1,
        min=1,
        soft_max=8,
        max=16,
        description="Number of segments for the bevel modifier",
        update=_auto_update_setting,
    )
    auto_update: bpy.props.BoolProperty(
        name="Auto Update",
        default=False,
        description="Automatically update the generated wall when its settings or source geometry changes",
        update=_auto_update_setting,
    )
    hide_source_curve: bpy.props.BoolProperty(
        name="Hide Source Curve",
        default=True,
        update=_auto_update_setting,
    )
    body_material: bpy.props.PointerProperty(
        name="Body",
        type=bpy.types.Material,
        description="Material for recessed wall body",
        update=_auto_update_setting,
    )
    trim_material: bpy.props.PointerProperty(
        name="Trim",
        type=bpy.types.Material,
        description="Material for top and bottom trim",
        update=_auto_update_setting,
    )
    top_material: bpy.props.PointerProperty(
        name="Top",
        type=bpy.types.Material,
        description="Material for the upward-facing top surface",
        update=_auto_update_setting,
    )
    section_material: bpy.props.PointerProperty(
        name="Section",
        type=bpy.types.Material,
        description="Material for the interior Section floor",
        update=_auto_update_setting,
    )


classes = (PWG_Properties,)


def copy_settings(source, target):
    with suspend_setting_updates():
        for field in SETTING_FIELDS:
            setattr(target, field, getattr(source, field))


def migrate_legacy_scene_settings():
    """Copy the former Scene-wide settings to already-linked source objects."""
    scenes = getattr(bpy.data, "scenes", None)
    if scenes is None:
        # During add-on startup Blender exposes _RestrictData. Migration is
        # retried by the add-on's persistent load_post handler.
        return False

    for scene in scenes:
        legacy_settings = getattr(scene, "profile_wall_props", None)
        if legacy_settings is None:
            continue
        for source_obj in scene.objects:
            if source_obj.get("profile_wall_generated"):
                continue
            if getattr(source_obj, "pwg_settings_initialized", False):
                continue
            has_wall_link = bool(
                source_obj.get("profile_wall_result")
                or getattr(source_obj, "pwg_result_ref", None)
            )
            if not has_wall_link:
                continue
            copy_settings(legacy_settings, source_obj.pwg_settings)
            source_obj.pwg_settings_initialized = True
    return True


def register():
    if hasattr(bpy.types.Scene, "profile_wall_props"):
        del bpy.types.Scene.profile_wall_props
    if hasattr(bpy.types.Object, "pwg_source_ref"):
        del bpy.types.Object.pwg_source_ref
    if hasattr(bpy.types.Object, "pwg_result_ref"):
        del bpy.types.Object.pwg_result_ref
    if hasattr(bpy.types.Object, "pwg_settings"):
        del bpy.types.Object.pwg_settings
    if hasattr(bpy.types.Object, "pwg_settings_initialized"):
        del bpy.types.Object.pwg_settings_initialized
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.profile_wall_props = bpy.props.PointerProperty(type=PWG_Properties)
    bpy.types.Object.pwg_source_ref = bpy.props.PointerProperty(
        name="Profile Wall Source",
        type=bpy.types.Object,
        description="Source object used to generate this profile wall",
    )
    bpy.types.Object.pwg_result_ref = bpy.props.PointerProperty(
        name="Profile Wall Result",
        type=bpy.types.Object,
        description="Generated profile wall linked to this source object",
    )
    bpy.types.Object.pwg_settings = bpy.props.PointerProperty(
        name="Profile Wall Settings",
        type=PWG_Properties,
        description="Profile Wall Generator settings stored on this source object",
    )
    bpy.types.Object.pwg_settings_initialized = bpy.props.BoolProperty(
        name="Profile Wall Settings Initialized",
        default=False,
        options={"HIDDEN"},
    )


def unregister():
    if hasattr(bpy.types.Object, "pwg_settings_initialized"):
        del bpy.types.Object.pwg_settings_initialized
    if hasattr(bpy.types.Object, "pwg_settings"):
        del bpy.types.Object.pwg_settings
    if hasattr(bpy.types.Object, "pwg_result_ref"):
        del bpy.types.Object.pwg_result_ref
    if hasattr(bpy.types.Object, "pwg_source_ref"):
        del bpy.types.Object.pwg_source_ref
    if hasattr(bpy.types.Scene, "profile_wall_props"):
        del bpy.types.Scene.profile_wall_props
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
