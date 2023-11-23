import multiprocessing
import threading

# g_data = 1

class Test:
    data = 0

def task():
    # global g_data

    # print(f'child process: {g_data}')
    print(f'child process: {Test.data}')
    # g_data = 2
    Test.data = 2
    # print(f'child process: {g_data}')
    print(f'child process: {Test.data}')
    print("blah")
 
if __name__ == '__main__':
    # https://superfastpython.com/multiprocessing-inherit-global-variables-in-python/
    # g_data = 1
    Test.data = 1

    # multiprocessing.set_start_method('spawn')

    # print(f'main process: {g_data}')
    print(f'main process: {Test.data}')
    process = multiprocessing.Process(target=task)
    process.start()
    process.join()

    # thread = threading.Thread(target=task)
    # thread.start()
    # thread.join()

    # print(f'main process: {g_data}')
    print(f'main process: {Test.data}')
