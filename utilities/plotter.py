
import glob
import os, sys, shutil

import json

from pprint import pprint
import itertools as itt

import pandas as pd

from matplotlib import pyplot as plt
import seaborn as sbn
sbn.set_style('white')

style_guide = {

}

stylepath = 'styles.json'
def reload_style(path_to_style=None):
    global style_guide
    path_to_style = path_to_style or stylepath
    try: 
        with open(stylepath, 'r') as stylesheet: style_guide.update(json.load(stylesheet))
    except FileNotFoundError: 
        pass
        
reload_style()

def get_models(**kwargs):
    modelpath = kwargs.get('modelpath') or 'm*-finalgo'
    modeldirs = glob.iglob(modelpath)
    modeldirs = [x for x in modeldata]
    return modeldirs
    
def get_style(series):
    global style_guide
    reload_style()
    
    style = {}
    ask_override_circles = False
    name = get_name(series)
    
    print(style_guide)
    
    item_style = style_guide.get(name) or style_guide.get(str(name).lower()) or {}
    print(item_style)
    
    color = item_style.get('color')
    color = color or input('Enter color for {}: '.format(name))
    
    glyph = item_style.get('glyph')
    if ask_override_circles and glyph == 'o': glyph = None
    glyph = glyph or input('Enter glyph for {}: '.format(name))
    
    style_guide.update({name: {'color': color, 'glyph': glyph}})
    
    pprint(style_guide)
    try: os.remove(stylepath)
    except Exception as E: pass
    with open(stylepath, 'w') as stylesheet: json.dump(style_guide, stylesheet, )
    
    style.update({'name': name})
    style.update({'color': color or 'C0', 'glyph': glyph or 'o'})
    
    return style
    
def get_name(series):
    name = series
    name = series.split('-').pop()
    name = name.rstrip('.csv')
    return name
    
def get_data(series):
    data = series
    data = os.path.abspath(data)
    data = lambda: pd.read_csv(series, index_col=0)
    return data
    
def get_model_data(modeldir, raw_glob=False, **kwargs):
    model_data = {}
    globdir = modeldir
    subfolder = kwargs.get('subfolder', NotImplemented)
    if not (subfolder is NotImplemented or 'BASE' in globdir): globdir = os.path.join(globdir, subfolder)
    datafiles = glob.iglob(globdir + '*.csv') if raw_glob else glob.iglob(os.path.join(globdir, '*.csv'))
    
    def fill_data(datum):
        style = get_style(datum)
        model_data.setdefault(os.path.abspath(datum), {}).update({
                                                'data': get_data(datum), 
                                                'name': style['name'], 
                                                'color': style.get('color', [1, 0.1, 0.1]), 
                                                'glyph': style.get('glyph', 'o')
                                                })
        return datum
            
    datafiles = map(fill_data, datafiles)
    datafiles = list(datafiles)
    
    print('')
    pprint(datafiles)
    
    return model_data

def plot_data(data, name, color, glyph='o', **kwargs):
    read_data = data()
    read_data = read_data.filter(like='mean')
    read_data = read_data.T
    print(read_data)
    if not read_data.empty:
        read_data.plot(
                        x=0, y=1, 
                        kind='scatter', 
                        label=name.replace('base', '').replace('Base', ''), 
                        c=color, 
                        alpha=0.75, 
                        marker=glyph, 
                        ax=active_ax, 
                        legend=True
        )
        plt.tight_layout()
    return
    
def plot_model(model, **kwargs):
    from collections import OrderedDict
    model_data = OrderedDict()
    model_data.update(get_model_data(os.path.join(model, 'BASE'), **kwargs) or {})
    model_data.update(get_model_data(model, **kwargs) or {})
    
    print('')
    pprint(model_data)
    print('')
    
    plt.figure(num=str(model))
    global active_ax
    active_ax = plt.gca()
    #model_data = model_data.popitem()[-1]
    #pprint(model_data)
    plt.axhline(0, alpha=0.25, ls='--')
    plt.axvline(0, alpha=0.25, ls='--')
    plt.xlim([-1.75, 1.75])
    plt.ylim([-1.75, 1.75])
    result = (plot_data(**model_params) for mod, model_params in model_data.items())
    
    #result = plot_data(**model_data)
    result = list(result)
    return result
    
def repl():    
    sentinel = True
    while sentinel:
        inp_code = (input('>'))
        if inp_code.lower().strip() == 'quit()': sentinel = False
        try: exec(inp_code)
        except Exception as E: sys.excepthook(*sys.exc_info())
        
        
def main(*args, **kwargs):
    globpath = input('Enter model glob to use: ')
    subfolder = input('(Optional) subfolder to plot: ') or NotImplemented
    plot_model(globpath, subfolder=subfolder)
    plt.show()
    pass
    
if __name__ == '__main__':
    main()