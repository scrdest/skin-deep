import sys, os, shutil
import pickle
import datetime

def log_params(logstr, dest='LOGS', to_print=True, *args, **kwargs):
    logstr = str(logstr)
    dest = os.path.abspath(dest or os.getcwd())
    if not os.path.isdir(dest):
        try: os.makedirs(dest)
        except Exception:
            sys.excepthook(*sys.exc_info())
            print('\nCould not create the log directory!')
    logfname = "{main}{addons}.txt".format(main='log', addons='')
    logfp = os.path.join(dest, logfname)
    with open(logfp, 'a') as log:
        log.write("\n[{timestamp}]: ".format(timestamp=datetime.datetime.utcnow().isoformat()))
        log.write("{logged}".format(logged=logstr))
        if to_print: print(logstr)

def inp_batch_norm(expression):
    """Provides a common set of parameters for preprocessing batch normalization between modules."""
    import keras.backend as K
    #expression, expr_mean, expr_var = K.normalize_batch_in_training(expression, gamma=K.variable([10]), beta=K.variable([0]), reduction_axes=[1])
    return expression,0,0#, expr_mean, expr_var
        
        
def main(*args, **kwargs):
    pass
    
if __name__ == '__main__':
    print('This module is not meant to be executed directly.')
    input('Press Enter to quit...')
    sys.exit(main(**args))
