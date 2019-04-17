from threading import Thread
from tabulate import tabulate
import sqlite3
from queue import Queue
from slackclient import SlackClient
from SSCChecker import SSCChecker

class SSCBot:
    _sql_select_grades = """
    SELECT
        subject,
        course_code,
        section,
        grade,
        letter,
        session,
        term,
        program,
        year,
        total_credits,
        credits,
        average,
        standing
    FROM grades WHERE user_id=?
    """
    def __init__(self, key, db_file="user.db"):
        print("init")
        self.db_file = db_file
        self.db = sqlite3.connect(self.db_file)
        self._init_db()
        self.clnt = SlackClient(key)
        self.ssc_checkers = []
        self.queue = Queue()

        if self.clnt.rtm_connect(with_team_state=False):
            self._id = self.clnt.api_call("auth.test")["user_id"]
            self._init_users()
        else:
            raise ConnectionError("Couldnt connect to slack")

    def _loop(self):
        self.db = sqlite3.connect(self.db_file)
        # Enable cascade delete
        self.db.execute("PRAGMA foreign_keys = ON")

        while True:
            self.handle_queue()
            self.parse_commands(self.clnt.rtm_read())

    def _init_users(self):
        c = self.db.cursor()

        for row in c.execute("SELECT id, channel, username FROM users"):
            user_id = row[0]
            channel = row[1]
            username = row[2]
            checker = SSCChecker(channel, self.queue, username)
            msg = "Looks like we crashed, ur gonna have to reregister"
            self._send_msg(channel, msg)
        self.db.close()

    def _reply(self, evt, msg):
        self.clnt.api_call("chat.postMessage", channel=evt["channel"], text=msg)

    def _send_msg(self, channel, msg):
        self.clnt.api_call("chat.postMessage", channel=channel, text=msg)

    def run(self):
        self.bot_thread = Thread(target=self._loop)
        self.bot_thread.start()

    def handle_queue(self):
        if self.queue.empty():
            return
        msg = self.queue.get()

        if msg["type"] == "login_status":
            self.handle_login_update(msg)
        elif msg["type"] == "new_grade":
            self.add_grade(msg)
        elif msg["type"] == "grade_update":
            self.update_grade(msg)

    def handle_login_update(self, msg):
        channel = msg["channel"]
        user = msg["user"]
        status = msg["payload"]["status"]
        if status == "success":
            msg = "Registration successful!"
            self._send_msg(channel, msg)
        else:
            msg = f"Registration error: {status}"
            self._send_msg(channel, msg)
            # Remove invalid entry from table
            c = self.db.cursor()
            sql = """
            DELETE FROM users WHERE username=? AND channel=?
            """
            c.execute(sql, (user, channel))

    def add_grade(self, msg):
        channel = msg["channel"]
        user = msg["user"]
        grade = msg["payload"]["grade"]
        user_id = self.get_user_id(uesr, channel)
        c = self.db.cursor()
        sql = """
        INSERT INTO grades (
            user_id,
            subject,
            course_code,
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
            standing
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (
                user_id,
                grade["subject"],
                grade["course_code"],
                grade["section"],
                grade["grade"],
                grade["total_credits"],
                grade["letter"],
                grade["session"],
                grade["term"],
                grade["program"],
                grade["year"],
                grade["credits"],
                grade["average"],
                grade["standing"]
                )
        c.execute(sql, values)
        self.db.commit()

        # Notify of new grade
        msg = f"New Grade: \n{self.format_grade(grade)}"
        self._send_msg(channel, msg)

    def update_grade(self, msg):
        channel = msg["channel"]
        user = msg["user"]
        grade = msg["payload"]["grade"]
        user_id = self.get_user_id(user, channel)
        c = self.db.cursor()

        sql = """
        UPDATE grades
        SET
            grade = ?,
            letter = ?,
            credits = ?,
            average = ?,
            standing = ?
        WHERE
            user_id = ? AND
            subject = ? AND
            course_code = ? AND
            section = ? AND
            session = ? AND
            term = ?
        """
        values = (
                grade["grade"],
                grade["letter"],
                grade["credits"],
                grade["average"],
                grade["standing"],

                user_id,
                grade["subject"],
                grade["course_code"],
                grade["section"],
                grade["session"],
                grade["term"]
                )
        c.execute(sql, values)
        self.db.commit()
        # Notify of new grade
        msg = f"Updated Grade: \n{self.format_grade(grade)}"
        self._send_msg(channel, msg)

    def format_grade(self, grade):
        course = f"{grade['subject']} {grade['course_code']}"
        credits_earned = grade["credits"] if grade["credits"] else 0
        credits = f"{credits_earned}/{grade['total_credits']}"
        grd = f"{grade['grade']} ({grade['letter']})"
        average = f"{grade['average']}"


        response = f"""
        *{course}*
        _Grade_: {grd}
        _Average_: {average}
        _Credits_: {credits}
        """
        return response



    def parse_commands(self, events):
        for event in filter(lambda x: x["type"]=="message" and "user" in x.keys(), events):
            if event["channel"].startswith("D"):
                args = event["text"].split()
                if args[0] == "help":
                    self.send_help(event)
                elif args[0] == "register":
                    self.register(event, args)
                elif args[0] == "grades":
                    self.get_grades(event, args)
                else:
                    self.send_err(event)

    def send_help(self, evt, cmd=None):
        if not cmd:
            response = "yea im too lazy to write help for now"
            self._reply(evt, response)
            return

    def send_err(self, evt):
        response = "lmao ur dum"
        self._reply(evt, response)
        return

    def register(self, evt, args):
        print("register")
        if len(args) != 3:
            self.send_err(evt)
            return

        user = args[1]
        pw = args[2]
        channel = evt["channel"]

        # Check to see if user already exists (reregistering)
        user_id = self.get_user_id(user, channel)
        c = self.db.cursor()
        if user_id is None:
            # User not in database, add user
            self._reply(evt, "Checking if login info is valid...")
            sql = """
            INSERT INTO users (
                username,
                channel
            ) VALUES (?, ?)
            """

            c.execute(sql, (user, channel))
            self.db.commit()

            checker = SSCChecker(channel, self.queue, user=user, pw=pw)
            self.ssc_checkers.append(checker)
        else:
            # User already in database, grab old grades
            self._reply(evt, f"Reregistering user id {user_id}")
            sql = self._sql_select_grades
            c.execute(sql, (user_id,))
            data = c.fetchall()
            grades = []
            for row in data:
                subject = row[0]
                course_code = row[1]
                section = row[2]
                grade = row[3]
                letter = row[4]
                session = row[5]
                term = row[6]
                program = row[7]
                year = row[8]
                total_credits = row[9]
                credits = row[10]
                average = row[11]
                standing = row[12]

                course = f"{subject} {course_code}"

                grades.append(SSCChecker.create_grade_entry(
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
                    standing))
            checker = SSCChecker(channel, self.queue, user=user, pw=pw, grades=grades)
            self.ssc_checkers.append(checker)

    def get_user_id(self, user, channel):
        c = self.db.cursor()
        if user is None:
            # no user specified, return all user_ids for this channel as a list
            sql = """
            SELECT id FROM users WHERE channel=?
            """
            data = c.execute(sql, (channel,)).fetchall()
            user_ids = [x[0] for x in data]
            return user_ids
        else:
            sql = """
            SELECT id FROM users WHERE username=? AND channel=?
            """
            data = c.execute(sql, (user, channel)).fetchone()
            if data is None:
                return None
            user_id = data[0]
            return user_id

    def get_grades(self, evt, args):
        channel = evt["channel"]
        if len(args) < 2:
            user_ids = self.get_user_id(None, channel)
            self._reply(evt, "unimplemented")
        else:
            user = args[1]
            user_id = self.get_user_id(user, channel)
            c = self.db.cursor()
            sql = self._sql_select_grades
            c.execute(sql, (user_id,))
            data = list(c.fetchall())

            for x in range(len(data)):
                data[x] = list(data[x])
                data[x][9:11] = ['/'.join([str(i) for i in reversed(data[x][9:11])])]
                # Merge subject and course code
                data[x][0:2] = [' '.join(data[x][0:2])]
            headers = [
                    "Course", "Section", "Grade",
                    "Letter", "Session", "Term", "Program",
                    "Year", "Credits", "Average", "Standing"
                    ]
            msg = f"""
```
{tabulate(data, headers=headers)}
```
            """
            self._reply(evt, msg)

    def _init_db(self):
        user_schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            channel TEXT,
            UNIQUE(username, channel)
        );
        """

        grades_schema = """
        CREATE TABLE IF NOT EXISTS grades (
            user_id INTEGER,
            subject TEXT,
            course_code TEXT,
            section TEXT,
            grade INTEGER,
            letter TEXT,
            session TEXT,
            term INTEGER,
            program TEXT,
            year INTEGER,
            total_credits REAL,
            credits REAL,
            average INTEGER,
            standing TEXT,
            UNIQUE(user_id, subject, course_code),
            CONSTRAINT fk_users
                FOREIGN KEY(user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );
        """

        self.db.execute(user_schema)
        self.db.execute(grades_schema)
        self.db.commit()
