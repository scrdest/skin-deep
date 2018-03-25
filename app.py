import sys, os, shutil
import pickle
import dparser as geo
import pandas as pd
import numpy as np
import itertools as itt
import collections as coll
import matplotlib.pyplot as plt
from importlib import reload as Reimport
Models = NotImplemented # deferred loading to save on keras bootup time; module-scope mostly for reloads

# option keys
LABEL_SAMPLE_SIZE = 'label_sample_size'

def build_models(datashape, compression_fac=32, activators=('selu', 'sigmoid'), **kwargs):
    try: Reimport(models)
    except (NameError, TypeError): import models
    Models = models
    return Models.build_models(datashape, compression_fac=32, activators=('selu', 'sigmoid'), **kwargs)
                   
def load_model(*args, model_path=NotImplemented, **kwargs):
    model, loaded_path = None, None
    
    while model_path is NotImplemented: 
        if kwargs.get('list_cwd'): print("Files in current dir: {}".format(
                                            [(x if os.path.isfile(x) else x + '/') 
                                            for x in os.listdir(os.getcwd())])
                                        )
        try: 
            model_path = input("Path to load:\n>>> ")
        except (KeyboardInterrupt, EOFError):
            break
        if not os.path.exists(model_path):
            if model_path in {'Q',}: 
                print('Returning to menu...')
                break
            else:
                print('Invalid path.')
                model_path = NotImplemented
    else:
        try:
            import keras
            model = keras.models.load_model(model_path)
            loaded_path = model_path
        except Exception as Err:
            if kwargs.get('verbose'): sys.excepthook(*sys.exc_info())
            print("\n\nModel could not be loaded from path {}!".format(loaded_path))
        return model, loaded_path
          
            
class MenuConfiguration(object):
    def __init__(self, opts=None, **kwargs):
        self.options = coll.OrderedDict()
        # defaults:
        self.options.update((
            ('train_steps', 75), 
            ('test_steps', 5), 
            (LABEL_SAMPLE_SIZE, 30000), 
            ('list_cwd', False), 
            ('model_depth', 2), 
            ('drop_labels', False),
            ('compression_fac', 256),
        ))
        # kwargs are options to use:
        if opts: self.options.update(opts)
        self.options.update(kwargs)
        # TODO: clean up the kwargs
        

