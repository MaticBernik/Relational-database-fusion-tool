#from os import listdir
#from os.path import isfile, join
import os
import pandas
from datetime import datetime,timedelta


latent_factors=[5,10,15,20,25,30,35,40]
databases=['avtomobilizem','parameciumDB','pagila']

directory='./'
#onlyfiles = [f for f in listdir(directory) if isfile(join(directory, f))]
#print(onlyfiles)

dataframe_structure={'database_name':[],'latent_factor':[],'object_type1_name':[],'object_type2_name':[],'relation_name':[],'ranking_place':[],'rmse':[],'duration_seconds':[]}
for file in os.listdir(directory):
    filename=os.fsdecode(file)
    if filename.endswith('.txt'):
        database_name = filename[:filename.index('_')]
        latent_factor = filename[filename.index('latent-')+7:filename.index('.txt')]
        file_content=open(file,'r')
        list_section=False
        for line in file_content:
            if line.startswith('===== Postopek je trajal:	'):
                duration=line[line.index('===== Postopek je trajal:	')+len('===== Postopek je trajal:	'):]
                datetime_object = datetime.strptime(duration, '%H:%M:%S.%f')
                timedelta_object=timedelta(hours=datetime_object.hour, minutes=datetime_object.minute, seconds=datetime_object.second )
                duration = timedelta_object.total_seconds()
                for i in range(place-1):
                    dataframe_structure['duration_seconds'].append(duration)
                break

            if line.startswith('RANGIRAN SEZNAM RELACIJ:'):
                list_section=True
                place=1
                continue
            if not list_section:
                continue
            if not line.strip():
                list_section=False
                continue
                #break
            ot1=line[line.index('(\'')+2 : line.index('\', ')]
            ot2=line[line.index(', \'')+3 : line.index('\') ')]
            relation_name=ot1+','+ot2
            rmse=line[line.index('RMSE: ')+6:]
            if '--' in rmse:
                rmse=None
            else:
                rmse=float(rmse)

            dataframe_structure['database_name'].append(database_name)
            dataframe_structure['latent_factor'].append(latent_factor)
            dataframe_structure['object_type1_name'].append(ot1)
            dataframe_structure['object_type2_name'].append(ot2)
            dataframe_structure['relation_name'].append(relation_name)
            dataframe_structure['ranking_place'].append(place)
            dataframe_structure['rmse'].append(rmse)
            place+=1
        file_content.close()
df=pandas.DataFrame.from_dict(dataframe_structure)
df.to_csv('multiple_run_data.csv')