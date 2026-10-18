# -*- coding: utf-8 -*-
"""把天气数据渲染成一段（有趣的）推送文案

风格: humor(幽默吐槽) / cute(卖萌可爱) / plain(正经简洁) / minimal(极简)
入口: build_message(weather_dict, style='humor', ...)
"""

from __future__ import annotations

import random
import re
from datetime import datetime

import console_utf8

# 时间段问候
GREETINGS = {
    'humor': {
        'morning': ['🌅 早，天气情报已送达，请查收', '☀️ 起床啦，先看一眼天气再决定穿什么'],
        'afternoon': ['🌤 下午好，插播一条天气', '🌞 午后的天气情报送到'],
        'evening': ['🌙 晚上好，明天的天气我先替你看了', '🌜 晚间天气播报时间'],
    },
    'cute': {
        'morning': ['🌻 早安鸭～今天的天气小报告来啦', '🐣 早上好呀，天气小助手报到'],
        'afternoon': ['🍀 下午好鸭，天气情报请签收', '🐰 午安～天气小报告悄悄送到'],
        'evening': ['🌛 晚上好鸭，明天天气先剧透给你', '⭐️ 晚安前，先看天气小报告'],
    },
    'plain': {
        'morning': ['【天气播报】', '【今日天气】'],
        'afternoon': ['【天气播报】', '【今日天气】'],
        'evening': ['【天气播报】', '【明日天气提示】'],
    },
}

STYLES = ('humor', 'cute', 'plain', 'minimal')

# 内部占位符：表示"这里需要一个空行"；普通空字符串('')表示"这段没有内容，不要这一行"
BLANK = '\x00'

# 天气现象 -> 吐槽文案（按列表顺序匹配，先匹配到的胜出，所以严重的放前面）
WEATHER_COMMENTS = [
    (('大暴雨', '暴雨'), {
        'humor': '🌊 暴雨预警式的雨，出门请自带船桨，非必要不出门',
        'cute': '🌊 雨好大好大呀，乖乖待在屋里好不好～',
        'plain': '⚠️ 暴雨，建议减少外出，注意积水路段',
    }),
    (('大雨',), {
        'humor': '🌧 大雨级别，伞是你的好朋友，袜子是你的牺牲品',
        'cute': '🌧 雨有点大哦，伞伞记得带上～',
        'plain': '🌧 大雨，出门带伞，注意路面湿滑',
    }),
    (('中雨',), {
        'humor': '🌧 中雨持续输出，裤子下摆大概率会湿，接受命运吧',
        'cute': '🌧 中等雨量，小伞伞可以上班啦',
        'plain': '🌧 中雨，建议携带雨具',
    }),
    (('雷阵雨', '雷雨', '雷'), {
        'humor': '⛈ 雷阵雨，老天爷今天情绪不太稳定，别站树下当避雷针',
        'cute': '⛈ 打雷啦，抱抱自己，别站树底下哦',
        'plain': '⛈ 雷阵雨，注意避雷，减少户外活动',
    }),
    (('阵雨',), {
        'humor': '🌦 阵雨：随机掉落式降水，出门带伞属于理性投资',
        'cute': '🌦 偶尔会下一点雨，伞伞带着不亏～',
        'plain': '🌦 有阵雨，建议随身带伞',
    }),
    (('冻雨', '雨夹雪'), {
        'humor': '🧊 雨夹雪/冻雨，路面自带溜冰场效果，走路请用企鹅步',
        'cute': '🧊 又下雨又下雪，路上滑滑的，慢一点点走',
        'plain': '🧊 雨夹雪/冻雨，路面湿滑结冰，注意防滑',
    }),
    (('大暴雪', '暴雪', '大雪'), {
        'humor': '❄️ 大雪出行，建议启动熊系过冬模式，能不出门就不出门',
        'cute': '❄️ 雪好大呀！记得穿厚厚，脚脚别冻着',
        'plain': '❄️ 大雪，注意保暖与交通安全',
    }),
    (('中雪', '小雪'), {
        'humor': '🌨 下雪了，浪漫归浪漫，鞋底打滑也是真的',
        'cute': '🌨 有雪花飘呀飘，围巾帽子安排上～',
        'plain': '🌨 有雪，注意保暖与路面湿滑',
    }),
    (('雪',), {
        'humor': '❄️ 有雪，拍照可以，摔跤不用',
        'cute': '❄️ 下雪雪啦，注意保暖哦',
        'plain': '❄️ 有降雪，注意保暖',
    }),
    (('冰雹',), {
        'humor': '🧊 冰雹，车别停露天，头别伸窗外，别的没了',
        'cute': '🧊 有冰雹，要躲进屋里哦',
        'plain': '🧊 冰雹天气，注意人身与车辆安全',
    }),
    (('强沙尘暴', '沙尘暴', '扬沙', '浮尘', '沙尘'), {
        'humor': '🏜 沙尘天气，口罩戴好，今天别去擦车',
        'cute': '🏜 空气里有沙沙，口罩记得戴～',
        'plain': '🏜 沙尘天气，佩戴防尘口罩，减少外出',
    }),
    (('雾',), {
        'humor': '🌫 有雾，能见度感人，开车记得开雾灯，看谁都是熟人',
        'cute': '🌫 雾蒙蒙的，出门慢慢走，注意安全呀',
        'plain': '🌫 有雾，能见度低，行车注意安全',
    }),
    (('霾',), {
        'humor': '😷 有霾，口罩是今天的时尚单品',
        'cute': '😷 空气不太干净，口罩口罩～',
        'plain': '😷 有霾，建议戴口罩，减少户外运动',
    }),
    (('阴',), {
        'humor': '☁️ 阴天，天空在划水，你也不用太有心理负担',
        'cute': '☁️ 阴阴的天气，心情也要亮亮的哦',
        'plain': '☁️ 阴天，体感偏凉，注意增减衣物',
    }),
    (('多云',), {
        'humor': '⛅️ 多云，太阳摸鱼中，适合出门但别指望蓝天大片',
        'cute': '⛅️ 云朵多多，出门散散步也不错呀',
        'plain': '⛅️ 多云，天气较为舒适',
    }),
    (('晴',), {
        'humor': '☀️ 晴天，阳光管够，防晒别偷懒',
        'cute': '☀️ 晴晴的天气，适合出门玩耍呀',
        'plain': '☀️ 晴天，注意防晒补水',
    }),
]

