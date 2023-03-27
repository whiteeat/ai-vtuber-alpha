import time
from tkinter import *
import tkinter.messagebox as messagebox
import pypinyin
import os
import win32api
import win32con



if __name__ == '__main__':
    def main():

        win32api.ShellExecute(0, 'open', 'D:\\Music\\requestSongs\\EndlessRainDerbyVox.mp3', '', '', 1)  # 播放视频
        win32api.ShellExecute(0, 'open', 'D:\\Music\\requestSongs\\EndlessRainDerbyBg.mp3', '', '', 1)  # 播放视频
        time.sleep(1)
    main()