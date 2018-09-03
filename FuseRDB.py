# !/usr/bin/python
# -*- coding: utf-8 -*-

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sys
import numpy as np
from collections import Counter
import itertools
from skfusion import fusion
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
import random
import psutil
# from eralchemy import render_er #https://github.com/Alexis-benoist/eralchemy
# import matplotlib.pyplot as plt
# import matplotlib.image as mpimg
from datetime import datetime
import os
import gc
import time

'''
#https://github.com/18F/rdbms-subsetter
#pip install rdbms-subsetter
https://github.com/18F/rdbms-subsetter/commit/dab67ab8638c27467dedf80c172c43a59da68ca8#comments
https://www.bountysource.com/issues/51999953-importerror-while-running-rdbms-subsetter
You need to copy the dialects folder of this project to your python site-packages folder.
--->
V mojem primeru sem kopiral mapo dialects v direktorij /usr/local/lib/python3.5/dist-packages/
'''


class FuseRDB():
    @staticmethod
    def is_numeric_data_type(data_type):
        numeric_data_types = ['bigint', 'integer', 'smallint', 'int', 'serial', 'float', 'real', 'float8', 'numeric']
        if data_type.lower() in numeric_data_types:
            return True
        else:
            return False

    @staticmethod
    def is_text_data_type(data_type):
        text_data_types = ['character', 'char', 'varchar', 'text']
        if data_type.lower() in text_data_types:
            return True
        else:
            return False

    def set_database_connection(self):
        self.database_active_connection = self.connect_to_postgreSQL(
            host=self.database_connection_credential_active['host'],
            database=self.database_connection_credential_active['database'],
            user=self.database_connection_credential_active['user'],
            password=self.database_connection_credential_active['password'])
        self.refresh_active_database_metadata()

    @staticmethod
    def connection_string_to_credentials(connection_string):
        credential = {'connection_string': connection_string, 'user': None, 'password': None, 'host': None,
                      'database': None}

        credential['connection_string'] = connection_string
        connection_string = connection_string[connection_string.index('//') + 2:]
        credential['user'] = connection_string[:connection_string.index(':')]
        database_connection = connection_string[connection_string.index(':') + 1:]
        credential['password'] = database_connection[:database_connection.index('@')]
        database_connection = database_connection[database_connection.index('@') + 1:]
        credential['host'] = database_connection[:database_connection.index('/')]
        if '/' in connection_string:
            database_connection = database_connection[database_connection.index('/') + 1:]
            credential['database'] = database_connection.lower()
        return credential

    def set_database_connection_credential(self, database_connection):
        '''
        Prvic se nastavi podatke osnovne baze,
        Naslednjic se spreminja le se aktivna baza.
        :param database_connection:
        :return:
        '''
        if self.database_connection_credential_base['connection_string'] is None:
            if '//' in database_connection:
                credential = self.connection_string_to_credentials(database_connection)
                self.database_connection_credential_base['connection_string'] = credential['connection_string']
                self.database_connection_credential_base['user'] = credential['user']
                self.database_connection_credential_base['password'] = credential['password']
                self.database_connection_credential_base['host'] = credential['host']
                self.database_connection_credential_base['database'] = credential['database']
            else:
                self.database_connection_credential_base['host'] = database_connection['host']
                self.database_connection_credential_base['database'] = database_connection['database']
                self.database_connection_credential_base['user'] = database_connection['user']
                self.database_connection_credential_base['password'] = database_connection['password']
                self.database_connection_credential_base['connection_string'] = \
                    self.database_connection_credential_base[
                        'database_system'] + '//' + \
                    self.database_connection_credential_base['user'] + ':' + \
                    self.database_connection_credential_base['password'] + '@' + \
                    self.database_connection_credential_base['host'] + '/' + \
                    self.database_connection_credential_base['database']
            if self.database_connection_credential_active['connection_string'] is None:
                self.database_connection_credential_active = self.database_connection_credential_base.copy()
        else:
            if '//' in database_connection:
                credential = self.connection_string_to_credentials(database_connection)
                self.database_connection_credential_active['connection_string'] = credential['connection_string']
                self.database_connection_credential_active['user'] = credential['user']
                self.database_connection_credential_active['password'] = credential['password']
                self.database_connection_credential_active['host'] = credential['host']
                self.database_connection_credential_active['database'] = credential['database']
            else:
                self.database_connection_credential_active['host'] = database_connection['host']
                self.database_connection_credential_active['database'] = database_connection['database']
                self.database_connection_credential_active['user'] = database_connection['user']
                self.database_connection_credential_active['password'] = database_connection['password']
                self.database_connection_credential_active['connection_string'] = \
                    self.database_connection_credential_active[
                        'database_system'] + '//' + \
                    self.database_connection_credential_active['user'] + ':' + \
                    self.database_connection_credential_active['password'] + '@' + \
                    self.database_connection_credential_active['host'] + '/' + \
                    self.database_connection_credential_active['database']
        self.set_database_connection()

    @staticmethod
    def connect_to_postgreSQL(host, database, user, password):
        '''
        Tries to establish a connection to (postgreSQL) database, specified by address of host machine, database name and user credentials.
        If connection fails program terminates.
        '''
        print("***Povezovanje na podatkovno bazo...")
        try:
            # con = psycopg2.connect(host='192.168.2.101', database='parameciumdb', user='postgres', password='geslo123')
            connection = psycopg2.connect(host=host, database=database, user=user, password=password)
            return connection
        except psycopg2.DatabaseError as e:
            print('Error %s' % e)
            sys.exit(1)

    def ignore_tables_no_rows(self):
        for key in list(self.active_database_meta['tables']):
            value=self.active_database_meta['tables'][key]
            if len(value['row_ids']) == 0:
                for fk_idx in range(len(self.active_database_meta['foreign_keys'])-1,0-1,-1):
                    fk=self.active_database_meta['foreign_keys'][fk_idx]
                    if key in fk[1] or key in fk[3]:
                        del self.active_database_meta['foreign_keys'][fk_idx]
                del self.active_database_meta['tables'][key]

    def refresh_active_database_metadata(self):
        connection = self.database_active_connection
        cursor = connection.cursor()

        # FOREIGN KEYS
        cursor.execute(
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
        foreign_keys = cursor.fetchall()
        self.active_database_meta['foreign_keys'] = foreign_keys  # !!!!

        # TABLE NAMES
        cursor.execute("SELECT tablename FROM pg_catalog.pg_tables where schemaname = 'public'")
        tables = [t[0] for t in cursor.fetchall()]
        for table in tables:
            self.active_database_meta['tables'][table] = {'columns': {}, 'column_name_PK': [],
                                                          'is_associative_entity': None, 'is_object_type': True,
                                                          'row_ids': []}

            # PRIMARY KEYS
            '''
            self.cursor.execute(
                "SELECT '" + table + "', a.attname, format_type(a.atttypid, a.atttypmod) AS data_type FROM   pg_index i JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE  i.indrelid = '" + table + "'::regclass AND    i.indisprimary;")
            '''
            cursor.execute(
                "SELECT a.attname FROM   pg_index i JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE  i.indrelid = '" + table + "'::regclass AND    i.indisprimary;")
            primary_keys = [c[0] for c in cursor.fetchall()]
            self.active_database_meta['tables'][table]['column_name_PK'] = primary_keys
            # ASSOCIATIVE ENTITY?
            self.active_database_meta['tables'][table]['is_associative_entity'] = True if set(primary_keys).issubset(
                set([c[2] for c in self.active_database_meta['foreign_keys'] if c[1] == table])) else False
            # COLUMNS
            cursor.execute(
                "SELECT column_name,data_type FROM information_schema.columns WHERE table_name = '" + table + "';")
            columns = cursor.fetchall()
            for column, column_data_type in columns:
                cursor.execute('SELECT COUNT (DISTINCT ' + column + ') FROM ' + table + ';')
                unique_values = cursor.fetchone()[0]
                self.active_database_meta['tables'][table]['columns'][column] = {'data_type': column_data_type,
                                                                                 'is_PK': True if column in primary_keys else False,
                                                                                 'is_FK': True if column in [f[2] for f
                                                                                                             in
                                                                                                             foreign_keys
                                                                                                             if f[
                                                                                                                 1] == table] else False,
                                                                                 'unique_values': unique_values}
            # OBJECT ID
            cursor.execute("SELECT " + ','.join(primary_keys) + " FROM " + table + ";")
            rows = list(set(cursor.fetchall()))
            self.active_database_meta['tables'][table]['row_ids'] = rows
        self.ignore_tables_no_rows()

    def database_is_big(self):
        complex_sum = 0
        for table, data in self.active_database_meta['tables'].items():
            nr_columns = len(data['columns'])
            nr_rows = len(data['row_ids'])
            complex_sum += nr_columns * nr_rows
        # Mejo postavi glede na sistemske resurse
        if complex_sum >= 10000:
            return True
        else:
            return False

    def optimal_rows_fraction(self):
        '''
        Poisci par povezanih tabel z najvec vrsticami.
        Oceni, koliko ju moras zmanjsati (produkt stevila vrstic),
        da tako matriko lahko shranis v pomnilnik.
        :return:
        '''
        '''
        max_size = 1073741824  # bytes
        cell_size = 8  # bytes
        '''
        max_size=self.parameters['max_matrix_size']
        cell_size=1
        max_row_product = 0
        for fk in self.active_database_meta['foreign_keys']:
            table1 = fk[1]
            table2 = fk[3]
            table1_rows = len(self.active_database_meta['tables'][table1]['row_ids'])
            table2_rows = len(self.active_database_meta['tables'][table2]['row_ids'])
            if table1_rows * table2_rows > max_row_product:
                max_row_product = table1_rows * table2_rows

        return max_size / (max_row_product * cell_size)

    def minify_database(self):
        '''
        Naredi pomanjsano (vzorcenje) verzijo podatkovne baze database_connection_credential_base
        kot aktivno bazo
        :return:
        '''
        credentials = self.connection_string_to_credentials(
            self.database_connection_credential_active['connection_string'])
        db_name = credentials['database'] if credentials['database'] is not None else 'mini_' + \
                                                                                      self.database_connection_credential_base[
                                                                                          'database']
        # Create new DB if not exists
        print('CREATING DB..')
        con = psycopg2.connect(dbname='postgres',
                               user=credentials['user'], host=credentials['host'],
                               password=credentials['password'])
        con.autocommit = True
        # con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)  # <-- ADD THIS LINE
        cur = con.cursor()
        cur.execute(
            'select exists(SELECT datname FROM pg_catalog.pg_database WHERE lower(datname) = lower(\'' + db_name + '\'));')
        db_exists = cur.fetchone()[0]
        if not db_exists:
            cur.execute("CREATE DATABASE %s  ;" % db_name)
            con.commit()
        cur.close()
        con.close()
        print('DB CREATED')
        print('SETTING ACTIVE DB:', self.database_connection_credential_active['connection_string'] + '' if credentials[
                                                                                                                'database'] is not None else '/' + db_name)
        self.set_database_connection_credential(
            self.database_connection_credential_active['connection_string'] + '' if credentials[
                                                                                        'database'] is not None else '/' + db_name)
        print('DUMPING DB')
        schema_dump_file_name = self.database_connection_credential_base['database'] + '.sql'
        '''
        os.system('pg_dump --schema-only -C -Fc \'' + self.database_connection_credential_base[
            'connection_string'] + '\' > \'' + schema_dump_file_name + '\'')
        '''
        os.system('pg_dump --schema-only -Fc \'' + self.database_connection_credential_base[
            'connection_string'] + '\' > \'' + schema_dump_file_name + '\'')
        '''
        os.system('pg_restore -C -v -d "' + self.database_connection_credential_active[
            'connection_string'] + '" "' + schema_dump_file_name + '"')
        '''
        os.system('pg_restore -v -d "' + self.database_connection_credential_active[
            'connection_string'] + '" "' + schema_dump_file_name + '"')
        print('polnim bazo')
        print('rdbms-subsetter' + ' \'' + self.database_connection_credential_base['connection_string'] + '\' \'' +
              self.database_connection_credential_active['connection_string'] + '\' ' + str(
            self.parameters['fraction_of_rows_to_keep'])+' -b 0')
        '''
        RecursionError: maximum recursion depth exceeded while getting the str of an object
        circular reference in database schema
        https://github.com/18F/rdbms-subsetter/issues/34
        '''
        '''
        You can restrict the tables included in the sample via the --table (-t) and --exclude-table (-T) parameters (which can be used multiple times).
        '''
        os.system(
            'rdbms-subsetter' + ' \'' + self.database_connection_credential_base['connection_string'] + '\' \'' +
            self.database_connection_credential_active['connection_string'] + '\' ' + str(
                self.parameters['fraction_of_rows_to_keep'])+' -b 0')

    def number_of_entities_is_great(self):
        tables_number = len(self.active_database_meta['tables'])
        non_associative_entity_number = len(
            [table for table, data in self.active_database_meta['tables'].items() if not data['is_associative_entity']])
        if tables_number > 20:
            return True
        else:
            return False

    def limit_object_types_number(self, first_table_selected=None):
        # 1. For each object type form a list of connected object types (directly or max 1 hoop - via inbetween table)
        # 2. Give each node a score equal to number of connections
        # 3. Initialize selected cluster with single node having the highest score
        # 4. While cluster size is lower than object type number limit
        #   select node with highest score, that is connected to any of already selected nodes and add it to selection.
        node_connections = {x: [] for x in self.active_database_meta['tables']}
        node_connections_indirect = {}
        for fk in self.active_database_meta['foreign_keys']:
            ot1 = fk[1]
            ot2 = fk[3]
            if ot1 not in self.active_database_meta['tables'] and ot2 not in self.active_database_meta['tables']:
                continue
            if ot1 in self.active_database_meta['tables'] and ot2 in self.active_database_meta['tables']:
                node_connections[ot1].append(ot2)
                node_connections[ot2].append(ot1)
            elif ot1 in self.active_database_meta['tables']:
                if ot2 not in node_connections_indirect:
                    node_connections_indirect[ot2] = []
                node_connections_indirect[ot2].append(ot1)
            elif ot2 in self.active_database_meta['tables']:
                if ot1 not in node_connections_indirect:
                    node_connections_indirect[ot1] = []
                node_connections_indirect[ot1].append(ot2)
        for n in node_connections_indirect:
            for k in node_connections_indirect[n]:
                val = node_connections_indirect[n][:]
                val.remove(k)
                node_connections[k] += val
                node_connections[k] = list(set(node_connections[k]))

        nodes_by_weight = list(self.active_database_meta['tables'].keys())
        nodes_by_weight.sort(key=lambda k: -len(node_connections[k]))
        selected_nodes = []
        if first_table_selected is None:
            selected_nodes.append(nodes_by_weight[0])
        else:
            selected_nodes.append(first_table_selected)
        for i in range(1, self.parameters['object_types_limit']):
            candidates = {}
            for n in selected_nodes:
                if n is None:
                    continue
                for c in node_connections[n]:
                    if c in selected_nodes:
                        continue
                    if not n in candidates:
                        candidates[n] = c
                    else:
                        if nodes_by_weight.index(c) < nodes_by_weight.index(candidates[n]):
                            candidates[n] = c
            winner = None
            for n in candidates:
                if winner is None:
                    winner = candidates[n]
                elif nodes_by_weight.index(candidates[n]) < nodes_by_weight.index(winner):
                    winner = candidates[n]
            selected_nodes.append(winner)

        return selected_nodes

    def make_data_connection(self):
        '''
        Povezi se na bazo;
        Preveri, velikost baze;
        Ce je baza prevelika uporabniku ponudi moznost vzorcenja vrstic v bazi;
        Uporabnik poda delez vrstic, ki ostanejo po vzorcenju in podatke za povezavo na streznik, kjer naj se ustvari testna baza;
        Uporabnik tudi poda oz. potrdi ime nove baze;
        :return:
        '''
        entity_type_subset = None
        if self.number_of_entities_is_great():
            if self.presample_OT_dialog:
                confirm_entity_type_sampling = input(
                    'V bazi je veliko stevilo tabel (' + str(len(self.active_database_meta[
                                                                     'tables'])) + '), kar lahko mocno podaljsa izvajalni cas. Zelite omejiti stevilo obravnavanih tabel (na podlagi stevila povezav)? [DA/ne]:')
                if 'ne' in confirm_entity_type_sampling.lower():
                    confirm_entity_type_sampling = False
                else:
                    confirm_entity_type_sampling = True
                if confirm_entity_type_sampling:
                    if self.parameters['object_types_limit'] is None:
                        table_list = list(self.active_database_meta['tables'])
                        self.parameters['object_types_limit'] = int(input('Koliko od trenutnih ' + str(
                            len(self.active_database_meta['tables'])) + ' tabel zelite obdrzati? [1-' + str(
                            len(self.active_database_meta['tables'])) + ']'))
                    if self.parameters['entity_of_interest'] is None:
                        manual_entity_type_selection = int(input(
                            'Zelite, da je katera od tabel nujno v vzorcu?:\n\t0\tNE, vi izberite tabele.\n\t' + '\n\t'.join(
                                [str(i + 1) + '\t' + table_list[i] for i in
                                 range(len(table_list))]) + '\n[Vnesite stevilko pred izbiro]:\n'))
                        self.parameters['entity_of_interest'] = None if manual_entity_type_selection == 0 else table_list[
                            manual_entity_type_selection - 1]
                    entity_type_subset = self.limit_object_types_number(
                        first_table_selected=self.parameters['entity_of_interest'])
            else:
                entity_type_subset = self.limit_object_types_number()
        if self.database_is_big():
            if self.presample_rows_dialog:
                confirm_presampling = input(
                    'Zaradi velikosti podatkovne baze lahko pride do prekoracitve porabe razpolozljivega pomnilnika. Zelite zmanjsati stevilo vrstic v tabelah s postokom vzorcenja? [DA/ne]:')
                if 'ne' in confirm_presampling.lower():
                    confirm_presampling = False
                else:
                    confirm_presampling = True

                if confirm_presampling:
                    database_connection_string = input(
                        'Vnesite niz za povezavo na bazo (connection string), kjer naj se ustvari modificirana/pomanjsana verzija podatkovne baze. [postgresql://[user[:password]@][netloc][:port]/[database]:')
                    if self.parameters['fraction_of_rows_to_keep'] is None:
                        fraction_of_db_size = input('Vnesite delez podatkov, ki jih zelite obdrzati. [predlagano: ' + str(
                            self.optimal_rows_fraction()) + '] :')
                        fraction_of_db_size = float(fraction_of_db_size)
                        self.parameters['fraction_of_rows_to_keep'] = fraction_of_db_size
                    self.database_connection_credential_active['connection_string'] = database_connection_string
                    self.minify_database()
                    self.set_database_connection_credential(self.database_connection_credential_active['connection_string'])
            else:
                self.minify_database()
                self.set_database_connection_credential(self.database_connection_credential_active['connection_string'])

        # Odstrani podatke, ki se navezujejo na tiste tabele, ki jih ni v vzorcu
        if entity_type_subset is not None:
            for table in list(self.active_database_meta['tables'].keys()):
                if table not in entity_type_subset:
                    del self.active_database_meta['tables'][table]
            for fk_idx in range(len(self.active_database_meta['foreign_keys']) - 1, 0 - 1, -1):
                fk = self.active_database_meta['foreign_keys'][fk_idx]
                if fk[1] not in entity_type_subset or fk[3] not in entity_type_subset:
                    del self.active_database_meta['foreign_keys'][fk_idx]

    def select_denser_matrices(self, matrices_list):
        '''
        Returns sublist of given matrices_list, of length equal to user-set parameter self.max_number_of_alternative_relation_matrices_to_use.
        Prefers matrices with higher percentage of non-zero elements.
        :param matrices_list:
        :return:
        '''
        scores = []
        for matrix in matrices_list:
            matrix = np.array(matrix)
            #scores.append(np.sum(np.isnan(matrix)) / (matrix.shape[0] * matrix.shape[1]))
            scores.append(1 - (np.sum(np.isnan(matrix)) / (matrix.shape[0] * matrix.shape[1])))
        chosen_matrices_indices = np.argsort(scores)[::-1][:self.parameters['alternative_matrices_limit']]
        return [matrices_list[i] for i in chosen_matrices_indices]

    def limit_relation_matrices_number(self, relation_matrices=None):
        '''
        Check if number of relation matrices describing any relation between pairs of object types exceeds the limit set by user.
        If the limit is not respected, select subset of matrices using different heuristics (size, density..)
        '''
        print("***Preverjam stevilo alternativnih relacijskih matrik za relacije..")
        if self.parameters['alternative_matrices_limit'] is None:
            return relation_matrices
        for relation, data in relation_matrices.items():
            if len(data) > self.parameters[
                'alternative_matrices_limit']:
                print("\tRelacija " + str(relation) + " ima " + str(len(data)) + " kar je vec kot omejitev " + str(
                    self.parameters['alternative_matrices_limit']) + " alternativnih relacijskih matrik!")
                print("\t\t\tIzbiram " + str(self.parameters['alternative_matrices_limit']) + " najgostejsih matrik")
                relation_matrices[relation] = self.select_denser_matrices(data)
                # self.relation_matrices[relation] = self.select_larger_matrices(self.relation_matrices[relation])
        return relation_matrices

    def remove_nan_relations(self, relation_matrices=None):
        if relation_matrices is None:
            return
        for relation in list(relation_matrices):
            for i in range(len(relation_matrices[relation]) - 1, 0 - 1, -1):
                if np.all(np.isnan(relation_matrices[relation][i])):
                    del relation_matrices[relation][i]
            if len(relation_matrices[relation]) == 0:
                del relation_matrices[relation]
        return relation_matrices

    @staticmethod
    def postgres_to_python_data_type(data_type):
        data_type = data_type.upper()
        postgres_to_python_data_types = {'CHARACTER': object, 'CHAR': object, 'VARCHAR': object, 'TEXT': object,
                                         'SMALLINT': int, "INTEGER": int, 'INT': int,
                                         'SERIAL': int, 'FLOAT': float, 'REAL': float, 'FLOAT8': float,
                                         'NUMERIC': float, 'DATE': 'datetime'}
        return postgres_to_python_data_types[data_type]

    def gen_matrices_for_column(self, fk_link1, fk_link2, table, column_id):
        '''
        :param table1:
        :param table2:
        :param table:
        :param column_id:
        :return:list of relational matrices.
        Only 1 matrix if binarization of attribute(column_id) is not required.
        '''
        build_dummy=self.is_text_data_type(self.active_database_meta['tables'][table]['columns'][column_id]['data_type'])

        # table=fk_link1[1]
        table1 = fk_link1[2]
        table2 = fk_link2[2]

        # print("GENERATE RELATION MATRIX",table1,table2,table+'->'+column_id)
        matrices = []
        # print("\tGeneriranje matrik za stolpec vmesne matrike..")
        table_table1_fk = [x for x in self.active_database_meta['foreign_keys'] if
                           x[1] == table and x[3] == table1 and x[0] == fk_link1[0]]
        table_table2_fk = [x for x in self.active_database_meta['foreign_keys'] if
                           x[1] == table and x[3] == table2 and x[0] == fk_link2[0]]
        table_table1_fk=list(set(table_table1_fk))
        table_table2_fk=list(set(table_table2_fk))
        objects_table1 = self.active_database_meta['tables'][table1]['row_ids']
        objects_table2 = self.active_database_meta['tables'][table2]['row_ids']
        if len(objects_table1) == 0 or len(objects_table2) == 0:
            return []
        sql_query = "SELECT " + ', '.join('a.' + x[4] for x in table_table1_fk) + ', ' + ', '.join('b.' + x[4] for x in
                                                                                                   table_table2_fk) + ', ' + table + '.' + column_id + " FROM " + table + " INNER JOIN " + table1 + " as a ON " + ' AND '.join(
            [x[1] + '.' + x[2] + ' = ' + 'a.' + x[4] for x in
             table_table1_fk]) + " INNER JOIN " + table2 + " as b ON " + ' AND '.join(
            [x[1] + '.' + x[2] + ' = ' + 'b.' + x[4] for x in table_table2_fk]) + ';'
        cursor = self.database_active_connection.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        column_dtype = [('fk1-' + str(i) + '_' + table_table1_fk[i][3] + '.' + table_table1_fk[i][4],
                         self.postgres_to_python_data_type(
                             self.active_database_meta['tables'][table_table1_fk[i][3]]['columns'][
                                 table_table1_fk[i][4]]['data_type'])) for i in range(len(table_table1_fk))] + [(
            'fk2-' + str(i) + '_' +
            table_table2_fk[i][
                3] + '.' +
            table_table2_fk[i][4],
            self.postgres_to_python_data_type(
                self.active_database_meta[
                    'tables'][
                    table_table2_fk[i][
                        3]][
                    'columns'][
                    table_table2_fk[i][
                        4]][
                    'data_type']))
                           for i
                           in
                           range(len(table_table2_fk))] + [
                           (table + '.' + column_id, self.postgres_to_python_data_type(
                               self.active_database_meta['tables'][table]['columns'][column_id]['data_type']))]
        if sum([x[-1] is None for x in rows]):
            if column_dtype[-1][1] is not object:
                print('NOT OBJECT')
                column_dtype[-1] = (column_dtype[-1][0], np.float)
        rows = np.array(rows, dtype=column_dtype)
        nr_columns = 1
        if rows.shape[0] > 0 and build_dummy:

            if None in [x[-1] for x in rows]:
                print(
                    "\t\t\t\t\t\t\tStolpec vsebuje vrednost 'None' --> nadaljujem brez razbitja na mnozico indikatorskih spremenljivk")
                return []
            else:
                labelencoder = LabelEncoder()
                print("\t\t\t\t\t\t\tROWS to TRANSFORM by LABELENCODER", rows[table + '.' + column_id])
                rows[table + '.' + column_id] = labelencoder.fit_transform(rows[table + '.' + column_id])
                nr_columns = len(labelencoder.classes_)
                onehotencoder = OneHotEncoder(categorical_features=[-1])
                dummy_variables = onehotencoder.fit_transform(rows[table + '.' + column_id].reshape(-1, 1)).toarray()
                # dummy_variables = np.array(dummy_variables,dtype=[(str(i),int) for i in range(nr_columns)])
                rows = rows[list(rows.dtype.names)[:-1]]
                new_dt = np.dtype(rows.dtype.descr + [(str(i), int) for i in range(nr_columns)])
                tmp = np.zeros(rows.shape, dtype=new_dt)
                for c in list(rows.dtype.names):
                    tmp[c] = rows[c]
                for c in range(nr_columns):
                    tmp[str(c)] = dummy_variables[:, c]
                rows = tmp
                # dummy variable trap?
                # move dummy variables from begining to end of table!
        column_order_row_o1 = [x[4] for x in table_table1_fk]
        column_order_row_o2 = [x[4] for x in table_table2_fk]

        if build_dummy:
            for i in range(nr_columns):
                print("\t\t\t\t\t\t\tPoskusam ustvariti prazno matriko velikosti: ", len(objects_table1), " X ",
                      len(objects_table2))
                R = np.empty((len(objects_table1), len(objects_table2)))
                R.fill(np.nan)
                matrices.append(R)

        matrix_combos={}
        for row in rows:
            row = list(row)
            c1 = row[0:len(self.active_database_meta['tables'][table1]['column_name_PK'])]
            # Ustrezno premesaj stolpce
            c1_dict = {table_table1_fk[i][4]: c1[i] for i in range(len(table_table1_fk))}
            c1 = (c1_dict[x] for x in self.active_database_meta['tables'][table1]['column_name_PK'])
            c1 = tuple(c1)
            c2 = row[len(self.active_database_meta['tables'][table1]['column_name_PK']):len(
                self.active_database_meta['tables'][table1]['column_name_PK']) + len(
                self.active_database_meta['tables'][table2]['column_name_PK'])]
            # Ustrezno premesaj stolpce
            c2_dict = {table_table2_fk[i][4]: c2[i] for i in range(len(table_table2_fk))}
            c2 = (c2_dict[x] for x in self.active_database_meta['tables'][table2]['column_name_PK'])
            c2 = tuple(c2)
            v = row[-nr_columns:]

            if build_dummy:
                #Pri indikatorskih matrikah lahko z 1 oznacimo povezanost dveh objektov razlicnih tipov tudi za vec vrednosti
                o1_idx = self.active_database_meta['tables'][table1]['row_ids'].index(c1)
                o2_idx = self.active_database_meta['tables'][table2]['row_ids'].index(c2)
                for i in range(nr_columns):
                    if not matrices[i][o1_idx][o2_idx] == 1:
                        matrices[i][o1_idx][o2_idx]=v[i]
            else:
                if not (c1,c2) in matrix_combos:
                    matrix_combos[(c1,c2)]=[set() for i in range(nr_columns)]
                for i in range(nr_columns):
                    matrix_combos[(c1,c2)][i].add(v[i])

        if not build_dummy:
            matrix_combos_iterators=[]
            matrix_combos_keys=list(matrix_combos.keys())
            for i in range(nr_columns):
                matrix_combos_iterators.append(itertools.product(
                *[matrix_combos[object_combo][i] for object_combo in matrix_combos_keys]))

            matrix_combos_lengths=[]
            for i in range(nr_columns):
                matrix_combos_lengths.append(int(np.prod([len(matrix_combos[x][i]) for x in matrix_combos])))
            nr_matrices=sum(matrix_combos_lengths)

            if self.parameters['alternative_matrices_limit'] is not None and self.parameters['alternative_matrices_limit']<nr_matrices:
                print('\t\t\t\t\t\t\tStevilo matrik ('+str(nr_matrices)+') presega omejitev ('+str(self.parameters['alternative_matrices_limit'])+'). Omejujem nabor.')
                nr_matrices=self.parameters['alternative_matrices_limit']

            for i in range(nr_matrices):
                k=i%nr_columns
                while matrix_combos_lengths[k%nr_columns]<=0:
                    k+=1
                matrix_combos_lengths[k]-=1
                combo = next(matrix_combos_iterators[k])

                print("\t\t\t\t\t\t\tPoskusam ustvariti prazno matriko velikosti: ", len(objects_table1), " X ",len(objects_table2))
                R = np.empty((len(objects_table1), len(objects_table2)))
                R.fill(np.nan)

                for j in range(len(matrix_combos_keys)):
                    o1=matrix_combos_keys[j][0]
                    o2=matrix_combos_keys[j][1]
                    o1_idx=self.active_database_meta['tables'][table1]['row_ids'].index(o1)
                    o2_idx=self.active_database_meta['tables'][table2]['row_ids'].index(o2)
                    v=combo[j]
                    R[o1_idx,o2_idx]=v
                matrices.append(R)

        for m in matrices:
            if np.isnan(m.all()):
                matrices.remove(m)
        return matrices

    def gen_indicator_matrix_for_relation(self, fk_link):
        '''
        :param table1:
        :param table2:
        :param table:
        :param column_id:
        :return:list of relational matrices.
        Only 1 matrix if binarization of attribute(column_id) is not required.
        '''
        table1 = fk_link[1]
        table2 = fk_link[2]
        matrices = []
        objects_table1 = self.active_database_meta['tables'][table1]['row_ids']
        objects_table2 = self.active_database_meta['tables'][table2]['row_ids']
        table1_table2_fk = [x for x in self.active_database_meta['foreign_keys'] if
                            x[1] == table1 and x[3] == table2 and x[0] == fk_link[0]]

        if len(objects_table1) == 0 or len(objects_table2) == 0:
            return []

        R = np.empty((len(objects_table1), len(objects_table2)))
        R.fill(np.nan)
        sql_query = "SELECT " + ', '.join(
            'a.' + x for x in self.active_database_meta['tables'][table1]['column_name_PK']) + ', ' + ', '.join(
            'b.' + x for x in self.active_database_meta['tables'][table2][
                'column_name_PK']) + " FROM " + table1 + " as a INNER JOIN " + table2 + " as b ON " + ' AND '.join(
            ['a.' + x[2] + ' = ' + 'b.' + x[4] for x in table1_table2_fk]) + ';'
        cursor = self.database_active_connection.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()

        for line in rows:
            object1_id = line[0:len(self.active_database_meta['tables'][table1]['column_name_PK'])]
            object2_id = line[len(self.active_database_meta['tables'][table1]['column_name_PK']):len(
                self.active_database_meta['tables'][table1]['column_name_PK']) + len(
                self.active_database_meta['tables'][table2]['column_name_PK'])]
            if len(object1_id) == 0 or len(object2_id) == 0 or None in object1_id or None in object2_id:
                continue
            object1_indx = self.active_database_meta['tables'][table1]['row_ids'].index(object1_id)#list(objects_table1).index(object1_id)
            object2_indx = self.active_database_meta['tables'][table2]['row_ids'].index(object2_id)#list(objects_table2).index(object2_id)
            R[object1_indx, object2_indx] = 1

        if np.isnan(R.all()):
            return []

        return [R]

    def build_relation_matricies(self):
        '''
        Build relation and constraint matrices for fusion process.
        Build relation matrices for every pair of object types, that is implicitly related via third table and
        also build one indicator relation matrix for each pair of directly connected object types.
        If object type is referencing itself, also build constraint matrix.
        :return:
        '''
        print("***Gradnja relacijskih in omejitvenih matrik..")
        relation_matrices = {}  # pripravi strukturo za hranjenje vseh moznih relacijskih matrik
        # constraint_matrices = {}  # pripravi strukturo za hranjenje vseh moznih omejitvenih matrik

        table_relations = [(x[1], x[3]) for x in self.active_database_meta['foreign_keys']]
        tables = set([x for x, y in table_relations])
        table_count = 0
        for t in tables:
            table_count += 1
            print("\t ( " + str(table_count) + ' / ' + str(len(tables)) + " )\tGradim relacijske matrike za tabelo: ",
                  t)
            tables_linked_to_t = [y for x, y in table_relations if x == t]
            fk_names_linked_to_t = set(
                [(y[0], y[1], y[3]) for y in self.active_database_meta['foreign_keys'] if y[1] == t])
            if len(tables_linked_to_t) >= 2:
                # Zgradi relacijske matrike za posredno povezane tabele.
                table_combo_count = 0
                fk_linked_to_t_combinations = list(itertools.combinations(fk_names_linked_to_t, 2))
                for t1, t2 in fk_linked_to_t_combinations:
                    table_combo_count += 1
                    # print("T1: ",t1,"T2: ",t2)
                    print("\t\t\t( " + str(table_combo_count) + ' / ' + str(
                        len(fk_linked_to_t_combinations)) + " )\tGradim relacijske matrike za povezavi:", t1, 'in', t2)
                    column_count = 0
                    columns_matrix_build = [column for column, data in
                                            self.active_database_meta['tables'][t]['columns'].items() if
                                            self.is_numeric_data_type(data['data_type']) or (
                                                        self.is_text_data_type(data['data_type']) and (
                                                            self.parameters['dummy_var_treshold'] is None or data[
                                                        'unique_values'] <= self.parameters['dummy_var_treshold']))]
                    for c in columns_matrix_build:
                        column_count += 1
                        print("\t\t\t\t\t( " + str(column_count) + ' / ' + str(
                            len(columns_matrix_build)) + " )\tGradim relacijske matrike stolpec:", c)
                        if self.active_database_meta['tables'][t]['columns'][c]['is_PK'] or \
                                self.active_database_meta['tables'][t]['columns'][c]['is_FK']:
                            print(
                                '\t\t\t\t\t\t\tStolpec predstavlja kljuc (primarni ali tuji) in zato ni primeren za gradnjo matrik.')
                            continue
                        matrices = self.gen_matrices_for_column(t1, t2, t, c)
                        if not (t1[2], t2[2]) in relation_matrices and not (t2[2], t1[2]) in relation_matrices:
                            relation_matrices[(t1[2], t2[2])] = []
                        if (t1[2], t2[2]) in relation_matrices:
                            relation_matrices[(t1[2], t2[2])] += matrices.copy()
                        else:
                            relation_matrices[(t2[2], t1[2])] += [np.transpose(x) for x in matrices]
            if len(tables_linked_to_t) >= 1 and self.active_database_meta['tables'][t]['is_object_type']:
                # Zgradi relacijske matrike za vsako direktno povezavo obravnavane tabele.
                # for t1 in tables_linked_to_t:
                table_combo_count = 0
                for t1 in fk_names_linked_to_t:
                    if not self.active_database_meta['tables'][t1[2]]['is_object_type'] or len(
                            self.active_database_meta['tables'][t1[2]]['column_name_PK']) == 0 or len(
                            self.active_database_meta['tables'][t1[1]]['column_name_PK']) == 0:
                        continue
                    table_combo_count += 1
                    print("\t\t\t( " + str(table_combo_count) + ' / ' + str(
                        len(fk_names_linked_to_t)) + " )\tGradim omejitvene oz. indikatorske matrike za povezavo s:",
                          t1)
                    matrices = self.gen_indicator_matrix_for_relation(t1)
                    if t == t1[2]:
                        # Gre za omejitveno matriko
                        if not (t, t) in relation_matrices:
                            relation_matrices[(t, t)] = []
                        relation_matrices[(t, t)] += matrices.copy()
                    else:
                        # Indikatorske matrike tudi gradimo, da lahko zagotovimo povezanost grafa, ki ga podamo fusion algoritmu
                        if not (t, t1[2]) in relation_matrices and not (t1[2], t) in relation_matrices:
                            relation_matrices[(t, t1[2])] = []
                        # Lahko zgradimo po eno za vsak stolpec (katere koli od) povezanih tabel
                        if (t, t1[2]) in relation_matrices:
                            relation_matrices[(t, t1[2])] += matrices.copy()
                        else:
                            relation_matrices[(t1[2], t)] += [np.transpose(x) for x in matrices]
            relation_matrices = self.limit_relation_matrices_number(
                relation_matrices)  # Zaradi porabe pomnilnika ze spotoma filtriraj seznam alternativnih matrik
            gc.collect()

        # relation_matrices = self.remove_nan_relations(relation_matrices)
        return relation_matrices

    @staticmethod
    def scale(X, amin, amax):
        X_nonnan = X[~np.isnan(X)]
        X_min = X_nonnan.min()
        X_max = X_nonnan.max()
        return (X - X_min) / (X_max - X_min) * (amax - amin) + amin

    def preprocess_relational_matrices(self, relation_matrices):
        # PREPROCESS RELATIONAL MATRICES
        nan_matrices_idx = []
        for key in relation_matrices:
            for i in range(len(relation_matrices[key])):
                rm_tmp = relation_matrices[key][i]
                rm_tmp = np.array(rm_tmp)
                # Mask NaNs
                # rm_tmp = np.ma.array(rm_tmp, mask=np.isnan(rm_tmp))
                mask = np.isnan(rm_tmp)
                if not np.isnan(rm_tmp).all():
                    mean_value = np.nanmean(rm_tmp)
                    min_value = rm_tmp[~mask].min()
                    max_value = rm_tmp[~mask].max()
                    # rm_tmp[mask] = mean_value
                    if not max_value - min_value == 0:
                        # Scale values to fit interval [0,1]
                        rm_tmp = self.scale(rm_tmp, 0, 1)
                rm_tmp = np.ma.array(rm_tmp, mask=mask)
                relation_matrices[key][i] = rm_tmp
        return relation_matrices

    def save_matrices(self, relation_matrices, dir):
        if not os.path.exists(dir):
            os.makedirs(dir)
        for key in relation_matrices:
            np.save(dir + '/' + '-'.join(key), relation_matrices[key])
        text_dir = dir + '/text'
        if not os.path.exists(text_dir):
            os.makedirs(text_dir)
        for key in relation_matrices:
            for i in range(len(relation_matrices[key])):
                np.savetxt(text_dir + '/' + '-'.join(key) + '_' + str(i), relation_matrices[key][i])

    def rmse(self, y_true, y_pred):
        return np.sqrt(np.sum((y_true - y_pred) ** 2) / y_true.size)

    def generate_fusion_graphs(self, relation_matrices):
        print("***Generiram graf za zlivanje..")
        object_types_fusion = {}
        relational_matrices_keys = list(relation_matrices.keys())
        # print('OBJEKTNI TIPI: ',self.object_types)
        object_types = [t for t, data in self.active_database_meta['tables'].items() if data['is_object_type']]
        for type_name in object_types:
            # print("Kreiram ObjectType objekt za ",type_name)
            if self.parameters['latent_factor'] is not None:
                object_types_fusion[type_name] = fusion.ObjectType(type_name,self.parameters['latent_factor'])
            else:
                object_types_fusion[type_name] = fusion.ObjectType(type_name)

        fusion_sets_length = 1

        for key in relation_matrices:
            fusion_sets_length *= len(relation_matrices[key])
        fusion_sets = itertools.product(
            *[relation_matrices[relation_name] for relation_name in relational_matrices_keys])
        object_types_in_fusion_scheme = set()
        # fusion_sets = []

        fusion_set_counter = 0
        print("\t#Pripravljam grafe za zlivanje..")
        for fusion_set in fusion_sets:
            fusion_set_counter += 1
            print("\t\t\t ( " + str(fusion_set_counter) + ' / ' + str(fusion_sets_length) + " ) Pripravljam graf..")

            fusion_graph = fusion.FusionGraph()
            relations = []

            for i in range(len(relational_matrices_keys)):
                related_objects = relational_matrices_keys[i]
                relational_matrix = fusion_set[i]

                object_types_in_fusion_scheme.add(related_objects[0])
                object_types_in_fusion_scheme.add(related_objects[1])
                relations.append(fusion.Relation(relational_matrix, object_types_fusion[related_objects[0]],
                                                 object_types_fusion[related_objects[1]]))

            fusion_graph.add_relations_from(relations)
            yield fusion_graph
            # self.fusion_graphs.append(fusion_graph)
            gc.collect()

    def score_relation_reconstruction(self, relation_name, graph_before_fusion, graph_after_fusion):
        '''
            :param relation: name of a relation
            :return: score for a given relation name, that is calculated as a mean of relation matrix reconstruction accuracy
            across all models.
        '''
        relation_object_types_names = relation_name
        object_type1 = [x for x in graph_before_fusion.object_types.keys() if x.name == relation_object_types_names[0]][
            0]
        object_type2 = [x for x in graph_before_fusion.object_types.keys() if x.name == relation_object_types_names[1]][
            0]
        # relation = [x for x in list(graph_before_fusion.relations.keys()) if x.__contains__(object_type1) and x.__contains__(object_type2)][0]
        relation = [x for x in list(graph_before_fusion.relations.keys()) if
                    (x.row_type == object_type1 and x.col_type == object_type2) or (
                            x.row_type == object_type2 and x.col_type == object_type1)][0]
        original_matrix = relation.data

        latent_space_matrix = graph_after_fusion.complete(relation)
        original_matrix_vector = original_matrix.reshape(1, original_matrix.shape[0] * original_matrix.shape[1])
        latent_space_matrix_vector = latent_space_matrix.reshape(1, latent_space_matrix.shape[0] *
                                                                 latent_space_matrix.shape[1])

        distance = self.rmse(original_matrix_vector, latent_space_matrix_vector)
        return distance

    def fuse_data(self, relation_matrices):
        '''
        https://github.com/marinkaz/scikit-fusion
        :return:
        '''
        print("***Zlivanje podatkov..")
        # Infer the latent data model for each fusion graph
        # self.latent_data_models = []
        object_type_relations = list(relation_matrices.keys())

        fusion_set_counter = 0
        models_scores = {}
        for graph in self.generate_fusion_graphs(relation_matrices):
            fusion_set_counter += 1
            # print("\t\t\t ( " + str(fusion_set_counter) + ' / ' + str(len(self.generate_fusion_graphs())) + " )")
            print("\t\t\t\t\t ..zlivam graf..")
            if not self.parameters['latent_factor'] is None:
                fuser = fusion.Dfmf(self.parameters['latent_factor'])
            else:
                fuser = fusion.Dfmf()
            fuser.fuse(graph)
            # self.latent_data_models.append(fuser)
            relation_scores = {}
            relation_counter = 1
            for relation in object_type_relations:
                relation_object_types_names = relation
                print("\t\t\t\t\t( " + str(relation_counter) + " / " + str(
                    len(object_type_relations)) + " ) ..ocenjujem rekonstrukcijo relacije: ", relation)

                # SPLOH RES ZELIMO IZ OBRAVNAVE IZLOCITI RELACIJE MED OBJEKTI ISTEGA TIPA??
                # PROBLEM, KER IZ MODELA NE MOREMO DOBITI REKONSTRUKCIJ OMEJITVENIH MATRIK?
                if relation_object_types_names[0] == relation_object_types_names[1]:
                    print("\t\t\t\t\t\t\t Preskocil relacijo med dvema enakima objektnima tipoma..", relation)
                    relation_counter += 1
                    continue

                distance = self.score_relation_reconstruction(relation, graph, fuser)
                relation_scores[relation] = distance
                relation_counter += 1
                # print ordered relation list for this model
            print("\t\t\t\t\tUREJEN SEZNAM RELACIJ:",
                  sorted([(k, relation_scores[k]) for k in relation_scores], key=lambda x: x[1]))
            models_scores[fusion_set_counter] = relation_scores
            gc.collect()
        print("***Konec zlivanja!!")
        relation_scores_avg = {}
        relation_scores_best = {}
        for relation in object_type_relations:
            if relation[0] == relation[1]:
                # Model ocitno ne generira napovedi za omejitvene matrike..
                print("\t\t\t\t\t Preskocil relacijo med dvema enakima objektnima tipoma..", relation)
                continue
            if self.parameters['multiple_models_relation_reconstruction'] == 'avg':
                sum = 0
                for model in models_scores:
                    sum += models_scores[model][relation]
                relation_scores_avg[relation] = sum / len(models_scores)
            elif self.parameters['multiple_models_relation_reconstruction'] == 'best':
                for model in models_scores:
                    if not relation in relation_scores_best:
                        relation_scores_best[relation]=models_scores[model][relation]
                    elif models_scores[model][relation] < relation_scores_best[relation]:
                        relation_scores_best[relation] = models_scores[model][relation]
            gc.collect()
        relation_scores_all=relation_scores_avg if self.parameters['multiple_models_relation_reconstruction']=='avg' else relation_scores_best
        relation_scores_final_list = [(x, relation_scores_all[x]) for x in relation_scores_all]
        relation_scores_final_list.sort(key=lambda tup: tup[1])
        print('RELATION SCORES',models_scores)
        return relation_scores_final_list

    def __str__(self):
        string_representation='\nFuseRDB object:'
        string_representation+='\n\tActive database:'
        for key,value in self.database_connection_credential_active.items():
            string_representation+='\n\t\t'+key+': '+str(value)
        string_representation += '\n\tParameters:'
        for key, value in self.parameters.items():
            string_representation += '\n\t\t' + key + ': ' + str(value)
        string_representation+='\n'
        return string_representation


    def __init__(self, database_connection, database2_connection_string=None, dummy_var_treshold=None,
                 fraction_of_rows_to_keep=None,
                 alternative_matrices_limit=None, object_types_limit=None, entity_of_interest=None, max_matrix_size=100000, latent_factor=None, multiple_models_relation_reconstruction='best'):
        self.database_connection_credential_base = {'database_system': 'postgresql', 'host': None, 'database': None,
                                                    'user': None, 'password': None, 'connection_string': None}
        self.database_connection_credential_active = {'database_system': 'postgresql', 'host': None, 'database': None,
                                                      'user': None, 'password': None, 'connection_string': None}
        self.database_active_connection = None
        self.active_database_meta = {'tables': {},
                                     'foreign_keys': {}}  # 'ime_tabele':{'stolpci':{'ime_stolpca':{'podatkovni_tip':PODATKOVNI_TIP,'primarni_kljuc':True/False, 'tuji_kljuc':True/False'}}, 'imena_stolpcev_PK':['ime_stolpca1','ime_stolpca2'],'imena_stolpcev_FK':{'ime_FK':'ime_stolpca1'}, 'objekti':[(vrednost_PK1_stolpca,vrednost_PK2_stolpca)] }
        self.parameters = {'dummy_var_treshold': None, 'fraction_of_rows_to_keep': None,
                           'alternative_matrices_limit': None,
                           'object_types_limit': None, 'latent_factor': None, 'entity_of_interest':None, 'max_matrix_size':None, 'multiple_models_relation_reconstruction':None}
        self.presample_rows_dialog = True
        self.presample_OT_dialog = True
        if database_connection is not None:
            self.set_database_connection_credential(database_connection)
        if database2_connection_string is not None:
            self.database_connection_credential_active['connection_string'] = database2_connection_string
            self.presample_rows_dialog = False
        if fraction_of_rows_to_keep is not None:
            self.parameters['fraction_of_rows_to_keep'] = fraction_of_rows_to_keep
        if alternative_matrices_limit is not None:
            self.parameters['alternative_matrices_limit'] = alternative_matrices_limit
        if object_types_limit is not None:
            self.parameters['object_types_limit'] = object_types_limit
            self.presample_OT_dialog = False
        self.parameters['entity_of_interest']=entity_of_interest
        self.parameters['max_matrix_size']=max_matrix_size
        if latent_factor is not None:
            self.parameters['latent_factor']=int(latent_factor)
        self.parameters['multiple_models_relation_reconstruction']=multiple_models_relation_reconstruction
        start_time = datetime.now()

        self.make_data_connection()
        run_dir = self.database_connection_credential_active['host'] + '-' + self.database_connection_credential_active[
            'database'] + '-' + str(self.parameters['fraction_of_rows_to_keep']) + '/'
        relation_matrices = self.build_relation_matricies()
        self.save_matrices(relation_matrices=relation_matrices, dir=run_dir + 'relacijske_matrike/surove')
        relation_matrices = self.preprocess_relational_matrices(relation_matrices)
        self.save_matrices(relation_matrices=relation_matrices, dir=run_dir + 'relacijske_matrike/obdelane')
        relation_scores = self.fuse_data(relation_matrices)
        print('***KONEC\n\n')
        end_time = datetime.now()
        final_list='RANGIRAN SEZNAM RELACIJ:'
        for i in range(len(relation_scores)):
            final_list+='\n\t'+str(i+1)+'. '+str(relation_scores[i][0])+' -- RMSE: '+str(relation_scores[i][1])
        print(final_list)


        #Write to file
        results_file=open(run_dir+'run_results.txt','w+')
        results_file.write(str(self)+'\n\n\n'+final_list+"\n\n\n===== Postopek je trajal:\t"+str( end_time - start_time))
        results_file.close()


        print("\n\n\n===== Postopek je trajal:\t", end_time - start_time)


if __name__ == "__main__":
    fuse = FuseRDB(database_connection='postgresql://postgres:geslo123@192.168.217.128/avtomobilizem2',dummy_var_treshold=4,alternative_matrices_limit=2,multiple_models_relation_reconstruction='best')
    '''
    fuse = FuseRDB(database_connection='postgresql://postgres:geslo123@192.168.217.128/parameciumdb',
                   database2_connection_string='postgresql://postgres:geslo123@127.0.0.1/mini_parameciumdb',
                   dummy_var_treshold=4, fraction_of_rows_to_keep=0.00001, alternative_matrices_limit=1,
                   object_types_limit=20)
    '''

    '''
    fuse = FuseRDB(database_connection='postgresql://postgres:geslo123@127.0.0.1/mini_parameciumdb',
                   dummy_var_treshold=4, alternative_matrices_limit=1,
                   object_types_limit=10)
    '''
    #fuse=FuseRDB(database_connection='postgresql://postgres:geslo123@192.168.217.128/pagila',database2_connection_string='postgresql://postgres:geslo123@127.0.0.1/mini_pagila',dummy_var_treshold=4, fraction_of_rows_to_keep=1, alternative_matrices_limit=1)
    #fuse=FuseRDB(database_connection='postgresql://postgres:geslo123@192.168.217.128/pagila',dummy_var_treshold=4, fraction_of_rows_to_keep=1, alternative_matrices_limit=1)
    #fuse=FuseRDB(database_connection='postgresql://postgres:geslo123@192.168.217.128/french_towns',dummy_var_treshold=4, fraction_of_rows_to_keep=1, alternative_matrices_limit=1)
