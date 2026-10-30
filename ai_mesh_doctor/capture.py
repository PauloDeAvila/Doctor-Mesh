"""Disposable diagnostic scene: never changes the user's render settings or materials."""
from dataclasses import dataclass
import math
import time
import hashlib
import json
from array import array
from pathlib import Path
from uuid import uuid4
import bpy
from mathutils import Vector
from .reporting import atomic_json, utc_now
from .identity import measurement_fingerprint


@dataclass(frozen=True)
class CaptureConfig:
    width: int = 960
    height: int = 540
    step_degrees: int = 15
    max_images: int = 128
    wireframe: bool = False
    max_total_vertices: int = 2_000_000
    profile: str = 'full'
    max_seconds: float = 600.0

    def __post_init__(self):
        if not 64 <= self.width <= 1920 or not 64 <= self.height <= 1080:
            raise ValueError("Diagnostic capture resolution outside budget")
        if self.step_degrees < 5 or 360 % self.step_degrees:
            raise ValueError("Step must divide 360 and be at least 5 degrees")
        if self.profile not in {'quick','full'} or not math.isfinite(self.max_seconds) or self.max_seconds <= 0:
            raise ValueError('Valid capture profile and time budget required')


def view_schedule(step=15, profile='full'):
    """Directions are Blender world axes; no unsupported anatomical front inference."""
    views = [(name, Vector(direction), "ORTHO") for name, direction in (
        ("axis_pos_x", (1,0,0)), ("axis_neg_x", (-1,0,0)),
        ("axis_pos_y", (0,1,0)), ("axis_neg_y", (0,-1,0)),
        ("top", (0,0,1)), ("bottom", (0,0,-1)))]
    if profile == 'quick':
        return views + [('diagonal_1_-1_1', Vector((1,-1,1)).normalized(), 'PERSP'),
                        ('diagonal_-1_1_-1', Vector((-1,1,-1)).normalized(), 'PERSP')]
    if profile != 'full':
        raise ValueError('Unknown capture profile')
    for orbit in ("horizontal", "vertical"):
        for angle in range(0, 360, step):
            r = math.radians(angle)
            direction = (math.cos(r), math.sin(r), 0) if orbit == "horizontal" else (math.cos(r), 0, math.sin(r))
            views.append((f"{orbit}_{angle:03}", Vector(direction), "PERSP"))
    for x in (-1,1):
        for y in (-1,1):
            for z in (-1,1):
                views.append((f"diagonal_{x}_{y}_{z}", Vector((x,y,z)).normalized(), "PERSP"))
    return views


