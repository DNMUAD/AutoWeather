# -*- coding: utf-8 -*-
"""天气文案预览（只打印，不发微信）—— 第一步的验证入口

用法：
    python weather_report.py                        # 预览 config.TARGETS 里所有启用的地点
    python weather_report.py 邵阳县                   # 城市名（自动查 AMap_adcode_citycode.xlsx 得 adcode）
    python weather_report.py 430523                  # 也可以直接给 6 位 adcode
    python weather_report.py 邵阳县 --label 老家       # 指定文案里显示的地名
    python weather_report.py 430523 --to 文件传输助手   # 预览时顺带看"接收人"一行（不会真的发送）
    python weather_report.py --style minimal         # 临时换风格 humor/cute/plain/minimal
    python weather_report.py --demo                  # 用内置示例数据预览模板（不联网）
    python weather_report.py --raw                   # 打印归一化后的原始数据(JSON)
    python weather_report.py --list                  # 列出 config.TARGETS 及解析出的地名
    python weather_report.py --check-key             # 检查高德 Key 是否可用
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import amap_adcode
import config
import console_utf8
import getWeather
import weather_template


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='天气文案预览（不发微信）')
    parser.add_argument('city', nargs='?', help='地点：6 位 adcode（430523）或城市名（邵阳县）')
    parser.add_argument('--adcode', help='临时指定城市 adcode，例如 430523')
    parser.add_argument('--label', help='文案里显示的地点名（不填则用城市名）')
    parser.add_argument('--to', help='预览用的接收人名称（仅影响打印，不会真的发送）')
    parser.add_argument('--style', help='文案风格：humor / cute / plain / minimal')
    parser.add_argument('--demo', action='store_true', help='用内置示例数据预览模板（不联网）')
    parser.add_argument('--raw', action='store_true', help='打印归一化后的原始数据(JSON)')
    parser.add_argument('--list', action='store_true', help='列出 config.TARGETS 及解析出的地名')
    parser.add_argument('--check-key', action='store_true', help='检查高德 Key 是否可用')
    return parser.parse_args(argv)


def resolve_city(value: str) -> tuple[str, str | None]:
    """'430523' 原样返回；'邵阳县' 则查 AMap_adcode_citycode.xlsx，返回 (adcode, 地名)"""
    value = (value or '').strip()
    if re.fullmatch(r'\d{6}', value):
        return value, None
    hits = amap_adcode.search(value, limit=5)
    if not hits:
        raise SystemExit('城市编码表里找不到 "%s"。\n可以先运行：python amap_adcode.py %s 查看候选，或者直接填 6 位 adcode。'
                         % (value, value))
    exact = [h for h in hits if h['name'] == value]
    hit = exact[0] if exact else hits[0]
    if not exact:
        others = '、'.join('%s(%s)' % (h['name'], h['adcode']) for h in hits[1:4])
        print('提示："%s" 不是精确匹配，已选用 %s(adcode=%s)%s' % (
            value, hit['name'], hit['adcode'], ('，其他候选：' + others) if others else ''))
    return hit['adcode'], hit['name']


def collect_targets(args: argparse.Namespace) -> list[dict]:
    """命令行指定了地点就用命令行，否则用 config.TARGETS 里启用的项"""
    value = args.adcode or args.city
    if value:
        adcode, name = resolve_city(value)
        return [{'label': args.label or name or '', 'adcode': adcode, 'to': args.to or '', 'enabled': True}]
    return [dict(t, to=args.to or t.get('to')) for t in config.TARGETS if t.get('enabled', True)]


def fetch_and_render(target: dict, style: str | None = None, raw: bool = False) -> tuple[dict, str]:
    """取数据 + 渲染文案，返回 (归一化数据, 要发送/打印的文本)

    这是"天气文案"的唯一出口：weather_report.py（预览）和 sendmsg.py（发送）都调这里，
    保证"预览看到的内容"和"实际发出去的内容"完全一致。style 不传则用 config.STYLE。
    """
    style = weather_template.normalize_style(style or config.STYLE)
    data = getWeather.get_weather(
        target.get('adcode'), config.AMAP_KEY, config.WITH_FORECAST, config.TIMEOUT, config.RETRIES)
    if raw:
        return data, json.dumps(data, ensure_ascii=False, indent=2)
    text = weather_template.build_message(
        data, style=style, show_source=config.SHOW_REPORT_TIME, label=target.get('label') or None)
    return data, text


def show_targets() -> int:
    """列出 config.TARGETS，并把 adcode 反向解析成地名（方便确认配置写对了）"""
    if not config.TARGETS:
        print('config.TARGETS 是空的')
        return 1
    print('config.py 里的发送目标：')
    for index, target in enumerate(config.TARGETS, 1):
        adcode = str(target.get('adcode') or '')
        try:
            hits = amap_adcode.search(adcode, limit=1)
            name = hits[0]['name'] if hits else '（编码表里查不到）'
        except FileNotFoundError:
            name = '（读不到 AMap_adcode_citycode.xlsx）'
        print('  %d) 启用=%-5s adcode=%-8s 地名=%-10s 接收人=%-12s label=%s' % (
            index, str(target.get('enabled', True)), adcode, name,
            target.get('to') or '-', target.get('label') or '-'))
    return 0


def run_demo(args: argparse.Namespace, style: str) -> int:
    weather = weather_template.DEMO_WEATHER
    if args.raw:
        print(json.dumps(weather, ensure_ascii=False, indent=2))
        return 0
    print('（以下为内置示例数据预览，不调用接口）')
    print('')
    print(weather_template.build_message(weather, style=style, label=args.label or '邵阳县'))
    return 0


def main(argv: list[str]) -> int:
    console_utf8.enable()
    args = parse_args(argv)
    style = weather_template.normalize_style(args.style or config.STYLE)

    if args.check_key:
        ok, message = getWeather.check_key(config.AMAP_KEY)
        print(('Key OK: ' if ok else 'Key 不可用: ') + message)
        return 0 if ok else 2

    if args.list:
        return show_targets()

    if args.demo:
        return run_demo(args, style)

    targets = collect_targets(args)
    if not targets:
        print('config.TARGETS 里没有启用的地点（把 enabled 改成 True 即可）')
        return 1

    failed = 0
    for target in targets:
        adcode = str(target.get('adcode') or '')
        try:
            data, text = fetch_and_render(target, style, raw=args.raw)
        except getWeather.WeatherError as exc:
            failed += 1
            print('=' * 46)
            print('地点：%s   adcode：%s' % (target.get('label') or '（未指定地名）', adcode))
            print('=' * 46)
            print('❌ 获取失败：%s' % exc)
            print('   排查建议：')
            print('   1) python getWeather.py --check-key              （确认 Key 可用）')
            print('   2) python amap_adcode.py %s      （确认 adcode 是否正确）' % adcode)
            print('')
            continue

        for warning in data.get('warnings') or []:
            print('⚠️ [提示] %s' % warning, file=sys.stderr)

        # 地名优先取 config/--label，其次用接口返回的城市名
        place = target.get('label') or data.get('city') or adcode
        header = '地点：%s   adcode：%s' % (place, data.get('adcode') or adcode)
        if target.get('to'):
            header += '   接收人：%s' % target['to']
        header += '   风格：%s' % style
        print('=' * 46)
        print(header)
        print('=' * 46)
        print(text)
        print('')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
