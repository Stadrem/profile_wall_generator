import importlib
import sys
from pathlib import Path

import bpy


ADDONS_DIR = Path(__file__).resolve().parents[2]
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import profile_wall_generator as addon


addon.register()
try:
    assert hasattr(bpy.types.Scene, "profile_wall_props")
    assert hasattr(bpy.types.Object, "pwg_settings")

    addon = importlib.reload(addon)
    addon.register()

    assert hasattr(bpy.types.Scene, "profile_wall_props")
    assert hasattr(bpy.types.Object, "pwg_settings")
    assert bpy.context.scene.profile_wall_props is not None
    assert addon.panels.PROFILE_WALL_PT_materials.bl_parent_id == "PROFILE_WALL_PT_panel"
    assert addon.panels.PROFILE_WALL_PT_uv.bl_parent_id == "PROFILE_WALL_PT_panel"
    assert addon.panels.PROFILE_WALL_PT_advanced.bl_parent_id == "PROFILE_WALL_PT_panel"
    assert "DEFAULT_CLOSED" in addon.panels.PROFILE_WALL_PT_materials.bl_options
    assert "DEFAULT_CLOSED" in addon.panels.PROFILE_WALL_PT_uv.bl_options
    assert "DEFAULT_CLOSED" in addon.panels.PROFILE_WALL_PT_advanced.bl_options
    assert addon.operators.settings_for_source(bpy.context.scene, None) is None
    assert sum(
        getattr(handler, "__name__", None) == "profile_wall_auto_update"
        for handler in bpy.app.handlers.depsgraph_update_post
    ) == 1
    assert sum(
        getattr(handler, "__name__", None) == "profile_wall_load_post"
        for handler in bpy.app.handlers.load_post
    ) == 1

    del bpy.types.Scene.profile_wall_props
    assert addon.operators.settings_for_source(bpy.context.scene, None) is None

    print("PWG_RELOAD_REGISTRATION_OK")
finally:
    addon.unregister()
