#!/usr/bin/env python3
"""Fetch new NSE bulk deals since last_data_date into ./incoming (GitHub Actions safe)."""
import os,sys,time,datetime,requests
BASE=os.path.dirname(os.path.abspath(__file__)); INC=os.path.join(BASE,"incoming")
os.makedirs(INC,exist_ok=True)
IST=datetime.timezone(datetime.timedelta(hours=5,minutes=30))
today=datetime.datetime.now(IST).date()
try: last=datetime.date.fromisoformat(open(os.path.join(BASE,"last_data_date.txt")).read().strip())
except Exception: last=today-datetime.timedelta(days=7)
frm=last+datetime.timedelta(days=1)
if frm>today: print("already current:",last); sys.exit(0)
H={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
   "Accept":"text/csv,application/json,text/plain,*/*","Accept-Language":"en-US,en;q=0.9",
   "Referer":"https://www.nseindia.com/report-detail/display-bulk-and-block-deals"}
s=requests.Session(); s.headers.update(H)
def prime():
    try: s.get("https://www.nseindia.com/",timeout=20); time.sleep(1); s.get("https://www.nseindia.com/market-data/large-deals",timeout=20); time.sleep(1)
    except Exception as e: print("prime warn:",e)
prime()
def dmy(d): return d.strftime("%d-%m-%Y")
cur=frm; got=0
while cur<=today:
    end=min(cur+datetime.timedelta(days=5),today)
    url=f"https://www.nseindia.com/api/historicalOR/bulk-block-short-deals?optionType=bulk_deals&from={dmy(cur)}&to={dmy(end)}&csv=true"
    ok=False
    for attempt in range(3):
        try:
            r=s.get(url,timeout=40)
            if r.status_code==200 and "Date" in r.text[:200]:
                fn=os.path.join(INC,f"deals_{dmy(cur)}_{dmy(end)}.csv"); open(fn,"w",encoding="utf-8").write(r.text)
                print("fetched",cur,"->",end,len(r.text),"bytes"); got+=1; ok=True; break
            else:
                print("bad resp",r.status_code,"retry",attempt); time.sleep(3); prime()
        except Exception as e:
            print("err",e,"retry",attempt); time.sleep(3); prime()
    if not ok: print("FAILED window",cur,end)
    cur=end+datetime.timedelta(days=1); time.sleep(1)
print("windows fetched:",got)
