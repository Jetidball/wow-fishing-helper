from dataclasses import replace
from pathlib import Path
import sys
from threading import Event
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from visual_targeting.geometry import Rect,WindowGeometry,Letterbox,Transforms,Target
from visual_targeting.guarded_mouse import GuardedMouse

class GeometryTests(unittest.TestCase):
    def window(self,dpi=144):
        return WindowGeometry(42,Rect(-1600,100,1200,900),dpi,Rect(-1920,0,1920,1080),Rect(-1920,0,3840,1080))
    def transform(self,dpi=144):
        registry=Transforms();t=registry.bind(self.window(dpi),Rect(20,30,400,200),Letterbox.fit(600,300,640,640))
        return registry,t
    def test_letterbox_inverse_padding_and_exact_dimensions(self):
        box=Letterbox.fit(600,300,640,640)
        self.assertEqual((box.resized_width,box.resized_height,box.pad_left,box.pad_top),(640,320,0,160))
        self.assertEqual(box.model_to_crop(320,320),(300,150))
        for point in ((0,0),(639,639),(640,320)):
            with self.assertRaises(ValueError):box.model_to_crop(*point)
        odd=Letterbox.fit(123,77,640,640)
        for x,y in ((0,0),(61.5,38.5),(122,76)):
            xx,yy=odd.model_to_crop(*odd.crop_to_model(x,y))
            self.assertAlmostEqual(x,xx);self.assertAlmostEqual(y,yy)
    def test_model_crop_desktop_dpi_and_negative_monitor(self):
        for dpi in (96,120,144,192):
            registry,t=self.transform(dpi)
            target=t.target(320,320,1,10)
            scale=dpi/96
            self.assertEqual((target.x,target.y),(-1600+int(220*scale),100+int(130*scale)))
            cx,cy=t.desktop_to_crop(target.x,target.y)
            self.assertLessEqual(abs(cx-300),1);self.assertLessEqual(abs(cy-150),1)
    def test_move_resize_dpi_monitor_revision_invalidate(self):
        for field,value in (("client",Rect(-1590,100,1200,900)),("client",Rect(-1600,100,1199,900)),("dpi",120),("monitor",Rect(0,0,1920,1080)),("desktop",Rect(-1920,0,4000,1080)),("revision",1),("hwnd",43)):
            registry,t=self.transform();self.assertFalse(registry.valid(t.identity,replace(t.window,**{field:value})))
            self.assertIsNone(registry.active)
            self.assertFalse(registry.valid(t.identity,t.window))
    def test_explicit_invalidation_and_rebind_reject_old_target(self):
        registry,t=self.transform();registry.invalidate("WM_DISPLAYCHANGE")
        new=registry.bind(t.window,t.crop_logical,t.letterbox)
        self.assertNotEqual(t.identity,new.identity)
        self.assertFalse(registry.valid(t.identity,t.window))
    def test_invalid_crop_and_nonfinite_coordinates(self):
        with self.assertRaises(ValueError):Rect(0,0,float("nan"),2)
        with self.assertRaises(ValueError):Letterbox.fit(0,300,640,640)
        with self.assertRaises(ValueError):Transforms().bind(self.window(),Rect(0,0,10000,10),Letterbox.fit(10,10,640,640))
        _,t=self.transform()
        with self.assertRaises(ValueError):t.target(320,0,1,10)
        with self.assertRaises(ValueError):t.crop_to_desktop(600,0)
        with self.assertRaises(ValueError):Target(0,0,t.identity,1,float("nan"))

    def test_explicit_box_transform_and_padding_rejection(self):
        _,t=self.transform()
        mapped=t.box_to_desktop(Rect(160,240,320,160))
        self.assertEqual(mapped,Rect(-1420,220,300,150))
        with self.assertRaises(ValueError):t.box_to_desktop(Rect(0,0,20,200))
    def test_letterbox_image_uses_recorded_padding(self):
        import numpy as np
        box=Letterbox.fit(30,10,64,64)
        image=box.apply(np.zeros((10,30,3),np.uint8))
        self.assertEqual(image.shape,(64,64,3))
        self.assertTrue((image[0]==114).all())
        self.assertTrue((image[box.pad_top+1]==0).all())

