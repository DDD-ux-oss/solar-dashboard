import os
import re
import cv2
import sys
import time
import easyocr
import argparse

_reader_cache = None

def get_easyocr_reader(langs=('ch_sim', 'en'), gpu=False):
    global _reader_cache
    if _reader_cache is None:
        _reader_cache = easyocr.Reader(list(langs), gpu=gpu)
    return _reader_cache

def extract_daily_generation_easyocr(img_path, roi=(0.0, 0.0, 0.42, 0.28), save_debug=True):
    """
    从截图左上角区域识别当日发电量。
    返回 (kWh数值或None, 诊断信息dict)
    roi: (x_percent, y_percent, w_percent, h_percent)
    """
    if not os.path.exists(img_path):
        raise FileNotFoundError(f'图片不存在: {img_path}')

    img = cv2.imread(img_path)
    if img is None:
        raise RuntimeError('读取图片失败')

    h, w = img.shape[:2]
    x0 = int(roi[0] * w)
    y0 = int(roi[1] * h)
    x1 = int(min(w, (roi[0] + roi[2]) * w))
    y1 = int(min(h, (roi[1] + roi[3]) * h))
    crop = img[y0:y1, x0:x1]

    # 预处理：灰度 + 放大 + 对比度增强 + 自适应阈值
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    th = cv2.adaptiveThreshold(eq, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 11)

    reader = get_easyocr_reader()
    # detail=1 返回 (bbox, text, confidence)
    results = reader.readtext(th, detail=1, paragraph=False)
    texts = [r[1] for r in results]
    full_text = ' '.join(texts)

    # 优先匹配带单位的数值
    m = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(kWh|MWh|千瓦时|兆瓦时)?',
                  full_text, flags=re.IGNORECASE)
    parsed_val = None
    unit = None
    if m:
        num_str = m.group(1).replace(',', '')
        try:
            parsed_val = float(num_str)
            unit = (m.group(2) or 'kWh').lower()
            if unit in ('mwh', '兆瓦时'):
                parsed_val *= 1000.0
        except Exception:
            parsed_val = None

    # 回退：从各行文本中取最大数字
    if parsed_val is None:
        candidates = []
        for t in texts:
            for s in re.findall(r'\d+(?:\.\d+)?', t):
                try:
                    candidates.append(float(s))
                except Exception:
                    pass
        if candidates:
            parsed_val = max(candidates)
            unit = 'kWh'

    debug_info = {
        'unit': 'kWh' if parsed_val is not None else unit,
        'raw_text': full_text,
        'roi': roi,
        'texts': texts,
        'boxes': [r[0] for r in results],
        'conf': [r[2] for r in results],
    }

    if save_debug:
        base, ext = os.path.splitext(img_path)
        roi_out = f"{base}_ocr_roi{ext}"
        overlay_out = f"{base}_ocr_overlay{ext}"
        try:
            # 保存ROI图片
            cv2.imwrite(roi_out, crop)
            # 画识别框与文字到ROI
            overlay = crop.copy()
            for (bbox, text, conf) in results:
                pts = [(int(p[0]), int(p[1])) for p in bbox]
                for j in range(4):
                    cv2.line(overlay, pts[j], pts[(j + 1) % 4], (0, 255, 0), 2)
                cv2.putText(overlay, f"{text} ({conf:.2f})", pts[0], cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            cv2.imwrite(overlay_out, overlay)
            debug_info['roi_image'] = roi_out
            debug_info['overlay_image'] = overlay_out
        except Exception as e:
            debug_info['save_debug_error'] = str(e)

    return (round(parsed_val, 2) if parsed_val is not None else None), debug_info


def main():
    parser = argparse.ArgumentParser(description='Extract daily generation (kWh) from SEMS screenshot top-left via EasyOCR')
    parser.add_argument('image_path', help='Path to screenshot image (e.g., screenshots/2025-10-26/power_curve_5.png)')
    parser.add_argument('--roi', type=float, nargs=4, default=(0.0, 0.0, 0.42, 0.28), help='ROI as percentages: x y w h')
    parser.add_argument('--gpu', action='store_true', help='Enable GPU for EasyOCR if available')
    parser.add_argument('--langs', nargs='+', default=['ch_sim', 'en'], help='Languages for EasyOCR')
    args = parser.parse_args()

    # 初始化Reader（按用户选择的语言和GPU）
    start = time.time()
    reader = easyocr.Reader(args.langs, gpu=args.gpu)
    global _reader_cache
    _reader_cache = reader
    print(f"EasyOCR Reader initialized in {time.time() - start:.2f}s, langs={args.langs}, gpu={args.gpu}")

    val, info = extract_daily_generation_easyocr(args.image_path, roi=tuple(args.roi), save_debug=True)
    print(f"Parsed kWh: {val}")
    print("Debug info:")
    for k, v in info.items():
        if isinstance(v, (list, tuple)):
            print(f"  {k}: {str(v)[:200]}")
        else:
            print(f"  {k}: {v}")

if __name__ == '__main__':
    main()