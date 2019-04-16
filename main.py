import json
import time
from threading import Thread
from slackclient import SlackClient
import sqlite3

class SSCBot:
    def __init__(self, key, db_file="user.db"):
        self.db = sqlite3.connect(db_file)
        self._init_db()
        self.clnt = SlackClient(key)
        if self.clnt.rtm_connect(with_team_state=False):
            self._id = self.clnt.api_call("auth.test")["user_id"]

    def _loop(self):
        while True:
            self.parse_commands(self.clnt.rtm_read())

    def _reply(self, evt, msg):
        self.clnt.api_call("chat.postMessage", channel=evt["channel"], text=msg)

    def run(self):
        self.bot_thread = Thread(target=self._loop)
        self.bot_thread.start()

    def parse_commands(self, events):
        for event in filter(lambda x: x["type"]=="message" and "user" in x.keys(), events):
            print(event)
            if event["channel"].startswith("D"):
                args = event["text"].split()
                if args[0] == "help":
                    self.send_help(event)
                elif args[0] == "register":
                    self.register(event, args)
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
        if len(args) != 3:
            self.send_err(evt)
            return

        user = args[1]
        pw = args[2]

        self._reply(evt, f"{user} {pw}")

    def _init_db(self):
        user_schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT
        );
        """

        grades_schema = """
        CREATE TABLE IF NOT EXISTS grades (
            user_id INTEGER,
            subject TEXT,
            code TEXT,
            section TEXT,
            grade INTEGER,
            letter TEXT,
            session TEXT,
            term INTEGER,
            program TEXT,
            year INTEGER,
            credits REAL,
            average INTEGER,
            standing TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """

        self.db.execute(user_schema)
        self.db.execute(grades_schema)
        self.db.commit()


if __name__ == '__main__':
    with open('private.json') as f:
        private = json.load(f)

    key = private["bot_oauth"]

    bot = SSCBot(key)

    bot.run()


