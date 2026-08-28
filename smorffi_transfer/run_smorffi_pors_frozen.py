#!/usr/bin/env python3
"""Frozen SMoRFFI measured-RF transfer experiment for PORS/S-PORS.

Target devices 101--123 are not accessed until all selection decisions are frozen.
The script intentionally separates development preparation from final unsealing.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
import argparse, hashlib, itertools, json, math, time
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

KNOWN = list(range(1,101))
TARGET_UNKNOWN = list(range(101,124))
SKEYS = ["S1","S2","S3","S4","S5","S6"]
DISPLAY = {"S1":"S1","S2":"S2","S3":"S3","S4":"S4","S5":"S5","S6":"FullM"}
SUBSETS = [c for r in range(1,7) for c in itertools.combinations(SKEYS,r)]
SPORS_SEEDS = [2026082801, 2026082903, 2026083007, 2026083109, 2026090113]
FEATURES = [
    "CFO","short_freq","long_freq","frac_dimension_1","frac_dimension_2",
    "iqi_1","iqi_2","mag_error_mean_1","mag_error_var_1",
    "mag_error_mean_2","mag_error_var_2","phase_error_mean_1",
    "phase_error_var_1","phase_error_mean_2","phase_error_var_2",
]

def sha256_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def sname(ss): return "+".join(DISPLAY[k] for k in ss)

def ecdf_apply(ref,x):
    ref=np.sort(np.asarray(ref,float)); x=np.asarray(x,float)
    return np.searchsorted(ref,x,side="right")/max(len(ref),1)

def tnr_at_tpr95_unknown(y_unknown,score):
    fpr,tpr,_=roc_curve(np.asarray(y_unknown,int),np.asarray(score,float),pos_label=1)
    ii=np.flatnonzero(tpr>=.95)
    return float(np.max(1-fpr[ii])) if len(ii) else 0.0

def oscr_score(true_known,pred_known,score_known,score_unknown):
    k=np.asarray(score_known,float); u=np.asarray(score_unknown,float)
    correct=np.asarray(true_known)==np.asarray(pred_known)
    vals=np.r_[k,u]
    if len(np.unique(vals))<=5000:
        th=np.r_[np.inf,np.sort(np.unique(vals))[::-1],-np.inf]
    else:
        th=np.r_[np.inf,np.unique(np.quantile(vals,np.linspace(1,0,4001))),-np.inf]
    fpr=[]; ccr=[]
    for t in th:
        fpr.append(np.mean(u<t)); ccr.append(np.mean(correct & (k<t)))
    fpr=np.asarray(fpr); ccr=np.asarray(ccr); order=np.argsort(fpr)
    return float(np.trapezoid(ccr[order],fpr[order]))

def method_metrics(y_unknown,score,known_true,known_pred,n_known):
    return {
        "AUROC":float(roc_auc_score(y_unknown,score)),
        "TNR@TPR95_unknown":tnr_at_tpr95_unknown(y_unknown,score),
        "OSCR":oscr_score(known_true,known_pred,score[:n_known],score[n_known:]),
    }

def load_and_clean(path:Path, allow_target=False):
    use=["Device Number"]+FEATURES
    df=pd.read_csv(path,usecols=lambda c:c in set(use),low_memory=False)
    missing=[c for c in use if c not in df.columns]
    if missing: raise ValueError(f"Missing required columns: {missing}")
    for c in use: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.dropna(subset=use).copy()
    df["Device Number"]=df["Device Number"].astype(int)
    df=df[df["Device Number"].between(1,123)].copy()
    if not allow_target:
        df=df[df["Device Number"].isin(KNOWN)].copy()
    return df.reset_index(drop=True)

def by_device_arrays(df):
    out={}
    for d,g in df.groupby("Device Number",sort=True):
        out[int(d)]=g.reset_index(drop=True)
    return out

def split_bounds(n):
    a=int(math.floor(.60*n)); b=int(math.floor(.70*n)); c=int(math.floor(.80*n))
    if a<20 or b<=a or c<=b or n<=c: raise ValueError(f"Too few valid rows for n={n}")
    return a,b,c

def stack(devmap, devices, lo_frac_label, hi_frac_label):
    X=[]; y=[]
    for d in devices:
        g=devmap[d]; n=len(g); a,b,c=split_bounds(n)
        if (lo_frac_label,hi_frac_label)==("0","60"): q=g.iloc[:a]
        elif (lo_frac_label,hi_frac_label)==("60","70"): q=g.iloc[a:b]
        elif (lo_frac_label,hi_frac_label)==("70","80"): q=g.iloc[b:c]
        elif (lo_frac_label,hi_frac_label)==("0","70"): q=g.iloc[:b]
        elif (lo_frac_label,hi_frac_label)==("80","100"): q=g.iloc[c:]
        elif (lo_frac_label,hi_frac_label)==("0","100"): q=g
        else: raise ValueError((lo_frac_label,hi_frac_label))
        X.append(q[FEATURES].to_numpy(float)); y.extend([d]*len(q))
    return np.vstack(X),np.asarray(y,int)

def score_block(Xtr,ytr,Xcal,ycal,Xev,seed):
    classes=np.array(sorted(np.unique(ytr))); cmap={d:i for i,d in enumerate(classes)}
    yi=np.array([cmap[int(v)] for v in ytr],int); yci=np.array([cmap[int(v)] for v in ycal],int)
    scaler=StandardScaler().fit(Xtr); Ztr=scaler.transform(Xtr); Zca=scaler.transform(Xcal); Zev=scaler.transform(Xev)
    rf=RandomForestClassifier(n_estimators=30,max_depth=12,min_samples_leaf=20,max_features=min(5,Ztr.shape[1]),random_state=seed,n_jobs=-1).fit(Ztr,yi)
    def base(Z):
        p=rf.predict_proba(Z); pred=p.argmax(1); sp=np.sort(p,axis=1)
        return pred,1-p[np.arange(len(p)),pred],1-(sp[:,-1]-sp[:,-2])
    pca,s1ca,s2ca=base(Zca); pev,s1ev,s2ev=base(Zev)
    means=[]; vars_=[]; prec=[]; nns=[]
    for i in range(len(classes)):
        z=Ztr[yi==i]; means.append(z.mean(0)); vars_.append(z.var(0,ddof=1)+1e-6)
        prec.append(LedoitWolf().fit(z).precision_)
        nns.append(NearestNeighbors(n_neighbors=min(7,len(z)),n_jobs=1).fit(z))
    means=np.asarray(means); vars_=np.asarray(vars_); prec=np.asarray(prec)
    def geom(Z,pred):
        out=[np.empty(len(Z)) for _ in range(4)]
        for i in range(len(classes)):
            ids=np.flatnonzero(pred==i)
            if not len(ids): continue
            z=Z[ids]; d=z-means[i]
            out[0][ids]=np.sqrt(np.sum(d*d,axis=1)); out[1][ids]=np.sqrt(np.sum(d*d/vars_[i],axis=1))
            dist=nns[i].kneighbors(z,n_neighbors=min(7,nns[i].n_samples_fit_),return_distance=True)[0]; out[2][ids]=dist.mean(1)
            out[3][ids]=np.sqrt(np.einsum('ij,jk,ik->i',d,prec[i],d))
        return out
    s3ca,s4ca,s5ca,s6ca=geom(Zca,pca); s3ev,s4ev,s5ev,s6ev=geom(Zev,pev)
    sca={"S1":s1ca,"S2":s2ca,"S3":s3ca,"S4":s4ca,"S5":s5ca,"S6":s6ca}
    sev={"S1":s1ev,"S2":s2ev,"S3":s3ev,"S4":s4ev,"S5":s5ev,"S6":s6ev}
    correct=pca==yci
    refs={k:(np.asarray(v)[correct] if correct.sum()>=20 else np.asarray(v)) for k,v in sca.items()}
    ranks=np.vstack([ecdf_apply(refs[k],sev[k]) for k in SKEYS]).T
    return ranks,sev,pev,classes,cmap

def make_folds(known,seed):
    rng=np.random.default_rng(seed); sh=rng.permutation(np.asarray(known,int))
    return [list(map(int,b)) for b in np.array_split(sh,4)]

def inner_fold(devmap,pseudo,seed):
    active=sorted(set(KNOWN)-set(pseudo))
    Xtr,ytr=stack(devmap,active,"0","60"); Xca,yca=stack(devmap,active,"60","70")
    Xk,yk=stack(devmap,active,"70","80"); Xu,yu=stack(devmap,pseudo,"70","80")
    Xev=np.vstack([Xk,Xu]); ranks,_,_,_,_=score_block(Xtr,ytr,Xca,yca,Xev,seed)
    yunk=np.r_[np.zeros(len(Xk),int),np.ones(len(Xu),int)]
    vals={}
    for ss in SUBSETS:
        cols=[SKEYS.index(k) for k in ss]; vals[sname(ss)]=float(roc_auc_score(yunk,ranks[:,cols].mean(1)))
    return vals

def select_maximin(folds):
    rows=[]
    for nm in folds[0]:
        a=np.array([f[nm] for f in folds],float)
        rows.append((nm,float(a.min()),float(a.mean()),nm.count('+')+1))
    rows.sort(key=lambda z:(-z[1],-z[2],z[3],z[0]))
    return rows[0],rows

def select_without_target(devmap):
    selections=[]; inner_rows=[]
    for ri,seed in enumerate(SPORS_SEEDS,1):
        blocks=make_folds(KNOWN,seed)
        folds=[]
        for fi,pseudo in enumerate(blocks,1):
            vals=inner_fold(devmap,pseudo,seed+fi*101)
            folds.append(vals)
            inner_rows.extend({"repeat":ri,"partition_seed":seed,"fold":fi,"subset":nm,"pseudo_AUROC":v} for nm,v in vals.items())
        sel,_=select_maximin(folds); selections.append(sel[0])
    pors=selections[0]
    counts=Counter(selections); modal,modal_count=counts.most_common(1)[0]
    if modal_count>=3: spors=modal; abstain=False
    else: spors="S4+S5"; abstain=True
    return {"pors_subset":pors,"spors_votes":selections,"spors_modal_subset":modal,"spors_modal_count":modal_count,
            "spors_subset":spors,"spors_abstain":abstain},pd.DataFrame(inner_rows)

def final_unseal(path:Path, decisions, outdir:Path):
    full=load_and_clean(path,allow_target=True); devmap=by_device_arrays(full)
    missing=[d for d in range(1,124) if d not in devmap]
    if missing: raise ValueError(f"Missing device IDs after cleaning: {missing}")
    Xtr,ytr=stack(devmap,KNOWN,"0","70"); Xca,yca=stack(devmap,KNOWN,"70","80"); Xte,yte=stack(devmap,KNOWN,"80","100")
    Xu,yu=stack(devmap,TARGET_UNKNOWN,"0","100")
    Xev=np.vstack([Xte,Xu]); ranks,sev,pred,classes,cmap=score_block(Xtr,ytr,Xca,yca,Xev,2026090201)
    nknown=len(Xte); yunk=np.r_[np.zeros(nknown,int),np.ones(len(Xu),int)]
    true_known=np.array([cmap[int(v)] for v in yte],int)
    subset_metrics={}
    for ss in SUBSETS:
        nm=sname(ss); cols=[SKEYS.index(k) for k in ss]; score=ranks[:,cols].mean(1)
        subset_metrics[nm]=method_metrics(yunk,score,true_known,pred[:nknown],nknown)
    oracle=min(subset_metrics.items(),key=lambda kv:(-kv[1]["AUROC"],kv[0].count('+')+1,kv[0]))
    def met(nm): return subset_metrics[nm]
    pors=decisions["pors_subset"]; spors=decisions["spors_subset"]
    counts={str(d):int(len(devmap[d])) for d in range(1,124)}
    summary={
      "dataset":"SMoRFFI measured RF transfer (not radar)","input_sha256":sha256_file(path),
      "n_devices_total":123,"known_devices":"1-100","target_unknown_devices":"101-123",
      "feature_dim":len(FEATURES),"retained_rows_total":int(sum(counts.values())),"retained_rows_by_device":counts,
      "known_class_accuracy":float(np.mean(pred[:nknown]==true_known)),
      "pors_subset":pors,"pors_AUROC":met(pors)["AUROC"],"pors_TNR@TPR95_unknown":met(pors)["TNR@TPR95_unknown"],"pors_OSCR":met(pors)["OSCR"],
      "oracle_subset":oracle[0],"oracle_AUROC":oracle[1]["AUROC"],"pors_oracle_regret":oracle[1]["AUROC"]-met(pors)["AUROC"],
      "spors_votes":decisions["spors_votes"],"spors_modal_subset":decisions["spors_modal_subset"],"spors_modal_count":decisions["spors_modal_count"],
      "spors_subset":spors,"spors_abstain":bool(decisions["spors_abstain"]),"spors_abstention_frequency":"1/1" if decisions["spors_abstain"] else "0/1",
      "spors_AUROC":met(spors)["AUROC"],"spors_TNR@TPR95_unknown":met(spors)["TNR@TPR95_unknown"],"spors_OSCR":met(spors)["OSCR"],
      "rank45_AUROC":met("S4+S5")["AUROC"],"fullM_AUROC":met("FullM")["AUROC"],"s4_AUROC":met("S4")["AUROC"],"s5_AUROC":met("S5")["AUROC"],
      "all6_AUROC":met("S1+S2+S3+S4+S5+FullM")["AUROC"],
    }
    pd.DataFrame([{"subset":k,**v} for k,v in subset_metrics.items()]).to_csv(outdir/"smorffi_outer_all63.csv",index=False)
    json.dump(summary,open(outdir/"smorffi_summary.json","w"),indent=2)
    pd.DataFrame([summary | {"retained_rows_by_device":json.dumps(counts),"spors_votes":json.dumps(summary["spors_votes"])}]).to_csv(outdir/"smorffi_summary.csv",index=False)
    return summary

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("csv",type=Path); ap.add_argument("--outdir",type=Path,default=Path("smorffi_pors_results")); args=ap.parse_args()
    args.outdir.mkdir(parents=True,exist_ok=True)
    known_df=load_and_clean(args.csv,allow_target=False); devmap=by_device_arrays(known_df)
    if sorted(devmap)!=KNOWN: raise ValueError(f"Known-only load did not contain exactly devices 1..100; got {sorted(devmap)}")
    counts=pd.Series({d:len(devmap[d]) for d in KNOWN},name="valid_rows"); counts.to_csv(args.outdir/"known_valid_rows_before_selection.csv")
    t=time.time(); decisions,inner=select_without_target(devmap)
    dec_path=args.outdir/"selection_frozen_before_target_unseal.json"
    json.dump(decisions,open(dec_path,"w"),indent=2)
    inner.to_csv(args.outdir/"smorffi_inner_pseudoopen.csv",index=False)
    print("SELECTION FROZEN BEFORE TARGET UNSEAL:",json.dumps(decisions),flush=True)
    print("SELECTION_SHA256:",sha256_file(dec_path),flush=True)
    summary=final_unseal(args.csv,decisions,args.outdir)
    print(json.dumps(summary,indent=2)); print(f"elapsed_s={time.time()-t:.1f}")

if __name__=="__main__": main()
