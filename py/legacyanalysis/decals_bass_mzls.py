#!/usr/bin/env python

"""compare two tractor catalogues that should have same objects
"""

from __future__ import division, print_function

import matplotlib
matplotlib.use('Agg') #display backend
import os
import sys
import logging
import argparse
import numpy as np
from scipy import stats as sp_stats
#import seaborn as sns

import matplotlib.pyplot as plt

from astropy.io import fits

#import thesis_code.targets as targets
from legacyanalysis import targets 
from legacyanalysis.pathnames import get_outdir
from legacyanalysis.combine_cats import combine_and_match,DataSet

def bin_up(data_bin_by,data_for_percentile, bin_edges=np.arange(20.,26.,0.25)):
    '''finds indices for 0.25 bins, returns bin centers and q25,50,75 percentiles of data_percentile in each bin
    bin_edges: compute percentiles for each sample between bin_edges
    '''
    count= np.zeros(len(bin_edges)-1)+np.nan
    q25,q50,q75= count.copy(),count.copy(),count.copy()
    for i,low,hi in zip(range(len(count)), bin_edges[:-1],bin_edges[1:]):
        ind= np.all((low <= data_bin_by,data_bin_by < hi),axis=0)
        if np.where(ind)[0].size > 0:
            count[i]= np.where(ind)[0].size
            q25[i]= np.percentile(data_for_percentile[ind],q=25)
            q50[i]= np.percentile(data_for_percentile[ind],q=50)
            q75[i]= np.percentile(data_for_percentile[ind],q=75)
        else:
            pass #given qs nan, which they already have
    return (bin_edges[1:]+bin_edges[:-1])/2.,count,q25,q50,q75


def create_confusion_matrix(obj):
    '''compares MATCHED decam (truth) to bokmos (prediction)
    return 5x5 confusion matrix and colum/row names
    obj[m_decam'] is DECaLS object'''
    cm=np.zeros((5,5))-1
    types=['PSF','SIMP','EXP','DEV','COMP']
    for i_dec,dec_type in enumerate(types):
        ind= np.where(obj['m_decam'].data['type'] == dec_type)[0]
        for i_bass,bass_type in enumerate(types):
            n_bass= np.where(obj['m_bokmos'].data['type'][ind] == bass_type)[0].size
            if ind.size > 0: cm[i_dec,i_bass]= float(n_bass)/ind.size #ind.size is constant for each loop over bass_types
            else: cm[i_dec,i_bass]= np.nan
    return cm,types

class PlotKwargs(object):
    def __init__(self):
        self.ax=dict(fontweight='bold',fontsize='medium')
        self.text=dict(fontweight='bold',fontsize='medium',va='top',ha='left')
        self.leg=dict(frameon=True,fontsize='x-small')

