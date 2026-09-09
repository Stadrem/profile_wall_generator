import bpy
from pathlib import Path


MATERIAL_KEYS = ("body", "trim", "top", "section")
SECTION_TEXTURE_PATH = (
    Path(__file__).resolve().parent / "Textures" / "Mat_Stripes_Base_color.png"
)
SECTION_IMAGE_NODE_NAME = "PWG Section Base Color"
DEFAULT_BASE_COLORS = {
    "PWG_Body": "C0C0C0FF",
    "PWG_Trim": "5886E7FF",
    "PWG_Top": "FFFFFFFF",
}
DEFAULT_COLOR_MARKER = "pwg_default_base_color"


def _srgb_channel_to_scene_linear(value):
    value = value / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def hex_rgba_to_scene_linear(hex_rgba):
    value = hex_rgba.lstrip("#")
    if len(value) != 8:
        raise ValueError("Expected an 8-digit RGBA hex color.")
    channels = [int(value[index:index + 2], 16) for index in range(0, 8, 2)]
    return (
        _srgb_channel_to_scene_linear(channels[0]),
        _srgb_channel_to_scene_linear(channels[1]),
        _srgb_channel_to_scene_linear(channels[2]),
        channels[3] / 255.0,
    )


def get_or_create_material(name, color):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        material.diffuse_color = color
    return material


def configure_default_base_color(material):
    hex_rgba = DEFAULT_BASE_COLORS.get(material.name)
    if hex_rgba is None or material.get(DEFAULT_COLOR_MARKER) == hex_rgba:
        return False

    material.use_nodes = True
    principled = next(
        (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
        None,
    )
    if principled is None:
        return False
    base_color = principled.inputs.get("Base Color")
    if base_color is None or base_color.is_linked:
        return False

    color = hex_rgba_to_scene_linear(hex_rgba)
    material.diffuse_color = color
    base_color.default_value = color
    material[DEFAULT_COLOR_MARKER] = hex_rgba
    return True


def configure_default_section_material(material):
    """Add the bundled stripe texture without replacing a custom Base Color link."""
    if material is None or material.name != "PWG_Section":
        return False
    if not SECTION_TEXTURE_PATH.is_file():
        print("Profile Wall Generator: missing Section texture:", SECTION_TEXTURE_PATH)
        return False

    material.use_nodes = True
    node_tree = material.node_tree
    principled = next(
        (node for node in node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
        None,
    )
    if principled is None:
        return False
    base_color = principled.inputs.get("Base Color")
    if base_color is None:
        return False

    # Respect any material editing the user has already done.
    if base_color.is_linked:
        return False

    image = bpy.data.images.load(str(SECTION_TEXTURE_PATH), check_existing=True)
    image_node = node_tree.nodes.get(SECTION_IMAGE_NODE_NAME)
    if image_node is None or image_node.type != "TEX_IMAGE":
        image_node = node_tree.nodes.new("ShaderNodeTexImage")
        image_node.name = SECTION_IMAGE_NODE_NAME
        image_node.label = "Section Base Color"
    image_node.image = image
    image_node.extension = "REPEAT"
    image_node.location = (principled.location.x - 320.0, principled.location.y + 120.0)
    node_tree.links.new(image_node.outputs["Color"], base_color)
    return True


def prepare_materials(context, obj, props):
    body = props.body_material or get_or_create_material(
        "PWG_Body", hex_rgba_to_scene_linear(DEFAULT_BASE_COLORS["PWG_Body"])
    )
    trim = props.trim_material or get_or_create_material(
        "PWG_Trim", hex_rgba_to_scene_linear(DEFAULT_BASE_COLORS["PWG_Trim"])
    )
    top = props.top_material or get_or_create_material(
        "PWG_Top", hex_rgba_to_scene_linear(DEFAULT_BASE_COLORS["PWG_Top"])
    )
    section = props.section_material or get_or_create_material(
        "PWG_Section", (0.34, 0.26, 0.18, 1.0)
    )
    configure_default_section_material(section)
    configure_default_base_color(body)
    configure_default_base_color(trim)
    configure_default_base_color(top)

    # Keep the source object's Material UI in sync with the defaults placed on
    # the generated mesh. Only empty fields are filled; custom choices remain
    # untouched. Suppression avoids recursively invoking Auto Update.
    from . import properties

    with properties.suspend_setting_updates():
        if props.body_material is None:
            props.body_material = body
        if props.trim_material is None:
            props.trim_material = trim
        if props.top_material is None:
            props.top_material = top
        if props.section_material is None:
            props.section_material = section

    obj.data.materials.clear()
    obj.data.materials.append(body)
    obj.data.materials.append(trim)
    obj.data.materials.append(top)
    obj.data.materials.append(section)

    return {
        "body": 0,
        "trim": 1,
        "top": 2,
        "section": 3,
        # Backward compatibility for any legacy/custom profile using "cap".
        "cap": 0,
    }
