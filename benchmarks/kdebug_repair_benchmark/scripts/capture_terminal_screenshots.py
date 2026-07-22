#!/usr/bin/env python3
"""Render trial terminal logs as PNG screenshots for Word reports.

This is intended for VM/SSH benchmark runs where a GUI terminal screenshot is
not always practical.  The PNG preserves the terminal evidence requirement by
showing the actual command log tail used for build/run/judge.
"""

import argparse
import csv
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/Consolas.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
]


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_font(size):
    for candidate in DEFAULT_FONT_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def find_log(log_root, row):
    model = row.get("model_id", "")
    group = row.get("group", "")
    case_id = row.get("case_id", "")
    candidates = [
        log_root / model / group / case_id / "agent_logs" / f"{model}_commands.log",
        log_root / group / case_id / "agent_logs" / f"{model}_commands.log",
        log_root / case_id / model / group / "agent_logs" / f"{model}_commands.log",
        log_root / model / group / case_id / "trial.log",
        log_root / group / case_id / "trial.log",
        log_root / case_id / model / group / "trial.log",
        log_root / f"{case_id}_{model}_{group}.log",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def terminal_image(text, title, out_path, width=1400, height=900, font_size=20):
    font = load_font(font_size)
    small_font = load_font(max(12, font_size - 4))
    bg = (18, 18, 18)
    fg = (228, 228, 228)
    muted = (160, 160, 160)
    green = (99, 200, 118)
    red = (230, 92, 92)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width, 52), fill=(34, 34, 34))
    draw.ellipse((18, 18, 34, 34), fill=red)
    draw.ellipse((44, 18, 60, 34), fill=(236, 189, 75))
    draw.ellipse((70, 18, 86, 34), fill=green)
    draw.text((108, 15), title, font=small_font, fill=fg)

    margin_x = 28
    y = 72
    line_h = int(font_size * 1.35)
    max_chars = 118
    raw_lines = text.splitlines()
    if len(raw_lines) > 36:
        raw_lines = ["... log head omitted; showing final terminal evidence ..."] + raw_lines[-35:]
    lines = []
    for line in raw_lines:
        if not line:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(line, width=max_chars, replace_whitespace=False) or [""])
    for line in lines:
        if y + line_h > height - 24:
            draw.text((margin_x, y), "... truncated ...", font=font, fill=muted)
            break
        color = fg
        upper = line.upper()
        if "PASS" in upper or "HIT GOOD TRAP" in upper or "FINAL_STATUS=PASS" in upper:
            color = green
        elif "FAIL" in upper or "ERROR" in upper or "TIMEOUT" in upper:
            color = red
        draw.text((margin_x, y), line, font=font, fill=color)
        y += line_h
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--log-root", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--require-logs",
        action="store_true",
        help="exit nonzero when any trial log is missing; placeholder PNGs remain diagnostic only",
    )
    args = parser.parse_args()

    rows = read_rows(args.results)
    created = 0
    missing = []
    for row in rows:
        case_id = row.get("case_id", "")
        model = row.get("model_id", "")
        group = row.get("group", "")
        out = args.out_dir / f"{case_id}_{model}_{group}.png"
        if out.exists() and not args.overwrite:
            continue
        log = find_log(args.log_root, row)
        if not log:
            missing.append(f"{case_id}/{model}/{group}")
            placeholder = (
                f"$ benchmark evidence unavailable\n"
                f"case={case_id} model={model} group={group}\n"
                "No terminal log was found for this trial.\n"
                "This report item does not satisfy final delivery evidence.\n"
            )
            terminal_image(placeholder, f"{case_id} {model} {group}", out)
            created += 1
            continue
        text = log.read_text(encoding="utf-8", errors="replace")
        terminal_image(text, f"{case_id} {model} {group}", out)
        created += 1

    print(f"created={created}")
    if missing:
        print("missing_logs=" + ",".join(missing))
        if args.require_logs:
            raise SystemExit(4)


if __name__ == "__main__":
    main()
