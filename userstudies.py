#! /usr/bin/env python

from subprocess import call
import sys
import ballatsq

skencil_py 	= './skencil.py'
input_file 	= 'k1.sk'
geometry 	= '--geometry=1680x1000+0+0'
f_participant = '--participant='
f_task = '--f2='
f_technique = '--f3='
f_tasksize 	= '--f4='
f_trial 		= '--f1='
first_editing_phase = 3
n_trials = 1
#there are two sessions in experiment (cloning and editing)
#there are two phases within each
phases = [['a1d','a1t','a1e','a2d','a2t','a2e','b1d','b1t','b1e','b2d','b2t','b2e'],  
		  ['d1d','d1t','d1e','d2d','d2t','d2e'],
		  ['e1c','e1s','e2c','e2s','f1c','f1s','f2c','f2s',  'g1c','g1s','g2c','g2s','h1c','h1s','h2c','h2s','i1c','i1s','i2c','i2s']]

def do_tasks(participant_no, get_command_sequence = 0, skip_tasks = 0):
	total_tasks = 0
	l_s = ballatsq.ballatsq(len(phases)-1) #-1 because last one is not counter-balanced
	print "l_s=",l_s
	
	phase_order = l_s[(participant_no) % (len(phases)-1)] #-1 because last one is not counter-balanced
	
	phase_order.append(3) # we dont counter-balance third phase, because it is a different experiment
	print "phaseorder",phase_order
	for phase in phase_order:
		
		curr_phase = phases[phase-1]
	
		print "phase #",phase," started"
		if phase >= first_editing_phase:
			#let's add trials to the editing phase
			print "this is an editing phase, let's add some trials"
			phase_with_trials = []
			for i in curr_phase:
				for j in range(1,n_trials+1):
					phase_with_trials.append(i+str(j))
			print curr_phase
			print "tasks with trials",phase_with_trials
			curr_phase = phase_with_trials

		length = len(curr_phase)
		#print "LENGTH:",length,"c_phase:",curr_phase
		latin_square = ballatsq.ballatsq(length)
		order = latin_square[(participant_no-1) % length]
		print "order=",order
		

		###########################
		#first show the practise session
		##########################
		practise_instance = curr_phase[0]
		print "practise instance",practise_instance
		#practise should be made different from actual crap
		if phase == 1:			
			practise_instance = 'b1'
		elif phase == 2:
			practise_intance = 'practise_d' #make one with diff offset
		
		if phase >= first_editing_phase:
			#practise should be made different from actual crap
			practise_task_file = './participant_playground/gh.sk'
			string1 = str('v')
			string2 = str('w')
			if phase == 3:
				string1 = str('x')
				string2 = str('y')
			call([skencil_py,geometry,f_task+str(practise_instance[0]),f_technique+string1,f_tasksize+str('1'),f_trial+str('1'),practise_task_file])
			call([skencil_py,geometry,f_task+str(practise_instance[0]),f_technique+string2,f_tasksize+str('1'),f_trial+str('1'),practise_task_file])
			print "practise file=", practise_task_file
		
		else: #Cloning Tasks
			practise_task_file = './participant_playground/'+practise_instance[0]+practise_instance[1] +'.sk'
			if phase == 2:
				practise_task_file = './participant_playground/practise_d.sk'
				call([skencil_py,geometry,f_task+str(practise_instance[0]),f_technique+str('p'),practise_task_file])
				call([skencil_py,geometry,f_task+str(practise_instance[0]),f_technique+str('q'),practise_task_file])
			else:		
				call([skencil_py,geometry,f_task+str(practise_instance[0]),f_technique+str('p'),practise_task_file])
				#because ALT is used for both Smart Duplication and Direct Cloning, we call two practise session of different types
				call([skencil_py,geometry,f_task+str(practise_instance[0]),f_technique+str('q'),practise_task_file])
			print "practise file=", practise_task_file
		for i in order:
			total_tasks += 1
			instance = curr_phase[i-1]
			task = instance[0]
			tasksize = instance[1]
			technique = instance[2]
			trial = phase #there will be no trials this time, we record phase number
			task_file = './tasks_backup/'+task+tasksize +'.sk'
			if phase >= first_editing_phase:
				trial = instance[3]
				if task == 'e': #CHANGE THESE AS NECESSARY!
					task_file = './tasks_backup/gh.sk'
				elif task == 'f': #CHANGE THESE AS NECESSARY!
					task_file = './tasks_backup/i.sk'
				elif task == 'h' or task == 'g': #CHANGE THESE AS NECESSARY!
					task_file = './tasks_backup/gh.sk'
				elif task == 'i':
					task_file = './tasks_backup/i.sk'
            
			line = skencil_py+' ' + geometry+' '+f_participant+str(participant_no)+' '+f_trial+str(trial)+' '+f_task+(task)+' '+f_technique+str(technique)+' '+f_tasksize+str(tasksize)+' '+ task_file
			if get_command_sequence:
				print "task_no:",total_tasks,line 
			else:
				if skip_tasks <= total_tasks:
					print "task_no:",total_tasks,line
					user_file = './participant_save/'+str(participant_no)+'/'+'n' + str(participant_no) +'_trial'+ str(trial) + '_task' + str(task) + '_tech' + str(technique)+'_size' + str(tasksize) + '.sk'
					#copy the task file to the user directory first
					call(['cp',task_file,user_file])
					#run the task
					call([skencil_py,geometry,f_participant+str(participant_no),f_task+str(task),f_technique+str(technique),f_tasksize+str(tasksize),f_trial+str(trial),user_file])
		str_phase_end =  "Phase #" + str(phase) + " ended, ask for further instructions"
		raw_input(str_phase_end)  
		print "phase# ", phase,"total_tasks=",total_tasks
		

def main():
	#participants are counted from 1, not from 0
	length = len (sys.argv)
	if length < 2:
		print "usage: userstudies.py p c s\np = participant number (1...)\nc = do not do the user studies just generate the commands list to replay, in case something goes wrong (0 or 1)\ns = start from task s"
	elif length < 3:
		participant_no = int(sys.argv[1])
		do_tasks(participant_no)
	elif length < 4:
		participant_no = int(sys.argv[1])
		do_tasks(participant_no,int(sys.argv[2]))
	elif length < 5:
		participant_no = int(sys.argv[1])
		do_tasks(participant_no,0,int(sys.argv[3]))
		

main()