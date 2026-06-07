#!/usr/bin/env python3
"""
Aurora Outpost CME Scoreboard card.

CCMC CME Scoreboard = source of truth for what's in flight + arrival timing.
Renders a rich table (Event/Source/Type/Arrival/Window/Lead/Models/Kp) plus a
Sun->Earth "approach lane" queue panel (positions from CCMC launch->avg-arrival
time fraction; Drag-Based Model distance is a fallback only).

Posts to Telegram (@auroraoutpost) + the Facebook Page ONLY when the active-CME
set changes (add/remove) and is non-empty. N->0 never posts an "all clear" card;
it just updates state so the next appearance posts again.

Env:
  AO_CME_TEMPLATE   template png       (default: template_ao_cme.png)
  AO_CME_DATA_DIR   state dir          (default: data_ao)
  AO_CME_OUTPUT     output png         (default: output/ao_cme_scoreboard.png)
  AO_TELEGRAM_BOT_TOKEN / AO_TELEGRAM_CHANNEL_ID   Telegram dest
  AO_FB_PAGE_ID / AO_FB_PAGE_TOKEN                 Facebook Page dest
  AO_CME_DRYRUN=1   render only, never post
"""
import os, re, json, sys
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
import requests
from PIL import Image, ImageDraw, ImageFont

URL = 'https://kauai.ccmc.gsfc.nasa.gov/CMEscoreboard/'
POSITIONS_URL = 'https://data.auroraoutpost.com/cme_positions.json'
TEMPLATE = os.environ.get('AO_CME_TEMPLATE', 'template_ao_cme.png')
DATA_DIR = os.environ.get('AO_CME_DATA_DIR', 'data_ao')
OUTPUT   = os.environ.get('AO_CME_OUTPUT', 'output/ao_cme_scoreboard.png')
STATE    = os.path.join(DATA_DIR, 'posted_cme_set.json')
DRYRUN   = os.environ.get('AO_CME_DRYRUN') == '1'

CME_COLORS = ['#00FFF0','#FF00FF','#00FF00','#FFFF00','#FF0080','#0080FF','#FF8000','#80FF00']

# ---- fonts: DejaVu on VPS, Windows fallback for local rendering ----
_REG = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/segoeui.ttf', 'arial.ttf']
_BLD = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 'C:/Windows/Fonts/segoeuib.ttf', 'arialbd.ttf']
def font(sz, bold=False):
    for p in (_BLD if bold else _REG):
        try: return ImageFont.truetype(p, sz)
        except Exception: continue
    return ImageFont.load_default()

# ---------- fetch + parse (CCMC) ----------
class _P(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]
    def handle_starttag(self,t,a):
        if t in {'br','p','div','li','tr','td','th','h1','h2','h3','h4','h5','h6'}: self.parts.append('\n')
    def handle_endtag(self,t):
        if t in {'p','div','li','tr','td','th','h1','h2','h3','h4','h5','h6'}: self.parts.append('\n')
    def handle_data(self,d):
        x=d.strip()
        if x: self.parts.append(x)

def get_lines():
    r=requests.get(URL,timeout=30); r.raise_for_status()
    p=_P(); p.feed(r.text)
    return [l for l in (re.sub(r'\s+',' ',x).strip() for x in '\n'.join(p.parts).splitlines()) if l]

