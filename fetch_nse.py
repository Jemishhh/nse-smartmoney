#!/usr/bin/env python3
"""Fetch new NSE bulk deals since last_data_date into ./incoming (GitHub Actions safe)."""
import os,sys,time,json,datetime,requests
BASE=os.path.dirname(os.path.abspath(__file__)); INC=os.path.join(BASE,"incoming")
os.makedirs(INC,exist_ok=True)
IST=datetime.timezone(datetime.timedelta(hours=5,minutes=30))
today=datetime.datetime.now(IST).date()

def write_status(**kw):
    kw["checked_at_ist"]=datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M")
    open(os.path.join(BASE,"fetch_status.json"),"w").write(json.dumps(kw,indent=2))

try: last=datetime.date.fromisoformat(open(os.path.join(BASE,"last_data_date.txt")).read().strip())
except Exception: last=today-datetime.timedelta(days=7)
frm=last+datetime.timedelta(days=1)
if frm>today:
    print("already current:",last)
    write_status(ok=True,reason="already_current",last_data_date=str(last),windows_attempted=0,windows_ok=0)
    sys.exit(0)

H={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
   "Accept":"text/csv,application/json,text/plain,*/*","Accept-Language":"en-US,en;q=0.9",
   "Accept-Encoding":"gzip, deflate, br","Connection":"keep-alive",
   "Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin",
   "Sec-Ch-Ua":'"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
   "Sec-Ch-Ua-Mobile":"?0","Sec-Ch-Ua-Platform":'"Windows"',
   "Referer":"https://www.nseindia.com/report-detail/display-bulk-and-block-deals"}
s=requests.Session(); s.headers.update(H)
last_err=""
def prime():
    global last_err
    try:
        r1=s.get("https://www.nseindia.com/",timeout=20); time.sleep(1)
        r2=s.get("https://www.nseindia.com/market-data/large-deals",timeout=20); time.sleep(1)
        last_err=f"prime status {r1.status_code}/{r2.status_code}"
    except Exception as e:
        last_err=f"prime exception: {e}"; print("prime warn:",e)
prime()
def dmy(d): return d.strftime("%d-%m-%Y")
cur=frm; got=0; attempted=0
while cur<=today:
    end=min(cur+datetime.timedelta(days=5),today)
    url=f"https://www.nseindia.com/api/historicalOR/bulk-block-short-deals?optionType=bulk_deals&from={dmy(cur)}&to={dmy(end)}&csv=true"
    ok=False; attempted+=1
    for attempt in range(4):
        try:
            r=s.get(url,timeout=40)
            if r.status_code==200 and "Date" in r.text[:200]:
                fn=os.path.join(INC,f"deals_{dmy(cur)}_{dmy(end)}.csv"); open(fn,"w",encoding="utf-8").write(r.text)
                print("fetched",cur,"->",end,len(r.text),"bytes"); got+=1; ok=True; break
            else:
                snippet=r.text[:150].replace("\n"," ")
                last_err=f"HTTP {r.status_code}: {snippet}"
                print("bad resp",r.status_code,"retry",attempt,"body:",snippet)
                time.sleep(3+attempt*2); prime()
        except Exception as e:
            last_err=f"exception: {e}"
            print("err",e,"retry",attempt); time.sleep(3+attempt*2); prime()
    if not ok: print("FAILED window",cur,end,"-",last_err)
    cur=end+datetime.timedelta(days=1); time.sleep(1)
print("windows fetched:",got,"/",attempted)
write_status(ok=(got==attempted),reason=("all_ok" if got==attempted else ("partial" if got>0 else "all_failed")),
             last_data_date=str(last),windows_attempted=attempted,windows_ok=got,last_error=("" if got==attempted else last_err))
if got==0 and attempted>0:
    print("WARNING: every fetch window failed — likely NSE is blocking this runner's IP. See fetch_status.json / last_error above.")
