"""Offline experiment provenance, dataset integrity, and optional pretrained training."""
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
import hashlib
import json
import platform
import subprocess
import sys
import math
from .dataset import validate, image_path, atomic_json, utc_now

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def environment():
    packages = dict(sorted((d.metadata["Name"], d.version) for d in metadata.distributions() if d.metadata["Name"]))
    source = Path(__file__).resolve().parent
    try:
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired): git = None
    return {"python": sys.version, "platform": platform.platform(), "processor":platform.processor(), "machine":platform.machine(), "packages": packages,
            "git_head": git, "source_sha256": {p.name: sha(p) for p in sorted(source.glob("*.py"))}}

def fresh_output(output, dataset):
    output, dataset = Path(output).resolve(), Path(dataset).resolve()
    if output.exists() or output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise ValueError("use a fresh output directory outside the dataset")
    output.mkdir(parents=True)
    return output

def exported_dataset(root):
    root = Path(root).resolve()
    data = validate(root)
    if "export" not in data: raise ValueError("use a validated session-split YOLO export")
    seen = {}
    for row in data["frames"]:
        part = row.get("split")
        if part not in ("train", "val", "test") or not row["annotation"]["reviewed"]:
            raise ValueError("export contains invalid split/unreviewed frames")
        if seen.setdefault(row["session_id"], part) != part:
            raise ValueError("session leakage between splits")
        if data["export"]["session_splits"].get(row["session_id"]) != part:
            raise ValueError("session split metadata disagrees with frame split")
        if row["image"] != f"images/{part}/{row['id']}.png":
            raise ValueError("noncanonical export image path")
        label = image_path(root, f"labels/{part}/{row['id']}.txt")
        lines = [line.split() for line in label.read_text().splitlines() if line.strip()]
        expected = []
        for b in row["annotation"]["boxes"]:
            expected.append([b["class_id"], (b["x"]+b["width"]/2)/row["width"], (b["y"]+b["height"]/2)/row["height"], b["width"]/row["width"], b["height"]/row["height"]])
        if len(lines) != len(expected): raise ValueError("YOLO labels disagree with manifest")
        for line, wanted in zip(lines, expected):
            values = [float(v) for v in line]
            if len(values) != 5 or any(not math.isfinite(v) or abs(v-w)>1e-9 for v,w in zip(values,wanted)):
                raise ValueError("YOLO labels disagree with manifest")
    return data

@dataclass(frozen=True)
class TrainConfig:
    model: str = "weights/yolo11n.pt"
    epochs: int = 50
    imgsz: int = 960
    batch: int = 8
    device: str = "cpu"
    workers: int = 0
    seed: int = 42
    deterministic: bool = True
    amp: bool = False
    optimizer: str = "AdamW"
    lr0: float = .001
    patience: int = 15

    def __post_init__(self):
        for key in ("epochs", "imgsz", "batch"):
            if type(getattr(self,key)) is not int or getattr(self,key) <= 0: raise ValueError(f"{key} must be a positive integer")
        if type(self.seed) is not int or not 0 <= self.seed < 2**31 or type(self.workers) is not int or self.workers < 0:
            raise ValueError("invalid seed/workers")
        if type(self.patience) is not int or self.patience < 0 or not math.isfinite(self.lr0) or self.lr0 <= 0:
            raise ValueError("invalid patience/learning rate")
        if type(self.amp) is not bool or type(self.deterministic) is not bool: raise ValueError("AMP/deterministic must be boolean")
        if not isinstance(self.model,str) or not self.model.endswith(".pt"): raise ValueError("training requires pretrained .pt weights")
        if not isinstance(self.device,str) or not self.device or not isinstance(self.optimizer,str): raise ValueError("invalid device/optimizer")

    @classmethod
    def read(cls,path): return cls(**json.loads(Path(path).read_text()))

def train(dataset, output, config, *, allow_download=False, model_factory=None):
    dataset = Path(dataset).resolve()
    data = exported_dataset(dataset)
    by_split = {s: [r for r in data["frames"] if r["split"] == s] for s in ("train", "val", "test")}
    if not by_split["train"] or not by_split["val"] or not any(r["annotation"]["boxes"] for r in by_split["train"]):
        raise ValueError("training requires independent train/val sessions and positive training boxes")
    weights = Path(config.model)
    if not weights.is_file() and not allow_download: raise ValueError("pretrained weights missing; supply a local .pt or explicitly allow download")
    if not weights.is_file() and (weights.name != config.model or ":" in config.model):
        raise ValueError("download requires a simple official model filename, e.g. yolo11n.pt")
    if model_factory is None:
        try: from ultralytics import YOLO as model_factory
        except ImportError: raise ValueError("install the optional ml extra in a separate environment") from None
    output = fresh_output(output,dataset)
    run = {"kind":"training", "status":"starting", "created_utc":utc_now(), "config":asdict(config),
           "dataset_manifest_sha256":sha(dataset/"manifest.json"), "environment":environment(),
           "train_sessions":sorted({r["session_id"] for r in by_split["train"]}),
           "val_sessions":sorted({r["session_id"] for r in by_split["val"]}), "test_used_for_training":False,
           "live_input_enabled":False}
    atomic_json(output/"run.json",run)
    try:
        model = model_factory(str(weights.resolve()) if weights.is_file() else config.model)
        actual_weights = Path(getattr(model,"ckpt_path",config.model))
        if not actual_weights.is_file(): raise ValueError("cannot identify loaded pretrained checkpoint for provenance")
        run["pretrained_sha256"] = sha(actual_weights)
        for split in ("train","val"):
            (output/(split+".txt")).write_text("\n".join(str(image_path(dataset,r["image"])) for r in by_split[split])+"\n")
        # Generate a train/val-only config; never trust arbitrary data.yaml paths or expose test to fitting.
        (output/"data.yaml").write_text(f"train: {json.dumps(str(output/'train.txt'))}\nval: {json.dumps(str(output/'val.txt'))}\nnames: {json.dumps(data['classes'])}\n")
        kwargs = asdict(config); kwargs.pop("model")
        kwargs.update(data=str(output/"data.yaml"), project=str(output), name="fit", exist_ok=False,
                      pretrained=True, plots=True, save=True, verbose=False)
        run["resolved_train_arguments"] = kwargs
        atomic_json(output/"run.json",run)
        model.train(**kwargs)
        best = output/"fit/weights/best.pt"
        if not best.is_file(): raise ValueError("trainer did not produce best.pt")
        run.update(status="completed", checkpoint=str(best), checkpoint_sha256=sha(best))
        resolved = output/"fit/args.yaml"
        if resolved.exists(): run["trainer_args_yaml"] = resolved.read_text()
        return best
    except BaseException as exc:
        run.update(status="failed", error=str(exc)); raise
    finally:
        torch=sys.modules.get("torch")
        if torch is not None:
            run["torch_runtime"]={"version":torch.__version__,"cuda":torch.version.cuda,
                "cpu_threads":torch.get_num_threads(),"gpu_names":[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
        run["finished_utc"] = utc_now()
        atomic_json(output/"run.json",run)
        (output/"requirements-run.txt").write_text("\n".join(f"{k}=={v}" for k,v in run["environment"]["packages"].items())+"\n")