class CaptureSession:
    """One render per step on the main thread, with an ownership manifest.

    Quick captures are 16 images and do not replace final 360 evidence. Budgets
    are checked between frames, not a hard interrupt of a running Blender render.
    Temporary Blender datablocks are released at finish. Exported temporary images
    are retained for review and removed only by cleanup_approved().
    """
    def __init__(self, context, target, directory, config=None, scope_objects=None, include_children=False,
                 reviewed_preview=None, require_quality=False):
        self.config = config or CaptureConfig()
        self.started = time.monotonic()
        self._finished = False
        self._signature_entries = []
        if context.mode != "OBJECT" or target.type not in {"MESH", "EMPTY"}:
            raise ValueError("Select a mesh or assembly root in Object Mode")
        self.target_members = {target} if target.type == "MESH" else {o for o in target.children_recursive if o.type == "MESH"}
        if include_children:
            self.target_members.update(o for o in target.children_recursive if o.type == "MESH")
        if not self.target_members:
            raise ValueError("Assembly has no mesh descendants")
        self.scope_objects = list(scope_objects) if scope_objects is not None else list(context.scene.objects)
        if not self.target_members <= set(self.scope_objects):
            raise ValueError("Capture scope must include every target component")
        self.owner = str(uuid4())
        self.directory = Path(directory).resolve()/self.owner
        self.directory.mkdir(parents=True, exist_ok=False)
        self.manifest_path = self.directory/"manifest.json"
        self.scene = None
        self.objects = []
        self.targets = []
        self.meshes = []
        self.cameras = []
        self.jobs = []
        self.position = 0
        self.manifest = {"schema_version": "1.0.0", "owner": self.owner, "target": target.name_full,
                         "created_at": utc_now(), "status": "running", "reviewed": False,
                         "approval": "pending", "files": [], "temporary_datablocks_released": False,
                         "coverage": "Sampled external views; occluded/internal surfaces need targeted inspection"}
        self.manifest["target_members"] = [o.name_full for o in sorted(self.target_members, key=lambda o:o.name_full)]
        self.manifest['profile'] = self.config.profile
        self.manifest['final_coverage'] = self.config.profile == 'full'
        try:
            self._prepare(context, target)
            self.manifest['capture_signature'] = hashlib.sha256(json.dumps(
                sorted(self._signature_entries, key=lambda x:x['name']), sort_keys=True).encode()).hexdigest()
            if reviewed_preview is not None:
                preview = json.loads(Path(reviewed_preview).read_text(encoding='utf-8'))
                if (self.config.profile != 'full' or preview.get('profile') != 'quick'
                        or preview.get('status') != 'complete' or not preview.get('reviewed')
                        or preview.get('capture_signature') != self.manifest['capture_signature']):
                    raise ValueError('A reviewed quick preview of this exact geometry/context is required')
                _validate_capture_files(preview, Path(reviewed_preview).parent)
                self.manifest['reviewed_preview'] = str(Path(reviewed_preview).resolve())
            if require_quality:
                from .quality import audit_component
                reports = [audit_component(obj) for obj in self.targets]
                if any(not row['accepted'] for row in reports):
                    raise ValueError('Geometry quality gate rejected candidate; inspect components before final capture')
                self.manifest['quality_checks'] = [{k:row[k] for k in ('accepted','fingerprint','reasons')} for row in reports]
            self.manifest['prepare_seconds'] = time.monotonic()-self.started
        except Exception:
            self.finish(cancelled=True)
            raise

    def _prepare(self, context, target):
        self.scene = bpy.data.scenes.new(f"MD_CAPTURE_{self.owner}")
        self.scene["mesh_doctor_owner"] = self.owner
        scene = self.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = self.config.width
        scene.render.resolution_y = self.config.height
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_depth = "16"
        scene.render.film_transparent = False
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "SINGLE"
        scene.display.shading.single_color = (0.55, 0.58, 0.62)
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        scene.display.shading.background_type = "WORLD"
        scene.display.shading.background_color = (0.07, 0.07, 0.07)
        scene.display.shading.show_object_outline = self.config.wireframe
        try:
            scene.view_settings.view_transform = "Filmic"
        except TypeError:
            pass
        depsgraph = context.evaluated_depsgraph_get()
        copied_vertices = 0
        for original in self.scope_objects:
            if original.type != "MESH" or (original not in self.target_members and not original.visible_get()):
                continue
            if original != target and (target.get("mesh_doctor_source") == original.name_full or original.get("mesh_doctor_source") == target.name_full):
                continue
            evaluated = original.evaluated_get(depsgraph)
            copied_vertices += len(evaluated.data.vertices)
            if copied_vertices > self.config.max_total_vertices:
                raise ValueError("Capture scene exceeds vertex budget; isolate a smaller assembly")
            mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=False, depsgraph=depsgraph)
            self.meshes.append(mesh)
            normals = array('f', [0]) * (3*len(mesh.corner_normals))
            mesh.corner_normals.foreach_get('vector', normals)
            self._signature_entries.append({'name': original.name_full, 'mesh': measurement_fingerprint(mesh),
                'normals': hashlib.sha256(normals.tobytes()).hexdigest(),
                'matrix': [list(row) for row in evaluated.matrix_world],
                'target': original in self.target_members, 'wireframe': self.config.wireframe})
            obj = bpy.data.objects.new(original.name_full, mesh)
            obj.matrix_world = evaluated.matrix_world.copy()
            obj["mesh_doctor_owner"] = self.owner
            obj.show_wire = self.config.wireframe
            obj.show_all_edges = self.config.wireframe
            # Workbench has an outline but does not guarantee a full wire render.
            scene.collection.objects.link(obj)
            self.objects.append(obj)
            if original in self.target_members:
                self.targets.append(obj)
        if not self.targets:
            raise ValueError("Target unavailable")
        self.target = self.targets[0]
        bounds = [obj.matrix_world @ Vector(p) for obj in self.targets for p in obj.bound_box]
        lower = Vector([min(p[i] for p in bounds) for i in range(3)])
        upper = Vector([max(p[i] for p in bounds) for i in range(3)])
        self.center = (lower+upper)/2
        self.radius = max((p-self.center).length for p in bounds)
        if self.radius <= 1e-10:
            raise ValueError("Target has no measurable extent")
        data = bpy.data.cameras.new(f"MD_CAMERA_{self.owner}")
        self.cameras.append(data)
        camera = bpy.data.objects.new(data.name, data)
        camera["mesh_doctor_owner"] = self.owner
        scene.collection.objects.link(camera)
        self.objects.append(camera)
        scene.camera = camera
        data.lens = 50
        data.dof.use_dof = False
        data.clip_start = max(1e-6, self.radius/1000)
        data.clip_end = self.radius*100
        schedule = view_schedule(self.config.step_degrees, self.config.profile)
        self.jobs = [(mode, view) for mode in ("isolated", "assembled") for view in schedule]
        if len(self.jobs) > self.config.max_images:
            raise ValueError(f"Full coverage needs {len(self.jobs)} images; raise budget or select a coarser step")
        self.manifest["expected_images"] = len(self.jobs)
        if self.config.wireframe:
            for obj in self.objects:
                if obj.type == "MESH":
                    modifier = obj.modifiers.new("Inspection wireframe", "WIREFRAME")
                    modifier.thickness = self.radius*0.003
                    modifier.use_replace = True
                    modifier.use_boundary = True
        self.manifest["wireframe"] = self.config.wireframe

    def step(self):
        if self._finished:
            return False
        if time.monotonic()-self.started > self.config.max_seconds:
            raise TimeoutError('Capture budget exhausted between frames; checkpoint retained')
        if self.position >= len(self.jobs):
            return False
        mode, (label, direction, projection) = self.jobs[self.position]
        scene = self.scene
        for obj in self.objects:
            if obj.type == "MESH":
                obj.hide_render = mode == "isolated" and obj not in self.targets
        camera = scene.camera
        camera.data.type = projection
        aspect = self.config.width/self.config.height
        # Bounding sphere with a margin bounds every orientation, including long parts.
        camera.data.ortho_scale = 2*self.radius*1.15*max(1, aspect)
        half_fov = min(camera.data.angle_x, camera.data.angle_y)/2
        distance = self.radius/max(0.01, math.sin(half_fov))*1.2
        camera.location = self.center + direction.normalized()*distance
        camera.rotation_euler = (self.center-camera.location).to_track_quat("-Z", "Y").to_euler()
        path = self.directory/f"{mode}_{label}.png"
        scene.render.filepath = str(path)
        frame_started = time.monotonic()
        self._render_image()
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError("Blender did not produce the requested capture")
        self.manifest["files"].append({"path": str(path), "classification": "temporary_inspection",
                                       "purpose": f"{mode}:{label}", "projection": projection,
                                       "camera_position": list(camera.location), "direction": list(direction),
                                       "center": list(self.center), "radius": self.radius,
                                       "render_seconds": time.monotonic()-frame_started})
        self.position += 1
        atomic_json(self.manifest_path, self.manifest)
        return self.position < len(self.jobs)

    def _render_image(self):
        bpy.ops.render.render(write_still=True, scene=self.scene.name)

    def finish(self, cancelled=False):
        if self._finished:
            return self.manifest
        for obj in self.objects:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        if self.scene and self.scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(self.scene)
        for mesh in self.meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for camera in self.cameras:
            if camera.users == 0:
                bpy.data.cameras.remove(camera)
        self.manifest["temporary_datablocks_released"] = True
        complete = (len(self.manifest['files']) == self.manifest.get('expected_images', 0)
                    and self.position == len(self.jobs) and bool(self.jobs))
        self.manifest["status"] = "cancelled" if cancelled else "complete" if complete else "incomplete"
        self.manifest['elapsed_seconds'] = time.monotonic()-self.started
        self.objects = []; self.meshes = []; self.cameras = []; self.scene = None
        self._finished = True
        atomic_json(self.manifest_path, self.manifest)
        return self.manifest


