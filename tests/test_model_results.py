import json,tempfile,unittest
from pathlib import Path
from visual_targeting.model_results import model_results,percent,validation_metrics

class ResultsTests(unittest.TestCase):
    def test_percent_missing_invalid_and_zero(self):
        self.assertEqual(percent(0),'0.0%')
        self.assertEqual(percent(.971),'97.1%')
        for value in (None,'bad',float('nan'),float('inf'),-1,2):self.assertEqual(percent(value),'—')
    def test_validation_history_is_explicit_and_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run=root/'runs/model';(run/'fit').mkdir(parents=True)
            (run/'run.json').write_text(json.dumps({'kind':'training','status':'completed','config':{}}))
            (run/'fit/results.csv').write_text('epoch,metrics/precision(B),metrics/recall(B),metrics/mAP50(B)\n1,0.8,0.4,0.5\n2,0.9,0.6,0.7\n')
            rows,errors=model_results(root)
            self.assertFalse(errors);self.assertEqual(len(rows),1)
            row=rows[0];self.assertEqual(row['precision'],.9);self.assertEqual(row['recall'],.6)
            self.assertEqual(row['scope'],'Validation — last epoch');self.assertIsNone(row['evaluation'])
            self.assertEqual(row['verdict'],'Needs held-out test')
            self.assertFalse((root/'data').exists())
    def test_missing_scores_are_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)/'runs/incomplete';run.mkdir(parents=True)
            (run/'run.json').write_text(json.dumps({'kind':'training','status':'failed'}))
            rows,errors=model_results(directory)
            self.assertIsNone(rows[0]['precision']);self.assertEqual(rows[0]['verdict'],'Training failed')
    def test_gui_help_and_results(self):
        import tkinter as tk
        from tkinter import ttk
        from visual_targeting.app_gui import TargetingPanel
        root=tk.Tk();root.withdraw()
        panel=TargetingPanel(root);root.update()
        try:
            self.assertTrue(hasattr(panel,'model_results'))
            def walk(w):
                for child in w.winfo_children():
                    if isinstance(child,(ttk.Entry,ttk.Combobox,ttk.Checkbutton)):
                        self.assertTrue(getattr(child,'input_description',''),str(child))
                    walk(child)
            walk(panel)
            self.assertEqual(panel.mode.get(),'dry-run')
        finally:panel.shutdown();root.destroy()
