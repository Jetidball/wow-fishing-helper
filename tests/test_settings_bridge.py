import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from visual_targeting.profiles import Profile,make_detector
from visual_targeting.settings_bridge import import_fishing_settings

class SettingsBridgeTests(unittest.TestCase):
    def profile(self):
        return Profile.read(Path(__file__).parents[1]/'configs/tasks/fishing-v1.json')
    def test_reuses_settings_without_overwriting_normal_or_base_profile(self):
        from settings import Settings
        settings=Settings();settings.img_dir='../images';settings.match_threshold=.83
        settings.canny_thresholds=[60,150];settings.cast_location=(1,2)
        settings.area_of_interest=[(-200,30),(-100,30),(-100,80),(-200,80)]
        base=self.profile();original=json.dumps(base.data,sort_keys=True)
        with tempfile.TemporaryDirectory() as root:
            path,region,mapping=import_fishing_settings(settings,base,root)
            loaded=Profile.read(path)
            self.assertEqual(region,'-200 30 100 50')
            self.assertEqual(loaded.data['confidence'],.83)
            self.assertEqual(loaded.data['model']['canny_thresholds'],[60,150])
            self.assertTrue(loaded.template_path().is_absolute())
            self.assertEqual(loaded.data['allowed_windows'],base.data['allowed_windows'])
            self.assertEqual(settings.cast_location,(1,2))
            self.assertEqual(json.dumps(base.data,sort_keys=True),original)
            again,_,_=import_fishing_settings(settings,base,root)
            self.assertEqual(path,again)
            settings.match_threshold=.85
            changed,_,_=import_fishing_settings(settings,base,root)
            self.assertNotEqual(changed,path)
    def test_preprocessing_uses_imported_canny_for_templates_and_frames(self):
        import cv2 as cv,numpy as np
        data=self.profile().data;data['model']['canny_thresholds']=[60,150]
        with tempfile.TemporaryDirectory() as root:
            image=np.zeros((50,50,3),np.uint8);cv.rectangle(image,(10,10),(35,35),(255,255,255),2)
            cv.imwrite(str(Path(root)/'bobber.jpg'),image)
            data['model']['templates']=root
            detector=make_detector(Profile(data))
            self.assertEqual(detector.inner.canny_thresholds,[60,150])
            self.assertEqual(len(detector.inner.templates),1)
    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_main_tabs_and_explicit_import(self):
        from settings import Settings
        from gui import App
        settings=Settings()
        with tempfile.TemporaryDirectory() as root:
            settings.img_dir=root
            app=App(settings);app.root.withdraw();app.root.update()
            try:
                self.assertEqual([app.pages.tab(t,'text') for t in app.pages.tabs()],
                                 ['Normal fishing','Visual targeting','Neural training','Model results'])
                self.assertEqual(app.pages.index(app.pages.select()),0)
                panel=app.targeting_panel
                with patch('visual_targeting.settings_bridge.import_fishing_settings',return_value=(Path(root)/'profile.json','1 2 3 4',{'source':'normal'})):
                    panel.import_normal_settings()
                self.assertEqual(panel.get('region'),'1 2 3 4')
                self.assertIn('normal',panel.details.get('1.0','end'))
            finally:app.close()
    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_training_arguments_remain_explicit_and_cancellable(self):
        import tkinter as tk
        from visual_targeting.app_gui import TargetingPanel
        from visual_targeting.experiments import TrainConfig
        root=tk.Tk();root.withdraw()
        panel=TargetingPanel(root);root.update()
        try:
            data=self.profile().data;data['model']['backend']='neural'
            with tempfile.TemporaryDirectory() as directory:
                profile=Path(directory)/'profile.json';profile.write_text(json.dumps(data))
                panel.values['profile'].set(str(profile))
                panel.values['config'].set(str(Path(__file__).parents[1]/'configs/task-training.json'))
                panel.values['output'].set('runs/not-executed')
                with patch.object(panel.job,'start') as start:
                    panel.job_command('train')
                    args=start.call_args.args[0]
                    snapshot=Path(args[args.index('--config')+1])
                    try:
                        self.assertEqual(TrainConfig.read(snapshot).epochs,50)
                        self.assertNotIn('--allow-download',args)
                        self.assertNotIn('--live-input',args)
                    finally:snapshot.unlink()
                self.assertEqual(panel.mode.get(),'dry-run')
        finally:panel.shutdown();root.destroy()
