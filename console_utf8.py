# -*- coding: utf-8 -*-
"""统一把标准输出/错误输出设为 UTF-8 —— 保证 emoji 与中文在"重定向"环境也能打印

背景（Windows 特有坑）：
    Python 在 Windows 控制台里会用 WriteConsoleW 输出 Unicode，中文/emoji 都正常；
    但一旦 stdout 被重定向（管道 `|`、写入文件、任务计划程序捕获输出），
    Python 会退回使用 locale 编码（GBK），打印 emoji 就会抛：
        UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f31e'
    直接让定时任务失败。这里统一把编码改成 UTF-8（errors='replace' 兜底）。

用法：
    import console_utf8
    console_utf8.enable()      # 放在入口脚本最开头调用一次即可
"""

from __future__ import annotations

import sys


def enable() -> None:
    """把 stdout/stderr 切换为 UTF-8（对真实控制台无影响，对重定向/计划任务生效）"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            continue


if __name__ == '__main__':
    enable()
    print('console_utf8 已生效：中文 ✔ emoji 🌤☂🥶 均可输出')