def _validate_capture_files(manifest, root):
    root = Path(root).resolve()
    if (manifest.get('status') != 'complete' or root.name != manifest.get('owner')
            or len(manifest.get('files', [])) != manifest.get('expected_images')
            or not manifest.get('files')):
        raise ValueError('Incomplete/unowned capture evidence')
    for entry in manifest['files']:
        path = Path(entry['path']).resolve()
        if path.parent != root or not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing or out-of-scope capture image')


def review_quick_capture(manifest_path, notes):
    """Record a performed technical visual review; never aesthetic approval."""
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('profile') != 'quick' or not str(notes).strip():
        raise ValueError('A quick preview and actual review notes are required')
    _validate_capture_files(manifest, path.parent)
    manifest.update(reviewed=True, review_notes=str(notes), reviewed_at=utc_now())
    atomic_json(path, manifest)
    return manifest


def cleanup_approved(manifest_path, explicit_approval=False):
    import json
    if not explicit_approval:
        raise ValueError("Explicit scope approval required before image cleanup")
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "complete" or manifest_path.parent.name != manifest["owner"]:
        raise ValueError("Incomplete or unowned capture scope")
    root = manifest_path.parent
    for entry in manifest["files"]:
        path = Path(entry["path"]).resolve()
        if path.parent != root or path.suffix != ".png" or entry["classification"] != "temporary_inspection":
            raise ValueError("File outside owned inspection scope")
    for entry in manifest["files"]:
        Path(entry["path"]).unlink(missing_ok=True)
        entry["removed_after_approval"] = True
    manifest["approval"] = "approved"
    manifest["cleaned_at"] = utc_now()
    atomic_json(manifest_path, manifest)
    return manifest
