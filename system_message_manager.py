class SystemMessageManager:
    def __init__(self):
        with open("system_messages/sm_main.txt", "r") as f:
            f = open("system_messages/sm_main.txt", "r", encoding="utf-8")
        
            self.systetm_message = f.read()
            print(self.systetm_message)

if __name__ == "__main__":
    system_message_manager = SystemMessageManager()