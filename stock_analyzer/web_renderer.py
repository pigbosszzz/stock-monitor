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
    if "买入" in s or "加仓" in s: return "buy"
    if "减仓" in s or "回避" in s: return "sell"
    return "hold"

def g(s, d):
    return "<div>"+s+"</div><div>"+d+"</div>"

def render(al, mr=None):
    css = _css()
    n = datetime.now().strftime("%Y-%m-%d %H:%M")
    B = []
    B.append("<html><head><meta charset=UTF-8><style>"+css+"</style></head><body>")
    B.append("<div class=header><h1>股票分析看板</h1><div class=time>"+n+"</div></div>")

    if mr and mr.indices:
        B.append("<div class=market-section><div class=market-grid>")
        for x in mr.indices:
            B.append("<div class=index-card>")
            B.append("<div class=name>"+x.index_name+"</div>")
            B.append("<div class=\"val "+cz(x.percent)+"\">"+str(int(x.price))+"</div>")
            B.append("<div class=\"change "+cz(x.percent)+"\">"+fc(x.percent)+"</div></div>")
        B.append("</div></div>")

    B.append("<div class=grid>")
    for r in al:
        q = r.quote
        if not q: continue
        a = "uarr" if q.percent>0 else ("darr" if q.percent<0 else "mdash")
        pc = cz(q.percent)
        sc = sg(r.signal)

        B.append("<div class=card>")
        B.append("<div class=card-title>"+q.name+"<span class=code>"+q.code+"</span></div>")
        B.append("<div class=price-row><span class=price>"+str(q.price)+"</span>")
        B.append("<span class=\"change "+pc+"\">&"+a+"; "+str(q.change)+" ("+fc(q.percent)+")</span></div>")

        # -- 价格区间条 --
        rng = q.high - q.low
        pct_pos = int((q.price - q.low) / rng * 100) if rng > 0 else 50
        B.append("<div class=price-bar>")
        B.append("<span class=bar-label>"+str(q.low)+"</span>")
        B.append("<div class=bar-track><div class=bar-fill style=width:"+str(pct_pos)+"%></div><div class=bar-dot style=left:"+str(pct_pos)+"%></div></div>")
        B.append("<span class=bar-label>"+str(q.high)+"</span>")
        B.append("</div>")

        # -- 四格关键数据 --
        B.append("<div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>开盘</div><div class=stat-val>"+str(q.open)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>昨收</div><div class=stat-val>"+str(q.prev_close)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>最高</div><div class=stat-val up>"+str(q.high)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>最低</div><div class=stat-val down>"+str(q.low)+"</div></div>")
        B.append("</div>")

        # -- 成交量行 --
        B.append("<div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>成交量</div><div class=stat-val>"+str(q.volume)+"手</div></div>")
        B.append("<div class=stat><div class=stat-label>成交额</div><div class=stat-val>"+str(int(q.amount))+"万</div></div>")
        if r.vol_ratio:
            B.append("<div class=stat><div class=stat-label>量比</div><div class=stat-val>"+str(r.vol_ratio)+"</div></div>")
            B.append("<div class=stat><div class=stat-label>状态</div><div class=stat-val>"+r.vol_analysis+"</div></div>")
        B.append("</div>")

        # -- 持仓 --
        pc2 = "up" if r.profit_loss>0 else "down"
        B.append("<div class=section-title>持仓</div>")
        B.append("<div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>成本</div><div class=stat-val>"+(str(r.cost_price) if r.cost_price else "-")+"</div></div>")
        B.append("<div class=stat><div class=stat-label>持仓</div><div class=stat-val>"+(str(r.shares)+"股" if r.shares else "-")+"</div></div>")
        B.append("<div class=stat><div class=stat-label>市值</div><div class=stat-val>"+(str(int(r.market_value)) if r.market_value else "-")+"</div></div>")
        B.append("<div class=stat><div class=stat-label>盈亏</div><div class=\"stat-val "+pc2+"\">"+(str(int(r.profit_loss))+" ("+fc(r.profit_loss_pct)+")" if r.cost_price else "-")+"</div></div>")
        B.append("</div>")

        # -- 参考价位 --
        B.append("<div class=section-title>参考价位</div>")
        B.append("<div class=stat-row>")
        B.append("<div class=stat><div class=stat-label>目标价</div><div class=stat-val t>"+str(r.target_price)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>止损价</div><div class=stat-val s>"+str(r.stop_loss)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>枢轴</div><div class=stat-val gray>"+str(r.pivot)+"</div></div>")
        B.append("<div class=stat><div class=stat-label>相对强度</div><div class=\"stat-val "+pc+"\">"+fc(r.relative_strength)+"</div></div>")
        B.append("</div>")

        # -- 信号 --
        B.append("<div class=\"signal "+sc+"\">"+r.signal+"  <span class=score>评分 "+str(r.score)+"</span></div>")
        B.append("<div class=detail>"+r.detail+"</div>")

        # -- 均线 --
        if r.ma5:
            B.append("<div class=section-title>均线</div>")
            B.append("<div class=stat-row>")
            B.append("<div class=stat><div class=stat-label>MA5</div><div class=\"stat-val "+cz(r.ma5_pct)+"\">"+str(r.ma5)+" <small>"+fc(r.ma5_pct)+"</small></div></div>")
            B.append("<div class=stat><div class=stat-label>MA10</div><div class=\"stat-val "+cz(r.ma10_pct)+"\">"+str(r.ma10)+" <small>"+fc(r.ma10_pct)+"</small></div></div>")
            B.append("<div class=stat><div class=stat-label>MA20</div><div class=\"stat-val "+cz(r.ma20_pct)+"\">"+str(r.ma20)+" <small>"+fc(r.ma20_pct)+"</small></div></div>")
            B.append("<div class=stat><div class=stat-label>趋势</div><div class=stat-val>"+r.trend+"</div></div>")
            B.append("</div>")

        # -- 行业排名 --
        ir = getattr(r, "_industry_rank", None)
        if ir and ir.ranked_stocks:
            B.append("<div class=section-title>行业排名 - "+ir.industry_name+"</div>")
            B.append("<div class=rank-list>")
            for i, s in enumerate(ir.ranked_stocks):
                cl = "mine" if s.get("code") == r.code else ""
                p2 = cz(s.get("percent", 0))
                nm = s.get("name", "")
                cd = s.get("code", "")
                pt = s.get("percent", 0)
                B.append("<div class=\"rank-row "+cl+"\"><span>"+str(i+1)+". "+nm+" ("+cd+")</span><span class="+p2+">"+fc(pt)+"</span></div>")
            B.append("</div>")
            B.append("<div class=rank-avg>行业均"+fc(ir.avg_change)+"</div>")

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