# -*- coding: utf-8 -*-
"""wxauto4 发送天气文案（第二步：先把"发送一次"跑通，定时留到下一步）

发送内容从哪来（与预览共用同一套逻辑，保证内容一致）：
    config.py           地点(adcode) / 微信接收人(to) / 风格(STYLE)
    weather_report.py   fetch_and_render() —— 取天气 + 渲染文案
    wxauto4             发微信

用法：
    python sendmsg.py --preview                    # 只打印要发送的内容，不碰微信（建议先跑这个）
    python sendmsg.py                              # 真的发送到 config.TARGETS 里启用的目标
    python sendmsg.py 邵阳县 --to 文件传输助手        # 临时指定地点和接收人
    python sendmsg.py --style minimal              # 临时换风格 humor/cute/plain/minimal

本文件里的 ensure_wechat() / send_to() 会被 daily_send.py（定时任务）复用。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from wxauto4 import WeChat  # 免费版

import config
import console_utf8
import weather_report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='把天气文案发到微信')
    parser.add_argument('city', nargs='?', help='地点：城市名（邵阳县）或 6 位 adcode（430523）')
    parser.add_argument('--adcode', help='直接指定 adcode，例如 430523')
    parser.add_argument('--label', help='文案里显示的地名')
    parser.add_argument('--to', help='微信接收人/群名（不填则用 config.TARGETS 里的 to）')
    parser.add_argument('--style', help='文案风格：humor / cute / plain / minimal')
    parser.add_argument('--preview', action='store_true', help='只打印，不真的发送（不碰微信）')
    return parser.parse_args(argv)


def find_wechat_process():
    """找微信主进程，返回 psutil.Process；没有则返回 None"""
    import psutil

    for proc in psutil.process_iter(['name']):
        try:
            name = (proc.info.get('name') or '').lower()
        except Exception:
            continue
        if name in ('weixin.exe', 'wechat.exe'):
            return proc
    return None


def ensure_wechat(log=print):
    """确保微信在运行，返回 (进程, 说明)

    到点时微信没开着的话，按 config.LAUNCH_WECHAT_IF_MISSING 自动拉起（最多等
    config.WECHAT_START_WAIT 秒）。定时任务无人值守时靠它兜底。
    """
    proc = find_wechat_process()
    if proc is not None:
        return proc, '微信已在运行（PID %s）' % proc.pid

    if not config.LAUNCH_WECHAT_IF_MISSING:
        return None, '微信没有运行，且 config.LAUNCH_WECHAT_IF_MISSING 为 False'

    exe = getattr(config, 'WECHAT_EXE', '') or ''
    if not exe or not os.path.exists(exe):
        return None, '微信没有运行，且找不到主程序：%r（请改 config.WECHAT_EXE）' % exe

    log('微信没在运行，正在拉起：%s' % exe)
    try:
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
    except OSError as exc:
        return None, '拉起微信失败：%s' % exc

    wait = int(getattr(config, 'WECHAT_START_WAIT', 60))
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(2)
        proc = find_wechat_process()
        if proc is not None:
            return proc, '已自动拉起微信（PID %s，等待了约 %.0f 秒）' % (proc.pid, wait - (deadline - time.time()))
    return None, '拉起微信后等待 %d 秒仍未检测到进程' % wait


def send_to(wx, target_name: str, text: str) -> tuple[bool, str]:
    """切换到指定聊天并发送，返回 (是否成功, 说明)

    wxauto4 返回的都是 dict 结构：
        ChatInfo() -> {'chat_name': ..., 'chat_type': ...}
        SendMsg()  -> WxResponse {'status': '成功'/'失败'/'错误', 'message': ...}
    """
    wx.ChatWith(target_name)                      # 打开聊天窗口（内部会走搜索框）
    chatinfo = wx.ChatInfo() or {}
    chat_name = chatinfo.get('chat_name')
    if chat_name != target_name:                  # 防呆：确认切对了窗口，避免发错人
        return False, '当前窗口是 %r，不是目标 %r，已跳过发送' % (chat_name, target_name)

    result = wx.SendMsg(text)                     # 发到"当前聊天窗口"
    if result and result.get('status') == '成功':
        return True, str(result.get('message') or '发送成功')
    return False, str(result)


def main(argv: list[str]) -> int:
    console_utf8.enable()
    args = parse_args(argv)
    style = args.style or config.STYLE

    # 复用 weather_report 的目标整理逻辑：命令行给了地点就用命令行，否则用 config.TARGETS
    targets = weather_report.collect_targets(args)
    if not targets:
        print('config.TARGETS 里没有启用的地点（把 enabled 改成 True 即可）')
        return 1

    jobs = []
    for target in targets:
        who = target.get('label') or target.get('adcode') or '?'
        try:
            data, text = weather_report.fetch_and_render(target, style)
        except Exception as exc:                  # 取天气失败就整条跳过，绝不发半截内容
            print('❌ %s 取天气失败：%s' % (who, exc))
            continue
        for warning in data.get('warnings') or []:
            print('⚠️ [提示] %s' % warning)
        jobs.append((target, text))

    if not jobs:
        print('没有可发送的内容')
        return 1

    if args.preview:
        for target, text in jobs:
            print('=' * 46)
            print('预览（未发送）→ 接收人：%s   风格：%s' % (target.get('to') or '(未指定)', style))
            print('=' * 46)
            print(text)
            print('')
        print('以上内容未发送。去掉 --preview 就会真的发送。')
        return 0

    print('正在初始化微信（需要微信已登录，且请不要在此期间操作鼠标键盘）...')
    wx = WeChat(ads=False)                                 # 初始化微信实例

    failed = 0
    for target, text in jobs:
        to = (target.get('to') or '').strip()
        if not to:
            print('❌ %s 没有指定接收人（config.py 里的 to，或者命令行 --to）' % (target.get('label') or ''))
            failed += 1
            continue
        try:
            ok, message = send_to(wx, to, text)
        except Exception as exc:
            ok, message = False, '%s: %s' % (type(exc).__name__, exc)
        if ok:
            print('✅ 已发送给 %s（%s）' % (to, message))
        else:
            print('❌ 发送给 %s 失败：%s' % (to, message))
            failed += 1

    # 顺手打印当前窗口最近几条消息，确认消息真的进去了
    try:
        msgs = wx.GetAllMessage()
        print('当前聊天窗口最近 3 条消息：')
        for msg in msgs[-3:]:
            print('==' * 30)
            print(msg.raw)
    except Exception as exc:
        print('（读取消息失败，已忽略：%s）' % exc)

    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
