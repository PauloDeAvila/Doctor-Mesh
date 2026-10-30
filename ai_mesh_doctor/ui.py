import logging
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import bpy
from bpy.props import BoolProperty, StringProperty, FloatProperty, IntProperty, PointerProperty, EnumProperty
from .config import InspectionConfig
from .scanner import ProjectScanner
from .reporting import atomic_json
from .policy import skill_manifest

logger = logging.getLogger(__package__)
_active_job = None
_last_report = None
_transaction = None
_reconstruction = None


class MD_Settings(bpy.types.PropertyGroup):
    output_directory: StringProperty(name="Reports", subtype="DIR_PATH", default="//mesh_doctor_reports")
    distance_tolerance: FloatProperty(name="Distance tolerance (world units)", default=1e-6, min=1e-12, precision=6)
    max_vertices: IntProperty(name="Vertices per mesh", default=250000, min=1)
    max_seconds: FloatProperty(name="Time budget (seconds)", default=120, min=1)
    evaluated: BoolProperty(name="Inspect evaluated geometry", default=True)
    status: StringProperty(default="Ready — inspection only")
    last_report: StringProperty(subtype="FILE_PATH")
    model: StringProperty(name="OpenAI model", default="")
    network_enabled: BoolProperty(name="Allow sending diagnostic data to OpenAI", default=False)
    api_budget: FloatProperty(name="Maximum USD per diagnosis", default=0.25, min=0.001)
    input_price: FloatProperty(name="Verified USD / 1M input tokens", default=0, min=0)
    output_price: FloatProperty(name="Verified USD / 1M output tokens", default=0, min=0)
    stage: EnumProperty(name="Stage", items=[(v,v.title(),"") for v in ("overview", "component", "region", "planning")])
    ai_images: StringProperty(name="Image paths (JSON list)", default="[]")
    references: StringProperty(name="Reference paths (JSON list)", default="[]")
    design_constraints: StringProperty(name="Design constraints", default="Preserve functional parts; no arbitrary caps")
    operation: EnumProperty(name="Operation", items=[(v,v.replace("_"," ").title(),"") for v in
        ("recalculate_normals", "merge_vertices", "remove_loose", "fit_plane", "smooth_local", "relax_local")])
    whole_component: BoolProperty(name="Use whole active component", default=False)
    region_indices: StringProperty(name="Base vertex indices (JSON)", default="[]")
    max_displacement: FloatProperty(name="Max displacement (world units)", default=0.001, min=0)
    max_dimension_delta: FloatProperty(name="Max dimension change", default=0.001, min=0)
    max_topology_delta: IntProperty(name="Max changed elements", default=0, min=0, max=10000)
    strength: FloatProperty(name="Correction strength", default=0.2, min=0.001, max=1)
    iterations: IntProperty(name="Iterations", default=1, min=1, max=20)
    plan_path: StringProperty(name="Repair plan", subtype="FILE_PATH")
    reconstruction_spec: StringProperty(name="Measured specification", subtype="FILE_PATH")
    capture_manifest: StringProperty(name="Capture manifest", subtype="FILE_PATH")
    reviewed_capture_manifests: StringProperty(name="Before/after manifests (JSON list)", default="[]")
    component_approval: BoolProperty(name="I approve this preview and its measured scope", default=False)
    uv_loss_approval: BoolProperty(name="Replacement UVs/material mapping reviewed", default=False)
    wireframe: BoolProperty(name="Wireframe diagnostic captures", default=False)
    reuse_measurements: BoolProperty(name="Reuse unchanged measurements", default=True)
    capture_profile: EnumProperty(name="Inspection", items=[('quick','Quick preview (16 images)','Check each attempt'),
        ('full','Final 360 inspection (124 images)','Stable geometry after quick review')], default='quick')
    capture_children: BoolProperty(name="Include component children", default=True)
    quick_preview_manifest: StringProperty(name="Quick preview", subtype='FILE_PATH')
    quick_review_notes: StringProperty(name="Technical review notes", default='')
    knowledge_family: StringProperty(name="Recipe family", default="revolved_profile")
    knowledge_parameters: StringProperty(name="Measured recipe parameters (JSON)", default="{}")
    knowledge_units: StringProperty(name="Recipe units", default="world_blender_units")


