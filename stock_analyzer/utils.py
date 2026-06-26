"""
工具函数 — 代码转换、格式化等通用逻辑。
"""
import datetime


def stock_code_key(code: str) -> str:
    """6位数字代码 → 腾讯API '市场+代码' 格式 (sh/sz + 6位)"""
    code = code.strip()
    if code.lower().startswith(("sh", "sz")):
        return code.lower()
    if code.startswith(("6", "5")):
        return f"sh{code}"
    return f"sz{code}"


def em_code(code: str) -> str:
    """→ 东方财富格式 SH600519 / SZ000858"""
    key = stock_code_key(code)
    prefix = "SH" if key.startswith("sh") else "SZ"
    return prefix + key[2:]


def is_trading_time(now: datetime.datetime | None = None) -> bool:
    """判断当前是否 A 股交易时间（工作日 9:30-11:30, 13:00-15:00）"""
    if now is None:
        now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    morning = datetime.time(9, 30) <= t <= datetime.time(11, 30)
    afternoon = datetime.time(13, 0) <= t <= datetime.time(15, 0)
    return morning or afternoon



def retry(max_attempts=3, delay=1.0):
    """Retry decorator with exponential backoff for transient failures."""
    import time
    import functools
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    if attempt < max_attempts - 1:
                        time.sleep(delay * (2 ** attempt))
            raise last_err
        return wrapper
    return decorator


def format_amount(amount: float) -> str:
    """格式化成交额显示（万元→亿元 或 万元）"""
    if amount >= 10000:
        return f"{amount / 10000:.2f}亿"
    return f"{amount:.0f}万"
