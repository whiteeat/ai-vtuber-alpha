import asyncio
import queue

import re
import multiprocessing

import pyvts

import logging

class ExpressionHelper:
    # emotion_to_expression = {
    #     "愉快": "Happy",
    #     "伤心": "Sad",
    #     "生气": "Angry",
    #     "平静": "neutral"
    # }
    emotion_to_expression = {}

    def get_emotion_and_line(response):
        pattern = r'^\[(.*?)\]'
        match = re.search(pattern, response)

        if match:
            emotion = match.group(1)
            emotion_with_brackets = match.group(0)

            return emotion, response[len(emotion_with_brackets):]
        else:
            return None, response
        
    def emotion_to_expression_file(emotion):
        if emotion in ExpressionHelper.emotion_to_expression:
            expression = ExpressionHelper.emotion_to_expression[emotion]
            return f"{expression}.exp3.json"
        else:
            return None
        

class VTSAPITask:
    def __init__(self, msg_type, data, request_id=None):
        self.msg_type = msg_type
        self.data = data
        self.request_id = request_id

class VTSAPIProcess(multiprocessing.Process):
    def __init__(
            self,
            vts_api_queue):
        super().__init__()
        self.vts_api_queue = vts_api_queue

    async def main(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        logging.getLogger("websockets").setLevel(logging.WARNING)

        plugin_name = "Expression Controller"
        developer = "Rotten Work"
        authentication_token_path = "./token.txt"

        plugin_info = {
            "plugin_name": plugin_name,
            "developer": developer,
            "authentication_token_path": authentication_token_path
        }

        myvts = pyvts.vts(plugin_info=plugin_info)
        
        try:
            await myvts.connect()
        except Exception as e:
            print(e)
            return

        try:
            await myvts.read_token()
            print("Token file found.")
        except FileNotFoundError:
            print("No token file found! Do authentication!")
            await myvts.request_authenticate_token()
            await myvts.write_token()
        
        success = await myvts.request_authenticate()

        if not success:
            print("Token file is invalid! request authentication token again!")
            await myvts.request_authenticate_token()
            await myvts.write_token()

            success = await myvts.request_authenticate()
            assert success

        while True:
            try:
                # vts_api_task = self.vts_api_queue.get_nowait()
                vts_api_task = self.vts_api_queue.get(block=True, timeout=10)
                if vts_api_task is None:
                    # Poison pill means shutdown
                    print(f"{proc_name}: Exiting")
                    break 

                msg_type = vts_api_task.msg_type
                data = vts_api_task.data
                request_id = vts_api_task.request_id

            except queue.Empty:
                # Heartbeat
                # await myvts.websocket.send("Ping")
                msg_type = "HotkeyTriggerRequest"
                data = {
                    "hotkeyID": "Clear"
                }
                
                request_id = None

            if msg_type == "ExpressionActivationRequest":
                pass
            elif msg_type == "HotkeyTriggerRequest":
                pass
            else:
                print(f"There is no such messageType: {msg_type}!")
                continue

            if request_id is None:
                request_msg = myvts.vts_request.BaseRequest(
                    msg_type,
                    data,
                    f"{msg_type}ID"
                )
            else:
                request_msg = myvts.vts_request.BaseRequest(
                    msg_type,
                    data,
                    request_id
                )

            try:
                response = await myvts.request(request_msg)
                print(response)

                if msg_type == "ExpressionActivationRequest":
                    # https://datagy.io/python-check-if-dictionary-empty/
                    # The expression_response[‘data’] dict should be empty if the request is successful.
                    assert not bool(response['data']), "ExpressionActivationRequest Error!"
                elif msg_type == "HotkeyTriggerRequest":
                    # https://stackoverflow.com/questions/17372957/why-is-assertionerror-not-displayed
                    assert "errorID" not in response['data'], "HotkeyTriggerRequest Error!"
            except AssertionError as e:
                print(e)
            except Exception as e:
                print(e)
                try:
                    # https://support.quicknode.com/hc/en-us/articles/9422611596305-Handling-Websocket-Drops-and-Disconnections
                    print("Reconnect")
                    await myvts.connect()
                    await myvts.request_authenticate()
                except Exception as e:
                    print(e)
                    return

        try:
            await myvts.close()
        except Exception as e:
            print(e)

    def run(self):
        asyncio.run(self.main())
