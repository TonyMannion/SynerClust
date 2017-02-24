#!/usr/bin/env python

import sys
import os
import NJ
import pickle
import networkx as nx
import numpy
import logging
import subprocess
import argparse
import time

DEVNULL = open(os.devnull, 'w')


def usage():
	print """From the rough cluster trees generated by WF_MakeRoughClusters, refine clusters so that all duplication events (paralogs) \
	occur after speciation from the most recent common ancestor or MRCA, which is [node]. [node_dir] is the directory that contains all \
	data about [node]. [flow_id] refers to a step in the workflow; [jobs_per_cmd] is the number of consensus sequence computations \
	distributed to a single node.

	[alpha], [gamma], [gain], and [loss] are parameters that impact the rooting of a tree

	WF_RefineClusters.py [node_dir] [flow_id] [jobs_per_cmd] [node] [alpha] [gamma] [gain] [loss] [children...]
	"""
	sys.exit(1)


def main():
	usage = "usage: WF_RefineCluster_leaf_centroid_newmatrix.py [options]"
	parser = argparse.ArgumentParser(usage)
	parser.add_argument('-dir', dest="node_dir", required=True, help="Path to the \"nodes\" folder. (Required)")
	parser.add_argument('-node', dest="node", required=True, help="Current node name. (Required)")
	parser.add_argument('-alpha', type=float, dest="alpha", required=True, help="Homology weight. (Required)")
	parser.add_argument('-beta', type=float, dest="beta", required=True, help="Synteny weight. (Required)")
	parser.add_argument('-gamma', type=float, dest="gamma", required=True, help="Gain/Loss weight. (Required)")
	parser.add_argument('-gain', type=float, dest="gain", required=True, help="Duplication rate for Poisson distribution. (Required)")
	parser.add_argument('-loss', type=float, dest="loss", required=True, help="Deletion rate for Poisson distribution. (Required)")
	parser.add_argument('children', nargs=2, help="Children nodes. (Required)")
	args = parser.parse_args()

	repo_path = args.node_dir[:-6]
	mrca = args.node

	my_dir = args.node_dir + mrca + "/"

	if "CLUSTERS_REFINED" in os.listdir(my_dir):
		sys.exit(0)

	FORMAT = "%(asctime)-15s %(levelname)s %(module)s.%(name)s.%(funcName)s at %(lineno)d :\n\t%(message)s\n"
	logger = logging.getLogger()
	logging.basicConfig(filename=my_dir + 'RefineClusters_leaf_centroid.log', format=FORMAT, filemode='w', level=logging.DEBUG)
	# add a new Handler to print all INFO and above messages to stdout
	ch = logging.StreamHandler(sys.stdout)
	ch.setLevel(logging.INFO)
	logger.addHandler(ch)
	logger.info('Started')

	TIMESTAMP = time.time()

	# read trees, resolve clusters
	# tree_dir = my_dir + "trees/"
	cluster_dir = my_dir + "clusters"
	if "clusters" in os.listdir(my_dir):
		if "old" not in os.listdir(my_dir):
			os.system("mkdir " + my_dir + "old")

		os.system("mv -f " + cluster_dir + "/ " + my_dir + "old/")
	os.system("mkdir " + cluster_dir)
	cluster_dir = cluster_dir + "/"

	cluster_counter = 1  # used to number clusters
	synteny_data = {}
	pickleSeqs = {}
	pickleToCons = {}
	singletons_pep = {}
	pickleMaps = {}
	# picklePeps = {}
	childrenpkls = {}
	children_cons = {}
	# print "last_tree", last_tree
	# load locus_mapping files from children
	for c in args.children:
		mapFile = args.node_dir + c + "/locus_mappings.pkl"
		pklFile = open(mapFile, 'rb')
		pickleMaps[c] = pickle.load(pklFile)
		pklFile.close()
		synFile = args.node_dir + c + "/synteny_data.pkl"
		pklFile = open(synFile, 'rb')
		synteny_data[c] = pickle.load(pklFile)
		pklFile.close()
		if c[0] == "L":
			with open(args.node_dir + c + "/" + c + ".pkl", "r") as f:
				childrenpkls[c] = pickle.load(f)
			children_cons[c] = childrenpkls[c]
		else:  # c[0] == "N"
			with open(args.node_dir + c + "/pep_data.pkl", "r") as f:
				childrenpkls[c] = pickle.load(f)
			with open(args.node_dir + c + "/singletons_pep_data.pkl", "r") as f:
				childrenpkls[c].update(pickle.load(f))
			with open(args.node_dir + c + "/consensus_data.pkl", "r") as f:
				children_cons[c] = pickle.load(f)

