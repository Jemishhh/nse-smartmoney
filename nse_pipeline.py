#!/usr/bin/env python3
"""NSE smart-money daily pipeline.
Ingests any raw NSE bulk-deal CSVs in ./incoming, cleans+removes intraday,
appends to master_clean.csv, recomputes rankings, rebuilds the dashboard.
Run: python3 nse_pipeline.py
"""
import glob,os,json,datetime,re
import pandas as pd, numpy as np
try: from rapidfuzz import fuzz; FUZZ=True
except Exception: FUZZ=False
BASE=os.path.dirname(os.path.abspath(__file__)); CR=1e7
MASTER=os.path.join(BASE,"master_clean.csv")
INC=os.path.join(BASE,"incoming"); ARC=os.path.join(BASE,"archive")

def clean_num(x):
    if pd.isna(x):return np.nan
    s=str(x).replace(",","").replace('"','').strip()
    if s in("","-","nan"):return np.nan
    try:return float(s)
    except:return np.nan
def loadcsv(p):
    # tolerate web_fetch preamble: start at the header line containing "Date"
    lines=open(p,encoding="utf-8-sig",errors="ignore").read().splitlines()
    hi=next((i for i,l in enumerate(lines) if l.lstrip().lower().startswith('"date') or l.lstrip().lower().startswith('date')),0)
    import io
    d=pd.read_csv(io.StringIO("\n".join(lines[hi:])),dtype=str,skipinitialspace=True,on_bad_lines="skip",engine="python")
    d.columns=[c.strip() for c in d.columns]
    for c in d.columns: d[c]=d[c].astype(str).str.strip()
    return d
def pdates(s):
    d=pd.to_datetime(s,format="%d-%b-%y",errors="coerce");m=d.isna()
    if m.any():d.loc[m]=pd.to_datetime(s[m],format="%d-%b-%Y",errors="coerce")
    m=d.isna()
    if m.any():d.loc[m]=pd.to_datetime(s[m],dayfirst=True,errors="coerce")
    return d
def norm(df):
    o=pd.DataFrame()
    o["Date"]=pdates(df["Date"]);o["Symbol"]=df["Symbol"].str.upper().str.strip()
    o["Security Name"]=df["Security Name"].str.strip();o["Client Name"]=df["Client Name"].str.strip()
    o["Buy / Sell"]=df["Buy / Sell"].str.upper().str.strip()
    o["Quantity"]=df["Quantity Traded"].map(clean_num);o["Price"]=df["Trade Price / Wght. Avg. Price"].map(clean_num)
    o["Source"]="daily"; return o
def rm_intra(df,tol=0.15):
    df=df.copy();df["_k"]=df["Date"].dt.strftime("%Y-%m-%d")+"|"+df["Symbol"]+"|"+df["Client Name"];drop=set()
    for k,g in df.groupby("_k"):
        b=g[g["Buy / Sell"]=="BUY"];s=g[g["Buy / Sell"]=="SELL"]
        if len(b)==0 or len(s)==0:continue
        used=set()
        for bi,br in b.iterrows():
            bq=br["Quantity"]
            if pd.isna(bq) or bq==0:continue
            for si,sr in s.iterrows():
                if si in used:continue
                sq=sr["Quantity"]
                if pd.isna(sq) or sq==0:continue
                if abs(bq-sq)/max(bq,sq)<=tol:drop.add(bi);drop.add(si);used.add(si);break
    return df.drop(index=list(drop)).drop(columns=["_k"]),len(drop)

# ---------- 1. INGEST ----------
master=pd.read_csv(MASTER,parse_dates=["Date"])
newfiles=sorted(glob.glob(os.path.join(INC,"*.csv")))
added=0
if newfiles:
    frames=[]
    for f in newfiles:
        try: frames.append(norm(loadcsv(f)))
        except Exception as e: print("skip",f,e)
    if frames:
        newd=pd.concat(frames,ignore_index=True).dropna(subset=["Date"])
        newd,nd=rm_intra(newd,0.15)
        master=pd.concat([master,newd],ignore_index=True)
        b0=len(master)
        master=master.drop_duplicates(subset=["Date","Symbol","Client Name","Buy / Sell","Quantity","Price"])
        added=len(master)- 0
        print(f"ingested {len(newd)} clean new rows (dropped {nd} intraday)")
    os.makedirs(ARC,exist_ok=True)
    for f in newfiles:
        try: os.replace(f,os.path.join(ARC,os.path.basename(f)))
        except Exception as e: print("archive warn:",e)
master=master.sort_values(["Date","Symbol","Client Name"]).reset_index(drop=True)
master.to_csv(MASTER,index=False)
latest=master["Date"].max()
open(os.path.join(BASE,"last_data_date.txt"),"w").write(str(latest.date()))
print("master rows",len(master),"latest",latest.date())

