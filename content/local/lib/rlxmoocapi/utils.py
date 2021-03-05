import json, notebook, re, inspect, uuid, os
import numpy as np
import subprocess
import random, string 

setgrader_regexp = "#(#*)\s*TEACHER\s*SETGRADER"
definegrader_regexp = "#(#*)\s*TEACHER\s*DEFINEGRADER"

def create_student_lab(source_notebook_fname, target_notebook_fname, 
                       enable_wgets=False, keep_all_output=False,
                       github_repo=None, github_init_prefix=""):
    assert source_notebook_fname!=target_notebook_fname, "source and target notebook file names must be different"
    nb = json.loads("\n".join(open(source_notebook_fname, "r").readlines()))

    rc = []
    for c in nb["cells"]:
        
        
        ## cells to ignore
        if c['cell_type']=='code' and "%%javascript" in "".join(c['source']) and \
           np.sum([re.search("^/+\s*TEACHER", i) is not None for i in c['source']])>0:
            continue
        if c['cell_type']=='code' and 'source' in c and\
          re.search("^\s*#(#*)\s*TEACHER", "".join(c['source'])) is not None:
                    continue
        if c['cell_type']=='code' and 'source' in c and\
          re.search("^\s*\/*\s*javscript", "".join(c['source'])) is not None:
                    continue
                
        ## uncomment wget lines
        if enable_wgets and c['cell_type']=='code' and 'source' in c:
            r = []
            for i in c['source']:
                if '##WGET_INIT##' in i and github_repo is not None:
                   i = "!wget --no-cache -O init.py -q https://raw.githubusercontent.com/%s/master/%s/init.py\n"%(github_repo, github_init_prefix)
                elif 'localhost:5000' in i:
                   i = None
                if i is not None:
                   r.append(i.replace("#!wget", "!wget"))
            c['source'] = r

        ## cells for which output is kept
        if keep_all_output:
            rc.append(c)
        elif c['cell_type']=='code' and 'source' in c and\
          re.search("^\s*Image\s*\(", "".join(c['source'])) is not None:
                    rc.append(c)
        elif c['cell_type']=='code' and 'source' in c and\
          re.search("^\s*#(#*)\s*KEEPOUTPUT", "".join(c['source'])) is not None:
            # remove the KEEPOUTPUT keyword, but keep the output
            c['source'] = re.sub("^\s*#(#*)\s*KEEPOUTPUT", '', "".join(c['source'])).split("\n")
            c['source'] = [i+"\n" for i in c['source']]
            rc.append(c)
        ## all the remaining code cells will get the output removed
        elif c['cell_type']=='code':
            c['outputs'] = []
            rc.append(c)
        else:
            rc.append(c)

    nb["cells"] = rc
    with open(target_notebook_fname, "w") as f:
        f.write(json.dumps(nb))

    print ("student notebook writen to '%s'"%target_notebook_fname)


def get_code_cells(source_notebook_fname, regexp):
    import json, re
    nb = json.loads("\n".join(open(source_notebook_fname, "r").readlines()))

    rc = []
    for c in nb["cells"]:
        if c['cell_type']=='code' and 'source' in c and\
          re.search(regexp, "".join(c['source'])) is not None:
            rc.append("".join(c["source"]))

    return "\n\n\n".join(rc)

def get_setgrader_cells(source_notebook_fname):
    return get_code_cells(source_notebook_fname, 
                          regexp=setgrader_regexp)

def get_definegrader_cells(source_notebook_fname):
    return get_code_cells(source_notebook_fname, 
                          regexp=definegrader_regexp)


def create_empty_course(admin, owner, course_id, course_description):
    cspec = { 
        "course_description": course_description,
        "course_id": course_id,
        "aggregate_labs_code": "wmean",
        "default_aggregate_tasks_code": "wmean",
        "default_aggregate_submissions_code": "max",
        "github_repo": "rlxmooc/sample_course",
        "labs": [        {
            "lab_id": "L01.01",
            "name": "Get acquanted with the grading platform",
            "start_week": 1,
            "weeks_duration": 10,
            "weight": 1,
            "tasks": [
                {
                    "name": "Manually compute max and min",
                    "task_id": "task_01",
                    "weight": 1
                },
                {
                    "name": "Function to compute mean and stdev",
                    "task_id": "task_02",
                    "weight": 1
                }
             ]
        },]
    }

    if admin.course_exists(course_id):
        raise ValueError("course %s already exists"%course_id)

    if type("owner")!=str:
        raise ValueError("owner must be an string with a user_id")

    admin.create_course(cspec, owner=owner)       
    print (cspec)

