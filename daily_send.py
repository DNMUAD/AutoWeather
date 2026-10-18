# -*- coding: utf-8 -*-
"""定时发送入口（给 Windows 任务计划程序调用，也可以手动运行）

无人值守要求都考虑到了：
    1. 启动先把工作目录切到项目目录（否则日志/下载文件会落到 C:\\Windows\\System32）
    2. 全程写日志到 logs/send-YYYY-MM.log（任务计划程序不会捕获控制台输出）
    3. 到点时微信没在运行 → 自动拉起（config.LAUNCH_WECHAT_IF_MISSING）
    4. 取天气失败/发送失败都会记录，并以非 0 退出码结束（方便排查）
    5. 发送逻辑与手动一致的：复用 weather_report.fetch_and_render + sendmsg.send_to

用法：
    python daily_send.py                     # 正式发送（计划任务执行的就是这条）
    python daily_send.py --dry-run           # 只取天气 + 写日志，不碰微信
    python daily_send.py --to 文件传输助手     # 临时改收件人（自己测试用）

注册/查看/删除计划任务见 register_task.ps1：
    powershell -ExecutionPolicy Bypass -File .\\register_task.ps1
"""

import os
import sys

# 必须在 import wxauto4 之前切目录：它的日志/下载目录是按"当前工作目录"算的
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import argparse          # noqa: E402
import logging           # noqa: E402
import time              # noqa: E402

import config            # noqa: E402
import console_utf8      # noqa: E402
import sendmsg           # noqa: E402
import weather_report    # noqa: E402

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='定时发送天气到微信（计划任务入口）')
    parser.add_argument('city', nargs='?', help='地点：城市名（邵阳县）或 6 位 adcode（430523）')
    parser.add_argument('--adcode', help='直接指定 adcode')
    parser.add_argument('--label', help='文案里显示的地名')
    parser.add_argument('--to', help='微信接收人/群名（不填则用 config.TARGETS 里的 to）')
    parser.add_argument('--style', help='文案风格：humor / cute / plain / minimal')
    parser.add_argument('--dry-run', action='store_true', help='只取天气并写日志，不碰微信')
    return parser.parse_args(argv)


def setup_logging() -> logging.Logger:
    """同时输出到日志文件和控制台（无控制台时只写文件，例如用 pythonw 运行时）"""
    log_dir = os.path.join(PROJECT_DIR, getattr(config, 'LOG_DIR', 'logs'))
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'send-%s.log' % time.strftime('%Y-%m'))

    logger = logging.getLogger('daily_send')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False        # 不要向上传给 root logger（wxauto4 会给 root 加 handler，否则日志会重复打印）

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')

    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if sys.stdout is not None:                      # pythonw 下 stdout 为 None
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logger.info('日志文件：%s', log_path)
    return logger


def connect_wechat(logger: logging.Logger, attempts: int = 3):
    """初始化微信窗口对象；刚拉起微信时窗口可能还没准备好，所以重试几次"""
    from wxauto4 import WeChat

    for attempt in range(1, attempts + 1):
        try:
            return WeChat(ads = False)
        except Exception as exc:
            logger.warning('初始化微信失败（第 %d/%d 次）：%s', attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(5)
    logger.error('多次尝试仍无法连接微信：请确认微信已登录、窗口没被最小化')
    return None


def _fmt(value) -> str:
    """22.0 -> '22'；None -> '-'（只用于日志输出，好看一点）"""
    if value is None:
        return '-'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(round(number))) if abs(number - round(number)) < 0.05 else '%.1f' % number


def collect_jobs(args: argparse.Namespace, logger: logging.Logger) -> list[tuple]:
    """取天气 + 渲染文案，返回 [(target, 文案), ...]（取失败的直接跳过）"""
    targets = weather_report.collect_targets(args)
    if not targets:
        logger.error('config.TARGETS 里没有启用的地点')
        return []

    jobs = []
    for target in targets:
        who = target.get('label') or target.get('adcode') or '?'
        try:
            data, text = weather_report.fetch_and_render(target, args.style)
        except Exception as exc:
            logger.error('❌ %s 取天气失败：%s', who, exc)
            continue
        for warning in data.get('warnings') or []:
            logger.warning('提示（%s）：%s', who, warning)
        today = data.get('today') or {}
        logger.info('天气：%s %s %s°C（湿度%s%%）｜ 今天 %s %s~%s°C',
                    data.get('city') or who, data.get('weather') or '-', _fmt(data.get('temperature')),
                    _fmt(data.get('humidity')), today.get('dayweather') or '-',
                    _fmt(today.get('nighttemp')), _fmt(today.get('daytemp')))
        jobs.append((target, text))
    return jobs


def main(argv: list[str]) -> int:
    console_utf8.enable()
    args = parse_args(argv)
    logger = setup_logging()
    logger.info('=== 定时发送开始（%s）===', 'dry-run' if args.dry_run else '正式发送')
    logger.info('工作目录：%s', os.getcwd())

    jobs = collect_jobs(args, logger)
    if not jobs:
        logger.error('没有可发送的内容，本次结束')
        return 1

    if args.dry_run:
        for target, text in jobs:
            logger.info('dry-run 未发送 → 接收人：%s\n%s', target.get('to') or '(未指定)', text)
        logger.info('=== dry-run 结束 ===')
        return 0

    proc, note = sendmsg.ensure_wechat(logger.info)
    logger.info('%s', note)
    if proc is None:
        logger.error('微信不可用，放弃本次发送')
        return 1

    wx = connect_wechat(logger)
    if wx is None:
        return 1

    failed = 0
    for target, text in jobs:
        to = (target.get('to') or '').strip()
        if not to:
            logger.error('❌ %s 没有指定接收人（config.py 里的 to，或者命令行 --to）',
                         target.get('label') or '')
            failed += 1
            continue
        try:
            ok, message = sendmsg.send_to(wx, to, text)
        except Exception as exc:
            ok, message = False, '%s: %s' % (type(exc).__name__, exc)
        if ok:
            logger.info('✅ 已发送给 %s（%s）', to, message)
        else:
            logger.error('❌ 发送给 %s 失败：%s', to, message)
            failed += 1

    logger.info('=== 定时发送结束：成功 %d 条，失败 %d 条 ===', len(jobs) - failed, failed)
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        logging.getLogger('daily_send').exception('未预期的异常，本次发送失败')
        sys.exit(1)