class MD_OT_scan(bpy.types.Operator):
    bl_idname = "mesh_doctor.scan"
    bl_label = "Scan Entire Project"
    bl_description = "Inspect the active scene; writes a report without repairing geometry"
    selected_only: BoolProperty(default=False)
    _timer = None
    _scanner = None

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and _active_job is None

    def execute(self, context):
        global _active_job
        settings = context.scene.mesh_doctor
        try:
            self._scanner = ProjectScanner(context, self.selected_only, InspectionConfig(
                distance_tolerance=settings.distance_tolerance,
                area_tolerance=settings.distance_tolerance**2,
                max_vertices=settings.max_vertices, inspect_evaluated=settings.evaluated,
                max_seconds=settings.max_seconds),
                cache_directory=_directory(context)/'measurement_cache' if settings.reuse_measurements else None)
            self._scene = context.scene
            self._settings = settings
            _active_job = self
            context.window_manager.progress_begin(0, max(1, self._scanner.total))
            self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
            context.window_manager.modal_handler_add(self)
            settings.status = "Scanning — Esc cancels"
            return {"RUNNING_MODAL"}
        except Exception as exc:
            _active_job = None
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, True)
        if event.type != "TIMER" or event.timer != self._timer:
            return {"PASS_THROUGH"}
        try:
            if context.scene != self._scene or context.mode != "OBJECT":
                return self._finish(context, True)
            more = self._scanner.step()
            context.window_manager.progress_update(self._scanner.position)
            self._settings.status = f"Scanned {self._scanner.position}/{self._scanner.total} — Esc cancels"
            if context.area:
                context.area.tag_redraw()
            return {"RUNNING_MODAL"} if more else self._finish(context, False)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            self._release(context)
            return {"CANCELLED"}

    def _release(self, context):
        global _active_job
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.window_manager.progress_end()
        _active_job = None

    def cancel(self, context):
        self._release(context)

    def _finish(self, context, cancelled):
        global _last_report
        try:
            report = self._scanner.finish(cancelled)
            _last_report = report
            directory = Path(bpy.path.abspath(self._settings.output_directory)).resolve()
            if not bpy.data.filepath and self._settings.output_directory.startswith("//"):
                directory = Path(bpy.utils.user_resource("DATAFILES", path="mesh_doctor/reports", create=True))
            path = directory / f"inspection-{report['session_id']}.json"
            atomic_json(path, report)
            try:
                _record_event(context, "inspection", "active_scene", "deterministic_scan",
                    {"objects": report["summary"]["objects"]}, report["config"], [str(path)],
                    ["Scan completed"] if report["status"] == "complete" else [])
            except Exception as exc:
                logger.warning("Knowledge recording failed: %s", type(exc).__name__)
            self._settings.last_report = str(path)
            self._settings.status = f"{report['status']}: {report['summary']['mesh_objects']} meshes, {report['summary']['base_findings']} findings"
            self.report({"INFO"}, self._settings.status)
        finally:
            self._release(context)
        return {"CANCELLED"} if cancelled else {"FINISHED"}


