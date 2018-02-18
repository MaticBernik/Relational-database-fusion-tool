#!/usr/bin/python
# -*- coding: utf-8 -*-

import urllib3
import requests
import json
import psycopg2
import sys
#from intermine.webservice import Service
import numpy as np
from collections import Counter
import itertools
from skfusion import fusion
from pathlib import Path
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
import random
import psutil
from eralchemy import render_er #https://github.com/Alexis-benoist/eralchemy
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from scipy.spatial import distance as distance_library
from datetime import datetime






class Fuse():
    '''
    1.Popisi vse tabele
        popisi vse "vmesne tabele" (z >=2 tujima kljucema)
        popisi podatkovne tipe za vsak stolpec znotraj "vmesnih tabel"
    2.sestavi vse mozne relacijske matrike
            za vsako "vmesno tabelo"
                za vsak mozen par tujih kljucev znotraj "vmesne tabele":
                    za vsak stolpec znotraj "vmesne tabele", ki:
                        vsebuje numericne vrednosti
                        vsebuje boolean vrednosti
                        vsebuje vrednosti, ki se jih da prevesti na numericne (koncen nabor vrednosti)
                        ni oznacen kot tuji kljuc
                    zgradi ustrezno relacijsko matriko
    3.sestavi vse mozne matrike relacijskih matrik (in matrike omejitvenih matrik)
    4.scikit-fusion
    '''

    def connect_to_postgreSQL(self,host,database,user,password):
        '''
        Tries to establish a connection to (postgreSQL) database, specified by address of host machine, database name and user credentials.
        If connection fails program terminates.
        '''
        print("***Povezovanje na podatkovno bazo...")
        try:
            #con = psycopg2.connect(host='192.168.2.101', database='parameciumdb', user='postgres', password='geslo123')
            self.con = psycopg2.connect(host=host, database=database, user=user, password=password)
            self.cursor = self.con.cursor()
        except psycopg2.DatabaseError as e:
            print('Error %s' % e)
            sys.exit(1)

    def estimate_complexity(self):
        '''
        Estimates complexity of a given task.
        Sum of dimensions of all tables within a database is used as a metric.
        :return: Integer value between 1 and 5.
        1 meaning problem is trivial and 5 indicating extreme complexity.
        '''
        print("***Ocenjevanje zahtevnosti problema...")
        complex_sum=0
        for table in self.tables:
            self.cursor.execute("SELECT count(*) FROM "+table[1]+";")
            nr_rows=self.cursor.fetchall()[0][0]
            self.cursor.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='"+table[1]+"';")
            nr_columns=self.cursor.fetchall()[0][0]
            complex_sum+=nr_columns*nr_rows

        print("\t#COMPLEX: ",complex_sum)
        #later implement tresholding based on system resources?
        if complex_sum<1000:
            return 1
        elif complex_sum<10000:
            return 2
        elif complex_sum<1000000:
            return 3
        elif complex_sum<100000000:
            return 4
        else:
            return 5

    def estimate_relation_matrix_dimension_constraint(self):
        '''
        Based on system resurces (specifically available mamory) proposes upper limit of objects per relation,
        to constraint size of relation matrices.
        :return: Proposed limit for number of objects (integer).
        '''
        print("***Ocenjujem primerno omejitev dimenzij relacijskih matrik")
        svmem=psutil.virtual_memory()
        print("\t#",svmem)
        return 20

    def restore_from_checkpoint(self,host,database):
        '''
            Load data from existing checkpoint file for specified database connection,
            or create new (empty) checkpoint file.
        :param host:
        :param database:
        :return:
        '''
        print("***Nalagam shranjene podatke iz datoteke...")
        checkpoint_file_path=".checkpoint_"+host+"_"+database+".txt"
        self.checkpoint_file=open(checkpoint_file_path,'a+')
        self.checkpoint_file.seek(0,0)

        foreign_key_section=False
        primary_key_section = False
        excluded_tables_section=False
        modified_tables_section=False
        tables_section=False
        relation_matrices_section=False
        constraint_matrices_section=False
        object_types_section = False
        sample_section=False

        for line in self.checkpoint_file:
            if line in ['\n', '\r\n']:
                print("\t..konec")
                foreign_key_section=False
                primary_key_section = False
                excluded_tables_section=False
                modified_tables_section=False
                tables_section=False
                relation_matrices_section = False
                constraint_matrices_section = False
                object_types_section = False
                sample_section=False
                continue
            elif "#FOREIGN KEYS" in line:
                print("\t#Nalagam seznam tujih kljucev..")
                self.foreign_keys=[]
                foreign_key_section=True
                continue
            elif "#PRIMARY KEYS" in line:
                print("\t#Nalagam seznam primarnih kljucev..")
                self.primary_keys=[]
                primary_key_section=True
                continue
            elif "#EXCLUDED TABLES LIST" in line:
                print("\t#Nalagam seznam izlocenih tabel..")
                self.excluded_tables=[]
                excluded_tables_section=True
                continue
            elif "#MODIFIED TABLES LIST" in line:
                print("\t#Nalagam seznam modificiranih tabel..")
                self.modified_tables={}
                modified_tables_section=True
                key_next=True
                continue
            elif "#TABLES" in line:
                print("\t#Nalagam seznam tabel...")
                self.tables=[]
                tables_section=True
                continue
            elif "#RELATION MATRICES" in line:
                print("\t#Nalagam seznam relacijskih matrik...")
                self.relation_matrices={}
                relation_matrices_section = True
                key_next=True
                continue
            elif "#CONSTRAINT MATRICES" in line:
                print("\t#Nalagam seznam omejitvenih matrik...")
                self.constraint_matrices={}
                constraint_matrices_section = True
                key_next=True
                continue
            elif "#OBJECT TYPES" in line:
                print("\t#Nalagam seznam objektnih tipov...")
                self.object_types=[]
                object_types_section=True
                continue
            elif "#SAMPLE" in line:
                print("\t#Nalagam vzorec podatkov...")
                self.sample={}
                self.sample_tables=set()
                sample_section = True
                key_next=True
                header_next=False
                continue


            if line[len(line)-1]=="\n":
                line=line[:-1]

            if foreign_key_section:
                self.foreign_keys.append(line.split('\t'))
            if primary_key_section:
                self.primary_keys.append(line.split("\t"))
            elif excluded_tables_section:
                self.excluded_tables.append(line)
            elif modified_tables_section:
                if line=='!':
                    key_next=True
                    if key_name and len(data)>0:
                        self.modified_tables[key_name]=data
                elif key_next:
                    key_name=line
                    data=[]
                    key_next=False
                else:
                    data.append(line.split("\t"))
            elif tables_section:
                tabela=line.split("\t")
                for i in range(len(tabela)):
                    if tabela[i]=="None":
                        tabela[i]=None
                self.tables.append(tabela)
            elif relation_matrices_section:
                if line=='!!':
                    key_next=True
                    if key_name and len(data)>0:
                        if key_name not in  self.relation_matrices:
                            self.relation_matrices[key_name]=[]
                        self.relation_matrices[key_name].append(np.array(data))
                elif line=='!':
                    if key_name and len(data)>0:
                        if key_name not in  self.relation_matrices:
                            self.relation_matrices[key_name]=[]
                        self.relation_matrices[key_name].append(np.array(data))
                    data=[]
                elif key_next:
                    key_name=line
                    data=[]
                    key_next=False
                else:
                    data.append([np.nan if x=='nan' else float(x) for x in line.split("\t")])
            elif constraint_matrices_section:
                if line=='!!':
                    key_next=True
                    if key_name and len(data)>0:
                        if key_name not in self.constraint_matrices:
                            self.constraint_matrices[key_name]=[]
                        self.constraint_matrices[key_name].append(np.array(data))
                elif line=='!':
                    if key_name and len(data)>0:
                        if key_name not in self.constraint_matrices:
                            self.constraint_matrices[key_name]=[]
                        self.constraint_matrices[key_name].append(np.array(data))
                    data=[]
                elif key_next:
                    key_name=line
                    data=[]
                    key_next=False
                else:
                    data.append([np.nan if x=='nan' else float(x) for x in line.split("\t")])
            elif object_types_section:
                #self.object_types.append(line.split("\t"))
                self.object_types.append(line)
            elif sample_section:
                if line=='!':
                    key_next=True
                    if key_name and len(data)>0:
                        if key_name not in self.sample:
                            self.sample[key_name]=[[],set()]
                        set_to_add=self.sample[key_name][1]
                        self.sample[key_name][1].update(tuple(data))
                elif key_next:
                    key_name=line
                    self.sample_tables.add(key_name)
                    data=[]
                    key_next=False
                    header_next=True
                    if key_name not in self.sample:
                        self.sample[key_name] = [[], set()]
                else:
                    if header_next:
                        self.sample[key_name][0]+=line.split('\t')
                        data_types_postgres=[self.column_data_type[key_name+' '+x][1] for x in self.sample[key_name][0]]
                        #print("DATA TYPES POSTGRES",data_types_postgres)
                        data_types_python=[self.postgres_to_python_data_types[x.upper()] if x.upper() in self.postgres_to_python_data_types else 'str' for x in data_types_postgres]
                        #print("DATA TYPES PYTHON",data_types_python)
                        header_next=False
                    else:
                        new_data=line.split("\t")
                        new_data_parsed=[]
                        for x in range(len(new_data)):
                            if data_types_python[x]=='str':
                                #nepotrebno
                                new_data_parsed.append(str(new_data[x]))
                            elif data_types_python[x]=='integer':
                                new_data_parsed.append(int(new_data[x]))
                            elif data_types_python[x] == 'float':
                                new_data_parsed.append(float(new_data[x]))
                            else:
                                print("\t\t\t! Nepodprt podatkovni tip")

                        data.append(tuple(new_data_parsed))

        self.checkpoint_file.seek(0, 2)

        '''print("FOREIGN KEYS: ",self.foreign_keys)
        print("EXCLUDED TABLES: ",self.excluded_tables)
        #print("MODIFIED TABLES: ",self.modified_tables)
        print("TABLES: ",self.tables)
        print("RELATION MATRICES: ",self.relation_matrices)
        print("CONSTRAINT MATRICES: ",self.constraint_matrices)'''


    def select_denser_matrices(self,matrices_list):
        '''
        Returns sublist of given matrices_list, of length equal to user-set parameter self.max_number_of_alternative_relation_matrices_to_use.
        Prefers matrices with higher percentage of non-zero elements.
        :param matrices_list:
        :return:
        '''
        scores=[]
        for matrix in matrices_list:
            matrix=np.array(matrix)
            scores.append(np.count_nonzero(matrix)/(matrix.shape[0]*matrix.shape[1])) #Nonzero ni korektno - 0 je tudi lahko vrednost
        chosen_matrices_indices=np.argsort(scores)[::-1][:self.max_number_of_alternative_relation_matrices_to_use]
        return [matrices_list[i] for i in chosen_matrices_indices]

    def limit_relation_matrices_number(self,relation_matrices=None):
        '''
        Check if number of relation matrices describing any relation between pairs of object types exceeds the limit set by user.
        If the limit is not respected, select subset of matrices using different heuristics (size, density..)
        '''
        if relation_matrices is None:
            relation_matrices=self.relation_matrices
        print("***Preverjam stevilo alternativnih relacijskih matrik za relacije..")
        for relation in relation_matrices:
            if len(relation_matrices[relation])>self.max_number_of_alternative_relation_matrices_to_use:
                print("\tRelacija "+str(relation)+" ima "+str(len(relation_matrices[relation]))+" kar je vec kot omejitev "+str(self.max_number_of_alternative_relation_matrices_to_use)+" alternativnih relacijskih matrik!")
                print("\t\t\tIzbiram "+str(self.max_number_of_alternative_relation_matrices_to_use)+" najgostejsih matrik")
                relation_matrices[relation]=self.select_denser_matrices(relation_matrices[relation])
                #self.relation_matrices[relation] = self.select_larger_matrices(self.relation_matrices[relation])



    def list_tables(self):
        '''
        List all data tables.
        '''
        if not self.tables==None:
            return

        self.cursor.execute("SELECT * FROM pg_catalog.pg_tables where schemaname = 'public'")
        self.tables = self.cursor.fetchall()
        # save list of tables to file
        self.checkpoint_file.write("#TABLES\n")
        for t in self.tables:
            self.checkpoint_file.write("\t".join([str(x) for x in t]) + "\n")
        self.checkpoint_file.write("\n")

    def list_key_constraints(self):
        '''
        Method lists foreign and primary key constraints.
        1.Lists columns that are foreign keys for every data table in database and where they point to.
        As a result it sets an object variable 'foreign_keys' with list of tuples formed: (id,table1,column1,table2,column2), where
            id - string formed as table name joined with column name using underscore character
            table1 - name of table containing FK column
            column1 - name of column that is marked as FK
            table2 - name of table containig column referenced by FK
            column2 - name of column referenced by FK
        2.Lists columns that are primary keys for every data table in database.
        As a result it sets an object variable 'primary_keys' with list of tuples formed: (table,column,type), where
            table - name of table containing PK constraint
            column - name of column that is marked as PK
            type - data type contained within column marked as PK
        '''
        if not self.foreign_keys==None and not self.primary_keys==None:
            return

        print("***Zbiranje vseh omejitev tipov 'tuji kljuc' in 'primarni kljuc'...")
        foreign_keys = []
        primary_keys = []
        for t in self.tables:
            if t[0]=='pg_catalog' or t[0]=='information_schema':
                print("ERRRRRRRRRROORRR.. za tole naj bi bilo ze poskrbljeno..ko odpravis lahko tale if izbrises")
                continue
            table_name = t[1]
            #print(t)
            #https://stackoverflow.com/questions/1152260/postgres-sql-to-list-table-foreign-keys
            self.cursor.execute(
                """select c.constraint_name
                , x.table_name
                , x.column_name
                , y.table_name as foreign_table_name
                , y.column_name as foreign_column_name
            from information_schema.referential_constraints c
            join information_schema.key_column_usage x
                on x.constraint_name = c.constraint_name
            join information_schema.key_column_usage y
                on y.ordinal_position = x.position_in_unique_constraint
                and y.constraint_name = c.unique_constraint_name
            order by c.constraint_name, x.ordinal_position""")
            #self.cursor.execute("SELECT tc.constraint_name, tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name FROM information_schema.table_constraints AS tc JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name WHERE constraint_type = 'FOREIGN KEY' AND tc.table_name = '" + table_name + "';")
            foreign_keys_tmp = self.cursor.fetchall()
            foreign_keys += foreign_keys_tmp
            self.cursor.execute("SELECT '"+table_name+"', a.attname, format_type(a.atttypid, a.atttypmod) AS data_type FROM   pg_index i JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE  i.indrelid = '"+table_name+"'::regclass AND    i.indisprimary;")
            primary_keys_tmp = self.cursor.fetchall()
            primary_keys+=primary_keys_tmp
        #return foreign_keys
        #foreign_keys=[x for x in foreign_keys if '_fkey' in x[0]]
        self.foreign_keys=foreign_keys
        self.foreign_keys=list(set(self.foreign_keys))
        self.primary_keys=primary_keys

        #save foreign keys to file
        self.checkpoint_file.write("#FOREIGN KEYS\n")
        for key in self.foreign_keys:
            self.checkpoint_file.write('\t'.join([str(z) for z in key])+"\n")
        self.checkpoint_file.write("\n")
        #save primary_keys to file
        self.checkpoint_file.write("#PRIMARY KEYS\n")
        for key in self.primary_keys:
            self.checkpoint_file.write('\t'.join(str(z) for z in key) + "\n")
        self.checkpoint_file.write("\n")

        '''fk_constraint_names_repeatabillity=Counter(fk_constraint_names)
        fk_constraint_names=[x[0] for x in self.foreign_keys]
        for y in fk_constraint_names_repeatabillity:
            if fk_constraint_names_repeatabillity[y]>1:
                print("GTE2: ",[x for x in self.foreign_keys if x[0]==y])'''


    def list_connected_tables(self):
        '''
        Lists all foreign key connections between pairs of tables.
        :return:
        sets object variable table_relations as a list of tuples.
        Each tuple contains ordred pair of table names, indicating that table at index 0 references table at index 1.
        '''
        self.table_relations = list(set([(x[1],x[3]) for x in self.foreign_keys])) #usmerjene povezave med tabelami (tabela1,tabela2) --> tabela1 je prek tujega kljuca povezana s tabelo2


    '''def list_tables_gte2_fk(self):
    
        List all tables, that reference at least 2 other tables via foreign keys.
        
        print("***Iskanje tabel, ki preko tujih kljucev referencirajo vsaj 2 razlicni tabeli...")
        self.tables_nr_fk=Counter([x[0] for x in self.table_relations]) #stevilo povezav na ostale tabele
        self.tables_gte2_fk=[x for x in self.tables_nr_fk if self.tables_nr_fk[x]>=2]'''

    def table_count_fk(self,table):
        '''
        :param table: table name
        :return: number of foreign keys in a given table
        '''
        fk_nr=Counter(set([([(x[0],x[1]) for x in self.foreign_keys])])) #stevilo tujih kljucev znotraj tabele
        return len([x[0] for x in self.foreign_keys if x[1]==table])

    def count_fk(self):
        '''
        :return: returns dictionary which stores number of foreign keys for each table
        '''
        return Counter([y[1] for y in set([(x[0], x[1]) for x in self.foreign_keys])])


    def list_tables_gte2_fk(self):
        '''
        List all tables, that contain at least two foreign keys
        '''
        print("***Iskanje tabel, z najmanj 2 tujima kljucema...")
        self.tables_nr_fk=Counter([x[1] for x in set([(x[0],x[1]) for x in self.foreign_keys])]) #stevilo tujih kljucev znotraj tabele
        self.tables_gte2_fk=[x for x in self.tables_nr_fk if self.tables_nr_fk[x]>=2]

    def get_column_data_types(self):
        '''
        For every data table in database lists all column and data type it holds.
        As a result it sets an object variable with dictionary where each entry has form
        id: (column,data_type) ; where:
            id - key string formed as table name joined with column name using space character
            column - name of a column
            data_type - type of data stored in column
        '''
        print("***Pridobivanje podatkov o podatkovnih tipih stolpcev...")
        self.cursor.execute("SELECT * FROM information_schema.tables WHERE table_schema = 'public';") #list tables
        tables=self.cursor.fetchall()
        column_types = {}
        for t in tables:
            self.cursor.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_name = '"+t[2]+"';")  # list tables
            columns = self.cursor.fetchall()
            for c in columns:
                column_types[t[2]+' '+c[0]]=c
        #return column_types
        self.column_data_type=column_types

    def list_table_columns(self,table):
        '''
        List names of columns for given table name;
        :param table: name of the table
        :return: list of names columns contained within specified table
        '''
        self.cursor.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_name = '" + table + "';")
        return [x[0] for x in self.cursor.fetchall()]

    def join_outmost_tables(self):
        '''
        Function 'recursively' finds outmost tables with no foreign keys and joins their columns to tables that reference them.
        As a result:
            -table excluded_tables contains a list of names of tables that have been joined and therefore shuld be excluded from further processing.
            -dictionary modified_tables contains modified tables (with aditional columns from joined tables) that shuld be used for further work instead of original tables within a database.
        '''
        '''
        Alternativno: namesto da se hrani celotne modificirane matrike, shrani le SQL poizvedbe za njihovo sestavo
        '''
        print("***pridruzevanje zunanjih tabel...")
        #print(self.excluded_tables)
        #print(self.modified_tables)
        if not self.excluded_tables==None and not self.modified_tables==None:
            return


        self.excluded_tables=set()
        self.modified_tables={}
        tables_to_modify=set()

        tables_nr_fk=self.count_fk()
        #find tables with no foreign keys
        '''tables_with_fk=set([x[1] for x in self.foreign_keys])
        tables_without_fk=set([x for x in self.tables if x not in tables_with_fk])'''
        tables_without_fk=set([x[1] for x in self.tables if x[1] not in tables_nr_fk])
        tables_without_fk_having_connected_tables = set([x[3] for x in self.foreign_keys if x[3] in tables_without_fk])
        tables_without_fk_having_connected_tables_with_one_fk=set([x for x in tables_without_fk_having_connected_tables if tables_nr_fk[x]==1])
        tables_connected_to_tables_without_fk=set([x[1] for x in self.foreign_keys if x[3] in tables_without_fk])
        tables_with_one_fk_connected_to_tables_without_fk=set([x for x in tables_connected_to_tables_without_fk if tables_nr_fk[x]==1])
        tables_to_modify=tables_with_one_fk_connected_to_tables_without_fk
        self.excluded_tables = tables_without_fk_having_connected_tables_with_one_fk

        len_tables_to_modify_tmp=-1
        while len(tables_to_modify)!=len_tables_to_modify_tmp:
            len_tables_to_modify_tmp=len(tables_to_modify)
            tables_without_fk = tables_to_modify
            tables_without_fk_having_connected_tables = set([x[3] for x in self.foreign_keys if x[3] in tables_without_fk])
            tables_without_fk_having_connected_tables_with_one_fk = set([x for x in tables_without_fk_having_connected_tables if tables_nr_fk[x] == 1])
            tables_connected_to_tables_without_fk = set([x[1] for x in self.foreign_keys if x[3] in tables_without_fk])
            tables_with_one_fk_connected_to_tables_without_fk = set([x for x in tables_connected_to_tables_without_fk if tables_nr_fk[x] == 1])
            tables_to_modify_having_connected_tables_with_one_fk=set([x[3] for x in self.foreign_keys if x[3] in tables_to_modify and tables_nr_fk[x[1]]==1])
            tables_to_modify = (tables_to_modify - tables_to_modify_having_connected_tables_with_one_fk) | tables_with_one_fk_connected_to_tables_without_fk
            self.excluded_tables |= tables_without_fk_having_connected_tables_with_one_fk

        print("###EXCLUDED TABLES:",self.excluded_tables)

        for t in tables_to_modify:
            sql_query = "SELECT * FROM "+t+' '
            table=t
            while True:
                table_connected_to_table=set([x[3] for x in self.foreign_keys if x[1]==t])
                if len(table_connected_to_table)==0:
                    break
                else:
                    table_connected_to_table=table_connected_to_table[0]
                    sql_query+=" INNER JOIN "+table_connected_to_table+" ON "
                    sql_query+=' AND '.join(x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4]+' ' for x in self.foreign_keys if x[1]==table and x[3]==table_connected_to_table)
            sql_query+=';'
            self.modified_tables[t]=sql_query

            #write to checkpoint file
            self.checkpoint_file.write("#EXCLUDED TABLES LIST\n")
            self.checkpoint_file.write("\n".join(self.excluded_tables))
            self.checkpoint_file.write("\n\n")
            self.checkpoint_file.write("#MODIFIED TABLES LIST\n")
            for x in self.modified_tables:
                print(x)
                self.checkpoint_file.write(x+"\n")
                for y in self.modified_tables[x]:
                    self.checkpoint_file.write("\t".join([str(z) for z in y])+"\n")
                self.checkpoint_file.write("!\n")
            self.checkpoint_file.write("\n")

    def get_column_data_types_tables_gte2_fk(self):
        '''
        For every intermediate data table in database lists all column and data type it holds.
        As a result it sets an object variable with dictionary where each entry has form
        id: (column,data_type) ; where:
            id - key string formed as table name joined with column name using underscore character
            column - name of a column
            data_type - type of data stored in column
        '''
        column_types={}
        for t in self.tables_gte2_fk:
            self.cursor.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_name = '" + t + "';")
            columns = self.cursor.fetchall()
            for c in columns:
                column_types[t + ' ' + c[0]] = c
        # return column_types
        self.column_data_type= column_types

    def filter_columns_fusion(self):
        '''
        Filters columns to only those, that can actually be used as values inside relation matricies.
        So we filter out:
            -columns marked as Foreign Keys
            -columns containing non-numerical data
            (Some non-numerical data can be converted tu nomerical: booleans, strings with finite(repeating) number of options..)
        As a result it sets an object variable with dictionary, where each entry has a form:
        id: (column,data_type)
            id - key string formed as table name joined with column name using underscore character
            column - name of a column
            data_type - type of data stored in column

        TO-DO: IZLOCI STOLPCE, KI PREDSTAVLJAJO PRIMARNI KLJUC??
        (kaj pa ce PK predstavlja kombinacija 2 stolpcev, kjer je posamezen se vedno lahko uporaben pri zlivanju?)
        '''
        print("***Izbor stolpcev primernih za zlivanje..")
        data_types_fusion=['smallint','integer','bigint','decimal','numeric','real','double precision','smallserial','serial','bigserial']
        data_types_fusion+=['text','str'] #uporaba v kombinaciji z razbitjem na mnozico indikatorskih spremenljivk
        column_fusion={}
        fk_ids=[id[0] for id in self.foreign_keys]
        for c_id in self.column_data_type:
            if not c_id in fk_ids and self.column_data_type[c_id][1] in data_types_fusion:
                #kaj pa v primeru ce c_id niso enaki id-jem tujih kljucev?
                column_fusion[c_id]=self.column_data_type[c_id]
        self.column_fusion=column_fusion

    def gen_matrices_for_column(self,fk_link1,fk_link2,table,column_id):
        '''
        :param table1:
        :param table2:
        :param table:
        :param column_id:
        :return:list of relational matrices.
        Only 1 matrix if binarization of attribute(column_id) is not required.
        '''

        #TEST!!!!!!!!!!!!!!  quick-and-dirty fix?
        if ' ' in column_id:
            column_id=column_id[column_id.index(' '):]
        column_id=column_id.strip()
        '''table_column_names=self.list_table_columns(table)
        if column_id not in table_column_names:
            print("COLUMN ",column_id," NOT IN ",table_column_names)
            if '_' in column_id:
                column_id=column_id[column_id.index('_')+1:]'''


        table1=fk_link1[2]
        table2=fk_link2[2]

        #print("GENERATE RELATION MATRIX",table1,table2,table+'->'+column_id)
        matrices=[]
        #print("\tGeneriranje matrik za stolpec vmesne matrike..")
        if self.presampling_mode:
            objects_table1=self.sample[table1]
            objects_table2=self.sample[table2]
        else:
            objects_table1 = self.get_object_ids(table1)
            objects_table2 = self.get_object_ids(table2)
        # print("OBJECTS TABLE 1 ",objects_table1)
        # print("OBJECTS TABLE 2 ",objects_table2)
        '''table_table1_fk=[x for x in self.foreign_keys if x[1]==table and x[3]==table1]
        table_table1_fk_names=set([x[0] for x in table_table1_fk])
        table_table2_fk=[x for x in self.foreign_keys if x[1]==table and x[3]==table2]
        table_table2_fk_names=set([x[0] for x in table_table2_fk])'''
        table_table1_fk = [x for x in self.foreign_keys if x[1] == table and x[3] == table1 and x[0]==fk_link1[0]]
        table_table2_fk = [x for x in self.foreign_keys if x[1] == table and x[3] == table2 and x[0]==fk_link2[0]]

        '''if len([x for x in self.primary_keys if x[0]==table1])<len(table_table1_fk) or len([x for x in self.primary_keys if x[0]==table2])<len(table_table2_fk):
            print("\tPROBLEM: ocitno sta tabeli povezani preko vecih sklopov stolpcev/kljucev!! - REZULTAT NE BO 'OPTIMALEN'")
            print("\tSANITY CHECK: Je st. tujih kljucev veckratnik stevila stolpcev primarnega kljuca? ")
            print(str(len(table_table1_fk))+' = n * '+str(len([x for x in self.primary_keys if x[0]==table1]))+"???  ---> ",len(table_table1_fk)%len([x for x in self.primary_keys if x[0]==table1])==0)
            print(str(len(table_table2_fk))+' = n * '+str(len([x for x in self.primary_keys if x[0]==table2]))+"???  ---> ",len(table_table2_fk)%len([x for x in self.primary_keys if x[0]==table2])==0)'''

        if len(objects_table1[1]) == 0 or len(objects_table2[1]) == 0:
            return []
        #CE JE MED DVEMA TABELAMA VEC FK POVEZAV KATERO IZBRATI ZA ZDRUZITEV TABEL?? --> TRETIRAJ LOCENO!! namesto po povezanih tabelah se sprehajaj po kombinacijah tujih kljucev
        #sql_query="SELECT "+', '.join(x[3]+'.'+x[4] for x in table_table1_fk)+', '+', '.join(x[3]+'.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table1+" INNER JOIN "+table+" ON "+' AND '.join([' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table1_fk if x[0]==y]) for y in table_table1_fk_names])+" INNER JOIN "+table2+" ON "+' AND '.join([' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table2_fk if x[0]==y]) for y in table_table2_fk_names])+';'
        '''print("TAAABLEEE",table)
        print("COLUMN ID",column_id)'''
        if self.presampling_mode:
            sql_query="SELECT "+', '.join('a.'+x[4] for x in table_table1_fk)+', '+', '.join('b.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table+" INNER JOIN "+table1+" as a ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'a.'+x[4] for x in table_table1_fk ])+" INNER JOIN "+table2+" as b ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'b.'+x[4] for x in table_table2_fk])
            sql_query+=' WHERE ( '


            '''
            for y in self.sample[table1][1]:
                for x in range(len(self.sample[table1][0])):
                    sql_query+="a."+str(self.sample[table1][0][x])+" = '"+y[x]+"' OR "
            sql_query = sql_query[:-len(" OR ")]
            sql_query+=" ) AND ( "
            for y in self.sample[table2][1]:
                for x in range(len(self.sample[table2][0])):
                    sql_query += "b."+str(self.sample[table2][0][x]) + " = '" + y[x] + "' OR "
            sql_query=sql_query[:-len(" OR ")]
            sql_query+=');'
            '''

            for y in self.sample[table1][1]:
                sql_query+=' ( '
                for x in range(len(self.sample[table1][0])):
                    sql_query += "a." + str(self.sample[table1][0][x]) + " = '" + str(y[x]) + "' AND "
                sql_query = sql_query[:-len(" AND ")]
                sql_query += ') '
                sql_query+=' OR '
            sql_query = sql_query[:-len(" OR ")]
            sql_query+=" ) AND ( "
            for y in self.sample[table2][1]:
                sql_query+=' ( '
                for x in range(len(self.sample[table2][0])):
                    sql_query += "b." + str(self.sample[table2][0][x]) + " = '" + str(y[x]) + "' AND "
                sql_query = sql_query[:-len(" AND ")]
                sql_query += ') '
                sql_query+=' OR '
            sql_query = sql_query[:-len(" OR ")]
            sql_query+=');'

            #sql_query="SELECT "+', '.join('a.'+x[4] for x in table_table1_fk)+', '+', '.join('b.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table+" INNER JOIN "+table1+" as a ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'a.'+x[4] for x in table_table1_fk ])+" INNER JOIN "+table2+" as b ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'b.'+x[4] for x in table_table2_fk])+' WHERE ('+'OR '.join([' OR '.join([self.sample[table1][0][x]+" = "+y[x] for x in range(len(self.sample[table1][0]))]) for y in self.sample[table1][1]])+") AND ("+'OR '.join([' OR '.join([self.sample[table2][0][x]+" = "+y[x] for x in range(len(self.sample[table2[0]]))]) for y in self.sample[table2][1]])
            #sql_query="SELECT "+', '.join('a.'+x[4] for x in table_table1_fk)+', '+', '.join('b.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table+" INNER JOIN "+table1+" as a ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'a.'+x[4] for x in table_table1_fk ])+" INNER JOIN "+table2+" as b ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'b.'+x[4] for x in table_table2_fk])+' WHERE ('+'OR '.join([' OR '.join([y[0][x]+" = "+list(y[1])[x] for x in range(len(y[0]))]) for y in self.sample[table1]])+") AND ("+'OR '.join([' OR '.join([y[0][x]+" = "+list(y[1])[x] for x in range(len(y[0]))]) for y in self.sample[table2]])

        else:
            sql_query="SELECT "+', '.join('a.'+x[4] for x in table_table1_fk)+', '+', '.join('b.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table+" INNER JOIN "+table1+" as a ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'a.'+x[4] for x in table_table1_fk ])+" INNER JOIN "+table2+" as b ON "+' AND '.join([x[1]+'.'+x[2]+' = '+'b.'+x[4] for x in table_table2_fk])+';'

        #print(sql_query)
        self.cursor.execute(sql_query)
        #print("SELECT "+', '.join(x[3]+'.'+x[4] for x in table_table1_fk)+', '+', '.join(x[3]+'.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table1+" INNER JOIN "+table+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table1_fk])+" INNER JOIN "+table2+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table2_fk])+';')
        #self.cursor.execute("SELECT "+', '.join(x[3]+'.'+x[4] for x in table_table1_fk)+', '+', '.join(x[3]+'.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table1+" INNER JOIN "+table+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table1_fk])+" INNER JOIN "+table2+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table2_fk])+';')
        rows=self.cursor.fetchall()
        rows = np.array(rows)

        nr_columns=1
        if rows.shape[0]>0 and (self.column_data_type[table+' '+column_id][1]=="str" or self.column_data_type[table+' '+column_id][1]=="text"):
            if len(set(rows[:,-1]))>self.dummy_variable_treshold:
                print("\t\t\t\t\t\t\tStolpec "+table+"."+column_id+" ima prevec razlicnih vrednosti za razbitje na mnozico indikatorskih spremenljivk.")
                return []
            labelencoder=LabelEncoder()
            rows[:,-1]=labelencoder.fit_transform(rows[:,-1])
            nr_columns=len(labelencoder.classes_)
            onehotencoder = OneHotEncoder(categorical_features=[-1])
            dummy_variables=onehotencoder.fit_transform(rows[:,-1].reshape(-1, 1)).toarray()
            rows=np.delete(rows,-1,1)
            rows=np.append(rows,dummy_variables,1)
            #dummy variable trap?
            #move dummy variables from begining to end of table!


        for i in range(nr_columns):
            #R=np.zeros((len(objects_table1[1]),len(objects_table2[1])))
            R = np.empty((len(objects_table1[1]), len(objects_table2[1])))
            R.fill(np.nan)
            matrices.append(R)
        column_order_row_o1=[x[4].strip() for x in table_table1_fk]
        column_order_row_o2 = [x[4].strip() for x in table_table2_fk]
        #print("fkLINK 1",fk_link1)
        objects_table1_data_type_postgres=[self.column_data_type[table1+' '+x][1] for x in objects_table1[0]]
        objects_table1_data_type_python=[self.postgres_to_python_data_types[x.upper()] for x in objects_table1_data_type_postgres]
        objects_table2_data_type_postgres = [self.column_data_type[table2 + ' ' + x][1] for x in objects_table2[0]]
        objects_table2_data_type_python=[self.postgres_to_python_data_types[x.upper()] for x in objects_table2_data_type_postgres]
        for row in rows:
            c1=row[0:len(objects_table1[0])]
            c1_tmp=[]
            for x in range(len(c1)):
                if objects_table1_data_type_python[x]=='integer':
                    c1_tmp.append(int(c1[x]))
                elif objects_table1_data_type_python[x]=='float':
                    c1_tmp.append(float(c1[x]))
                else:
                    c1_tmp.append(str(c1[x]))
            c1=c1_tmp
            #REMOVE .strip() quickfix
            #c1=tuple([c1[column_order_row_o1.index(x)] for x in objects_table1[0]])
            c1=[c1[column_order_row_o1.index(x)] for x in objects_table1[0]]
            #print("TYPE? ",str(type(c1[0]))=="<class \'numpy.str_\'>")
            c1=[x.strip() if type(x)=='str' or str(type(x))=="<class \'numpy.str_\'>" else x for x in c1]

            c1=tuple(c1)
            #c2=row[len(objects_table1[0]):-nr_columns]
            c2 = row[len(objects_table1[0]):-nr_columns]
            c2_tmp = []
            for x in range(len(c2)):
                if objects_table2_data_type_python[x] == 'integer':
                    c2_tmp.append(int(c2[x]))
                elif objects_table2_data_type_python[x] == 'float':
                    c2_tmp.append(float(c2[x]))
                else:
                    c2_tmp.append(str(c2[x]))
            c2 = c2_tmp
            #c2 = tuple([c2[column_order_row_o2.index(x)].strip() for x in objects_table2[0]])
            c2 = [c2[column_order_row_o2.index(x)] for x in objects_table2[0]]
            #print("TYPE? ", str(type(c2[0])) == "<class \'numpy.str_\'>")
            c2=[x.strip() if type(x)=='str' or type(x)=="<class \'numpy.str_\'>" else x for x in c2]
            c2=tuple(c2)



            v=row[-nr_columns:]
            for i in range(nr_columns):
                '''print("OBJECTS 1",objects_table1)
                #print("TYPE 1",self.column_data_type[table1])
                print("OBJECTS 2",objects_table2)
                #print("TYPE 2",self.column_data_type[table2])
                print("C1",c1)
                print("C2",c2)
                print("C1 TYPES",str(type(c1[0])))
                print("C2 TYPES",str(type(c2[0])))'''
                matrices[i][list(objects_table1[1]).index(c1)][list(objects_table2[1]).index(c2)]=v[i]
        return matrices

    def get_object_ids(self,table):
        '''
        Get list of unique combinations of values for columns representing (composite) primary key.
        Returns list with header(tuple of ordered column names) at index 0 and list of different value combinations (tuples) at index 1.
        '''
        pk_columns = [x[1] for x in self.primary_keys if x[0]==table]
        if self.presampling_mode:
            sql_query="SELECT " + ','.join(pk_columns) + " FROM " + table
            sql_query += ' WHERE '
            for y in self.sample[table][1]:
                sql_query+=' ( '
                for x in range(len(self.sample[table][0])):
                    sql_query += table+"." + str(self.sample[table][0][x]) + " = '" + str(y[x]) + "' AND "
                sql_query = sql_query[:-len(" AND ")]
                sql_query += ') '
                sql_query+=' OR '
            sql_query = sql_query[:-len(" OR ")] +';'
            self.cursor.execute(sql_query)
        else:
            self.cursor.execute("SELECT "+','.join(pk_columns)+" FROM "+table+";")
        #print("SELECT "+','.join(pk_columns)+" FROM "+table+";")
        rows=list(set(self.cursor.fetchall()))
        return [pk_columns,rows]

    def gen_indicator_matrix_for_relation(self,table1,fk_link):
        '''
        For two tables related via Foreign Key constraint create matrix of dimensions |objects in table1| x |objects in table2|,
        that has 1 in every cell for actually related objects and 0 elsewhere.
        :param table1:
        :param table2:
        :return:
        '''
        print("TABELE, KI SO V VZORCU:",self.sample_tables)
        table2 = fk_link[2]
        objects_table1=self.get_object_ids(table1)
        objects_table2=self.get_object_ids(table2)
        #print("OBJECTS TABLE 1 ",objects_table1)
        #print("OBJECTS TABLE 2 ",objects_table2)
        table_relations=[x for x in self.foreign_keys if x[1]==table1 and x[3]==table2 and x[0]==fk_link[0]]

        if len(objects_table1[1]) == 0 or len(objects_table2[1]) == 0:
            return []
        #R = np.zeros((len(objects_table1[1]), len(objects_table2[1])))
        R = np.empty((len(objects_table1[1]), len(objects_table2[1])))
        R.fill(np.nan)
        #fill in 1s
        header_fk_tmp=[]
        for x in objects_table2[0]:
            for y in table_relations:
                if y[3]==table2 and y[4]==x:
                    header_fk_tmp.append(y[2])
        if table1==table2:
            #PROBLEM PRI SESTAVLJENIH PRIMARNIH KLJUCEV ZARADI povezovanja vsakega od FK stoplcev na VSAKEGA od PK stolpcev??
            self.cursor.execute("SELECT "+",".join(["a."+x for x in objects_table1[0]])+','+",".join("b."+x for x in objects_table2[0])+" FROM "+table1+" as a INNER JOIN "+table2+" as b ON "+" AND ".join(["a."+x[2]+" = "+"b."+x[4] for x in table_relations])+";")
            #self.cursor.execute("SELECT "+",".join(["a."+x for x in objects_table1[0]])+','+",".join("b."+x for x in objects_table2[0])+" FROM "+table1+"as a NATURAL JOIN "+table2+" as b;")
        else:
            #print("SELECT "+",".join([table1+"."+x for x in objects_table1[0]])+','+",".join(table2+"."+x for x in objects_table2[0])+" FROM "+table1+" INNER JOIN "+table2+" ON "+" AND ".join([x[1]+"."+x[2]+" = "+x[3]+"."+x[4] for x in table_relations])+";")
            self.cursor.execute("SELECT "+",".join([table1+"."+x for x in objects_table1[0]])+','+",".join(table2+"."+x for x in objects_table2[0])+" FROM "+table1+" INNER JOIN "+table2+" ON "+" AND ".join([x[1]+"."+x[2]+" = "+x[3]+"."+x[4] for x in table_relations])+";")
        lines=self.cursor.fetchall()
        for line in lines:
            #print("LINE ",line)
            object1_id=tuple(line[0:len(objects_table1[0])])
            '''print("O1ID: ",object1_id)
            print("OBJECTS TABLE 1",objects_table1)'''
            object2_id=tuple(line[len(objects_table1[0]):])
            '''print("O2ID: ",object2_id)
            print("OBJECTS TABLE 2",objects_table2)'''
            if len(object1_id)==0 or len(object2_id)==0 or None in object1_id or None in object2_id:
                continue
            object1_indx=objects_table1[1].index(object1_id)
            object2_indx=objects_table2[1].index(object2_id)
            R[object1_indx,object2_indx]=1

        return [R]


    def list_object_types(self):
        '''
        Table is identified as the one representing object type if at least one of columns composing primary key
        is located within the observed table (meaning it is not referencing another table as foreign key).

        As a result, method defines and initializes object variable object_types as a list of names
        for each table representing object type.
        '''
        if not self.object_types==None:
            return

        self.object_types=[]
        for table in self.tables:
            primary_key_columns=[x[1] for x in self.primary_keys if x[0]==table[1]]
            foreign_key_columns=[x[2] for x in self.foreign_keys if x[1]==table[1]]
            for key in primary_key_columns:
                if not key in foreign_key_columns:
                    self.object_types.append(table[1])
                    break

        #save list of object types to file
        self.checkpoint_file.write("#OBJECT TYPES\n")
        for line in self.object_types:
            self.checkpoint_file.write(line+"\n")
        self.checkpoint_file.write("\n")

    def build_relation_matricies(self):
        '''
        Build relation and constraint matrices for fusion process.
        Build relation matrices for every pair of object types, that is implicitly related via third table and
        also build one indicator relation matrix for each pair of directly connected object types.
        If object type is referencing itself, also build constraint matrix.
        :return:
        '''
        if not self.relation_matrices==None and not self.constraint_matrices==None :
            return

        print("***Gradnja relacijskih in omejitvenih matrik..")
        relation_matrices = {}  # pripravi strukturo za hranjenje vseh moznih relacijskih matrik
        constraint_matrices = {}  # pripravi strukturo za hranjenje vseh moznih omejitvenih matrik


        tables=set([x for x,y in self.table_relations])
        table_count=0
        for t in tables:
            table_count+=1
            print("\t ( "+str(table_count)+' / '+str(len(tables))+" )\tGradim relacijske matrike za tabelo: ",t)
            if self.presampling_mode:
                if t not in self.sample_tables:
                    print("\t\t\tTABELE NI V VZORCU!!")
                    '''print("T",t)
                    print("SAMPLE",self.sample_tables)'''
                    continue
            tables_linked_to_t=[y for x,y in self.table_relations if x==t]
            fk_names_linked_to_t=set([(y[0],y[1],y[3]) for y in self.foreign_keys if y[1]==t])
            '''print("TTTTTT:",t)
            print("FKNAMESLINKED:",fk_names_linked_to_t)'''
            if len(tables_linked_to_t)>=2:
                #Zgradi relacijske matrike za posredno povezane tabele.
                #self.tables_object_types+=tables_linked_to_t
                #for t1,t2 in itertools.combinations(tables_linked_to_t,2):
                table_combo_count=0
                fk_linked_to_t_combinations=list(itertools.combinations(fk_names_linked_to_t,2))
                for t1,t2 in fk_linked_to_t_combinations:
                    table_combo_count+=1
                    #print("T1: ",t1,"T2: ",t2)
                    print("\t\t\t( "+str(table_combo_count)+' / '+str(len(fk_linked_to_t_combinations))+" )\tGradim relacijske matrike za povezavi:",t1,'in',t2)
                    if self.presampling_mode:
                        if t1[2] not in self.sample_tables or t2[2] not in self.sample_tables:
                            print("\t\t\t\t\tENE OD TABEL NI V VZORCU!!")
                            '''print("T1",t1[2])
                            print("T2",t2[2])
                            print("SAMPLE",self.sample_tables)'''
                            continue
                    #print("!!!!STOLPCI PRIMERNI ZA ZLIVANJE, KI NAJ BI PRIPADALI TABELI "+str(t),[x for x in self.column_fusion if t+' ' in x])
                    column_count=0
                    columns_matrix_build=[x for x in self.column_fusion if x.split(' ')[0]==t]
                    for c in columns_matrix_build:
                        column_count+=1
                        print("\t\t\t\t\t( " + str(column_count) + ' / ' + str(len(columns_matrix_build)) + " )\tGradim relacijske matrike stolpec:", c)
                        c=c[len(t+' '):]
                        matrices=self.gen_matrices_for_column(t1,t2,t,c)
                        if not t1[2]+' '+t2[2] in relation_matrices:
                            relation_matrices[t1[2] + ' ' + t2[2]] = []
                        relation_matrices[t1[2]+' '+t2[2]]+=matrices
            if len(tables_linked_to_t)>=1:
                #Zgradi relacijske matrike za vsako direktno povezavo obravnavane tabele.
                #for t1 in tables_linked_to_t:
                table_combo_count=0
                for t1 in fk_names_linked_to_t:
                    table_combo_count+=1
                    print("\t\t\t( "+str(table_combo_count)+' / '+str(len(fk_names_linked_to_t))+" )\tGradim omejitvene oz. indikatorske matrike za povezavo s:",t1)
                    if self.presampling_mode:
                        if t1 not in self.sample_tables:
                            '''print("\tTABELE NI V VZORCU!!")
                            print("T1", t1)
                            print("SAMPLE", self.sample_tables)'''
                            continue
                    matrices=self.gen_indicator_matrix_for_relation(t,t1)
                    if t==t1[2]:
                        if not t in constraint_matrices:
                            constraint_matrices[t] = []
                        constraint_matrices[t] += matrices
                    else:
                        #Indikatorske matrike tudi gradimo, da lahko zagotovimo povezanost grafa, ki ga podamo fusion algoritmu
                        if not t + ' ' + t1[2] in relation_matrices:
                            relation_matrices[t + ' ' + t1[2]] = []
                        #Lahko zgradimo po eno za vsak stolpec (katere koli od) povezanih tabel
                        relation_matrices[t + ' ' + t1[2]] += matrices
            self.limit_relation_matrices_number(relation_matrices) #Zaradi porabe pomnilnika ze spotoma filtriraj seznam alternativnih matrik
        self.relation_matrices=relation_matrices
        self.constraint_matrices=constraint_matrices
        #print("RELATION MATRICES: ",relation_matrices)
        #print("CONSTRAINT MATRICES: ",constraint_matrices)

        #Write to checkpoint file
        self.checkpoint_file.write("#RELATION MATRICES\n")
        for key in self.relation_matrices:
            self.checkpoint_file.write(key+"\n")
            for t in self.relation_matrices[key]:
                for line in t:
                    self.checkpoint_file.write("\t".join([str(x) for x in line])+"\n")
                self.checkpoint_file.write("!\n")
            self.checkpoint_file.write('!!\n')
        self.checkpoint_file.write("\n")

        self.checkpoint_file.write("#CONSTRAINT MATRICES\n")
        for key in self.constraint_matrices:
            self.checkpoint_file.write(key + "\n")
            for t in self.constraint_matrices[key]:
                for line in t:
                    self.checkpoint_file.write("\t".join([str(x) for x in line]) + "\n")
                self.checkpoint_file.write("!\n")
            self.checkpoint_file.write('!!\n')
        self.checkpoint_file.write("\n")


    def test_references_same_table_more_than_once(self,table1,table2):
        '''
        :return:    True; if table1 references table2 via FK >=2 times
                    False; else
        '''
        foreign_keys = [x[4] for x in self.foreign_keys if x[1] == table1 and x[3]==table2]
        c=Counter(foreign_keys)
        return all(x>=2 for x in c.values())

    def test_references_same_table_more_than_once_composite_PK(self,table1,table2):
        '''

        :return:    True; if table1 references table2 via FK >=2 times AND table2 has composite PK
                    False; else

        https://www.postgresql.org/docs/9.0/static/catalog-pg-constraint.html
        '''
        return self.test_references_same_table_more_than_once(table1,table2) and len(x for x in self.primary_keys if x[0]==table2)>=2

    def presample(self):
        '''
        Sample table relations so that no Relation matrix dimension is greater than the user specified bound.
        Method is randomly selecting lines from tables that reference at least two tables via FK until SUM of implicitly selected objects
        from any pair of referenced tables reaches specified limit.

        Try out different sampling methods to downsize relational matrices.

        Should ratio between table sizes be preserved??
        https://www.postgresql.org/docs/9.0/static/infoschema-referential-constraints.html
        
        :return:
        '''
        if not self.sample==None:
            return

        print("***Vzorcenje relacij...")
        self.sample={}
        self.sample_tables=set()
        table_count=0
        for t in self.tables_gte2_fk:
            table_count+=1
            print("\t ( "+str(table_count)+' / '+str(len(self.tables_gte2_fk))+" ) Vzorcim relacije preko tabele:",t)
            table_is_ot=True if t in self.object_types else False
            foreign_keys = [x for x in self.foreign_keys if x[1] == t] #tuji kljuci znotraj tabele
            foreign_keys_names=set([x[0] for x in foreign_keys])
            referenced_tables = [x[1] for x in self.table_relations if x[0] == t]
            if self.presampling_mode:
                self.presampling_mode=False
                table_ids=self.get_object_ids(t)
                self.presampling_mode=True
            else:
                table_ids=self.get_object_ids(t)
            referenced_tables_ids={}
            reffering_columns=[]
            reffering_columns_ordered_list=[]
            columns_select = ""
            for x in foreign_keys_names:
                fk_x=[y for y in foreign_keys if y[0]==x]
                reffering_columns=[y[2] for y in fk_x]
                reffering_columns=[y[0] for y in itertools.groupby(reffering_columns)]
                reffering_columns_ordered_list=reffering_columns_ordered_list+reffering_columns
                columns_select += ',' + ','.join(reffering_columns)
            columns_select = columns_select[1:]

            number_selected_objects=0
            while number_selected_objects<self.max_number_of_objects and len(table_ids[1])>0:
                #later select multiple rows at once!
                relation_id=random.choice(table_ids[1]) #randomly choose row from table
                table_ids[1].remove(relation_id) #remove that row from further selection
                self.cursor.execute("SELECT "+columns_select+" FROM "+t+" WHERE "+','.join([str(table_ids[0][x])+"='"+str(relation_id[x])+"'" for x in range(len(table_ids[0]))])+';')
                relation_row=self.cursor.fetchall()[0]
                if table_is_ot:
                    if not t in self.sample:
                        self.sample[t]=[table_ids[0],set()]
                    self.sample[t][1].add(tuple(relation_id))
                    #self.sample[t] = list(set(self.sample[t]))

                for referenced_table in referenced_tables:
                    self.sample_tables.add(referenced_table)
                    if self.presampling_mode:
                        self.presampling_mode=False
                        referenced_tables_ids[referenced_table] = self.get_object_ids(referenced_table)
                        self.presampling_mode=True
                    else:
                        referenced_tables_ids[referenced_table] = self.get_object_ids(referenced_table)
                    if not referenced_table in self.sample:
                        self.sample[referenced_table] = [referenced_tables_ids[referenced_table][0],set()]
                    #id = [tuple([[relation_row[reffering_columns_ordered_list.index(z[2])] for z in fk_x if z[4] == y]]) for y in referenced_tables_ids[x][0]]
                    referenced_table_fk_names=set([x[0] for x in foreign_keys if x[3]==referenced_table])
                    for fk_name in referenced_table_fk_names:
                        id=[]
                        fk=[x for x in foreign_keys if x[0]==fk_name]
                        for fk_column in referenced_tables_ids[referenced_table][0]:
                            column=[z[2] for z in fk if z[4]==fk_column][0]
                            value=relation_row[reffering_columns_ordered_list.index(column)]
                            id.append(value)
                        if not None in id:
                            self.sample[referenced_table][1].add(tuple(id))
                            #self.sample[referenced_table]=set(self.sample[referenced_table])

                #sum of selected rows for a pair of referenced tables with largest sample size
                nr_rows_tables=[len(self.sample[x][1]) for x in referenced_tables]
                number_selected_objects=max(nr_rows_tables)
                nr_rows_tables.remove(number_selected_objects)
                number_selected_objects+=max(nr_rows_tables)
        #print("\tSAMPLE:",self.sample)
        #Save sample to disk
        self.checkpoint_file.write("#SAMPLE\n")
        for key in self.sample:
            self.checkpoint_file.write(key + "\n")
            self.checkpoint_file.write('\t'.join(self.sample[key][0])+'\n')
            for t in self.sample[key][1]:
                self.checkpoint_file.write("\t".join([str(x) for x in t]) + "\n")
            self.checkpoint_file.write("!\n")
        self.checkpoint_file.write("\n")

    def generate_fusion_graphs(self):
        print("***Generiram graf za zlivanje..")
        self.object_types_fusion = {}
        relational_matrices_keys = list(self.relation_matrices.keys())
        # print("RELATIONAL MATRICES KEYS",relational_matrices_keys)
        constraint_matrices_keys = list(self.constraint_matrices.keys())

        # print('OBJEKTNI TIPI: ',self.object_types)
        for type_name in self.object_types:
            self.object_types_fusion[type_name] = fusion.ObjectType(type_name)

        matrices_of_relational_matrices = []  # seznam hrani vse mozne nabore matrik relacijskih matrik
        first = True
        for relation_key in relational_matrices_keys:
            if first:
                matrices_of_relational_matrices += self.relation_matrices[relation_key]
                first = False
                continue
            matrices_of_relational_matrices = list(
                itertools.product(matrices_of_relational_matrices, self.relation_matrices[relation_key]))
        # print("MATRICES OF RELATIONAL MATRICES: ",matrices_of_relational_matrices)

        matrices_of_constraint_matrices = []  # seznam hrani vse mozne nabore matrik omejitvenih matrik
        first = True
        for relation_key in constraint_matrices_keys:
            if first:
                matrices_of_constraint_matrices += self.constraint_matrices[relation_key]
                first = False
                continue
            matrices_of_constraint_matrices = list(
                itertools.product(matrices_of_constraint_matrices, self.constraint_matrices.values[relation_key]))
        # print("MATRICES OF CONSTRAINT MATRICES: ", matrices_of_constraint_matrices)

        # ustvarimo po eno zlivanje oz. latentni podatkovni model za vsako od kombinacij relacijskih in omejitvenih matrik
        if len(matrices_of_constraint_matrices) > 0:
            fusion_sets = list(itertools.product(matrices_of_relational_matrices, matrices_of_constraint_matrices))
        else:
            fusion_sets = [(x, ()) for x in matrices_of_relational_matrices]

        self.object_types_in_fusion_scheme = set()
        self.fusion_sets = []
        #self.fusion_graphs = []
        fusion_set_counter = 0
        print("\t#Pripravljam grafe za zlivanje..")
        for fusion_set in fusion_sets:
            fusion_set_counter += 1
            print("\t\t\t ( " + str(fusion_set_counter) + ' / ' + str(len(fusion_sets)) + " ) Pripravljam graf..")

            relations = []
            fusion_set_tmp = {}
            # print("FUSION SET: ")
            # print("\tRELATIONAL MATRICES:")
            relational = fusion_set[0]
            for i in range(len(self.relation_matrices)):
                # print("\t\t"+relational_matrices_keys[-i-1])
                if i == len(self.relation_matrices) - 1:
                    relational_matrix = np.array(relational)
                else:
                    relational_matrix = np.array(relational[-1])
                # print("\t\t",relational_matrix.shape)
                # print(relational_matrix)
                relational = relational[0]
                related_objects = relational_matrices_keys[-i - 1].split(' ')
                # print("RELATED OBJECTS",related_objects)
                self.object_types_in_fusion_scheme.add(related_objects[0])
                self.object_types_in_fusion_scheme.add(related_objects[1])
                fusion_set_tmp[related_objects[0] + ' ' + related_objects[1]] = (
                relational_matrix, self.object_types_fusion[related_objects[0]],
                self.object_types_fusion[related_objects[1]])
                relations.append(fusion.Relation(relational_matrix, self.object_types_fusion[related_objects[0]],
                                                 self.object_types_fusion[related_objects[1]]))
            # print("\tCONSTRAINT MATRICES:")
            constraint = fusion_set[1]
            for i in range(len(self.constraint_matrices)):
                # print("\t\t" + constraint_matrices_keys[-i-1])
                if i == len(self.constraint_matrices) - 1:
                    constraint_matrix = np.array(constraint)
                else:
                    constraint_matrix = np.array(constraint[-1])
                # print("\t\t",constraint_matrix.shape)
                # print(constraint_matrix)
                constraint = constraint[0]
                related_objects = constraint_matrices_keys[-i - 1]
                self.object_types_in_fusion_scheme.add(related_objects)
                fusion_set_tmp[related_objects + ' ' + related_objects] = (
                constraint_matrix, self.object_types_fusion[related_objects], self.object_types_fusion[related_objects])
                relations.append(fusion.Relation(constraint_matrix, self.object_types_fusion[related_objects],
                                                 self.object_types_fusion[related_objects]))
            self.fusion_sets.append(fusion_set_tmp)
            # Build new fusion graph
            fusion_graph = fusion.FusionGraph()
            fusion_graph.add_relations_from(relations)
            yield  fusion_graph
            #self.fusion_graphs.append(fusion_graph)


    def list_latent_data_models(self):
        print("***Izpisujem podatke o grafih v latentnem prostoru")
        for x in range(len(self.latent_data_models)):
            print("\tMODEL #"+str(x))
            print("\t\t\tOBJEKTNI TIPI", self.latent_data_models[x].object_types)
            print("\t\t\tFAKTORJI:")
            for object_type in self.object_types_in_fusion_scheme:
                print('\t\t\t\t\t'+object_type+' shape:  ',self.latent_data_models[x].factor(self.object_types_fusion[object_type]).shape)
            print("\t\t\tRELACIJE", self.latent_data_models[x].relations)

    def display_database_erm(self,host,database,user,password):
        url='postgresql://'+user+':'+password+'@'+host+'/'+database
        print(url)
        output_file="ERD_"+host+"_"+database+".png"
        render_er(url,output_file)
        imgplot = plt.imshow(mpimg.imread(output_file))
        plt.rcParams["figure.figsize"]=(15,10)
        plt.show()

    def order_relations_OT(self,ranked_relation_list,list_length=10):
        print("***Pripravljam rangiran seznam relacij..")
        #ranked_relation_list = self.rank_object_type_relations()
        print("\n\n\n\n\nRANGIRAN SEZNAM RELACIJ:\n")
        i = 1
        for relation, score in ranked_relation_list:
            if i==list_length:
                break
            '''if score>=9999999999:
                break'''
            print("%5d. %s\t(%d)\n" % (i, relation, score))
            i += 1


    def score_relation_reconstruction(self,relation_name,graph_before_fusion,graph_after_fusion):
        '''
            :param relation: name of a relation
            :return: score for a given relation name, that is calculated as a mean of relation matrix reconstruction accuracy
            across all models.
        '''
        '''
        Pomembno je izbrati metriko razdalje, ki ne preferira matrik manjsih dimenzij
        '''
        relation_object_types_names=relation_name.split(' ')
        object_type1 = [x for x in graph_before_fusion.object_types.keys() if x.name==relation_object_types_names[0]][0]
        object_type2 = [x for x in graph_before_fusion.object_types.keys() if x.name==relation_object_types_names[1]][0]
        relation = [x for x in list(graph_before_fusion.relations.keys()) if x.__contains__(object_type1) and x.__contains__(object_type2)][0]
        original_matrix=relation.data
        '''object_type1_latent_matrix = graph_after_fusion.factor(object_type1)
        object_type2_latent_matrix = graph_after_fusion.factor(object_type2)
        latent_space_matrix = object_type1_latent_matrix.dot(object_type2_latent_matrix.T)'''
        latent_space_matrix=graph_after_fusion.complete(relation)
        original_matrix_vector = original_matrix.reshape(1, original_matrix.shape[0] * original_matrix.shape[1])
        latent_space_matrix_vector = latent_space_matrix.reshape(1, latent_space_matrix.shape[0] * latent_space_matrix.shape[1])
        if np.isnan(original_matrix).any():
            # Failsafe - Zakaj so vcasih vrednosti nan?
            print("\t\t\t\t\t\t\t! V ORIGINALNI matriki se nahajajo NaN vrednosti!!")
            if np.isnan(original_matrix).all():
                print("\t\t\t\t\t\t\t! Vse vrednosti v ORIGINALNI matriki so NaN!!")
                return 999999999999999
        if np.isnan(latent_space_matrix).any():
            # Failsafe - Zakaj so vcasih vrednosti nan?
            print("\t\t\t\t\t\t\t! V LATENTNI matriki se nahajajo NaN vrednosti!!")
            if np.isnan(latent_space_matrix).all():
                print("\t\t\t\t\t\t\t! Vse vrednosti v LATENTNI matriki so NaN!!")
                return 999999999999999

        #distance = distance_library.euclidean(original_matrix_vector, latent_space_matrix_vector)
        #distance=np.sqrt(sum((original_matrix_vector[x]-latent_space_matrix_vector[x])**2 for x in range(len(latent_space_matrix_vector)) if not np.isnan(original_matrix_vector[x]) and not np.isnan(latent_space_matrix_vector[x])) / len(latent_space_matrix_vector))
        #RMSE razdalja se izracuna zgolj za tiste elemente, ki niso NaN
        distance=np.sqrt(sum([(original_matrix_vector[0][x]-latent_space_matrix_vector[0][x])**2 for x in range(len(latent_space_matrix_vector[0])) if not np.isnan(original_matrix_vector[0][x]) and not np.isnan(latent_space_matrix_vector[0][x])]) / np.count_nonzero(~np.isnan(original_matrix_vector[0])))
        return distance

    def fuse_data(self):
        '''
        https://github.com/marinkaz/scikit-fusion
        :return:
        '''
        print("***Zlivanje podatkov..")
        # Infer the latent data model for each fusion graph
        #self.latent_data_models = []
        object_type_relations = list(self.relation_matrices.keys())
        fusion_set_counter=0
        models_scores={}
        for graph in self.generate_fusion_graphs():
            fusion_set_counter+=1
            #print("\t\t\t ( " + str(fusion_set_counter) + ' / ' + str(len(self.generate_fusion_graphs())) + " )")
            print("\t\t\t\t\t ..zlivam graf..")
            fuser = fusion.Dfmf()
            fuser.fuse(graph)
            #self.latent_data_models.append(fuser)
            relation_scores={}
            relation_counter=1
            for relation in object_type_relations:
                print("\t\t\t\t\t( "+str(relation_counter)+" / "+str(len(object_type_relations))+" ) ..ocenjujem rekonstrukcijo relacije: ",relation)
                distance=self.score_relation_reconstruction(relation,graph,fuser)
                relation_scores[relation]=distance
                relation_counter+=1
            models_scores[fusion_set_counter]=relation_scores
        print("***Konec zlivanja!!")
        relation_scores_avg={}
        for relation in object_type_relations:
            sum=0
            for model in models_scores:
                sum+=models_scores[model][relation]
            relation_scores_avg[relation]=sum/len(models_scores)
        relation_scores_avg_list=[(x,relation_scores_avg[x]) for x in relation_scores_avg]
        relation_scores_avg_list.sort(key=lambda tup: tup[1])
        return  relation_scores_avg_list


    def __init__(self,host,database,user,password):
            cas_zacetka=datetime.now()
            self.postgres_to_python_data_types={'CHARACTER':'str', 'CHAR':'str', 'VARCHAR':'str', 'TEXT':'str', 'SMALLINT':'integer', "INTEGER":'integer', 'INT':'integer', 'SERIAL':'integer', 'FLOAT':'float', 'real':'float', 'float8':'float', 'numeric':'float','DATE':'datetime'}
            print('***Initcializacija..')
            self.join_outmost_tables_mode = False #Ce True se pred zlivanjem stolpci obrobnih tabel (brez 'izhodnih' tujih kljucev) prepisejo v tabele, ki jih referencirajo
            self.dummy_variable_treshold=0 #stevilo razlicnih vrednosti za kategoricne spremenljivke, pri katerih naj se se izvaja delitev na vec indikatorskih spremenljivk
            self.max_number_of_objects=self.estimate_relation_matrix_dimension_constraint()
            self.max_number_of_alternative_relation_matrices_to_use=10 #Omeji stevilo alternativnih relacijskih matrik, ki naj se upostevajo za relacijo med katerima koli objektnima tipoma (ce se preseze se matrike izbere z razlicnimi hevristikami)

            self.foreign_keys=None
            self.primary_keys=None
            self.modified_tables=None
            self.excluded_tables=None
            self.tables=None
            self.relation_matrices=None
            self.constraint_matrices=None
            self.object_types=None
            self.sample=None
            self.sample_tables=None

            #self.display_database_erm(host,database,user,password)
            self.connect_to_postgreSQL(host,database,user,password)
            self.get_column_data_types()
            self.restore_from_checkpoint(host,database)
            #self.get_column_data_types() #hitreje: pridobi podatkovne tipe samo za stoplpce v vmesnih tabelah
            self.list_tables()
            self.presampling_mode=True if self.estimate_complexity()>=3 else False
            self.list_key_constraints()
            self.list_object_types()
            self.list_connected_tables()
            self.list_tables_gte2_fk()
            if self.join_outmost_tables_mode:
                self.join_outmost_tables()
            #self.get_column_data_types_tables_gte2_fk()
            self.filter_columns_fusion()
            if self.presampling_mode:
                self.presample()
            #print("tabele gte2 fk: ", self.tables_gte2_fk)
            #print("vrste stolpcev v tabelah gte2 fk: ",self.column_data_type)
            #print("columns fusion: ",self.column_fusion)
            self.build_relation_matricies()
            self.limit_relation_matrices_number()
            relation_scores=self.fuse_data()
            #self.latent_data_models
            self.order_relations_OT(relation_scores)
            self.checkpoint_file.close()
            cas_konca=datetime.now()
            print("\n\n\n===== Postopek je trajal:\t",cas_konca-cas_zacetka)



if __name__ == "__main__":
    fuse = Fuse(host='192.168.217.128', database='avtomobilizem1', user='postgres', password='geslo123')
    #fuse = Fuse(host='192.168.217.128', database='parameciumdb', user='postgres', password='geslo123')
