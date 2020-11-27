#! /bin/bash

# ####
# #SBATCH --qos=premium
# #SBATCH --nodes=3
# #SBATCH --ntasks-per-node=32
# #SBATCH --cpus-per-task=2
# #SBATCH --time=48:00:00
# #SBATCH --licenses=SCRATCH
# #SBATCH -C haswell
# #cores=96

# # Quarter-subscribed
# #SBATCH --qos=premium
# #SBATCH --nodes=3
# #SBATCH --ntasks-per-node=8
# #SBATCH --cpus-per-task=8
# #SBATCH --time=48:00:00
# #SBATCH --licenses=SCRATCH
# #SBATCH -C haswell
# nmpi=24
# brick=0137m377

# Half-subscribed, 96 tasks
#SBATCH --qos=premium
#SBATCH --nodes=6
#SBATCH --ntasks-per-node=16
#SBATCH --cpus-per-task=4
#SBATCH --time=48:00:00
#SBATCH --licenses=SCRATCH
#SBATCH -C haswell
#SBATCH --name 0715m657
nmpi=96
brick=0715m657

#nmpi=4
#brick=0309p335

#brick=$1

#module unload cray-mpich
#module load   openmpi
export PYTHONPATH=$(pwd):${PYTHONPATH}

outdir=/global/cscratch1/sd/dstn/dr9m-mpi
#outdir=/global/cscratch1/sd/dstn/mpi-test

BLOB_MASK_DIR=/global/cfs/cdirs/cosmo/work/legacysurvey/dr8/south

export LEGACY_SURVEY_DIR=/global/cfs/cdirs/cosmo/work/legacysurvey/dr9m

export DUST_DIR=/global/cfs/cdirs/cosmo/data/dust/v0_1
export UNWISE_COADDS_DIR=/global/cfs/cdirs/cosmo/work/wise/outputs/merge/neo6/fulldepth:/global/cfs/cdirs/cosmo/data/unwise/allwise/unwise-coadds/fulldepth
export UNWISE_COADDS_TIMERESOLVED_DIR=/global/cfs/cdirs/cosmo/work/wise/outputs/merge/neo6
export UNWISE_MODEL_SKY_DIR=/global/cfs/cdirs/cosmo/work/wise/unwise_catalog/dr3/mod
export GAIA_CAT_DIR=/global/cfs/cdirs/cosmo/work/gaia/chunks-gaia-dr2-astrom-2
export GAIA_CAT_VER=2
export TYCHO2_KD_DIR=/global/cfs/cdirs/cosmo/staging/tycho2
export LARGEGALAXIES_CAT=/global/cfs/cdirs/cosmo/staging/largegalaxies/v3.0/SGA-ellipse-v3.0.kd.fits
export PS1CAT_DIR=/global/cfs/cdirs/cosmo/work/ps1/cats/chunks-qz-star-v3
export SKY_TEMPLATE_DIR=/global/cfs/cdirs/cosmo/work/legacysurvey/sky-templates

# Don't add ~/.local/ to Python's sys.path
#export PYTHONNOUSERSITE=1

# Force MKL single-threaded
# https://software.intel.com/en-us/articles/using-threaded-intel-mkl-in-multi-thread-application
export MKL_NUM_THREADS=1
export OMP_NUM_THREADS=1

# To avoid problems with MPI and Python multiprocessing
export MPICH_GNI_FORK_MODE=FULLCOPY
export KMP_AFFINITY=disabled

bri=$(echo $brick | head -c 3)
mkdir -p $outdir/logs/$bri
log="$outdir/logs/$bri/$brick.log"

mkdir -p $outdir/metrics/$bri

echo Logging to: $log
echo Running on $(hostname)

echo -e "\n\n\n" >> $log
echo "-----------------------------------------------------------------------------------------" >> $log
echo "PWD: $(pwd)" >> $log
echo >> $log
#echo "Environment:" >> $log
#set | grep -v PASS >> $log
#echo >> $log
ulimit -a >> $log
echo >> $log

echo -e "\nStarting on $(hostname)\n" >> $log
echo "-----------------------------------------------------------------------------------------" >> $log

#mpirun -n $nmpi --map-by core --rank-by node \

srun -n $nmpi --distribution cyclic:cyclic \
     python -u -O -m mpi4py.futures \
     legacypipe/mpi-runbrick.py \
       --no-wise-ceres \
       --run south \
       --brick $brick \
       --skip-calibs \
       --blob-mask-dir ${BLOB_MASK_DIR} \
       --checkpoint ${outdir}/checkpoints/${bri}/checkpoint-${brick}.pickle \
       --wise-checkpoint ${outdir}/checkpoints/${bri}/wise-${brick}.pickle \
       --stage wise_forced \
       --pickle "${outdir}/pickles/${bri}/runbrick-%(brick)s-%%(stage)s.pickle" \
       --outdir $outdir \
       >> $log 2>&1

#       --skip \
#     --ps "${outdir}/metrics/${bri}/ps-${brick}-${SLURM_JOB_ID}.fits" \
#     --ps-t0 $(date "+%s") \

# QDO_BATCH_PROFILE=cori-shifter qdo launch -v tst 1 --cores_per_worker 8 --walltime=30:00 --batchqueue=debug --keep_env --batchopts "--image=docker:dstndstn/legacypipe:intel" --script "/src/legacypipe/bin/runbrick-shifter.sh"