class MD_OT_skills(bpy.types.Operator):
    bl_idname = "mesh_doctor.export_skills"
    bl_label = "Export Construction Policy + Skills"

    def execute(self, context):
        try:
            path = Path(bpy.utils.user_resource("DATAFILES", path="mesh_doctor", create=True)) / "skill_manifest.json"
            atomic_json(path, skill_manifest(Path.home()/".codex/skills"))
            self.report({"INFO"}, f"Saved {path}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_PT_panel(bpy.types.Panel):
    bl_label = "AI Mesh Doctor"
    bl_idname = "MD_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Mesh Doctor"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mesh_doctor
        layout.label(text="Measured inspection + guarded repair")
        layout.operator("mesh_doctor.scan", text="Scan Entire Project")
        layout.operator("mesh_doctor.scan", text="Scan Selected Objects").selected_only = True
        layout.label(text=settings.status)
        layout.prop(settings, "output_directory")
        layout.prop(settings, "evaluated")
        layout.prop(settings, "distance_tolerance")
        layout.prop(settings, "max_vertices")
        layout.prop(settings, "max_seconds")
        layout.prop(settings, "reuse_measurements")
        layout.operator("mesh_doctor.export_skills")
        if settings.last_report:
            layout.prop(settings, "last_report", text="Last JSON")
        box = layout.box()
        box.label(text="Visual inspection")
        box.prop(settings, "wireframe")
        box.prop(settings, "capture_profile")
        box.prop(settings, "capture_children")
        box.operator("mesh_doctor.capture")
        box.prop(settings, "quick_review_notes")
        box.operator('mesh_doctor.review_quick')
        box.prop(settings, "capture_manifest")
        box = layout.box()
        box.label(text="Optional OpenAI diagnosis")
        box.prop(settings, "model")
        box.prop(settings, "network_enabled")
        box.prop(settings, "api_budget")
        box.prop(settings, "input_price")
        box.prop(settings, "output_price")
        box.prop(settings, "stage")
        box.prop(settings, "ai_images")
        box.prop(settings, "references")
        box.prop(settings, "design_constraints")
        box.operator("mesh_doctor.analyze")
        box = layout.box()
        box.label(text="Measured repair")
        for field in ("operation", "whole_component", "region_indices", "max_displacement", "max_dimension_delta", "max_topology_delta", "strength", "iterations"):
            box.prop(settings, field)
        box.operator("mesh_doctor.plan")
        box.prop(settings, "plan_path")
        box.operator("mesh_doctor.preview")
        box.prop(settings, "component_approval")
        box.operator("mesh_doctor.apply")
        box.operator("mesh_doctor.discard")
        box.operator("mesh_doctor.rollback")
        box = layout.box()
        box.label(text="Complete component reconstruction")
        box.prop(settings, "reconstruction_spec")
        box.operator("mesh_doctor.reconstruct")
        box.prop(settings, "reviewed_capture_manifests")
        box.prop(settings, "uv_loss_approval")
        box.operator("mesh_doctor.accept_component")
        box.operator("mesh_doctor.record_case")
        box.prop(settings, "knowledge_family")
        box.prop(settings, "knowledge_parameters")
        box.prop(settings, "knowledge_units")
        box.operator("mesh_doctor.retrieve_cases")
        box.operator("mesh_doctor.cleanup")
        box = layout.box()
        box.label(text="Boundaries require design context")
        box.label(text="No arbitrary fill; approval required")


def _directory(context):
    settings = context.scene.mesh_doctor
    if not bpy.data.filepath and settings.output_directory.startswith("//"):
        return Path(bpy.utils.user_resource("DATAFILES", path="mesh_doctor/reports", create=True))
    return Path(bpy.path.abspath(settings.output_directory)).resolve()


def _report(context):
    global _last_report
    if _last_report is None:
        from .reporting import validate_report
        _last_report = validate_report(json.loads(Path(bpy.path.abspath(context.scene.mesh_doctor.last_report)).read_text(encoding="utf-8")))
    return _last_report


def _record_event(context, family, scope, method, measurements, parameters, evidence, tests, approval="pending"):
    from .knowledge import KnowledgeStore
    from .policy import skill_manifest
    path = _data_directory()/"knowledge.sqlite3"
    identifier = KnowledgeStore(path).record({"project": bpy.data.filepath or "unsaved",
        "scope": scope, "family": family, "units": "world_blender_units",
        "measurements": measurements, "method": method, "parameters": parameters,
        "problems": [], "corrections": [], "evidence": evidence, "tests": tests,
        "limitations": ["Case-specific; new dimensions, interfaces and visual validation required"],
        "sources": skill_manifest(Path.home()/".codex/skills")["sources"],
        "technical_status": "tested" if tests and evidence else "documented", "approval": approval,
        "reusable_rule": "Reuse measured method only after checking new scope and constraints",
        # Automatic event records intentionally have no reusable parameter range.
        # A reviewed recipe revision must declare its geometric applicability.
        "valid_ranges": {}})
    from .reporting import utc_now
    with (_data_directory()/"events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": utc_now(), "event": family, "case_id": identifier,
            "scope": scope, "method": method, "approval": approval}, ensure_ascii=False)+"\n")
    return identifier


def _data_directory():
    path = Path(os.environ.get("MESH_DOCTOR_DATA_DIR") or bpy.utils.user_resource("DATAFILES", path="mesh_doctor", create=True))
    path.mkdir(parents=True, exist_ok=True)
    return path


