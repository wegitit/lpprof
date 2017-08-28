# -*- coding: utf-8 -*-
##############################################################################
#  This file is part of the LPprofiler profiling tool.                       #
#        Copyright (C) 2017  EDF SA                                          #
#                                                                            #
#  LPprofiler is free software: you can redistribute it and/or modify        #
#  it under the terms of the GNU General Public License as published by      #
#  the Free Software Foundation, either version 3 of the License, or         #
#  (at your option) any later version.                                       #
#                                                                            #
#  LPprofiler is distributed in the hope that it will be useful,             #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#  GNU General Public License for more details.                              #
#                                                                            #
#  You should have received a copy of the GNU General Public License         #
#  along with LPprofiler.  If not, see <http://www.gnu.org/licenses/>.       #
#                                                                            #
############################################################################## 

from subprocess import Popen,PIPE
import lpprofiler.perf_samples_profiler as psp
import lpprofiler.perf_hwcounters_profiler as php
import sys, os, stat, re, datetime



class LpProfiler :
    
    def __init__(self,launcher,launcher_args,binary):

        # Launcher name (ex: srun)
        self.launcher=launcher

        # Launcher arguments
        self.launcher_args=launcher_args

        # Binary to profile
        self.binary=binary

        # Profiling options (TODO: should be customizable at launch )
        self.profiling_flavours=["asm_prof","hwcounters_prof"]

        self.global_metrics={}

        today=datetime.date.today()
        self.traces_directory="PERF_{}".format(today.isoformat())

        os.mkdir(self.traces_directory)
        
        # List of profilers
        if (self.launcher=='srun'):
            self.profilers=[php.PerfHWcountersProfiler("./{}/perf.stats_%t".format(self.traces_directory),\
                                                       ["./{}/perf.stats_0".format(self.traces_directory)]),\
                            psp.PerfSamplesProfiler("./{}/perf.data_%t".format(self.traces_directory),\
                                                    ["./{}/perf.data_0".format(self.traces_directory)])]

        elif (self.launcher=='std'):
            self.profilers=[php.PerfHWcountersProfiler("./{}/perf.stats".format(self.traces_directory)),\
                            psp.PerfSamplesProfiler("./{}/perf.data".format(self.traces_directory))]
    
    def _std_run(self,frequency):
        """ Run standard exe with perf profiling """

        for prof in self.profilers :
            run_cmd+=prof.get_profile_cmd()
        
        run_cmd+=binary
        srun_process=Popen(run_cmd,shell=True)
        # Wait for the command to finish
        run_process.communicate()

                        
    def _slurm_run(self,frequency):
        """ Run slurm job with profiling """

        profile_cmd=""
        for prof in self.profilers :
            profile_cmd+=prof.get_profile_cmd()

        slurm_ntasks=os.environ["SLURM_NTASKS"]
        with open("./lpprofiler.conf","w") as f_conf:
            f_conf.write("0-{} bash ./profile_cmd.sh %t".format(int(slurm_ntasks)-1))

        with open("./profile_cmd.sh","w") as f_cmd:
            f_cmd.write(profile_cmd.replace('%t','$1')+self.binary)
            

        srun_argument="--cpu_bind=cores,verbose"
        srun_cmd='chmod +x ./profile_cmd.sh; srun {} --multi-prog lpprofiler.conf'.format(self.launcher_args)
                        
        srun_process=Popen(srun_cmd,shell=True)
        # Wait for the command to finish
        srun_process.communicate()

    
    def run(self,frequency="99"):
        """ Run job with profiling """

        # Execute profiling possibly with parallel launcher.
        if (self.launcher=='srun'):
            self._slurm_run(frequency)
        elif (self.launcher=='std'):
            self._std_run(frequency)
        else :
            print("Unsupported launcher: "+self.launcher)
            exit

        # Calls to analyze
        for prof in self.profilers :
            prof.analyze()
            
                
    def report(self):
        """ Print profiling reports """
        
        for prof in self.profilers :
            prof.report()
                    
        # Combine global metrics to build new ones 
        for prof in self.profilers :
            self.global_metrics.update(prof.global_metrics)

        self._report_dgflops()
        self._report_mpi_usage()

    def _report_mpi_usage(self):
        if ("mpi_samples_prop" in self.global_metrics):
            mpi_samples_prop=self.global_metrics["mpi_samples_prop"]
            print ("Estimated mpi communication time : {:.2f} %".format(mpi_samples_prop))
    
    def _report_dgflops(self):

        print(self.global_metrics)
        
        if ("dflop_per_ins" in self.global_metrics )and\
           ("instructions" in self.global_metrics)and\
           ("cpu-clock" in self.global_metrics):
            
            dflop_per_ins=self.global_metrics["dflop_per_ins"]
            nb_ins=self.global_metrics["instructions"]
            cpu_clock=self.global_metrics["cpu-clock"]

            # cpu_clock is in ms and output in Gflops
            dgflops=(dflop_per_ins*nb_ins)/(cpu_clock*10**6)
            
            print ("Estimated Glops per core : {:.2f} Gflops".format(dgflops))
            

            
        
