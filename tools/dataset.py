"""Recording and labeling only: no clicking, key injection, task execution or focus changes."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from visual_targeting.dataset import annotate, export_yolo, preview, record, validate

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    rec = subs.add_parser("record", help="record color screen crops only; Ctrl+C stops")
    rec.add_argument("--dataset", type=Path, required=True)
    rec.add_argument("--session", required=True)
    rec.add_argument("--cast", required=True)
    rec.add_argument("--region", type=int, nargs=4, metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"), required=True)
    rec.add_argument("--fps", type=float, default=5)
    rec.add_argument("--duration", type=float, default=60)
    rec.add_argument("--max-frames", type=int, default=600)
    ann = subs.add_parser("annotate", help="label saved frames, never capture or send input")
    ann.add_argument("--dataset", type=Path, required=True)
    source = ann.add_mutually_exclusive_group(required=True)
    source.add_argument("--frame")
    source.add_argument("--annotations", type=Path, help="JSON array of annotation updates")
    labels = ann.add_mutually_exclusive_group()
    labels.add_argument("--box", type=float, nargs=4, action="append", metavar=("X", "Y", "WIDTH", "HEIGHT"))
    labels.add_argument("--negative", action="store_true")
    ann.add_argument("--bite", choices=("splash", "no_bite", "unknown"))
    view = subs.add_parser("preview", help="write a PNG overlay; no interactive mouse UI")
    view.add_argument("--dataset", type=Path, required=True)
    view.add_argument("--frame", required=True)
    view.add_argument("--output", type=Path, required=True)
    check = subs.add_parser("validate")
    check.add_argument("--dataset", type=Path, required=True)
    exp = subs.add_parser("export-yolo")
    exp.add_argument("--dataset", type=Path, required=True)
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--val", type=float, default=.2)
    exp.add_argument("--test", type=float, default=.1)
    exp.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            result = {"saved": record(args.dataset, args.session, args.cast, args.region,
                fps=args.fps, duration=args.duration, max_frames=args.max_frames)}
        elif args.command == "annotate":
            if args.annotations:
                if args.box or args.negative or args.bite: raise ValueError("batch annotations cannot be mixed with single-frame flags")
                updates = json.loads(args.annotations.read_text(encoding="utf-8"))
                if not isinstance(updates, list): raise ValueError("annotations must be a JSON array")
            else:
                update = {"frame_id": args.frame}
                if args.box or args.negative:
                    update["boxes"] = [dict(zip(("x", "y", "width", "height"), b), class_id=0, space="frame_pixels") for b in (args.box or [])]
                if args.bite is not None: update["bite"] = None if args.bite == "unknown" else args.bite
                updates = [update]
            result = {"updated": annotate(args.dataset, updates)}
        elif args.command == "preview": result = {"preview": str(preview(args.dataset, args.frame, args.output))}
        elif args.command == "validate":
            data = validate(args.dataset)
            result = {"frames": len(data["frames"]), "sessions": len(data["sessions"]),
                      "reviewed": sum(r["annotation"]["reviewed"] for r in data["frames"])}
        else: result = export_yolo(args.dataset, args.output, val=args.val, test=args.test, seed=args.seed)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result))

if __name__ == "__main__": main()
