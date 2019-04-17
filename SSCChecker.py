from threading import Thread
import requests as req
from time import sleep
from queue import Queue
from bs4 import BeautifulSoup


class SSCChecker:
    grades_url = "https://ssc.adm.ubc.ca/sscportal/servlets/SRVAcademicRecord"
    login_url = "https://cas.id.ubc.ca/ubc-cas/login"

    def __init__(self, channel, data_out, user, pw=None, grades=None):
        self.form_data = {
                "username": "",
                "password": "",
                "_eventId": "submit",
                "geolocation": "",
                "execution": ""
                }
        if grades is None:
            self.grades = []
        else:
            self.grades = grades

        self.user = user
        self.channel = channel
        self.data_out = data_out
        self.queue = Queue()
        self.sess = req.Session()

        # Attempt to login if user and password supplied
        if pw:
            self.login(self.user, pw)

    def run(self):
        self.check_thread = Thread(target=self._loop, daemon=True)
        self.check_thread.start()

    def _loop(self):
        while True:
            grades = self.get_grades()
            # Sorta inefficient but only the main thread
            # can/should access the database
            for grade in grades:
                query = next((x for x in self.grades if (
                    x["subject"] == grade["subject"] and
                    x["course_code"] == grade["course_code"])), None)

                if query is None:
                    # course not currently in memory, add to list
                    self.grades.append(grade)
                    # Notify main thread
                    payload = {
                            "grade": grade
                            }
                    msg = self._create_msg("new_grade", payload)
                    self.data_out.put(msg)
                elif query != grade:
                    # New course info
                    self.grades.remove(query)
                    self.grades.append(grade)
                    # Notify main thread
                    payload = {
                            "grade": grade
                            }
                    msg = self._create_msg("grade_update", payload)
                    self.data_out.put(msg)
            sleep(1)

    def _create_msg(self, _type, payload):
        msg = {
                "channel": self.channel,
                "user": self.user,
                "type": _type,
                "payload": payload
                }
        return msg

    def _create_form_data(self, user, pw, execution):
        form_data = {
                "username": user,
                "password": pw,
                "_eventId": "submit",
                "geolocation": "",
                "execution": execution
                }
        return form_data

    @staticmethod
    def create_grade_entry(
            course,
            section,
            grade,
            total_credits,
            letter,
            session,
            term,
            program,
            year,
            credits,
            average,
            standing):

        subject = course.split()[0]
        course_code = course.split()[1]

        grade_entry = {
                "subject": str(subject),
                "course_code": str(course_code),
                "section": str(section),
                "grade": str(grade),
                "total_credits": str(total_credits),
                "letter": str(letter),
                "session": str(session),
                "term": str(term),
                "program": str(program),
                "year": str(year),
                "credits": str(credits),
                "average": str(average),
                "standing": str(standing)
                }
        return grade_entry

    def get_grades(self):
        grades = self.sess.get(self.grades_url)
        soup = BeautifulSoup(grades.text, "lxml")
        # Grab div with all grades
        grades = soup.find(attrs={"id": "tabs-all"})
        rows = grades.findAll("tr", attrs={"class": "listRow"})

        grades = []
        for row in rows:
            children = row.findChildren("td")

            course = children[0].text
            section = children[1].text
            grade = children[2].text
            total_credits = children[2]["credits"]
            letter = children[3].text
            session = children[4].text
            term = children[5].text
            program = children[6].text
            year = children[7].text
            credits = children[8].text
            average = children[9].text
            standing = children[10].text

            grade_entry = self.create_grade_entry(
                    course,
                    section,
                    grade,
                    total_credits,
                    letter,
                    session,
                    term,
                    program,
                    year,
                    credits,
                    average,
                    standing)
            grades.append(grade_entry)
        return grades

    def login(self, user, pw):
        login_page = self.sess.get(self.login_url)
        soup = BeautifulSoup(login_page.text, "lxml")
        # Looks like some kind of XSS prevention?
        execution = soup.find(attrs={"name": "execution"})["value"]
        form_data = self._create_form_data(user, pw, execution)
        login_data = self.sess.post(self.login_url, data=form_data)

        if "TGC" in self.sess.cookies.get_dict():
            grades = self.sess.get(self.grades_url)
            if grades.status_code == 200:
                # Send OK down data_out
                payload = {
                        "status": "success"
                        }
                msg = self._create_msg("login_status", payload)
                self.data_out.put(msg)

                # Start getting grades
                self.run()
            else:
                # Send not a student error
                payload = {
                        "status": "not_a_student"
                        }
                msg = self._create_msg("login_status", payload)
                self.data_out.put(msg)
        else:
            # Send bad login error
            payload = {
                    "status": "invalid_login"
                    }
            msg = self._create_msg("login_status", payload)
            self.data_out.put(msg)