# 	old_orphans = open(tree_dir + "orphan_genes.txt", 'r').readlines()
# 	orphans = open(tree_dir + "orphan_genes.txt", 'r').readlines()
	orphans = []
	ok_trees = []

	with open(repo_path + "nodes/" + args.node + "/trees/gene_to_cluster.pkl", "r") as f:
		gene_to_cluster = pickle.load(f)
	with open(repo_path + "nodes/" + args.node + "/trees/cluster_to_genes.pkl", "r") as f:
		cluster_to_genes = pickle.load(f)

	muscle_cmd = ["#MUSCLE_PATH", "-maxiters", "2", "-diags", "-sv", "-distance1", "kbit20_3", "-quiet"]
	# muscle_cmd = ["/Users/cgeorges/Work/Tools/muscle3.8.31_i86darwin64", "-maxiters", "2", "-diags", "-sv", "-distance1", "kbit20_3", "-quiet"]
	fasttree_cmd = ["#FASTTREE_PATH", "-quiet", "-nosupport"]
	# fasttree_cmd = ["/Users/cgeorges/Work/Tools/FastTreeDouble", "-quiet", "-nosupport"]
	ok_trees = []

	logger.debug("Loading files took " + str(time.time() - TIMESTAMP))
	TIMESTAMP = time.time()

# 	for clusterID in pickleSeqs:
	for cluster in cluster_to_genes:
		if len(cluster_to_genes[cluster]) == 1:
			orphans.append(cluster_to_genes[cluster][0])
			continue
# 		if len(pickleSeqs[clusterID]) == 1:
# 			orphans.append(pickleSeqs[clusterID][0].split(";")[0][1:])
# 			continue

		stdin_data = ""
		lengths = {}
# 		add_to_stdin = ""
# 		for gene in cluster_to_genes[cluster]:
# 			stdin_data += ">" + gene + "\n"
# 			stdin_data += childrenpkls[gene] + "\n"
		for gene in cluster_to_genes[cluster]:
			# stdin_data += ">" + gene + "\n"
			stdin_data += ">" + gene + "\n"
			try:
				if args.children[0][0] == "L":
					stdin_data += childrenpkls[args.children[0]][gene] + "\n"
					lengths[gene] = len(childrenpkls[args.children[0]][gene])
				else:
					stdin_data += childrenpkls[args.children[0]][gene][0].split("\n")[1] + "\n"
					lengths[gene] = len(childrenpkls[args.children[0]][gene][0].split("\n")[1])
			except KeyError:
				if args.children[1][0] == "L":
					stdin_data += childrenpkls[args.children[1]][gene] + "\n"
					lengths[gene] = len(childrenpkls[args.children[1]][gene])
				else:
					stdin_data += childrenpkls[args.children[1]][gene][0].split("\n")[1] + "\n"
					lengths[gene] = len(childrenpkls[args.children[1]][gene][0].split("\n")[1])

		process = subprocess.Popen(muscle_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=DEVNULL)
		output = process.communicate(stdin_data)[0]
		process = subprocess.Popen(fasttree_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=DEVNULL)
		output = process.communicate(output)[0]
		# if (len(locus_mapping[cluster]) > 5):

		logger.debug("Built fasttree for " + cluster + " in " + str(time.time() - TIMESTAMP))
		TIMESTAMP = time.time()
		logger.debug(output + "\n\n")
		# tree = NJ.NJTree("", "", node, alpha, beta, gamma, gain, loss)

		graph = nx.Graph()
		counter = 1
		leaves = []
		while(True):
			r = output.find(")")
			l = output[:r].rfind("(")

			children_string = output[l + 1:r].split(",")
			if len(children_string) == 1:
				if len(graph.nodes()) == 0:
					ok_trees.append(output.split(":")[0][1:])
				break
			group = "node" + str(counter)
			counter += 1

			new_length = 0
			if group not in graph.nodes():  # isn't it always a new node?
				graph.add_node(group)
			for child in children_string:
				child = child.split(":")
				if child[0] not in graph.nodes():
					graph.add_node(child[0])
					leaves.append(child[0])
				graph.add_edge(group, child[0], dist=(float(child[1]) * lengths[child[0]]))  # child[1] is a rate, so scaling based on sequence length
				new_length += lengths[child[0]]
			lengths[group] = new_length / 2
			output = output[:l] + group + output[r + 1:]

		leaves.sort()
		cluster_to_genes[cluster].sort()
		if leaves != cluster_to_genes[cluster]:
			logger.critical("leaves:\n%s\ngenes:\n%s\nstdin_data:\n%s\n" % (leaves, cluster_to_genes[cluster], stdin_data))

		logger.debug("Read fasttree for " + cluster + " in " + str(time.time() - TIMESTAMP))
		TIMESTAMP = time.time()

		leaves.sort()
		syn = {}
		for n in leaves:  # genes
			syn[n] = []
			leaf = "_".join(n.split("_")[:-1])
			for m in synteny_data[leaf][n]['neighbors']:
				syn[n].append(gene_to_cluster[m])

		hom_matrix = numpy.empty(len(leaves) * (len(leaves) - 1) / 2)
		syn_matrix = numpy.empty(len(leaves) * (len(leaves) - 1) / 2)
		i = 1
		pos = 0
		# max_neighbors_count = max([len(syn[k]) for k in syn])
		longest_hom = float("-Inf")
		for m in leaves[1:]:
			syn_m = set(syn[m])
			mSeqs = len(syn[m])
