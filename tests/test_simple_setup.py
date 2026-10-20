import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from visual_targeting.fishing_setup import setup_result

class SimpleSetupTests(unittest.TestCase):
    def test_saved_coordinate_mapping(self):
        result=setup_result((10,20,80,90),(50,180),-1920,-200)
        self.assertEqual(result['area_of_interest'],[(-1910,-180),(-1840,-180),(-1840,-110),(-1910,-110)])
        self.assertEqual(result['cast_location'],(-1870,-20))

    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_home_default_missing_setup_and_dry_run_start(self):
        from settings import Settings
        from gui import App
        from visual_targeting.input import desktop,DryRunInput
        settings=Settings()
        with tempfile.TemporaryDirectory() as directory:
            settings.img_dir=directory
            app=App(settings);app.root.withdraw();app.root.update()
            try:
                self.assertFalse(app.live_controls.get())
                self.assertIn('Needs setup',app.ready_text.get())
                with patch.object(app,'guided_setup') as wizard:
                    app.start();wizard.assert_called_once()
                self.assertFalse(app.started)
                settings.area_of_interest=[(0,0),(40,0),(40,40),(0,40)]
                settings.cast_location=(50,50)
                app.simple_auto_loot.set(True)
                with patch.object(settings,'image_files',return_value=['bobber.png']),patch.object(settings,'load_images',side_effect=lambda:setattr(settings,'templates',[object()])),patch.object(settings,'save'),patch.object(app,'close'):
                    app.start()
                self.assertTrue(app.started)
                self.assertIsInstance(desktop.adapter,DryRunInput)
                self.assertEqual(len(desktop.adapter.actions),0)
            finally:
                app.close()
