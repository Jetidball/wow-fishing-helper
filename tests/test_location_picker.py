import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from visual_targeting.area_picker import desktop_location

class LocationPickerTests(unittest.TestCase):
    def test_scaled_point_with_negative_monitor_origin(self):
        self.assertEqual(desktop_location((50,25),.5,400,200,-1920,-100),(-1820,-50))
    def test_invalid_or_outside_point(self):
        for position,scale in [((-1,0),1),((400,10),1),((0,0),0)]:
            with self.assertRaises(ValueError):desktop_location(position,scale,400,200,0,0)

    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_all_location_pick_buttons_use_screenshot_and_keep_cancelled_values(self):
        from settings import Settings
        from gui import App
        settings=Settings()
        with tempfile.TemporaryDirectory() as directory:
            settings.img_dir=directory
            app=App(settings);app.root.withdraw();app.root.update()
            try:
                for attr in ('cast_location','loot_location','bait_location','pole_location','hearthstone_location','area_of_interest','chat_area'):
                    with self.subTest(attr=attr):
                        point=attr not in ('area_of_interest','chat_area')
                        value=(100,200) if point else [(10,20),(50,20),(50,60),(10,60)] if attr=='area_of_interest' else [(10,20),(50,60)]
                        with patch.object(app.root,'after',return_value='fake') as timer:
                            app.pick(attr,attr)
                        self.assertTrue(app.busy)
                        self.assertEqual(timer.call_args.args[0],5000)
                        callback=timer.call_args.args[1]
                        with patch('visual_targeting.area_picker.pick_desktop_area') as picker:
                            callback()
                            self.assertEqual(picker.call_args.kwargs['point'],point)
                            picker.call_args.args[2](value)
                        self.assertEqual(getattr(settings,attr),value)
                        self.assertFalse(app.busy)
                        with patch.object(app.root,'after',return_value='fake') as timer:
                            app.pick(attr,attr)
                        with patch('visual_targeting.area_picker.pick_desktop_area') as picker:
                            timer.call_args.args[1]()
                            picker.call_args.args[2](None)
                        self.assertEqual(getattr(settings,attr),value)
                        self.assertFalse(app.busy)
            finally:app.close()

    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_single_click_selection_on_frozen_picture(self):
        import tkinter as tk
        import numpy as np
        from visual_targeting.area_picker import pick_desktop_area
        class Capture:
            monitors=[dict(left=-100,top=20,width=200,height=200)]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def grab(self,monitor):return np.zeros((200,200,4),np.uint8)
        root=tk.Tk();root.withdraw();result=[]
        try:
            with patch('mss.mss',return_value=Capture()):
                top=pick_desktop_area(root,'Fishing ability',result.append,point=True);root.update()
                def widgets(parent):
                    for child in parent.winfo_children():
                        yield child
                        yield from widgets(child)
                button=next(w for w in widgets(top) if w.winfo_class()=='TButton' and w.cget('text')=='Use this location')
                button.invoke();self.assertEqual(result,[])
                canvas=next(w for w in widgets(top) if isinstance(w,tk.Canvas))
                canvas.event_generate('<ButtonPress-1>',x=70,y=90);root.update()
                button.invoke()
                self.assertEqual(result,[(-30,110)])
        finally:root.destroy()