class MD_OT_capture(bpy.types.Operator):
    bl_idname = "mesh_doctor.capture"
    bl_label = "Capture Selected Inspection"

    @classmethod
    def poll(cls, context):
        return _active_job is None and context.mode == "OBJECT" and context.object and context.object.type in {"MESH", "EMPTY"}

    def execute(self, context):
        global _active_job
        from .capture import CaptureSession, CaptureConfig
        try:
            self.settings = context.scene.mesh_doctor
            profile = self.settings.capture_profile
            candidate = bool(context.object.get('mesh_doctor_source') or context.object.get('md_original_mesh'))
            preview = self.settings.quick_preview_manifest if profile == 'full' and candidate else None
            if profile == 'full' and candidate and not preview:
                raise ValueError('Capture and review the quick preview of this candidate before final 360')
            self.session = CaptureSession(context, context.object, _directory(context)/"captures",
                CaptureConfig(width=512 if profile=='quick' else 960, height=512 if profile=='quick' else 540,
                              wireframe=self.settings.wireframe,profile=profile,max_seconds=self.settings.max_seconds),
                include_children=self.settings.capture_children, reviewed_preview=preview,
                require_quality=profile=='full' and candidate)
            self.scene = context.scene
            self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
            context.window_manager.modal_handler_add(self)
            context.window_manager.progress_begin(0, len(self.session.jobs))
            _active_job = self
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        if event.type == "ESC" or context.scene != self.scene:
            self.cancel(context)
            return {"CANCELLED"}
        if event.type != "TIMER" or event.timer != self._timer:
            return {"PASS_THROUGH"}
        try:
            more = self.session.step()
            self.settings.status = f"Capture {self.session.position}/{len(self.session.jobs)} — Esc cancels"
            context.window_manager.progress_update(self.session.position)
            if not more:
                self.session.finish()
                self.settings.capture_manifest = str(self.session.manifest_path)
                if self.session.config.profile == 'quick':
                    self.settings.quick_preview_manifest = str(self.session.manifest_path)
                self.settings.status = "Capture complete; visual review pending"
                self._release(context)
                return {"FINISHED"}
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.cancel(context)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def _release(self, context):
        global _active_job
        context.window_manager.event_timer_remove(self._timer)
        context.window_manager.progress_end()
        _active_job = None

    def cancel(self, context):
        self.session.finish(cancelled=True)
        self._release(context)


class MD_OT_review_quick(bpy.types.Operator):
    bl_idname = 'mesh_doctor.review_quick'
    bl_label = 'Record Quick Preview Review'

    def execute(self, context):
        from .capture import review_quick_capture
        try:
            settings = context.scene.mesh_doctor
            review_quick_capture(bpy.path.abspath(settings.quick_preview_manifest),settings.quick_review_notes)
            settings.status = 'Technical preview reviewed; aesthetic approval remains separate'
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}


class MD_OT_analyze(bpy.types.Operator):
    bl_idname = "mesh_doctor.analyze"
    bl_label = "Analyze Diagnostic Evidence"

    @classmethod
    def poll(cls, context):
        return _active_job is None

    def execute(self, context):
        global _active_job
        from .ai_client import DiagnosticClient, AIConfig
        try:
            settings = context.scene.mesh_doctor
            config = AIConfig(model=settings.model, allow_network=settings.network_enabled,
                max_cost_usd=settings.api_budget, input_usd_per_million=settings.input_price,
                output_usd_per_million=settings.output_price, dependency_path=str(_data_directory()/"python"))
            if not config.allow_network or not config.model:
                raise ValueError("Configure model and enable diagnostic transmission first")
            # All Blender access ends before the worker starts.
            report = json.loads(json.dumps(_report(context)))
            paths = json.loads(settings.ai_images)
            refs = json.loads(settings.references)
            if type(paths) is not list or type(refs) is not list or not all(type(p) is str for p in paths+refs):
                raise ValueError("Image/reference paths must be JSON string arrays")
            self.output = _directory(context)/"ai_diagnosis.json"
            self.executor = ThreadPoolExecutor(max_workers=1)
            self.future = self.executor.submit(DiagnosticClient(config).analyze, report, settings.stage,
                paths, refs, settings.design_constraints,
                {"construction_policy": skill_manifest(Path.home()/".codex/skills")["policy"]})
            self._timer = context.window_manager.event_timer_add(0.15, window=context.window)
            context.window_manager.modal_handler_add(self)
            _active_job = self
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        if event.type == "ESC":
            self.cancel(context)
            self.report({"INFO"}, "Result discarded; an in-flight API request may still be billed")
            return {"CANCELLED"}
        if event.type != "TIMER" or event.timer != self._timer or not self.future.done():
            return {"PASS_THROUGH"}
        try:
            result = self.future.result()
            atomic_json(self.output, result)
            if result["repair_plans"]:
                path = self.output.parent/"ai_repair_plan.json"
                atomic_json(path, result["repair_plans"][0])
                context.scene.mesh_doctor.plan_path = str(path)
                context.scene.mesh_doctor.component_approval = False
            context.scene.mesh_doctor.status = "Diagnosis saved; no repairs executed"
            text = bpy.data.texts.get("MD_Diagnosis.json") or bpy.data.texts.new("MD_Diagnosis.json")
            text.clear()
            text.write(json.dumps(result, ensure_ascii=False, indent=2))
            return {"FINISHED"}
        except Exception as exc:
            # Provider exceptions may contain request details. Keep UI errors generic.
            self.report({"ERROR"}, f"AI analysis failed ({type(exc).__name__}); scene unchanged")
            return {"CANCELLED"}
        finally:
            self._release(context)

    def _release(self, context):
        global _active_job
        context.window_manager.event_timer_remove(self._timer)
        self.executor.shutdown(wait=False, cancel_futures=True)
        _active_job = None

    def cancel(self, context):
        self.future.cancel()
        self._release(context)


