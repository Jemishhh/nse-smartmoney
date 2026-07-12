#!/usr/bin/env python3
"""Build the morning alert email from alerts.json + daily_summary.json."""
import os,json,datetime
BASE=os.path.dirname(os.path.abspath(__file__))
def load(n):
    try: return json.load(open(os.path.join(BASE,n)))
    except: return {}
al=load("alerts.json").get("alerts",[])
S=load("daily_summary.json")
site="https://jemishhh.github.io/nse-smartmoney/"
maxd=max((a["d"] for a in al),default="")
hi_new=[a for a in al if a["d"]==maxd and a.get("hi")]
oth_new=[a for a in al if a["d"]==maxd and not a.get("hi")]
hi_recent=sorted([a for a in al if a.get("hi")],key=lambda x:x["d"],reverse=True)[:10]
def row(a):
    return (f"<tr><td>{a['d']}</td><td><b>{a['p']}</b></td><td>{a['s']}</td>"
            f"<td align=right>{a.get('q',0):,}</td><td align=right>{a.get('pr','')}</td>"
            f"<td align=right>#{a['rk']} / {a.get('sc','')}</td><td align=right>{a.get('wr','')}%</td></tr>")
if hi_new:
    subj=f"NSE Smart-Money: {len(hi_new)} high-score BUY(s) on {maxd}"
    lead=f"<p><b>{len(hi_new)} high-score buyer(s) bought on {maxd}:</b></p>"
    body_rows="".join(row(a) for a in hi_new)
else:
    subj=f"NSE Smart-Money: no high-score buys on {maxd or 'latest'} — recent picks inside"
    lead=f"<p>No high-score buyers on {maxd or 'the latest day'}. Most recent high-score buys:</p>"
    body_rows="".join(row(a) for a in hi_recent) or "<tr><td colspan=7>None recently.</td></tr>"
oth=""
if oth_new:
    oth="<p style='margin-top:14px'>Other tracked-player buys that day:</p><table border=0 cellpadding=5 style='border-collapse:collapse;font:13px Arial'>"+ "".join(row(a) for a in oth_new[:8])+"</table>"
top=S.get("top10",[])[:5]
tp="".join(f"<tr><td>#{t['Rank']}</td><td><b>{t['Player']}</b></td><td align=right>{t.get('win_rate_pct','')}%</td><td align=right>{t.get('val_wtd_return_pct','')}%</td><td align=right>{t.get('total_realized_pnl_cr','')} cr</td></tr>" for t in top)
html=f"""<div style="font:14px Arial,Helvetica,sans-serif;color:#1a2233;max-width:720px">
<h2 style="color:#1f3864;margin:0 0 4px">NSE Bulk-Deals — Smart-Money Alert</h2>
<div style="color:#667;font-size:12px">Data current to {S.get('data_through','')} · {S.get('players','')} tracked players · {S.get('new_rows_today',0)} new deal rows</div>
{lead}
<table border=0 cellpadding=5 style="border-collapse:collapse;font:13px Arial">
<tr style="background:#1f3864;color:#fff"><th align=left>Date</th><th align=left>Buyer</th><th align=left>Bought</th><th>Qty</th><th>Price</th><th>Rank/Score</th><th>Win%</th></tr>
{body_rows}</table>
{oth}
<p style="margin-top:16px"><b>Top 5 profitable players today</b></p>
<table border=0 cellpadding=5 style="border-collapse:collapse;font:13px Arial">
<tr style="background:#eef;"><th align=left>#</th><th align=left>Player</th><th>Win%</th><th>Val-wtd%</th><th>Realized P&L</th></tr>
{tp}</table>
<p style="margin-top:16px"><a href="{site}" style="background:#4f8cff;color:#fff;padding:9px 16px;border-radius:6px;text-decoration:none">Open full dashboard →</a></p>
<p style="color:#889;font-size:11px;margin-top:14px">A high score reflects past record, not a guarantee. Research tool, not investment advice.</p>
</div>"""
open(os.path.join(BASE,"email_body.html"),"w").write(html)
open(os.path.join(BASE,"email_subject.txt"),"w").write(subj)
print("email built:",subj)
