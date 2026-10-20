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

    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_guided_three_selections_save_without_desktop_input(self):
        import tkinter as tk
        import types
        import numpy as np
        from visual_targeting.fishing_setup import open_fishing_setup
        class Capture:
            monitors=[dict(left=-100,top=20,width=200,height=200)]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def grab(self,monitor):return np.zeros((200,200,4),np.uint8)
        root=tk.Tk();root.withdraw();result=[]
        try:
            with patch('mss.mss',return_value=Capture()),patch('visual_targeting.fishing_setup.save_template',return_value=Path('bobber.png')) as save:
                top=open_fishing_setup(root,'images',result.append);root.update()
                def widgets(parent):
                    for child in parent.winfo_children():
                        yield child
                        yield from widgets(child)
                def button(text):
                    return next(w for w in widgets(top) if w.winfo_class()=='TButton' and w.cget('text')==text)
                canvas=next(w for w in widgets(top) if isinstance(w,tk.Canvas))
                def drag(a,b):
                    canvas.event_generate('<ButtonPress-1>',x=a[0],y=a[1])
                    canvas.event_generate('<ButtonRelease-1>',x=b[0],y=b[1])
                    root.update()
                drag((10,10),(150,150));button('Next').invoke()
                drag((30,30),(60,60));button('Next').invoke()
                canvas.event_generate('<ButtonPress-1>',x=170,y=180);root.update()
                button('Save setup').invoke()
                self.assertEqual(result,[])  # Auto Loot confirmation is required.
                next(w for w in widgets(top) if w.winfo_class()=='TCheckbutton').invoke()
                button('Save setup').invoke()
                self.assertEqual(result[0]['cast_location'],(70,200))
                self.assertEqual(result[0]['area_of_interest'][0],(-90,30))
                save.assert_called_once()
        finally:root.destroy()