class Plots_Cat_Comparison(object):
    '''common plots for comparing two tractor catalogues'''
    def __init__(self, ref_name='ref',test_name='test'): 
        '''ref_name, test_name could be decals,bass/mzls for example'''  
        self.kwargs= PlotKwargs()
        self.ref_name= ref_name
        self.test_name= test_name

    # WARNING: all plots below assume self.ds exists 
    # Which has keys ref_matched,test_matched, ref_missed, etc
    def _nobs():
        '''make histograms of nobs so can compare depths of g,r,z between the two catalogues'''   
        hi=0 
        for key in ['ref_matched','test_matched']:
            for band in 'grz':
                hi= np.max((hi, self.data[key][band+'_nobs'].max()))
        bins= hi
        for key in ['ref_matched','test_matched']:
            for band in 'grz':
                junk=plt.hist(self.data[key][band+'_nobs'],\
                            bins=bins,normed=True,cumulative=True,align='mid')
                xlab=plt.xlabel('nobs %s' % band, **self.kwargs.ax)
                ylab=plt.ylabel('CDF', **self.kwargs.ax)
                plt.savefig(os.path.join(get_outdir('bmd'),'hist_nobs_%s_%s.png' % (band,cam[2:])), \
                        bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
                plt.close()

    def _radec(addname=''): 
        '''obj[m_types] -- DECaLS() objects with matched OR unmatched indices'''
        #set seaborn panel styles
        #sns.set_style('ticks',{"axes.facecolor": ".97"})
        #sns.set_palette('colorblind')
        #setup plot
        fig,ax=plt.subplots(1,2,figsize=(9,6),sharey=True,sharex=True)
        plt.subplots_adjust(wspace=0.25)
        #plt.subplots_adjust(wspace=0.5)
        #plot
        ax[0].scatter(self.data['ref_matched']['ra'], self.data['ref_matched']['dec'], \
                    edgecolor='b',c='none',lw=1.)
        ax[1].scatter(self.data['ref_missed']['ra'], self.data['ref_missed']['dec'], \
                    edgecolor='b',c='none',lw=1.,label=self.ref_name)
        ax[1].scatter(self.data['test_missed']['ra'], self.data['test_missed']['dec'], \
                    edgecolor='g',c='none',lw=1.,label=self.test_name)
        for cnt,ti in zip(range(2),['Matched','Unmatched']):
            ti=ax[cnt].set_title(ti,**self.kwargs.ax)
            xlab=ax[cnt].set_xlabel('RA', **self.kwargs.ax)
        ylab=ax[0].set_ylabel('DEC', **self.kwargs.ax)
        ax[0].legend(loc='upper left',**self.kwargs.leg)
        #save
        #sns.despine()
        plt.savefig(os.path.join(get_outdir('bmd'),'radec%s.png' % addname), \
                bbox_extra_artists=[xlab,ylab,ti], bbox_inches='tight',dpi=150)
        plt.close()


    def _HistTypes(addname=''):
        '''decam,bokmos -- DECaLS() objects with matched OR unmatched indices'''
        #matched or unmatched objects
        #c2=sns.color_palette()[0] #'b'
        c1= 'b' 
        c2= 'r'
        ###
        types= self.ds.types.keys()
        ind = np.arange(len(types))  # the x locations for the groups
        width = 0.35       # the width of the bars
        ###
        ht_ref, ht_test= np.zeros(5,dtype=int),np.zeros(5,dtype=int)
        for cnt,typ in enumerate(types):
            ht_ref[cnt]= len(self.data['ref_matched']['ra'][ self.ds['ref_matched'].types[typ] ]/ \
                            float(self.data['deg2']['ref'])
            ht_test[cnt]= len(self.data['test_matched']['ra'][ self.ds['test_matched'].types[typ] ]/ \
                            float(self.data['deg2']['test'])
        ###
        fig, ax = plt.subplots()
        rects1 = ax.bar(ind, ht_decam, width, color=c1)
        rects2 = ax.bar(ind + width, ht_bokmos, width, color=c2)
        ylab= ax.set_ylabel("counts/deg2")
        if matched: ti= ax.set_title('Matched')
        else: ti= ax.set_title('Unmatched')
        ax.set_xticks(ind + width)
        ax.set_xticklabels(types)
        ax.legend((rects1[0], rects2[0]), (self.ref_name, self.test_name,**self.kwargs.leg)
        #save
        if matched: name='hist_types_Matched%s.png' % addname
        else: name='hist_types_Unmatched%s.png' % addname
        plt.savefig(os.path.join(get_outdir('bmd'),name), \
                    bbox_extra_artists=[ylab,ti], bbox_inches='tight',dpi=150)
        plt.close()


    def _SN_vs_mag(obj_type='PSF', addname=''):
        ''''''
        #bin up SN values
        min,max= 18.,25.
        bin_SN=dict(ref_matched={},test_matched={})
        for key in bin_SN.keys():
            for band in ['g','r','z']:
                bin_SN[key][band]={}
                i= self.ds['key'].type[obj_type]
                bin_edges= np.linspace(min,max,num=30)
                bin_SN[key][band]['binc'],count,bin_SN[key][band]['q25'],bin_SN[key][band]['q50'],bin_SN[key][band]['q75']=\
                        bin_up(self.ds[key].magAB[band][i], \
                               self.data[key][band+'flux'][i]*np.sqrt(self.data[key][band+'flux_ivar'][i]),\
                                    bin_edges=bin_edges)
        #setup plot
        fig,ax=plt.subplots(1,3,figsize=(9,3),sharey=True)
        plt.subplots_adjust(wspace=0.25)
        #plot SN
        for cnt,band in zip(range(3),['g','r','z']):
            #horiz line at SN = 5
            ax[cnt].plot([1,40],[5,5],'k--',lw=2)
            #data
            for inst,color,lab in zip(bin_SN.keys(),['b','g'],[self.ref_name,self.test_name]):
                ax[cnt].plot(bin_SN[inst][band]['binc'], bin_SN[inst][band]['q50'],c=color,ls='-',lw=2,label=lab)
                ax[cnt].fill_between(bin_SN[inst][band]['binc'],bin_SN[inst][band]['q25'],bin_SN[inst][band]['q75'],color=color,alpha=0.25)
        #labels
        ax[2].legend(loc=1,**self.kwargs.leg)
        for cnt,band in zip(range(3),['g','r','z']):
            ax[cnt].set_yscale('log')
            xlab=ax[cnt].set_xlabel('%s' % band, **self.kwargs.ax)
            ax[cnt].set_ylim(1,100)
            ax[cnt].set_xlim(20.,26.)
        ylab=ax[0].set_ylabel('S/N', **self.kwargs.ax)
        ax[2].text(26,5,'S/N = 5  ',**self.kwargs.text)
        plt.savefig(os.path.join(get_outdir('bmd'),'sn_%s%s.png' % (obj_type,addname)), bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
        plt.close()

    def _confusion_matrix(cm,ticknames, addname=''):
        '''cm -- NxN array containing the Confusion Matrix values
        ticknames -- list of strings of length == N, column and row names for cm plot'''
        plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues,vmin=0,vmax=1)
        cbar=plt.colorbar()
        plt.xticks(range(len(ticknames)), ticknames)
        plt.yticks(range(len(ticknames)), ticknames)
        ylab=plt.ylabel('True (%s)' % self.ref_name)
        xlab=plt.xlabel('Predicted (%s)' % self.test_name)
        for row in range(len(ticknames)):
            for col in range(len(ticknames)):
                if np.isnan(cm[row,col]):
                    plt.text(col,row,'n/a',va='center',ha='center')
                elif cm[row,col] > 0.5:
                    plt.text(col,row,'%.2f' % cm[row,col],va='center',ha='center',color='yellow')
                else:
                    plt.text(col,row,'%.2f' % cm[row,col],va='center',ha='center',color='black')
        plt.savefig(os.path.join(get_outdir('bmd'),'confusion_matrix%s.png' % addname), \
                    bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
        plt.close()



    def _matched_separation_hist():
        '''d12 is array of distances in degress between matched objects'''
        #pixscale to convert d12 into N pixels
        pixscale=dict(decam=0.25,bokmos=0.45)
        #sns.set_style('ticks',{"axes.facecolor": ".97"})
        #sns.set_palette('colorblind')
        #setup plot
        fig,ax=plt.subplots()
        #plot
        ax.hist(self.data['d_matched']*3600,bins=50,color='b',align='mid')
        ax2 = ax.twiny()
        ax2.hist(self.data['d_matched']*3600./pixscale['bokmos'],bins=50,color='g',align='mid',\
                    visible=False)
        xlab= ax.set_xlabel("arcsec")
        xlab= ax2.set_xlabel("pixels [BASS]")
        ylab= ax.set_ylabel("Matched")
        #save
        #sns.despine()
        plt.savefig(os.path.join(get_outdir('bmd'),"separation_hist.png"), \
                        bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
        plt.close()

    def _psf_hists():
        '''decam,bokmos are DECaLS() objects matched to decam ra,dec'''
        #divide into samples of 0.25 mag bins, store q50 of each
        width=0.25 #in mag
        low_vals= np.arange(20.,26.,width)
        med={}
        for b in ['g','r','z']: med[b]=np.zeros(low_vals.size)-100
        for i,low in enumerate(low_vals):
            for band in ['g','r','z']:
                ind= np.all((low <= self.ds['ref_matched'].magAB[band],\
                             self.ds['ref_matched'].magAB[band] < low+width),axis=0)
                if np.where(ind)[0].size > 0:
                    med[band][i]= np.percentile(self.ds['ref_test'].magAB[band][ind] - \
                                                self.ds['ref_matched'].magAB[band][ind],q=50)
                else: 
                    med[band][i]= np.nan
        #make plot
        #set seaborn panel styles
        #sns.set_style('ticks',{"axes.facecolor": ".97"})
        #sns.set_palette('colorblind')
        #setup plot
        fig,ax=plt.subplots(1,3,figsize=(9,3)) #,sharey=True)
        plt.subplots_adjust(wspace=0.5)
        #plot
        for cnt,band in zip(range(3),['r','g','z']):
            ax[cnt].scatter(low_vals, med[band],\
                           edgecolor='b',c='none',lw=2.) #,label=m_type.split('_')[-1])
            xlab=ax[cnt].set_xlabel('bins of %s (%s)' % (band,self.ref_name), **self.kwargs.ax)
            ylab=ax[cnt].set_ylabel('q50[%s %s - %s]' % (band,self.test_name,self.ref_name), **self.kwargs.ax)
            if zoom: ax[cnt].set_ylim(-0.25,0.25)
        # sup=plt.suptitle('decam with matching bokmos',**laba)
        #save
        #sns.despine()
        name="median_color_diff.png"
        plt.savefig(os.path.join(get_outdir('bmd'),name), \
                    bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
        plt.close()


    def _plot_dflux_chisq(obj_type='PSF', low=-8.,hi=8.,addname=''):
        #get flux diff for each band
        hist= dict(g=0,r=0,z=0)
        binc= dict(g=0,r=0,z=0)
        stats=dict(g=0,r=0,z=0) 
        i_type= np.all((self.ds['ref_matched'].type[obj_type],\
                        self.ds['test_matched'].type[obj_type]), axis=0)
        for band in ['g','r','z']:
            sample=(self.data['ref_matched'][band+'flux'][i_type]-self.data['test_matched'][band+'flux'][i_type])/\
                    np.sqrt(np.power(self.data['ref_matched'][band+'flux_ivar'][i_type],-1)+\
                            np.power(self.data['test_matched'][band+'flux_ivar'][i_type],-1))
            hist[band],bins,junk= plt.hist(sample,range=(low,hi),bins=50,normed=True)
            db= (bins[1:]-bins[:-1])/2
            binc[band]= bins[:-1]+db
            stats[band]= sample_gauss_stats(sample)
        plt.close() #b/c plt.hist above
        #for drawing unit gaussian N(0,1)
        G= sp_stats.norm(0,1)
        xvals= np.linspace(low,hi)
        #plot
        fig,ax=plt.subplots(1,3,figsize=(9,3),sharey=True)
        plt.subplots_adjust(wspace=0.25)
        for cnt,band in zip(range(3),['g','r','z']):
            ax[cnt].step(binc[band],hist[band], where='mid',c='b',lw=2)
            ax[cnt].plot(xvals,G.pdf(xvals))
            #for yloc,key in zip([0.95,0.85,0.75,0.65,0.55],['mean','std','q25','q75','perc_out']):
            #    ax[cnt].text(0.1,yloc,"%s %.2f" % (key,stats[band]['sample'][key]),transform=ax[cnt].transAxes,horizontalalignment='left',**text_args)
        #ax[2].text(0.9,0.95,"N(0,1)",transform=ax[2].transAxes,horizontalalignment='right',**text_args)
        #for yloc,key in zip([0.85,0.75,0.65,0.55],['mean','std','q25','perc_out']):
        #    ax[2].text(0.9,yloc,"%s %.2f" % (key,stats['g']['gauss'][key]),transform=ax[2].transAxes,horizontalalignment='right',**text_args)
        #labels
        for cnt,band in zip(range(3),['g','r','z']):
            if band == 'r': xlab=ax[cnt].set_xlabel(r'%s  $(F_{d}-F_{bm})/\sqrt{\sigma^2_{d}+\sigma^2_{bm}}$' % band, **self.kwargs.ax)
            else: xlab=ax[cnt].set_xlabel('%s' % band, **self.kwargs.ax)
            #xlab=ax[cnt].set_xlabel('%s' % band, **laba)
            ax[cnt].set_ylim(0,0.6)
            ax[cnt].set_xlim(low,hi)
        ylab=ax[0].set_ylabel('PDF', **self.kwargs.ax)
        ti=ax[1].set_title(type,**self.kwargs.ax)
        #put stats in suptitle
        plt.savefig(os.path.join(get_outdir('bmd'),'dflux_chisq_%s%s.png' % (type,addname)), \
                    bbox_extra_artists=[ti,xlab,ylab], bbox_inches='tight',dpi=150)
        plt.close()
    ################

    def _N_per_deg2(obj_type='PSF',req_mags=[24.,23.4,22.5],addname=''):
        '''image requirements grz<=24,23.4,22.5
        compute number density in each bin for each band mag [18,requirement]'''
        #indices for type for matched and unmatched samples
        index={}
        for inst in ['m_decam','u_decam','m_bokmos','u_bokmos']:
            index[inst]= indices_for_type(obj, inst=inst,type=type) 
        bin_nd=dict(decam={},bokmos={})
        for inst in ['decam','bokmos']:
            bin_nd[inst]={}
            for band,req in zip(['g','r','z'],req_mags):
                bin_nd[inst][band]={}
                bin_edges= np.linspace(18.,req,num=15)
                i_m,i_u= index['m_'+inst], index['u_'+inst] #need m+u
                #join m_decam,u_decam OR m_bokmos,u_bokmos and only with correct all,psf,lrg index
                sample= np.ma.concatenate((obj['m_'+inst].data[band+'mag'][i_m], obj['u_'+inst].data[band+'mag'][i_u]),axis=0)
                bin_nd[inst][band]['binc'],bin_nd[inst][band]['cnt'],q25,q50,q75=\
                        bin_up(sample,sample,bin_edges=bin_edges)
        #plot
        fig,ax=plt.subplots(1,3,figsize=(9,3),sharey=True)
        plt.subplots_adjust(wspace=0.25)
        for cnt,band in zip(range(3),['g','r','z']):
            for inst,color,lab in zip(['decam','bokmos'],['b','g'],['DECaLS','BASS/MzLS']):
                ax[cnt].step(bin_nd[inst][band]['binc'],bin_nd[inst][band]['cnt']/obj['deg2_'+inst], where='mid',c=color,lw=2,label=lab)
        #labels
        for cnt,band in zip(range(3),['g','r','z']):
            xlab=ax[cnt].set_xlabel('%s' % band) #, **laba)
            #ax[cnt].set_ylim(0,0.6)
            #ax[cnt].set_xlim(maglow,maghi)
        ax[0].legend(loc='upper left', **leg_args)
        ylab=ax[0].set_ylabel('counts/deg2') #, **laba)
        ti=plt.suptitle("%ss" % type.upper(),**laba)
        # Make space for and rotate the x-axis tick labels
        fig.autofmt_xdate()
        #put stats in suptitle
        plt.savefig(os.path.join(get_outdir('bmd'),'n_per_deg2_%s%s.png' % (type,addname)), bbox_extra_artists=[ti,xlab,ylab], bbox_inches='tight',dpi=150)
        plt.close()





class bassmos_v_decals(object):
    '''defines functions that make plots for bass/mzls vs. decals data'''
    def __init__(self, decals_list,bassmos_list):
        self.data= match_two_cats(decals_list, bassmos_list)
        self.ds= DataSets(self.data)
        #inheret plotting functins and self.kwargs
        super(Plots_Cat_Comparison, self).__init__()
        self.make_plots()

    def make_plots(self):
        print('square deg covered by %s=%.2f and %s=%.2f' % \
            (self.ref_name,self.data['deg2']['ref'],self.test_name,self.data['deg2']['test']))
        self._radec()
        self._matched_separation_hist()
        # Depths are very different so develop a cut to make fair comparison
        self._SN_vs_mag(type='psf')
        # Change mask: BASS SN g < 5 or BASS SN r < 5
        sn_crit=5.
        mask= np.any((self.data['test_matched']['gflux']*np.sqrt(\
                        self.data['test_matched']['gflux_ivar']) < sn_crit,\
                      self.data['test_matched']['rflux']*np.sqrt(\
                        self.data['test_matched']['rflux_ivar']) < sn_crit),\
                        axis=0)
        for key in ['ref_matched','test_matched','ref_missed','test_missed']: 
            self.ds[key].update_mask(mask)
        # Continue plotting
        self._radec(addname='snGe5')
        self._HistTypes(addname='snGe5')
        self._SN_vs_mag(type='psf',addname='snGe5')
        cm,names= create_confusion_matrix(b)
        self._confusion_matrix(cm,names,addname='snGe5')
        self._dflux_chisq(type='psf',addname='snGe5')
        self._N_per_deg2(type='psf',addname='snGe5')
        self._N_per_deg2(type='lrg',addname='snGe5')
        



parser=argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                 description='DECaLS simulations.')
parser.add_argument('--decals_list', type=str, help='process this brick (required input)',required=True)
parser.add_argument('--bassmos_list', type=str, help='object type (STAR, ELG, LRG, BGS)',required=True) 
args = parser.parse_args()

#plots automade when instantiate object
obj= bassmos_v_decals(args.decals_list, args.bassmos_list)


# Plots
plot_radec(data,ds)
plot_matched_separation_hist(data'deg2']['ref'])
# Depths are very different so develop a cut to make fair comparison
plot_SN_vs_mag(b, found_by='matched',type='psf')
# mask=True where BASS SN g < 5 or BASS SN r < 5
sn_crit=5.
mask= np.any((b['m_bokmos'].data['gflux']*np.sqrt(b['m_bokmos'].data['gflux_ivar']) < sn_crit,\
              b['m_bokmos'].data['rflux']*np.sqrt(b['m_bokmos'].data['rflux_ivar']) < sn_crit),\
                axis=0)
b['m_decam'].update_masks_for_everything(mask=mask, mask_wise=mask)
b['m_bokmos'].update_masks_for_everything(mask=mask, mask_wise=mask)
# contintue with fairer comparison
plot_radec(b,addname='snGe5')
plot_HistTypes(b,m_types=['m_decam','m_bokmos'],addname='snGe5')
plot_SN_vs_mag(b, found_by='matched',type='psf',addname='snGe5')
#plot_SN_vs_mag(b, found_by='matched',type='all')
#plot_SN_vs_mag(b, found_by='matched',type='lrg')
#plot_SN_vs_mag(b, found_by='unmatched',type='all')
#plot_SN_vs_mag(b, found_by='unmatched',type='psf')
#plot_SN_vs_mag(b, found_by='unmatched',type='lrg')
cm,names= create_confusion_matrix(b)
plot_confusion_matrix(cm,names,addname='snGe5')
plot_dflux_chisq(b,type='all',addname='snGe5')
plot_dflux_chisq(b,type='psf',addname='snGe5')
# Number density cutting to requirement mags: grz<=24,23.4,22.5
print('square deg covered by decam=',b['deg2_decam'],'and by bokmos=',b['deg2_bokmos'])
plot_N_per_deg2(b,type='psf',addname='snGe5')
plot_N_per_deg2(b,type='lrg',addname='snGe5')





print('exiting early')
sys.exit()

plot_matched_dmag_vs_psf_fwhm(b, type='psf')
plot_matched_decam_vs_bokmos_psf_fwhm(b, type='psf')

print('finished comparison: bass-mosaic-decals')
#sys.exit()
#
#
##REVISE THIS BELOW
##print stats of total objects, each group, # masked, etc
#print("---- DECAM ----")
#print("N not masked due to grz= %d, N total= %d" % \
#        (m_decam_not_masked+b['u_decam'].count_not_masked(), b['m_decam'].count_total()+b['u_decam'].count_total()))
#print("-- Matched --")
#print("N not masked before join bokmos mask= %d, N not masked after= %d" % \
#        (m_decam_not_masked, b['m_decam'].count_not_masked()))
#print("-- Unmatched -- ")
#print("N masked before join bokmos mask = N masked after = %d" % \
#        (b['u_decam'].count_total()- b['u_decam'].count_not_masked()))
####bokmos
#print("---- BOKMOS ----")
#print("N not masked due to grz= %d, N total= %d" % \
#        (m_bokmos_not_masked+b['u_bokmos'].count_not_masked(), b['m_bokmos'].count_total()+b['u_bokmos'].count_total()))
#print("-- Matched --")
#print("N not masked before join decam mask= %d, N not masked after= %d" % \
#        (m_bokmos_not_masked, b['m_bokmos'].count_not_masked()))
#print("-- Unmatched -- ")
#print("N masked before join decam mask = N masked after = %d" % \
#        (b['u_bokmos'].count_total()- b['u_bokmos'].count_not_masked()))
#print('done')


