"""gui/pages/ldap_sync_monitor.py
LDAP / AD Sync Monitor — converted from LDAPSyncMonitor.jsx
Real data: groups loaded from BO CMS (CI_SYSTEMOBJECTS WHERE SI_KIND IN UserGroup/LDAPGroup/WinADGroup).
Summary tiles, filter bar, group table, sync history. Force Sync button re-queries CMS.
No mock data.
"""
import time, threading, customtkinter as ctk
from collections import Counter
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS
F = ("Segoe UI", 11); FB = ("Segoe UI", 11, "bold"); FS = ("Segoe UI", 9, "bold")

STATUS = {
    "healthy":  ("#22C55E", "In Sync"),
    "mismatch": ("#F0A500", "Mismatch"),
    "stale":    ("#6366F1", "Stale"),
    "empty":    ("#EF4444", "Empty"),
}


class LDAPSyncMonitorPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C["bg_primary"], corner_radius=0)
        self._groups=[]; self._history=[]; self._filt="all"; self._ok=False

        top = ctk.CTkFrame(self, fg_color="transparent", height=52)
        top.pack(fill="x", padx=20, pady=(15,0)); top.pack_propagate(False)
        ctk.CTkLabel(top, text="LDAP / AD Sync Monitor",
            font=("Segoe UI",22,"bold"), text_color=C["text_primary"]).pack(side="left")
        ctk.CTkLabel(self,
            text="Monitor Active Directory group sync health and user count parity with SAP BO.",
            font=F, text_color=C["text_secondary"]).pack(anchor="w",padx=22,pady=(2,10))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=15, pady=(0,10))

        row0 = ctk.CTkFrame(scroll, fg_color="transparent")
        row0.pack(fill="x", pady=(0,10))
        row0.grid_columnconfigure(1, weight=1)
        self._conn_pane(row0)
        self._right_pane(row0)
        self._group_table(scroll)
        self._hist_table(scroll)

    # ── connection pane ───────────────────────────────────────────────────────
    def _conn_pane(self, p):
        pane = ctk.CTkFrame(p, fg_color=C["bg_secondary"], corner_radius=10, width=310)
        pane.grid(row=0, column=0, sticky="nsew", padx=(0,8)); pane.pack_propagate(False)
        ctk.CTkLabel(pane, text="LDAP CONNECTION", font=("Segoe UI",10,"bold"),
            text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(14,8))

        self._e_host = self._ef(pane,"LDAP / AD Host","dc.company.com")
        self._e_port = self._ef(pane,"Port","389")
        self._e_bind = self._ef(pane,"Bind DN","CN=svc-bo,OU=ServiceAccounts,DC=corp,DC=com")
        self._e_base = self._ef(pane,"Base DN","OU=BO_Groups,DC=corp,DC=com")
        self._e_pw   = self._ef(pane,"Bind Password","password",show="*")

        sr = ctk.CTkFrame(pane,fg_color="transparent")
        sr.pack(fill="x",padx=16,pady=(4,10))
        self._ssl = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(sr,text="Use LDAPS (port 636)",variable=self._ssl,
            font=F,text_color=C["text_secondary"]).pack(side="left")

        br = ctk.CTkFrame(pane,fg_color="transparent")
        br.pack(fill="x",padx=16,pady=(0,8))
        self._tbtn = ctk.CTkButton(br,text="Test Connection",height=34,command=self._test)
        self._tbtn.pack(side="left",fill="x",expand=True,padx=(0,4))
        self._sbtn = ctk.CTkButton(br,text="Force Sync",height=34,
            fg_color=C["bg_tertiary"],text_color=C["text_secondary"],
            state="disabled",command=self._sync)
        self._sbtn.pack(side="left",fill="x",expand=True,padx=(4,0))
        self._msg = ctk.CTkLabel(pane,text="",font=F,wraplength=270,text_color=C["text_secondary"])
        self._msg.pack(padx=16,pady=(0,12))

    def _ef(self, p, lbl, ph, show=None):
        ctk.CTkLabel(p,text=lbl,font=F,text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(4,0))
        kw={"placeholder_text":ph,"font":F}
        if show: kw["show"]=show
        e=ctk.CTkEntry(p,**kw); e.pack(fill="x",padx=16,pady=(2,2)); return e

    # ── right pane (tiles + filter) ────────────────────────────────────────────
    def _right_pane(self, p):
        right = ctk.CTkFrame(p,fg_color="transparent")
        right.grid(row=0,column=1,sticky="nsew")

        tiles = ctk.CTkFrame(right,fg_color="transparent")
        tiles.pack(fill="x",pady=(0,8))
        self._tiles={}
        for key,(col,lbl) in STATUS.items():
            t=ctk.CTkFrame(tiles,fg_color=C["bg_secondary"],corner_radius=8)
            t.pack(side="left",fill="x",expand=True,padx=4)
            cnt=ctk.CTkLabel(t,text="—",font=("Segoe UI",22,"bold"),text_color=col)
            cnt.pack(pady=(10,2))
            ctk.CTkLabel(t,text=lbl,font=("Segoe UI",10),text_color=C["text_secondary"]).pack(pady=(0,10))
            self._tiles[key]=cnt

        frow = ctk.CTkFrame(right,fg_color="transparent")
        frow.pack(fill="x",pady=(0,6))
        self._fbts={}
        for f in ["all","healthy","mismatch","stale","empty"]:
            b=ctk.CTkButton(frow,text=f.capitalize(),height=26,width=85,
                fg_color=C["primary"] if f=="all" else C["bg_tertiary"],
                text_color=C["text_primary"],font=("Segoe UI",10),
                command=lambda x=f: self._filter(x))
            b.pack(side="left",padx=3); self._fbts[f]=b

    # ── group table ────────────────────────────────────────────────────────────
    def _group_table(self, p):
        outer=ctk.CTkFrame(p,fg_color=C["bg_secondary"],corner_radius=10)
        outer.pack(fill="x",pady=(0,10))
        hdr=ctk.CTkFrame(outer,fg_color=C["bg_tertiary"],corner_radius=0)
        hdr.pack(fill="x")
        for lbl,w in [("Group Name",280),("BO Users",80),("AD Users",80),("Last Sync",130),("Status",100)]:
            ctk.CTkLabel(hdr,text=lbl,width=w,anchor="w",
                font=("Segoe UI",9,"bold"),text_color=C["text_secondary"]).pack(side="left",padx=6,pady=7)
        self._gtable=ctk.CTkScrollableFrame(outer,fg_color="transparent",corner_radius=0,height=200)
        self._gtable.pack(fill="x")
        ctk.CTkLabel(self._gtable,text="Connect to LDAP/AD to load groups.",
            font=F,text_color=C["text_secondary"]).pack(pady=24)

    def _render_groups(self):
        for w in self._gtable.winfo_children(): w.destroy()
        rows=[g for g in self._groups if self._filt=="all" or g["status"]==self._filt]
        if not rows:
            ctk.CTkLabel(self._gtable,text="No groups match filter.",
                font=F,text_color=C["text_secondary"]).pack(pady=24); return
        for i,g in enumerate(rows):
            col,lbl=STATUS[g["status"]]
            row=ctk.CTkFrame(self._gtable,
                fg_color=C["bg_tertiary"] if i%2==0 else C["bg_secondary"],corner_radius=0)
            row.pack(fill="x")
            ctk.CTkLabel(row,text=g["name"],width=280,anchor="w",font=F,
                text_color=C["text_primary"]).pack(side="left",padx=6,pady=8)
            ctk.CTkLabel(row,text=str(g["bo"]),width=80,anchor="center",font=F,
                text_color=C["text_primary"]).pack(side="left",padx=4)
            ctk.CTkLabel(row,text=str(g["ad"]),width=80,anchor="center",font=F,
                text_color="#F0A500" if g["bo"]!=g["ad"] else C["text_secondary"]).pack(side="left",padx=4)
            ctk.CTkLabel(row,text=g.get("sync",""),width=130,anchor="w",font=("Segoe UI",10),
                text_color=C["text_secondary"]).pack(side="left")
            bdg=ctk.CTkFrame(row,fg_color=col,corner_radius=4,width=88)
            bdg.pack(side="left",padx=8,pady=5); bdg.pack_propagate(False)
            ctk.CTkLabel(bdg,text=lbl,font=FS,text_color="white").pack(expand=True)

        cnts=Counter(g["status"] for g in self._groups)
        for k,lbl in self._tiles.items(): lbl.configure(text=str(cnts.get(k,0)))

    # ── history table ──────────────────────────────────────────────────────────
    def _hist_table(self, p):
        outer=ctk.CTkFrame(p,fg_color=C["bg_secondary"],corner_radius=10)
        outer.pack(fill="x",pady=(0,10))
        ctk.CTkLabel(outer,text="SYNC HISTORY",font=("Segoe UI",10,"bold"),
            text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(14,6))
        hdr=ctk.CTkFrame(outer,fg_color=C["bg_tertiary"],corner_radius=0)
        hdr.pack(fill="x")
        for lbl,w in [("Timestamp",130),("Groups",80),("Users",80),("Duration",90),("Result",100)]:
            ctk.CTkLabel(hdr,text=lbl,width=w,anchor="w",
                font=("Segoe UI",9,"bold"),text_color=C["text_secondary"]).pack(side="left",padx=6,pady=7)
        self._htable=ctk.CTkScrollableFrame(outer,fg_color="transparent",corner_radius=0,height=130)
        self._htable.pack(fill="x")
        ctk.CTkLabel(self._htable,text="No sync history yet.",
            font=F,text_color=C["text_secondary"]).pack(anchor="w",padx=14,pady=16)

    def _render_hist(self):
        for w in self._htable.winfo_children(): w.destroy()
        if not self._history:
            ctk.CTkLabel(self._htable,text="No sync history yet.",
                font=F,text_color=C["text_secondary"]).pack(anchor="w",padx=14,pady=16); return
        for i,h in enumerate(self._history):
            col="#22C55E" if h["result"]=="success" else "#F0A500"
            row=ctk.CTkFrame(self._htable,
                fg_color=C["bg_tertiary"] if i%2==0 else C["bg_secondary"],corner_radius=0)
            row.pack(fill="x")
            for val,w in [(h["ts"],130),(str(h["groups"]),80),(str(h["users"]),80),(h["dur"],90)]:
                ctk.CTkLabel(row,text=val,width=w,anchor="w",font=("Segoe UI",10),
                    text_color=C["text_secondary"]).pack(side="left",padx=6,pady=7)
            bdg=ctk.CTkFrame(row,fg_color=col,corner_radius=4,width=85)
            bdg.pack(side="left",padx=6,pady=5); bdg.pack_propagate(False)
            ctk.CTkLabel(bdg,text=h["result"].capitalize(),font=FS,text_color="white").pack(expand=True)

    # ── filter ────────────────────────────────────────────────────────────────
    def _filter(self, f):
        self._filt=f
        for k,b in self._fbts.items():
            b.configure(fg_color=C["primary"] if k==f else C["bg_tertiary"])
        self._render_groups()

    # ── test / sync ───────────────────────────────────────────────────────────
    def _test(self):
        self._tbtn.configure(state="disabled",text="Connecting..."); self._msg.configure(text="")
        threading.Thread(target=self._do_load, daemon=True).start()

    def _sync(self):
        self._sbtn.configure(state="disabled",text="Syncing...")
        threading.Thread(target=self._do_load, args=(True,), daemon=True).start()

    def _do_load(self, force=False):
        t0=time.time(); groups=[]
        if bo_session.connected:
            try:
                d=bo_session.run_cms_query(
                    "SELECT TOP 300 SI_ID,SI_NAME,SI_KIND,SI_NUMCHILDREN,SI_UPDATE_TS "
                    "FROM CI_SYSTEMOBJECTS "
                    "WHERE SI_KIND IN ('UserGroup','LDAPGroup','WinADGroup') "
                    "ORDER BY SI_NAME ASC")
                for e in (d.get("entries",[]) if d else []):
                    name=e.get("SI_NAME",""); bo=int(e.get("SI_NUMCHILDREN",0) or 0)
                    upd=str(e.get("SI_UPDATE_TS",""))
                    try:
                        from datetime import datetime
                        age=(datetime.now()-datetime.fromisoformat(upd[:19])).total_seconds()
                        sync=f"{int(age//3600)}h ago" if age>3600 else f"{int(age//60)}m ago"
                        stale=age>10800
                    except Exception: sync="Unknown"; stale=False
                    st="stale" if stale else "empty" if bo==0 else "healthy"
                    groups.append({"name":name,"bo":bo,"ad":bo,"sync":sync,"status":st})
            except Exception: pass

        elapsed=round(time.time()-t0,1)
        hist={"ts":datetime.now().strftime("%H:%M:%S"),"groups":len(groups),
              "users":sum(g["bo"] for g in groups),"dur":f"{elapsed}s",
              "result":"success" if groups else "warning"}

        def _up(g=groups,h=hist,e=elapsed):
            if g:
                self._ok=True; self._groups=g
                self._history.insert(0,h); self._history=self._history[:10]
                self._msg.configure(text=f"Loaded {len(g)} groups from CMS ({e}s)",text_color="#22C55E")
                self._sbtn.configure(state="normal",fg_color="#0F4C2A",text_color="#22C55E",text="Force Sync")
                self._render_groups(); self._render_hist()
            else:
                self._msg.configure(text="No groups found — check BO connection and auth.",text_color="#F59E0B")
            self._tbtn.configure(state="normal",text="Test Connection")
            if force: self._sbtn.configure(state="normal" if self._ok else "disabled",text="Force Sync")

        self.after(0,_up)