# 			for n in graph.nodes():
			for n in leaves[:i]:
				hom_matrix[pos] = nx.shortest_path_length(graph, n, m, "dist")
				if hom_matrix[pos] > longest_hom:
					longest_hom = hom_matrix[pos]
				nSeqs = len(syn[n])
				matches = 0
				if mSeqs == 0 or nSeqs == 0:
					syn_matrix[pos] = 1.0  # no neighbors in common if someone has no neighbors  # -= 0 ? does it change anything?
					pos += 1
					continue
				all_neighbors = syn_m & set(syn[n])
				for a in all_neighbors:
					t_m = max(syn[m].count(a), 0)
					t_n = max(syn[n].count(a), 0)
					matches += min(t_m, t_n)
				synFrac = float(matches) / float(max(mSeqs, nSeqs))  # why mSeqs and not len(syn_m) which is a set that removes duplicates?
				# synFrac = float(matches) / float(max_neighbors_count)  # why mSeqs and not len(syn_m) which is a set that removes duplicates?
				syn_matrix[pos] = 1.0 - synFrac
				pos += 1
			i += 1
		if longest_hom > 0.0:  # to prevent dividing by zero
			for pos in xrange(len(hom_matrix)):
				hom_matrix[pos] /= longest_hom

		logger.debug("Built matrices for " + cluster + " in " + str(time.time() - TIMESTAMP))
		# formatting matrices for output
		i = 0
		j = 1
		hom_buff = leaves[0] + "\n" + leaves[1] + "\t"
		syn_buff = leaves[0] + "\n" + leaves[1] + "\t"
		for x, y in numpy.nditer([hom_matrix, syn_matrix]):
			hom_buff += str(x) + "\t"
			syn_buff += str(y) + "\t"
			i += 1
			if i >= j:
				i = 0
				j += 1
				if j < len(leaves):
					hom_buff += "\n" + leaves[j] + "\t"
					syn_buff += "\n" + leaves[j] + "\t"
				else:
					hom_buff += "\n"
					syn_buff += "\n"
		logger.debug("Homology matrix for " + cluster + ":\n" + hom_buff)
		logger.debug("Synteny matrix for " + cluster + ":\n" + syn_buff)
		TIMESTAMP = time.time()

		# Root, evaluate and split every tree until all trees are OK
		unchecked_trees = []
		# Could probably replace these lines by directly reading the distance matrix file into the list without needing to create a NJ.NJTree
# 			myTree = NJ.NJTree(hom_mat, syn_mat, mrca, alpha, beta, gamma, gain, loss)
		myTree = NJ.NJTree(mrca, args.alpha, args.beta, args.gamma, args.gain, args.loss)
		myTree.buildGraphFromNewDistanceMatrix(hom_matrix, syn_matrix, leaves)

		logger.debug("Built NJtree for " + cluster + " in " + str(time.time() - TIMESTAMP) + "\n" + "\n".join([e[0] + " " + e[1] + " " + str(myTree.graph[e[0]][e[1]]['homology_dist']) + " " + str(myTree.graph[e[0]][e[1]]['synteny_dist']) for e in myTree.graph.edges()]))

		TIMESTAMP = time.time()

