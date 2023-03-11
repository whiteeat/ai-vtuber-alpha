import time

import queue
import multiprocessing

import tkinter as tk
from tkinter import ttk

class SubtitleBar():
    def __init__(self, task_queue):
        self.lastClickX = 0
        self.lastClickY = 0

        self.window = tk.Tk()
        self.window.title('Subtitle')
        transparentcolor = "black"
        self.window.configure(bg=transparentcolor)
        # self.window.overrideredirect(True)
        # self.window.attributes('-topmost', True)
        self.window.geometry("512x512+256+256")
        self.window.bind('<Button-1>', self.SaveLastClickPos)
        self.window.bind('<B1-Motion>', self.Dragging)
        
        # https://www.tutorialspoint.com/python/tk_fonts.htm
        # #ffdb00
        self.text = tk.Label(self.window, wraplength=1024, font=("Noto Sans SC", 32, "bold"), fg="#ffdb00", bg=transparentcolor, text="这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕这是字幕")
        self.text.place(relx=0.5, rely=0.5, anchor='center')

        self.grip = ttk.Sizegrip(self.window)
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<B1-Motion>", self.OnMotion)

        # window.attributes('-alpha', 0.5)
        # self.window.wm_attributes("-transparentcolor", "black")

        # Ext_but = tk.Button(self.window, text="X", bg="#FF6666", fg="white", command=lambda: self.window.quit())
        # Ext_but.place(relx=1.0, rely=0, anchor="ne", width=16, height=16)

        self.task_queue = task_queue

        self.Update()
        self.window.mainloop()

    def SaveLastClickPos(self, event):
        global lastClickX, lastClickY
        lastClickX = event.x
        lastClickY = event.y

    def Dragging(self, event):
        x, y = event.x - lastClickX + self.window.winfo_x(), event.y - lastClickY + self.window.winfo_y()
        self.window.geometry("+%s+%s" % (x , y))

    def OnMotion(self, event):
        x1 = self.window.winfo_pointerx()
        y1 = self.window.winfo_pointery()
        # x1 = event.x 
        # y1 = event.y
        x0 = self.window.winfo_rootx()
        y0 = self.window.winfo_rooty()
        self.window.geometry(f"{x1-x0}x{y1-y0}")

        self.text.config(wraplength=self.window.winfo_width())

    def Update(self):
        try:
            # https://superfastpython.com/multiprocessing-queue-in-python/
            subtitle = self.task_queue.get(block=False)
            if subtitle is None:
                self.window.quit()
            else:
                process = multiprocessing.current_process()
                proc_name = process.name
                print(f"{proc_name} is working...")
                print(f"Show the subtitle: {subtitle}")
                self.text.config(text=subtitle)
        except queue.Empty:
            pass
        except Exception as e:
            print(e)
        self.window.after(100, self.Update)


class SubtitleBarProcess(multiprocessing.Process):
    def __init__(self, task_queue, event_init):
        super().__init__()

        self.task_queue = task_queue
        self.event_init = event_init
    
    def run(self):
        proc_name = self.name
        print(f"Initializing {proc_name}...")

        self.event_init.set()

        print(f"{proc_name} is working...")

        self.bar = SubtitleBar(self.task_queue)

if __name__ == '__main__':
    event_subtitle_bar_process_initialized = multiprocessing.Event()

    subtitle_task_queue = multiprocessing.Queue()

    subtitle_bar_process = SubtitleBarProcess(subtitle_task_queue, event_subtitle_bar_process_initialized)
    subtitle_bar_process.start()

    event_subtitle_bar_process_initialized.wait()

    while True:
        user_input = input("Please enter commands:\n")

        if user_input == 'esc':
            break
        else:
            subtitle_task_queue.put(user_input)
    
    subtitle_task_queue.put(None)
    subtitle_bar_process.join()

# References:
# https://stackoverflow.com/questions/4055267/tkinter-mouse-drag-a-window-without-borders-eg-overridedirect1
# https://stackoverflow.com/questions/22421888/tkinter-windows-without-title-bar-but-resizable
# https://www.pythontutorial.net/tkinter/tkinter-sizegrip/
# https://stackoverflow.com/questions/19080499/transparent-background-in-a-tkinter-window
# https://www.pythontutorial.net/tkinter/tkinter-ttk/
# https://www.geeksforgeeks.org/python-after-method-in-tkinter/
# https://stackoverflow.com/questions/2400262/how-can-i-schedule-updates-f-e-to-update-a-clock-in-tkinter
# https://stackoverflow.com/questions/66529633/destroy-tkinter-window-in-thread
# https://stackoverflow.com/questions/53641648/tkinter-python-3-moving-a-borderless-window
# https://www.geeksforgeeks.org/python-tkinter-frameless-window/
# https://www.geeksforgeeks.org/transparent-window-in-tkinter/
# https://code-maven.com/slides/python/tk-timer-event
# https://pythonguides.com/python-tkinter-events/
# https://www.geeksforgeeks.org/how-to-change-the-tkinter-label-text/
# https://www.tutorialspoint.com/how-to-put-a-tkinter-window-on-top-of-the-others
# https://www.tutorialspoint.com/python/tk_fonts.htm