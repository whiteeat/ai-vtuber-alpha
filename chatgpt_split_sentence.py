from revChatGPT.V1 import Chatbot

access_token = ""

punctuations_to_split_paragraphs = set("。！？")
punctuations_to_split_paragraphs_longer = set(",")

min_sentence_length = 16
sentence_longer_threshold = 32

chatbot = Chatbot(config={
    "access_token": access_token
})

prompt = "测试。请随便跟我说一段100字左右的话。"

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
        if new_sentence[-1] in punctuations_to_split_paragraphs:
            should_split = True
        elif len(new_sentence) >= sentence_longer_threshold:
            if new_sentence[-1] in punctuations_to_split_paragraphs_longer:
                should_split = True
    
    if should_split:
        sentences.append(new_sentence)
        new_sentence = ""

    prev_message = message

print()
print(message)
print(sentences)