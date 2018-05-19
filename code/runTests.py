from FuseRDB import FuseRDB
import contextlib
import itertools
import os
import threading
import time
#import Queue

num_active_threads=3
active_threads=[]
#workQueue = Queue.Queue(maxsize=0)
#queueLock = threading.Lock()

#threadLimiter = threading.BoundedSemaphore(num_active_threads)
#threading.current_thread().name = 'MainThread'

class myThread (threading.Thread):
   def __init__(self, presampling_mode, dummy_var_threshold, latent_factor,run_nr):
        threading.Thread.__init__(self)
        self.presampling_mode = presampling_mode
        self.dummy_var_threshold = dummy_var_threshold
        self.latent_factor = latent_factor
        self.run_nr=run_nr

   def run(self):
       '''
       threadLimiter.acquire()
       try:
           with open('avtomobilizem_' + str(self.presampling_mode) + '_' + str(self.dummy_var_threshold) + '_' + str(self.latent_factor) + '_run' + str(self.run_nr) + '.log', 'w') as f:
               with contextlib.redirect_stdout(f):
                   if os.path.exists(".checkpoint_" + host + "_" + database + ".txt"):
                        os.remove(".checkpoint_" + host + "_" + database + ".txt")
                   FuseRDB(host=host, database=database, user='postgres', password='geslo123',
                           dummy_var_treshold=self.dummy_var_threshold, join_outmost_tables_mode=False, presampling_mode=self.presampling_mode, latent_factor=self.latent_factor)
       finally:
           threadLimiter.release()
       '''
       with open('avtomobilizem_' + str(self.presampling_mode) + '_' + str(self.dummy_var_threshold) + '_' + str(
               self.latent_factor) + '_run' + str(self.run_nr) + '.log', 'w') as f:
           with contextlib.redirect_stdout(f):
               if os.path.exists(".checkpoint_" + host + "_" + database + ".txt"):
                   os.remove(".checkpoint_" + host + "_" + database + ".txt")
               FuseRDB(host=host, database=database, user='postgres', password='geslo123',
                       dummy_var_treshold=self.dummy_var_threshold, join_outmost_tables_mode=False,
                       presampling_mode=self.presampling_mode, latent_factor=self.latent_factor)


latent_factor=range(1,50)
presampling_mode=[True,False]
dummy_var_treshold=range(20)
nr_runs=5
host='192.168.217.128'
database='avtomobilizem2'

for p,d,l in itertools.product(presampling_mode,dummy_var_treshold,latent_factor):
    for i in range(nr_runs):
        thread = myThread(presampling_mode=p,dummy_var_threshold=d,latent_factor=l,run_nr=i)
        thread.setDaemon(True)
        active_threads.append(thread)

        thread.start()
        thread.join()
        '''
        if len(active_threads)==num_active_threads:
            for thread in active_threads:
                thread.start()
            for thread in active_threads:
                thread.join()
            active_threads=[]
        '''


