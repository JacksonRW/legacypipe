from __future__ import division, print_function
import h5py
from glob import glob
import numpy as np
import csv
import os

def read_dict(fn):
    d = {}
    for key, val in csv.reader(open(fn)):
        d[key] = val
    return d

def dobash(cmd):
    print('UNIX cmd: %s' % cmd)
    if os.system(cmd): raise ValueError

class GatherTraining(object):
    '''1 hdf5 with groups /star,qso,elg,lrg,back each being its own data set'''
    def __init__(self,fns_dict=None,
                 data_dir=None,rank=None):
        '''
        fns_dict -- dict of fn lists for each objtype, e.g. fns_dict['elg']= list of filename
        rank -- optional, use if mpi4py
        '''
        assert(not fns_dict is None)
        for obj in fns_dict.keys():
            assert(obj in ['elg','lrg','star','qso'])
        self.objs= list(fns_dict.keys())
        #
        if data_dir is None:
            self.data_dir= os.getenv('DECALS_SIM_DIR')
        else:
            self.data_dir= data_dir
        #
        if rank is None:
            self.hdf5_fn= os.path.join(self.data_dir,"training_gathered.hdf5")
        else: # mpi4py 
            self.hdf5_fn= os.path.join(self.data_dir,"training_gathered_%d.hdf5" % rank)

    def get_grzSets(self):
        for obj in self.objs:
            self.grzSets(obj=obj)

    def grzSets(self, obj=None):
        print('Getting grzSets for obj=%s' % obj)
        # Read/write if exists, create otherwise (default)
        fobj= h5py.File(self.hdf5_fn,'a')
        write_node= '%s' % obj
        # Are we already done?
        if write_node in list( fobj.keys() ):
            print('Already exists: node %s in file %s' % (write_node,self.hdf5_fn)) 
        # Load in the data
        else:
            # Wildcard for: elg/138/1381p122/rowstart0/elg_1381p122.hdf5
            fns= glob( os.path.join(self.data_dir,'%s/*/*/rowstart0/%s*.hdf5' % (obj,obj)) )
            assert(len(fns) > 0)
            fns= fns[:2] #glob( os.path.join(self.data_dir,'%s/*/*/rowstart0/%s*.hdf5' % (obj,obj)) )
            #n_sets= self.numberGrzSets(fns=fns)
            # Data Arrays
            #print('%s dataset has shape: (%d,64,64,3)' % (obj,n_sets))
            data= [] #np.zeros((n_sets,64,64,3))+np.nan   
            if obj == 'elg': 
                data_back= [] #data.copy() 
            # Fill Data Arrays
            num=0L 
            for fn in fns:
                f= h5py.File(fn,'r')
                for id in list(f.keys()):
                    num_bands= len(f['/%s' % id].keys())
                    if num_bands == 3:
                        # At least one grz set
                        ccdnames={}
                        for band in ['g','r','z']:
                            ccdnames[band]= list( f['/%s/%s' % (id,band)].keys() )
                        num_passes= min([ len(ccdnames['g']),\
                                        len(ccdnames['r']),\
                                        len(ccdnames['z'])])
                        for ith_pass in range(num_passes):
                            grz_tmp= np.zeros((64,64,3))+np.nan
                            if obj == 'elg':
                                grz_back_tmp = grz_tmp.copy()
                            for iband,band in zip(range(3),['g','r','z']):
                                    dset= f['/%s/%s/%s' % (id,band,ccdnames[band][ith_pass])]
                                    grz_tmp[:,:,iband]= dset[:,:,0] # Stamp
                                    if obj == 'elg':
                                        grz_back_tmp[:,:,iband]= dset[:,:,1] # Background
                            data += [grz_tmp]
                            if obj == 'elg':
                                data_back += [grz_back_tmp]
                            num += 1
                            if num % 20 == 0:
                                print('grzSets: Read in num=%d' % num)
            # List --> numpy
            data= np.array(data)
            assert(np.all(np.isfinite(data)))
            if obj == 'elg':
                data_back= np.array(data_back)
                assert(np.all(np.isfinite(data_back)))
            # 
            print('%s dataset has shape: ' % obj,data.shape)
            # Save
            dset = fobj.create_dataset(write_node, data=data,chunks=True)
            print('Wrote node %s in file %s' % (write_node,self.hdf5_fn)) 
            if obj == 'elg':
                node= '%s' % 'back'
                dset = fobj.create_dataset(node, data=data_back,chunks=True)
                print('Wrote node %s in file %s' % (node,self.hdf5_fn)) 
 
    def readData(self):
        '''return hdf5 file object containing training data'''
        return h5py.File(self.hdf5_fn,'r')

if __name__ == '__main__':
    gather= GatherTraining()
    gather.get_grzSets()
    f= gather.readData()
    raise ValueError
    print('done')
