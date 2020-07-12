import importlib
import setup_nx # your own module, setup.nx.py
import numpy as np
import math as m
import statistics as st
import cmath
import matplotlib.pyplot as plt 
import itertools
from operator import add
importlib.reload(setup_nx)
from setup_nx import *
from graphviz import Source, render

import datetime
import time

import my_feeder_funcs as ff
import my_impedance_funcs as imp
import my_configVis_funcs as vis
import my_detControlMatExistence_funcs as ctrl
import my_detLznRange_funcs as lzn


'DO NOT NEED TO EDIT THIS CELL BEFORE RUNNING'
# See pseudocode doc for more complete descriptions of each method:
# https://docs.google.com/document/d/1VdYNN96FhywGcb0QNml61C8GLlIXbs8bU1Bh2cINPt0/edit

def get_path_to_substation(feeder, node,depths):
    #returns list of edges, not impedances, between node and substation
    #node = node name as string
    #feeder = initiaized feeder object
    graph = feeder.network
    node_path = []
    current_node = node
    
    for i in range(depths[node]):
        pred_node = list(graph.predecessors(current_node)) #retrieves parent node of current_node
        node_path += [(current_node, pred_node[0])]
        current_node = pred_node[0]
    return node_path


def createRXmatrices(feeder, node_index_map,depths):
    #calculated using phase A impedances unless there is no phase A then phase B else phase C
    #feeder = initiaized feeder object
    #node_index_map = dictionary of node indices with node names as keys
    graph = feeder.network
    n = len(graph.nodes) #number of nodes
    R = np.zeros((n,n)) #initializing R matrix
    X = np.zeros((n,n)) #initializing X matrix
    P = {} #initializing line path dictionary
   
    for node in graph.nodes:
        P[node] = get_path_to_substation(feeder, node,depths)
    
    for n_outer in graph.nodes: #outer loop
        index_outer = node_index_map[n_outer]
        
        for n_inner in graph.nodes: #inner loop
            index_inner = node_index_map[n_inner]
            intersection_set = set.intersection(set(P[n_outer]), set(P[n_inner])) #finds common edges in paths from node to substation
            intersection_list = list(intersection_set)
            r_sum = 0
            x_sum = 0
            
            for edge in intersection_list: #iterates through shared edges and sums their impedances
                tot_edge_impedance = imp.get_total_impedance_between_two_buses(feeder, edge[0], edge[1],depths)
                
                if tot_edge_impedance['Phase 1']:
                    phase_edge_impedance = tot_edge_impedance['Phase 1']
                elif tot_edge_impedance['Phase 2']:
                    phase_edge_impedance = tot_edge_impedance['Phase 2']
                else:
                    phase_edge_impedance = tot_edge_impedance['Phase 3']  
                    
                r_sum += phase_edge_impedance.real
                x_sum += phase_edge_impedance.imag
            R[index_outer][index_inner] = 2*r_sum
            X[index_outer][index_inner] = 2*x_sum
            
    return R, X


def createRXmatrices_3ph(feeder, node_index_map,depths):
    #includes all 3 phases
    #feeder = initiaized feeder object
    #node_index_map = dictionary of node indices with node names as keys
    graph = feeder.network
    n = len(graph.nodes) #number of nodes
    R = np.zeros((3*n, 3*n)) #initializing R matrix
    X = np.zeros((3*n, 3*n)) #initializing X matrix
    P = {} #initializing line path dictionary
   
    for node in graph.nodes:
        P[node] = get_path_to_substation(feeder, node,depths)
    
    for n_outer in graph.nodes: #outer loop
        index_outer = node_index_map[n_outer]
        
        for n_inner in graph.nodes: #inner loop
            index_inner = node_index_map[n_inner]
            intersection_set = set.intersection(set(P[n_outer]), set(P[n_inner])) #finds common edges in paths from node to substation
            intersection_list = list(intersection_set)
            imped_sum = np.zeros((3,3))
            imped_sum = imped_sum.astype('complex128')
            
            for edge in intersection_list: #iterates through shared edges and sums their impedances
                impedance = feeder.network.get_edge_data(edge[1], edge[0], default=None)['connector']
                tot_edge_impedance = impedance.Z if isinstance(impedance, setup_nx.line) else np.zeros((3,3)) 
                imped_sum += tot_edge_impedance
            
            for i_row in range(3):
                
                for i_col in range(3):
                    R[i_row * index_outer][i_col * index_inner] = 2 * imped_sum[i_row][i_col].real
                    X[i_row * index_outer][i_col * index_inner] = 2 * imped_sum[i_row][i_col].imag
            
    return R, X


def createNodeIndexMap(feeder):
    #indexes assigned based on numerical value of node, not node's possition in the network
    #for example, the node named with the lowest numerical value will map to 0, not the substation
    #feeder = initiaized feeder object
    graph = feeder.network
    node_index_map = {} #node indices for indicMat and F matrix
    t = 0 #initializing first index for node_index_map
    
    for node in graph.nodes: #populating node_idex_map
        node_index_map[node] = t
        t += 1
    return node_index_map


def getKey(dictionary, value):
    #use to retrieve node name from node_index_map using node index
    #value = node index
    for k, v in dictionary.items(): 
         if value == v:
                key = k
    return key 