# 		myTree = NJ.NJTree(tree_file, syn_file, mrca, alpha, beta, gamma, gain, loss)
		# If "false" refers to orphan status, why are there also both "true" and "orphan"?
		unchecked_trees.append((myTree, False))
		while len(unchecked_trees) > 0:
			this_tree = unchecked_trees.pop()
			myTree = this_tree[0]
			isOrphan = this_tree[1]
# 				myTree = NJ.NJTree("filler", syn_mat, mrca, alpha, beta, gamma, gain, loss)
			# single node tree genes are added to orphans
			if isOrphan == "orphan":
				logger.critical("Need to handle orphan case")
# 				for n in nodes:  # can there be more than one node if it's an orphan? If not, can use nodes[0] and assert len(nodes) == 0
# 					o = n[1].split(":")[0]
# 					o = o.replace("(", "")
# 					orphans.append(o)
#					last_tree = "orphan"
				continue
			# multiple node trees continue
			else:
				# bigNode = myTree.buildGraphFromDistanceMatrix(uTree)
				myleaves = myTree.bigNode.split(";")
				mysources = set([])  # sources are the child species contributing to this tree
				for m in myleaves:
					mysources.add("_".join(m.split("_")[:-1]))
				# a valid tree has genes from both children, single source trees are broken into individual genes and added to the orphan list
				if len(mysources) == 1:
					for m in myleaves:
						orphans.append(m)
				# if the tree has >1 source, it is rooted and evaluated
				else:
					root = myTree.rootTree()
					logger.debug("Root for " + cluster + " is: " + "\t".join(root[1]))
					myTree.checkTree(root)
					# tree is valid, added to resolved clusters
					if myTree.OK == "true" or myTree.OK == "parcimony":
						format_nodes = []
						#### TODO store rooted tree as newick string from graph
						for n in myTree.graph.nodes():
							if n.count(";") == 0:
								format_nodes.append(n)
						if myTree.OK == "true":
							ok_trees.append([format_nodes, myTree.getNewick(), True])
						else:  # parcimony
							ok_trees.append([format_nodes, myTree.getNewick(), False])
						logger.debug("Got some OKtree for " + cluster + " in " + str(time.time() - TIMESTAMP))
						TIMESTAMP = time.time()
					# tree is invalid, added to unchecked trees unless it is an orphan
					else:
						# additional orphan exit
						if myTree.OK == "orphan":
							unchecked_trees.append((NJ.NJTree.toNewick(myTree.graph).split("\n"), myTree.OK))
							# unchecked_trees.append((NJ.NJTree.splitNewTree(myTree), myTree.OK)) # need to return both subtrees + myTree.OK in list
						else:
							# (myNewicks, myMatrices) = myTree.splitTree(root)
							(new_trees, new_root_edges) = myTree.splitNewTree(root)
							# for m in myMatrices:
							for new_tree in new_trees:
								unchecked_trees.append((new_tree, myTree.OK))
							logger.debug("Split NJtree for " + cluster + " in " + str(time.time() - TIMESTAMP))
							TIMESTAMP = time.time()

	logger.debug("Finished processing " + cluster + " in " + str(time.time() - TIMESTAMP))
	TIMESTAMP = time.time()

	newPickleMap = {}  # this will turn into the locus mappings for this node
	newSyntenyMap = {}
	newNewickMap = {"children": [set(args.children)]}
	# special_pep = {}
	childToCluster = {}  # child gene/og --> og.id for this node

	for o in orphans:
		ok_trees.insert(0, [[o.rstrip()], [o.rstrip(), o.rstrip()], True])  #### TODO add tree here

	blast_pep = {}
	for c in args.children:
		my_blast_pep = open(my_dir + c + ".blast.fa", 'r').readlines()
		curBlast = ""
		curPep = ""
		for m in my_blast_pep:
			m = m.rstrip()
			if len(m) < 1:
				continue
			if m.find(">") > -1:
				if len(curBlast) > 0:
					blast_pep[curBlast].append(curPep)
					curPep = ""
				line = m[1:]
				curBlast = line.split(";")[0]
				if curBlast not in blast_pep:
					blast_pep[curBlast] = []
			else:
				curPep += m
				# blast_pep[curBlast] += m
		if len(curPep) > 0:
			blast_pep[curBlast].append(curPep)

	# make control files for consensus sequence formation
	# cons_cmds = []
	cons_pkl = {}
	singletons = cluster_dir + "singletons.cons.pep"
	singles = open(singletons, 'w')
	sum_stats = my_dir + "summary_stats.txt"
	sstats = open(sum_stats, 'w')
	for ok in ok_trees:  #### TODO check ok[2] for True (solved) or False (3 gene node to solve at next node)
		c = str(cluster_counter)
		clusterID = ""
		while len(c) < 6:
			c = "0" + c
		clusterID = mrca + "_" + c
		newPickleMap[clusterID] = []
		newSyntenyMap[clusterID] = {'count': 0, 'neighbors': [], 'children': []}

		# get list of leaf sequences to pull and organize in treeSeqs
		treeSeqs = {}
		tree_seq_count = 0
		# leafSeqs = {}
		child_leaves = {}
		taxa = set([])
		taxa_map = {}
		for g in ok[0]:
			child = "_".join(g.split("_")[:-1])
			newSyntenyMap[clusterID]['children'].append(g)
			childToCluster[g] = clusterID
			leafKids = pickleMaps[child][g]
			if child not in child_leaves:
				child_leaves[child] = 0
			child_leaves[child] += len(leafKids)