DEFAULT_WEATHER_COMMENT = {
    'humor': '🤔 天气有点不按套路出牌，出门前再瞄一眼窗外',
    'cute': '🤔 天气怪怪的，出门看一眼窗外再走哦',
    'plain': '天气情况请以实时为准',
}


# 温度 -> 穿衣建议（从高温往低温匹配；文案里不写死温度区间，避免和"今天 xx~xx°C"打架）
TEMP_ADVICE = [
    (35, {
        'humor': '🥵 35°C+，这条命是空调给的，能不出门都是英雄',
        'cute': '🥵 好热好热，多喝水水，别中暑啦',
        'plain': '高温天气，防暑降温，避免午后长时间户外活动',
    }),
    (30, {
        'humor': '🥵 热得挺认真，短袖短裤冰饮齐上，走两步就是汗蒸',
        'cute': '🥵 有点热哦，多喝水、少在太阳下站着',
        'plain': '偏热，建议清凉着装，注意补水',
    }),
    (25, {
        'humor': '😎 温度很友好，最舒服的档位，短袖走天下',
        'cute': '😎 刚刚好的温度，穿短袖就很好看',
        'plain': '温度适宜，短袖单衣即可',
    }),
    (20, {
        'humor': '🧥 温度刚好，长袖薄外套走起，风一吹也不慌',
        'cute': '🧥 有一点点凉，加件薄外套暖暖的',
        'plain': '建议长袖加薄外套',
    }),
    (15, {
        'humor': '🧣 有点凉，外套安排上，别硬撑',
        'cute': '🧣 有点凉凉，外套不要偷懒不穿哦',
        'plain': '偏凉，建议穿外套',
    }),
    (10, {
        'humor': '🧥 秋意上来了，秋衣秋裤的社交距离正在缩短',
        'cute': '🧥 凉凉的，穿厚一点点，别感冒了',
        'plain': '较凉，建议穿厚外套',
    }),
    (5, {
        'humor': '🥶 冷得挺认真，羽绒服可以出场了',
        'cute': '🥶 冷冷哒，羽绒服和围巾都要哦',
        'plain': '寒冷，注意保暖，穿厚外套',
    }),
    (0, {
        'humor': '🧊 冷飕飕的，把手揣兜里，风度和温度选温度',
        'cute': '🧊 好冷呀，手套帽子围巾全套上',
        'plain': '寒冷，注意防寒保暖',
    }),
    (-999, {
        'humor': '🥶 零下啦，出门是勇者行为，能躺就躺',
        'cute': '🥶 冻冻的天气，把自己裹成小球再出门',
        'plain': '严寒，尽量减少户外活动',
    }),
]

