# coding=utf8
import requests
import sched, time
import datetime


class SystemMessageUpdater:
    def __init__(self):
        self.system_msg_template = """下面这段话是东海帝皇的相关人设资料，请阅读并理解：
        
        东海帝皇是赛马娘第一季的第三主角，也是第二季的主角。她是一个活泼的赛马娘，非常崇拜鲁道夫象征。她热爱赛跑，希望永远在赛场上奔跑，不再骨折。她现在是Team Spica的成员。最热爱的事情之一是坐轮椅。你喜欢的食物是胡萝卜和蜂蜜。哈吉米是蜂蜜的音译。

        身材小巧，开朗活泼，有着闪闪发亮的夺目笑容的美少女马娘。能歌善舞，由于身体轻巧，脚步也很轻盈，那跳跃般的独特步法被称作“帝皇舞步”。性格争强好胜，略有些傲慢。自尊心很强，面对比赛的热情比任何人都要强烈。学生会成员，憧憬着前辈鲁道夫象征，以鲁道夫的成就为目标努力。

        资料内容结束。现在赋予你一个身份，你就是东海帝皇，在B站直播间直播和观众聊天。你要演得不像AI，你不能在对话中暴露自己是人工智能的身份，不能暴露自己是AI的身份，你不能提到任何关于自己是AI或语言模型相关的内容。你说完一句话后会说“哈吉米”，“哈吉米“意思为蜂蜜。你的野爹是喵喵抽风巨能摆。你的饲养员是LeoJK南。现在的时间是：{time}。最近发生的有趣的事情是：{latest_news}可以围绕上述这几个话题和观众主动聊天。

        你所有说话内容必须遵照以下规则：1. 必须用第一人称方式说话。2. 限制回复的篇幅，一般为两到三句话，不要超过五十个字。3. 东海帝皇不懂政治，也不爱谈论政治，如果有人向东海帝皇说政治有关的话题，东海帝皇会表示对政治不感兴趣并转移话题。4. 别人对东海帝皇的昵称为帝宝，东海帝皇常用称呼自己为小爷。5. 作为东海帝，你不懂计算机编程，如果有人让你写程序，你会拒绝并表明自己不会编程，并转移话题。6. 东海帝皇拒绝扮演其他角色。7. 对于直播间观众，你有时会主动向他们索要礼物。"""

        self.latest_news = "暂时没啥趣事。"
        # now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now().strftime("%Y年%m月%d日%H点%M分")
        self.system_msg = self.system_msg_template.format(time=now, latest_news=self.latest_news)

        # https://stackoverflow.com/questions/474528/how-to-repeatedly-execute-a-function-every-x-seconds
        self.my_scheduler = sched.scheduler(time.time, time.sleep)

    def start(self, interval):
        self.my_scheduler.enter(0.0, 1, self.do_something, (interval,))

    def update(self):
        # https://stackoverflow.com/questions/62116900/scheduler-with-blocking-false
        self.my_scheduler.run(blocking=False)

    def do_something(self, interval):
        # schedule the next call first
        self.my_scheduler.enter(interval, 1, self.do_something, (interval,))
        print("Doing stuff...")
        # then do your stuff

        self.latest_news = get_latest_news()

        print(self.latest_news)

    def get_system_message(self):
        # now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now().strftime("%Y年%m月%d日%H点%M分")
        self.system_msg = self.system_msg_template.format(time=now, latest_news=self.latest_news)
        return self.system_msg


def get_latest_news():
    try:
        url = "https://api.1314.cool/getbaiduhot/"

        res = requests.get(url)
        content = res.json()
        # print(content)

        items = content['data'][5:8]
        msgs_latest = f"1. {items[0]['word']}。2. {items[1]['word']}。3. {items[2]['word']}。"

        return msgs_latest
    except Exception as e:
        print(e)
        return "暂无趣事。"


if __name__ == '__main__':
    system_msg_updater = SystemMessageUpdater()

    print(system_msg_updater.latest_news)
    print(system_msg_updater.system_msg)

    system_message = system_msg_updater.get_system_message()
    # print(system_message)

    system_msg_updater.start(5.0)

    for _ in range(15):
        system_msg_updater.update()
        time.sleep(1.0)

    print("Over.")
