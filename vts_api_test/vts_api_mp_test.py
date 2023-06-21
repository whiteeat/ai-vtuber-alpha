import asyncio

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

        plugin_name = "expression controller"
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
        
        await myvts.request_authenticate()

        while True: 
            vts_api_task = self.vts_api_queue.get()

            if vts_api_task is None:
                # Poison pill means shutdown
                print(f"{proc_name}: Exiting")
                break

            msg_type = vts_api_task.msg_type
            data = vts_api_task.data
            request_id = vts_api_task.request_id

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

            response = await myvts.request(request_msg)

            # https://datagy.io/python-check-if-dictionary-empty/
            # The expression_response[‘data’] dict should be empty if the request is successful.
            assert not bool(response['data'])
            
        await myvts.close()

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
        user_input = input("Press 1 to activate, 2 to deactivate, 0 to quit:\n")
        if user_input == '1':
            active = True
        elif user_input == '2':
            active = False
        elif user_input == '0':
            vts_api_queue.put(None)
            break
        else:
            continue
        
        msg_type = "ExpressionActivationRequest"
        expression_file = "test.exp3.json"
        expression_request_data = {
            "expressionFile": expression_file,
            "active": active
        }

        vts_api_task = VTSAPITask(msg_type, expression_request_data)

        vts_api_queue.put(vts_api_task)
    
    vts_api_process.join()