# 结尾彩蛋
EGGS = {
    'humor': [
        '（今日彩蛋：别的话我不保证，带伞这句我是认真的）',
        '（今日彩蛋：天气我不负责，心情你负责）',
        '（今日彩蛋：记得吃早饭，胃比天气更需要被善待）',
        '（今日彩蛋：不管天气怎样，你今天都值得被夸一句）',
    ],
    'cute': [
        '（今日彩蛋：今天也要开开心心呀～）',
        '（今日彩蛋：记得喝水水，摸摸头）',
        '（今日彩蛋：你是今天最好看的那个！）',
    ],
    'plain': [
        '（数据仅供参考，请以实际天气为准）',
        '（如与实况不符，请以当地气象台发布为准）',
    ],
}

RAIN_WORDS = ('雨', '雪', '冰雹', '冻雨')

STYLE_ALIASES = {
    '幽默': 'humor', '吐槽': 'humor', 'humor': 'humor',
    '可爱': 'cute', '卖萌': 'cute', 'cute': 'cute',
    '正经': 'plain', '简洁': 'plain', 'plain': 'plain',
    '极简': 'minimal', '精简': 'minimal', '最短': 'minimal',
    'minimal': 'minimal', 'simple': 'minimal', 'short': 'minimal',
}


def normalize_style(style: str) -> str:
    style = (style or 'humor').strip().lower()
    return STYLE_ALIASES.get(style, 'humor')


def _format_temp(value) -> str:
    if value is None:
        return '-'
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return '%.1f' % value


def _temp_range(cast: dict) -> tuple[float | None, float | None]:
    """返回 (低温, 高温)

    接口给的是 nighttemp / daytemp，正常是 nighttemp <= daytemp，
    但极端情况下可能反过来，这里统一按大小排序，避免显示成 "20~-1°C"。
    """
    night, day = cast.get('nighttemp'), cast.get('daytemp')
    if night is None or day is None:
        return night, day
    return (night, day) if night <= day else (day, night)