# TODO in this part, children pickle are opened every time, could probably only open each one
			for l in leafKids:
				newPickleMap[clusterID].append(l)
				lKid = "_".join(l.split("_")[:-1])
				taxa.add(lKid)
				if lKid not in taxa_map:
					taxa_map[lKid] = 0
				taxa_map[lKid] += 1
				if lKid not in pickleSeqs:
					seqFile = args.node_dir + lKid + "/" + lKid + ".pkl"
					pklFile = open(seqFile, 'rb')
					pickleSeqs[lKid] = pickle.load(pklFile)
					pklFile.close()
				seq = pickleSeqs[lKid][l]
				if seq not in treeSeqs:
					treeSeqs[seq] = []
				treeSeqs[seq].append(l)
				tree_seq_count += 1
				newSyntenyMap[clusterID]['count'] += 1
		newNewickMap[clusterID] = [ok[1], ok[2]]  ###### CHANGE ok[1] or change reading in ClusterPostProcessing

		my_lengths = []
		min_taxa = len(taxa)
		max_taxa = 0
		for tm in taxa_map:
			tm_val = taxa_map[tm]
			if tm_val > max_taxa:
				max_taxa = tm_val
			if tm_val < min_taxa:
				min_taxa = tm_val
		for seq in treeSeqs:
			for me in treeSeqs[seq]:
				my_lengths.append(len(seq))
		avg = numpy.average(my_lengths)
		std = numpy.std(my_lengths)
		std_avg = std / avg
		out_dat = [clusterID, str(len(my_lengths)), str(len(taxa)), str(min_taxa), str(max_taxa), str(min(my_lengths)), str(max(my_lengths)), str(avg), str(std), str(std_avg)]

# 		sys.exit()
		sstats.write("\t".join(out_dat) + "\n")

		if len(ok[0]) == 1:
			child = "_".join(ok[0][0].split("_")[:-1])
# 			seq = children_cons[child][ok[0][0]]
			seqs = {}
			if child[0] == "L":
				seqs[g] = children_cons[child][g]
			else:
				for seq in children_cons[child][g]:
					i = 0
					identifier = None
					for s in seq.rstrip().split("\n"):
						if not i % 2:
							identifier = s[1:].split(";")[0]
						else:
							seqs[identifier] = s
						i += 1
# 			else:
				# need to get list of sequences to write them all
			for k, s in seqs.iteritems():
				cons_pkl[clusterID] = [">" + clusterID + ";" + str(len(s)) + "\n" + s + "\n"]
				singletons_pep[clusterID] = [">" + clusterID + ";" + str(len(s)) + "\n" + s + "\n"]
				singles.write(">" + clusterID + ";" + str(len(s)) + "\n" + s + "\n")
		else:
			pickleToCons[clusterID] = []
			newNewickMap[clusterID].append([])
			for g in ok[0]:
				child = "_".join(g.split("_")[:-1])
				seqs = {}
				if child[0] == "L":
					seqs[g] = children_cons[child][g]
				else:
					for seq in children_cons[child][g]:
