import trimesh
import pygltflib
import numpy as np
from PIL import Image
import base64
import io
import math
import os


def _as_scene(mesh_or_scene):
    if isinstance(mesh_or_scene, trimesh.Scene):
        return mesh_or_scene.copy()
    scene = trimesh.Scene()
    scene.add_geometry(mesh_or_scene, node_name="Generated_Mesh")
    return scene


def _camera_c2w_matrix(elev=0, azim=0, camera_distance=1.45, center=None):
    elev = -elev
    azim += 90

    elev_rad = math.radians(elev)
    azim_rad = math.radians(azim)

    camera_position = np.array(
        [
            camera_distance * math.cos(elev_rad) * math.cos(azim_rad),
            camera_distance * math.cos(elev_rad) * math.sin(azim_rad),
            camera_distance * math.sin(elev_rad),
        ],
        dtype=np.float32,
    )

    if center is None:
        center = np.array([0, 0, 0], dtype=np.float32)
    else:
        center = np.array(center, dtype=np.float32)

    lookat = center - camera_position
    lookat = lookat / np.linalg.norm(lookat)

    up = np.array([0, 0, 1.0], dtype=np.float32)
    right = np.cross(lookat, up)
    right = right / np.linalg.norm(right)
    up = np.cross(right, lookat)
    up = up / np.linalg.norm(up)

    c2w = np.eye(4, dtype=np.float32)
    c2w[:3, :3] = np.stack([right, up, -lookat], axis=-1)
    c2w[:3, 3] = camera_position
    return c2w


def _create_visible_camera_marker(elev=0, azim=0, camera_distance=1.45, center=None, size=0.18):
    c2w = _camera_c2w_matrix(elev=elev, azim=azim, camera_distance=camera_distance, center=center)

    body = trimesh.creation.box(extents=[size * 0.75, size * 0.45, size * 0.36])
    body.visual.vertex_colors = [30, 30, 30, 255]

    lens_transform = np.eye(4, dtype=np.float32)
    lens_transform[:3, 3] = [0, 0, -size * 0.34]
    lens = trimesh.creation.cone(radius=size * 0.18, height=size * 0.32, sections=24, transform=lens_transform)
    lens.visual.vertex_colors = [70, 120, 220, 255]

    marker = trimesh.util.concatenate([body, lens])
    marker.apply_transform(c2w)
    return marker


def add_visible_camera_marker(mesh_or_scene, elev=0, azim=0, camera_distance=1.45, center=None):
    scene = _as_scene(mesh_or_scene)
    marker = _create_visible_camera_marker(
        elev=elev,
        azim=azim,
        camera_distance=camera_distance,
        center=center,
    )
    scene.add_geometry(marker, node_name="Generated_Camera_Marker", geom_name="Generated_Camera_Marker")
    return scene


def export_glb_with_camera(
    mesh_or_scene,
    output_path,
    include_normals=False,
    elev=0,
    azim=0,
    camera_distance=1.45,
    center=None,
    visible_camera=False,
):
    if visible_camera:
        export_obj = add_visible_camera_marker(
            mesh_or_scene,
            elev=elev,
            azim=azim,
            camera_distance=camera_distance,
            center=center,
        )
    else:
        export_obj = mesh_or_scene

    export_obj.export(output_path, include_normals=include_normals)
    add_camera_to_glb(
        output_path,
        elev=elev,
        azim=azim,
        camera_distance=camera_distance,
        center=center,
    )
    return output_path


