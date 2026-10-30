"""Prepare/check all component meshes before swapping any source datablock."""
from uuid import uuid4
import hashlib
import json
from array import array
import bpy
from .quality import audit_component
from .identity import measurement_fingerprint
from .dependencies import rna_settings


def batch_signature(obj):
    """Bulk attribute hashing for the NEW batch path; legacy rollback unchanged."""
    mesh=obj.data;digest=hashlib.sha256(measurement_fingerprint(mesh).encode())
    for attribute in mesh.attributes:
        digest.update(json.dumps([attribute.name,attribute.domain,attribute.data_type]).encode())
        if not len(attribute.data):continue
        for prop in attribute.data[0].bl_rna.properties:
            if prop.identifier=='rna_type':continue
            if prop.type in {'BOOLEAN','INT','FLOAT'}:
                count=len(attribute.data)*(prop.array_length if prop.is_array else 1)
                values=array({'BOOLEAN':'b','INT':'i','FLOAT':'f'}[prop.type],[0])*count
                attribute.data.foreach_get(prop.identifier,values);digest.update(values.tobytes())
            elif prop.type in {'STRING','ENUM'}:
                digest.update(json.dumps([getattr(v,prop.identifier) for v in attribute.data]).encode())
    indices=array('i',[0])*len(mesh.polygons);mesh.polygons.foreach_get('material_index',indices);digest.update(indices.tobytes())
    content={'matrix':[list(row) for row in obj.matrix_world],
        'materials':[(s.material.as_pointer() if s.material else None,s.link) for s in obj.material_slots],
        'parent':obj.parent.as_pointer() if obj.parent else None,
        'uv':[(u.name,u.active_render) for u in mesh.uv_layers], 'active_uv':mesh.uv_layers.active_index,
        'modifiers':[(m.type,rna_settings(m)) for m in obj.modifiers],
        'constraints':[(c.type,rna_settings(c)) for c in obj.constraints]}
    digest.update(json.dumps(content,sort_keys=True,allow_nan=False).encode())
    return digest.hexdigest()


class ComponentBatch:
    def __init__(self, context, *, retain_sources):
        self.context=context;self.retain_sources=retain_sources;self.items=[]
        self.state='preparing';self.owner=str(uuid4());self.failures=[]

    def stage(self, source, mesh, constraints=()):
        """Takes ownership of the new mesh. Source stays unchanged until commit."""
        if self.state!='preparing' or source.type!='MESH' or source.modifiers or source.data.shape_keys:
            raise ValueError('Editable base meshes without modifier/shape-key dependencies required')
        if not source.is_editable or not source.data.is_editable or mesh==source.data:
            raise ValueError('A separate editable candidate mesh is required')
        if any(item['source']==source for item in self.items):
            raise ValueError('Source already staged')
        obj=source.copy();obj.data=mesh;obj.name='MD_BATCH_'+source.name
        self.context.scene.collection.objects.link(obj);obj.matrix_world=source.matrix_world.copy()
        obj.hide_set(True);obj.hide_render=True;obj['mesh_doctor_batch']=self.owner
        item={'source':source,'candidate':obj,'old':source.data,'signature':batch_signature(source)}
        self.items.append(item)
        try:
            if source.data.uv_layers:
                if not mesh.uv_layers:mesh.uv_layers.new(name='UVMap')
                mod=obj.modifiers.new('Reference UV correspondence','DATA_TRANSFER');mod.object=source
                mod.use_loop_data=True;mod.data_types_loops={'UV'};mod.loop_mapping='POLYINTERP_NEAREST'
                with self.context.temp_override(object=obj,active_object=obj,selected_objects=[obj],selected_editable_objects=[obj]):
                    bpy.ops.object.modifier_apply(modifier=mod.name)
            item['quality']=audit_component(obj,constraints)
            if not item['quality']['accepted']:
                raise ValueError(f'Quality gate failed for {source.name}: '+', '.join(item['quality']['reasons']))
            item['candidate_signature']=batch_signature(obj)
            return obj,item['quality']
        except Exception as exc:
            self.failures.append({'source':source.name,'error':str(exc),'quality':item.get('quality')})
            self.discard()
            raise

    def _assign(self, source, mesh):
        source.data=mesh

    def commit(self):
        if self.state!='preparing' or not self.items:
            raise ValueError('No prepared batch')
        self.context.view_layer.update()
        for item in self.items:
            if (batch_signature(item['source'])!=item['signature']
                    or batch_signature(item['candidate'])!=item['candidate_signature']):
                raise ValueError('Source/candidate edited during preparation; preserve edits and regenerate')
        assigned=[]
        try:
            for item in self.items:
                self._assign(item['source'],item['candidate'].data);assigned.append(item)
        except Exception:
            for item in reversed(assigned):item['source'].data=item['old']
            self.discard();raise
        for item in self.items:
            source,old=item['source'],item['old']
            if self.retain_sources and not (source.get('md_original_mesh') or source.get('mesh_doctor_batch_original_mesh')):
                old.use_fake_user=True;source['mesh_doctor_batch_original_mesh']=old.name
        self.state='committed'
        self._release()
        return [item['quality'] for item in self.items]

    def _release(self):
        for item in self.items:
            obj=item['candidate'];mesh=obj.data
            bpy.data.objects.remove(obj,do_unlink=True)
            if mesh.users==0:bpy.data.meshes.remove(mesh)
            old=item['old']
            if self.state=='committed' and old.users==0 and not old.use_fake_user:
                bpy.data.meshes.remove(old)

    def discard(self):
        if self.state not in {'discarded','committed'}:
            self.state='discarded';self._release()
