def assign_basic_uv(mesh, face_uvs, uv_scale_u=1.0, uv_scale_v=1.0):
    uv_layer = mesh.uv_layers.new(name="ProfileWallUV")
    for polygon, uv_coords in zip(mesh.polygons, face_uvs):
        for loop_index, uv in zip(polygon.loop_indices, uv_coords):
            uv_layer.data[loop_index].uv = (
                uv[0] * uv_scale_u,
                uv[1] * uv_scale_v,
            )
