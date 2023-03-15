import os

from revChatGPT.V1 import Chatbot as ChatbotV1
from revChatGPT.V3 import Chatbot as ChatbotV3

USE_API_KEY = True
USE_ACCESS_TOKEN = False

# punctuations_to_split_text = set("。！？")
# punctuations_to_split_text_longer = set(",")

punctuations_to_split_text = {'。', '！', '？', '：', '\n'}
punctuations_to_split_text_longer = {'，'}

min_sentence_length = 16
sentence_longer_threshold = 32

if USE_API_KEY:
    api_key = ""
    chatbot = ChatbotV3(api_key)

    prompt = "测试。请随便跟我说一段话，必须大于300字。"

    sentences = []
    new_sentence = ""
    length = 0
    for data in chatbot.ask(prompt):
        print(data, end="", flush=True)
        length += len(data)
        if len(data) > 1:
            print(data)

        should_split = False
        new_sentence += data
        if len(new_sentence) >= min_sentence_length:
            if new_sentence[-1] in punctuations_to_split_text:
                should_split = True
            elif len(new_sentence) >= sentence_longer_threshold:
                if new_sentence[-1] in punctuations_to_split_text_longer:
                    should_split = True

        if should_split:
            sentences.append(new_sentence.strip())
            new_sentence = ""

    if len(new_sentence) > 0:
        sentences.append(new_sentence)
    
    print()
    print(length)
    print(sentences)

access_token = ""

if USE_ACCESS_TOKEN:
    chatbot = ChatbotV1(config={
        "access_token": access_token
    })

    prev_message = ""
    sentences = []
    prompt_is_skipped = False
    new_sentence = ""
    for data in chatbot.ask(
        prompt
    ):
        message = data["message"]
        new_words = message[len(prev_message):]
        print(new_words, end="", flush=True)

        if not prompt_is_skipped:
            # The streamed response may contain the prompt,
            # So the prompt in the streamed response should be skipped
            new_sentence += new_words
            if new_sentence == prompt[:len(new_sentence)]:
                continue
            else:
                prompt_is_skipped = True
                new_sentence = ""

        should_split = False
        new_sentence += new_words
        if len(new_sentence) >= min_sentence_length:
            if new_sentence[-1] in punctuations_to_split_text:
                should_split = True
            elif len(new_sentence) >= sentence_longer_threshold:
                if new_sentence[-1] in punctuations_to_split_text_longer:
                    should_split = True
        
        if should_split:
            sentences.append(new_sentence)
            new_sentence = ""

        prev_message = message
    
    if len(new_sentence) > 0:
        sentences.append(new_sentence)

    print()
    print(message)
    print(sentences)