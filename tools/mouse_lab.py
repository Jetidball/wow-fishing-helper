"""Local target window. Dry-run by default; no fishing, capture or model imports."""
import argparse
import json
import sys
import time
from pathlib import Path
from threading import Event
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from visual_targeting.geometry import Rect,Letterbox,Transforms
from visual_targeting.guarded_mouse import GuardedMouse
from visual_targeting.windows_mouse import WindowsMouse


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile",type=Path,help="run a second-task profile demo with simulated mouse input only")
    parser.add_argument("--mode",choices=("dry-run","move","single-click"),default="dry-run")
    parser.add_argument("--verify",action="store_true",help="run one bounded test against this window, then exit")
    parser.add_argument("--manual",action="store_true",help="wait for a user press of Run instead of automatically starting verification")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--timeout",type=float,default=15)
    args=parser.parse_args()
    if not 2<=args.timeout<=300:parser.error("timeout must be between 2 and 300 seconds")
    if args.output and args.output.exists():parser.error("output already exists")
    if args.profile:
        if args.mode!="dry-run" or args.output is None:parser.error("profile demo requires dry-run mode and an output directory")
        from visual_targeting.profiles import Profile
        from visual_targeting.local_demo import run_demo
        print(json.dumps(run_demo(Profile.read(args.profile),args.output,show=True,verify=args.verify)))
        return
    api=WindowsMouse()
    # Create the entire Tk window within a PMv2 thread context.
    with api.dpi_scope():
        import tkinter as tk
        root=tk.Tk();root.title("Fishing helper - local mouse verification only")
        root.geometry("620x460+70+70")
        transforms=Transforms();cancelled=Event();controller=None;hits=[];motions=[];report={"mode":args.mode,"passed":False,"live_fishing_enabled":False}
        status=tk.StringVar(value="Mode: "+args.mode+". Esc cancels. Move the pointer to take over.")
        tk.Label(root,textvariable=status,wraplength=590,height=2).pack()
        buttons=tk.Frame(root);buttons.pack()
        canvas=tk.Canvas(root,width=580,height=330,bg="#18202a",highlightthickness=0,bd=0);canvas.pack()
        targets=[(120,100),(450,240)]
        for i,(x,y) in enumerate(targets):
            canvas.create_oval(x-18,y-18,x+18,y+18,fill="#fa6a35",outline="white")
            canvas.create_text(x,y+35,text=f"Target {i+1}: ({x}, {y})",fill="white")
        def changed(event):
            if event.widget in (root,canvas):
                api.revision+=1;transforms.invalidate("window_configured")
        root.bind("<Configure>",changed)
        canvas.bind("<Configure>",changed)
        def received(event):
            hits.append({"x":event.x,"y":event.y,"target":next((i for i,(x,y) in enumerate(targets) if (x-event.x)**2+(y-event.y)**2<=18**2),None)})
        canvas.bind("<ButtonRelease-1>",received)
        def motion(event):
            motions.append({"x":event.x,"y":event.y})
            del motions[:-8]
        canvas.bind("<Motion>",motion)
        canvas.bind("<Enter>",motion)
        def finish():
            report["received_clicks"]=hits
            if args.output:
                args.output.parent.mkdir(parents=True,exist_ok=True)
                with args.output.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2)
            print(json.dumps(report),flush=True)
            root.destroy()
        def stop():
            cancelled.set();transforms.invalidate("cancelled");status.set("Cancelled; close and restart to re-arm")
        root.bind("<Escape>",lambda _:stop())
        root.protocol("WM_DELETE_WINDOW",lambda:(stop(),finish()))
        def run():
            nonlocal controller
            hits.clear();motions.clear()
            try:
                hwnd=api.root(root.winfo_id());window=api.geometry(hwnd);scale=window.dpi/96
                native_canvas=api.geometry(canvas.winfo_id()).client
                crop=Rect((native_canvas.left-window.client.left)/scale,(native_canvas.top-window.client.top)/scale,native_canvas.width/scale,native_canvas.height/scale)
                letterbox=Letterbox.fit(int(native_canvas.width),int(native_canvas.height),640,640)
                transform=transforms.bind(window,crop,letterbox)
                point=targets[0]
                crop_point=(point[0]*native_canvas.width/canvas.winfo_width(),point[1]*native_canvas.height/canvas.winfo_height())
                model=letterbox.crop_to_model(*crop_point)
                controller=GuardedMouse(api,transforms,mode=args.mode,cancelled=cancelled)
                report.update(hwnd=hwnd,dpi=window.dpi,model_point=model,crop_point=point,
                              desktop_point=transform.crop_to_desktop(*crop_point),transform_id=transform.identity,
                              canvas_native=vars(native_canvas),canvas_tk=[canvas.winfo_width(),canvas.winfo_height()],client_native=vars(window.client))
                if not controller.arm():raise RuntimeError(controller.reason)
                target=transform.target(*model,0,time.monotonic())
                if not controller.execute(target,"move"):raise RuntimeError(controller.reason)
                report["movement_verified"]=False
                def next_step():
                    try:
                        report["cursor_after"]=api.cursor()
                        report["tk_pointer_after"]=canvas.winfo_pointerxy()
                        report["canvas_native_after"]=vars(api.geometry(canvas.winfo_id()).client)
                        report["received_movement"]=motions[-1] if motions else None
                        report["movement_verified"]=bool(motions and abs(motions[-1]["x"]-point[0])<=2 and abs(motions[-1]["y"]-point[1])<=2)
                        if args.mode!="dry-run" and not report["movement_verified"]:raise RuntimeError("canvas movement did not reach the known target")
                        if args.mode!="dry-run" and not controller.gate(target):raise RuntimeError(controller.reason)
                        if args.mode=="single-click":
                            fresh=transform.target(*model,1,time.monotonic())
                            if not controller.execute(fresh,"click"):raise RuntimeError(controller.reason)
                            root.after(200,check_click)
                        else:
                            report["passed"]=not hits
                            if args.verify:finish()
                            else:status.set("Movement-only PASS (no canvas clicks)" if args.mode=="move" else "Dry-run PASS; no input issued")
                    except (OSError,ValueError,RuntimeError) as exc:failed(exc)
                def check_click():
                    report["passed"]=len(hits)==1 and hits[0]["target"]==0
                    status.set("Single-click PASS" if report["passed"] else "Single-click delivery mismatch")
                    if args.verify:finish()
                root.after(350,next_step)
            except (OSError,ValueError,RuntimeError) as exc:failed(exc)
        def failed(exc):
            report.update(passed=False,error=str(exc));status.set("Blocked: "+str(exc))
            if args.verify:finish()
        tk.Button(buttons,text="Run one verification",command=lambda:root.after(250,run)).pack(side="left")
        tk.Button(buttons,text="Cancel",command=stop).pack(side="left")
        if args.verify:
            if not args.manual:root.after(1000,run)
            def timeout():
                report.update(passed=False,error="timeout");stop();finish()
            root.after(round(args.timeout*1000),timeout)
        root.mainloop()

if __name__=="__main__":main()
