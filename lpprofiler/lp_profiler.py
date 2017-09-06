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
import lpprofiler.valgrind_memory_profiler as vmp
import sys, os, stat, re, datetime
#from jinja2 import Template


class LpProfiler :
    
    def __init__(self,launcher,pid,rank,binary,profiling_args):

        # Launcher name (ex: srun)
        self.launcher=launcher

        # Pid and rank of the processus to profile
        self.pid_to_profile=pid
        self.proc_rank=rank

        # If parallel rank is not given use pid as rank in output files
        if not self.proc_rank:
            self.proc_rank=pid

        # Binary to profile
        self.binary=binary

        # Profiling options (TODO: should be customizable at launch )
        self.profiling_flavours=["asm_prof","hwcounters_prof"]

        self.global_metrics={}

        today=datetime.datetime.today()
        self.traces_directory="PERF_{}".format(today.isoformat())

        os.mkdir(self.traces_directory)
        
        # Build profilers
        if (self.launcher)and('srun' in self.launcher):
            trace_samples="./{}/perf.data_%t".format(self.traces_directory)
            trace_hwc="./{}/perf.stats_%t".format(self.traces_directory)
            output_samples=["./{}/perf.data_0".format(self.traces_directory)]
            output_hwc=["./{}/perf.stats_0".format(self.traces_directory)]
        elif (self.launcher=='std'):
            trace_samples="./{}/perf.data".format(self.traces_directory)
            trace_hwc="./{}/perf.stats".format(self.traces_directory)
            output_samples=None
            output_hwc=None
        elif (self.pid_to_profile):
            trace_samples="./{}/perf.data_{}".format(self.traces_directory,self.proc_rank)
            trace_hwc="./{}/perf.stats_{}".format(self.traces_directory,self.proc_rank)
            output_samples=None
            output_hwc=None


        self.profilers=[
            php.PerfHWcountersProfiler(trace_hwc,output_hwc,profiling_args),\
            psp.PerfSamplesProfiler(trace_samples,output_samples,profiling_args)
        ]
            

    def _std_run(self):
        """ Run standard exe with perf profiling """

        run_cmd=''
        
        for prof in self.profilers :
            run_cmd+=prof.get_profile_cmd()
        
        run_cmd+=binary
        run_process=Popen(run_cmd,shell=True)
        # Wait for the command to finish
        run_process.communicate()

                        
    def _slurm_run(self):
        """ Run slurm job with profiling """

        profile_cmd=""
        for prof in self.profilers :
            profile_cmd+=prof.get_profile_cmd()

        slurm_ntasks=os.environ["SLURM_NTASKS"]
        with open("./{}/lpprofiler.conf".format(self.traces_directory),"w") as f_conf:
            f_conf.write("0-{} bash ./{}/profile_cmd.sh %t".format(int(slurm_ntasks)-1,self.traces_directory))

        with open("./{}/profile_cmd.sh".format(self.traces_directory),"w") as f_cmd:
            f_cmd.write(profile_cmd.replace('%t','$1')+self.binary)
            

        srun_argument="--cpu_bind=cores,verbose"
        srun_cmd='chmod +x ./{}/profile_cmd.sh; {} --multi-prog ./{}/lpprofiler.conf'.format(self.traces_directory,self.launcher,self.traces_directory)
                        
        srun_process=Popen(srun_cmd,shell=True)
        # Wait for the command to finish
        srun_process.communicate()

    def _pid_run(self):
        """ Profile a processus given its PID"""

        run_cmd=''
        
        for prof in self.profilers :
            run_cmd+=prof.get_profile_cmd(pid=self.pid_to_profile)

        # Use tail 
        run_cmd+=' tail --pid={} -f /dev/null'.format(self.pid_to_profile)

        print("Profiling command : {}".format(run_cmd))
        run_process=Popen(run_cmd,shell=True)
        
        # Wait for the command to finish
        run_process.communicate()


    
    def run(self):
        """ Run job with profiling """

        # Execute profiling possibly with parallel launcher.
        if self.launcher and ('srun' in self.launcher):
            self._slurm_run()
        elif (self.launcher=='std'):
            self._std_run()
        elif (self.pid_to_profile):
            self._pid_run()
        else:
            print("Unsupported launcher: "+self.launcher)
            exit

        # Calls to analyze
        for prof in self.profilers :
            prof.analyze()
            
                
    def report(self):
        """ Print profiling reports """
                    
        # Combine metrics from all profilers in a single dictionary.
        for prof in self.profilers :
            self.global_metrics.update(prof.global_metrics)

        # Raw print (TODO use templates)
        print("-------------------------------------------------------")
        self._report_elapsedtime()
        print("-------------------------------------------------------")
        self._report_inspercycle()
        print("-------------------------------------------------------")
        self._report_dgflops()
        print("-------------------------------------------------------")
        self._report_vectorisation()
        print("-------------------------------------------------------")
        self._report_tlbmiss_cost()
        print("-------------------------------------------------------")
        self._report_mpi_usage()
        print("-------------------------------------------------------")

        # print(_render('../templates/default.out',metrics=self.global_metrics))

        # Reporting that are internal to profilers and may not be stored in
        # a dictionnary.
        for prof in self.profilers :
            prof.report()

        

    # def _render(tpl_path, context):
    #     path, filename = os.path.split(tpl_path)
    #     return jinja2.Environment(
    #         loader=jinja2.FileSystemLoader(path or './')
    #     ).get_template(filename).render(context)
                    

    def _report_elapsedtime(self):
        if ("cpu-clock" in self.global_metrics) :
            cpu_clock_s=self.global_metrics["cpu-clock"]/1000
            print("Elapsed time: {:.2f}s".format(cpu_clock_s))

    def _report_inspercycle(self):
        """ Compute and print instruction per cycle ratio"""
        if ("instructions" in self.global_metrics) and ("cycles" in self.global_metrics) :
            nb_ins=self.global_metrics["instructions"]
            nb_cycles=self.global_metrics["cycles"]

            print("Instructions per cycle: {:.2f}".format(nb_ins/nb_cycles))

    def _report_tlbmiss_cost(self):
        """ Compute and print cycles spent in the page table walking caused by TLB miss """
        
        if ("dTLBmiss_cycles" in self.global_metrics) and ("iTLBmiss_cycles" in self.global_metrics) :
            nb_pagewalk_cycles=self.global_metrics["iTLBmiss_cycles"]+self.global_metrics["dTLBmiss_cycles"]
            nb_cycles=self.global_metrics["cycles"]
            
            print("Percentage of cycles spent in page table walking caused by TLB miss: {:.2f} ".format((nb_pagewalk_cycles*100)/nb_cycles)+'%')


    def _report_vectorisation(self):
        if 'avx_prop' in self.global_metrics:
            print("Percentage of floating point AVX instructions: {:.2f} %".format(self.global_metrics['avx_prop']))
        if 'avx2_prop' in self.global_metrics:
            print("Percentage of floating point AVX2 instructions: {:.2f} %".format(self.global_metrics['avx2_prop']))
        if 'vec_prop' in self.global_metrics:            
            print("Floating point operations vectorisation ratio: {:.2f} %".format(self.global_metrics['vec_prop']))
            
            
    def _report_mpi_usage(self):
        if ("mpi_samples_prop" in self.global_metrics):
            mpi_samples_prop=self.global_metrics["mpi_samples_prop"]
            print ("Estimated MPI communication time: {:.2f} %".format(mpi_samples_prop))

    def _report_dgflops(self):
        if ("dflop_per_ins" in self.global_metrics )and\
           ("instructions" in self.global_metrics)and\
           ("cpu-clock" in self.global_metrics):
            
            dflop_per_ins=self.global_metrics["dflop_per_ins"]
            nb_ins=self.global_metrics["instructions"]
            cpu_clock=self.global_metrics["cpu-clock"]

            # cpu_clock is in ms and output in Gflops
            dgflops=(dflop_per_ins*nb_ins)/(cpu_clock*10**6)
            
            print ("Estimated Gflops per core: {:.2f} Gflops".format(dgflops))
            

            
        