def write_houdini_camera_script(
    model_path,
    script_path=None,
    camera_name="Generated_Camera",
    elev=0,
    azim=0,
    camera_distance=1.45,
    center=None,
    yfov=0.857487,
):
    """Write a Houdini Python script that creates a camera from the calculated transform."""
    if script_path is None:
        script_path = os.path.splitext(model_path)[0] + "_houdini_camera.py"

    c2w = _camera_c2w_matrix(elev=elev, azim=azim, camera_distance=camera_distance, center=center)
    matrix_values = c2w.reshape(-1).astype(float).tolist()
    camera_position = c2w[:3, 3].astype(float).tolist()
    if center is None:
        center = [0.0, 0.0, 0.0]
    else:
        center = np.array(center, dtype=np.float32).astype(float).tolist()

    # Houdini's default aperture is 41.4214mm. Compute focal length from vertical FOV.
    aperture = 41.4214
    focal = aperture / (2.0 * math.tan(yfov / 2.0))

    script = f'''# Run this in Houdini's Python Shell, Python Source Editor, or as a shelf tool.
# It creates/updates a real Houdini camera using the Hunyuan render camera transform.
import hou

CAMERA_NAME = {camera_name!r}
MODEL_PATH = {os.path.abspath(model_path)!r}
CAMERA_POSITION = {camera_position!r}
CAMERA_TARGET = {center!r}
CAMERA_WORLD_MATRIX = {matrix_values!r}
CAMERA_YFOV_RAD = {float(yfov)!r}
CAMERA_FOCAL_MM = {float(focal)!r}
CAMERA_APERTURE_MM = {float(aperture)!r}

obj = hou.node("/obj")
cam = obj.node(CAMERA_NAME)
if cam is None:
    cam = obj.createNode("cam", node_name=CAMERA_NAME)

cam.setWorldTransform(hou.Matrix4(CAMERA_WORLD_MATRIX))
cam.parm("focal").set(CAMERA_FOCAL_MM)
cam.parm("aperture").set(CAMERA_APERTURE_MM)
cam.parm("near").set(0.01)
cam.parm("far").set(100.0)

# Optional: keep the source model path on the node for pipeline lookup/debugging.
cam.setUserData("hunyuan_model_path", MODEL_PATH)
cam.setUserData("hunyuan_camera_position", repr(CAMERA_POSITION))
cam.setUserData("hunyuan_camera_target", repr(CAMERA_TARGET))

cam.moveToGoodPosition()
if hasattr(hou, "ui"):
    hou.ui.displayMessage("Created/updated camera: " + cam.path())
else:
    print("Created/updated camera:", cam.path())
'''
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    return script_path


def add_camera_to_glb(
    glb_path,
    elev=0,
    azim=0,
    camera_distance=1.45,
    center=None,
    yfov=0.857487,
    aspect_ratio=1.0,
    znear=0.01,
    zfar=100.0,
):
    """Add a glTF camera node using the renderer's spherical camera math."""
    gltf = pygltflib.GLTF2().load(glb_path)

    if gltf.cameras is None:
        gltf.cameras = []
    if gltf.nodes is None:
        gltf.nodes = []
    if not gltf.scenes:
        gltf.scenes = [pygltflib.Scene(nodes=[])]
        gltf.scene = 0
    if gltf.scene is None or gltf.scene >= len(gltf.scenes):
        gltf.scene = 0
    if gltf.scenes[gltf.scene].nodes is None:
        gltf.scenes[gltf.scene].nodes = []

    camera_index = len(gltf.cameras)
    if hasattr(pygltflib, "PerspectiveCameraInfo"):
        perspective = pygltflib.PerspectiveCameraInfo(
            yfov=yfov,
            aspectRatio=aspect_ratio,
            znear=znear,
            zfar=zfar,
        )
    else:
        perspective = pygltflib.Perspective(
            yfov=yfov,
            aspectRatio=aspect_ratio,
            znear=znear,
            zfar=zfar,
        )

    gltf.cameras.append(
        pygltflib.Camera(
            name="Generated_Camera",
            type="perspective",
            perspective=perspective,
        )
    )

    c2w = _camera_c2w_matrix(elev=elev, azim=azim, camera_distance=camera_distance, center=center)
    node_index = len(gltf.nodes)
    gltf.nodes.append(
        pygltflib.Node(
            name="Generated_Camera",
            camera=camera_index,
            matrix=c2w.T.reshape(-1).astype(float).tolist(),
        )
    )
    gltf.scenes[gltf.scene].nodes.append(node_index)
    gltf.save(glb_path)
    return glb_path


def combine_metallic_roughness(metallic_path, roughness_path, output_path):
    """
    将metallic和roughness贴图合并为一张贴图
    GLB格式要求metallic在B通道，roughness在G通道
    """
    # 加载贴图
    metallic_img = Image.open(metallic_path).convert("L")  # 转为灰度
    roughness_img = Image.open(roughness_path).convert("L")  # 转为灰度

    # 确保尺寸一致
    if metallic_img.size != roughness_img.size:
        roughness_img = roughness_img.resize(metallic_img.size)

    # 创建RGB图像
    width, height = metallic_img.size
    combined = Image.new("RGB", (width, height))

    # 转为numpy数组便于操作
    metallic_array = np.array(metallic_img)
    roughness_array = np.array(roughness_img)

    # 创建合并的数组 (R, G, B) = (AO, Roughness, Metallic)
    combined_array = np.zeros((height, width, 3), dtype=np.uint8)
    combined_array[:, :, 0] = 255  # R通道：AO (如果没有AO贴图，设为白色)
    combined_array[:, :, 1] = roughness_array  # G通道：Roughness
    combined_array[:, :, 2] = metallic_array  # B通道：Metallic

    # 转回PIL图像并保存
    combined = Image.fromarray(combined_array)
    combined.save(output_path)
    return output_path


