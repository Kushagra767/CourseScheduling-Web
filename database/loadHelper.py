from CourseScheduling.blueprints.schedule.models import Course, Requirement, SubReq, Major, Quarter
import json
import warnings
from database.Validator import CourseValidator, InvalidJsonError, RequirementValidator
from database.schemas import CourseSchema, RequirementsSchema

def load_quarters():
    qdict = ['fall 1', 'winter 1', 'spring 1', 'fall 2', 'winter 2', 'spring 2']
    for idx, value in enumerate(qdict):
        # clean old quarter
        Quarter.objects(name=value).update_one(code=idx,upsert=True)
        qdict[idx] = Quarter.objects(name=value).first()
    return qdict


def format_quarters(qlist, qdict):
    qlist = list(qlist)
    for i in range(len(qlist)):
        qlist[i] = qdict[qlist[i]]
    return qlist

def getDeptCid(course):
    a_tuple = course.strip().split(' ')
    return ' '.join(a_tuple[:-1]), a_tuple[-1]

def format_prereqs(prereqs):
    """
    convert OR sets to OR lists in order to load them into the db
    :param prereqs:
        in format [{'CSE46', 'I&CSCI23', 'CSE23', 'I&CSCI46', 'I&CSCIH23'},
                             {'I&CSCI6B'}, {'I&CSCI6D'}, {'MATH2B'}]
    :return:
        prereqs in format:
        [['CSE46', 'I&CSCI23', 'CSE23', 'I&CSCI46', 'I&CSCIH23'],
                             ['I&CSCI6B'], ['I&CSCI6D'], ['MATH2B']]
        """

    output = []
    for or_set in prereqs:
        output.append([])
        for course in or_set:   
            # ex. PHY SCI 122B 
            # assume the last segment is the cid, everything in front of cid is a dept
            dept, cid = getDeptCid(course)
            course_obj = Course.objects(dept=dept, cid=cid).first()
            if course_obj:
                output[-1].append(course_obj)
        if not output[-1]: output.pop()
    return output


def load_course(filename):
    """
    load course info to database from txt file
    :param filename: txt file path
    :param delete: delete all courses in db if True
    sample line:
        COMPSCI;161;DES&ANALYS OF ALGOR;
        [{'CSE46', 'I&CSCI23', 'CSE23', 'I&CSCI46', 'I&CSCIH23'},
        {'I&CSCI6B'}, {'I&CSCI6D'}, {'MATH2B'}];4;{0, 1, 2, 3, 4};False
    """
    qdict = load_quarters()
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            CourseValidator(data, CourseSchema.SCHEMA)
            for k, c in data.items():
                Course(name=c['name'], cid=c['cid'], units=c['units'], upperOnly=c['upperOnly'], dept=c['dept'],
                    quarters=[Quarter.objects(code=x).first() for x in c['quarters']]).save()

    except FileNotFoundError as e:
        print("json loading ERROR: ", e)
        raise e
    except InvalidJsonError as e:
        print("json validation ERROR", e)
        raise e

    else:
        print("Successfully loaded json file", filename)
        # to refer to the course object, we have to load courses without adding prereqs first,
        # and add the prereqs later
        with open(filename, 'r') as f:
            for k, c in json.load(f).items():
                Course.objects(cid=c['cid'], dept=c['dept']).update_one(prereq=format_prereqs(c['prereqs']))

        print ("updated prerequisites")

def load_requirement(filename):
    """
    load requirement info to database from txt file
    this one does not consider the recommand!
    :param filename: txt file path
    """

    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            RequirementValidator(data, RequirementsSchema.SCHEMA)
            name = data.get('major')
            Major.objects(name=name.upper()).upsert_one(requirements=[])
            major = Major.objects(name=name).first()
            reqs = data.get('requirements', [])
            specs = data.get('specs', [])
            cnt = 0
            err_msg = ""
            for req in reqs+specs:
                Requirement.objects(name=req['name']).update_one(sub_reqs=[], upsert=True)
                requirement = Requirement.objects(name=req['name']).first()
                for subr in req.get('sub_reqs', []):
                    subreq = SubReq(req_list=[], req_num=subr['req_num'])
                    for c in subr.get("req_list", []):
                        dept, cid = getDeptCid(c)
                        if not Course.objects(dept=dept, cid=cid).first():
                            err_msg += "Error in {} \n".format(dept+" "+cid)
                            continue
                        subreq.req_list.append(Course.objects(dept=dept, cid=cid).first())
                    requirement.sub_reqs.append(subreq)
                requirement.save()
                if cnt < len(reqs):
                    major.requirements.append(requirement)
                else:
                    major.specs.append(requirement)
                cnt += 1
            major.save()
    except FileNotFoundError as e:
        print("json loading ERROR: ", e)
        raise e
    except InvalidJsonError as e:
        print("json validation ERROR", e)
        raise e
    else:
        print("Successfully loaded json file", filename)
        if err_msg:
            warnings.warn("error exists during loading, skipped: \n" + err_msg)

