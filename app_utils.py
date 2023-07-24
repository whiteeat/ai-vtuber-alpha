class AppState:
    CHAT = 1
    PRESING = 2
    SING = 3

class ChatTask:
    def __init__(self, user_name, message, channel):
        self.user_name = user_name
        self.message = message
        self.channel = channel
