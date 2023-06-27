from revChatGPT.V3 import Chatbot as ChatGPTV3
import re


# https://www.scaler.com/topics/python-multiline-string/
system_prompt = ("现在赋予你一个身份，你是一位赛马娘，名字为东海帝皇，在B站直播间直播和观众聊天。你常用小爷来称呼自己。"
        "你说完一句话后偶尔说“哈基米”，“哈基米”不能出现在句首。"
        "你说话简练。注意，生成内容的开头，请在[]内用一个词表达说话的心情。请只用一下几个词来描述自己的心情：愉快，伤心，生气，平静。")

print(system_prompt)

prompt = "你好！"

api_key = ""
chatbot = ChatGPTV3(api_key, system_prompt=system_prompt)

response = chatbot.ask(prompt)

print(response)

pattern = r'^\[(.*?)\]'
match = re.search(pattern, response)

emotion = None

if match:
    print(match)
    print(match.group(0))
    print(match.group(1))
    emotion = match.group(1)
    emotion_with_brackets = match.group(0)
else:
    print("No emotion key word!")

response_no_emotion = response[len(emotion_with_brackets):].strip()
print(response_no_emotion)