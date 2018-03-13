import glob
import pickle
import os, os.path, sys
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import re

DATA_COLNAME = 'Target'

def ask_for_files():
    files = set()
    while not files: 
        filename=str(input('Input the name of the file to parse: '))
        files.update(glob.glob(filename))
        if not files: print('Invalid filename! Try again!')
    return files

# parsers
def parse_datasets(files=None, verbose=False, *args, **kwargs):
    files = glob.glob(files) if files else files
    if not files: 
        if verbose: files = ask_for_files()
    for filepath in files:
        table = []
        filename = os.path.basename(filepath)
        accession = re.match('([A-Z]{3}\d+?)-.*', filename)
        accession = accession.group(1) if accession else filename
        with open(filepath) as file:
            try:
                table = pd.read_table(file,
                                     names = (DATA_COLNAME, accession))
            except Exception as E:
                sys.excepthook(*sys.exc_info())
        if verbose: 
            print ('Could not parse {}!'.format(filename) if not any(table) else '{} parsed successfully.'.format(filename))
        yield table


def parse_miniml(files=None, tags=None, junk_phrases=None, verbose=False, *args, **kwargs):
    if tags is None: tags = {'sample'}
    if junk_phrases is None: junk_phrases = {'{http://www.ncbi.nlm.nih.gov/geo/info/MINiML}',}
    files = glob.glob(files) if files else files
    if not files:
        if verbose: files = ask_for_files()
        else: return list()
    data = []
    for filename in files:
        xml_data = None
        with open(filename) as xml_file:
            xml_data = xml_file.read()
        if xml_data:
            root = ET.XML(xml_data)
            all_records = []
            if verbose: verbose = True if 'n' == input('Mute ([Y]/n): ').lower().strip() else False
            
            def parse_node(xml_node):
                _verbosity = verbose
                print("\nPARSING {}\n".format(xml_node))
                #print(dir(xml_node), '\n\n')
                #print(xml_node)
                parsed_records = []
                for child in xml_node:
                    print(child)
                    record = {}
                    #if not any((tag.lower() in xml_node.tag.lower() for tag in tags)): continue
                    
                    # MAKE ME RECURSiVE!
                    subtext = (child.text or '').strip()
                    subtag = child.tag
                    for junk in junk_phrases:
                        subtag = subtag.replace(junk, '')
                    #if not all((subtag, subtext)): continue
                    record[subtag] = subtext
                    if _verbosity or True:
                        print (child, child.attrib)#dir(child))
                        situation = input('\n[B]reak/[S]ilence/[Continue]: ').strip()
                        print('')
                        if situation == 'B': return list()
                        if situation == 'S': _verbosity = False
                        
                    record.update({child: parse_node(child)})
                    #print (record)
                return parsed_records
            
            all_records.extend(parse_node(root))
            
                
                
            data.append(pd.DataFrame(all_records))
    return data

# Low-level, intra-dataset cleaning logic.
def clean_xmls(parsed_input):
    cleaned = (x for x in parsed_input)
    print(next(cleaned)['Channel'])
    cleaned = (fr.set_index('Accession') for fr in cleaned)
    cleaned = (get_patient_type(fr) for fr in cleaned)
    #cleaned = (fr.transpose() for fr in cleaned)
    for clean_xml in cleaned:
        yield clean_xml

def get_patient_type(dframe):
    """Retrieves the label of the sample type from the Title field and returns it as a (new) dataframe."""
    #return dframe['Title']
    #print('TITLE IS: {}'.format(dframe['Title']))
    result = dframe['Title']
    try: result = dframe.transform({'Title' : lambda x: x.split('_')[-2]}) # 2 for mag, 1 for mag2
    except IndexError as IE: 
        print('Could not split the title!', file=sys.stderr)
        result = result.rename_axis('Title')
    except Exception: 
        sys.excepthook(*sys.exc_info())
    return result

def clean_data(raw_data):
    for datum in raw_data:
        cleaned = datum
        cleaned = cleaned.set_index(DATA_COLNAME)
        yield cleaned

# Higher-level logic for integration
def xml_pipeline(path=None, *args, **kwargs):
    raw_parse = parse_miniml(path or '*.xml', *args, **kwargs)
    cleaned = clean_xmls(raw_parse)
    return cleaned
   
def txt_pipeline(path=None, *args, **kwargs):
    raw_data = parse_datasets(path or '*.txt', *args, **kwargs)
    cleaned = clean_data(raw_data)
    return cleaned
    return raw_data #debugging purposes
    
def combo_pipeline(xml_path=None, txt_path=None, verbose=False, *args, **kwargs):
    xmls = xml_pipeline(path=xml_path, *args, **kwargs)
    #txts = txt_pipeline(path=txt_path, *args, **kwargs)
    count = 0

    for xml in xmls:
        sample_groups = xml.groupby('Title').groups
        print(xml)
        types = set(sample_groups.keys())
        pos = 0
        while types:
            batch = dict() #dict/set!
            ignored = set()
            for t in types:
                if t in ignored: continue
                try: 
                    batch.update({t : sample_groups[t][pos]}) #in dict
                    count += 1
                except IndexError as IE:
                    ignored.update(t)
            if not len(batch): break
            #print(batch)
            yield batch
            pos += 1
            
   
    print("\nFound {} datafiles. \n".format(count))
        

def main(xml=None, txt=None, verbose=None, *args, **kwargs):
    data = combo_pipeline(xml_path=xml, txt_path=txt, verbose=verbose)
    #start = (next(data))
    for d in data:
        #start = start.append(d, ignore_index=True)
        print (d)
        #print(d[0].columns.item(), d[1])
    #print(len(tuple(data)))
    #print(start.groupby('Type').groups)
    return 1

if __name__ == '__main__':
    import argparse
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--xml')
    argparser.add_argument('--txt')
    argparser.add_argument('-v', '--verbose', action='store_true')
    args = vars(argparser.parse_args())
    sys.exit(main(**args))



