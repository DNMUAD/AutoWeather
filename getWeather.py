# -*- coding: utf-8 -*-
"""高德天气 API 客户端（零第三方依赖，仅标准库 urllib）

文件位置：d:\\Python_Build\\getWeather.py

接口: https://restapi.amap.com/v3/weather/weatherInfo
  - extensions=base : 返回实况天气 lives（每小时更新多次）
  - extensions=all  : 返回预报天气 forecasts[0].casts（casts[0]=当天, [1]=第二天 ...）

命令行自测：
    python getWeather.py 430523          # 打印归一化后的天气数据(JSON)
    python getWeather.py --check-key     # 检查 config.AMAP_KEY 是否可用
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import console_utf8

API_URL = 'https://restapi.amap.com/v3/weather/weatherInfo'

# 高德常见错误码说明（其余码只显示 info/infocode 原文）
INFOCODE_HINT = {
    '10001': 'Key 不正确或已过期（INVALID_USER_KEY）——必须是【Web服务】类型的 Key',
    '10002': 'Key 已被删除（SERVICE_NOT_AVAILABLE）',
    '10003': '当日调用量已超限（DAILY_QUERY_OVER_LIMIT）',
    '10004': '访问过于频繁（OUT_OF_SERVICE），请降低 QPS',
    '10021': '并发 QPS 超出限制（CUQPS_HAS_EXCEEDED_THE_LIMIT），稍后自动重试即可',
    '10005': 'IP 白名单校验失败（IP_WHITELIST）',
    '10007': '数字签名校验失败（INVALID_USER_SCODE）',
    '10009': 'Key 与绑定平台不符（USERKEY_PLAT_NOMATCH）——请用 Web服务 Key',
    '10012': '该 Key 无此服务权限，请在控制台勾选"天气查询"',
    '10013': 'Key 已过期（USER_KEY_EXPIRED）',
    '10019': '服务未开通（SERVICE_NOT_OPENED）',
    '20000': '请求参数错误（INVALID_PARAMS）',
    '20003': '参数缺失或非法，请检查 city/adcode',
}

WEEKDAY_CN = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

# 触发频次限制的错误码：可以退避重试（其他错误码重试也没用，直接抛出）
RETRYABLE_INFOCODES = {'10004', '10021'}

# 同一个 adcode 的 base / all 两次请求之间的间隔（秒），避免触发 QPS 限制
REQUEST_INTERVAL = 0.5


class WeatherError(RuntimeError):
    """天气数据获取/解析失败的统一异常"""


class WeatherApiError(WeatherError):
    """高德接口返回 status=0"""


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def weekday_cn(date_str: str) -> str:
    """'2026-09-18' -> '星期五'；解析失败返回空字符串"""
    for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
        try:
            return WEEKDAY_CN[datetime.strptime(date_str, fmt).weekday()]
        except (TypeError, ValueError):
            continue
    return ''


def _check_adcode(adcode) -> str:
    adcode = str(adcode or '').strip()
    if not adcode:
        raise WeatherError('adcode 不能为空，请在 config.py 里填写（可用 python amap_adcode.py 邵阳 查询）')
    return adcode


def _build_error(payload: dict) -> str:
    infocode = str(payload.get('infocode', '?'))
    info = payload.get('info', 'UNKNOWN')
    hint = INFOCODE_HINT.get(infocode)
    message = '高德接口返回失败：info=%s, infocode=%s' % (info, infocode)
    if hint:
        message += '（%s）' % hint
    return message


def _request(params: dict, timeout: float = 15, retries: int = 3) -> dict:
    url = API_URL + '?' + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 weather-daily/1.0'})
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode('utf-8', 'replace'))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
                continue
            raise WeatherError('请求高德接口失败（已重试 %d 次）：%s' % (retries, exc)) from exc

        if str(payload.get('status')) != '1':
            infocode = str(payload.get('infocode', '?'))
            if infocode in RETRYABLE_INFOCODES and attempt < retries:
                time.sleep(1.5 * attempt)   # 触发 QPS / 并发限制：退避后重试
                continue
            raise WeatherApiError(_build_error(payload))
        return payload
    raise WeatherError('请求高德接口失败：%s' % last_error)


def fetch_live(adcode, key: str, timeout: float = 15, retries: int = 3) -> dict:
    """实况天气 lives[0]"""
    adcode = _check_adcode(adcode)
    payload = _request({'key': key, 'city': adcode, 'extensions': 'base', 'output': 'JSON'}, timeout, retries)
    lives = payload.get('lives') or []
    if not lives:
        raise WeatherError('adcode=%s 没有返回实况天气，请确认编码是否有效（省/市/区县 adcode 均可）' % adcode)
    return lives[0]


def fetch_casts(adcode, key: str, timeout: float = 15, retries: int = 3) -> tuple[list[dict], str]:
    """预报天气，返回 (casts 列表, 预报发布时间)"""
    adcode = _check_adcode(adcode)
    payload = _request({'key': key, 'city': adcode, 'extensions': 'all', 'output': 'JSON'}, timeout, retries)
    forecasts = payload.get('forecasts') or payload.get('forecast') or []
    if not forecasts:
        return [], ''
    first = forecasts[0]
    casts = [c for c in (first.get('casts') or []) if isinstance(c, dict)]
    return casts, first.get('reporttime', '')


def _normalize_cast(cast: dict) -> dict:
    date = (cast.get('date') or '').strip()
    week = (cast.get('week') or '').strip()
    weekday = weekday_cn(date)
    if not weekday and week.isdigit():
        num = int(week)
        weekday = WEEKDAY_CN[num % 7] if 0 <= num <= 6 else ''
    return {
        'date': date,
        'weekday': weekday,
        'dayweather': (cast.get('dayweather') or '').strip(),
        'nightweather': (cast.get('nightweather') or '').strip(),
        'daytemp': _to_float(cast.get('daytemp')),
        'nighttemp': _to_float(cast.get('nighttemp')),
        'daywind': (cast.get('daywind') or '').strip(),
        'nightwind': (cast.get('nightwind') or '').strip(),
        'daypower': (cast.get('daypower') or '').strip(),
        'nightpower': (cast.get('nightpower') or '').strip(),
    }


def get_weather(adcode, key: str, with_forecast: bool = True,
                timeout: float = 15, retries: int = 3) -> dict:
    """获取某地天气（实况 + 可选预报），返回统一结构的 dict：

    source / adcode / province / city / weather / temperature / humidity /
    winddirection / windpower / reporttime / today / tomorrow / casts /
    forecast_reporttime / warnings
    """
    live = fetch_live(adcode, key, timeout, retries)
    data = {
        'source': '高德地图 AMap',
        'adcode': str(live.get('adcode') or adcode),
        'province': (live.get('province') or '').strip(),
        'city': (live.get('city') or '').strip(),
        'weather': (live.get('weather') or '').strip(),
        'temperature': _to_float(live.get('temperature')),
        'humidity': _to_float(live.get('humidity')),
        'winddirection': (live.get('winddirection') or '').strip(),
        'windpower': (live.get('windpower') or '').strip(),
        'reporttime': (live.get('reporttime') or '').strip(),
        'today': None,
        'tomorrow': None,
        'casts': [],
        'forecast_reporttime': '',
        'warnings': [],
    }

    if not with_forecast:
        return data

    time.sleep(REQUEST_INTERVAL)   # 两次请求之间稍作间隔，避免触发 QPS 限制
    try:
        casts, reporttime = fetch_casts(adcode, key, timeout, retries)
    except WeatherError as exc:
        # 预报失败不影响实况推送，只记录提醒
        data['warnings'].append('预报天气获取失败：%s' % exc)
        return data

    casts = [_normalize_cast(c) for c in casts]
    data['casts'] = casts
    data['forecast_reporttime'] = reporttime
    if not casts:
        data['warnings'].append('预报天气为空（接口未返回 casts）')
        return data

    today_str = datetime.now().strftime('%Y-%m-%d')
    today = next((c for c in casts if c['date'] == today_str), casts[0])
    data['today'] = today
    rest = [c for c in casts if c is not today]
    data['tomorrow'] = rest[0] if rest else (casts[1] if len(casts) > 1 else None)
    return data


def check_key(key: str, timeout: float = 15) -> tuple[bool, str]:
    """检查 Key 是否可用于 Web 服务（顺带验证天气查询权限）"""
    try:
        payload = _request({'key': key, 'city': '110101', 'extensions': 'base', 'output': 'JSON'}, timeout, 1)
    except WeatherApiError as exc:
        return False, str(exc)
    except WeatherError as exc:
        return False, '网络异常：%s' % exc
    lives = payload.get('lives') or []
    if not lives:
        return False, '接口可访问但没有返回数据，请确认该 Key 已勾选"天气查询"服务'
    return True, 'Key 可用：%s %s（数据时间 %s）' % (
        lives[0].get('province', ''), lives[0].get('city', ''), lives[0].get('reporttime', ''))


def main(argv: list[str]) -> int:
    console_utf8.enable()
    import config

    if not argv:
        print(__doc__)
        return 1

    if argv[0] in ('--check-key', '-k'):
        ok, message = check_key(config.AMAP_KEY)
        print(('Key OK: ' if ok else 'Key 不可用: ') + message)
        return 0 if ok else 2

    adcode = argv[0]
    data = get_weather(adcode, config.AMAP_KEY, config.WITH_FORECAST, config.TIMEOUT, config.RETRIES)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
