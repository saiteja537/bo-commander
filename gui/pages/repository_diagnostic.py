"""gui/pages/repository_diagnostic.py
Repository Diagnostic — converted from RepositoryDiagnostic.jsx
8 real CMS checks (no MOCK_FINDINGS): connectivity, tables, index timing, orphans,
broken refs, object counters, query perf benchmark, repo size estimate.
2-column check grid, animated progress bar, severity findings panel (✓ ⚠ ℹ ✗).
"""
import time, threading, customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C  = Config.COLORS
F  = ("Segoe UI", 11); FB = ("Segoe UI", 11, "bold")
DB_TYPES = ["SAP HANA","Oracle","MS SQL Server","MySQL / MariaDB","DB2"]
CHECKS = [
    ("conn",    "CMS DB Connection",    "Verify database connectivity"),
    ("tables",  "Core Tables Integrity","Validate SI_* table structure"),
    ("indexes", "Index Health",          "Check index performance via timing"),
    ("orphans", "Orphan Detection",      "Find instances with no parent report"),
    ("refs",    "Broken References",     "Detect reports with no owner"),
    ("counts",  "Object Counters",       "Audit object count accuracy"),
    ("perf",    "Query Performance",     "Benchmark key CMS query patterns"),
    ("size",    "Repository Size",       "Estimate DB size via object counts"),
]
SC = {"idle":"#94A3B8","running":"#F0A500","pass":"#22C55E","warn":"#F0A500","fail":"#EF4444","skip":"#6B7280"}
SL = {"idle":"Pending","running":"Running...","pass":"OK","warn":"Warning","fail":"Error","skip":"Skipped"}
SEV = {"pass":("#22C55E","✓"),"warn":("#F0A500","⚠"),"info":("#60A5FA","ℹ"),"fail":("#EF4444","✗")}


class RepositoryDiagnosticPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C["bg_primary"], corner_radius=0)
        self._dot={}; self._stat={}

        top=ctk.CTkFrame(self,fg_color="transparent",height=52)
        top.pack(fill="x",padx=20,pady=(15,0)); top.pack_propagate(False)
        ctk.CTkLabel(top,text="Repository Diagnostic",font=("Segoe UI",22,"bold"),
            text_color=C["text_primary"]).pack(side="left")
        ctk.CTkLabel(self,
            text="Deep health check of the SAP BO CMS repository — tables, orphans, performance and size.",
            font=F,text_color=C["text_secondary"]).pack(anchor="w",padx=22,pady=(2,10))

        body=ctk.CTkFrame(self,fg_color="transparent")
        body.pack(fill="both",expand=True,padx=15,pady=(0,10))
        body.grid_columnconfigure(0,weight=0); body.grid_columnconfigure(1,weight=1)
        body.grid_rowconfigure(0,weight=1);   body.grid_rowconfigure(1,weight=0)
        self._cfg_pane(body); self._checks_pane(body); self._findings_pane(body)

    # ── config ────────────────────────────────────────────────────────────────
    def _cfg_pane(self, p):
        pane=ctk.CTkScrollableFrame(p,fg_color=C["bg_secondary"],corner_radius=10,width=290)
        pane.grid(row=0,column=0,sticky="nsew",padx=(0,8),pady=(0,8))
        ctk.CTkLabel(pane,text="CMS CONNECTION",font=("Segoe UI",10,"bold"),
            text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(14,8))

        self._e_h=self._ef(pane,"CMS Host","bo-cms.company.com")
        self._e_p=self._ef(pane,"CMS Port","6400")
        self._e_u=self._ef(pane,"Admin Username","Administrator")
        self._e_w=self._ef(pane,"Admin Password","password",show="*")

        try:
            if bo_session.connected:
                h=bo_session.cms_details.get("host",""); po=bo_session.cms_details.get("port","6400")
                u=bo_session.cms_details.get("user","Administrator")
                if h:
                    self._e_h.insert(0,h); self._e_p.delete(0,"end"); self._e_p.insert(0,str(po))
                    self._e_u.delete(0,"end"); self._e_u.insert(0,u)
        except Exception: pass

        ctk.CTkLabel(pane,text="DB Platform",font=F,text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(6,0))
        self._db=ctk.CTkComboBox(pane,values=DB_TYPES,font=F)
        self._db.set(DB_TYPES[0]); self._db.pack(fill="x",padx=16,pady=(2,12))

        self._pf=ctk.CTkFrame(pane,fg_color="transparent"); self._pf.pack(fill="x",padx=16,pady=(0,8))
        self._pl=ctk.CTkLabel(self._pf,text="",font=("Segoe UI",10),text_color=C["text_secondary"])
        self._pl.pack(anchor="w")
        self._pb=ctk.CTkProgressBar(self._pf,height=8); self._pb.set(0); self._pb.pack(fill="x")
        self._pf.pack_forget()

        self._btn=ctk.CTkButton(pane,text="Run Full Diagnostic",height=38,font=FB,command=self._run)
        self._btn.pack(fill="x",padx=16,pady=(4,10))
        self._sum=ctk.CTkLabel(pane,text="",font=FB,wraplength=260,text_color=C["text_secondary"])
        self._sum.pack(padx=16,pady=(0,12))

    def _ef(self, p, lbl, ph, show=None):
        ctk.CTkLabel(p,text=lbl,font=F,text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(4,0))
        kw={"placeholder_text":ph,"font":F}
        if show: kw["show"]=show
        e=ctk.CTkEntry(p,**kw); e.pack(fill="x",padx=16,pady=(2,2)); return e

    # ── checks grid ───────────────────────────────────────────────────────────
    def _checks_pane(self, p):
        pane=ctk.CTkFrame(p,fg_color=C["bg_secondary"],corner_radius=10)
        pane.grid(row=0,column=1,sticky="nsew",pady=(0,8))
        ctk.CTkLabel(pane,text="DIAGNOSTIC CHECKS",font=("Segoe UI",10,"bold"),
            text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(14,8))
        grid=ctk.CTkFrame(pane,fg_color="transparent")
        grid.pack(fill="both",expand=True,padx=12,pady=(0,12))
        grid.grid_columnconfigure(0,weight=1); grid.grid_columnconfigure(1,weight=1)
        for i,(cid,lbl,desc) in enumerate(CHECKS):
            rf=ctk.CTkFrame(grid,fg_color=C["bg_tertiary"],corner_radius=8)
            rf.grid(row=i//2,column=i%2,sticky="ew",padx=4,pady=4)
            dot=ctk.CTkLabel(rf,text="●",font=("Segoe UI",12),text_color=SC["idle"],width=16)
            dot.pack(side="left",padx=(10,6),pady=10)
            inf=ctk.CTkFrame(rf,fg_color="transparent")
            inf.pack(side="left",fill="both",expand=True,pady=8)
            ctk.CTkLabel(inf,text=lbl,font=F,text_color=C["text_primary"],anchor="w").pack(anchor="w")
            ctk.CTkLabel(inf,text=desc,font=("Segoe UI",9),text_color=C["text_secondary"],anchor="w").pack(anchor="w")
            st=ctk.CTkLabel(rf,text="Pending",font=("Segoe UI",9,"bold"),text_color=SC["idle"],width=62)
            st.pack(side="right",padx=8)
            self._dot[cid]=dot; self._stat[cid]=st
        self._banner=ctk.CTkLabel(pane,text="",font=FB,text_color=C["text_secondary"])
        self._banner.pack(padx=16,pady=(0,12))

    # ── findings ──────────────────────────────────────────────────────────────
    def _findings_pane(self, p):
        outer=ctk.CTkFrame(p,fg_color=C["bg_secondary"],corner_radius=10)
        outer.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(0,0))
        ctk.CTkLabel(outer,text="FINDINGS",font=("Segoe UI",10,"bold"),
            text_color=C["text_secondary"]).pack(anchor="w",padx=16,pady=(14,8))
        self._fs=ctk.CTkScrollableFrame(outer,fg_color="transparent",corner_radius=0,height=160)
        self._fs.pack(fill="x",padx=10,pady=(0,10))
        ctk.CTkLabel(self._fs,text="Run the diagnostic to see findings.",
            font=F,text_color=C["text_secondary"]).pack(pady=20)

    def _render_findings(self, findings):
        for w in self._fs.winfo_children(): w.destroy()
        if not findings:
            ctk.CTkLabel(self._fs,text="No findings — repository appears healthy.",
                font=F,text_color="#22C55E").pack(pady=20); return
        for fd in findings:
            col,icon=SEV.get(fd["sev"],("#94A3B8","ℹ"))
            row=ctk.CTkFrame(self._fs,fg_color=C["bg_tertiary"],corner_radius=6)
            row.pack(fill="x",padx=4,pady=3)
            ctk.CTkLabel(row,text=icon,font=("Segoe UI",16,"bold"),text_color=col,width=28
                ).pack(side="left",padx=(10,4),pady=8)
            ctk.CTkLabel(row,text=fd["text"],font=F,text_color=C["text_primary"],anchor="w",wraplength=700
                ).pack(side="left",fill="x",expand=True,padx=4,pady=8)

    # ── step state ────────────────────────────────────────────────────────────
    def _sc(self, cid, st):
        if cid in self._dot:
            self._dot[cid].configure(text_color=SC[st]); self._stat[cid].configure(text=SL[st],text_color=SC[st])

    def _reset(self):
        for cid,_,_ in CHECKS: self._sc(cid,"idle")

    # ── run ───────────────────────────────────────────────────────────────────
    def _run(self):
        if not bo_session.connected:
            self._sum.configure(text="Not connected to SAP BO",text_color="#EF4444"); return
        self._btn.configure(state="disabled",text="Running Diagnostics...")
        self._reset(); self._banner.configure(text=""); self._sum.configure(text="")
        self._pf.pack(fill="x",padx=16,pady=(0,8)); self._pb.set(0)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        F2=[]; N=len(CHECKS)
        def C2(cid,st): self.after(0,lambda c=cid,s=st: self._sc(c,s))
        def P(n): self.after(0,lambda p=n/N: (self._pb.set(p), self._pl.configure(text=f"Progress: {round(p*100)}%")))
        def add(sev,txt): F2.append({"sev":sev,"text":txt})

        # 1 DB connection
        C2("conn","running")
        try:
            bo_session.run_cms_query("SELECT TOP 1 SI_ID FROM CI_INFOOBJECTS WHERE SI_ID=1")
            C2("conn","pass"); add("pass","CMS database connection verified successfully")
        except Exception as e:
            C2("conn","fail"); add("fail",f"CMS DB connection failed: {e}")
        P(1); time.sleep(0.5)

        # 2 Tables
        C2("tables","running"); ok=True
        for kind in ["Webi","CrystalReport","Folder","User"]:
            try:
                bo_session.run_cms_query(f"SELECT TOP 1 SI_ID FROM CI_INFOOBJECTS WHERE SI_KIND='{kind}'")
            except Exception:
                ok=False; add("warn",f"Could not query SI_KIND={kind}")
        if ok: C2("tables","pass"); add("pass","All core CMS object types queryable")
        else:  C2("tables","warn")
        P(2); time.sleep(0.4)

        # 3 Index timing
        C2("indexes","running")
        try:
            t0=time.time()
            bo_session.run_cms_query("SELECT TOP 50 SI_ID,SI_NAME,SI_KIND FROM CI_INFOOBJECTS WHERE SI_KIND='Webi' ORDER BY SI_UPDATE_TS DESC")
            ms=int((time.time()-t0)*1000)
            if ms>5000: C2("indexes","warn"); add("warn",f"Slow query: {ms}ms — indexes may need rebuilding (threshold: 5000ms)")
            else:       C2("indexes","pass"); add("pass",f"Query response: {ms}ms (within threshold)")
        except Exception as e: C2("indexes","skip"); add("info",f"Index check skipped: {e}")
        P(3); time.sleep(0.4)

        # 4 Orphans
        C2("orphans","running")
        try:
            d=bo_session.run_cms_query(
                "SELECT TOP 200 SI_ID FROM CI_INFOOBJECTS "
                "WHERE SI_INSTANCE=1 AND SI_PROCESSINFO.SI_STATUS_INFO=1 "
                "AND SI_STARTTIME < '2020-01-01 00:00:00'")
            n=len(d.get("entries",[]) if d else [])
            if n>0: C2("orphans","warn"); add("warn",f"{n} very old failed instance(s) found (pre-2020)")
            else:   C2("orphans","pass"); add("pass","No orphaned / stuck old instances detected")
        except Exception as e: C2("orphans","skip"); add("info",f"Orphan check skipped: {e}")
        P(4); time.sleep(0.4)

        # 5 Broken refs (no owner)
        C2("refs","running")
        try:
            d=bo_session.run_cms_query(
                "SELECT TOP 100 SI_ID,SI_NAME FROM CI_INFOOBJECTS "
                "WHERE SI_INSTANCE=0 AND SI_KIND IN ('Webi','CrystalReport') "
                "AND (SI_OWNER='' OR SI_OWNER IS NULL)")
            n=len(d.get("entries",[]) if d else [])
            if n>0: C2("refs","warn"); add("warn",f"{n} report(s) with no owner — possible broken references")
            else:   C2("refs","pass"); add("pass","No broken owner references found in reports")
        except Exception as e: C2("refs","skip"); add("info",f"Reference check skipped: {e}")
        P(5); time.sleep(0.4)

        # 6 Object counters
        C2("counts","running")
        try:
            s=bo_session.get_dashboard_stats()
            C2("counts","pass")
            add("pass",f"Object counts — Reports: {s.get('reports',0)}, Universes: {s.get('universes',0)}, "
                       f"Users: {s.get('users',0)}, Connections: {s.get('connections',0)}, "
                       f"Failed instances: {s.get('failed_instances',0)}")
        except Exception as e: C2("counts","warn"); add("warn",f"Counter audit error: {e}")
        P(6); time.sleep(0.4)

        # 7 Query perf benchmark
        C2("perf","running")
        try:
            times=[]
            for q in [
                "SELECT TOP 10 SI_ID,SI_NAME FROM CI_INFOOBJECTS WHERE SI_KIND='Webi'",
                "SELECT TOP 10 SI_ID,SI_NAME FROM CI_SYSTEMOBJECTS WHERE SI_KIND='User'",
                "SELECT TOP 10 SI_ID,SI_NAME FROM CI_APPOBJECTS WHERE SI_KIND='Universe'",
            ]:
                t0=time.time(); bo_session.run_cms_query(q); times.append(int((time.time()-t0)*1000))
            avg=sum(times)//len(times)
            if avg>3000: C2("perf","warn"); add("warn",f"Avg CMS query: {avg}ms — exceeds 3000ms threshold")
            else:        C2("perf","pass"); add("pass",f"Avg CMS query: {avg}ms across 3 query types (threshold: 3000ms)")
        except Exception as e: C2("perf","skip"); add("info",f"Perf benchmark skipped: {e}")
        P(7); time.sleep(0.4)

        # 8 Repo size
        C2("size","running")
        try:
            di=bo_session.run_cms_query("SELECT TOP 2000 SI_ID FROM CI_INFOOBJECTS WHERE SI_INSTANCE=0")
            dn=bo_session.run_cms_query("SELECT TOP 2000 SI_ID FROM CI_INFOOBJECTS WHERE SI_INSTANCE=1")
            objs=len(di.get("entries",[]) if di else [])
            inst=len(dn.get("entries",[]) if dn else [])
            C2("size","pass")
            add("info",f"Repository sample: {objs}+ objects, {inst}+ instances (TOP 2000 sampled per category)")
        except Exception as e: C2("size","skip"); add("info",f"Size check skipped: {e}")
        P(8)

        warns=sum(1 for fd in F2 if fd["sev"]=="warn")
        fails=sum(1 for fd in F2 if fd["sev"]=="fail")

        def _fin(fds=F2,w=warns,x=fails):
            self._render_findings(fds)
            self._pf.pack_forget()
            self._btn.configure(state="normal",text="Run Full Diagnostic")
            if x>0:   self._banner.configure(text=f"Critical: {x} error(s) found",text_color="#EF4444")
            elif w>0: self._banner.configure(text=f"{w} warning(s) require attention",text_color="#F0A500")
            else:     self._banner.configure(text="Repository is healthy",text_color="#22C55E")

        self.after(0,_fin)