TS = re.compile(r'\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::\d{2})?Z\b')
def parse_dt(s):
    m=TS.search(s or '')
    return datetime.strptime(m.group(1),'%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc) if m else None
METHODS=['WSA-ENLIL','Ensemble','CMEFM','Met Office','BoM','NOAA/SWPC','SIDC','Other (','KSWC','SWASFC']

def parse_active():
    lines=get_lines()
    ai=lines.index('Active CMEs:'); pi=lines.index('Past CMEs:')
    sec=lines[ai+1:pi]
    blocks=[]; cur=None
    for l in sec:
        if l.startswith('CME: '):
            if cur: blocks.append(cur)
            cur={'id':l[5:].strip(),'lines':[],'note':''}
        elif cur is not None:
            if l.startswith('CME Note:'): cur['note']=l[len('CME Note:'):].strip()
            cur['lines'].append(l)
    if cur: blocks.append(cur)

    events=[]
    for b in blocks:
        m=re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})',b['id'])
        ev_dt=datetime.strptime(m.group(1)+' '+m.group(2),'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc) if m else None
        chunks=[]; c=[]
        for l in b['lines']:
            if l=='Detail': chunks.append(c); c=[]
            else: c.append(l)
        if c: chunks.append(c)
        model_arr=[]; kp_lo=[]; kp_hi=[]; avg=None; med=None; nmodels=0
        for ch in chunks:
            txt=' '.join(ch)
            arr=None
            for x in ch:
                if parse_dt(x): arr=parse_dt(x); break
            after=(arr is not None) and (ev_dt is None or arr>ev_dt+timedelta(hours=6))
            is_avg='Average of all Methods' in txt
            is_med='Median of all Methods' in txt
            is_model=any(mk in txt for mk in METHODS) and not is_avg and not is_med
            if is_avg and after: avg=arr
            if is_med and after: med=arr
            if is_model and after:
                model_arr.append(arr); nmodels+=1
                km=re.search(r'Max Kp Range:\s*([\d.]+)\s*-\s*([\d.]+)',txt)
                if km: kp_lo.append(float(km.group(1))); kp_hi.append(float(km.group(2)))
        if model_arr and avg is None:
            avg=datetime.fromtimestamp(sum(d.timestamp() for d in model_arr)/len(model_arr),tz=timezone.utc)
        window=(min(model_arr),max(model_arr)) if model_arr else (None,None)
        kp=(min(kp_lo),max(kp_hi)) if kp_lo else (None,None)
        note=b['note']
        ar=re.search(r'(?:Active Region|AR)\s+0*(\d+)',note)
        loc=re.search(r'\(([NS]\d+[EW]\d+)\)',note)
        flare=re.search(r'\b([XMC]\d(?:\.\d)?)\s*flare',note)
        nl=note.lower(); halo='—'
        if 'full halo' in nl: halo='Full Halo'
        elif 'partial halo' in nl: halo='Partial Halo'
        elif 'glancing' in nl: halo='Glancing'
        elif 'halo' in nl: halo='Halo'
        elif 'faint' in nl: halo='Faint'
        events.append({'id':b['id'],'event_dt':ev_dt,'avg':avg,'window':window,'models':nmodels,'kp':kp,
            'ar':('AR '+ar.group(1)[-4:]) if ar else '—','loc':loc.group(1) if loc else '—',
            'flare':flare.group(1) if flare else '—','halo':halo})
    return events

def fetch_positions():
    """DBM positions (app) — fallback for placing a CME when CCMC timing is absent."""
    try:
        r=requests.get(POSITIONS_URL,timeout=15)
        if r.ok:
            out={}
            for c in r.json().get('cmes',[]):
                d=parse_dt(c.get('id','')) or parse_dt(c.get('source',{}).get('launch_time','') or '')
                if d: out[d.strftime('%Y-%m-%dT%H:%M')]=c
            return out
    except Exception: pass
    return {}

# ---------- formatting ----------
MON=['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
def fmt(dt): return f'{MON[dt.month]} {dt.day} {dt:%H:%M}' if dt else '—'
def lead_str(dt):
    if not dt: return '—'
    h=(dt-datetime.now(timezone.utc)).total_seconds()/3600
    return f'{h:+.0f} h' if abs(h)>=1 else '<1 h'
def gscale(hi):
    return {5:'G1',6:'G2',7:'G3',8:'G4',9:'G5'}.get(int(hi),'—') if hi is not None else '—'
def hx(h): return tuple(int(h[i:i+2],16) for i in (1,3,5))

# ---------- render ----------
def render(events):
    img=Image.open(TEMPLATE).convert('RGBA'); W,H=img.size
    ov=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    mx=70; x0,x1=mx,W-mx; y0=250; pad=30; head_h=46; row_h=60; foot_h=42
    n=max(1,len(events)); y1=y0+pad+head_h+n*row_h+12+foot_h+pad
    d.rounded_rectangle([x0,y0,x1,y1],radius=18,fill=(18,27,34,196),outline=(150,200,210,150),width=2)
    cols=[('EVENT (UTC)',0.12,'l'),('SOURCE',0.14,'l'),('TYPE',0.17,'l'),('ARRIVAL (avg)',0.13,'c'),
          ('WINDOW',0.17,'c'),('LEAD',0.07,'c'),('MODELS',0.05,'c'),('PRED Kp / G',0.15,'c')]
    usable=(x1-x0)-2*pad; xs=[]; acc=x0+pad
    for _,w,_a in cols: xs.append(acc); acc+=usable*w
    xs.append(x1-pad)
    def cell(i): return xs[i],xs[i+1]
    def put(i,txt,y,fnt,fill,align):
        l,r=cell(i); b=d.textbbox((0,0),txt,font=fnt); tw=b[2]-b[0]
        x=l+6 if align=='l' else (r-6-tw if align=='r' else (l+r)/2-tw/2)
        d.text((x,y),txt,font=fnt,fill=fill)
    def ctext(cx,cy,txt,fnt,fill):
        b=d.textbbox((0,0),txt,font=fnt); d.text((cx-(b[2]-b[0])/2,cy),txt,font=fnt,fill=fill)

    fh=font(18,True); fr=font(23); frb=font(24,True); fsmall=font(15)
    cyan=(120,225,240); purple=(200,180,255); green=(150,240,200); amber=(255,205,130); white=(238,240,244)
    hy=y0+pad
    for i,(label,_w,al) in enumerate(cols): put(i,label,hy,fh,(120,185,200),'l' if al=='l' else al)
    d.line([x0+pad,hy+head_h-8,x1-pad,hy+head_h-8],fill=(120,185,200,90),width=1)

    ry=hy+head_h+4
    for idx,e in enumerate(events):
        if idx>0: d.line([x0+pad,ry-6,x1-pad,ry-6],fill=(150,200,210,40),width=1)
        ty=ry+(row_h-26)//2; col=e['color']
        klo,khi=e['kp']; kp_txt=f"{klo:.0f}–{khi:.0f}  {gscale(khi)}" if klo is not None else '—'
        kcol=amber if (khi and khi>=7) else green
        wlo,whi=e['window']; win=f"{fmt(wlo)} → {whi:%H:%M}" if wlo else '—'
        models_txt=str(e['models']) if e['models'] else '—'
        src_txt=e['ar']+(f"  {e['loc']}" if e['loc']!='—' else '')
        type_txt=e['halo']+(f" · {e['flare']}" if e['flare']!='—' else '')
        chx=xs[0]+12; chy=ty+12
        d.ellipse([chx-10,chy-10,chx+10,chy+10],fill=col+(255,))
        nb=d.textbbox((0,0),str(e['num']),font=fh)
        d.text((chx-(nb[2]-nb[0])/2,chy-nb[3]/2-1),str(e['num']),font=fh,fill=(8,12,16))
        d.text((xs[0]+28,ty),fmt(e['event_dt']),font=fr,fill=white)
        put(1,src_txt,ty,fr,white,'l'); put(2,type_txt,ty,fr,green,'l')
        put(3,fmt(e['avg']),ty,frb,cyan,'c'); put(4,win,ty,fr,purple,'c')
        put(5,lead_str(e['avg']),ty,fr,white,'c'); put(6,models_txt,ty,frb,white,'c')
        put(7,kp_txt,ty,frb,kcol,'c')
        ry+=row_h

    now=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    fy=y1-pad-foot_h+8
    d.line([x0+pad,fy-6,x1-pad,fy-6],fill=(120,185,200,70),width=1)
    d.text((x0+pad+6,fy),f"Updated {now} UTC   ·   Active CMEs: {len(events)}",font=fsmall,fill=(180,195,210))
    rt="Source: NASA CCMC CME Scoreboard   ·   auroraoutpost.com"
    b=d.textbbox((0,0),rt,font=fsmall); d.text((x1-pad-6-(b[2]-b[0]),fy),rt,font=fsmall,fill=(150,170,185))

    # queue panel
    def dash(xa,y,xb,seg=10,gap=7,fill=(110,160,205,120),w=2):
        x=xa
        while x<xb: d.line([x,y,min(x+seg,xb),y],fill=fill,width=w); x+=seg+gap
    qy0=y1+22; qy1=qy0+196
    d.rounded_rectangle([x0,qy0,x1,qy1],radius=18,fill=(18,27,34,196),outline=(150,200,210,150),width=2)
    d.text((x0+pad,qy0+14),'CMEs IN FLIGHT',font=font(18,True),fill=(120,185,200))
    lane_y=(qy0+qy1)//2+16; sunx=x0+pad+66; sunr=38; earthx=x1-pad-58; earthr=15
    sun_edge=sunx+sunr; earth_edge=earthx-earthr
    dash(sun_edge,lane_y,earth_edge)
    for r,al in [(sunr+26,34),(sunr+12,60)]: d.ellipse([sunx-r,lane_y-r,sunx+r,lane_y+r],fill=(255,150,40,al))
    d.ellipse([sunx-sunr,lane_y-sunr,sunx+sunr,lane_y+sunr],fill=(255,136,0,255))
    d.ellipse([sunx-24,lane_y-24,sunx+24,lane_y+24],fill=(255,212,72,255))
    ctext(sunx,lane_y-9,'SUN',font(17,True),(60,30,0))
    d.ellipse([earthx-earthr-6,lane_y-earthr-6,earthx+earthr+6,lane_y+earthr+6],fill=(70,140,230,55))
    d.ellipse([earthx-earthr,lane_y-earthr,earthx+earthr,lane_y+earthr],fill=(46,100,180,255))
    d.ellipse([earthx-7,lane_y-9,earthx+1,lane_y-1],fill=(150,195,255,255))
    ctext(earthx,lane_y+earthr+6,'EARTH',font(14,True),(170,200,235))
    now_dt=datetime.now(timezone.utc)
    for e in events:
        frac=e.get('frac')
        if frac is None and e['avg'] and e['event_dt']:
            frac=(now_dt-e['event_dt']).total_seconds()/max(1.0,(e['avg']-e['event_dt']).total_seconds())
        if frac is None: frac=0.5
        frac=min(0.97,max(0.04,frac)); cx=sun_edge+frac*(earth_edge-sun_edge); col=e['color']
        d.line([sun_edge,lane_y,cx,lane_y],fill=col+(120,),width=3)
        d.ellipse([cx-17,lane_y-17,cx+17,lane_y+17],fill=col+(55,))
        d.ellipse([cx-8,lane_y-8,cx+8,lane_y+8],fill=col+(255,))
        ctext(cx,lane_y-32,str(e['num']),font(17,True),col)
        ctext(cx,lane_y+13,lead_str(e['avg']),font(15),(180,195,210))

    os.makedirs(os.path.dirname(OUTPUT) or '.',exist_ok=True)
    Image.alpha_composite(img,ov).convert('RGB').save(OUTPUT)
    return OUTPUT

# ---------- posting ----------
def _social_text(events):
    n=len(events); soon=events[0]
    return (f"CME Scoreboard — {n} Earth-directed CME{'s' if n!=1 else ''} in flight\n"
            f"Soonest arrival: {fmt(soon['avg'])} UTC ({lead_str(soon['avg'])})\n"
            f"Updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n"
            f"auroraoutpost.com")

def post_telegram(path, caption):
    token=os.environ.get('AO_TELEGRAM_BOT_TOKEN'); chat=os.environ.get('AO_TELEGRAM_CHANNEL_ID')
    if not (token and chat): print('[tg] no token/chat — skip'); return
    try:
        with open(path,'rb') as ph:
            r=requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',
                data={'chat_id':chat,'caption':caption}, files={'photo':ph}, timeout=90)
        print('[tg]', 'ok' if r.ok else r.text[:160])
    except Exception as e: print('[tg] error', e)

def post_facebook(path, caption):
    pid=os.environ.get('AO_FB_PAGE_ID'); tok=os.environ.get('AO_FB_PAGE_TOKEN')
    if not (pid and tok): print('[fb] no token — skip'); return
    try:
        with open(path,'rb') as f:
            r=requests.post(f'https://graph.facebook.com/v21.0/{pid}/photos',
                data={'message':caption,'access_token':tok}, files={'source':f}, timeout=60)
        print('[fb]', 'posted' if r.ok else r.text[:160])
    except Exception as e: print('[fb] error', e)

# A set change must persist this many consecutive runs before we post — rides
# out CCMC's transient scoreboard scrape flicker so a CME briefly dropping then
# reappearing never produces a flapping pair of Telegram/FB posts.
CONFIRM_RUNS = 2

def load_state():
    """Returns {'posted', 'candidate', 'candidate_count'} or None (first run).
    Migrates the legacy bare-list format (just the posted set)."""
    try:
        with open(STATE) as f: d=json.load(f)
    except Exception:
        return None
    if isinstance(d, list):  # legacy: just the posted-set list
        return {'posted': d, 'candidate': [], 'candidate_count': 0}
    return d
def save_state(posted, candidate, count):
    os.makedirs(DATA_DIR,exist_ok=True)
    with open(STATE,'w') as f:
        json.dump({'posted': sorted(posted), 'candidate': sorted(candidate),
                   'candidate_count': count}, f)

# ---------- main ----------
def main():
    try:
        events=parse_active()
    except Exception as e:
        print(f'[ccmc] fetch/parse failed: {e} — keeping previous card'); sys.exit(0)
    events=[e for e in events if e['avg']]
    events.sort(key=lambda e: e['avg'])
    positions=fetch_positions()
    now_dt=datetime.now(timezone.utc)
    for i,e in enumerate(events):
        e['color']=hx(CME_COLORS[i%len(CME_COLORS)]); e['num']=i+1
        # position fraction: CCMC timing primary; DBM distance_au fallback
        e['frac']=(now_dt-e['event_dt']).total_seconds()/max(1.0,(e['avg']-e['event_dt']).total_seconds())
        if e['event_dt']:
            p=positions.get(e['event_dt'].strftime('%Y-%m-%dT%H:%M'))
            if p and not e['avg']:
                au=p.get('position',{}).get('distance_au')
                if au: e['frac']=au

    render(events)
    cur={e['id'] for e in events}
    st=load_state()
    posted = set(st['posted']) if st else None
    cand   = set(st.get('candidate', [])) if st else set()
    cand_n = st.get('candidate_count', 0) if st else 0
    print(f'[set] current={sorted(cur)} posted={sorted(posted) if posted is not None else None} '
          f'candidate={sorted(cand)} count={cand_n}')

    if DRYRUN:
        print('[dryrun] rendered only, no post'); return

    # No change vs the last posted set — clear any pending flicker candidate.
    if posted is not None and cur == posted:
        if cand_n: save_state(posted, set(), 0)
        print('[set] unchanged — no post'); return

    # A change is in play. Require it to repeat CONFIRM_RUNS times before acting,
    # so a one-off CCMC scrape flicker can't post a flapping pair.
    if cur == cand:
        cand_n += 1
    else:
        cand, cand_n = cur, 1

    if cand_n < CONFIRM_RUNS:
        print(f'[set] change pending confirmation ({cand_n}/{CONFIRM_RUNS}) — not posting yet')
        save_state(posted if posted is not None else set(), cand, cand_n); return

    # Confirmed change. Post only when non-empty; N->0 updates state silently.
    if cur:
        cap=_social_text(events)
        post_telegram(OUTPUT, cap); post_facebook(OUTPUT, cap)
        print('[set] confirmed change — posted'); save_state(cur, set(), 0)
    else:
        print('[set] confirmed drop to zero — no post, state updated'); save_state(set(), set(), 0)

if __name__ == '__main__':
    main()