class MD_Ready:
    @classmethod
    def poll(cls, context):
        return _active_job is None and context.mode == "OBJECT"


class MD_OT_plan(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.plan"
    bl_label = "Generate Measured Repair Plan"

    def execute(self, context):
        from .planning import deterministic_plan, validate_plan
        from .repair import measured_plane
        try:
            obj, settings, report = context.object, context.scene.mesh_doctor, _report(context)
            if context.mode != "OBJECT" or not obj or obj.type != "MESH":
                raise ValueError("Select a mesh in Object Mode")
            record = next(o for o in report["objects"] if o["name"] == obj.name_full)
            region = list(range(len(obj.data.vertices))) if settings.whole_component else json.loads(settings.region_indices)
            operation, parameters = settings.operation, {}
            if operation == "fit_plane":
                fit = measured_plane(obj, region)
                parameters = {"origin": fit["origin"], "normal": fit["normal"], "strength": settings.strength}
            elif operation in {"smooth_local", "relax_local"}:
                parameters = {"strength": settings.strength, "iterations": settings.iterations}
            elif operation == "merge_vertices":
                parameters = {"distance": settings.distance_tolerance}
            plan = deterministic_plan(record, operation, region, parameters,
                {"max_displacement": settings.max_displacement, "max_dimension_delta": settings.max_dimension_delta,
                 "max_topology_delta": settings.max_topology_delta, "protected_vertices": []}, "User-selected measured operation")
            validate_plan(plan, report)
            path = _directory(context)/"repair_plan.json"
            atomic_json(path, plan)
            settings.plan_path = str(path)
            settings.component_approval = False
            text = bpy.data.texts.get("MD_Plan.json") or bpy.data.texts.new("MD_Plan.json")
            text.clear()
            text.write(json.dumps(plan, indent=2))
            settings.status = "Plan saved; review it before preview/apply"
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_preview(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.preview"
    bl_label = "Preview Repair + Validate"

    def execute(self, context):
        global _transaction
        from .repair import RepairTransaction
        try:
            if _transaction:
                _transaction.obj.hide_set(getattr(_transaction, "original_hidden", False))
                _transaction.discard()
                _transaction = None
            settings = context.scene.mesh_doctor
            plan = json.loads(Path(bpy.path.abspath(settings.plan_path)).read_text(encoding="utf-8"))
            _transaction = RepairTransaction(context, context.object, plan, _report(context))
            _transaction.report_path = _directory(context)/f"repair-{_transaction.id}.json"
            atomic_json(_transaction.report_path, {"plan": plan, "validation": _transaction.validation})
            settings.component_approval = False
            _transaction.original_hidden = context.object.hide_get()
            context.object.hide_set(True)
            _transaction.preview.hide_set(False)
            settings.status = "Validated preview visible; original retained"
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_apply(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.apply"
    bl_label = "Apply Approved Repair"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global _transaction
        try:
            if not _transaction:
                raise ValueError("Create a validated preview first")
            _transaction.apply(approved=context.scene.mesh_doctor.component_approval)
            _transaction.obj.hide_set(getattr(_transaction, "original_hidden", False))
            try:
                _record_event(context, "repair:"+_transaction.plan["operation"], _transaction.obj.name_full,
                    _transaction.plan["operation"], {"vertex_count": len(_transaction.obj.data.vertices)},
                    _transaction.plan["parameters"], [str(_transaction.report_path)],
                    ["Independent validation passed", "Source retained for rollback"], "approved")
            except Exception as exc:
                self.report({"WARNING"}, f"Repair applied; learning record failed ({type(exc).__name__})")
            context.scene.mesh_doctor.status = "Repair applied; original retained for rollback"
            _transaction = None
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_discard(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.discard"
    bl_label = "Discard Preview"

    def execute(self, context):
        global _transaction
        if _transaction:
            _transaction.obj.hide_set(getattr(_transaction, "original_hidden", False))
            _transaction.discard()
            _transaction = None
        return {"FINISHED"}


class MD_OT_rollback(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.rollback"
    bl_label = "Rollback Last Repair"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .repair import rollback
        try:
            rollback(context.object)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_reconstruct(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.reconstruct"
    bl_label = "Preview Complete Measured Component"

    def execute(self, context):
        global _reconstruction
        from .reconstruction import build_component, inspect_neighbors
        from .repair import state_signature
        try:
            if _reconstruction:
                prior = _reconstruction["candidate"]
                mesh = prior.data
                bpy.data.objects.remove(prior, do_unlink=True)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
                _reconstruction = None
            source = context.object
            if not source or source.type != "MESH" or context.mode != "OBJECT":
                raise ValueError("Select the source component in Object Mode")
            settings = context.scene.mesh_doctor
            spec = json.loads(Path(bpy.path.abspath(settings.reconstruction_spec)).read_text(encoding="utf-8"))
            obj, validation = build_component(spec, "MD_REBUILT_"+source.name)
            context.scene.collection.objects.link(obj)
            obj["mesh_doctor_source"] = source.name_full
            obj["mesh_doctor_specification"] = json.dumps(spec)
            neighbors = inspect_neighbors(context, obj, source, spec)
            _reconstruction = {"source": source, "candidate": obj, "source_signature": state_signature(source),
                               "candidate_signature": state_signature(obj), "spec": spec,
                               "validation": validation, "neighbors": neighbors,
                               "report_path": str(_directory(context)/f"reconstruction-{obj['mesh_doctor_component']}.json")}
            obj.hide_render = True
            settings.component_approval = False
            atomic_json(_reconstruction["report_path"], {"spec": spec, "validation": validation, "neighbors": neighbors})
            settings.status = f"Component preview; {neighbors['unclassified']} neighbor relations need classification"
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_accept_component(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.accept_component"
    bl_label = "Accept Reviewed Component"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global _reconstruction
        from .repair import state_signature
        from .reconstruction import inspect_neighbors
        try:
            data, settings = _reconstruction, context.scene.mesh_doctor
            if not data or not settings.component_approval or not settings.uv_loss_approval:
                raise ValueError("Review the component and explicitly approve replacement mapping first")
            if state_signature(data["source"]) != data["source_signature"] or state_signature(data["candidate"]) != data["candidate_signature"]:
                raise ValueError("Source/candidate changed; regenerate measured preview")
            from .quality import audit_component
            quality = audit_component(data['candidate'])
            if not quality['accepted']:
                raise ValueError('Candidate quality gate failed: '+', '.join(quality['reasons']))
            neighbors = inspect_neighbors(context, data["candidate"], data["source"], data["spec"])
            if neighbors["unclassified"]:
                raise ValueError("Unclassified neighbor relations block acceptance")
            manifests = json.loads(settings.reviewed_capture_manifests)
            if len(manifests) < 2:
                raise ValueError("Supply reviewed before/after capture manifests")
            for path in manifests:
                manifest = json.loads(Path(path).read_text(encoding="utf-8"))
                if manifest["status"] != "complete" or len(manifest["files"]) < 124:
                    raise ValueError("Full isolated/assembled 15-degree capture coverage is required")
                expected = {f"{mode}:{orbit}_{angle:03}" for mode in ("isolated","assembled") for orbit in ("horizontal","vertical") for angle in range(0,360,15)}
                if not expected <= {f["purpose"] for f in manifest["files"]}:
                    raise ValueError("Incomplete orbit coverage")
            if data["source"].name_full not in {json.loads(Path(p).read_text(encoding="utf-8"))["target"] for p in manifests} or data["candidate"].name_full not in {json.loads(Path(p).read_text(encoding="utf-8"))["target"] for p in manifests}:
                raise ValueError("Manifests must include this source and candidate")
            # Acceptance promotes a separate functional component; source remains in-project.
            data["source"].hide_set(True)
            data["source"].hide_render = True
            data["candidate"].hide_render = False
            data["candidate"]["mesh_doctor_source"] = data["source"].name_full
            data["candidate"]["mesh_doctor_approved"] = True
            try:
                _record_event(context, data["spec"]["family"], data["source"].name_full,
                    "complete_measured_profile", {"vertex_count": len(data["candidate"].data.vertices)},
                    data["spec"], [data["report_path"], *manifests],
                    ["Closed topology and measured bounds passed", "Interfaces reviewed by user"], "approved")
            except Exception as exc:
                self.report({"WARNING"}, f"Component accepted; learning record failed ({type(exc).__name__})")
            context.view_layer.objects.active = data["candidate"]
            settings.status = "Component accepted; source retained in same project"
            _reconstruction = None
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_record_case(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.record_case"
    bl_label = "Record Case JSON in Knowledge Store"

    def execute(self, context):
        from .knowledge import KnowledgeStore
        try:
            text = bpy.data.texts.get("MD_Case.json")
            if text is None:
                raise ValueError("Create MD_Case.json in Text Editor using the documented case schema")
            path = _data_directory()/"knowledge.sqlite3"
            identifier = KnowledgeStore(path).record(json.loads(text.as_string()))
            context.scene.mesh_doctor.status = f"Case recorded: {identifier}"
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_cleanup(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.cleanup"
    bl_label = "Clean Approved Temporary Captures"

    def execute(self, context):
        from .capture import cleanup_approved
        try:
            settings = context.scene.mesh_doctor
            cleanup_approved(bpy.path.abspath(settings.capture_manifest), settings.component_approval)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MD_OT_retrieve_cases(MD_Ready, bpy.types.Operator):
    bl_idname = "mesh_doctor.retrieve_cases"
    bl_label = "Retrieve Compatible Approved Recipes"

    def execute(self, context):
        from .knowledge import KnowledgeStore
        try:
            settings = context.scene.mesh_doctor
            parameters = json.loads(settings.knowledge_parameters)
            if type(parameters) is not dict:
                raise ValueError("Measured parameters must be a JSON object")
            results = KnowledgeStore(_data_directory()/"knowledge.sqlite3").candidates(
                settings.knowledge_family, settings.knowledge_units, parameters)
            text = bpy.data.texts.get("MD_Recipes.json") or bpy.data.texts.new("MD_Recipes.json")
            text.clear()
            text.write(json.dumps(results, ensure_ascii=False, indent=2))
            settings.status = f"{len(results)} compatible recipes; each requires new validation"
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


CLASSES = (MD_Settings, MD_OT_scan, MD_OT_skills, MD_OT_capture, MD_OT_review_quick, MD_OT_analyze,
           MD_OT_plan, MD_OT_preview, MD_OT_apply, MD_OT_discard, MD_OT_rollback,
           MD_OT_reconstruct, MD_OT_accept_component, MD_OT_record_case, MD_OT_cleanup, MD_OT_retrieve_cases, MD_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mesh_doctor = PointerProperty(type=MD_Settings)


def unregister():
    global _active_job, _transaction, _reconstruction, _last_report
    if _active_job:
        _active_job.cancel(bpy.context)
    if _transaction:
        _transaction.obj.hide_set(getattr(_transaction, "original_hidden", False))
        _transaction.discard()
        _transaction = None
    if _reconstruction:
        obj = _reconstruction["candidate"]
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        _reconstruction = None
    _last_report = None
    if hasattr(bpy.types.Scene, "mesh_doctor"):
        del bpy.types.Scene.mesh_doctor
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
