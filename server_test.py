from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib
import multiprocessing
import json

class HTTPServerProcess(multiprocessing.Process):
    def __init__(self, server_class, handler_class, server_address, event_initialized=None):
        super().__init__()
        self.server_class = server_class
        self.handler_class = handler_class
        self.server_address = server_address
        self.event_initialized = event_initialized

    def run(self):
        # https://stackoverflow.com/questions/39815633/i-have-get-really-confused-in-ip-types-with-sockets-empty-string-local-host
        
        # https://pythonbasics.org/webserver/
        # try:
        print("Running HTTPServer...", flush=True)
        self.event_initialized.set()

        # 开启http服务，设置监听ip和端口
        self.httpd = self.server_class(self.server_address, self.handler_class)
        self.httpd.serve_forever()
        # except KeyboardInterrupt:
            # pass

class HttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        print(path)
        path, args = urllib.parse.splitquery(self.path)
        # self._response(path, args)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        message_test = "你好，东海帝皇！"
        data = {'result': message_test, 'status': 0}
        self.wfile.write(json.dumps(data).encode())

        # if message := get_message():
        #     data = {'result': message['text'], 'status': 0}
        #     self.wfile.write(json.dumps(data).encode())
        # else:
        #     data = {'result': '', 'status': -1}
        #     self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        args = self.rfile.read(int(self.headers['content-length'])).decode("utf-8")
        print("==================================================")
        print(args)
        print("==================================================")

        self._response(self.path, args)

    def _response(self, path, args):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()


if __name__ == '__main__':
    event_http_server_process_initialized = multiprocessing.Event()

    # https://stackoverflow.com/questions/39815633/i-have-get-really-confused-in-ip-types-with-sockets-empty-string-local-host
    # Empty string means '0.0.0.0'.
    server_address = ('', 8787)
    http_sever_process = HTTPServerProcess(HTTPServer, 
                                           HttpHandler, 
                                           server_address,
                                           event_http_server_process_initialized)
    
    http_sever_process.start()

    event_http_server_process_initialized.wait()

    while True:
        user_input = input("Please enter commands: ")
        if user_input == 'esc':
            break
        if user_input == '0':
            print("test")

    # https://superfastpython.com/kill-a-process-in-python/
    http_sever_process.terminate()
    http_sever_process.join()
    http_sever_process.close()