import inspect
def deploy_course(teacher, 
                  cspec_file,
                  set_grader_notebooks_fileglob=""):
    import json, re, inspect, pickle, base64, time
    
    steacher = base64.urlsafe_b64encode(pickle.dumps(teacher)).decode("utf-8")
    icode  = 'import pickle, base64\n'
    icode += "s='%s'\n"%steacher
    icode += 'teacher = pickle.loads(base64.urlsafe_b64decode(s))'    
    
    with open(cspec_file, "r") as f:
        cspec = json.loads(f.read())
    
    print ("course id: %s"%cspec["course_id"])

    teacher.update_course(cspec)       
    run_all_setgraders(teacher, cspec['course_id'], set_grader_notebooks_fileglob)   

def run_all_setgraders(teacher, course_id, 
                       set_grader_notebooks_fileglob=""):                
    import json, re, inspect, pickle, base64, time, glob
    notebooks = glob.glob(set_grader_notebooks_fileglob)
    for notebook in notebooks:
        print ("RUNNING SETGRADERS IN %-50s"%("'"+notebook+"'"), end=" .. ")
        code = get_definegrader_cells(notebook)
        code = code.replace("init.course_id", "'%s'"%course_id)
        
        unique_filename = 'rr'+str(uuid.uuid4()).replace("-","")
        
        with open("%s.py"%unique_filename, "w") as f:
            f.write(code)
        time.sleep(.5)
        code = get_setgrader_cells(notebook)
        code = code.replace("init.course_id", "'%s'"%course_id)
        code = "from %s import * \nimport inspect\n"%unique_filename+code
        print ("found %d setgraders"%len(re.findall(setgrader_regexp, code)))
        exec(code)

        os.remove(unique_filename+".py")


def deploy_session(teacher, course_id, session_id, start_date, force_reset=True):
    if teacher.course_session_exists(course_id, session_id):
        if force_reset:
            teacher.delete_course_session(course_id, session_id)
            print ("deleted session %s %s"%(course_id, session_id))
    print ("creating session %s %s, starting on %s"%(course_id, session_id, start_date))
    teacher.create_course_session(course_id, session_id, start_date)


#Esteban
def random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))


def xcommand(cmd):
    """
    Runs a command in the underlying shell

    Parameters:
    -----------

    cmd : str
        string containing the command to run

    Returns:
    --------
    code:  int
        return code from the executed command

    stdout: str
        captured standard output from the command

    stderr: str
        captured standard error from the command

    """
    try:
        # search for single quoted args (just one such arg is accepted)
        init = cmd.find("'")
        end  = len(cmd)-cmd[::-1].find("'")
        if init>0 and init!=end-1:
            scmd = cmd[:init].split() + [cmd[init+1:end-1]] + cmd[end+1:].split()
        else:
            scmd = cmd.split()

        p = subprocess.Popen(scmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout,stderr = p.communicate()
        code = p.returncode
    except Exception as e:
        stderr = str(e)
        code = 127
        stdout = ""

    stdout = stdout.decode() if type(stdout)==bytes else stdout
    stderr = stderr.decode() if type(stderr)==bytes else stderr

    return code, stdout, stderr

def command(cmd):
    remove_empty_lines = lambda s: "\n".join([i for i in s.split("\n") if i.strip()!=""])

    import os
    os.system("rm -rf /tmp/stdout /tmp/stderr")
    ret = os.system(cmd+" >/tmp/stdout 2>/tmp/stderr")

    try:
        stdout, stderr = "<no content>", "<no content>"
        with open("/tmp/stdout", "r") as f:
            stdout = "".join(f.readlines())
        with open("/tmp/stderr", "r") as f:
            stderr = "".join(f.readlines())
        os.system("rm -rf /tmp/stdout /tmp/stderr")
        return ret, stdout, stderr
    except Exception as e:
        os.system("rm -rf /tmp/stdout /tmp/stderr")
        raise ValueError(f"could not exec command\n--stdout--\n{stdout}\n--stderr--\n{stderr}\n--exception--"+str(e))

def convert_this_notebook_to_student(github_init_prefix="content", enable_wgets=True):
    # -----------------------------------
    # CREATE STUDENT NOTEBOOK
    # -----------------------------------

    # make sure the notebook is saved
    from IPython.display import HTML, display, Javascript
    display(Javascript('IPython.notebook.save_checkpoint();'))

    from local.lib.rlxmoocapi import utils

    # install library
    import sys, subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'ipynb-path'])

    # get notebook name
    import ipynb_path, os
    notebook_name = os.path.split(ipynb_path.get())[-1]

    # create student notebook
    if notebook_name.endswith("--XX--TEACHER--XX.ipynb"):
        student_notebook_name=notebook_name.split("--XX--TEACHER--XX.ipynb")[0]+'.ipynb'
        create_student_lab(notebook_name, student_notebook_name, 
                                 enable_wgets=enable_wgets,
                                 github_init_prefix=github_init_prefix)
        return student_notebook_name
    else:
        print ("THIS IS NOT A TECHER's NOTEBOOK, the notebook file name must end with ''--XX--TEACHER--XX.ipynb'")
        
   