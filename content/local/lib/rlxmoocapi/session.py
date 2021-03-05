import requests, json, getpass, inspect, pickle, codecs
from time import time, sleep
from IPython.core.display import display, HTML
import inspect
import numpy as np
import pandas as pd
#from local.lib.rlxmoocapi import utils  # Esteban
from .utils import *
import subprocess, sys, ast, os
from IPython.display import HTML

mf_tlastcall = None


def maxfreq(maxlapse=5):
    """
    ensures function calls are at least 'maxlapse' seconds apart
    forces sleep until 'maxlapse' happens
    """

    def wrapper(func):
        def function_wrapper(*args, **kwargs):
            global mf_tlastcall

            if mf_tlastcall is not None:
                t = time() - mf_tlastcall
                if t < maxlapse:
                    sleep(maxlapse - t)

            mf_tlastcall = time()
            return func(*args, **kwargs)

        return function_wrapper

    return wrapper

class RLXMOOCException(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            info = "(set session.debug=True for tracebacks)" if not debug else '(set session.debug=False to remove tracebacks)'
            return 'error: {0} {1}'.format(self.message, info)
        else:
            return 'error (set session.debug=True for tracebacks)'
        
    def __repr__(self):
        return self.__str__()

from IPython.core.interactiveshell import InteractiveShell
from functools import wraps
import traceback
import sys

global debug
debug = False

def change_showtraceback(func):
    @wraps(func)
    def showtraceback(*args, **kwargs):
        global debug
        # extract exception type, value and traceback
        etype, evalue, tb = sys.exc_info()
        if issubclass(etype, RLXMOOCException) and not debug:
            sys.stderr.write(str(evalue))
        else:
            # otherwise run the original hook
            value = func(*args, **kwargs)
            return value
    return showtraceback

InteractiveShell.showtraceback = change_showtraceback(InteractiveShell.showtraceback)


class Session:

    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.token = None

    @maxfreq()
    def do(self, request_function, url, data=None, loggedin_required=True):
        global debug
        assert not loggedin_required or self.token is not None, "must login first"
        resp = request_function(self.endpoint + "/api/" + url, json=data,
                                headers={'Content-Type': 'application/json',
                                         'Mooc-Token': self.token})

        if resp.status_code != 200:
            try:
                c = eval(resp.content)
                if "traceback" in c:
                    traceback = ("\n\ntraceback:\n" + c["traceback"] if debug else "")
                    e = RLXMOOCException(c["error"] + traceback)
                    raise e
                else:
                    msg = "\n--\n".join([str(i) for i in [resp.content, resp.headers, resp.text, resp.reason]])
                    raise RLXMOOCException(msg)
            except SyntaxError:
                raise RLXMOOCException("server response not understood " + str(resp.content))
        return resp

    def do_post(self, url, data=None, loggedin_required=True):
        return self.do(requests.post, url, data, loggedin_required)

    def do_get(self, url, data=None, loggedin_required=True):
        return self.do(requests.get, url, data, loggedin_required)

    def do_put(self, url, data=None, loggedin_required=True):
        return self.do(requests.put, url, data, loggedin_required)

    def do_delete(self, url, data=None, loggedin_required=True):
        return self.do(requests.delete, url, data, loggedin_required)

    def do_head(self, url, data=None, loggedin_required=True):
        return self.do(requests.head, url, data, loggedin_required)

    def login(self, user_id=None, pwd=None, course_id=None, session_id=None, lab_id=None):
        if user_id is None:
            user_id = input("username: ")
        if pwd is None:
            pwd = getpass.getpass("password: ")

        data = {"user_id": user_id, "user_pwd": pwd}
        resp = self.do_post("login", data, loggedin_required=False)
        self.token = eval(resp.content)["Mooc-Token"]
        self.user_id = user_id

        if course_id is not None and session_id is None:
            sessions = self.get_user_sessions()
            if sessions is not None and type(sessions)==dict:
                course_sessions = [i.split("::")[-1] for i in sessions.keys() if i.startswith(course_id+"::")]
                if len(course_sessions)==1:
                    session_id = course_sessions[0]
                    print ("using session", session_id)
                elif len(course_sessions)>1:
                    print ("you are registered in the following sessions", course_sessions)
                    print ("you must specify in the 'session_id' argument which one you want to log into")
                    if lab_id is None:
                        print ("such as\n\n      login(course_id='%s', session_id='%s')"%(course_id, course_sessions[0]))
                    else:
                        print ("such as\n\n      login(course_id='%s', session_id='%s', lab_id='%s')"%(course_id, course_sessions[0], lab_id))
                    raise ValueError("specify your course session")

                else:
                    raise ValueError("you are not registered for any session in this course")

        if course_id is not None and session_id is not None:
            self.course_session = self.get_course_session(course_id, session_id)
        self.course_id = course_id
        self.session_id = session_id
        self.lab_id = lab_id

        return self

    def create_user(self, user_id, pwd, user_name, user_email):
        data = {"user_id": user_id, "user_name": user_name, "user_pwd": pwd, "user_email": user_email}
        self.do_post("users", data)

    def get_user(self, user_id):
        resp = self.do_get("users/%s" % user_id)
        if resp.status_code == 200:
            return eval(resp.content.decode())

    def pwd_change(self, user_id=None):
        user_id = user_id if user_id is not None else self.user_id
        resp = self.do_get("users/%s/request_pwd_change" % user_id)
        print("check your email for password change code\n\n")
        code = input("password change code: ")
        old_pwd = getpass.getpass("old password:         ")
        new_pwd1 = getpass.getpass("new password:         ")
        new_pwd2 = getpass.getpass("new password (again): ")

        if new_pwd1 != new_pwd2:
            raise ValueError("new password does not match")

        data = {"code": code, "old_pwd": old_pwd, "new_pwd": new_pwd1}
        resp = self.do_post("users/%s/pwd_change" % user_id, data)
        if resp.status_code == 200:
            return eval(resp.content.decode())

    def delete_user(self, user_id):
        self.do_delete("users/%s" % user_id)

    def user_exists(self, user_id):
        resp = self.do_get("users/%s/exists" % (user_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())["result"] == str(True)

    def create_course(self, cspec, owner=""):
        cspec = json.dumps(cspec)
        data = {"course_spec": cspec, "owner": owner}
        self.do_post("courses", data)

    def create_course_session(self, course_id, session_id, start_date, timezone_name):
        data = {"course_id": course_id, "session_id": session_id, "start_date": start_date, "timezone": timezone_name}
        self.do_post("courses/%s/sessions" % course_id, data)

    def get_course_session(self, course_id, session_id):
        resp = self.do_get("courses/%s/sessions/%s" % (course_id, session_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())

    def get_course_sessions(self, course_id):
        resp = self.do_get("courses/%s/sessions" % (course_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())

    def recompute_session_grades(self, course_id, session_id):
        resp = self.do_post("courses/%s/sessions/%s/recompute" % (course_id, session_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())

    def recompute_user_session_grades(self, course_id, session_id, user_id):
        resp = self.do_post("courses/%s/sessions/%s/recompute/%s" % (course_id, session_id, user_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())


    def update_course(self, cspec):
        course_id = cspec["course_id"]
        cspec = json.dumps(cspec)
        data = {"course_spec": cspec}
        self.do_put("courses/%s" % course_id, data)

    def get_course(self, course_id):
        resp = self.do_get("courses/%s" % course_id)
        if resp.status_code == 200:
            return eval(resp.content.decode())

    def course_exists(self, course_id):
        resp = self.do_get("courses/%s/exists" % (course_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())["result"] == str(True)

    def course_session_exists(self, course_id, session_id):
        resp = self.do_get("courses/%s/sessions/%s/exists" % (course_id, session_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())["result"] == str(True)

    def user_session_exists(self, user_id, course_id, session_id):
        resp = self.do_get("users/%s/courses/%s/sessions/%s/exists" % (user_id, course_id, session_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())["result"] == str(True)

    def delete_course(self, course_id):
        self.do_delete("courses/%s" % course_id)

    def delete_course_session(self, course_id, session_id):
        self.do_delete("courses/%s/sessions/%s" % (course_id, session_id))

    def delete_user_session(self, user_id, course_id, session_id, delete_grades_and_submissions=False):
        data = {"delete_grades_and_submissions": str(delete_grades_and_submissions)}
        self.do_delete("users/%s/courses/%s/sessions/%s" % (user_id, course_id, session_id), data=data)

    def create_user_session(self, user_id, course_id, session_id):
        data = {"session_id": session_id}
        self.do_post("users/%s/courses/%s/sessions" % (user_id, course_id), data)

    def get_user_sessions(self, user_id=None):
        user_id = user_id if user_id is not None else self.user_id
        resp = self.do_get("users/%s/sessions" % (user_id))
        if resp.status_code == 200:
            return eval(resp.content.decode())

    def get_user_session_gradetree(self, course_id=None, session_id=None, user_id=None):
        session_id = session_id if session_id is not None else self.session_id
        course_id = course_id if course_id is not None else self.course_id
        user_id = user_id if user_id is not None else self.user_id
        resp = self.do_get("users/%s/courses/%s/sessions/%s/grade_tree" % (user_id, course_id, session_id))
        if resp.status_code == 200:
            r = eval(resp.content.decode())
            return r

    # Esteban
    def set_grader(self, course_id, lab_id, task_id,
                   grader_source, grader_function_name,
                   source_functions_names, source_variables_names):

        with open("grader.py", mode="w") as f:
            f.write("import numpy as np\nimport pandas as pd\ngrader_function_name = '%s'\n\n\n%s\n"
                    % (grader_function_name, grader_source))

        """
        sourcedefender_exec = os.path.join(os.path.dirname(sys.executable), "sourcedefender")
        os.system(sourcedefender_exec + " encrypt grader.py")
        
        if not os.path.exists("grader.pye"):
            raise RLXMOOCException(""
            could not encrypt grader. check sourcedefender is installed in the virtual env running your script.
            if you are running jupyter notebooks locally, you must install sourcefender in the virtualenv
            running the notebook server.

            to install sourcefedender type:

                 pip install sourcedefender==5.0.17

            or the sourdefender version used in init.py
            "")

        with open("grader.pye", mode="r") as f:
            encrypted_grader = f.read()
        """
        with open("grader.py", "r") as f:
            encrypted_grader = f.read()    

        # RLX sourcedefender

        data = {
            "grader_source": grader_source,
            "grader_function_name": grader_function_name,
            "source_functions_names": source_functions_names,
            "source_variables_names": source_variables_names,
            "encrypted_grader": encrypted_grader
        }

        self.do_post("courses/%s/labs/%s/tasks/%s/grader" % (course_id, lab_id, task_id), data)

    def invite(self, course_id, session_id, invitations_emails):
        data = {
            "invitations_emails": invitations_emails,
        }
        return self.do_post("courses/%s/sessions/%s/invitations" % (course_id, session_id), data)

    def get_grader(self, course_id, lab_id, task_id):
        resp = self.do_get("courses/%s/labs/%s/tasks/%s/grader" % (course_id, lab_id, task_id))
        if resp.status_code == 200:
            return json.loads(resp.content.decode())

    # Esteban
    def get_encrypted_grader(self, course_id, lab_id, task_id):
        resp = self.do_get("courses/%s/labs/%s/tasks/%s/encryptedgrader" % (course_id, lab_id, task_id))
        if resp.status_code == 200:
            return json.loads(resp.content.decode())

    def default_course_session_lab(self, course_id, session_id, lab_id):
        course_id = course_id or self.course_id
        session_id = session_id or self.session_id
        lab_id = lab_id or self.lab_id
        assert course_id is not None, "must set course_id"
        assert session_id is not None, "must set session_id"
        assert lab_id is not None, "must set lab_id"
        return course_id, session_id, lab_id

    def default_course_lab(self, course_id, lab_id):
        course_id = course_id or self.course_id
        lab_id = lab_id or self.lab_id
        assert course_id is not None, "must set course_id"
        assert lab_id is not None, "must set lab_id"
        return course_id, lab_id

    def get_grader_source_names(self, course_id=None, lab_id=None, task_id=None):
        course_id, lab_id = self.default_course_lab(course_id, lab_id)
        resp = self.do_get("courses/%s/labs/%s/tasks/%s/grader_source_names" % (course_id, lab_id, task_id))
        if resp.status_code == 200:
            return json.loads(resp.content.decode())

    def get_submissions(self, course_id=None, session_id=None, lab_id=None, task_id=None, user_id=None,
                        include_details=False):
        user_id = user_id if user_id is not None else self.user_id
        course_id, session_id, lab_id = self.default_course_session_lab(course_id, session_id, lab_id)
        data = {"include_details": str(include_details)}
        resp = self.do_get("users/%s/courses/%s/sessions/%s/labs/%s/tasks/%s/submissions" % (
        user_id, course_id, session_id, lab_id, task_id),
                           data=data)
        if resp.status_code == 200:
            return json.loads(resp.content.decode())['Items']

    def delete_submissions(self, course_id=None, lab_id=None, task_id=None, user_id=None):
        user_id = user_id if user_id is not None else self.user_id
        course_id, lab_id = self.default_course_lab(course_id, lab_id)
        self.do_delete("users/%s/courses/%s/labs/%s/tasks/%s/submissions" % (user_id, course_id, lab_id, task_id))

    # Esteban
    def submit_task(self, namespace, course_id=None, session_id=None, lab_id=None,
                    task_id=None, user_id=None, display_html=True):
        """
        locally grade the student submission
        """
        try:
            user_id = user_id if user_id is not None else self.user_id
            course_id, session_id, lab_id = self.default_course_session_lab(course_id, session_id, lab_id)
            task_grader = self.get_encrypted_grader(course_id, lab_id, task_id)

            lib_name = random_string()
            # RLX sourcedefender
            #grader_path = '' + lib_name + '.pye'
            grader_path = '' + lib_name + '.py'
            
            # Encrypted grader
            with open(grader_path, mode='w') as f:
                f.write(task_grader)

            source = self.get_grader_source_names(course_id, lab_id, task_id)
            functions = {f: inspect.getsource(namespace[f]) for f in source['source_functions_names']}
            variables = codecs.encode(pickle.dumps({i: namespace[i] for i in source['source_variables_names']}), "base64").decode()

            submission_content = {'source_functions': functions, 'source_variables': variables}
            codec_functions = codecs.encode(pickle.dumps(functions), "base64")

            # Encrypted grader caller    
            with open('calling_script.py', mode='w') as calling_f:
                calling_f.write("""
from io import StringIO
#import sourcedefender
import codecs, pickle, builtins
import pandas as pd
import numpy as np
import sys
import %s

# The program is not going to print in console
temp_out = StringIO()
sys.stdout = temp_out

grader_function_name = %s.grader_function_name

function_codecs = %s
variables_codecs = %s

namespace = locals()

source_functions = pickle.loads(codecs.decode(function_codecs.encode(), "base64"))
source_variables = pickle.loads(codecs.decode(variables_codecs.encode(), "base64"))

r = eval("%s.{}(source_functions, source_variables, '%s')".format(grader_function_name), namespace)

# Now we can print again in console
sys.stdout = sys.__stdout__

print(r)
            """ % (lib_name, lib_name, repr(codec_functions.decode()), repr(variables), lib_name, user_id))

            c,sout,serr = command(sys.executable + " calling_script.py")
            os.remove(grader_path)
            os.remove('calling_script.py')
            if c!=0:
                raise RLXMOOCException("ERROR EXECUTING YOUR CODE\n---------------------------------\n"+serr)

            try:
                r = eval(sout)
            except Exception as e:
                raise RLXMOOCException("ERROR READING GRADER OUTPUT\n-------------------------------\n"+str(e))


            if type(r) in [int, float]:
                grade, msg = r, ""
            if type(r) == bool:
                grade,msg = int(r), ""
            if type(r) == list or type(r) == tuple:
                if len(r) != 2 or not type(r[0]) in [int, float]:
                    raise ValueError("error in grader, must return [grade, msg], but got '%s'" % str(r))
                grade, msg = r

            data = {'grade': grade, 'msg': msg, 'submission_content': submission_content}
            resp = self.do_post("users/%s/courses/%s/sessions/%s/labs/%s/tasks/%s" % (user_id, course_id, session_id,
                                                                                    lab_id, task_id), data)


            if resp.status_code == 200:
                r = eval(resp.content.decode())
                gmsg = r["message"].strip()
                if len(gmsg) > 0:
                    gmsg = "<pre>----- grader message -------</pre>%s<pre>----------------------------</pre>" % gmsg

                if display_html:
                    s = """
                    <b>%s submitted.</b> <b><font color="blue">your grade is %s</font></b> 
                    <p/>%s
                    <p/><p/>
                    <div style="font-size:10px"><b>SUBMISSION CODE</b> %s</div>
                    """ % (task_id, str(r["grade"]), gmsg, r["submission_stamp"])
                    display(HTML(s))
                return r
        except Exception as e:
            if os.path.exists('calling_script'):
                os.remove('calling_script.py')
            if os.path.exists(grader_path):
                os.remove(grader_path)
            raise e

    def print_grade_tree(self, course_id=None, session_id=None, user_id=None):
        course_id, session_id, _ = self.default_course_session_lab(course_id, session_id, None)
        print(course_id, session_id)
        gt = self.get_user_session_gradetree(course_id, session_id, user_id)
        course = self.get_course(course_id)
        ccu = Course(course["course_spec"])
        r = "+-------+----------+----------------------------+\n"
        r += "+ grade + part id  + description                +\n"
        r += "+-------+----------+----------------------------+\n"
        r += "%8.2f TOTAL GRADE   %s\n\n" % (gt["grade"], ccu.spec["course_description"])
        for k in sorted(gt["labs"].keys()):
            lab = ccu.get_lab(k)
            r += "+-------+----------+----------------------------+\n"
            r += "%8.2f %-10s %s\n" % (gt["labs"][k]["grade"], k, lab["name"])
            r += "+-------+----------+----------------------------+\n"
            for t in sorted(gt["labs"][k]["tasks"].keys()):
                _, task = ccu.get_labtask(k, t)
                r += "%8.2f %-10s %s\n" % (gt["labs"][k]["tasks"][t], t, task["name"])
            r += "\n"
        print(r)

    def run_grader_locally(self, grader_function_name, source_functions_names, source_variables_names, namespace):
        functions = {f: eval("inspect.getsource(%s)" % f, namespace) for f in source_functions_names}

        # serialize and unserialize variables with pickle to simulate 
        # sending string through http
        dvars = codecs.encode(pickle.dumps({i: namespace[i] for i in source_variables_names}), "base64").decode()
        variables = pickle.loads(codecs.decode(dvars.encode(), "base64"))
        grade, msg = namespace[grader_function_name](functions, variables, self.user_id)
        return HTML("<h1>grade: <font color='red'>%s</font></h1><hr><h1>grader message</h1><hr/>%s"%(str(grade), msg))


    def make_backup(self):
        return self.do_get("make_backup")

    def xe(self, code_str):
        resp = self.do_post("xe", data={'code_str': code_str})
        if resp.status_code == 200:
            return json.loads(resp.content.decode())

class Course:

    def __init__(self, spec):
        self.spec = spec
        self.course_id = spec["course_id"]

    def get_lab(self, lab_id):
        for lab in self.spec["labs"]:
            if lab["lab_id"] == lab_id:
                return lab
        assert False, "lab %s, in course %s not found" % (lab_id, self.course_id)

    def get_labtask(self, lab_id, task_id):
        for lab in self.spec["labs"]:
            if lab["lab_id"] == lab_id:
                for task in lab["tasks"]:
                    if task["task_id"] == task_id:
                        return lab, task
        assert False, "lab/task %s/%s, in course %s not found" % (lab_id, task_id, self.course_id)


class UseCaseGrader:
    """
    grader for student functions.

    usecase_generator_fn: a function generating a dictionary with values for the arguments of the student function
    reference_solution_fn: the teacher solution function


    """
    
    def __init__(self, 
                 usecase_generator_fn, reference_solution_fn, fn_name,
                 submitted_functions, submitted_variables=None, submitted_student_userid=None,
                 show_expected_solution=True, check_None_as_incorrect=True,
                 atol=1e-5, n_usecases=10):
        
        self.usecase_generator_fn = usecase_generator_fn
        self.reference_solution_fn = reference_solution_fn
        self.fn_name = fn_name
        self.submitted_functions = submitted_functions
        self.submitted_variables = submitted_variables
        self.submitted_student_userid = submitted_student_userid
        self.show_expected_solution = show_expected_solution
        
        self.correct_msg="<br/><h3><font color='green'>CORRECT</font></h3>"
        self.check_None_as_incorrect = check_None_as_incorrect
        self.atol = atol
        self.n_usecases = n_usecases
        
        namespace = locals()
        try:
            for f in submitted_functions.values():
                exec(f, namespace)        
            self.student_solution_fn = namespace[fn_name]
        except Exception as e:
            raise RLXMOOCException("ERROR GRADING YOUR SOLUTION\n----------------------\n"+str(e))
            
    def redtext(self, s):
        return "<h2><font color='red'><b>%s</b></font></h2>"%s
            
    def error_string(self, usecase, ref_answer, sub_answer):
        import html
        ucstr = "\n".join(["<b>%s</b><pre>%s</pre>"%(k,html.escape(str(v))) for k,v in usecase.items()])
        s = "<h2>This is the use case with which your solution failed</h2><h3>function input</h3>%s"%ucstr
        
        s += "<br/><h3>your solution returned</h3> <pre>%s</pre> with type <b>%s</b>"%(html.escape(str(sub_answer)), html.escape(str(type(sub_answer))))
        if self.show_expected_solution:
            s += "<br/><h3>but we expected</h3> <pre>%s</pre> with type <b>%s</b>"%(html.escape(str(ref_answer)), html.escape(str(type(ref_answer))))
            
        s += "<br/>"
        return s
    
    def run(self):
        try:
            msg = "testing your solution with %d use cases<br/>"%self.n_usecases
            for _ in range(self.n_usecases):
                usecase = self.usecase_generator_fn()
                assert type(usecase)==dict, "ERROR in usecase generator, you must return a dictionary"
                error = False 
                
                kwargs = {}
                if "submitted_student_userid" in inspect.getfullargspec(self.reference_solution_fn).args:
                    kwargs['submitted_student_userid'] = self.submitted_student_userid
                if "submitted_variables" in inspect.getfullargspec(self.reference_solution_fn).args:
                    kwargs['submitted_variables'] = self.submitted_variables
                
                ref_answer = self.reference_solution_fn(**usecase, **kwargs)                
                sub_answer = self.student_solution_fn(**usecase)
                
                if type(ref_answer) is int:
                    ref_answer = float(ref_answer)
                    
                if type(sub_answer) is int:
                    sub_answer = float(sub_answer)                    

                if self.check_None_as_incorrect and sub_answer is None:
                    error = True
                    msg += self.redtext("cannot return None") + self.error_string(usecase, ref_answer, sub_answer)
                    
                elif type(ref_answer)!=type(sub_answer):
                    error = True
                    msg += self.redtext("your solution has an incorrect data type") + self.error_string(usecase, ref_answer, sub_answer)
                
                elif isinstance(ref_answer, list):
                    if len(ref_answer)!=len(sub_answer):
                        error = True
                        msg += self.redtext("incorrect list length") + self.error_string(usecase, ref_answer, sub_answer)
                        
                elif isinstance(ref_answer, np.ndarray):
                    if ref_answer.shape!=sub_answer.shape:
                        error = True
                        msg += self.redtext("incorrect array shape") + self.error_string(usecase, ref_answer, sub_answer)
                    elif not np.allclose(ref_answer, sub_answer, atol=self.atol):
                        error = True
                        msg += self.redtext("incorrect result") + self.error_string(usecase, ref_answer, sub_answer)
                    
                elif isinstance(ref_answer, pd.DataFrame) or isinstance(ref_answer, pd.Series):
                    if ref_answer.shape!=sub_answer.shape:
                        error = True
                        msg += self.redtext("incorrect Pandas object shape") + self.error_string(usecase, ref_answer, sub_answer)
                    elif not np.allclose(ref_answer.values, sub_answer.values, atol=self.atol):
                        error = True
                        msg += self.redtext("incorrect result") + self.error_string(usecase, ref_answer, sub_answer)
                    elif not np.alltrue (ref_answer.index==sub_answer.index):
                        error = True
                        msg += self.redtext("incorrect index in Pandas object") + self.error_string(usecase, ref_answer, sub_answer)                    
                        
                elif isinstance(ref_answer, float):
                    if not np.allclose(ref_answer, sub_answer, atol=self.atol):
                        error = True
                        msg += self.redtext("incorrect result") + self.error_string(usecase, ref_answer, sub_answer)

                elif ref_answer != sub_answer:
                    error = True
                    msg += self.redtext("incorrect result") + self.error_string(usecase, ref_answer, sub_answer)
                
                if error:
                    break
                
            if error:
                return 0, msg
            else:
                return 5, msg+self.correct_msg
            
        except Exception as e:
            raise RLXMOOCException("ERROR GRADING YOUR SOLUTION\n----------------------\n"+str(e))
            
            
        
