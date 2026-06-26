"""Web dashboard renderer."""
from datetime import datetime
from pathlib import Path
import webbrowser

def _css():
    p = Path(__file__).parent / "dashboard.css"
    return p.read_text(encoding="utf-8")

def fc(v):
    return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"

def cz(v):
    return "up" if v > 0 else ("down" if v < 0 else "")

def sg(s):
    if any(k in s for k in ("buy","add")): return "buy"
    if any(k in s for k in ("sell","avoid")): return "sell"
    return "hold"

def g(s, d):
    return "<div>"+s+"</div><div>"+d+"</div>"

def render(al, mr=None):
    css = _css()
    n = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("<html><head><meta charset=UTF-8><style>"+css+"</style></head><body>")
    L.append("<div class=header><h1>股票分析看板</h1><div class=time>"+n+"</div></div>")

    if mr and mr.indices:
        L.append("<div class=market-section><div class=market-grid>")
        for x in mr.indices:
            L.append("<div class=index-card>")
            L.append("<div class=name>"+x.index_name+"</div>")
            L.append("<div class=\"val "+cz(x.percent)+"\">"+str(int(x.price))+"</div>")
            L.append("<div class=\"change "+cz(x.percent)+"\">"+fc(x.percent)+"</div></div>")
        L.append("</div></div>")

    L.append("<div class=grid>")
    for r in al:
        q = r.quote
        if not q: continue
        a = "uarr;" if q.percent>0 else ("darr;" if q.percent<0 else "mdash;")
        pc, sc = cz(q.percent), sg(r.signal)

        L.append("<div class=card>")
        L.append("<div class=card-title>"+q.name+"<span class=code>"+q.code+"</span></div>")
        L.append("<div class=price-row><span class=price>"+str(q.price)+"</span>")
        L.append("<span class=\"change "+pc+"\">&"+a+"; "+str(q.change)+" ("+fc(q.percent)+")</span></div>")

        # 行情
        L.append("<div class=card-section>")
        L.append("<div class=section-title>行情数据</div>")
        L.append("<div class=info-grid>")
        L.append(g("开盘","<span>"+str(q.open)+"</span>"))
        L.append(g("最高","<span style=color:#3fb950>"+str(q.high)+"</span>"))
        L.append(g("昨收","<span>"+str(q.prev_close)+"</span>"))
        L.append(g("最低","<span style=color:#f85149>"+str(q.low)+"</span>"))
        L.append(g("成交量","<span>"+str(q.volume)+"手</span>"))
        L.append(g("成交额","<span>"+str(int(q.amount))+"万</span>"))
        L.append("</div></div>")

        # 持仓
        if r.cost_price and r.shares:
            pc2 = "up" if r.profit_loss>0 else "down"
            L.append("<div class=card-section>")
            L.append("<div class=section-title>持仓明细</div>")
            L.append("<div class=info-grid>")
            L.append(g("成本",str(r.cost_price)))
            L.append(g("持仓",str(r.shares)+"股"))
            L.append(g("市值",str(int(r.market_value))))
            L.append(g("盈亏","<span class="+pc2+">"+str(int(r.profit_loss))+" ("+fc(r.profit_loss_pct)+")</span>"))
            L.append("</div></div>")

        # 价位
        L.append("<div class=card-section>")
        L.append("<div class=section-title>参考价位</div>")
        L.append("<div class=info-grid>")
        L.append(g("目标价","<span class=t>"+str(r.target_price)+"</span>"))
        L.append(g("止损价","<span class=s>"+str(r.stop_loss)+"</span>"))
        L.append(g("枢轴","<span class=gray>"+str(r.pivot)+"</span>"))
        L.append(g("相对强度","<span class="+pc+">"+fc(r.relative_strength)+"</span>"))
        L.append("</div></div>")

        L.append("<div class=\"signal "+sc+"\">"+r.signal+"</div>")
        L.append("<div class=detail>评分: "+str(r.score)+" | "+r.detail+"</div>")

        # 均线
        if r.ma5:
            L.append("<div class=card-section>")
            L.append("<div class=section-title>均线趋势</div>")
            L.append("<div class=info-grid>")
            L.append(g("MA5",str(r.ma5)+" <span class="+cz(r.ma5_pct)+">"+fc(r.ma5_pct)+"</span>"))
            L.append(g("MA10",str(r.ma10)+" <span class="+cz(r.ma10_pct)+">"+fc(r.ma10_pct)+"</span>"))
            L.append(g("MA20",str(r.ma20)+" <span class="+cz(r.ma20_pct)+">"+fc(r.ma20_pct)+"</span>"))
            L.append(g("趋势","<span>"+r.trend+"</span>"))
            L.append("</div></div>")

        # 量
        if r.vol_ratio:
            L.append("<div class=card-section>")
            L.append("<div class=section-title>成交量</div>")
            L.append("<div class=info-grid>")
            L.append(g("量比",str(r.vol_ratio)))
            L.append(g("状态","<span>"+r.vol_analysis+"</span>"))
            L.append("</div></div>")

        # 排名
        ir = getattr(r, "_industry_rank", None)
        if ir and ir.ranked_stocks:
            L.append("<div class=card-section>")
            L.append("<div class=section-title>行业排名 - "+ir.industry_name+"</div>")
            L.append("<div class=rank-list>")
            for i, s in enumerate(ir.ranked_stocks):
                cl = "mine" if s.get("code") == r.code else ""
                p2 = cz(s.get("percent", 0))
                nm = s.get("name", "")
                cd = s.get("code", "")
                pt = s.get("percent", 0)
                L.append("<div class=\"rank-row "+cl+"\"><span>"+str(i+1)+". "+nm+" ("+cd+")</span><span class="+p2+">"+fc(pt)+"</span></div>")
            L.append("</div>")
            L.append("<div class=rank-avg>行业均"+fc(ir.avg_change)+"</div></div>")

        # 风险
        if r.warnings:
            L.append("<div class=card-section>")
            for w in r.warnings:
                L.append("<div class=warn>"+w+"</div>")
            L.append("</div>")

        L.append("</div>")

    L.append("</div><div class=footer>以上分析不构成投资建议</div></body></html>")
    return "\n".join(L)

def save_and_open(html, fname="stock_dashboard.html"):
    p = Path(fname)
    p.write_text(html, encoding="utf-8")
    webbrowser.open("file:///" + str(p.absolute()))
    return str(p)