# ---------- 2. ENTITY RESOLUTION ----------
SUF={"PRIVATE","PVT","LIMITED","LTD","LLP","LP","LLC","INC","CO","COMPANY","AND","THE","INDIA","INDIAN","&"}
def nn(x):
    s=re.sub(r"[^A-Z0-9 ]"," ",str(x).upper());s=re.sub(r"\s+"," ",s).strip()
    return " ".join(t for t in s.split(" ") if t and t not in SUF)
master["norm"]=master["Client Name"].map(nn)
kc=master["norm"].value_counts();keys=list(kc.index);parent={k:k for k in keys}
def find(x):
    while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
    return x
def uni(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[rb if kc[ra]>=kc[rb] else ra]=ra if kc[ra]>=kc[rb] else rb
if FUZZ:
    tk=keys[:800]
    for i in range(len(tk)):
        a=tk[i]
        if not a:continue
        for j in range(i+1,len(tk)):
            b=tk[j]
            if not b or abs(len(a)-len(b))>8:continue
            if fuzz.token_sort_ratio(a,b)>=92:uni(a,b)
master["pk"]=master["norm"].map(lambda k:find(k) if k in parent else k)
disp=master.groupby("pk")["Client Name"].agg(lambda s:s.value_counts().index[0])
master["Player"]=master["pk"].map(disp)

# ---------- 3. PROFITABILITY ----------
master["Val"]=master["Quantity"]*master["Price"]
b=master[master["Buy / Sell"]=="BUY"];s=master[master["Buy / Sell"]=="SELL"]
ba=b.groupby(["Player","Symbol"]).agg(buy_qty=("Quantity","sum"),buy_val=("Val","sum"),first_buy=("Date","min"),last_buy=("Date","max")).reset_index()
ba["avg_buy"]=ba["buy_val"]/ba["buy_qty"]
sa=s.groupby(["Player","Symbol"]).agg(sell_qty=("Quantity","sum"),sell_val=("Val","sum"),last_sell=("Date","max")).reset_index()
sa["avg_sell"]=sa["sell_val"]/sa["sell_qty"]
pos=pd.merge(ba,sa,on=["Player","Symbol"],how="outer")
for c in ["buy_qty","sell_qty","buy_val","sell_val"]:pos[c]=pos[c].fillna(0)
pos["realized"]=(pos["buy_qty"]>0)&(pos["sell_qty"]>0)
pos["matched_qty"]=pos[["buy_qty","sell_qty"]].min(axis=1)
pos["return_pct"]=np.where(pos["realized"],(pos["avg_sell"]-pos["avg_buy"])/pos["avg_buy"]*100,np.nan)
pos["realized_pnl"]=np.where(pos["realized"],pos["matched_qty"]*(pos["avg_sell"]-pos["avg_buy"]),np.nan)
pos["open_qty"]=(pos["buy_qty"]-pos["sell_qty"]).clip(lower=0)
pos["open_cost"]=pos["open_qty"]*pos["avg_buy"]
rz=pos[pos["realized"]].copy();g=rz.groupby("Player")
players=pd.DataFrame({"realized_positions":g.size(),
 "win_rate_pct":g.apply(lambda x:(x["return_pct"]>0).mean()*100,include_groups=False),
 "avg_return_pct":g["return_pct"].mean(),
 "val_wtd_return_pct":g.apply(lambda x:np.average(x["return_pct"],weights=x["matched_qty"]*x["avg_buy"]),include_groups=False),
 "total_realized_pnl":g["realized_pnl"].sum(),
 "matched_value":g.apply(lambda x:(x["matched_qty"]*x["avg_buy"]).sum(),include_groups=False)}).reset_index()
op=pos[pos["open_qty"]>0].groupby("Player").agg(open_positions=("Symbol","nunique"),open_cost=("open_cost","sum")).reset_index()
players=players.merge(op,on="Player",how="left").fillna({"open_positions":0,"open_cost":0})
tb=b.groupby("Player")["Val"].sum().rename("total_buy_value").reset_index()
players=players.merge(tb,on="Player",how="left")
for a,c in [("total_realized_pnl_cr","total_realized_pnl"),("matched_value_cr","matched_value"),("open_cost_cr","open_cost"),("total_buy_value_cr","total_buy_value")]:
    players[a]=players[c]/CR
q=players[(players["realized_positions"]>=3)&(players["matched_value_cr"]>=1.0)].copy()
q["score"]=q["val_wtd_return_pct"]*0.5+q["win_rate_pct"]*0.3+np.log10(q["matched_value_cr"].clip(lower=0.1)+1)*10*0.2
q=q.sort_values(["score","avg_return_pct"],ascending=False).reset_index(drop=True);q.insert(0,"Rank",range(1,len(q)+1))
q.to_csv(os.path.join(BASE,"players_ranked.csv"),index=False)

# ---------- 4. DASHBOARD ----------
secmap=dict(zip(master["Symbol"],master["Security Name"]))
def ff(x,d=2):
    try:return round(float(x),d)
    except:return None
data=[]
for _,r in q.iterrows():
    pl=r["Player"];pp=pos[pos["Player"]==pl]
    posl=[]
    for _,z in pp.sort_values("realized_pnl",ascending=False,na_position="last").iterrows():
        held=z["open_qty"]>0;rl=bool(z["realized"])
        posl.append({"s":z["Symbol"],"n":secmap.get(z["Symbol"],""),
         "ab":ff(z["avg_buy"]) if z["buy_qty"]>0 else None,"as":ff(z["avg_sell"]) if z["sell_qty"]>0 else None,
         "ret":ff(z["return_pct"],1) if rl else None,"pnl":ff(z["realized_pnl"]/CR,3) if rl else None,
         "oq":int(z["open_qty"]) if held else 0,
         "st":"Closed" if (rl and not held) else("Partly held" if rl and held else("Holding" if held else "-")),
         "fb":str(pd.to_datetime(z["first_buy"]).date()) if pd.notna(z["first_buy"]) else "",
         "ls":str(pd.to_datetime(z["last_sell"]).date()) if pd.notna(z["last_sell"]) else ""})
    data.append({"rk":int(r["Rank"]),"p":pl,"wr":ff(r["win_rate_pct"],1),"ar":ff(r["avg_return_pct"],1),
     "vw":ff(r["val_wtd_return_pct"],1),"pnl":ff(r["total_realized_pnl_cr"]),"cap":ff(r["matched_value_cr"]),
     "rt":int(r["realized_positions"]),"op":int(r["open_positions"]),"oc":ff(r["open_cost_cr"]),
     "tb":ff(r["total_buy_value_cr"]),"sc":ff(r["score"],1),"pos":posl})
# ---------- 3b. BUY ALERTS: fresh buys by good-score players ----------
rk=q.set_index("Player")
hi_thresh=float(np.nanpercentile(q["score"],80)) if len(q) else 0.0
awin=latest - pd.Timedelta(days=21)
buys=master[(master["Buy / Sell"]=="BUY")&(master["Date"]>=awin)&(master["Player"].isin(rk.index))].copy()
buys["Val"]=buys["Quantity"]*buys["Price"]
al=[]
for _,r in buys.iterrows():
    pr=rk.loc[r["Player"]]
    al.append({"d":str(r["Date"].date()),"p":r["Player"],"s":r["Symbol"],"n":secmap.get(r["Symbol"],""),
      "q":int(r["Quantity"]) if pd.notna(r["Quantity"]) else 0,"pr":ff(r["Price"]),
      "v":ff(r["Val"]/CR,3),"rk":int(pr["Rank"]),"sc":ff(pr["score"],1),
      "wr":ff(pr["win_rate_pct"],1),"vw":ff(pr["val_wtd_return_pct"],1),
      "hi":bool(pr["score"]>=hi_thresh)})
al=sorted(al,key=lambda x:(x["d"],x["sc"] or 0),reverse=True)[:500]
open(os.path.join(BASE,"alerts.json"),"w").write(json.dumps({"hi_thresh":round(hi_thresh,1),"window_days":21,"alerts":al},separators=(",",":")))
today_buys=[a for a in al if a["d"]==str(latest.date())]
hi_today=[a for a in today_buys if a["hi"]]

meta=dict(span=f"{master['Date'].min():%d-%b-%Y} to {latest:%d-%b-%Y}",
          gen=datetime.datetime.now().strftime("%d-%b-%Y %H:%M"),rows=len(master),latest=f"{latest:%d-%b-%Y}",n=len(data))
tpl=open(os.path.join(BASE,"dashboard_template.html")).read()
outhtml=(tpl.replace("__DATA__",json.dumps(data,separators=(",",":"))).replace("__ALERTS__",json.dumps(al,separators=(",",":"))).replace("__HITHRESH__",str(round(hi_thresh,1)))
 .replace("__SPAN__",meta["span"]).replace("__GEN__",meta["gen"])
 .replace("__N__",str(meta["n"])).replace("__ROWS__",f"{meta['rows']:,}").replace("__LATEST__",meta["latest"]))
open(os.path.join(BASE,"NSE_SmartMoney_Dashboard.html"),"w").write(outhtml)
# summary for the morning ping
top=q.head(10)[["Rank","Player","win_rate_pct","val_wtd_return_pct","total_realized_pnl_cr","realized_positions"]]
summ={"generated":meta["gen"],"data_through":meta["latest"],"deals":len(master),
      "players":len(q),"new_rows_today":int(added) if added else 0,"buys_latest_day":len(today_buys),"high_score_buys_latest_day":len(hi_today),"alerts_window":len(al),
      "top10":top.round(1).to_dict("records")}
open(os.path.join(BASE,"daily_summary.json"),"w").write(json.dumps(summ,indent=2))
print("dashboard + summary rebuilt. players:",len(q))
