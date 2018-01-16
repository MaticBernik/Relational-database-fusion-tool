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

        print("###COMPLEX: ",complex_sum)
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


    def restore_from_checkpoint(self,host,database):
        '''
            Load data from existing checkpoint file for specified database connection,
            or create new (empty) checkpoint file.
        :param host:
        :param database:
        :return:
        '''
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

        for line in self.checkpoint_file:
            if line in ['\n', '\r\n']:
                print("###..konec")
                foreign_key_section=False
                primary_key_section = False
                excluded_tables_section=False
                modified_tables_section=False
                tables_section=False
                relation_matrices_section = False
                constraint_matrices_section = False
                object_types_section = False
                continue
            elif "#FOREIGN KEYS" in line:
                print("###Nalagam seznam tujih kljucev..")
                self.foreign_keys=[]
                foreign_key_section=True
                continue
            elif "#PRIMARY KEYS" in line:
                print("###Nalagam seznam primarnih kljucev..")
                self.primary_keys=[]
                primary_key_section=True
                continue
            elif "#EXCLUDED TABLES LIST" in line:
                print("###Nalagam seznam izlocenih tabel..")
                self.excluded_tables=[]
                excluded_tables_section=True
                continue
            elif "#MODIFIED TABLES LIST" in line:
                print("###Nalagam seznam modificiranih tabel..")
                self.modified_tables={}
                modified_tables_section=True
                key_next=True
                continue
            elif "#TABLES" in line:
                print("###Nalagam seznam tabel...")
                self.tables=[]
                tables_section=True
                continue
            elif "#RELATION MATRICES" in line:
                print("###Nalagam seznam relacijskih matrik...")
                self.relation_matrices={}
                relation_matrices_section = True
                key_next=True
                continue
            elif "#CONSTRAINT MATRICES" in line:
                print("###Nalagam seznam omejitvenih matrik...")
                self.constraint_matrices={}
                constraint_matrices_section = True
                key_next=True
                continue
            elif "#OBJECT TYPES" in line:
                print("###Nalagam seznam objektnih tipov...")
                self.object_types=[]
                object_types_section=True
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
                if line=='!':
                    key_next=True
                    if key_name and len(data)>0:
                        if key_name not in  self.relation_matrices:
                            self.relation_matrices[key_name]=[]
                        self.relation_matrices[key_name].append(np.array(data))
                elif key_next:
                    key_name=line
                    data=[]
                    key_next=False
                else:
                    data.append([float(x) for x in line.split("\t")])
            elif constraint_matrices_section:
                if line=='!':
                    key_next=True
                    if key_name and len(data)>0:
                        if key_name not in self.constraint_matrices:
                            self.constraint_matrices[key_name]=[]
                        self.constraint_matrices[key_name].append(np.array(data))
                elif key_next:
                    key_name=line
                    data=[]
                    key_next=False
                else:
                    data.append([float(x) for x in line.split("\t")])
            elif object_types_section:
                self.object_types.append(line.split("\t"))

        self.checkpoint_file.seek(0, 2)

        '''print("FOREIGN KEYS: ",self.foreign_keys)
        print("EXCLUDED TABLES: ",self.excluded_tables)
        #print("MODIFIED TABLES: ",self.modified_tables)
        print("TABLES: ",self.tables)
        print("RELATION MATRICES: ",self.relation_matrices)
        print("CONSTRAINT MATRICES: ",self.constraint_matrices)'''

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
            self.cursor.execute("SELECT tc.constraint_name, tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name FROM information_schema.table_constraints AS tc JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name WHERE constraint_type = 'FOREIGN KEY' AND tc.table_name = '" + table_name + "';")
            foreign_keys_tmp = self.cursor.fetchall()
            foreign_keys += foreign_keys_tmp
            self.cursor.execute("SELECT '"+table_name+"', a.attname, format_type(a.atttypid, a.atttypmod) AS data_type FROM   pg_index i JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE  i.indrelid = '"+table_name+"'::regclass AND    i.indisprimary;")
            primary_keys_tmp = self.cursor.fetchall()
            primary_keys+=primary_keys_tmp
        #return foreign_keys
        #foreign_keys=[x for x in foreign_keys if '_fkey' in x[0]]
        self.foreign_keys=foreign_keys
        self.primary_keys=primary_keys
        #print(foreign_keys)

        #save foreign keys to file
        self.checkpoint_file.write("#FOREIGN KEYS\n")
        for key in self.foreign_keys:
            self.checkpoint_file.write('\t'.join(key)+"\n")
        self.checkpoint_file.write("\n")
        #save primary_keys to file
        self.checkpoint_file.write("#PRIMARY KEYS\n")
        for key in self.primary_keys:
            self.checkpoint_file.write('\t'.join(key) + "\n")
        self.checkpoint_file.write("\n")


    def list_connected_tables(self):
        '''
        Lists all foreign key connections between pairs of tables.
        :return:
        sets object variable table_relations as a list of tuples.
        Each tuple contains ordred pair of table names, indicating that table at index 0 references table at index 1.
        '''
        self.table_relations = list(set([(x[1],x[3]) for x in self.foreign_keys])) #usmerjene povezave med tabelami (tabela1,tabela2) --> tabela1 je prek tujega kljuca povezana s tabelo2


    def list_tables_gte2_fk(self):
        '''
        List all tables, that reference at least 2 other tables via foreign keys.
        '''
        print("***Iskanje tabel, ki preko tujih kljucev referencirajo vsaj 2 razlicni tabeli...")
        self.tables_nr_fk=Counter([x[0] for x in self.table_relations]) #stevilo povezav na ostale tabele
        self.tables_gte2_fk=[x for x in self.tables_nr_fk if self.tables_nr_fk[x]>=2]


    def get_column_data_types(self):
        '''
        For every data table in database lists all column and data type it holds.
        As a result it sets an object variable with dictionary where each entry has form
        id: (column,data_type) ; where:
            id - key string formed as table name joined with column name using underscore character
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

    def join_outmost_tables(self):
        '''
        Function 'recursively' finds outmost tables with no foreign keys and joins their columns to tables that reference them.
        As a result:
            -table excluded_tables contains a list of names of tables that have been joined and therefore shuld be excluded from further processing.
            -dictionary modified_tables contains modified tables (with aditional columns from joined tables) that shuld be used for further work instead of original tables within a database.
        '''
        print("***pridruzevanje zunanjih tabel...")
        #print(self.excluded_tables)
        #print(self.modified_tables)
        if not self.excluded_tables==None and not self.modified_tables==None:
            return


        self.excluded_tables=[]
        self.modified_tables={}
        tables_to_modify=[]

        #find tables with no foreign keys
        for t in self.tables:
            table_name = t[1]
            if not table_name in [x[1] for x in self.foreign_keys]:
                for x in self.foreign_keys:
                    if x[3]==table_name:
                        #find all foreign key constraints that connect another table to this table
                        #print("foreign key: ",x)
                        #print("list(fk): ",[x])
                        tables_to_modify.append([x])
                self.excluded_tables.append(table_name)

        tables_to_join_exist=True
        while tables_to_join_exist:
            tables_to_modify_tmp=[]
            for t in tables_to_modify:
                #iterate trough all 'chains' of FK constraint connecting any table to outmost table (without FK constraints)
                last_link=t[len(t)-1]
                last_table=last_link[1]
                last_table_nr_connected_tables=len(set([x for x in self.foreign_keys if x[1] == last_table]))
                #check how many tables there are that are connected to any 'chain' via FK constraint
                if last_table_nr_connected_tables > 1:
                    #tables referencing other tables can not be joined
                    tables_to_join_exist = False
                    tables_to_modify_tmp.append(t)
                    continue
                table_connections = [x for x in self.foreign_keys if x[3] == last_table]
                ##find all foreign key constraints that connect another table to this 'chain'
                if len(table_connections)==0:
                    tables_to_join_exist=False
                    tables_to_modify_tmp.append(t)
                else:
                    for c in table_connections:
                        #create new chain for every possible new link at the end of current chain
                        t_tmp=[x for x in t]
                        tables_to_modify_tmp.append(t_tmp.append(c))
                    self.excluded_tables.append(last_table)
            tables_to_modify=tables_to_modify_tmp

        for t in tables_to_modify:
            #print(t)
            sql_query="SELECT * FROM"
            last_link=t[len(t)-1]
            key=last_link[1]
            first=True
            for c in t:
                #print("C: ",c)
                if first:
                    sql_query+=" "+c[1]+" INNER JOIN "+c[3]+" ON "+c[1]+"."+c[2]+" = "+c[3]+"."+c[4]
                    first=False
                    continue
                sql_query+=" INNER JOIN "+c[1]+" ON "+c[1]+"."+c[2]+" = "+c[3]+"."+c[4]
            sql_query+=';'
            self.cursor.execute(sql_query)
            joined_table=self.cursor.fetchall()
            # REMOVE COLUMNS THAT ARE NOT SUITABLE FOR FUSION
            self.modified_tables[key]=joined_table

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
        numerical_data_types=['smallint','integer','bigint','decimal','numeric','real','double precision','smallserial','serial','bigserial']
        column_fusion={}
        fk_ids=[id[0] for id in self.foreign_keys]
        for c_id in self.column_data_type:
            if not c_id in fk_ids and self.column_data_type[c_id][1] in numerical_data_types:
                column_fusion[c_id]=self.column_data_type[c_id]
        self.column_fusion=column_fusion

    def gen_matrices_for_column(self,table1,table2,table,column_id):
        '''
        :param table1:
        :param table2:
        :param table:
        :param column_id:
        :return:list of relational matrices.
        Only 1 matrix if binarization of attribute(column_id) is not required.
        '''
        matrices=[]
        print("***Generiranje matrik za stolpec vmesne matrike..")
        objects_table1 = self.get_object_ids(table1)
        objects_table2 = self.get_object_ids(table2)
        # print("OBJECTS TABLE 1 ",objects_table1)
        # print("OBJECTS TABLE 2 ",objects_table2)
        table_table1_fk=[x for x in self.foreign_keys if x[1]==table and x[3]==table1]
        table_table2_fk=[x for x in self.foreign_keys if x[1]==table and x[3]==table2]

        if len([x for x in self.primary_keys if x[0]==table1])<len(table_table1_fk) or len([x for x in self.primary_keys if x[0]==table2])<len(table_table2_fk):
            print("###PROBLEM: ocitno sta tabeli povezani preko vecih sklopov stolpcev/kljucev!! - REZULTAT NE BO 'OPTIMALEN'")
            print("###SANITY CHECK: Je st. tujih kljucev veckratnik stevila stolpcev primarnega kljuca? ")
            print(str(len(table_table1_fk))+' = n * '+str(len([x for x in self.primary_keys if x[0]==table1]))+"???  ---> ",len(table_table1_fk)%len([x for x in self.primary_keys if x[0]==table1])==0)
            print(str(len(table_table2_fk))+' = n * '+str(len([x for x in self.primary_keys if x[0]==table2]))+"???  ---> ",len(table_table2_fk)%len([x for x in self.primary_keys if x[0]==table2])==0)

        if len(objects_table1[1]) == 0 or len(objects_table2[1]) == 0:
            return []

        print("SELECT "+', '.join(x[3]+'.'+x[4] for x in table_table1_fk)+', '+', '.join(x[3]+'.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table1+" INNER JOIN "+table+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table1_fk])+" INNER JOIN "+table2+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table2_fk])+';')
        self.cursor.execute("SELECT "+', '.join(x[3]+'.'+x[4] for x in table_table1_fk)+', '+', '.join(x[3]+'.'+x[4] for x in table_table2_fk)+', '+table+'.'+column_id+" FROM "+table1+" INNER JOIN "+table+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table1_fk])+" INNER JOIN "+table2+" ON "+' AND '.join([x[1]+'.'+x[2]+' = '+x[3]+'.'+x[4] for x in table_table2_fk])+';')
        rows=self.cursor.fetchall()
        #print(rows)

        nr_columns=1
        print("PODATKOVNI TIP STOLPCA: ",self.column_data_type[table + ' ' + column_id])
        if self.column_data_type[table+' '+column_id][1]=="str":
            if len(set(rows[:,-1]))>self.dummy_variable_treshold:
                print("###Stolpec "+table+"."+column_id+" ima prevec razlicnih vrednosti za razbitje na mnozico indikatorskih spremenljivk.")
                return []
            labelencoder=LabelEncoder()
            rows[:,-1]=labelencoder.fit_transform(rows[:,-1])
            nr_columns=len(labelencoder.classes_)
            onehotencoder = OneHotEncoder(categorical_features=[-1])
            rows=onehotencoder.fit_transform(rows).toarray()
            #dummy variable trap?
            print(rows)
            #move dummy variables from begining to end of table!

        for i in range(nr_columns):
            R=np.zeros((len(objects_table1[1]),len(objects_table2[1])))
            matrices.append(R)
        for row in rows:
            #print(row)
            c1=tuple(row[0:len(objects_table1[0])])
            c2=tuple(row[len(objects_table1[0]):-nr_columns])
            v=row[-nr_columns:]
            for i in range(nr_columns):
                matrices[i][objects_table1[1].index(c1)][objects_table2[1].index(c2)]=v[i]
        return matrices

    def get_object_ids(self,table):
        '''
        Get list of unique combinations of values for columns representing (composite) primary key.
        Returns list with header(tuple of ordered column names) at index 0 and list of different value combinations (tuples) at index 1.
        '''
        pk_columns = [x[1] for x in self.primary_keys if x[0]==table]
        self.cursor.execute("SELECT "+','.join(pk_columns)+" FROM "+table+";")
        #print("SELECT "+','.join(pk_columns)+" FROM "+table+";")
        rows=list(set(self.cursor.fetchall()))
        return [pk_columns,rows]

    def gen_indicator_matrix_for_relation(self,table1,table2):
        '''
        For two tables related via Foreign Key constraint create matrix of dimensions |objects in table1| x |objects in table2|,
        that has 1 in every cell for actually related objects and 0 elsewhere.
        :param table1:
        :param table2:
        :return:
        '''
        objects_table1=self.get_object_ids(table1)
        objects_table2=self.get_object_ids(table2)
        #print("OBJECTS TABLE 1 ",objects_table1)
        #print("OBJECTS TABLE 2 ",objects_table2)
        table_relations=[x for x in self.foreign_keys if x[1]==table1 and x[3]==table2]

        if len(objects_table1[1]) == 0 or len(objects_table2[1]) == 0:
            return []
        R = np.zeros((len(objects_table1[1]), len(objects_table2[1])))
        #fill in 1s
        header_fk_tmp=[]
        for x in objects_table2[0]:
            for y in table_relations:
                if y[3]==table2 and y[4]==x:
                    header_fk_tmp.append(y[2])
        if table1==table2:
            #print("SELECT "+",".join(objects_table1[0])+','+",".join(header_fk_tmp)+" FROM "+table1+";")
            #self.cursor.execute("SELECT "+",".join(objects_table1[0])+','+",".join(header_fk_tmp)+" FROM "+table1+";")
            self.cursor.execute("SELECT "+",".join(["a."+x for x in objects_table1[0]])+','+",".join("b."+x for x in objects_table2[0])+" FROM "+table1+" as a INNER JOIN "+table2+" as b ON "+" AND ".join(["a."+x[2]+" = "+"b."+x[4] for x in table_relations])+";")
        else:
            #print("SELECT "+",".join([table1+"."+x for x in objects_table1[0]])+','+",".join(table2+"."+x for x in objects_table2[0])+" FROM "+table1+" INNER JOIN "+table2+" ON "+" AND ".join([x[1]+"."+x[2]+" = "+x[3]+"."+x[4] for x in table_relations])+";")
            self.cursor.execute("SELECT "+",".join([table1+"."+x for x in objects_table1[0]])+','+",".join(table2+"."+x for x in objects_table2[0])+" FROM "+table1+" INNER JOIN "+table2+" ON "+" AND ".join([x[1]+"."+x[2]+" = "+x[3]+"."+x[4] for x in table_relations])+";")
        lines=self.cursor.fetchall()
        for line in lines:
            #print("LINE ",line)
            object1_id=tuple(line[0:len(objects_table1[0])])
            #print("O1ID: ",object1_id)
            object2_id=tuple(line[len(objects_table1[0]):])
            #print("O2ID: ",object2_id)
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
        for t in tables:
            tables_linked_to_t=[y for x,y in self.table_relations if x==t]
            if len(tables_linked_to_t)>=2:
                #Zgradi relacijske matrike za posredno povezane tabele.
                #self.tables_object_types+=tables_linked_to_t
                for t1,t2 in itertools.combinations(tables_linked_to_t,2):
                    #print("T1: ",t1,"T2: ",t2)
                    for c in [x for x in self.column_fusion if t+' ' in x]:
                        # Kaj narediti v primeru, ko na neko tabelo kaze vec tujih kljucev??!! Vrstice so lahko medsebojno drugace povezane? Se ena gnezdena zanka?
                        # Posebej problematicni primer: tabela1 referencira tabelo 2, ki ima primarni kljuc sestavljen iz vecih stolpcev preko vec kot enega samega sklopa stolpcev..
                        # npr. orodje preko enega sklopa stolpcev referencira drzavo prodaje, preko drugega pa drzavo izdelave. Ce pa je PK tabele drzava sestavljen iz vec kot enega stolpca, kako lociti??
                        c=c[len(t+' '):]
                        matrices=self.gen_matrices_for_column(t1,t2,t,c)
                        if not t1+' '+t2 in relation_matrices:
                            relation_matrices[t1 + ' ' + t2] = []
                        relation_matrices[t1+' '+t2]+=matrices
            if len(tables_linked_to_t)>=1:
                #Zgradi relacijske matrike za vsako direktno povezavo obravnavane tabele.
                #SE OMEJITVENA MATRIKA SME POJAVITI TUDI MED RELACIJSKIMI???
                for t1 in tables_linked_to_t:
                    matrices=self.gen_indicator_matrix_for_relation(t,t1)
                    if t==t1:
                        if not t in constraint_matrices:
                            constraint_matrices[t] = []
                        constraint_matrices[t] += matrices
                    else:
                        if not t + ' ' + t1 in relation_matrices:
                            relation_matrices[t + ' ' + t1] = []
                        relation_matrices[t + ' ' + t1] += matrices

            '''if t in tables_linked_to_t:
                #Kadar tabela referencira samo sebe, zgradi se omejitveno matriko
                for c in [x for x in self.column_fusion if t + '_' in x]:
                    c = c[len(t + '_'):]
                    foreign_keys = [x for x in self.foreign_keys if x[1] == t and x[3] == t]
                    for foreign_key in foreign_keys:
                        matrices=self.gen_matrices_for_column(foreign_key,foreign_key,t,c)
                    if not t in constraint_matrices:
                        constraint_matrices[t]=[]
                    constraint_matrices[t]+=matrices'''

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
        self.checkpoint_file.write("\n")

        self.checkpoint_file.write("#CONSTRAINT MATRICES\n")
        for key in self.constraint_matrices:
            self.checkpoint_file.write(key + "\n")
            for t in self.constraint_matrices[key]:
                for line in t:
                    self.checkpoint_file.write("\t".join([str(x) for x in line]) + "\n")
                self.checkpoint_file.write("!\n")
        self.checkpoint_file.write("\n")


    def presample(self):
        '''
        Try different sampling methods to downsize tables.
        !!!!!
        PROBLEM: ROWS REFERENCED FROM SAMPLED TABLE1 SHOULD BE INCLUDED IN SAMPLE REPRESENTING TABLE2

        Should ratio between table sizes be preserved??
        :return:
        '''
        pass

    def fuse_data(self):
        '''
        https://github.com/marinkaz/scikit-fusion
        :return:
        '''
        print("***Zlivanje podatkov..")
        object_types={}
        relational_matrices_keys=list(self.relation_matrices.keys())
        constraint_matrices_keys=list(self.constraint_matrices.keys())

        print('OBJEKTNI TIPI: ',self.object_types)
        for type_name in self.object_types:
            object_types[type_name]=fusion.ObjectType(type_name)

        matrices_of_relational_matrices=[] #seznam hrani vse mozne nabore matrik relacijskih matrik
        first=True
        for relation_key in relational_matrices_keys:
            if first:
                matrices_of_relational_matrices+=self.relation_matrices[relation_key]
                first=False
                continue
            matrices_of_relational_matrices = list(itertools.product(matrices_of_relational_matrices, self.relation_matrices[relation_key]))
        print("MATRICES OF RELATIONAL MATRICES: ",matrices_of_relational_matrices)

        matrices_of_constraint_matrices = []  # seznam hrani vse mozne nabore matrik omejitvenih matrik
        first = True
        for relation_key in constraint_matrices_keys:
            if first:
                matrices_of_constraint_matrices += self.constraint_matrices[relation_key]
                first = False
                continue
            matrices_of_constraint_matrices = list(itertools.product(matrices_of_constraint_matrices, self.constraint_matrices.values[relation_key]))
        print("MATRICES OF CONSTRAINT MATRICES: ", matrices_of_constraint_matrices)

        #ustvarimo po eno zlivanje oz. latentni podatkovni model za vsako od kombinacij relacijskih in omejitvenih matrik
        if len(matrices_of_constraint_matrices)>0:
            self.fusion_sets=list(itertools.product(matrices_of_relational_matrices,matrices_of_constraint_matrices))
        else:
            self.fusion_sets=[(x,()) for x in matrices_of_relational_matrices]

        self.fusion_graphs=[]
        for fusion_set in self.fusion_sets:
            relations = []
            print("FUSION SET: ")
            print("\tRELATIONAL MATRICES:")
            relational=fusion_set[0]
            for i in range(len(self.relation_matrices)):
                print("\t\t"+relational_matrices_keys[-i-1])
                if i==len(self.relation_matrices)-1:
                    relational_matrix=np.array(relational)
                else:
                    relational_matrix=np.array(relational[-1])
                print("\t\t",relational_matrix.shape)
                print(relational_matrix)
                relational=relational[0]
                related_objects=relational_matrices_keys[-i-1].split(' ')
                relations.append(fusion.Relation(relational_matrix,object_types[related_objects[0]],object_types[related_objects[1]]))
            print("\tCONSTRAINT MATRICES:")
            constraint = fusion_set[1]
            for i in range(len(self.constraint_matrices)):
                print("\t\t" + constraint_matrices_keys[-i-1])
                if i==len(self.constraint_matrices)-1:
                    constraint_matrix=np.array(constraint)
                else:
                    constraint_matrix=np.array(constraint[-1])
                print("\t\t",constraint_matrix.shape)
                print(constraint_matrix)
                constraint = constraint[0]
            #Build new fusion graph
            fusion_graph = fusion.FusionGraph()
            fusion_graph.add_relations_from(relations)
            self.fusion_graphs.append(fusion_graph)

        #Infer the latent data model for each fusion graph
        self.latent_data_models=[]
        for graph in self.fusion_graphs:
            fuser = fusion.Dfmf()
            fuser.fuse(graph)
            self.latent_data_models.append(fuser)

    def __init__(self,host,database,user,password):
            print('***Initcializacija..')
            self.join_outmost_tables_mode = False #Ce True se pred zlivanjem stolpci obrobnih tabel (brez 'izhodnih' tujih kljucev) prepisejo v tabele, ki jih referencirajo
            self.dummy_variable_treshold=20 #stevilo razlicnih vrednosti za kategoricne spremenljivke, pri katerih naj se se izvaja delitev na vec indikatorskih spremenljivk

            self.foreign_keys=None
            self.primary_keys=None
            self.modified_tables=None
            self.excluded_tables=None
            self.tables=None
            self.relation_matrices=None
            self.constraint_matrices=None
            self.object_types=None

            self.connect_to_postgreSQL(host,database,user,password)
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
            self.get_column_data_types()
            self.filter_columns_fusion()
            if self.presampling_mode:
                self.presample()
            #print("tabele gte2 fk: ", self.tables_gte2_fk)
            #print("vrste stolpcev v tabelah gte2 fk: ",self.column_data_type)
            #print("columns fusion: ",self.column_fusion)
            self.build_relation_matricies()
            self.fuse_data()
            self.checkpoint_file.close()


if __name__ == "__main__":
    fuse = Fuse(host='192.168.217.128', database='avtomobilizem', user='postgres', password='geslo123')
    #fuse = Fuse(host='192.168.217.128', database='parameciumdb', user='postgres', password='geslo123')
