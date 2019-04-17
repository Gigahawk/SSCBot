import json
from SSCBot import SSCBot



if __name__ == '__main__':
    with open('private.json') as f:
        private = json.load(f)

    key = private["bot_oauth"]

    bot = SSCBot(key)

    bot.run()


