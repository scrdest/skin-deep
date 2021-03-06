import sys, os, shutil
import pickle
import datetime
import pandas as pd
import numpy as np
import itertools as itt
import collections as coll
import matplotlib.pyplot as plt
from importlib import reload as Reimport

Models = NotImplemented # deferred loading to save on Keras bootup time; module-scope mostly for reloads
Keras = NotImplemented # lazy loading, see above

import dparser as geo
geo._key_cache = dict() #clean run
import config
import SDutils
     
def kerasLazy():
    """Helper for lazy-loading Keras."""
    global Keras
    if Keras is NotImplemented:
        import keras as k
        Keras = k
    return Keras

def top_2_accuracy(y_true, y_pred): return kerasLazy().metrics.top_k_categorical_accuracy(y_true, y_pred, k=2)
    
class SkinApp(object):    
    ACT_TRAIN= '(T)rain'
    ACT_PRED = '(P)redict'
    ACT_EVAL = '(E)valuate'
    ACT_LOAD = '(L)oad model'
    ACT_SAVE = '(S)ave model'
    ACT_DROP = '(D)rop model'
    ACT_CONF = '(C)onfigure'
    ACT_QUIT = '(Q)uit'

    DBG_DATA = 'DEBUG DATA (!)'
    DBG_MODE = '!lvl'
    
    config = config.MenuConfiguration()
    
    def __init__(self, *args, **kwargs):
        self.prediction, self.history, self.modelpath = None, None, None
        self.config = config.MenuConfiguration({self.DBG_MODE : False,}, **kwargs)
        self.model = [None for _ in range(self.config.get('model_amt', 4))]
        self.actionqueque = coll.deque()
        #self.config.options.update(sorted([('verbosity', verbose), ('xml_path', xml), ('txt_path', txt), ('directory', dir)]))
        
        self.modes = coll.OrderedDict()
        self.modes.update({self.ACT_TRAIN: {'1', 'train', 't'},})
        self.modes.update({self.ACT_PRED : {'2', 'predict', 'p'},})
        self.modes.update({self.ACT_EVAL : {'3', 'evaluate', 'e'},})
        self.modes.update({self.ACT_LOAD : {'4', 'load', 'l'},})
        self.modes.update({self.ACT_SAVE : {'5', 'save', 's'},})
        self.modes.update({self.ACT_DROP : {'6', 'drop', 'd'},})
        self.modes.update({self.ACT_CONF : {'7', 'configure', 'c'},})
        self.modes.update({self.ACT_QUIT : {'quit', 'q'},})
    
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
        
        catprompt = 'Enter sample type regexes (comma-separated) or leave blank to use cached: '
        cat_regexes = (self.config.get('category_regexes') 
                        or kwargs.get('category_regexes') 
                        or {rgx for rgx in (self.get_input(catprompt) or '').strip().split(',') if rgx}
                        or tuple(geo._key_cache.get('Cached-1', {}))
                       )
        label_mapping = (self.config.get('label_mapping') 
                         or kwargs.get('label_mapping')
                        )
        
        
        Reimport(geo) # drops the cache...
        catlabels, tries = [], 0
        while tries==0 and len(catlabels) < len(cat_regexes):
            tries += 1
            datagen, catlabels = geo.build_datastreams_gen(xml=xml, txt=txt, dir=dir, 
                                                           mode=mode, debug=False,
                                                           drop_labels=self.config.get('drop_labels', False),
                                                           category_regexes=cat_regexes, # ...but we're restoring/resetting it here (indirectly)
                                                           category_labels=label_mapping,
                                                           validate_label=(mode in {'train',}),
                                                           )
            assert tries < 3
        #genelabels = labels of next TODO
        sampled, genelabels, size = geo.sample_labels(datagen, self.config.get(config.LABEL_SAMPLE_SIZE))
        
        # Ugly debug hacks:
        if max(size) > 60000: raise RuntimeError('Unsafe size!') # debug - prevents crashes due to OOM
        global _encoding
        _encoding = catlabels # TEMPORARY, MEMOs THE LABELS
        import model_defs
        Reimport(model_defs)
        model_type = model_defs.variational_deep_AE
        
        batch_stream = model_type.batchgen(
                                             source=sampled[0], 
                                             catlabels=catlabels, 
                                             batch_size=self.config.get('batch_size', 1),
                                             with_name=True,
                                            )
        def evalfunc(models):
            batch, batchnames = next(batch_stream)
            zipped_inps= {i: {key : np.array([batch[0][key][i-1]]) for key in batch[0].keys()} for i in range(len(batch[0].values()))}
            zipped_inps = {0: zipped_inps[0]} # temporary
            predicted = tuple([zipped_inps[k] for k in sorted(zipped_inps.keys())])
                                            
            zipped_targ = {i: {key : np.array([batch[1][key][i-1]]) for key in batch[1].keys()} for i in range(len(batch[1].values()))}
            zipped_targ = {0: zipped_targ[0]} # temporary
            target = tuple([zipped_targ[k] for k in sorted(zipped_targ.keys())])
            
            ac_types = {i: batchnames[i] for i in zipped_inps.keys()}
            type_names = tuple([ac_types[k] for k in sorted(ac_types.keys())])
            
            used_model = models[self.config.get('usemodel')]
            metrics = used_model.test_on_batch(predicted[-1], target[-1])
            
            metrics = pd.DataFrame(data=metrics, index=used_model.metrics_names, columns=type_names)
            print(metrics)
            
            return metrics

        
        def predfunc(models):
            batch, batchnames = next(batch_stream)
                                            
                                            
            zipped = {i: {key : np.array([batch[0][key][i:(i+1)]][-1]) for key in batch[0].keys()} for i in range(len(batch[0].values()))}
            zipped = {0: zipped[0]} # temporary
            ac_types = {i: batchnames[i] for i in zipped.keys()}
            
            
            target = tuple(zipped.values())
            print("PREDTARGET: \n", target)
            prediction = models[self.config.get('usemodel')].predict_on_batch(target[-1])
            SDutils.log_params("Actual types: {}".format(ac_types))
            prediction = geo.parse_prediction(prediction, catlabels, sample_type=ac_types[0], raw_expr=zipped[0]['expression_in'], genes=genelabels, usemodel=self.config.get('usemodel'))
            return prediction
            
        def trainfunc(models, e=1):
            Callbacks = kerasLazy().callbacks
            trained_model = models[self.config.get('usemodel')]
            history = trained_model.fit_generator(
                                                  model_type.batchgen(
                                                                      source=sampled[0], 
                                                                      catlabels=catlabels, 
                                                                      batch_size=self.config.get('batch_size', 5)
                                                                      ),
                                                                  
                                                  steps_per_epoch=self.config.get('train_steps', 60), 
                                                  initial_epoch=e-1, epochs=e,
                                                  
                                                  #class_weight = {0: 1.0, 1: 1.0, 2: 0.25, 2: 2.0},
                                                  
                                                  callbacks=[
                                                            Callbacks.CSVLogger(filename='trainlog.csv', append=True),
                                                            Callbacks.ReduceLROnPlateau(monitor='diagnosis_loss', 
                                                                                         factor=0.75, 
                                                                                         patience=5, 
                                                                                         verbose=1
                                                                                        ),
                                                            ],
                                                  validation_data=model_type.batchgen(source=sampled[1], catlabels=catlabels),
                                                  validation_steps=self.config.get('test_steps', 30),
                                                )
            return history
            
        mode_func = {'test': lambda x, e: (predfunc(x)),
                     'train': lambda x, e: (trainfunc(x, e)),
                     'eval': lambda x, e: (evalfunc(x)),
                    }.get(mode)
        
        built_models = [None for x in range(self.config.get('model_amt', 4))]
        SDutils.log_params("SIZE: " + str(size))
        
        if models is None or not all(models): 
            print(built_models)
            K = kerasLazy().backend
            print(catlabels)
            built_models = self.build_models(datashape=size, kind=model_type, labels=K.eval(K.variable(np.array(tuple(catlabels.values())))),
                                            compression_fac=self.config.get('compression_fac', 1000),
                                            depth=self.config.get('model_depth', 4),
                                            activators=self.config.get('activators'),
                                            )
        
        def Compile(mdl, i=1, *args, **kwargs): 
            SDutils.log_params("DEBUG: Compile kwargs for submodel {no} ({mod}): \n".format(no=i, mod=mdl) + str(kwargs))
            #def merge_losses(*losses): return kerasLazy().backend.mean(kerasLazy().backend.sum(*[l() for l in losses]))
            if i==0: mdl.compile(
                                 optimizer=kwargs.get('optimizer'), 
                                 loss={'diagnosis': 'categorical_crossentropy', 'expression_out': getattr(mdl, 'custom_loss', kwargs.get('loss'))},
                                 loss_weights={'diagnosis': 8, 'expression_out': 2,},
                                 metrics={'diagnosis': ['binary_accuracy', 'categorical_accuracy', top_2_accuracy]},
                                 )
            elif i==2: mdl.compile(
                                 optimizer=kwargs.get('optimizer'), 
                                 loss={'diagnosis': 'categorical_crossentropy', 'expression_out': getattr(mdl, 'custom_loss', kwargs.get('loss'))},
                                 loss_weights={'diagnosis': 6, 'expression_out': 2,},
                                 metrics={'diagnosis': ['binary_accuracy', 'categorical_accuracy', top_2_accuracy]},
                                 )
            else: mdl.compile(optimizer=kwargs.get('optimizer'), loss=kwargs.get('loss'))
            
            return mdl
            
        mdl_optimizer = kerasLazy().optimizers.RMSprop(lr=0.000003, decay=0.1)
        mdl_losses = {'default': 'mape'}
        
        models =[print(i, models) or (models or [None for _ in range(i+1)])[i] 
                 #or Compile(mdl=built_models[i], i=i, optimizer=mdl_optimizer, loss=mdl_losses.get(i, mdl_losses['default'])) 
                or built_models[i]
                for (i,x) in enumerate(built_models)]
        if kwargs.get('recompile', False): models = [Compile(mdl=models[i], i=i, optimizer=mdl_optimizer, loss=mdl_losses.get(i, mdl_losses['default'])) for (i,x) in enumerate(models)]
        
        self.model = models
        autoencoder = models[0]
        
        fits, totalfits = 1, 0
        savepath = NotImplemented
        result = None
        while fits:
            fits -= 1
            if not fits or fits < 1:
                while True:
                    try:
                        fits = int(self.get_input("Enter a number of fittings to perform before prompting again.\n (value <= 0 to terminate): "))
                        break
                    except (KeyboardInterrupt, EOFError):
                        return
                    except Exception as Exc:
                        if verbose: print(Exc)
                        print("Invalid input. Try again.")
                        
            if fits:
                totalfits = max(totalfits, fits)
                if savepath is NotImplemented: 
                    savepath = self.get_input("If you want to save the result, enter the filename of file to save it to: ")
                try:
                    fitting = mode_func(models, fits)
                    if result is None or mode=='train': result = fitting
                    else: result = result.join(mode_func(models, fits), how='outer', rsuffix=str(totalfits))
                except KeyboardInterrupt: fits = 0
                
                checkpoint = self.config.get(config.SAVE_EVERY, 10)
                tail_saves = self.config.get(config.SAVE_TAILS, False)
                
                if savepath and (not savepath is NotImplemented) and (fits == 0 or (checkpoint > 0 and not fits % checkpoint) or (tail_saves and (0 <= fits < 10))): 
                    try: os.replace(savepath, savepath+'.backup')
                    except Exception: pass
                    
                    if mode == 'train': 
                        for i,m in enumerate(models): m.save('{}.{}'.format(savepath, i)) if i==0 else None
                        
                    if mode == 'test': result.to_csv(savepath)
                    
            else: savepath = None if savepath is NotImplemented else savepath
        
        return (models, result, savepath)

    def build_models(self, datashape, kind=None, labels=None, compression_fac=None, activators=None, **kwargs):
        try: Reimport(models)
        except (NameError, TypeError): import model_defs
        Models = model_defs
        SDutils.log_params('App build_models args: {}'.format(", ".join(map(str, [datashape, kind, labels, compression_fac, kwargs]))))
        
        built = Models.build_models(datashape, 
                                    labels = labels, 
                                    compression_fac = compression_fac or self.config.get('compression_fac'), 
                                    activators = activators, 
                                    num_classes = len(_encoding), 
                                    depth_scaling = kwargs.get('depth_scaling') or self.config.get('depth_scaling', 2),
                                    **kwargs)
        return built
    
    def load_model(self, *args, model_path=NotImplemented, **kwargs):
        model, loaded_path = None, None
        
        while model_path is NotImplemented: 
            if kwargs.get('list_cwd'): print("Files in current dir: {}".format(
                                                [(x if os.path.isfile(x) else x + '/') 
                                                for x in os.listdir(os.getcwd())])
                                            )
            try: model_path = self.get_input("Path to load:\n>>> ")
            except (KeyboardInterrupt, EOFError): break
            
            if not os.path.exists(model_path):
                if model_path in {'Q',}: 
                    print('Returning to menu...')
                    break
                else:
                    print('Invalid path.')
                    model_path = NotImplemented
        else:
            try:
                loadmode = self.config.get('weight_loading', 'weights')
                
                if loadmode in {0, 'model'}:
                    with kerasLazy().utils.CustomObjectScope({'_VAElossFunc': None, 'VAE_loss': None, 'top_2_accuracy': top_2_accuracy}):
                        model = kerasLazy().models.load_model(model_path)
                        
                elif loadmode in {1, 'weights'}:
                    if not self.model or None in self.model:
                        K = kerasLazy().backend
                        self.model = self.build_models(datashape=(54675), labels=K.eval(K.variable(np.array(tuple(self.config.get('label_mapping', {}).keys())))),
                                            compression_fac=self.config.get('compression_fac', 1000),
                                            depth=self.config.get('model_depth', 4),
                                            activators=self.config.get('activators'),
                                            )
                    model = self.model[0]
                    model.load_weights(model_path)
                    self.get_primary_weights()
                    
                loaded_path = model_path
            except Exception as Err:
                if kwargs.get('verbose'): sys.excepthook(*sys.exc_info())
                else: print(Err)
                SDutils.log_params("\n\nModel could not be loaded from path {}!".format(loaded_path))
            return model, loaded_path
            
    def get_input(self, prompt='>>> ', secondary='>>> '):
        curr_prompt = prompt
        action = NotImplemented
        new_cmds = []
        while action is NotImplemented:
            try: 
                action = self.actionqueque.popleft()
                action = str(action) if action and action is not NotImplemented else None
                if action == 'None': action = None
                if action != (new_cmds or [NotImplemented])[0]: print(curr_prompt + str(action))
            except (IndexError, AttributeError):
                action = NotImplemented
                if not self.actionqueque:
                    try: new_cmds = [x.strip(' ') for x in (str(input(curr_prompt)).split(';'))] or [None]
                    except (KeyboardInterrupt, EOFError): action = None
                    self.actionqueque = coll.deque(new_cmds)
            curr_prompt = secondary
        return action
            
    def run(self, *args, **kwargs):
        mainloop = True
        self.actionqueque.extend(kwargs.get('cmd') or [])
        
        while mainloop:
            prompt = self.baseprompt.format(mdl=(('\n Currently loaded model: '+ str(self.modelpath))))
            action = str(self.get_input(prompt, '>>> ')).lower()
            if not action: action = NotImplemented
            
            if action in self.modes[self.ACT_TRAIN]: 
                try: _tmp = self.run_model(*args, models=self.model, verbose=self.config.get('verbose'), 
                                                 xml=self.config.get('xml'), txt=self.config.get('txt'), 
                                                 dir=self.config.get('dir'), mode='train',  **kwargs)
                except Exception as Err: 
                    sys.excepthook(*sys.exc_info())
                    _tmp = None
                
                try: _tmpFN = _tmp[2]
                except Exception as Err: _tmpFN = None
                
                try: self.history = _tmp[1]
                except Exception as Err: self.history = None
                
                try: _tmp = _tmp[0]
                except Exception as Err: _tmp = None
                
                self.model = _tmp if _tmp else self.model
                self.modelpath = _tmpFN if (_tmp and _tmpFN) else (str(self.model) if _tmp else self.modelpath)
                
            if action in self.modes[self.ACT_PRED]:
                try: _tmp = self.run_model(*args, models=self.model,
                                            dir=self.config.get('dir'), xml=self.config.get('xml'), txt=self.config.get('txt'), 
                                            mode='test', verbose=self.config.get('verbose'),
                                            **kwargs
                                           )
                except Exception as Err: 
                    sys.excepthook(*sys.exc_info())
                    _tmp = None
                
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
                    
            if action in self.modes[self.ACT_EVAL]:
                try: _tmp = self.run_model(*args, models=self.model,
                                            dir=self.config.get('dir'), xml=self.config.get('xml'), txt=self.config.get('txt'), 
                                            mode='eval', verbose=self.config.get('verbose'),
                                            **kwargs
                                           )
                except Exception as Err: 
                    sys.excepthook(*sys.exc_info())
                    _tmp = None
                
                try: _tmpFN = _tmp[2]
                except Exception as Err: _tmpFN = None
                
                try: eval_metrics = _tmp[1]
                except Exception as Err: eval_metrics = None
                
                try: _tmp = _tmp[0]
                except Exception as Err: _tmp = None
                
                model = _tmp if _tmp else self.model
                modelpath = _tmpFN if (_tmp and _tmpFN) else (str(self.model) if _tmp else self.modelpath)
                
                if eval_metrics is not None: 
                    print(eval_metrics)
                    self.eval_metrics = eval_metrics
                    
            if action in self.modes[self.ACT_LOAD]:
                _tmp, _tmp2 = None, None
                
                try: 
                    import model_defs
                    with kerasLazy().utils.CustomObjectScope({'_VAElossFunc': None, 'VAE_loss': None}):
                        _tmp, _tmp2 = self.load_model(list_cwd=self.config.get('list_cwd', False))
                        
                except Exception as Err: 
                    sys.excepthook(*sys.exc_info()) if self.config.get('verbose') else print(Err)
                
                if _tmp: 
                    model = list(self.model or [None for x in range(self.config.get('model_amt', 4))])
                    model[0] = _tmp
                        
                    self.model = tuple(model)
                    try: self.get_primary_weights(messy=False)
                    except Exception as E: sys.excepthook(*sys.exc_info())
                    
                    self.modelpath = str(_tmp2)
                    if self.config.get('verbose'): print(self.model[0].summary())
                    #self.config.options[config.LABEL_SAMPLE_SIZE] = self.model[0].input_shape[-1]
                    SDutils.log_params("Loading {}".format(self.modelpath), to_print=False)
                    SDutils.log_params("Model loaded successfully.")
            
            if action in self.modes[self.ACT_SAVE]:
                if self.model[0]:
                    savepath = self.get_input("Enter the filename of file to save it to: ")
                    savepath = savepath.strip() if savepath else savepath
                    if savepath: 
                        with kerasLazy().utils.CustomObjectScope({'_VAElossFunc': self.model[0].custom_loss}): self.model[0].save(savepath)
                        self.modelpath = savepath
                        SDutils.log_params('Model successfully saved to {}.'.format(savepath))
                else: SDutils.log_params('Model not currenly loaded.')
                
            if action in self.modes[self.ACT_DROP]:
                if self.get_input('Are you sure you want to drop the model? ').lower() in {'y', 'yes'}:
                    self.model = None
                    self.modelpath = None
                    geo._key_cache = dict()
                
            if action in self.modes[self.ACT_CONF]:
                while True:
                    blacklist = {'category_regexes',}
                    optstrings = [(repr(Opt), repr(Val)) for Opt, Val in self.config.options.items() if Opt not in blacklist]
                    leftspace = "{f1}{space}{f2}".format(f1="{O:<", space=max(map(len, (x[0] for x in optstrings))), f2="}")
                    rightspace = "{f1}{space}{f2}".format(f1="{V:>", space=max(map(len, (x[1] for x in optstrings))), f2="}")
                    lines = ["    > o {lsp}{sep:^3}{rsp} <".format(lsp=leftspace, rsp=rightspace, sep=' - ').format(O=repr(Opt), V=repr(Val)) 
                                                                      for Opt, Val in self.config.options.items() if Opt not in blacklist]
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
                    try: option = self.get_input('\n    > ', '\n    > ')
                    except (KeyboardInterrupt, EOFError): option = 'Q'
                    print(' ')
                    
                    if option == 'Q': break
                    
                    try: intable = int(option)
                    except Exception as E: intable = False
                    if intable:
                        try: option = tuple(self.config.options.keys())[intable]
                        except Exception as E: print(E)
                    
                    if option in self.config.options:
                        newval = self.get_input("    - {} => ".format(option))
                        if newval:
                            evaluables = {'None' : None, 'False' : False, 'True' : True}
                            if newval in evaluables: newval = evaluables[newval]
                            else: newval = int(newval) if newval.isnumeric() else newval
                            self.config.options[option] = newval
                            print(" ")
                
            if action in self.modes[self.DBG_DATA]:
                _tmp = geo.build_datastreams_gen(*args, 
                                                 dir=self.config.get('dir'), 
                                                 xml=self.config.get('xml'), 
                                                 txt=self.config.get('txt'), 
                                                 verbose=self.config.get('verbose'), 
                                                 debug=self.config.get(self.DBG_MODE),
                                                 **kwargs)
                try: _tmp = _tmp[0]
                except Exception as Err: 
                    print(Err)
                    _tmp = None
                if _tmp is not None: print((_tmp))
                
            if action == '!eval':
                while True:
                    dbgres = None
                    try: query = self.get_input('DEBUG: >> ')
                    except (KeyboardInterrupt, EOFError): break
                    if not query or 'q' == query.lower(): break
                    try: dbgres = eval(query)
                    except Exception as E: print('>', E)
                    if dbgres is not None: print(dbgres)
                
            if action in self.modes[self.ACT_QUIT]:
                mainloop = False
                action = None
    
    def get_primary_weights(self, target_mdls=NotImplemented, messy=False):
        if target_mdls is NotImplemented: target_mdls = self.model
        if target_mdls and target_mdls[0]:
            weightfname = 'primary.wgts'
            target_mdls[0].save_weights(weightfname)
            
            for i, mod in enumerate(target_mdls[1:]):
                try: mod.load_weights(weightfname, by_name=True) if mod else print('Model {} not built, skipping...'.format(i+1))
                except Exception as E: sys.excepthook(*sys.exc_info())
                else: self.config.get('verbose') and print('Loaded weights for model {}...'.format(i+1))
            else: print('Weight loading complete.')
                
            if not messy:
                try: os.remove(weightfname)
                except Exception as E: sys.excepthook(*sys.exc_info())
        else:
            print('No model found!')
            
    def predictor_dump(self, fname=NotImplemented, model_ind=2):
        if fname is NotImplemented: fname = 'preddump.csv'
        predwgts = self.model[model_ind].get_weights()[-1]
        predwgts = pd.DataFrame(predwgts)
        try: predwgts = predwgts.set_index(self.prediction.index)
        except Exception as E: print('Could not set indices!')
        try: predwgts = predwgts.rename(columns={'0':'IN', '1':'NN', '2':'PN', '3':'PP'})
        except Exception as E: print('Could not set column names!')
        if fname: predwgts.to_csv(fname, index_label='Gene', )
        return predwgts
        
    dump_predictors = preddump = predictor_dump #aliases
    
    
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
    argparser.add_argument('-R', '--recompile', action='store_true')
    args = vars(argparser.parse_args())
    sys.exit(main(**args))

