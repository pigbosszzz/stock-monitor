"""Web dashboard renderer."""
from datetime import datetime
from pathlib import Path
import webbrowser

def _css():
    p = Path(__file__).parent / "dashboard.css"
    return p.read_text(encoding="utf-8")

def fc(v):
    return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"

def render(al, mr=None):
    css = _css()
    n = datetime.now().strftime("%Y-%m-%d %H:%M")
    B = []
    B.append("<html><head><meta charset=UTF-8><style>"+css+"</style></head><body>")
    B.append("<div class=header><h1>股票分析看板</h1><div class=time>"+n+"</div></div>")

    if mr and mr.indices:
        B.append("<div class=market-section><div class=market-grid>")
        for x in mr.indices:
            B.append("<div class=index-card><div class=name>"+x.index_name+"</div>")
            B.append("<div class=\"val "+("up" if x.percent>0 else "down")+"\">"+str(int(x.price))+"</div>")
            B.append("<div class=\"change "+("up" if x.percent>0 else "down")+"\">"+fc(x.percent)+"</div></div>")
        B.append("</div></div>")

    B.append("<div class=grid>")
    for r in al:
        q = r.quote
        if not q: continue
        up_down = "up" if q.percent>0 else ("down" if q.percent<0 else "")
        sig_cls = "buy" if any(k in r.signal for k in ("buy","add")) else ("sell" if any(k in r.signal for k in ("sell","avoid")) else "hold")
        arrow = "uarr" if q.percent>0 else ("darr" if q.percent<0 else "mdash")

        # Card header
        B.append("<div class=card><div class=card-title>"+q.name+"<span class=code>"+q.code+"</span></div>")
        B.append("<div class=price-row><span class=price>"+str(q.price)+"</span>")
        B.append("<span class=change style=color:"+("#f85149" if q.percent>0 else "#3fb950")+">&"+arrow+"; "+str(q.change)+" ("+fc(q.percent)+")</span></div>")

        # Price bar
        rng = q.high - q.low or 1
        pct_pos = int((q.price - q.low) / rng * 100)
        B.append("<div class=price-bar><span class=bar-label>"+str(q.low)+"</span>")
        B.append("<div class=bar-track><div class=bar-fill style=width:"+str(pct_pos)+"%></div>")
        B.append("<div class=bar-dot style=left:"+str(pct_pos)+"%></div></div>")
        B.append("<span class=bar-label>"+str(q.high)+"</span></div>")

        # OHLC grid
        B.append("<div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>开盘</div><div class=stat-val>"+str(q.open)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>昨收</div><div class=stat-val>"+str(q.prev_close)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>最高</div><div class=stat-val style=color:#f85149>"+str(q.high)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>最低</div><div class=stat-val style=color:#3fb950>"+str(q.low)+"</div></div>")
        B.append("</div>")

        # Volume
        B.append("<div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>成交量</div><div class=stat-val>"+str(q.volume)+"手</div></div>")
        B.append("<div class=stat><div class=stat-label>成交额</div><div class=stat-val>"+str(int(q.amount))+"万</div></div>")
        if r.vol_ratio:
            B.append("<div class=stat><div class=stat-label>量比</div><div class=stat-val>"+str(r.vol_ratio)+"</div></div>")
            B.append("<div class=stat><div class=stat-label>状态</div><div class=stat-val>"+r.vol_analysis+"</div></div>")
        B.append("</div>")

        # Holdings
        pl_cls = "up" if r.profit_loss>0 else ("down" if r.profit_loss<0 else "gray")
        pl_color = "#f85149" if r.profit_loss>0 else ("#3fb950" if r.profit_loss<0 else "#8b949e")
        B.append("<div class=section-title>持仓</div><div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>成本</div><div class=stat-val>"+(str(r.cost_price) if r.cost_price else "-")+"</div></div>")
        B.append("<div class=stat><div class=stat-label>持仓</div><div class=stat-val>"+(str(r.shares)+"股" if r.shares else "-")+"</div></div>")
        B.append("<div class=stat><div class=stat-label>市值</div><div class=stat-val>"+(str(int(r.market_value)) if r.market_value else "-")+"</div></div>")
        B.append("<div class=stat><div class=stat-label>盈亏</div><div class=stat-val style=color:"+pl_color+">"+(str(int(r.profit_loss))+" ("+fc(r.profit_loss_pct)+")" if r.cost_price else "-")+"</div></div>")
        B.append("</div>")

        # Target / Stop
        B.append("<div class=section-title>参考价位</div><div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>目标价</div><div class=stat-val style=color:#f85149>"+str(r.target_price)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>止损价</div><div class=stat-val style=color:#3fb950>"+str(r.stop_loss)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>枢轴</div><div class=stat-val style=color:#8b949e>"+str(r.pivot)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>相对强度</div><div class=stat-val style=color:"+("#f85149" if r.relative_strength>0 else "#3fb950")+">"+fc(r.relative_strength)+"</div></div>")
        B.append("</div>")

        # Signal
        B.append("<div class=\"signal "+sig_cls+"\">"+r.signal+" <span class=score>评分 "+str(r.score)+"</span></div>")
        B.append("<div class=detail>"+r.detail+"</div>")

        # MA
        if r.ma5:
            B.append("<div class=section-title>均线</div><div class=stat-row>")
            for ma, val, pct_val in [("MA5",r.ma5,r.ma5_pct),("MA10",r.ma10,r.ma10_pct),("MA20",r.ma20,r.ma20_pct)]:
                c = "#f85149" if pct_val>0 else ("#3fb950" if pct_val<0 else "#8b949e")
                B.append("<div class=stat><div class=stat-label>"+ma+"</div><div class=stat-val style=color:"+c+">"+str(val)+" <small>"+fc(pct_val)+"</small></div></div>")
            B.append("<div class=stat><div class=stat-label>趋势</div><div class=stat-val>"+r.trend+"</div></div>")
            B.append("</div>")

        # Multi-timeframe + Backtest
        bt = getattr(r, "_backtest", None)
        if bt and bt.timeframe:
            B.append("<div class=section-title>多周期趋势</div><div class=stat-row>")
            for t in bt.timeframe:
                em = {"多头排列":"#f85149","空头排列":"#3fb950","短线偏多":"#d2991d","短线偏空":"#58a6ff"}.get(t.trend,"#8b949e")
                B.append("<div class=stat><div class=stat-label>"+t.name+"</div><div class=stat-val><span style=color:"+em+";font-size:13px>"+t.trend+"</span><div style=font-size:10px;color:#8b949e>MA20:"+str(round(t.ma20,1))+"</div></div></div>")
            B.append("</div>")
        if bt and bt.total_return != 0:
            B.append("<div class=section-title>90日回测</div><div class=stat-row>")
            rc = "#f85149" if bt.total_return>0 else "#3fb950"
            bc = "#f85149" if bt.buy_hold_return>0 else "#3fb950"
            B.append("<div class=stat><div class=stat-label>策略收益</div><div class=stat-val style=color:"+rc+">"+str(bt.total_return)+"%</div></div>")
            B.append("<div class=stat><div class=stat-label>买入持有</div><div class=stat-val style=color:"+bc+">"+str(bt.buy_hold_return)+"%</div></div>")
            B.append("<div class=stat><div class=stat-label>胜率</div><div class=stat-val>"+str(bt.win_rate)+"%</div></div>")
            B.append("<div class=stat><div class=stat-label>交易</div><div class=stat-val>"+str(bt.trade_count)+"次</div></div>")
            B.append("</div>")

        # Industry rank
        ir = getattr(r, "_industry_rank", None)
        if ir and ir.ranked_stocks:
            B.append("<div class=section-title>行业排名 - "+ir.industry_name+"</div><div class=rank-list>")
            for i, s in enumerate(ir.ranked_stocks):
                cl = "mine" if s.get("code") == r.code else ""
                nm, cd, pt = s.get("name",""), s.get("code",""), s.get("percent",0)
                c2 = "#f85149" if pt>0 else ("#3fb950" if pt<0 else "#8b949e")
                B.append("<div class=\"rank-row "+cl+"\"><span>"+str(i+1)+". "+nm+" ("+cd+")</span><span style=color:"+c2+">"+fc(pt)+"</span></div>")
            B.append("</div><div class=rank-avg>行业均"+fc(ir.avg_change)+"</div>")

        if r.warnings:
            for w in r.warnings:
                B.append("<div class=warn>"+w+"</div>")
        B.append("</div>")

    B.append("</div><div class=footer>以上分析不构成投资建议</div></body></html>")
    return "\n".join(B)

def save_and_open(html, fname="stock_dashboard.html"):
    p = Path(fname)
    p.write_text(html, encoding="utf-8")
    webbrowser.open("file:///" + str(p.absolute()))
    return str(p)