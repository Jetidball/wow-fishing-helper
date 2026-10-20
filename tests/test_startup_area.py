"""Exercise exact legacy startup functions without loading Windows hooks."""
import ast
from pathlib import Path
import threading
import types
import unittest
from unittest.mock import Mock, patch
from visual_targeting.input import Cancelled

class StartupAreaTests(unittest.TestCase):
    def functions(self):
        tree=ast.parse((Path(__file__).parents[1]/'src/setup.py').read_bytes())
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('get_area_of_interest','get_box','get_single_loc','get_pole_loc')]
        env={'logger':types.SimpleNamespace(info=lambda text:None),
             'countdown':Mock(),'pag':types.SimpleNamespace(cancelled=threading.Event()),'Cancelled':Cancelled}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'setup.py','exec'),env)
        return env
    def test_startup_uses_rectangle_polygon_and_does_not_poll_cursor(self):
        env=self.functions()
        points=[(10,10),(100,10),(100,60),(10,60)]
        with patch('visual_targeting.area_picker.request_desktop_area',return_value=points) as picker:
            self.assertEqual(env['get_area_of_interest'](),points)
            self.assertTrue(picker.call_args.kwargs['polygon'])
            self.assertIs(picker.call_args.kwargs['cancelled'],env['pag'].cancelled)
    def test_cancel_exits_instead_of_repeating(self):
        env=self.functions()
        with patch('visual_targeting.area_picker.request_desktop_area',return_value=None) as picker:
            with self.assertRaises(Cancelled):env['get_area_of_interest']()
            picker.assert_called_once()
    def test_box_uses_same_frozen_picker(self):
        env=self.functions()
        with patch('visual_targeting.area_picker.request_desktop_area',return_value=[(1,2),(20,30)]):
            self.assertEqual(env['get_box']('loot'),[(1,2),(20,30)])


    def test_startup_single_location_does_not_read_dry_run_cursor(self):
        env=self.functions()
        with patch('visual_targeting.area_picker.request_desktop_area',return_value=(-100,200)) as picker:
            self.assertEqual(env['get_single_loc']('cast action'),(-100,200))
            self.assertTrue(picker.call_args.kwargs['point'])

    def test_pole_setup_does_not_type_character_panel_hotkey(self):
        env=self.functions()
        with patch('visual_targeting.area_picker.request_desktop_area',return_value=(50,60)):
            self.assertEqual(env['get_pole_loc'](),(50,60))
