from revChatGPT.V1 import Chatbot as ChatbotV1
from revChatGPT.V3 import Chatbot as ChatbotV3

USE_API_KEY = True
USE_ACCESS_TOKEN = False

# punctuations_to_split_text = set("。！？")
# punctuations_to_split_text_longer = set(",")

punctuations_min_to_cut= {'。', '！', '？', '：', '\n'}
punctuations_threshold_to_cut = {'。', '！', '？', '：', '\n', '，'}

min_length = 16
threshold_length = 32

def should_cut_text(text, min, punctuations_min, threshold, punctuations_threshold):
    should_cut = False
    if len(text) >= min:
        if text[-1] in punctuations_min:
            should_cut = True
        elif len(text) >= threshold:
            if text[-1] in punctuations_threshold:
                should_cut = True

    return should_cut


if USE_API_KEY:
    api_key = ""
    chatbot = ChatbotV3(api_key)

    prompt = "测试。请随便跟我说一段话，必须大于300字。"

    sentences = []
    new_sentence = ""
    length = 0
    for data in chatbot.ask_stream(prompt):
        print(data, end='|', flush=True)
        length += len(data)
        # if len(data) > 1:
        #     print(data)

        new_sentence += data
        should_cut = should_cut_text(new_sentence, 
                                       min_length, 
                                       punctuations_min_to_cut, 
                                       threshold_length,
                                       punctuations_threshold_to_cut)

        if should_cut:
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

        new_sentence += new_words

        should_cut = should_cut_text(new_sentence, 
                                    min_length, 
                                    punctuations_min_to_cut, 
                                    threshold_length,
                                    punctuations_threshold_to_cut)
        
        if should_cut:
            sentences.append(new_sentence)
            new_sentence = ""

        prev_message = message
    
    if len(new_sentence) > 0:
        sentences.append(new_sentence)

    print()
    print(message)
    print(sentences)