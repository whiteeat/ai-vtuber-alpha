from revChatGPT.V1 import Chatbot

access_token = ""

chatbot = Chatbot(config={
    "access_token": access_token
})

prompt = "你好！"
response = ""

for data in chatbot.ask(
    prompt
):
    response = data["message"]

print(response)
print()
print("========================================")


print("Chinese Test: ")
prev_text = ""
for data in chatbot.ask(
    "你好"
):
    message = data["message"][len(prev_text):]
    print(message, flush=True)
    prev_text = data["message"]

print("English Test: ")
prev_text = ""
for data in chatbot.ask(
    "Hello"
):
    message = data["message"][len(prev_text):]
    print(message, flush=True)
    prev_text = data["message"]