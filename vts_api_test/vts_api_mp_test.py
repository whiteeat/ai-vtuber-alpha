import asyncio
import queue

import multiprocessing

import pyvts

class VTSAPIProcess(multiprocessing.Process):
    def __init__(
            self,
            vts_api_queue):
        super().__init__()
        self.vts_api_queue = vts_api_queue

    async def main(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

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


class VTSAPITask:
    def __init__(self, msg_type, data, request_id=None):
        self.msg_type = msg_type
        self.data = data
        self.request_id = request_id

if __name__ == "__main__":
    vts_api_queue = multiprocessing.Queue(maxsize=4)

    # event_vts_api_process_initialized = multiprocessing.Event()

    vts_api_process = VTSAPIProcess(vts_api_queue)
    vts_api_process.start()

    while True:
        user_input = input(("Press 1 to set test, "
                            "2 to unset test, "
                            "3 to set Happy, "
                            "4 to unset Happy, "
                            "5 to clear, "
                            "6 wrong hotkey name to test, "
                            "0 to quit:\n"))
        if user_input == '1':
            expression = "test"
            active = True
        elif user_input == '2':
            expression = "test"
            active = False
        elif user_input == '3':
            expression = "Happy"
            active = True
        elif user_input == '4':
            expression = "Happy"
            active = False
        elif user_input == '5':
            msg_type = "HotkeyTriggerRequest"
            data_dict = {
                "hotkeyID": "Clear"
            }
            vts_api_task = VTSAPITask(msg_type, data_dict)
            vts_api_queue.put(vts_api_task)
            continue
        elif user_input == '6':
            msg_type = "HotkeyTriggerRequest"
            data_dict = {
                "hotkeyID": "WrongHotkeyName"
            }
            vts_api_task = VTSAPITask(msg_type, data_dict)
            vts_api_queue.put(vts_api_task)
            continue
        elif user_input == '7':
            msg_type = "HotkeyTriggerRequest"
            data_dict = {
                "hotkeyID": "MoveEars"
            }
            vts_api_task = VTSAPITask(msg_type, data_dict)
            vts_api_queue.put(vts_api_task)
            continue
        elif user_input == '0':
            vts_api_queue.put(None)
            break
        else:
            continue
        
        msg_type = "ExpressionActivationRequest"
        expression_file = f"{expression}.exp3.json"
        expression_request_data = {
            "expressionFile": expression_file,
            "active": active
        }

        vts_api_task = VTSAPITask(msg_type, expression_request_data)

        vts_api_queue.put(vts_api_task)
    
    vts_api_process.join()