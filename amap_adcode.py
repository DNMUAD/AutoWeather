# -*- coding: utf-8 -*-
"""高德城市编码表 AMap_adcode_citycode.xlsx 查询工具（零依赖，仅标准库）

xlsx 本质是 zip + XML，所以不需要 openpyxl/pandas 也能读：
    python amap_adcode.py                 # 打印表头、行数、前几行
    python amap_adcode.py 邵阳             # 按名称搜索 adcode
    python amap_adcode.py 430523          # 按 adcode 反查名称
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

import console_utf8

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
SHEET = 'xl/worksheets/sheet1.xml'
SHARED = 'xl/sharedStrings.xml'
DEFAULT_XLSX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AMap_adcode_citycode.xlsx')

ADCODE_KEYS = ('adcode', '城市编码', '区域编码')
CITYCODE_KEYS = ('citycode', '城市区号', '电话区号')
NAME_KEYS = ('name', 'city', 'district', 'cityname', '中文名', '城市', '城市名', '名称', '地区')


def _col_index(cell_ref: str) -> int:
    """把 A1 / BC12 这样的单元格引用转成 0 开始的列号"""
    letters = re.match(r'([A-Z]+)', cell_ref or '')
    if not letters:
        return 0
    idx = 0
    for ch in letters.group(1):
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if SHARED not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(SHARED))
    return [''.join(t.text or '' for t in si.iter(NS + 't')) for si in root]


def _cell_value(cell: ET.Element, strings: list[str]) -> str:
    ctype = cell.get('t')
    if ctype == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter(NS + 't'))
    v = cell.find(NS + 'v')
    if v is None or v.text is None:
        return ''
    if ctype == 's':
        try:
            return strings[int(v.text)]
        except (ValueError, IndexError):
            return ''
    return v.text


def read_table(path: str = DEFAULT_XLSX) -> tuple[list[str], list[list[str]]]:
    """读取 xlsx 的第一个工作表，返回 (表头, 数据行)"""
    if not os.path.exists(path):
        raise FileNotFoundError(
            '找不到城市编码表：%s\n请把 AMap_adcode_citycode.xlsx 放到脚本同目录，'
            '或直接在高德官网下载"城市编码表"后重命名。' % path
        )
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        sheet_name = SHEET if SHEET in names else next(n for n in names if n.startswith('xl/worksheets/'))
        strings = _shared_strings(zf)
        root = ET.fromstring(zf.read(sheet_name))

    rows: list[list[str]] = []
    for row in root.find(NS + 'sheetData'):
        cells: dict[int, str] = {}
        for cell in row:
            cells[_col_index(cell.get('r', ''))] = _cell_value(cell, strings).strip()
        if not cells:
            continue
        width = max(cells) + 1
        rows.append([cells.get(i, '') for i in range(width)])

    if not rows:
        return [], []
    header = rows[0]
    width = max(len(header), max(len(r) for r in rows))
    header = header + [''] * (width - len(header))
    data = [r + [''] * (width - len(r)) for r in rows[1:]]
    return header, data


def _guess_columns(header: list[str], data: list[list[str]]) -> tuple[int, int, int]:
    """返回 (名称列, adcode列, citycode列) 的下标"""
    lower = [h.strip().lower() for h in header]

    def find(keys: tuple[str, ...]) -> int:
        for i, h in enumerate(lower):
            if h in keys:
                return i
        for i, h in enumerate(lower):
            if any(k in h for k in keys):
                return i
        return -1

    adcode_col = find(ADCODE_KEYS)
    citycode_col = find(CITYCODE_KEYS)
    name_col = find(NAME_KEYS)

    if adcode_col < 0:  # 表头不可用时按内容猜：6 位数字最多的列
        best, best_hits = 0, -1
        for i in range(max(len(header), 1)):
            hits = sum(1 for r in data[:500] if i < len(r) and re.fullmatch(r'\d{6}', r[i]))
            if hits > best_hits:
                best, best_hits = i, hits
        adcode_col = best
    if name_col < 0:
        candidates = [i for i in range(max(len(header), 1)) if i not in (adcode_col, citycode_col)]
        name_col = max(
            candidates,
            key=lambda i: sum(1 for r in data[:500] if i < len(r) and re.search(r'[\u4e00-\u9fff]', r[i])),
            default=0,
        )
    return name_col, adcode_col, citycode_col


def load_records(path: str = DEFAULT_XLSX) -> list[dict[str, str]]:
    """把表读成 [{'name': .., 'adcode': .., 'citycode': ..}, ...]"""
    header, data = read_table(path)
    name_col, adcode_col, citycode_col = _guess_columns(header, data)
    records = []
    for r in data:
        name = r[name_col] if name_col < len(r) else ''
        adcode = r[adcode_col] if adcode_col < len(r) else ''
        citycode = r[citycode_col] if citycode_col < len(r) else ''
        if not adcode:
            continue
        if re.fullmatch(r'\d+(\.0+)?', adcode):
            adcode = str(int(float(adcode)))
        records.append({
            'name': name,
            'adcode': adcode,
            'citycode': '' if citycode in ('\\N', 'N/A') else citycode,
        })
    return records


def search(keyword: str, limit: int = 20, path: str = DEFAULT_XLSX) -> list[dict[str, str]]:
    """按名称 / adcode 搜索，名称完全相等的排前面"""
    keyword = (keyword or '').strip()
    records = load_records(path)
    hits = [r for r in records if keyword and (keyword in r['name'] or keyword == r['adcode'])]
    hits.sort(key=lambda r: (r['name'] != keyword, len(r['name']), r['adcode']))
    return hits[:limit]


def main(argv: list[str]) -> int:
    console_utf8.enable()
    path = DEFAULT_XLSX
    if argv and os.path.exists(argv[0]):
        path = argv.pop(0)

    header, data = read_table(path)
    name_col, adcode_col, citycode_col = _guess_columns(header, data)
    print('文件      : %s' % path)
    print('表头      : %s' % header)
    print('列映射    : 名称=%s列, adcode=%s列, citycode=%s列' % (
        chr(ord('A') + name_col), chr(ord('A') + adcode_col), chr(ord('A') + citycode_col)))
    print('数据行数  : %d' % len(data))
    print('前 3 行   : %s' % data[:3])

    for kw in argv:
        print('')
        print('=== 搜索 "%s" ===' % kw)
        hits = search(kw, path=path)
        if not hits:
            print('  没有匹配，试试更短的关键字（如 "邵阳"）')
        for r in hits:
            print('  adcode=%s  citycode=%s  %s' % (r['adcode'], r['citycode'] or '-', r['name']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
