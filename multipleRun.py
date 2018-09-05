from FuseRDB import FuseRDB
import gc

nr_runs=30
latent_factors=[5,10,15,20,25,30,35,40]
#for l in latent_factors:
for i in range(nr_runs):
    fuse = FuseRDB(database_connection='postgresql://postgres:geslo123@127.0.0.1/avtomobilizem2',alternative_matrices_limit=1,multiple_models_relation_reconstruction='avg',output_file_path='avtomobilizem_run_'+str(i)+'_latent-'+'default'+'.txt',object_sampling_dialog=False) #,latent_factor=l
    gc.collect()
    fuse = FuseRDB(database_connection='postgresql://postgres:geslo123@127.0.0.1/mini_parameciumdb', alternative_matrices_limit=1, object_types_limit=12,output_file_path='mini_parameciumDB_run_latent-'+'default'+'.txt',multiple_models_relation_reconstruction='avg',object_sampling_dialog=False) #,latent_factor=l
    gc.collect()
    fuse = FuseRDB(database_connection='postgresql://postgres:geslo123@127.0.0.1/pagila',
                   alternative_matrices_limit=1,output_file_path='pagila_run_'+str(i)+'_latent-'+"default"+'.txt',multiple_models_relation_reconstruction='avg',object_sampling_dialog=False) #,latent_factor=l
    gc.collect()