def setupStateSpace(n, feeder, node_index_map,depths):
    #n = number of nodes in network
    #feeder = initiaized feeder object
    #node_index_map = dictionary of node indices with node names as keys
    A = np.identity(6*n)
    R, X = createRXmatrices(feeder, node_index_map,depths)
    concat_XR = np.concatenate((X, R), axis = 1)
    concat_XR_halfs = np.concatenate(((-1/2) * R, (1/2) * X), axis = 1)
    B = np.concatenate((concat_XR, concat_XR_halfs))
    return A, B


#def computeFeas(feeder, perf_node, A, B, indicMat):
    #node_1 = list(feeder.network.successors(substation_name))
    #z12 = get_total_impedance_from_substation(feeder, node_1[0])['Phase 1']
    #matExist = detControlMatExistence(A, B, indicMat)
    #maxLznError = detLznRange(feeder, Vbase_ll, Sbase, z12, perf_node)
    #return matExist, maxLznError
    
    
def computeFeas(feeder, act_locs, perf_nodes, A, B, indicMat):
    random_bit = np.random.choice(2,1)
    if random_bit[0] == 0:
        feas = True
    else:
        feas = False
    maxError = 10
    return feas, maxError


def updateStateSpace(n, act_locs, perf_nodes, node_index_map):
    #creates (2n*2n) matrix with 1 and ij and (i+n)(j+n) if there is an actuator at i tracking a performance node at j, and 0 otherwise
    #n = number of nodes in network
    #act_locs = list of actuators locations in network (list of strings)
    #perf_node = performance node as string
    #node_index_map = dictionary of node indices for indicMat and F matrix
    indicMat = np.zeros((2*n,2*n))
    perf_index = node_index_map[perf_nodes]
    for act in act_locs: 
        act_index = node_index_map[act]
        indicMat[act_index][perf_index] = 1
        indicMat[act_index+n][perf_index+n] = 1
    return indicMat
    
    
def markActLoc(graph, act_loc):
    #changes color of nodes with set actuators to turquoise
    #graph = networkx graph object (feeder.network)
    #act_loc = node name as string where actuator is placed
    graph.nodes[act_loc]['style'] = 'filled'
    graph.nodes[act_loc]['fillcolor'] = 'turquoise'
    return
        

def markFeas(feas, test_act_loc, graph):
    #if controllability can be achieved with actuator at test_act_loc then mark green, otherwise mark red
    #feas = True or False
    #test_act_loc = node name as string
    #graph = networkx graph object (feeder.network)
    graph.nodes[test_act_loc]['style'] = 'filled'
   
    if feas:
        graph.nodes[test_act_loc]['fillcolor'] = 'green'
    else:
        graph.nodes[test_act_loc]['fillcolor'] = 'red'
    return


def make_indv_heatmap(feeder, all_act_locs, perf_nodes, node_index_map,depths):
    #all_act_locs and perf_node = lists of node names as strings
    graph = feeder.network
    n = len(graph.nodes) #number of nodes in network
    A, B = setupStateSpace(n, feeder, node_index_map, depths)
    lzn_error_run_sum = 0
    lst_feas_configs = []
    
    for act in all_act_locs: 
        markActLoc(graph, act)
            
    lzn_error_dic = {} #contains maxLznError for each choice of actuator location with node name as key  
    test_nodes = []
    for node in graph.nodes:
        if node not in all_act_locs:
            test_nodes.append(node)
    
    for test in test_nodes:
        indicMat = updateStateSpace(n, [test]+all_act_locs, perf_nodes, node_index_map)
        feas, maxError = computeFeas(feeder, [test]+all_act_locs, perf_nodes, A, B, indicMat)
        lzn_error_dic[test] = maxError
        markFeas(feas, test, graph)
        if feas:
            lst_feas_configs += [cur_act_locs + [test]]
        
    nx.nx_pydot.write_dot(graph, 'single_act_config_test_' + file_name)
    render('dot', 'png', 'single_act_config_test_' + file_name)   
    return lst_feas_configs


def runHeatMapProcess(feeder, all_act_locs, perf_nodes, node_index_map,depths):
    #all_act_locs and perf_nodes = lists of node names as strings
    a = 0
    graph = feeder.network
    cur_act_locs = []
    n = len(graph.nodes) #number of nodes in network
    A, B = setupStateSpace(n, feeder, node_index_map,depths)
    lzn_error_run_sum = 0
    lst_feas_configs = []
    
    while a <= len(all_act_locs): #outer loop
        for act in cur_act_locs: 
            markActLoc(graph, act)
            
        lzn_error_dic = {} #contains maxLznError for each choice of actuator location with node name as key  
        test_nodes = []
        for node in graph.nodes:
            if node not in cur_act_locs:
                test_nodes.append(node)
    
        for test in test_nodes: #inner loop
            indicMat = updateStateSpace(n, [test]+cur_act_locs, perf_nodes, node_index_map)
            feas, maxError = computeFeas(feeder, [test]+cur_act_locs, perf_nodes, A, B, indicMat)
            lzn_error_dic[test] = maxError
            markFeas(feas, test, graph)
            if feas:
                lst_feas_configs += [cur_act_locs + [test]]
        
        nx.nx_pydot.write_dot(graph, 'act_test_' + str(a) + '_' + file_name)
        render('dot', 'png', 'act_test_' + str(a) + '_' + file_name)
        a += 1
        
        if a <= len(all_act_locs):
            cur_act_locs = all_act_locs[0:a]
            lzn_error_run_sum += lzn_error_dic[cur_act_locs[-1]]
            print('The total max linearization error after '+ str(a) +' actuators have been placed = '+ str(lzn_error_run_sum))
    return lst_feas_configs, lzn_error_run_sum
    