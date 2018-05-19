import os
import pandas as pd

dir='logs/'
column_ime_baze=[]
column_presampling_mode=[]
column_dummy_var_treshold=[]
column_latent_factor=[]
column_run_nr=[]
column_ime_relacije=[]
column_ime_relacije_ObjektniTip1=[]
column_ime_relacije_ObjektniTip2=[]
column_rmse=[]
for filename in os.listdir(dir):
    if filename.endswith(".log"):
        tmp=filename.split('_')
        ime_baze=tmp[0]
        presampling_mode=bool(tmp[1])
        dummy_var_treshold=int(tmp[2])
        latent_factor=int(tmp[3])
        run_nr=int(tmp[4][tmp[4].index('run')+len('run'):tmp[4].index('.')])
        log_File=open(dir+filename,'r')
        rankings=False
        for line in log_File:
            if 'RANGIRAN SEZNAM RELACIJ:' in line:
                rankings=True
                continue
            if not rankings or not line.strip():
                continue
            if rankings and '=====' in line:
                break

            tmp=line.split('. ')[1].split('\t')
            ime_relacije=tmp[0]
            rmse=float(tmp[1][tmp[1].index('(')+1:tmp[1].index(')')])

            column_ime_baze.append(ime_baze)
            column_presampling_mode.append(presampling_mode)
            column_dummy_var_treshold.append(dummy_var_treshold)
            column_latent_factor.append(latent_factor)
            column_run_nr.append(run_nr)

            column_ime_relacije.append(ime_relacije)
            column_ime_relacije_ObjektniTip1.append(ime_relacije.split(' ')[0])
            column_ime_relacije_ObjektniTip2.append(ime_relacije.split(' ')[1])
            column_rmse.append(rmse)
    else:
        continue

d={'Ime podatkovne baze':column_ime_baze, 'Vzorcenje':column_presampling_mode, 'Dummy variable treshold':column_dummy_var_treshold, 'Latentni faktor':column_latent_factor, 'St. ponovitve':column_run_nr, 'Ime relacije':column_ime_relacije, 'Objektni tip 1':column_ime_relacije_ObjektniTip1, 'Objektni tip 2':column_ime_relacije_ObjektniTip2, 'RMSE':column_rmse}
df=pd.DataFrame(data=d)
df.to_csv(ime_baze+'_runs.csv', encoding='utf-8')