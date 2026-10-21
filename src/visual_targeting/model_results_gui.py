"""Model comparison UI with explicit independent-test vs validation percentages."""
import tkinter as tk
from tkinter import ttk,messagebox
from pathlib import Path
from .model_results import model_results,percent

class ModelResultsPanel(ttk.Frame):
    def __init__(self,parent,root=Path('.'),on_preview=None):
        super().__init__(parent,padding=12)
        self.root_path=Path(root);self.on_preview=on_preview;self.rows=[]
        ttk.Label(self,text='How your trained models are doing',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(self,text='Correct detections = precision (how often it was right). Bobbers found = recall (how many it saw). Higher is better. There is no single overall accuracy percentage.',
                  wraplength=900).pack(anchor='w',pady=4)
        ttk.Label(self,text='Independent test is preferred. Validation-only rows are NOT independent test results. Compare models on the same test set; select a row for all metrics and settings.',
                  wraplength=900).pack(anchor='w',pady=4)
        buttons=ttk.Frame(self);buttons.pack(fill='x',pady=5)
        ttk.Button(buttons,text='Refresh results',command=self.refresh).pack(side='left')
        ttk.Button(buttons,text='Open selected model folder',command=self.open_folder).pack(side='left',padx=5)
        if on_preview:
            ttk.Button(buttons,text='Preview selected (no input)',command=self.preview).pack(side='left')
        table=ttk.Frame(self);table.pack(fill='both',expand=True)
        columns=('model','scope','precision','recall','f1','ap50','verdict')
        self.tree=ttk.Treeview(table,columns=columns,show='headings',height=9,selectmode='browse')
        headings=['Model','Data used','Correct detections','Bobbers found','F1 balance','mAP50','Readiness']
        for column,label,width in zip(columns,headings,[260,175,125,120,100,90,220]):
            self.tree.heading(column,text=label);self.tree.column(column,width=width,minwidth=70,stretch=column in ('model','verdict'))
        vertical=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview)
        horizontal=ttk.Scrollbar(table,orient='horizontal',command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        table.rowconfigure(0,weight=1);table.columnconfigure(0,weight=1)
        self.tree.tag_configure('approved',foreground='#147d3d')
        self.tree.tag_configure('pending',foreground='#95601b')
        self.tree.bind('<<TreeviewSelect>>',lambda event:self.show_details())
        self.status=tk.StringVar();ttk.Label(self,textvariable=self.status,wraplength=900).pack(fill='x',pady=5)
        detail=ttk.Frame(self);detail.pack(fill='both',expand=True)
        self.details=tk.Text(detail,height=11,wrap='word')
        scroll=ttk.Scrollbar(detail,command=self.details.yview);self.details.configure(yscrollcommand=scroll.set)
        self.details.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.refresh()
    def selected(self):
        selection=self.tree.selection()
        return self.rows[int(selection[0])] if selection else None
    def refresh(self):
        selected=self.selected()
        selected_name=selected['name'] if selected else None
        self.rows,errors=model_results(self.root_path)
        self.tree.delete(*self.tree.get_children())
        selection=None
        for index,row in enumerate(self.rows):
            self.tree.insert('','end',iid=str(index),values=(row['name'],row['scope'],percent(row['precision']),
                             percent(row['recall']),percent(row['f1']),percent(row['ap50']),row['verdict']),
                             tags=('approved' if row['verdict'] in ('Approved','Active — approved') else 'pending',))
            if row['name']==selected_name:selection=str(index)
        if self.rows:self.tree.selection_set(selection or '0')
        self.status.set(f'{len(self.rows)} training runs. Missing metrics show —, never a made-up 0%. '+(f'{len(errors)} unreadable metadata files; retry after a running job finishes.' if errors else ''))
        self.show_details()
    def show_details(self):
        row=self.selected();self.details.configure(state='normal');self.details.delete('1.0','end')
        if row is None:
            self.details.insert('end','No training runs yet. Use Neural training → Train my reviewed pictures.')
        else:
            metrics=row['metrics'];val=row['validation'];config=row['config'];report=row['evaluation']
            lines=[f"Model: {row['name']}",f"Training: {row['status']} | Results: {row['scope']} | {row['verdict']}",
                   f"Correct detections (precision): {percent(row['precision'])}",
                   f"Bobbers found (recall): {percent(row['recall'])}",
                   f"F1: {percent(row['f1'])} — balances precision and recall; not catch success.",
                   f"mAP50: {percent(row['ap50'])} | mAP50–95: {percent(row['map50_95'])} — localization scores, not click success.",
                   f"Last validation epoch {val.get('epoch','—')}: correct {percent(val.get('precision'))}, found {percent(val.get('recall'))}. Validation can overestimate unseen-session performance."]
            if report:
                small=metrics.get('small_targets',{});miss=small.get('miss_rate')
                lines.extend([f"Small-bobber miss rate: {percent(miss)} (lower is better; sample count {small.get('count','—')}).",
                              f"False detections per cast: {metrics.get('false_detections_per_cast',{}).get('mean','—')} (count, not a percent; lower is better).",
                              f"Click-point error p95: {metrics.get('click_point_error',{}).get('p95_px','—')} pixels (lower is better; prediction-to-label proxy).",
                              f"Test frames: {metrics.get('frames',len(report.get('frame_ids',[])))} | Test sessions: {', '.join(report.get('sessions',[]))}",
                              f"Comparison group: {row['comparison']} — compare only matching groups/annotations.",
                              f"Required live-use thresholds: {row['run'].get('profile',{}).get('promotion',{})}"])
            else:lines.append('No matching completed independent-test evaluation is available. Do not treat validation as proof of live readiness.')
            lines.extend([f"Training settings: {config.get('epochs','—')} passes, image size {config.get('imgsz','—')}, batch {config.get('batch','—')}, device {config.get('device','—')}.",
                          f"Model file: {row['weights']}",f"Training folder: {row['run_dir']}",
                          f"Evaluation report: {row['evaluation_file'] or 'Not evaluated'}",
                          'Selecting this row or previewing never activates the model.'])
            self.details.insert('end','\n'.join(lines))
        self.details.configure(state='disabled')
    def open_folder(self):
        import os
        row=self.selected()
        if row:os.startfile(str(row['run_dir'].resolve()))
    def preview(self):
        row=self.selected()
        if row and self.on_preview:
            try:self.on_preview(row)
            except Exception as exc:messagebox.showerror('Preview unavailable',str(exc),parent=self)