class GuardTests(unittest.TestCase):
    window=GeometryTests.window
    transform=GeometryTests.transform
    def adapter(self,mode="single-click"):
        registry,t=self.transform();api=Mock()
        api.geometry.return_value=t.window;api.foreground.return_value=42
        api.cursor.return_value=(-1500,200);api.last_input.return_value=10
        api.buttons_down.return_value=False;api.window_at.return_value=42
        def move(x,y):api.cursor.return_value=(x,y);api.last_input.return_value+=1
        def click():api.last_input.return_value+=1
        api.move.side_effect=move;api.click.side_effect=click
        mouse=GuardedMouse(api,registry,mode=mode,clock=lambda:10.1)
        self.assertTrue(mouse.arm())
        return mouse,api,registry,t,t.target(320,320,1,10)
    def test_single_click_requires_verified_move_and_only_one_click(self):
        mouse,api,_,_,target=self.adapter()
        self.assertFalse(mouse.execute(target,"click"));api.click.assert_not_called()
        self.assertTrue(mouse.arm());self.assertTrue(mouse.execute(target,"move"))
        self.assertTrue(mouse.execute(target,"click"))
        self.assertFalse(mouse.execute(target,"click"));api.click.assert_called_once()
    def test_dry_run_and_movement_only_cannot_click(self):
        for mode in ("dry-run","move"):
            mouse,api,_,_,target=self.adapter(mode)
            self.assertTrue(mouse.execute(target,"move"))
            self.assertFalse(mouse.execute(target,"click"));api.click.assert_not_called()
            if mode=="dry-run":api.move.assert_not_called()
    def test_freshness_future_foreground_bounds_and_cancel_gate_each_action(self):
        cases=(lambda m,a,t,r,x:replace(x,captured_at=9),
               lambda m,a,t,r,x:replace(x,captured_at=11),
               lambda m,a,t,r,x:(setattr(a.foreground,"return_value",99) or x),
               lambda m,a,t,r,x:replace(x,x=1000),
               lambda m,a,t,r,x:(m.cancelled.set() or x))
        for case in cases:
            mouse,api,registry,t,target=self.adapter()
            target=case(mouse,api,t,registry,target)
            self.assertFalse(mouse.execute(target,"move"));api.move.assert_not_called();api.click.assert_not_called()
    def test_window_move_invalidates_and_cannot_click_old_target(self):
        mouse,api,registry,t,target=self.adapter()
        self.assertTrue(mouse.execute(target,"move"))
        api.geometry.return_value=replace(t.window,client=Rect(-1500,100,1200,900))
        self.assertFalse(mouse.execute(target,"click"));self.assertIsNone(registry.active);api.click.assert_not_called()
    def test_foreground_loss_after_verified_move_blocks_click(self):
        mouse,api,_,_,target=self.adapter();self.assertTrue(mouse.execute(target,"move"))
        api.foreground.return_value=99
        self.assertFalse(mouse.execute(target,"click"));api.click.assert_not_called()
    def test_takeover_cursor_or_keyboard_latches_cancellation(self):
        for takeover in ("cursor","keyboard"):
            mouse,api,_,_,target=self.adapter();self.assertTrue(mouse.execute(target,"move"))
            if takeover=="cursor":api.cursor.return_value=(target.x+20,target.y)
            else:api.last_input.return_value+=1
            self.assertFalse(mouse.execute(target,"click"));self.assertTrue(mouse.cancelled.is_set());api.click.assert_not_called()
            self.assertFalse(mouse.arm())
    def test_held_button_occlusion_and_explicit_invalidation_block(self):
        for block in ("button","occluded","invalidated"):
            mouse,api,registry,_,target=self.adapter()
            if block=="button":api.buttons_down.return_value=True
            elif block=="occluded":api.window_at.return_value=77
            else:registry.invalidate("display changed")
            self.assertFalse(mouse.execute(target,"move"));api.move.assert_not_called()
    def test_native_failure_never_retries_click_or_reports_success(self):
        mouse,api,_,_,target=self.adapter();self.assertTrue(mouse.execute(target,"move"))
        api.click.side_effect=OSError("blocked")
        self.assertFalse(mouse.execute(target,"click"));self.assertFalse(mouse.execute(target,"click"));api.click.assert_called_once()
    def test_movement_failure_prevents_click(self):
        mouse,api,_,_,target=self.adapter();api.move.side_effect=None
        self.assertFalse(mouse.execute(target,"move"));self.assertFalse(mouse.execute(target,"click"));api.click.assert_not_called()
    def test_cancellation_after_move_blocks_click(self):
        mouse,api,_,_,target=self.adapter();self.assertTrue(mouse.execute(target,"move"));mouse.cancelled.set()
        self.assertFalse(mouse.execute(target,"click"));api.click.assert_not_called()

class NativePacketTests(unittest.TestCase):
    def test_standard_click_is_one_down_up_pair(self):
        from visual_targeting.windows_mouse import WindowsMouse,INPUT
        import ctypes
        native=WindowsMouse.__new__(WindowsMouse);native.user=Mock();packets=[]
        def send(n,array,size):
            packets.append([array[i].u.mi.dwFlags for i in range(n)])
            self.assertEqual(size,ctypes.sizeof(INPUT));return n
        native.user.SendInput.side_effect=send
        native.click()
        self.assertEqual(packets,[[2,4]])
    def test_partial_click_only_releases_and_never_retries_down(self):
        from visual_targeting.windows_mouse import WindowsMouse
        native=WindowsMouse.__new__(WindowsMouse);native.user=Mock();packets=[]
        def send(n,array,size):
            packets.append([array[i].u.mi.dwFlags for i in range(n)])
            return 1
        native.user.SendInput.side_effect=send
        with self.assertRaises(OSError):native.click()
        self.assertEqual(packets,[[2,4],[4]])

if __name__=="__main__":unittest.main()
