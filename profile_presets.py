PROFILE_PRESETS = {
    "BASIC_MOLDING": {
        "label": "Basic Molding",
        "description": "Simple top and bottom trim with recessed body",
        "profile": [
            (0.00, 0.08, "trim"),
            (0.20, 0.08, "trim"),
            (0.30, 0.00, "body"),
            (2.70, 0.00, "body"),
            (2.80, 0.08, "trim"),
            (3.00, 0.08, "trim"),
        ],
    },
    "DOUBLE_TRIM": {
        "label": "Double Trim",
        "description": "Prototype preset with an extra middle trim band",
        "profile": [
            (0.00, 0.10, "trim"),
            (0.15, 0.10, "trim"),
            (0.25, 0.03, "body"),
            (1.45, 0.00, "body"),
            (1.60, 0.05, "trim"),
            (1.75, 0.00, "body"),
            (2.75, 0.03, "body"),
            (2.85, 0.10, "trim"),
            (3.00, 0.10, "trim"),
        ],
    },
}


def get_preset(key):
    return PROFILE_PRESETS.get(key) or PROFILE_PRESETS["BASIC_MOLDING"]


def enum_items(self=None, context=None):
    return [
        (key, data["label"], data.get("description", ""))
        for key, data in PROFILE_PRESETS.items()
    ]


def validate_profile(profile):
    if not profile or len(profile) < 2:
        raise ValueError("Profile needs at least two points.")

    last_z = None
    for item in profile:
        if len(item) != 3:
            raise ValueError("Profile items must be (z, offset, material_key).")
        z, _offset, material_key = item
        if last_z is not None and z < last_z:
            raise ValueError("Profile z values must be sorted from bottom to top.")
        if material_key not in {"body", "trim", "cap"}:
            raise ValueError("Unknown material key: " + str(material_key))
        last_z = z
