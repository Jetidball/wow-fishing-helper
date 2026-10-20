import tempfile
import unittest
from pathlib import Path
import numpy as np
import cv2 as cv
from visual_targeting.template_setup import crop_box,save_template

class TemplateSetupTests(unittest.TestCase):
    def test_reverse_scaled_clamped_crop(self):
        self.assertEqual(crop_box((90,60),(-10,10),.5,160,100),(0,20,160,100))
    def test_tiny_and_invalid_scale(self):
        for scale in (0,-1,float('nan')):
            with self.assertRaises(ValueError):crop_box((0,0),(10,10),scale,20,20)
        with self.assertRaises(ValueError):crop_box((1,1),(2,2),1,20,20)
    def test_save_valid_crop_original_resolution_and_no_overwrite(self):
        image=np.zeros((80,100,3),np.uint8)
        cv.rectangle(image,(20,20),(50,50),(255,255,255),-1)
        with tempfile.TemporaryDirectory() as root:
            first=save_template(image,(10,10,60,60),root)
            second=save_template(image,(10,10,60,60),root)
            self.assertNotEqual(first,second)
            self.assertEqual(cv.imread(str(first)).shape,(50,50,3))
    def test_empty_edges_or_bounds_rejected(self):
        image=np.zeros((30,30,3),np.uint8)
        with tempfile.TemporaryDirectory() as root:
            for box in [(0,0,20,20),(-1,0,20,20),(0,0,40,20)]:
                with self.assertRaises(ValueError):save_template(image,box,root)
            self.assertEqual(list(Path(root).iterdir()),[])