def create_glb_with_pbr_materials(obj_path, textures_dict, output_path, add_camera=True, visible_camera=False):
    """
    使用pygltflib创建包含完整PBR材质的GLB文件

    textures_dict = {
        'albedo': 'path/to/albedo.png',
        'metallic': 'path/to/metallic.png',
        'roughness': 'path/to/roughness.png',
        'normal': 'path/to/normal.png',  # 可选
        'ao': 'path/to/ao.png'  # 可选
    }
    """
    # 1. 加载OBJ文件
    mesh = trimesh.load(obj_path)
    if visible_camera:
        mesh = add_visible_camera_marker(mesh)

    # 2. 先导出为临时GLB
    temp_glb = "temp.glb"
    mesh.export(temp_glb)

    # 3. 加载GLB文件进行材质编辑
    gltf = pygltflib.GLTF2().load(temp_glb)

    # 4. 准备纹理数据
    def image_to_data_uri(image_path):
        """将图像转换为data URI"""
        with open(image_path, "rb") as f:
            image_data = f.read()
        encoded = base64.b64encode(image_data).decode()
        return f"data:image/png;base64,{encoded}"

    # 5. 合并metallic和roughness
    if "metallic" in textures_dict and "roughness" in textures_dict:
        mr_combined_path = "mr_combined.png"
        combine_metallic_roughness(textures_dict["metallic"], textures_dict["roughness"], mr_combined_path)
        textures_dict["metallicRoughness"] = mr_combined_path

    # 6. 添加图像到GLTF
    images = []
    textures = []

    texture_mapping = {
        "albedo": "baseColorTexture",
        "metallicRoughness": "metallicRoughnessTexture",
        "normal": "normalTexture",
        "ao": "occlusionTexture",
    }

    for tex_type, tex_path in textures_dict.items():
        if tex_type in texture_mapping and tex_path:
            # 添加图像
            image = pygltflib.Image(uri=image_to_data_uri(tex_path))
            images.append(image)

            # 添加纹理
            texture = pygltflib.Texture(source=len(images) - 1)
            textures.append(texture)

    # 7. 创建PBR材质
    pbr_metallic_roughness = pygltflib.PbrMetallicRoughness(
        baseColorFactor=[1.0, 1.0, 1.0, 1.0], metallicFactor=1.0, roughnessFactor=1.0
    )

    # 设置纹理索引
    texture_index = 0
    if "albedo" in textures_dict:
        pbr_metallic_roughness.baseColorTexture = pygltflib.TextureInfo(index=texture_index)
        texture_index += 1

    if "metallicRoughness" in textures_dict:
        pbr_metallic_roughness.metallicRoughnessTexture = pygltflib.TextureInfo(index=texture_index)
        texture_index += 1

    # 创建材质
    material = pygltflib.Material(name="PBR_Material", pbrMetallicRoughness=pbr_metallic_roughness)

    # 添加法线贴图
    if "normal" in textures_dict:
        material.normalTexture = pygltflib.NormalTextureInfo(index=texture_index)
        texture_index += 1

    # 添加AO贴图
    if "ao" in textures_dict:
        material.occlusionTexture = pygltflib.OcclusionTextureInfo(index=texture_index)

    # 8. 更新GLTF
    gltf.images = images
    gltf.textures = textures
    gltf.materials = [material]

    # 确保mesh使用材质
    if gltf.meshes:
        for mesh_obj in gltf.meshes:
            for primitive in mesh_obj.primitives:
                primitive.material = 0

    # 9. 保存最终GLB
    gltf.save(output_path)
    if add_camera:
        add_camera_to_glb(output_path)
        write_houdini_camera_script(output_path)
    print(f"PBR GLB文件已保存: {output_path}")


