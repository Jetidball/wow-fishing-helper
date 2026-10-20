"""Optional offline neural backend. Importing this module never imports desktop input."""
from pathlib import Path
import math

class NeuralDetector:
    def __init__(self, weights, *, device="cpu", imgsz=960, score_floor=.001, model_factory=None):
        if not Path(weights).is_file(): raise ValueError("evaluation requires local checkpoint weights")
        if not 0 <= score_floor <= 1 or imgsz <= 0: raise ValueError("invalid neural inference configuration")
        self.device, self.imgsz, self.score_floor = device, imgsz, score_floor
        self.torch = None
        if model_factory is None:
            try:
                import torch
                from ultralytics import YOLO as model_factory
            except ImportError: raise ValueError("install optional ml dependencies for neural inference") from None
            self.torch = torch
            if device != "cpu":
                index = int(device.removeprefix("cuda:"))
                if not torch.cuda.is_available() or index >= torch.cuda.device_count(): raise ValueError("requested CUDA device unavailable")
        self.model = model_factory(str(Path(weights).resolve()))
        names=getattr(self.model,"names",{})
        if names not in ({0:"bobber"},["bobber"]):
            raise ValueError("evaluation checkpoint must be fine-tuned with exactly class 0 = bobber")

    def sync(self):
        if self.torch is not None and self.device != "cpu": self.torch.cuda.synchronize(self.device if self.device.startswith("cuda:") else int(self.device))

    def predict(self, frame):
        # Ultralytics maps letterboxed predictions back into the original input image.
        result = self.model.predict(source=frame.pixels.copy(), device=self.device, imgsz=self.imgsz,
                                    conf=self.score_floor, classes=[0], save=False, show=False, verbose=False)[0]
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        scores = result.boxes.conf.detach().cpu().numpy()
        predictions=[]
        for (x1,y1,x2,y2),score in zip(boxes,scores):
            values=[float(v) for v in (x1,y1,x2,y2,score)]
            if not all(math.isfinite(v) for v in values): raise ValueError("neural backend returned nonfinite detection")
            x1,y1,x2,y2,score=values
            if not (0 <= x1 < x2 <= frame.bounds.width and 0 <= y1 < y2 <= frame.bounds.height and 0 <= score <= 1):
                raise ValueError("neural backend returned invalid frame-local box")
            predictions.append({"box":[x1,y1,x2,y2],"score":score,
                                "point":[int((x1+x2)/2),int((y1+y2)/2)]})
        return predictions
