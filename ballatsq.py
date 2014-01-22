def transposed(lists):
   if not lists: return []
   return map(lambda *row: list(row), *lists)
   
def ballatsq(size):
	first_row = [1,2]
	j = size
	for i in range(size,2,-2):
		first_row.append(j)
		j-=1
	j = 3
	for i in range(3,size,2):
		first_row.insert(i,j)
		j+=1
	#initial values were generated, 
	#now let's fill these rows using circular shift
	bls = []
	for i in range(0,size):
		bls.append([first_row[i]])
		for j in range(0,size-1):
			next_val = 1+(bls[i][j])%(size) 
			bls[i].append(next_val)

	return transposed(bls)

if __name__ == '__main__':
	import sys
	length = len (sys.argv)
	if length == 2:
		M = ballatsq(int(sys.argv[1]))
		for i in M: print i
	else:
		print "usage: ballatsq.py n\nn=size of balanced latin square (must be even)"