class SkinApp(object):    
    ACT_TRAIN= '(T)rain'
    ACT_PRED = '(P)redict'
    ACT_LOAD = '(L)oad model'
    ACT_SAVE = '(S)ave model'
    ACT_DROP = '(D)rop model'
    ACT_CONF = '(C)onfigure'
    ACT_QUIT = '(Q)uit'

    DBG_DATA = 'DEBUG DATA (!)'
    DBG_MODE = '!lvl'
    
    def __init__(self, *args, **kwargs):
        self.prediction, self.history, self.modelpath = None, None, None
        self.model = [None, None, None]
        self.config = MenuConfiguration({self.DBG_MODE : False,}, **kwargs)
        #self.config.options.update(sorted([('verbosity', verbose), ('xml_path', xml), ('txt_path', txt), ('directory', dir)]))
        
        self.modes = coll.OrderedDict()
        self.modes.update({self.ACT_TRAIN: {'1', 'train', 't'},})
        self.modes.update({self.ACT_PRED : {'2', 'predict', 'p'},})
        self.modes.update({self.ACT_LOAD : {'3', 'load', 'l'},})
        self.modes.update({self.ACT_SAVE : {'4', 'save', 's'},})
        self.modes.update({self.ACT_DROP : {'5', 'drop', 'd'},})
        self.modes.update({self.ACT_CONF : {'6', 'configure', 'c'},})
        self.modes.update({self.ACT_QUIT : {'0', 'quit', 'q'},})
    
        self.modes.update({self.DBG_DATA : {'!', '-1'},})
    
        self.baseprompt = """
           __________
          /          \\
          |   MENU   |
          \__________/
 {mdl}
  
 The available options are: 
   - {opts}.
    
>>> """.format(opts=',\n   - '.join(self.modes), mdl="{mdl}")
    pass # just to clarify end of def since init doesn't explicitly return

    
    def run_model(self, models=None, verbose=None, *args, xml=None, txt=None, dir=None, **kwargs):
        mode = kwargs.get('mode', 'train')
        
        datagen = geo.build_datastreams_gen(xml=xml, txt=txt, dir=dir, 
                                        mode=mode, debug=False,
                                        drop_labels=self.config.options.get('drop_labels', False),
                                        )
                                                    
        sampled, labels, size = geo.sample_labels(datagen, self.config.options.get(LABEL_SAMPLE_SIZE, 1000))
        #raise Exception(next(sampled[0]))
        
        def predfunc(models):
            batch = next(sampled[0])
            prediction = models[1].predict_on_batch(np.asarray([batch.values]))
            prediction = pd.DataFrame(prediction[0])
            prediction = prediction.T
            #prediction = prediction.set_index(labels)
            prediction = prediction.rename(columns={0 : "{} ({})".format(batch.index[0], batch.index.name)})
            return prediction
            
        def trainfunc(models, e):
            batchgen = (np.asarray([x.values]) for x in sampled[0])
            validgen = itt.cycle([np.asarray([next(sampled[1]).values]) for x in range(self.config.options.get('train_steps', 75))])
            history = models[0].fit_generator(zip(((batch + 0.25 * np.random.normal(size=size)) for batch in batchgen), batchgen), 
                                              steps_per_epoch=self.config.options.get('train_steps', 75), 
                                              initial_epoch=e-1, epochs=e,
                                              validation_data=zip(validgen, validgen),
                                              validation_steps=self.config.options.get('train_steps', 75)
                                              )
            return history
            
        mode_func = {'test': lambda x, e: (predfunc(x)),
                     'train': lambda x, e: (trainfunc(x, e)),
                    }.get(mode)
        
        built_models = [None]
        print("SIZE: ", size)
        if models is None or not all(models): 
            print(built_models)
            built_models = build_models(datashape=size, 
                                        compression_fac=self.config.options.get('compression_fac', 32), 
                                        depth=self.config.options.get('model_depth', 2),
                                        activators=('selu', 'sigmoid')
                                        )
        #if len(models)>0 and hasattr(models[0], 'layers'): models = [x or models[0]
        print(built_models)
        models = [x or built_models[i] for (i,x) in enumerate(models or built_models)]
        autoencoder = models[0]
        autoencoder.compile(optimizer='adadelta', loss='binary_crossentropy')
        
        fits = 1
        savepath = NotImplemented
        result = None
        while fits:
            fits -= 1
            if not fits or fits < 1:
                while True:
                    try:
                        fits = int(input("Enter a number of fittings to perform before prompting again.\n (value <= 0 to terminate): "))
                        break
                    except (KeyboardInterrupt, EOFError):
                        return
                    except Exception as Exc:
                        if verbose: print(Exc)
                        print("Invalid input. Try again.")
                        
            if fits:
                if savepath is NotImplemented: 
                    savepath = input("If you want to save the result, enter the filename of file to save it to: ")
                try:
                    fitting = mode_func(models, fits)
                    print("\nRuns remaining: {}".format(fits))
                    if result is None or mode=='train': result = fitting
                    else:
                        try: result = result[result!=0].combine_first(fitting).fillna(0)
                        except Exception:  result = result.join(mode_func(models, fits), how='outer', rsuffix='-REP')
                except KeyboardInterrupt: fits = 0
                sampled, labels, size = geo.sample_labels(datagen, self.config.options.get(LABEL_SAMPLE_SIZE, 1000))
                
                if savepath and (not savepath is NotImplemented) and (not fits % 10 or 0 <= fits < 10): 
                    try: os.replace(savepath, savepath+'.backup')
                    except Exception: pass
                    
                    if mode == 'train': autoencoder.save(savepath)
                    if mode == 'test': result.to_csv(savepath)
                    
            else: savepath = None if savepath is NotImplemented else savepath
        
        return (models, result, savepath)


    def run(self, *args, **kwargs):
        mainloop = True
        actionqueque = coll.deque(kwargs.get('cmd') or [NotImplemented])
        action = NotImplemented
        while mainloop:
            prompt = self.baseprompt.format(mdl=(('\n Currently loaded model: '+ str(self.modelpath))))
            if not action: 
                prompt = '>>> '
                action = NotImplemented
            if not actionqueque:
                try: actionqueque.extend(input(prompt).lower().split())
                except (KeyboardInterrupt, EOFError):
                    action = None
                    mainloop = False
            try: action = str(actionqueque.popleft()).lower()
            except IndexError: action = None
            
            if action in self.modes[self.ACT_TRAIN]: 
                try:
                    _tmp = self.run_model(*args, models=self.model, verbose=self.config.options.get('verbose'), 
                                     xml=self.config.options.get('xml'), txt=self.config.options.get('txt'), 
                                     dir=self.config.options.get('dir'), mode='train',  **kwargs)
                except Exception as Err: 
                    _tmp = None
                    sys.excepthook(*sys.exc_info())
                
                try: _tmpFN = _tmp[2]
                except Exception as Err: _tmpFN = None
                
                try: self.history = _tmp[1]
                except Exception as Err: self.history = None
                
                try: _tmp = _tmp[0]
                except Exception as Err: _tmp = None
                
                self.model = _tmp if _tmp else self.model
                self.modelpath = _tmpFN if (_tmp and _tmpFN) else (str(self.model) if _tmp else self.modelpath)
                
            if action in self.modes[self.ACT_PRED]:
                try:
                    _tmp = self.run_model(*args, models=self.model, verbose=self.config.options.get('verbose'), 
                                        xml=self.config.options.get('xml'), txt=self.config.options.get('txt'), 
                                        dir=self.config.options.get('dir'), 
                                        mode='test', **kwargs
                                    )
                except Exception as Err: 
                    _tmp = None
                    sys.excepthook(*sys.exc_info())
                
                try: _tmpFN = _tmp[2]
                except Exception as Err: _tmpFN = None
                
                try: prediction = _tmp[1]
                except Exception as Err: prediction = None
                
                try: _tmp = _tmp[0]
                except Exception as Err: _tmp = None
                
                model = _tmp if _tmp else self.model
                modelpath = _tmpFN if (_tmp and _tmpFN) else (str(self.model) if _tmp else self.modelpath)
                if prediction is not None: 
                    print(prediction)
                    self.prediction = prediction
                    
            if action in self.modes[self.ACT_LOAD]:
                _tmp, _tmp2 = None, None
                try: _tmp, _tmp2 = load_model(list_cwd=self.config.options.get('list_cwd', False))
                except Exception as Err: pass
                if _tmp: 
                    model = list(self.model or [None, None, None])
                    model[0] = _tmp
                    _aux_components = getattr(model[0], 'aux_components', {})
                    print("Aux components:", _aux_components)
                    model[1], model[2] = _aux_components.get('Encoder'), _aux_components.get('Decoder')
                    self.model = tuple(model)
                    self.modelpath = str(_tmp2)
                    self.config.options[LABEL_SAMPLE_SIZE] = self.model[0].input_shape[-1]
                    print("Model loaded successfully.")
            
            if action in self.modes[self.ACT_SAVE]:
                if self.model[0]:
                    savepath = input("Enter the filename of file to save it to: ")
                    savepath = savepath.strip() if savepath else savepath
                    if savepath: 
                        self.model[0].save(savepath)
                        self.modelpath = savepath
                        print('Model successfully saved to {}.'.format(savepath))
                else: print('Model not currenly loaded.')
                
            if action in self.modes[self.ACT_DROP]:
                self.model = None
                self.modelpath = None
                
            if action in self.modes[self.ACT_CONF]:
                while True:
                    optstrings = [(repr(Opt), repr(Val)) for Opt, Val in self.config.options.items()]
                    leftspace = "{f1}{space}{f2}".format(f1="{O:<", space=max(map(len, (x[0] for x in optstrings))), f2="}")
                    rightspace = "{f1}{space}{f2}".format(f1="{V:>", space=max(map(len, (x[1] for x in optstrings))), f2="}")
                    lines = ["    > o {lsp}{sep:^3}{rsp} <".format(lsp=leftspace, rsp=rightspace, sep=' - ').format(O=repr(Opt), V=repr(Val)) 
                                                                      for Opt, Val in self.config.options.items()]
                    menusize = max(map(len, lines))
                    print(" ")
                    print("    >>> {siz} <<<"
                            .format(siz='{text:^'+repr(menusize-12)+'}')
                            .format(text="CONFIGURATION:")
                        )
                    print("    \n".join(lines))
                    print("    >>> {siz} <<<"
                            .format(siz='{text:^'+repr(menusize-12)+'}')
                            .format(text="'Q' - RETURN"))
                    try: option = input('\n    > ')
                    except (KeyboardInterrupt, EOFError): option = 'Q'
                    print(' ')
                    
                    if option == 'Q':
                        break
                    
                    try: intable = int(option)
                    except Exception as E: intable = False
                    if intable:
                        try: option = tuple(self.config.options.keys())[intable]
                        except Exception as E: print(E)
                    
                    if option in self.config.options:
                        newval = input("    - {} => ".format(option))
                        if newval:
                            evaluables = {'None' : None, 'False' : False, 'True' : True}
                            if newval in evaluables: newval = evaluables[newval]
                            else: newval = int(newval) if newval.isnumeric() else newval
                            self.config.options[option] = newval
                            print(" ")
                
            if action in self.modes[self.DBG_DATA]:
                _tmp = geo.build_datastreams_gen(*args, xml=self.config.options.get('xml'), 
                                             txt=self.config.options.get('txt'), dir=self.config.options.get('dir'), 
                                             verbose=self.config.options.get('verbose'), 
                                             debug=self.config.options.get(self.DBG_MODE),
                                             **kwargs)
                try: _tmp = _tmp[0]
                except Exception as Err: 
                    print(Err)
                    _tmp = None
                if _tmp is not None: print((_tmp))
                
            if action == '!eval':
                while True:
                    dbgres = None
                    try: query = input('DEBUG: >> ')
                    except (KeyboardInterrupt, EOFError): break
                    if not query or 'q' == query.lower(): break
                    try: dbgres = eval(query)
                    except Exception as E: print('>', E)
                    if dbgres is not None: print(dbgres)
                
            if action in self.modes[self.ACT_QUIT]:
                mainloop = False
    
def main(verbose=None, *args, xml=None, txt=None, dir=None, **kwargs):
    app_instance = SkinApp(*args, verbose=verbose, xml=xml, txt=txt, dir=dir, **kwargs)
    app_instance.run(*args, **kwargs)
    
if __name__ == '__main__':
    print(' ')
    import argparse
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--xml')
    argparser.add_argument('--txt')
    argparser.add_argument('--dir')
    argparser.add_argument('--cmd', nargs='*')
    argparser.add_argument('-v', '--verbose', action='store_true')
    args = vars(argparser.parse_args())
    args['dir'] = args['dir'] or 'mag'
    sys.exit(main(**args))