#!/usr/bin/env python3
# Post-unseal evaluation-only uncertainty analysis. No selector/hyperparameter changes.
from pathlib import Path
import sys,json
import numpy as np
from sklearn.metrics import roc_auc_score
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_smorffi_pors_frozen as fr

PORS='S1+S5+FullM'
BASES={'PORS':PORS,'RankMean45':'S4+S5','S5':'S5','All6':'S1+S2+S3+S4+S5+FullM'}

def cols(nm):
    inv={'S1':'S1','S2':'S2','S3':'S3','S4':'S4','S5':'S5','FullM':'S6'}
    return [fr.SKEYS.index(inv[x]) for x in nm.split('+')]

def pair_auc_matrix(scores, known_dev, unknown_dev):
    K=np.unique(known_dev); U=np.unique(unknown_dev); M=np.empty((len(U),len(K)))
    sknown=scores[:len(known_dev)]; sunknown=scores[len(known_dev):]
    for i,u in enumerate(U):
        su=sunknown[unknown_dev==u]
        for j,k in enumerate(K):
            sk=sknown[known_dev==k]; tot=0.0; n=0
            for q in np.array_split(su,max(1,int(np.ceil(len(su)/500)))):
                d=q[:,None]-sk[None,:]; tot+=(d>0).sum()+0.5*(d==0).sum(); n+=d.size
            M[i,j]=tot/n
    return K,U,M

def main(csv,outdir):
    csv=Path(csv);outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    full=fr.load_and_clean(csv,allow_target=True);dm=fr.by_device_arrays(full)
    Xtr,ytr=fr.stack(dm,fr.KNOWN,'0','70');Xca,yca=fr.stack(dm,fr.KNOWN,'70','80');Xte,yte=fr.stack(dm,fr.KNOWN,'80','100');Xu,yu=fr.stack(dm,fr.TARGET_UNKNOWN,'0','100')
    Xev=np.vstack([Xte,Xu]);ranks,sev,pred,classes,cmap=fr.score_block(Xtr,ytr,Xca,yca,Xev,2026090201)
    kd=[];ud=[]
    for d in fr.KNOWN:
        n=len(dm[d]);a,b,c=fr.split_bounds(n);kd.extend([d]*(n-c))
    for d in fr.TARGET_UNKNOWN:ud.extend([d]*len(dm[d]))
    kd=np.asarray(kd);ud=np.asarray(ud);y=np.r_[np.zeros(len(kd)),np.ones(len(ud))]
    score={nm:ranks[:,cols(sub)].mean(1) for nm,sub in BASES.items()};observed={nm:roc_auc_score(y,s) for nm,s in score.items()}
    mats={}
    for nm,s in score.items():K,U,M=pair_auc_matrix(s,kd,ud);mats[nm]=M
    rng=np.random.default_rng(202608280951);B=20000;bk=rng.integers(0,len(K),(B,len(K)));bu=rng.integers(0,len(U),(B,len(U)));boots={nm:np.empty(B) for nm in score}
    for ii in range(B):
        for nm,M in mats.items():boots[nm][ii]=M[np.ix_(bu[ii],bk[ii])].mean()
    res={'resampling_unit':'physical device','B':B,'n_known_devices':len(K),'n_unknown_devices':len(U),'observed_AUROC':observed,'CI95_AUROC':{nm:np.quantile(v,[.025,.975]).tolist() for nm,v in boots.items()},'differences':{}}
    for base in ['RankMean45','S5','All6']:
        d=boots['PORS']-boots[base];res['differences'][f'PORS_minus_{base}']={'observed':observed['PORS']-observed[base],'CI95':np.quantile(d,[.025,.975]).tolist(),'Pr_le_0':float(np.mean(d<=0))}
    true=np.array([cmap[int(v)] for v in yte]);corr=(pred[:len(kd)]==true).astype(float);devacc=np.array([corr[kd==d].mean() for d in K]);bacc=devacc[bk].mean(1)
    res['known_accuracy']={'observed':float(corr.mean()),'device_cluster_CI95':np.quantile(bacc,[.025,.975]).tolist()}
    json.dump(res,open(outdir/'smorffi_device_cluster_bootstrap.json','w'),indent=2);print(json.dumps(res,indent=2))
if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--outdir',default='smorffi_bootstrap_results');a=ap.parse_args();main(a.csv,a.outdir)
