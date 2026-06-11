import os
import sys
import json
import argparse
from typing import Dict, Any, List

try:
    from nuscenes.nuscenes import NuScenes
except Exception:
    here = os.path.dirname(os.path.abspath(__file__))
    sdk_fallback = os.path.normpath(os.path.join(here, '..', 'nuscenes-devkit', 'nuscenes-devkit-master', 'python-sdk'))
    if os.path.isdir(sdk_fallback) and sdk_fallback not in sys.path:
        sys.path.insert(0, sdk_fallback)
    from nuscenes.nuscenes import NuScenes

from PIL import Image, ImageDraw, ImageFont

CAM_ORDER = [
    'CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT',
    'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT'
]

CAT_COLORS = {
    'vehicle': (228, 26, 28),
    'human': (55, 126, 184),
    'movable_object': (152, 78, 163),
    'static_object': (255, 127, 0),
    'flat': (166, 86, 40),
}


def color_for(cat: str):
    prefix = cat.split('.')[0] if cat and '.' in cat else cat
    return CAT_COLORS.get(prefix, (80, 80, 80))


def short_cat(cat: str) -> str:
    if not cat:
        return ''
    parts = cat.split('.')
    if parts[0] in ('vehicle', 'human') and len(parts) > 1:
        return parts[1]
    return parts[-1]


def draw_box(draw: ImageDraw.ImageDraw, bbox, color, width=3):
    x1, y1, x2, y2 = bbox
    draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=width)


def render_frame(nusc: NuScenes, frame: Dict[str, Any], out_path: str, max_boxes_per_cam: int = 30):
    sample = nusc.get('sample', frame['sample_token'])

    # open images
    imgs: List[Image.Image] = []
    for ch in CAM_ORDER:
        if ch not in sample['data']:
            imgs.append(None)
            continue
        sd = nusc.get('sample_data', sample['data'][ch])
        img_path = os.path.join(nusc.dataroot, sd['filename'])
        if not os.path.isfile(img_path):
            imgs.append(None)
            continue
        imgs.append(Image.open(img_path).convert('RGB'))

    # find max size to standardize columns
    widths = [im.width for im in imgs if im]
    heights = [im.height for im in imgs if im]
    if not widths or not heights:
        return
    W = max(widths)
    H = max(heights)

    # resize to same size and compose 2x3 mosaic
    grid = []
    for im in imgs:
        if im is None:
            grid.append(Image.new('RGB', (W, H), (30, 30, 30)))
        else:
            if im.size != (W, H):
                grid.append(im.resize((W, H)))
            else:
                grid.append(im)

    mosaic = Image.new('RGB', (W*3, H*2), (0, 0, 0))
    positions = [(0,0),(W,0),(2*W,0),(0,H),(W,H),(2*W,H)]
    for (x,y), im in zip(positions, grid):
        mosaic.paste(im, (x,y))

    draw = ImageDraw.Draw(mosaic)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    # draw boxes per channel
    ch_to_offset = {CAM_ORDER[i]: positions[i] for i in range(len(CAM_ORDER))}

    for n in frame['nodes']:
        if n['id'] == 'ego':
            continue
        vis = n.get('visibility') or {}
        cat = n.get('category_name', '')
        color = color_for(cat)
        cnt = 0
        for ch in CAM_ORDER:
            v = vis.get(ch)
            if not v or not v.get('visible'):
                continue
            bbox = v.get('bbox2d')
            if not bbox:
                continue
            (ox, oy) = ch_to_offset[ch]
            x1, y1, x2, y2 = bbox
            draw_box(draw, (ox+x1, oy+y1, ox+x2, oy+y2), color)
            # label
            label = f"{short_cat(cat)}"
            center_uv = v.get('center_uv')
            if center_uv:
                du, dv = ox+center_uv[0], oy+center_uv[1]
            else:
                du, dv = ox+x1, oy+y1-12
            draw.text((du, dv-14), label, fill=color, font=font)
            cnt += 1
            if cnt >= max_boxes_per_cam:
                break

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mosaic.save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataroot', type=str, required=True)
    ap.add_argument('--version', type=str, default='v1.0-mini')
    ap.add_argument('--jsonl', type=str, required=True)
    ap.add_argument('--out_dir', type=str, required=True)
    ap.add_argument('--max_frames', type=int, default=24)
    args = ap.parse_args()

    nusc = NuScenes(version=args.version, dataroot=args.dataroot, verbose=False)

    with open(args.jsonl, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if idx >= args.max_frames:
                break
            frame = json.loads(line)
            out_path = os.path.join(args.out_dir, f"{idx:06d}_{frame['sample_token']}.jpg")
            render_frame(nusc, frame, out_path)
    print(f"Saved mosaics to {args.out_dir}")


if __name__ == '__main__':
    main()
