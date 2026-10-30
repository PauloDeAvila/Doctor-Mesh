"""Regressions from the hand rebuild; independent factory-startup scene."""
import sys,json,tempfile,unittest,math
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy,numpy as np
from mathutils import Matrix
from ai_mesh_doctor.arrays import load_npz_arrays,mesh_arrays,validate_source_snapshot
from ai_mesh_doctor.cache import MeasurementCache,content_key
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.config import InspectionConfig
from ai_mesh_doctor.quality import (audit_component,check_surface,through_cut_interval,
                                   segments_for_sagitta,inspect_coincident_interface,QualityPolicy)
from ai_mesh_doctor.reconstruction import build_component
from ai_mesh_doctor.capture import CaptureSession,CaptureConfig,view_schedule,review_quick_capture
from ai_mesh_doctor.reporting import atomic_json
from ai_mesh_doctor.batch import ComponentBatch
from ai_mesh_doctor.geometry import analyze_mesh


class EfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        bpy.ops.wm.read_factory_settings(use_empty=False)
        self.cube=bpy.data.objects['Cube']
    def tearDown(self):self.temp.cleanup()

    def test_eager_archive_decodes_each_member_once(self):
        path=self.directory/'data.npz';np.savez_compressed(path,vertices=np.ones((30,3)),triangles=np.array([[0,1,2]]))
        original=np.lib.npyio.NpzFile.__getitem__;calls=[]
        def read(obj,key):calls.append(key);return original(obj,key)
        with patch.object(np.lib.npyio.NpzFile,'__getitem__',read):
            arrays=mesh_arrays(path)
            for _ in range(1000):arrays['vertices'][0]
        self.assertEqual(calls,['vertices','triangles'])
        self.assertFalse(arrays['vertices'].flags.writeable)
        path.unlink() # The file handle has been closed.

    def test_bad_numeric_inputs_are_rejected(self):
        for value in (np.array([float('nan')]),np.array([object()],dtype=object)):
            path=self.directory/'bad.npz';np.savez(path,vertices=value)
            with self.assertRaises(ValueError):load_npz_arrays(path)
        np.savez(self.directory/'budget.npz',x=np.ones(100))
        with self.assertRaises(ValueError):load_npz_arrays(self.directory/'budget.npz',max_bytes=10)
        np.savez(self.directory/'badmesh.npz',vertices=np.ones((3,3)),triangles=np.array([[0,1,8]]))
        with self.assertRaises(ValueError):mesh_arrays(self.directory/'badmesh.npz')

    def test_source_snapshot_rejects_changed_mold_or_frame(self):
        coords=np.array([list(v.co) for v in self.cube.data.vertices],float);frame=list(map(list,self.cube.matrix_world))
        self.cube.data.calc_loop_triangles();triangles=np.array([list(t.vertices) for t in self.cube.data.loop_triangles])
        other=bpy.data.meshes.new('changed connectivity');faces=triangles.copy();faces[0]=faces[0][::-1];other.from_pydata(coords.tolist(),[],faces.tolist())
        with self.assertRaises(ValueError):validate_source_snapshot(other,self.cube.matrix_world,coords,frame,triangles)
        validate_source_snapshot(self.cube.data,self.cube.matrix_world,coords,frame)
        with self.assertRaises(ValueError):validate_source_snapshot(self.cube.data,Matrix.Translation((1,0,0)),coords,frame)
        self.cube.data.vertices[0].co.x+=.1
        with self.assertRaises(ValueError):validate_source_snapshot(self.cube.data,self.cube.matrix_world,coords,frame)

    def test_incomplete_and_corrupt_measurements_are_not_reused(self):
        cache=MeasurementCache(self.directory);key=content_key('test',{'mesh':'a'})
        self.assertFalse(cache.put(key,{'status':'partial'}));self.assertIsNone(cache.get(key))
        cache.put(key,{'status':'complete','value':1});self.assertEqual(cache.get(key)['value'],1)
        entry=json.loads((self.directory/f'{key}.json').read_text());entry['payload']['value']=2
        (self.directory/f'{key}.json').write_text(json.dumps(entry));self.assertIsNone(cache.get(key))

    def _scan(self,config=None):
        scanner=ProjectScanner(bpy.context,selected=True,config=config,cache_directory=self.directory/'cache')
        scanner.queue=[self.cube];scanner.total=1
        return scanner.run()

    def test_cache_reuses_base_evaluated_and_next_scan(self):
        first=self._scan();second=self._scan()
        self.assertEqual(first['summary']['geometry_analysis_runs'],1)
        self.assertEqual(first['summary']['geometry_cache_hits'],1)
        self.assertEqual(second['summary']['geometry_analysis_runs'],0)
        self.assertEqual(second['summary']['geometry_cache_hits'],2)

    def test_cache_invalidates_geometry_transform_sharp_and_config(self):
        self._scan();self.cube.data.vertices[0].co.x+=.1
        self.assertGreater(self._scan()['summary']['geometry_analysis_runs'],0)
        self.cube.location.x+=1;bpy.context.view_layer.update()
        self.assertGreater(self._scan()['summary']['geometry_analysis_runs'],0)
        self.cube.data.edges[0].use_edge_sharp=True
        self.assertGreater(self._scan()['summary']['geometry_analysis_runs'],0)
        self.assertGreater(self._scan(InspectionConfig(distance_tolerance=2e-6))['summary']['geometry_analysis_runs'],0)

    def test_evaluated_cache_uses_content_not_temporary_pointer(self):
        modifier=self.cube.modifiers.new('bevel','BEVEL');modifier.width=.1
        report=self._scan();self.assertEqual(report['summary']['geometry_analysis_runs'],2)
        modifier.width=.2;bpy.context.view_layer.update()
        report=self._scan();self.assertEqual(report['summary']['geometry_analysis_runs'],1)

    def test_measured_plane_group_catches_warped_triangles(self):
        mesh=bpy.data.meshes.new('warped');mesh.from_pydata([(0,0,0),(1,0,0),(1,1,.01),(0,1,0)],[],[(0,1,2),(0,2,3)])
        constraint={'family':'plane','vertices':[0,1,2,3],'origin':[0,0,0],'normal':[0,0,1],'tolerance':.001}
        self.assertFalse(check_surface(mesh,Matrix.Identity(4),constraint)['accepted'])

    def test_small_geometry_does_not_collapse_under_world_translation(self):
        for v in self.cube.data.vertices:v.co*=1e-7
        config=InspectionConfig(distance_tolerance=1e-10,area_tolerance=1e-22)
        before=analyze_mesh(self.cube.data,Matrix.Identity(4),config)
        after=analyze_mesh(self.cube.data,Matrix.Translation((3,4,1)),config)
        self.assertTrue(before['closed_topology_candidate']);self.assertTrue(after['closed_topology_candidate'])
        self.assertEqual(before['duplicate_pair_count'],after['duplicate_pair_count'])
        self.assertEqual(before['face_area_world'],after['face_area_world'])

    def test_measured_circle_catches_oval(self):
        mesh=bpy.data.meshes.new('oval');mesh.from_pydata([(1.02*math.cos(i*math.tau/32),math.sin(i*math.tau/32),0) for i in range(32)],[],[])
        constraint={'family':'circle','vertices':list(range(32)),'origin':[0,0,0],'normal':[0,0,1],'radius':1.,'tolerance':.001}
        self.assertFalse(check_surface(mesh,Matrix.Identity(4),constraint)['accepted'])

    def test_through_cut_overshoots_both_stock_caps(self):
        lower,upper=through_cut_interval(-.026,.001)
        self.assertLess(lower,-.026);self.assertGreater(upper,.001)
        n=segments_for_sagitta(.06,.00001);self.assertLessEqual(.06*(1-math.cos(math.pi/n)),.00001)
        with self.assertRaises(ValueError):segments_for_sagitta(1,1e-12)

    def test_closed_cube_passes_open_and_budget_cases_do_not(self):
        self.assertTrue(audit_component(self.cube)['accepted'])
        self.assertFalse(audit_component(self.cube,policy=QualityPolicy(max_triangles=1))['accepted'])
        mesh=bpy.data.meshes.new('open');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
        obj=bpy.data.objects.new('open',mesh)
        self.assertFalse(audit_component(obj)['accepted'])

    def test_same_facing_duplicate_interface_is_rejected(self):
        other=self.cube.copy();other.data=self.cube.data.copy();bpy.context.scene.collection.objects.link(other)
        report=inspect_coincident_interface(self.cube,other)
        self.assertFalse(report['accepted'])
        self.assertTrue(any(x['orientation']=='same_facing' for x in report['forward']['examples']))

    def test_batch_failure_restores_all_source_data(self):
        other=self.cube.copy();other.data=self.cube.data.copy();bpy.context.scene.collection.objects.link(other)
        before=(self.cube.data,other.data);batch=ComponentBatch(bpy.context,retain_sources=True)
        batch.stage(self.cube,self.cube.data.copy());batch.stage(other,other.data.copy())
        assign=batch._assign;count=[0]
        def fail_second(source,mesh):
            count[0]+=1
            if count[0]==2:raise RuntimeError('synthetic commit failure')
            assign(source,mesh)
        with patch.object(batch,'_assign',side_effect=fail_second):
            with self.assertRaises(RuntimeError):batch.commit()
        self.assertEqual((self.cube.data,other.data),before)
        self.assertFalse(any(o.get('mesh_doctor_batch') for o in bpy.data.objects))

    def test_batch_preserves_intervening_edits_and_keeps_original_on_success(self):
        old=self.cube.data;batch=ComponentBatch(bpy.context,retain_sources=True)
        batch.stage(self.cube,old.copy());self.cube.location.x=2;bpy.context.view_layer.update()
        with self.assertRaises(ValueError):batch.commit()
        self.assertEqual(self.cube.data,old);self.assertEqual(self.cube.location.x,2);batch.discard()
        batch=ComponentBatch(bpy.context,retain_sources=True);batch.stage(self.cube,old.copy());batch.commit()
        self.assertTrue(old.use_fake_user);self.assertEqual(self.cube['mesh_doctor_batch_original_mesh'],old.name)

    def test_opposed_planar_contact_requires_specific_plane(self):
        other=self.cube.copy();other.data=self.cube.data.copy();bpy.context.scene.collection.objects.link(other);other.location.x=2;bpy.context.view_layer.update()
        self.assertFalse(inspect_coincident_interface(self.cube,other)['accepted'])
        contact={'origin':[1,0,0],'normal':[1,0,0],'tolerance':1e-6}
        self.assertTrue(inspect_coincident_interface(self.cube,other,contact)['accepted'])

    def test_capture_quick_is_not_full_and_incomplete_is_not_complete(self):
        self.assertEqual(len(view_schedule(profile='quick')),8);self.assertEqual(len(view_schedule()),62)
        s=CaptureSession(bpy.context,self.cube,self.directory,CaptureConfig(width=80,height=80,profile='quick'))
        s.step();manifest=s.finish();self.assertEqual(manifest['status'],'incomplete')
        self.assertEqual(s.finish(),manifest)
        with self.assertRaises(ValueError):review_quick_capture(s.manifest_path,'checked')

    def test_failed_frame_does_not_advance_and_budget_stops(self):
        s=CaptureSession(bpy.context,self.cube,self.directory,CaptureConfig(width=80,height=80,profile='quick'))
        with patch.object(s,'_render_image',side_effect=RuntimeError('synthetic render failure')):
            with self.assertRaises(RuntimeError):s.step()
        self.assertEqual(s.position,0);self.assertFalse(s.manifest['files'])
        s.started-=1000
        with self.assertRaises(TimeoutError):s.step()
        s.finish(cancelled=True)

    def test_full_candidate_requires_reviewed_unchanged_quick_evidence(self):
        s=CaptureSession(bpy.context,self.cube,self.directory,CaptureConfig(width=80,height=80,profile='quick'))
        while s.step():pass
        self.assertEqual(s.finish()['status'],'complete');self.assertEqual(len(s.manifest['files']),16)
        before=(len(bpy.data.scenes),len(bpy.data.objects))
        with self.assertRaises(ValueError):CaptureSession(bpy.context,self.cube,self.directory,reviewed_preview=s.manifest_path)
        self.assertEqual(before,(len(bpy.data.scenes),len(bpy.data.objects)))
        review_quick_capture(s.manifest_path,'All directions including rear bore inspected')
        full=CaptureSession(bpy.context,self.cube,self.directory,reviewed_preview=s.manifest_path,require_quality=True)
        full.finish(cancelled=True)
        self.cube.data.vertices[0].co.x+=.1
        with self.assertRaises(ValueError):CaptureSession(bpy.context,self.cube,self.directory,reviewed_preview=s.manifest_path)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EfficiencyTests))
    atomic_json(ROOT/'efficiency-test-results.json',{'success':result.wasSuccessful(),'tests':result.testsRun,
        'errors':[str(t)+d for t,d in result.errors],'failures':[str(t)+d for t,d in result.failures]})
    if not result.wasSuccessful():raise RuntimeError('Efficiency/quality regression suite failed')
