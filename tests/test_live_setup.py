import tempfile,json,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from visual_targeting.live_setup import fishing_setup
from visual_targeting.profiles import Profile,WindowIdentity
from visual_targeting.geometry import Rect
from visual_targeting.experiments import sha
from visual_targeting.errors import record_error
from settings import Settings

class LiveSetupTests(unittest.TestCase):
    def settings(self):
        s=Settings();s.area_of_interest=[(10,10),(80,10),(80,70),(10,70)];s.cast_location=(50,90);s.attach_bait=False;s.auto_loot=True
        return s
    def probe(self,profile):
        rule=profile.data['allowed_windows'][0]
        return lambda hwnd:(WindowIdentity(hwnd,'World of Warcraft',rule['executables'][0]),Rect(0,0,100,100),0)
    def test_live_fill_uses_exact_approved_weights_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);candidate=root/'best.pt';candidate.write_bytes(b'weights');approved=root/'approved.pt';approved.write_bytes(b'weights')
            profile=Path('configs/tasks/fishing-neural-v2.json').resolve();s=self.settings()
            info={'profile':profile,'weights':candidate}
            with patch('visual_targeting.live_setup.ModelRegistry') as registry:
                registry.return_value.active.return_value={'weights_sha256':sha(candidate),'weights_path':approved}
                result=fishing_setup(s,info,root/'registry',7,self.probe(Profile.read(profile)))
            self.assertTrue(result['ready']);self.assertEqual(result['fields']['weights'],str(approved.resolve()))
            self.assertIsNone(s.top_left) # Startup-derived geometry need not exist while the settings GUI is open.
            for value in result['fields'].values():self.assertTrue(Path(value).is_absolute())
    def test_wrong_model_and_moved_window_are_explicit_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            weights=Path(tmp)/'weights.pt';weights.write_bytes(b'w');profile=Path('configs/tasks/fishing-neural-v2.json');s=self.settings();s.cast_location=(200,200)
            with patch('visual_targeting.live_setup.ModelRegistry') as registry:
                registry.return_value.active.return_value={'weights_sha256':'different','weights_path':weights}
                result=fishing_setup(s,{'profile':profile,'weights':weights},tmp,7,self.probe(Profile.read(profile)))
            self.assertFalse(result['ready']);self.assertIn('not the active approved',result['message']);self.assertIn('ability is outside',result['message'])
    def test_persistent_errors_include_context_and_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:raise ValueError('output folder reused')
            except ValueError as exc:identifier,path=record_error('evaluate',exc,{'output':'runs/existing'},tmp)
            event=json.loads(path.read_text())
            self.assertEqual(event['id'],identifier);self.assertEqual(event['context']['output'],'runs/existing');self.assertIn('ValueError',event['traceback'])
    def test_gui_reuses_unique_output_on_retry_without_enabling_input(self):
        import tkinter as tk
        from visual_targeting.app_gui import TargetingPanel
        root=tk.Tk();root.withdraw();panel=TargetingPanel(root);root.update()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                panel.values['dataset'].set(str(Path(tmp)/'dataset'));panel.values['output'].set(tmp)
                panel.values['weights'].set('weights.pt');panel.values['training_run'].set('runs/run')
                with patch.object(panel.job,'start') as started:
                    panel.job_command('evaluate');args=started.call_args.args[0]
                    self.assertFalse(Path(args[args.index('--output')+1]).exists())
                    self.assertNotEqual(args[args.index('--output')+1],tmp)
                self.assertEqual(panel.mode.get(),'dry-run')
        finally:panel.shutdown();root.destroy()

    def test_auto_fill_restores_exact_profile_without_overwriting_edited_snapshot(self):
        from visual_targeting.deployment import candidate_for_run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'runs/model';run.mkdir(parents=True)
            weights=run/'best.pt';weights.write_bytes(b'weights')
            profile=Profile.read('configs/tasks/fishing-neural-v2.json')
            (run/'run.json').write_text(json.dumps({'status':'completed','checkpoint':str(weights),'checkpoint_sha256':sha(weights),'profile':profile.data,'profile_sha256':profile.digest}))
            snapshot=root/'data/profiles'/('trained-'+profile.digest[:16]+'.json');snapshot.parent.mkdir(parents=True);snapshot.write_text('edited invalid profile')
            info=candidate_for_run(run,root=root)
            self.assertEqual(Profile.read(info['profile']).digest,profile.digest)
            self.assertEqual(snapshot.read_text(),'edited invalid profile')
    def test_auto_fill_updates_normal_controls_without_enabling_input(self):
        from gui import App
        app=App(Settings());app.root.withdraw();app.root.update()
        try:
            report={'ready':True,'hwnd':7,'fields':{'weights':'D:/models/approved.pt','profile':'D:/profiles/exact.json','registry':'D:/registry'},'message':'LIVE SETUP READY'}
            with patch('visual_targeting.live_setup.fishing_setup',return_value=report):app.use_selected_fishing({})
            self.assertEqual(app.s.detector_backend,'neural');self.assertEqual(app.s.neural_weights,'D:/models/approved.pt')
            self.assertEqual(app.neural_registry_var.get(),'D:/registry');self.assertEqual(app.s.neural_window_hwnd,7)
            self.assertFalse(app.live_controls.get())
        finally:app.cancel()
