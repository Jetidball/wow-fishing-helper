import unittest
from visual_targeting.area_picker import desktop_points

class AreaPickerTests(unittest.TestCase):
    def test_rectangle_scaled_negative_monitor(self):
        self.assertEqual(desktop_points((100,60),(10,10),.5,400,200,-1920,-200),
                         [(-1900,-180),(-1720,-80)])
    def test_aoi_is_four_ordered_polygon_corners(self):
        self.assertEqual(desktop_points((10,10),(100,60),1,400,200,0,0,True),
                         [(10,10),(100,10),(100,60),(10,60)])
    def test_empty_selection_rejected(self):
        with self.assertRaises(ValueError):
            desktop_points((10,10),(10,10),1,400,200,0,0,True)