# 						if seq[0] == ">":  # else its a leaf so only sequence is present
						i = 0
						identifier = None
						for s in seq.rstrip().split("\n"):
							if not i % 2:  # not so that 0 is True
								identifier = s[1:].split(";")[0]
							else:
								seqs[identifier] = s
							i += 1
# 						else:
# 							seqs = [seq]
				i = 0
				for k, s in seqs.iteritems():
					pickleToCons[clusterID].append(">" + k + ";" + str(i) + ";" + str(len(s)) + "\n" + s + "\n")  # str(i) is a unique part in name so that all different names for muscle/fasttree
					newNewickMap[clusterID][2].append(">" + k + ";" + str(len(s)) + "\n" + s + "\n")
					i += 1
# 		if tree_seq_count == 1:
# 			for seq in treeSeqs:
# 				seqlen = str(len(seq))
# 				singles.write(">" + clusterID + ";" + seqlen + "\n" + seq + "\n")
# 			seq = treeSeqs.keys()[0]
# 			singletons_pep[clusterID] = [">" + clusterID + ";" + str(len(seq)) + "\n" + seq + "\n"]
# 		elif len(ok[0]) == 1:
# 			for bseq in blast_pep[ok[0][0]]:
# 				seqlen = str(len(bseq))
# 				singles.write(">" + clusterID + ";" + seqlen + "\n" + bseq + "\n")
# 			bseq = blast_pep[ok[0][0]][0]
# 			singletons_pep[clusterID] = [">" + clusterID + ";" + str(len(bseq)) + "\n" + bseq + "\n"]
# 		else:
# 			#  temp_pep = cluster_dir + clusterID + ".pep"
# 			#  pepOut = open(temp_pep, 'w')
# 			pickleToCons[clusterID] = []
# 			newNewickMap[clusterID].append([])
# 			for seq in treeSeqs:
# 				seqlen = str(len(seq))
# 				identifier = treeSeqs[seq][0]  # TODO output ALL IDs from seq because there might be more than a single ID, and this is NOT a .cons.pep file, just a .pep file
# # 				pepOut.write(">" + identifier + ";" + seqlen + "\n" + seq + "\n")
# # 				pickleToCons[clusterID].append(">" + identifier + ";" + seqlen + "\n" + seq + "\n")
# 				pickleToCons[clusterID].append(children_cons[child][g])
# 				newNewickMap[clusterID][2].append(">" + identifier + ";" + seqlen + "\n" + seq + "\n")
# 			pepOut.close()
		cluster_counter += 1
	singles.close()
	sstats.close()

	pklPep = my_dir + "pep_data.pkl"
	sdat = open(pklPep, 'wb')
	pickle.dump(pickleToCons, sdat)
	sdat.close()

	with open(my_dir + "singletons_pep_data.pkl", "w") as f:
		pickle.dump(singletons_pep, f)

	# update synteny data
	for clust in newSyntenyMap:
		for child in newSyntenyMap[clust]['children']:
			lc = "_".join(child.split("_")[:-1])
			# logger.debug("%s splitted to %s" % (child, lc))
			for neigh in synteny_data[lc][child]['neighbors']:
				# logger.debug("newSyntenyMap[%s]['neighbors'].append(childToCluster[%s]" % (clust, neigh))
				newSyntenyMap[clust]['neighbors'].append(childToCluster[neigh])
	# pickle synteny data
	pklSyn = my_dir + "synteny_data.pkl"
	sdat = open(pklSyn, 'wb')
	pickle.dump(newSyntenyMap, sdat)
	sdat.close()

	# pickle the locus mappings
	pklMap = my_dir + "locus_mappings.pkl"
	sdat = open(pklMap, 'wb')
	pickle.dump(newPickleMap, sdat)
	sdat.close()

	with open(my_dir + "clusters_newick.pkl", "w") as f:
		pickle.dump(newNewickMap, f)

	with open(my_dir + "consensus_data.pkl", "w") as f:
		pickle.dump(cons_pkl, f)
	# script complete call
	clusters_done_file = my_dir + "CLUSTERS_REFINED"
	cr = open(clusters_done_file, 'w')
	cr.write("Way to go!\n")
	cr.close()


if __name__ == "__main__":
	main()
