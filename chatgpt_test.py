from revChatGPT.V1 import Chatbot as ChatGPTV1
from revChatGPT.V3 import Chatbot as ChatGPTV3

USE_API_KEY = True
USE_ACCESS_TOKEN = False

prompt_cn = "你好！"
prompt_en = "Hello!"

if USE_API_KEY:
    api_key = ""
    chatbot = ChatGPTV3(api_key)

    result = chatbot.ask(prompt_cn)
    print(result)
    print()


if USE_ACCESS_TOKEN:
    # The address to get access_token:
    # https://chat.openai.com/api/auth/session
    access_token = ""

    chatbot = ChatGPTV1(config={
        "access_token": access_token
    })

    # email = ""
    # password = ""

    # chatbot = Chatbot(config={
    #     "email": email,
    #     "password": password
    # })

    for data in chatbot.ask(
        prompt_cn
    ):
        response = data["message"]

    print(response)
    print()
    print("========================================")


    print("Chinese Test: ")
    prev_text = ""
    for data in chatbot.ask(
        prompt_cn
    ):
        message = data["message"][len(prev_text):]
        print(message, flush=True)
        prev_text = data["message"]

    print("English Test: ")
    prev_text = ""
    for data in chatbot.ask(
        prompt_en
    ):
        message = data["message"][len(prev_text):]
        print(message, flush=True)
        prev_text = data["message"]