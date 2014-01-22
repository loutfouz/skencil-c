#! /usr/bin/env python

from subprocess import call
import sys

geometry 	= '--geometry=1680x1000+0+0'

def main():
	#participants are counted from 1, not from 0
	length = len (sys.argv)
	session = None
	if length < 2:
		print "usage: ./practise.py a|b|c|d|e|f|g|h|i|j|k"
		return
	elif length < 3:
			session = sys.argv[1]
	else: 
		return
	#for practise we only open the 1st condition for each session
	task_file = './participant_playground/'+session+str(1) +'.sk'
	print "ok"
	call(['./skencil.py',geometry,task_file])
	
main()