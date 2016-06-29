#! /bin/bash

# For modules loaded, see "bashrc" in this directory.

export LEGACY_SURVEY_DIR=$SCRATCH/cosmos

export DUST_DIR=/scratch1/scratchdirs/desiproc/dust/v0_0

export PYTHONPATH=${PYTHONPATH}:.

# Force MKL single-threaded
# https://software.intel.com/en-us/articles/using-threaded-intel-mkl-in-multi-thread-application
export MKL_NUM_THREADS=1

# Try limiting memory to avoid killing the whole MPI job...
#ulimit -S -v 30000000
ulimit -a

brick="$1"
subset="$2"

outdir=$SCRATCH/cosmos-$subset

logdir=$(echo $brick | head -c 3)
mkdir -p $outdir/logs/$logdir
log="$outdir/logs/$logdir/$brick.log"

echo Logging to: $log
echo Running on ${NERSC_HOST} $(hostname)

echo -e "\n\n\n" > $log
echo "-----------------------------------------------------------------------------------------" >> $log
echo "PWD: $(pwd)" >> $log
echo "Modules:" >> $log
module list >> $log 2>&1
echo >> $log
echo "Environment:" >> $log
set | grep -v PASS >> $log
echo >> $log
ulimit -a >> $log
echo >> $log

echo -e "\nStarting on ${NERSC_HOST} $(hostname)\n" >> $log
echo "-----------------------------------------------------------------------------------------" >> $log

python -u legacypipe/runcosmos.py \
    --subset $subset \
    --no-write \
    --pipe \
    --threads 24 \
    --skip \
    --skip-calibs \
    --no-wise \
    --brick $brick --outdir $outdir --nsigma 6 \
     >> $log 2>&1

# qdo launch cosmos 1 --cores_per_worker 24 --batchqueue regular --walltime 4:00:00 --keep_env --batchopts "-a 0-19 --qos=premium" --script ../bin/pipebrick-cosmos.sh