def _period(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if hour < 11:
        return 'morning'
    if hour < 18:
        return 'afternoon'
    return 'evening'


def _match_comment(weather: str, style: str) -> str:
    weather = weather or ''
    for keywords, comments in WEATHER_COMMENTS:
        if any(word in weather for word in keywords):
            return comments[style]
    return DEFAULT_WEATHER_COMMENT[style]


def _temp_advice(temp, style: str) -> str:
    if temp is None:
        return ''
    for limit, advice in TEMP_ADVICE:
        if temp >= limit:
            return advice[style]
    return ''


def _wind_level(power: str) -> int | None:
    """'≤3' -> 3, '4' -> 4, '5-6' -> 6, 取最大等级"""
    numbers = [int(n) for n in re.findall(r'\d+', power or '')]
    return max(numbers) if numbers else None


def _wind_advice(power: str, style: str) -> str:
    level = _wind_level(power)
    if level is None:
        return ''
    if level >= 6:
        return {
            'humor': '🌪 风力 %d 级，瘦子请结伴出行，帽子是留不住的' % level,
            'cute': '🌪 风好大呀，抓紧帽子和伞伞',
            'plain': '🌪 风力较大（%d 级），注意高空坠物' % level,
        }[style]
    if level >= 4:
        return {
            'humor': '💨 风力 %d 级，发型这种事今天随缘' % level,
            'cute': '💨 有点风哦，头发会飞起来那种',
            'plain': '💨 有风（%d 级），注意防风' % level,
        }[style]
    return ''


def _rain_advice(*weathers: str) -> str:
    text = ' '.join(w for w in weathers if w)
    if '雪' in text or '冰雹' in text:
        return '☂ 有降水，伞 + 防滑鞋，双保险'
    if any(word in text for word in RAIN_WORDS):
        return '☂ 有雨，出门记得带伞，别当"淋雨侠"'
    return ''


def _humidity_comment(humidity, style: str) -> str:
    if humidity is None:
        return ''
    if humidity >= 85:
        return {'humor': '💧 湿度 %.0f%%，空气有点"糊"，体感比温度更难熬' % humidity,
                'cute': '💧 潮潮的，衣服可能干不透哦',
                'plain': '💧 湿度较高，体感闷热'}[style]
    if humidity <= 30:
        return {'humor': '💧 湿度只有 %.0f%%，记得给自己补水' % humidity,
                'cute': '💧 干干哒，多喝水水',
                'plain': '💧 空气干燥，注意补水保湿'}[style]
    return ''


def _gap_advice(daytemp, nighttemp, style: str) -> str:
    if daytemp is None or nighttemp is None:
        return ''
    gap = abs(daytemp - nighttemp)
    if gap < 8:
        return ''
    return {
        'humor': '🧣 昼夜温差 %.0f°C，早晚加件外套，别让感冒钻空子' % gap,
        'cute': '🧣 早晚温差 %.0f°C，出门带件外套暖暖的' % gap,
        'plain': '🧣 昼夜温差 %.0f°C，注意早晚增减衣物' % gap,
    }[style]


def _wind_text(direction: str, power: str) -> str:
    if direction and power:
        return '%s风 %s 级' % (direction, power)
    if power:
        return '风力 %s 级' % power
    if direction:
        return '%s风' % direction
    return ''


def _cast_line(prefix: str, cast: dict) -> str:
    day = cast.get('dayweather') or ''
    night = cast.get('nightweather') or ''
    low, high = _temp_range(cast)
    temp = ''
    if low is not None and high is not None:
        temp = '，%s~%s°C' % (_format_temp(low), _format_temp(high))
    elif high is not None:
        temp = '，最高 %s°C' % _format_temp(high)
    text = '%s %s%s' % (prefix, day or '—', temp)
    if night and night != day:
        text += '（夜里转%s）' % night
    return text


def _cast_short(prefix: str, cast: dict) -> str:
    """极简版预报行，例如：📆 今天 多云 19~25°C"""
    day = cast.get('dayweather') or ''
    low, high = _temp_range(cast)
    if low is not None and high is not None:
        return '%s %s %s~%s°C' % (prefix, day, _format_temp(low), _format_temp(high))
    if high is not None:
        return '%s %s %s°C' % (prefix, day, _format_temp(high))
    return '%s %s' % (prefix, day)


def _minimal_advice(weather: dict, today: dict) -> str:
    """极简风只保留最必要的一条提醒；没有需要提醒的就返回空字符串

    优先级：下雪/冰雹 > 下雨 > 大风 > 高温 > 严寒
    （穿衣/早晚温差已由 👕 那一行负责，这里不重复）
    """
    joined = ' '.join(t for t in (weather.get('weather') or '',
                                  today.get('dayweather') or '',
                                  today.get('nightweather') or '') if t)
    if '雪' in joined or '冰雹' in joined:
        return '☂ 有雪，注意保暖防滑'
    if any(word in joined for word in RAIN_WORDS):
        return '☂ 记得带伞'

    level = _wind_level(weather.get('windpower') or today.get('daypower') or '')
    if level is not None and level >= 6:
        return '🌪 风大，注意安全'

    _, high = _temp_range(today)
    if high is None:
        high = weather.get('temperature')
    if high is not None and high >= 35:
        return '🥵 高温，注意防暑'
    if high is not None and high <= 0:
        return '🧊 严寒，注意防寒'
    return ''


# 极简风穿衣：按当日最高温匹配（从高温往低温），文案尽量短
# 注意：湿度修正见下方 _humidity_note（先看湿度，再套这里的温度档）
MINIMAL_CLOTHES = [
    (35, '背心短裤，怎么凉快怎么来'),
    (30, '短袖 + 短裤'),
    (25, '短袖'),
    (20, '长袖 + 薄外套'),
    (15, '外套 / 夹克'),
    (10, '毛衣 + 厚外套'),
    (5, '羽绒服 / 棉服'),
    (0, '厚羽绒 + 围巾手套'),
    (-999, '最厚的都穿上'),
]


# 湿度阈值：先看湿度再定"避暑/避寒"的说法，比只看温度更贴近体感
HUMID_HIGH = 75     # 高湿
HUMID_LOW = 30      # 干燥
HOT_TEMP = 28       # 进入"避暑"考虑的温度
COLD_TEMP = 12      # 进入"避寒"考虑的温度


def _clothes_by_temp(high: float) -> str:
    """温度档 -> 基础穿衣"""
    for limit, text in MINIMAL_CLOTHES:
        if high >= limit:
            return text
    return ''


def _humidity_note(high: float, humidity) -> str:
    """湿度 -> 体感修正短句（避暑：闷热/干热；避寒：湿冷/干冷），不需要修正时返回空字符串

    - 高温 + 高湿 = 闷热：比同温度的干热更难受，衣服要透气速干
    - 高温 + 干燥 = 干热：出汗蒸发快，更要补水
    - 低温 + 高湿 = 湿冷：体感比温度更低，加防风层更管用
    - 低温 + 干燥 = 干冷：主要靠保暖 + 防风，注意润肤
    """
    if humidity is None:
        return ''
    if high >= HOT_TEMP and humidity >= HUMID_HIGH:
        return '湿度 %s%%，闷热，建议透气速干' % _format_temp(humidity)
    if high >= HOT_TEMP and humidity <= HUMID_LOW:
        return '湿度 %s%%，干热，注意补水' % _format_temp(humidity)
    if high <= COLD_TEMP and humidity >= 80:
        return '湿度 %s%%，湿冷，体感更凉，加防风层' % _format_temp(humidity)
    if high <= COLD_TEMP and humidity <= HUMID_LOW:
        return '湿度 %s%%，干冷，注意润肤防风' % _format_temp(humidity)
    return ''


def _minimal_clothes(weather: dict, today: dict) -> str:
    """极简风穿衣推荐：先看湿度（避暑/避寒体感），再按温度定基础穿衣

    湿度用实况湿度（高德的预报数据里没有湿度字段）。
    """
    low, high = _temp_range(today)
    if high is None:
        high = weather.get('temperature')
    if high is None:
        return ''

    clothes = _clothes_by_temp(high)
    if not clothes:
        return ''

    notes = []
    note = _humidity_note(high, weather.get('humidity'))
    if note:
        notes.append(note)

    # 只有"夜里确实偏凉"才追加这句；否则 36°C 高温天也会被温差触发，看起来莫名其妙
    if low is not None and low <= 20 and (high - low) >= 8 and '外套' not in clothes:
        notes.append('早晚凉，带件外套')

    if notes:
        return '%s（%s）' % (clothes, '，'.join(notes))
    return clothes


def _today_wind_text(weather: dict, today: dict) -> str:
    """当天的风向风力：优先用当日预报的风，没有则退回实况风"""
    text = _wind_text(today.get('daywind') or '', today.get('daypower') or '')
    if text:
        return text
    return _wind_text(weather.get('winddirection') or '', weather.get('windpower') or '')


def _build_minimal(weather: dict, label: str | None = None) -> str:
    """极简风：地点+实况 / 当天天气(含风向风力) / 穿衣推荐 / 最多一条提醒

    只看当天，不带问候语、天气吐槽、湿度、未来几天预报、数据时间、彩蛋。
    """
    today = weather.get('today') or {}
    city = label or weather.get('city') or '目的地'

    live = weather.get('weather') or ''
    temp = _format_temp(weather.get('temperature'))
    bits = [b for b in (live, ('%s°C' % temp) if temp != '-' else '') if b]
    head = '📍 %s' % city
    if bits:
        head += ' ' + ' '.join(bits)

    lines = [head]
    wind = _today_wind_text(weather, today)

    if today:
        today_line = _cast_short('📆 今天', today)
        if wind:
            today_line += ' ｜ ' + wind
        lines.append(today_line)
    elif wind:
        # 没有预报数据时，把风向风力并到第一行，保持简短
        lines[0] = '%s ｜ %s' % (head, wind)

    clothes = _minimal_clothes(weather, today)
    if clothes:
        lines.append('👕 %s' % clothes)

    advice = _minimal_advice(weather, today)
    if advice:
        lines.append(advice)
    return '\n'.join(lines)


def build_message(weather: dict, style: str = 'humor', show_source: bool = True,
                  label: str | None = None, rng: random.Random | None = None) -> str:
    """把 get_weather() 的数据渲染成可直接发送的文案（style='minimal' 时走极简模板）"""
    style = normalize_style(style)
    rng = rng or random.Random()

    if style == 'minimal':
        return _build_minimal(weather, label=label)

    today = weather.get('today') or {}
    tomorrow = weather.get('tomorrow') or {}
    live_weather = weather.get('weather') or today.get('dayweather') or ''
    city = label or weather.get('city') or '目的地'
    province = weather.get('province') or ''

    lines = [rng.choice(GREETINGS[style][_period()]), BLANK]

    place = city if (not province or province in city) else '%s（%s）' % (city, province)
    lines.append('📍 %s' % place)

    bits = ['🌡 实况 %s %s°C' % (live_weather or '—', _format_temp(weather.get('temperature')))]
    humidity = weather.get('humidity')
    if humidity is not None:
        bits.append('💧 湿度 %s%%' % _format_temp(humidity))
    wind = _wind_text(weather.get('winddirection', ''), weather.get('windpower', ''))
    if wind:
        bits.append('🍃 %s' % wind)
    lines.append(' ｜ '.join(bits))

    lines.append(_match_comment(live_weather, style))

    if today:
        lines.append(_cast_line('📆 今天', today))
        _, day_high = _temp_range(today)
        lines.append(_temp_advice(day_high if day_high is not None else weather.get('temperature'), style))
        lines.append(_gap_advice(today.get('daytemp'), today.get('nighttemp'), style))
    else:
        lines.append(_temp_advice(weather.get('temperature'), style))

    lines.append(_rain_advice(live_weather, today.get('dayweather', ''), today.get('nightweather', '')))
    lines.append(_wind_advice(weather.get('windpower') or '', style))
    lines.append(_humidity_comment(humidity, style))

    if tomorrow:
        lines.append(BLANK)
        lines.append(_cast_line('📅 明天', tomorrow))

    if show_source:
        lines.append(BLANK)
        source = '🕗 数据时间 %s（%s）' % (weather.get('reporttime') or '未知', weather.get('source') or '高德地图')
        lines.append(source)

    lines.append(BLANK)
    lines.append(rng.choice(EGGS[style]))

    rendered = ['' if line == BLANK else line for line in lines if line == BLANK or line.strip()]
    return '\n'.join(rendered).strip()


DEMO_WEATHER = {
    'source': '高德地图 AMap',
    'province': '湖南',
    'city': '邵阳县',
    'weather': '雾',
    'temperature': 24.0,
    'humidity': 89.0,
    'winddirection': '东北',
    'windpower': '≤3',
    'reporttime': '2026-09-18 16:02:00',
    'today': {'date': '2026-09-18', 'weekday': '星期五', 'dayweather': '小雨', 'nightweather': '多云',
              'daytemp': 27.0, 'nighttemp': 18.0, 'daywind': '东北', 'nightwind': '东北',
              'daypower': '≤3', 'nightpower': '≤3'},
    'tomorrow': {'date': '2026-09-19', 'weekday': '星期六', 'dayweather': '多云', 'nightweather': '多云',
                 'daytemp': 26.0, 'nighttemp': 20.0, 'daywind': '南', 'nightwind': '北',
                 'daypower': '≤3', 'nightpower': '≤3'},
    'casts': [],
    'forecast_reporttime': '2026-09-18 11:00:00',
    'warnings': [],
}

if __name__ == '__main__':
    import sys

    console_utf8.enable()
    for style_name in (sys.argv[1:] or list(STYLES)):
        print('===== style=%s =====' % style_name)
        print(build_message(DEMO_WEATHER, style=style_name, rng=random.Random(7)))
        print('')


