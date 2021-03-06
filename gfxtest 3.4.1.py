﻿#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
  当渲染时间大于16.67，按照垂直同步机制，该帧就已经渲染超时
  那么，如果它正好是16.67的整数倍，比如66.68，则它花费了4个垂直同步脉冲，减去本身需要一个，则超时3个
  如果它不是16.67的整数倍，比如67，那么它花费的垂直同步脉冲应向上取整，即5个，减去本身需要一个，即超时4个，可直接算向下取整

  最后的计算方法思路：
  执行一次命令，总共收集到了m帧（理想情况下m=128），但是这m帧里面有些帧渲染超过了16.67毫秒，算一次jank，一旦jank，
  需要用掉额外的垂直同步脉冲。其他的就算没有超过16.67，也按一个脉冲时间来算（理想情况下，一个脉冲就可以渲染完一帧）

  所以FPS的算法可以变为：
  m / （m + 额外的垂直同步脉冲） * 60
  '''
import Queue
import collections
import datetime
import glob
import hashlib
import os
import random
import signal
import subprocess
import thread
import tkSimpleDialog as dl
import xml.dom.minidom
from Tkinter import *
from optparse import OptionParser, OptionGroup
from subprocess import Popen, PIPE

import requests
import tkinter.filedialog
import tkinter.messagebox
from PIL import Image, ImageTk
from tkinter import ttk
from uiautomator import Device

import MinicapMin
import MyMini
from lib.imcp.mixin import DeviceMixin
from myocr import MYOCRTest

UINode = collections.namedtuple('UINode', [
    'xml',
    'bounds',
    'selected', 'checkable', 'clickable', 'scrollable', 'focusable', 'enabled', 'focused', 'long_clickable',
    'password',
    'class_name',
    'index', 'resource_id',
    'text', 'content_desc',
    'package'])
__boundstuple = collections.namedtuple('Bounds', ['left', 'top', 'right', 'bottom'])
FindPoint = collections.namedtuple('FindPoint', ['pos', 'confidence', 'method', 'matched'])

import threading
import time


class Bounds(__boundstuple):
    def __init__(self, *args, **kwargs):
        self._area = None

    def is_inside(self, x, y):
        v = self
        return x > v.left and x < v.right and y > v.top and y < v.bottom

    @property
    def area(self):
        if not self._area:
            v = self
            self._area = (v.right - v.left) * (v.bottom - v.top)
        return self._area

    @property
    def center(self):
        v = self
        return (v.left + v.right) / 2, (v.top + v.bottom) / 2

    def __mul__(self, mul):
        return Bounds(*(int(v * mul) for v in self))


class MyLogger(type(sys)):
    '''
    This class is used for printing colorful log
    '''
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    # NOTSET = 0
    WINDOWS_STD_OUT_HANDLE = -11
    GREEN_COLOR = 2
    RED_COLOR = 4
    YELLOW_COLOR = 6
    WHITE_COLOR = 7

    def __init__(self, *args, **kwargs):
        self.level = self.__class__.INFO
        self.output = "log_" + time.strftime("%m-%d-%H-%M",
                                             time.localtime()) + ".txt"

    # def __set_color(self, color):
    #     out_handler = ctypes.windll.kernel32.GetStdHandle(self.__class__.WINDOWS_STD_OUT_HANDLE)
    #     ctypes.windll.kernel32.SetConsoleTextAttribute(out_handler, color)

    def __log(self, level, fmt, *args, **kwargs):
        sys.stderr.write(
            '{0} {1} {2}\n'.format(level, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), fmt % args))
        if level >= self.level and self.output is not None:
            with open(self.output, 'a') as f:
                f.write('{0} {1} {2}\n'.format(level, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), fmt % args))

    def format(color, level):
        def wrapped(func):
            def log(self, fmt, *args, **kwargs):
                # self.__set_color(color)
                self.__log(level, fmt, *args, **kwargs)
                # self.__set_color(self.__class__.WHITE_COLOR)

            return log

        return wrapped

    def config(self, *args, **kwargs):
        if 'outfile' in kwargs:
            self.output = kwargs['outfile']

        if 'level' in kwargs:
            self.level = kwargs['level']
        else:
            self.level = int(kwargs.get('level', self.__class__.INFO))

    @format(GREEN_COLOR, 'DEBUG')
    def debug(self, fmt, *args, **kwargs):
        pass

    @format(WHITE_COLOR, 'INFO')
    def info(self, fmt, *args, **kwargs):
        pass

    @format(YELLOW_COLOR, 'WARNING')
    def warning(self, fmt, *args, **kwargs):
        pass

    @format(RED_COLOR, 'ERROR')
    def error(self, fmt, *args, **kwargs):
        pass

    @format(RED_COLOR, 'CRITICAL')
    def critical(self, fmt, *args, **kwargs):
        pass


class GFXTest():
    def __init__(self):
        self.screensave = 3
        self.numberChosen = None

        self.scroll_xy = "v"
        self.scroll_direct = "v"
        self.platfrom_fps = "n"
        self.stop_flag = False

        self.package = ""
        self.apkversion = ""
        self.buildversion = ""
        self.targetSDK = ""
        self.fps_ave = 0
        self.WIDTH = None
        self.HEIGHT = None
        self.mem = ""
        self.cpu = ""
        self.cpu_max = []
        self.md5list = []
        self.cpu_flag = True
        self.q = Queue.Queue(0)
        self.enableFPS = "yes"
        self.d = None
        self.dm = None
        self.textout = None
        self.radionButton_value = None
        self.radionButton_rp_value = None
        self.typeRecord = None
        self.typeReplay = None
        self.typeManu = None
        self.typeSuper = None
        self.typeDirect = None
        self.packageEdit = ""
        self.serial = ""
        # self.serial = self.options.serial_number
        self.fileEdit = "record.text"
        self.startX = 0
        self.startY = 0
        self.radiobutton = []
        self.imglabel = None
        self.radionButton_type_value = None
        self.root = None
        self.canvas = None
        self.status_canvas = None
        self.canvas_performance = None
        self._mouse_motion = ""
        self._mouse_motion_crop = ""
        self._mouse_motion_xy = []
        self.cavas_x_y = {}
        self.crop_box = []
        self.job_plan = True
        self.emmc_start = {}
        self.emmc_end = {}
        self.minicap_ins = None
        self.draw_overflow = 0
        self.result = "True"

    def getAllPkg(self):
        try:
            allpkg = []
            out = self.raw_cmd('shell', "pm list package |grep -E '(ape.)|(myos.)|(com.a)'")
            for k in (out.strip().split("\r")):
                pkg = k[k.find("package:") + 8:]
                allpkg.append(pkg)
            new_ls = sorted(allpkg, reverse=True)
            if len(new_ls) == 0:
                return [""]
            else:
                return new_ls
        except Exception, e:
            self.textout.insert(END, "出错了\n")
            self.textout.update()
            return [""]

    def getAllFile(self):
        try:
            allFile = []
            for filename in glob.glob(os.getcwd() + u'\*.txt'):
                allFile.append(filename)
            if len(allFile) == 0:
                return [""]
            else:
                return allFile
        except Exception, e:
            print "get file error"
            import traceback
            traceback.print_exc()
            return [""]

    def inidevice(self):
        self.package = self.getPackage()

        self.apkversion, self.buildversion, self.targetSDK = self.getAPKVersion()
        # size = self.screenSize()
        # self.WIDTH = int(size[0])
        # self.HEIGHT = int(size[1])
        self.d = Device(self.serial)
        self.dm = DeviceMixin(self.d)

    def gettk(self):
        self.root = Tk()
        self.root['bg'] = "White"
        self.root.geometry('1100x720+100+100')
        self.root.title("GFXTest 3.4.1")
        self.canvas = Canvas(self.root, bg="gray", bd=0, highlightthickness=0, relief='ridge')
        # self.status_canvas = Canvas(self.root,bd=0, highlightthickness=0, relief='ridge')
        self.canvas.bind("<Button-1>", self._mouse_click)
        self.canvas.bind("<B1-Motion>", self._stroke_move)
        self.canvas.bind("<B1-ButtonRelease>", self._stroke_done)

        self.canvas.bind_all("<KeyPress-Up>", self.swiptDown)
        self.canvas.bind_all("<KeyPress-Down>", self.swiptUp)
        self.canvas.bind_all("<KeyPress-Left>", self.swiptLeft)
        self.canvas.bind_all("<KeyPress-Right>", self.swiptRight)
        self.canvas.bind_all("<Key-space>", self.press_back)
        self.canvas.place(x=740, y=0, width=360, height=720)
        totallable = Label(self.root, bg="MediumAquamarine", text='Tinno Performance Test Tool',
                           font=("Century", "16", "bold"))
        totallable.place(x=0, y=0, width=740, height=40)
        settingslable = Label(self.root, bg="MediumAquamarine", text='请手动打开设置中的GPU Rendering!', font=("Century"),
                              fg="Crimson")
        settingslable.place(x=0, y=695, width=740, height=25)

        serialRefresh = Label(self.root, bg="White", text='设备列表')
        serialRefresh.place(x=2, y=340, width=60, height=30)

        serial = self.getAdb2()
        self.radionButton_value = StringVar()
        for i in xrange(len(serial)):
            self.radionButton_value.set(serial[i])
            model = self.getModel(serial[i])
            # if len(serial[i])>15:
            #     model = model[0:4]
            self.radiobutton.append(
                Radiobutton(self.root, bg="White", text=serial[i] + "_" + str(model), variable=self.radionButton_value,
                            value=serial[i],
                            command=lambda: self.on_serial_select(self.root)))
            self.radiobutton[i].place(x=0, y=380 + 30 * i)

        clickxy = Label(self.root, bg="White", text='点击')
        clickxy.place(x=2, y=160, width=30, height=30)
        self.startX = Entry(self.root, bg="white")
        self.startX.place(x=35, y=160, width=90, height=30)
        x = Label(self.root, bg="White", text='x')
        x.place(x=130, y=160, width=10, height=30)
        self.startY = Entry(self.root, bg="white")
        self.startY.place(x=145, y=160, width=90, height=30)
        self.textout = Text(self.root, bg="Black", fg="AntiqueWhite")
        self.textout.bind("<KeyPress-Return>", self.adb_mode)
        self.textout.bind("<KeyPress-Escape>", self.clear_textout)
        # self.textout.place(x=240, y=40, width=500, height=555)
        self.textout.place(x=240, y=40, width=500, height=655)
        if len(serial) == 1:
            self.serial = serial[0]
            size = self.screenSize()
            self.WIDTH = int(size[0])
            self.HEIGHT = int(size[1])
            self.apkversion, self.buildversion, self.targetSDK = self.getAPKVersion()
            self.textout.insert(END, "系统: " + self.buildversion + "\n")
            self.textout.insert(END, "当前设备: " + self.serial + "\n")
        elif len(serial) > 1:
            self.serial = self.radionButton_value.get()
            size = self.screenSize()
            self.WIDTH = int(size[0])
            self.HEIGHT = int(size[1])
            self.apkversion, self.buildversion, self.targetSDK = self.getAPKVersion()
            self.textout.insert(END, "系统: " + self.buildversion + "\n")
            self.textout.insert(END, "当前设备: " + self.serial + "\n")
        else:
            print "No any device!"
            tkinter.messagebox.askokcancel('提示', '没有连接设备，请连接设备后重启！')
            #self.textout.insert("1.0", "No any device found!\n")
            sys.exit(1)

        self.typeRecord = IntVar()
        self.typeReplay = IntVar()
        self.typeManu = IntVar()
        self.typeSuper = IntVar()
        self.typeDirect = IntVar()
        manuButton = Checkbutton(self.root, bg="White", variable=self.typeDirect, text='水平', onvalue=1, offvalue=0)
        manuButton.place(x=3, y=195, width=50, height=30)

        self.radionButton_rp_value = StringVar()
        self.radionButton_rp_value.set("v")
        radiobuttonr = Radiobutton(self.root, bg="White", text="记录", variable=self.radionButton_rp_value,
                                   value="r",
                                   command=self.on_recordreplay_record)
        radiobuttonr.place(x=63, y=195, width=50, height=30)

        radiobuttonp = Radiobutton(self.root, bg="White", text="回放", variable=self.radionButton_rp_value,
                                   value="p",
                                   command=self.on_recordreplay_replay)
        radiobuttonp.place(x=125, y=195, width=50, height=30)

        radiobuttonm = Radiobutton(self.root, bg="White", text="手动", variable=self.radionButton_rp_value,
                                   value="m")
        radiobuttonm.place(x=185, y=195, width=50, height=30)

        # radiobuttonm = Radiobutton(self.root, bg="White", text="控制", variable=self.radionButton_rp_value,
        #                            value="s")
        # radiobuttonm.place(x=2, y=220, width=50, height=30)

        self.radionButton_type_value = StringVar()
        self.radionButton_type_value.set("fps")
        radiobuttone = Radiobutton(self.root, bg="White", text="FPS", variable=self.radionButton_type_value,
                                   value="fps",
                                   command=self.execute_select)
        radiobuttone.place(x=20, y=45, width=50, height=30)
        radiobuttone = Radiobutton(self.root, bg="White", text="启动", variable=self.radionButton_type_value,
                                   value="start",
                                   command=self.execute_select)
        radiobuttone.place(x=93, y=45, width=50, height=30)

        radiobuttone = Radiobutton(self.root, bg="White", text="压力", variable=self.radionButton_type_value,
                                   value="pressure",
                                   command=self.execute_select)
        radiobuttone.place(x=163, y=45, width=50, height=30)

        packageLabel = Label(self.root, bg="White", text='包名')
        packageLabel.place(x=2, y=80, width=30, height=30)
        number = StringVar()
        self.packageEdit = ttk.Combobox(self.root, width=40, textvariable=number)
        self.packageEdit['values'] = self.getAllPkg()  # 设置下拉列表的值
        self.packageEdit.place(x=35, y=80, width=200, height=30)  # 设置其在界面中出现的位置  column代表列   row 代表行
        self.packageEdit.current(0)

        fileLabel = Label(self.root, bg="White", text='文件')
        fileLabel.place(x=2, y=120, width=30, height=30)

        number = StringVar()
        self.fileEdit = ttk.Combobox(self.root, width=40, textvariable=number)
        self.fileEdit['values'] = self.getAllFile()  # 设置下拉列表的值
        self.fileEdit.place(x=35, y=120, width=200, height=30)  # 设置其在界面中出现的位置  column代表列   row 代表行
        self.fileEdit.current(0)

        number = StringVar()
        timeLabel = Label(self.root, bg="White", text='次数/时间')
        timeLabel.place(x=2, y=230, width=70, height=30)
        self.numberChosen = ttk.Combobox(self.root, width=12, textvariable=number)
        self.numberChosen['values'] = (1, 3, 5, 10, 20, 30, 100, 500, 1000)
        self.numberChosen.place(x=75, y=232, width=80, height=30)
        self.numberChosen.current(1)
        self.screensave = int(self.numberChosen.get())

        menubar = Menu(self.root)

        menubar.add_command(label=" 帮助   |", command=self.help)

        # control_menu = Menu(menubar, tearoff=0)

        tools_menu = Menu(menubar, tearoff=0)
        tools_menu.add_command(label="网络流量统计", command=self.net_flow_tool)
        tools_menu.add_separator()
        tools_menu.add_command(label="EMMC开始", command=self.emmc_start_tool)
        tools_menu.add_command(label="EMMC结束统计", command=self.emmc_end_tool)
        tools_menu.add_separator()
        tools_menu.add_command(label="语言切换开始", command=self.chang_language)
        tools_menu.add_separator()
        tools_menu.add_command(label="Monkey开始", command=self.run_monkey)
        tools_menu.add_command(label="Monkey结束", command=self.killmonkey)
        tools_menu.add_separator()
        tools_menu.add_command(label="GO整机测试", command=self.platformRun2)
        menubar.add_cascade(label='专项   |', menu=tools_menu)
        menubar.add_command(label="BACK   |", command=lambda: self.press_back(None))
        menubar.add_command(label="HOME   |", command=self.press_home)
        menubar.add_command(label="POWER   |", command=self.press_power)
        menubar.add_command(label="截图   |", command=self.crop_image_show)
        screen_tool = Menu(menubar, tearoff=0)
        screen_tool.add_command(label="上滑", command=lambda: self.swiptDown(None))
        screen_tool.add_command(label="下滑", command=lambda: self.swiptUp(None))
        screen_tool.add_command(label="左滑", command=lambda: self.swiptLeft(None))
        screen_tool.add_command(label="右滑", command=lambda: self.swiptRight(None))
        screen_tool.add_separator()
        screen_tool.add_command(label="左旋转", command=lambda: self.screen_oration("l"))
        screen_tool.add_command(label="右旋转", command=lambda: self.screen_oration("r"))
        screen_tool.add_command(label="恢复", command=lambda: self.screen_oration("n"))
        menubar.add_cascade(label='滑动和旋转   |', menu=screen_tool)

        device_tool = Menu(menubar, tearoff=0)
        device_tool.add_command(label="刷新设备", command=lambda: self.on_serial_refresh(self.root))
        device_tool.add_separator()
        device_tool.add_command(label="断开显示", command=self.on_minicap_killed)
        device_tool.add_separator()
        device_tool.add_command(label="重连显示", command=self.on_minicap_reconnect)
        menubar.add_cascade(label='设备管理   |', menu=device_tool)
        onekey_menu = Menu(menubar, tearoff=0)
        onekey_menu.add_command(label="ROOT", command=self.enable_root)
        onekey_menu.add_command(label="PUSH文件", command=self.push_res)
        onekey_menu.add_command(label="连接PENTURN", command=self.enable_wifi)
        # onekey_menu.add_separator()
        # onekey_menu.add_command(label="Logcat", command=self.adb_mode)

        onekey_menu.add_command(label="执行命令", command=lambda: self.command_shell(serial))
        menubar.add_cascade(label='工具箱   |', menu=onekey_menu)

        edit_menu = Menu(menubar, tearoff=0)
        edit_menu.add_command(label="清除输入框", command=self.control_clear)
        edit_menu.add_command(label="打开文件", command=self.control_openfile)
        edit_menu.add_command(label="插入记录文件", command=lambda: self.control_edit("playrecord"))
        edit_menu.add_separator()
        edit_menu.add_command(label="点击返回", command=lambda: self.control_edit("pressback"))
        edit_menu.add_command(label="点击HOME", command=lambda: self.control_edit("presshome"))
        edit_menu.add_command(label="最近任务", command=lambda: self.control_edit("pressrecent"))
        edit_menu.add_separator()
        edit_menu.add_command(label="点击文字", command=lambda: self.control_edit("clicktext"))
        edit_menu.add_command(label="点击坐标", command=lambda: self.control_edit("clickscreen"))
        edit_menu.add_command(label="点击图片", command=lambda: self.control_edit("clickimage"))
        edit_menu.add_separator()
        edit_menu.add_command(label="检查文字", command=lambda: self.control_edit("checktext"))
        edit_menu.add_command(label="检查图片", command=lambda: self.control_edit("checkimage"))
        edit_menu.add_separator()
        edit_menu.add_command(label="保存", command=self.control_save)
        menubar.add_cascade(label='脚本编辑模式   |', menu=edit_menu)

        menubar.add_command(label="清除屏幕   |", command=lambda: self.clear_textout(None))
        # menubar.add_command(label="执行命令   |", command=self.adb_mode)


        self.root['menu'] = menubar

        execute_Button = Button(self.root, text='开始', bg="Orange", font=("黑体", "14"), command=self.execute_type)
        execute_Button.place(x=0, y=280, width=120, height=40)
        execute_Button = Button(self.root, text='停止', fg="Orange", bg="Black", font=("黑体", "14"),
                                command=self.execute_stop)
        execute_Button.place(x=120, y=280, width=120, height=40)

        self.installbundle()
        if os.path.isfile(os.getcwd() + '/maintmp.png'):
            img = Image.open(os.getcwd() + '/maintmp.png')  # 打开图片
            w, h = img.size
            img = img.resize((360, 720), Image.ANTIALIAS)
            # image = img.copy()
            # image.thumbnail((324, 600), Image.ANTIALIAS)
            tkimage = ImageTk.PhotoImage(img)
            # self._tkimage = tkimage
            self.canvas.config(width=w, height=h)
            self.canvas.create_image(0, 0, anchor=tkinter.NW, image=tkimage)
            # if len(serial) == 1:
            # self.minicap_ins = MinicapMin.screen_with_controls(serial=self.serial, tk=self.root, cav=self.canvas)
            # self.minicap_ins.screen_simple()
        self.minicap_ins = MyMini.MyMini(serial=self.serial, tk=self.root, cav=self.canvas)
        self.minicap_ins.screen_simple()
        # self.status_canvas.place(x=240, y=550, width=500, height=150)
        # self.status_canvas.create_rectangle(0, 0, 150, 150,fill='blue')
        # self.root.after(100, self.draw_threading)
        self.root.mainloop()

    def press_back(self, event):
        self.raw_cmd_nowait('shell', 'input', 'keyevent 4')
        self.textout.insert(END, "返回上层\n")
        self.textout.update()

    def press_home(self):
        self.raw_cmd_nowait('shell', 'input', 'keyevent 3')
        self.textout.insert(END, "回到Launcher主页面\n")
        self.textout.update()

    def press_power(self):
        self.raw_cmd_nowait('shell', 'input', 'keyevent 26')
        self.textout.insert(END, "按下电源键\n")
        self.textout.update()

    def execute_stop(self):
        if tkinter.messagebox.askokcancel('提示', '是否终止执行？'):
            self.stop_flag = True
        else:
            self.stop_flag = False

    def execute_type(self):
        zhixingfangshi = self.radionButton_type_value.get()

        if zhixingfangshi == "fps":
            self.gettest()
        elif zhixingfangshi == "start":
            self.testLaunch()
        elif zhixingfangshi == "pressure":
            self.pressure_test()
            self.getLog()

    def pressure_test(self):
        try:
            self.inidevice()
            self.screensave = int(self.numberChosen.get())
            getfile = self.fileEdit.get()
            (path, shotname) = os.path.split(getfile)
            if not os.path.isfile(getfile):
                self.textout.insert(1.0, "没有输入或找不到文件:" + getfile + "\n")
                self.textout.update()
                return 0
            #self.d.freeze_rotation(0)
            for i in xrange(1, int(self.screensave) + 1):
                if self.stop_flag:
                    return 0
                else:
                    self.playatxthread(getfile, self.d, self.dm)
                    self.textout.insert(1.0, str(i) + " ><" + str(shotname) + ">:" + str(
                        self.result) + "\n")
                    self.textout.update()
            #self.d.freeze_rotation(0)

        except Exception, e:
            import traceback
            traceback.print_exc()
            pass
        finally:
            self.stop_flag = False

            #
            # if "Found at" in xy:
            #     #self.canvas.itemconfigure('select-bounds', width=2)
            #     x_y = xy.split(":")[1]
            #     if ("," in x_y) and ("(" in x_y):
            #         x_y  = x_y.replace("(","")
            #         x_y = x_y.replace(")", "")
            #         x_y = x_y.split(",")
            #         x_y_x = int(x_y[0])
            #         x_y_y = int(x_y[1])
            #     # self.canvas.create_rectangle(x_y_x-10, x_y_y-10,x_y_x+10,x_y_y+10, outline='red', tags='select-bounds',
            #     #                    width=2)
            #     # self.textout.update()

    def execute_select(self):
        zhixingfangshi = self.radionButton_type_value.get()
        if zhixingfangshi == "fps":
            self.textout.delete("1.0", END)
            self.textout.insert(END, "当前设备：" + self.serial + "\n")
            self.textout.insert(END, "选择了：流畅度【FPS测试】\n")
            self.textout.update()
        elif zhixingfangshi == "start":
            self.textout.delete("1.0", END)
            self.textout.insert(END, "当前设备：" + self.serial + "\n")
            self.textout.insert(END, "选择了：启动时间【截图】\n")
            self.textout.update()
        elif zhixingfangshi == "pressure":
            self.textout.delete("1.0", END)
            self.textout.insert(END, "当前设备：" + self.serial + "\n")
            self.textout.insert(END, "选择了：压力测试【脚本控制】\n")
            self.textout.update()

    def help(self):
        try:
            self.textout.delete("1.0", END)
            self.textout.insert("1.0", "当前设备：" + self.serial + "\n")
        except Exception, e:
            pass
        finally:
            self.textout.insert(END, "Help doc please refer to PPT. \n")
            self.textout.insert(END, "Download:\n http://ttms.tinno.com/tools/test-tools-version/24/\n")
            self.textout.insert(END, "Email：\n lin.shen@tinno.com\n")
            self.textout.update()

    def on_serial_select(self, tk):
        self.serial = self.radionButton_value.get()
        size = self.screenSize()
        self.WIDTH = int(size[0])
        self.HEIGHT = int(size[1])
        self.textout.delete("1.0", END)
        self.textout.insert("1.0", "当前设备：" + self.serial + "\n")
        self.textout.update()
        number = StringVar()
        self.packageEdit = ttk.Combobox(tk, width=40, textvariable=number)
        self.packageEdit['values'] = self.getAllPkg()  # 设置下拉列表的值
        self.packageEdit.place(x=35, y=70, width=178, height=30)  # 设置其在界面中出现的位置  column代表列   row 代表行
        self.packageEdit.current(0)
        self.startX.delete(0, END)
        self.startY.delete(0, END)
        self.installbundle()
        self.on_minicap_reconnect()
        # self.minicap_ins = MinicapMin.screen_with_controls(serial=self.serial, tk=self.root, cav=self.canvas)
        # self.minicap_ins.screen_simple()
        # for i in xrange(len(self.radiobutton)):
        #     self.radiobutton[i].config(state='disabled')

    def on_serial_refresh(self, tk):
        self.radionButton_rp_value.set("v")
        serial = self.getAdb2()
        self.startX.delete(0, END)
        self.startY.delete(0, END)
        if len(serial) == 1:
            self.serial = serial[0]
            size = self.screenSize()
            self.WIDTH = int(size[0])
            self.HEIGHT = int(size[1])
        elif len(serial) > 1:
            self.serial = serial[0]
            size = self.screenSize()
            self.WIDTH = int(size[0])
            self.HEIGHT = int(size[1])
        else:
            print "No any device!"
            self.textout.insert("1.0", "No any device found!\n")
            self.textout.update()
        self.radiobutton = []
        self.radionButton_value = StringVar()
        for i in xrange(len(serial)):
            self.radionButton_value.set(serial[i])
            model = self.getModel(serial[i])
            # if len(serial[i]) > 15:
            #     model = model[0:4]
            self.radiobutton.append(
                Radiobutton(self.root, bg="White", text=serial[i] + "_" + str(model), variable=self.radionButton_value,
                            value=serial[i],
                            command=lambda: self.on_serial_select(self.root)))
            self.radiobutton[i].place(x=0, y=380 + 30 * i)
        # self.installbundle()
        self.textout.delete(1.0, END)
        self.textout.insert(1.0, "当前设备：" + self.radionButton_value.get() + "\n")
        self.textout.update()

    def on_minicap_killed(self):
        if tkinter.messagebox.askokcancel('提示', '是否断开当前设备的屏幕显示？' + self.serial):
            self.minicap_ins.killMinicap()
            self.textout.delete(1.0, END)
            self.textout.insert(1.0, "断掉当前设备的MINICAP：" + self.radionButton_value.get() + "\n")
            self.textout.update()

    def on_minicap_reconnect(self):
        self.minicap_ins.killMinicap()
        self.apkversion, self.buildversion, self.targetSDK = self.getAPKVersion()
        self.textout.delete(1.0, END)
        self.textout.insert(END, "系统: " + self.buildversion + "\n")
        self.textout.insert(END, "当前设备: " + self.serial + "\n")
        self.textout.insert(1.0, "重新连接当前设备的MINICAP：" + self.radionButton_value.get() + "\n")
        self.textout.update()
        self.minicap_ins.open_minicap_stream(port=1313, serial=self.serial)
        self.minicap_ins.flag = True
        self.minicap_ins.screen_simple()

    def on_super_replay(self):
        tkinter.messagebox.showinfo(title="提示框",
                                    message="输入测试脚本文件:\n" + "[功能列表：]\n"
                                            + "sleep\n"
                                            + "presshome\n"
                                            + "pressback\n"
                                            + "pressrecent\n"
                                            + "swipe:100,200,100,300\n"
                                            + "drag:100,200,100,300\n"
                                            + "checktext:text\n"
                                            + "checkimage:image.png\n"
                                            + "clickscreen:200x300\n"
                                            + "clicktext:text\n"
                                            + "clickimage:image.png\n"
                                            + "playrecord:record.txt\n"
                                            + "reboot\n"
                                            + "ocrface\n"
                                            + "ocrtext:text\n"
                                    )

    def on_recordreplay_record(self):
        self.scroll_direct = "v"
        self.scroll_xy = "r"
        self.raw_cmd('push', os.getcwd() + '/lib/bundle/eventrec', '/data/local/tmp/')
        time.sleep(0.1)
        self.raw_cmd('shell', 'chmod', '777', '/data/local/tmp/eventrec')
        if self.fileEdit.get() == "":
            tkinter.messagebox.showinfo(title="提示框", message="录制回放可以输入文件，默认temp.txt \n 请点击[START]开始！")

    def on_recordreplay_replay(self):
        self.scroll_direct = "v"
        self.scroll_xy = "p"
        self.raw_cmd('push', os.getcwd() + '/lib/bundle/eventrec', '/data/local/tmp/')
        time.sleep(0.1)
        self.raw_cmd('shell', 'chmod', '777', '/data/local/tmp/eventrec')
        if self.fileEdit.get() == "":
            tkinter.messagebox.showinfo(title="提示框", message="录制回放可以输入文件，默认temp.txt \n 请点击[START]开始！")

    def getLog(self):
        try:
            out = self.raw_cmd('shell',
                               'logcat -d |grep -A 1 -E \"FATAL EXCEPTION|ANR in|CRASH:|NOT RESPONDING\"')
            outline = out.split("\r\n")
            find_crash = False
            for i in outline:
                if ("UiAutomation" in i) or ("ADB_SERVICES" in i):
                    continue
                if ("FATAL EXCEPTION" in i) or ("CRASH:" in i):
                    find_crash = True
                    continue
                if find_crash:
                    find_crash = False
                    start = i.find("com")
                    end = i.find(',')
                    package = i[start:end].strip()
                    if " " in package:
                        package = package.split()[0]
                    pid = i[i.find("PID:"):].strip()
                    # print "<" + str(self.serial) + "> " + package + "-> [CRASH]: " + i
                    # readini = self.readinit(os.getcwd() + '/' + str(s) + '.ini', "CRASH", package)
                    # if "NONE" == readini:
                    #     self.writeinit(os.getcwd() + '/' + str(s) + '.ini', "CRASH", package, 1)
                    # elif readini.isdigit():
                    #     readini = int(readini) + 1
                    #     self.writeinit(os.getcwd() + '/' + str(s) + '.ini', "CRASH", package, readini)
                    # self.logger.info("<" + pkg + ">" + " < CRASH:" + str(i) + " >")
                    self.textout.insert(END, "CRASH Found:" + str(i) + "\n")
                    self.textout.update()
                if ("ANR in" in i) or ("NOT RESPONDING:" in i):
                    start = i.find("com")
                    package = i[start:].strip()
                    # readini = self.readinit(os.getcwd() + '/' + str(s) + '.ini', "ANR", package)
                    # print "<" + str(self.serial) + "> " + package + "-> [ANR]: " + i
                    if " " in package:
                        package = package.split()[0]
                        # if "NONE" == readini:
                        #     self.writeinit(os.getcwd() + '/' + str(s) + '.ini', "ANR", package, 1)
                        # elif readini.isdigit():
                        #     readini = int(readini) + 1
                        #     self.writeinit(os.getcwd() + '/' + str(s) + '.ini', "ANR", package, readini)
                        #     # self.writeinit()
                    # self.logger.info("<" + pkg + ">" + " < ANR:" + str(i) + " >")
                    self.textout.insert(END, "ANR Found:" + str(i) + "\n")
        except Exception, e:
            self.textout.insert(END, "getLog出错了\n")
            self.textout.update()
        finally:
            self.textout.insert(END, "getLog结束.\n")
            self.textout.update()
            self.raw_cmd('shell', 'logcat', '-c')

    def installbundle(self):
        try:
            self.inidevice()
            out1 = subprocess.check_output(
                "adb -s " + self.serial + " wait-for-device shell ls /data/local/tmp/bundle.jar; exit 0",
                stderr=subprocess.STDOUT, shell=True)
            if "No such" in out1:
                self.raw_cmd('push', os.getcwd() + '/lib/bundle/bundle.jar', '/data/local/tmp/')
                self.raw_cmd('shell', 'ls /data/local/tmp/bundle.jar')
            out = subprocess.check_output(
                "adb -s " + self.serial + " wait-for-device shell ls /data/local/tmp/uiautomator-stub.jar; exit 0",
                stderr=subprocess.STDOUT, shell=True)
            if "No such" in out:
                self.raw_cmd('push', os.getcwd() + '/lib/bundle/uiautomator-stub.jar',
                             '/data/local/tmp/')
            out = subprocess.check_output(
                "adb -s " + self.serial + " wait-for-device shell ls /data/local/tmp/busybox; exit 0",
                stderr=subprocess.STDOUT, shell=True)
            if "No such" in out:
                self.raw_cmd('push', os.getcwd() + '/lib/bundle/busybox', '/data/local/tmp/')
                self.raw_cmd('shell', 'chmod', '777', '/data/local/tmp/busybox')
            print "install test app,please wait..."
            outinstall = self.raw_cmd('shell', 'pm', 'list', 'package', ' com.github.uiautomator')
            if "com.github.uiautomator" not in outinstall:
                self.raw_cmd('install', '-r', os.getcwd() + '/lib/bundle/app.apk')
            outinstallest = self.raw_cmd('shell', 'pm', 'list', 'package',
                                         'com.github.uiautomator.test')

            if "com.github.uiautomator.test" not in outinstallest:
                self.raw_cmd('install', '-r', os.getcwd() + '/lib/bundle/app-test.apk')
            cpu = self.raw_cmd('shell', 'getprop', 'ro.product.cpu.abi')
            cpu = cpu.strip()
            sdk = self.raw_cmd('shell', 'getprop', 'ro.build.version.sdk')
            sdk = sdk.strip()
            self.raw_cmd('push', os.getcwd() + '/lib/' + sdk + '/' + cpu + '/minicap.so',
                         '/data/local/tmp/')
            self.raw_cmd('push', os.getcwd() + '/lib/' + sdk + '/' + cpu + '/minicap',
                         '/data/local/tmp/')
            self.raw_cmd('shell', 'chmod', '777', '/data/local/tmp/minicap')
            return True
        except Exception, e:
            return False

    def screenSize(self):
        try:
            out = self.raw_cmd('shell', 'wm', 'size')
            out = out.split()[-1].split("x")
            return out
        except Exception, e:
            return False

    def getPackage(self):
        out = self.shell_cmd('getprop ro.build.version.sdk')
        sdk = int(out.strip())
        if sdk < 26:
            getp = self.shell_cmd('dumpsys activity |grep mFocusedActivity')
        else:
            getp = self.shell_cmd('dumpsys activity |grep mResumedActivity')
        # out = self.raw_cmd( 'shell', 'ps', '|grep', 'minicap')
        start = getp.find("com")
        end = getp.find('/')
        package = getp[start:end].strip()
        # apkversion = self.raw_cmd( 'shell', 'dumpsys', "package", package, "|", "grep",'versionName', '|head -n 1')
        return package

    def getModel(self, serial):
        cmds = ['adb'] + ['-s'] + [serial] + ['shell', 'getprop', 'ro.product.model']
        p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        c = p.communicate()[0].strip().replace(" ", "_")
        return c

    def getAPKVersion(self):
        apkversion = ""
        targetSDKapkversion = ""
        buildversion = \
            self.raw_cmd('shell', 'getprop', 'ro.custom.build.version').strip()
        if self.package != "":
            apkversion = \
                self.raw_cmd('shell', 'dumpsys', "package", self.package, "|", "grep", 'versionName')
            # targetSDKapkversion = \
            #     self.raw_cmd('shell', 'dumpsys', "package", self.package, "|", "grep", 'targetSdk', '| cut -d \'=\' -f 4')
            targetSDKapkversion = \
                self.raw_cmd('shell', 'dumpsys', "package", self.package, "|", "grep", 'targetSdk')
            try:
                targetSDKapkversion = targetSDKapkversion[targetSDKapkversion.find("targetSdk"):].split("=")[1]
            except Exception, e:
                pass
            if "versionName=" in apkversion:
                apkversion = apkversion.replace("versionName=", "").strip().split()[0]
            if "_" in apkversion:
                apkversion = apkversion.split("_")[0]
        return apkversion, buildversion, targetSDKapkversion

    def getActivity(self):
        out = self.raw_cmd('shell', 'getprop', 'ro.build.version.sdk')
        sdk = int(out.strip())
        if sdk < 26:
            getp = self.raw_cmd('shell', 'dumpsys', 'activity', '|grep', 'mFocusedActivity')
        else:
            getp = self.raw_cmd('shell', 'dumpsys', 'activity', '|grep', 'mResumedActivity')
        # out = self.raw_cmd( 'shell', 'ps', '|grep', 'minicap')
        start = getp.find("com")
        end = getp.find('/')
        package = getp[start:end].strip()  # "com.android.settings"
        endactivty = getp[start:].strip()  # "com.android.setings/.abcdef xyszn"
        endactivty1 = endactivty.find(" ")  #
        aend = endactivty[:endactivty1].strip("\r\n")  # "com.android.setings/.abcdef"

        if "/." in aend:
            activity = aend.replace("/.", "/" + package + ".")
        return activity

    def setup_arg_parser(self):
        usage = "usage: %prog -c TEST_CAMPAIGN [OPTIONS]"
        parser = OptionParser(usage=usage)
        mandatory_group = OptionGroup(parser, "MANDATORIES")

        mandatory_group.add_option("-c",
                                   metavar=u"fps或者start启动时间",
                                   default="fps",
                                   dest="campaign_name")
        parser.add_option_group(mandatory_group)
        optional_group = OptionGroup(parser, "OPTIONS")
        optional_group.add_option("-s",
                                  metavar=u"123456 |设备号,只有1个设备时无需设置|",
                                  default="",
                                  dest="serial_number")

        optional_group.add_option("-p",
                                  metavar=u"com.android.settings |测试包名,默认当前窗口|",
                                  default="",
                                  dest="test_package")

        optional_group.add_option("-t",
                                  metavar=u"5 |截图时间默认3秒|",
                                  default="3",
                                  dest="screen_save")

        optional_group.add_option("-x",
                                  metavar=u"200x300 |点击点xy坐标|",
                                  default="",
                                  dest="screen_xy")

        optional_group.add_option("-a",
                                  metavar=u"com.android.settings/com.android.settings.Settings  |包名全称|",
                                  default="",
                                  dest="pkg_activity")

        optional_group.add_option("-d",
                                  metavar=u"v |滑动方向,h 水平 v 垂直 m 手动 默认v r 录制 p 回放|",
                                  default="v",
                                  dest="scrool_xy")

        optional_group.add_option("-u",
                                  metavar=u"图形界面",
                                  default="n",
                                  dest="gfxtest_gui")

        optional_group.add_option("-r",
                                  metavar=u"y |流畅度整机测试,默认n|",
                                  default="n",
                                  dest="platfrom_fps")

        optional_group.add_option("-g",
                                  metavar=u"g |不测FPS，用于提高其他测试的性能|",
                                  default="y",
                                  dest="enable_fps")

        parser.add_option_group(optional_group)
        return parser

    def raw_cmd(self, *args):
        try:
            cmds = ['adb'] + ['-s'] + [self.serial] + list(args)
            p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            c = p.communicate()[0]
            return c
        except Exception, e:
            pass

    def raw_cmd_nowait(self, *args):
        try:

            cmds = ['adb'] + ['-s'] + [self.serial] + list(args)
            subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception, e:
            pass

    def getAdb(self):
        try:
            serial = []
            p = Popen("adb devices", shell=True, stdout=PIPE, stderr=PIPE)
            serial = p.stdout.readlines()
            if len(serial) == 3:
                serial = serial[1:-1]
                for i in range(len(serial)):
                    serial[i] = serial[i].replace("\t", "")
                    serial[i] = serial[i].replace("\n", "")
                    serial[i] = serial[i].replace("\r", "")
                    serial[i] = serial[i].replace("\r", "")
                    serial[i] = serial[i].replace("device", "")
                return serial
            elif len(serial) == 2:
                print "Device not found!"
                sys.exit(1)
            elif len(serial) >= 4:
                if self.options.serial_number == "":
                    print u"发现多个设备，请使用 -s xxx 参数指定xxx设备序列号！"
                    sys.exit(1)
                else:
                    self.serial = self.options.serial_number
                return self.serial
        except Exception, e:
            self.textout.insert(END, "设备没找到\n")
            self.textout.update()
            sys.exit(1)

    def getAdb2(self):
        try:
            serial = []
            p = Popen("adb devices", shell=True, stdout=PIPE, stderr=PIPE)
            out = p.stdout.readlines()
            for i in range(len(out)):
                if "List" in out[i]:
                    continue
                if len(out[i]) > 5:
                    serial.append(out[i].split()[0])
            return serial
        except Exception, e:
            self.textout.insert(END, "设备没找到\n")
            self.textout.update()
            sys.exit(1)

    def run_monkey(self):
        serial = [self.serial]
        if tkinter.messagebox.askokcancel('提示', '运行所有设备点<是>,<否>仅仅执行选择的设备'):
            serial = self.getAdb2()
        else:
            pass
        for i in xrange(0, len(serial)):
            self.serial = serial[i]
            self.textout.insert(END, self.serial + " run monkey at: " + str(
                datetime.datetime.now().strftime("%m/%d-%H:%M:%S")) + " \n")
            self.textout.update()
            # self.raw_cmd('push', os.getcwd() + '/lib/bundle/lan.sh',
            #              '/data/local/tmp/')
            # self.raw_cmd('shell', 'chmod', '777', '/data/local/tmp/lan.sh')
            # self.raw_cmd('push', os.getcwd() + '/lib/bundle/language_config.ini',
            #              '/sdcard/')
            # self.raw_cmd('push', os.getcwd() + '/lib/bundle/travel_config.ini',
            #              '/sdcard')
            # self.raw_cmd('mkdir', '-p', '/sdcard/test')
            # outinstallest = self.raw_cmd('shell', 'pm', 'list', 'package',
            #                              'com.tinno.test.appstraveler')
            # if "com.tinno.test.appstraveler" not in outinstallest:
            #     self.raw_cmd('install', '-t', '-r', os.getcwd() + '/lib/bundle/lan.apk')
            # outinstallest = self.raw_cmd('shell', 'pm', 'list', 'package',
            #                              'com.tinno.test.appstraveler.test')
            # if "com.tinno.test.appstraveler.test" not in outinstallest:
            #     self.raw_cmd('install', '-t', '-r', os.getcwd() + '/lib/bundle/lan-test.apk')
            # self.raw_cmd('shell', 'pm', 'grant', 'com.tinno.test.appstraveler',
            #              'android.permission.CHANGE_CONFIGURATION')
            # self.grantPermission("com.tinno.test.appstraveler")
            # self.grantPermission("com.tinno.test.appstraveler.test")
            # subprocess.call("adb -s " + self.serial + " shell am instrument -w -r -e debug false -e listener de.schroepf.androidxmlrunlistener.XmlRunListener -e class com.tinno.autotravel.AppsTraveler#testLan com.tinno.test.appstraveler.test/android.support.test.runner.AndroidJUnitRunner")
            # self.screensave = int(self.numberChosen.get())
            # self.raw_cmd('shell', 'sh',  '/data/local/tmp/lan.sh &')
            # lan_run = threading.Thread(target=self.chang_language).start()
            monkey_run = threading.Thread(target=self.monkeythread).start()
            time.sleep(2)
            print "monkey:", self.serial
            # ct = 0
            # timeNow = time.time()
            # while ct <= int(self.screensave):
            #     time.sleep(20)
            #     ct = time.time() - timeNow
            #
            # self.killmonkey()
            # self.getLog()

    def chang_language(self):
        if tkinter.messagebox.askokcancel('提示', '目录中lib/bundle/language_config.ini为语言配置文件！'):
            self.killlc()
            self.textout.insert(END, "Run LC threading：" + str(
                datetime.datetime.now().strftime("%m/%d-%H:%M:%S")) + " \n")
            self.textout.update()
            self.raw_cmd('push', os.getcwd() + '/lib/bundle/lan.sh',
                         '/data/local/tmp/')
            self.raw_cmd('shell', 'chmod', '777', '/data/local/tmp/lan.sh')
            self.raw_cmd('push', os.getcwd() + '/lib/bundle/language_config.ini',
                         '/sdcard/')
            self.raw_cmd('push', os.getcwd() + '/lib/bundle/travel_config.ini',
                         '/sdcard')
            self.raw_cmd('mkdir', '-p', '/sdcard/test')
            outinstallest = self.raw_cmd('shell', 'pm', 'list', 'package',
                                         'com.tinno.test.appstraveler')
            if "com.tinno.test.appstraveler" not in outinstallest:
                self.raw_cmd('install', '-t', '-r', os.getcwd() + '/lib/bundle/lan.apk')
            outinstallest = self.raw_cmd('shell', 'pm', 'list', 'package',
                                         'com.tinno.test.appstraveler.test')
            if "com.tinno.test.appstraveler.test" not in outinstallest:
                self.raw_cmd('install', '-t', '-r', os.getcwd() + '/lib/bundle/lan-test.apk')
            self.raw_cmd('shell', 'pm', 'grant', 'com.tinno.test.appstraveler',
                         'android.permission.CHANGE_CONFIGURATION')
            self.grantPermission("com.tinno.test.appstraveler")
            self.grantPermission("com.tinno.test.appstraveler.test")
            # subprocess.call("adb -s " + self.serial + " shell am instrument -w -r -e debug false -e listener de.schroepf.androidxmlrunlistener.XmlRunListener -e class com.tinno.autotravel.AppsTraveler#testLan com.tinno.test.appstraveler.test/android.support.test.runner.AndroidJUnitRunner")
            # self.screensave = int(self.numberChosen.get())
            # self.raw_cmd('shell', 'sh',  '/data/local/tmp/lan.sh &')
            # lan_run = threading.Thread(target=self.chang_language).start()
            t = threading.Thread(target=self.lcthread).start()

    def monkeythread(self):
        try:
            package_Edit = self.packageEdit.get()
            print self.serial
            if package_Edit == "":
                self.raw_cmd('shell', 'monkey',
                             '--throttle', '1000', '-s', '10',
                             '--ignore-security-exceptions',
                             '--ignore-crashes', '--ignore-timeouts', '--ignore-native-crashes', '-v', '20000000',
                             '>/mnt/sdcard/monkeylog.log 2>&1')
            else:
                self.package = package_Edit
                self.raw_cmd('shell', 'monkey', '-p', str(self.package),
                             '--throttle', '1000', '-s', '10',
                             '--ignore-security-exceptions',
                             '--ignore-crashes', '--ignore-timeouts', '--ignore-native-crashes', '-v', '20000000',
                             '>/mnt/sdcard/monkeylog.log 2>&1')
        except Exception, e:
            return False

    def lcthread(self):
        try:
            self.raw_cmd('shell', 'am', 'instrument', '-w', '-r', '-e', 'debug false', '-e', 'class',
                         'com.tinno.autotravel.AppsTraveler#testLan com.tinno.test.appstraveler.test/android.support.test.runner.AndroidJUnitRunner 2>&1')
        except Exception, e:
            return False

    def removeFileInFirstDir(self, targetDir):
        for file in os.listdir(targetDir):
            targetFile = os.path.join(targetDir, file)
            if os.path.isfile(targetFile):
                os.remove(targetFile)

    def screen_oration(self, ori):
        try:
            self.d.orientation = ori
        except Exception, e:
            return False

    def swiptDown(self, event):
        self.shell_cmd(
            'input swipe ' + str(self.WIDTH / 2) + " " + str(self.HEIGHT * 0.7) + " " + str(self.WIDTH / 2) + " " + str(
                self.HEIGHT * 0.2))

    def swiptUp(self, event):
        self.shell_cmd(
            'input swipe ' + str(self.WIDTH / 2) + " " + str(self.HEIGHT * 0.3) + " " + str(self.WIDTH / 2) + " " + str(
                self.HEIGHT * 0.7))

    def swiptRight(self, event):
        self.shell_cmd(
            'input swipe ' + str(self.WIDTH - 50) + " " + str(self.HEIGHT / 2) + " 50 " + str(self.HEIGHT / 2))

    def swiptLeft(self, event):
        self.shell_cmd(
            'input swipe  50 ' + str(self.HEIGHT / 2) + " " + str(self.WIDTH - 50) + " " + str(self.HEIGHT / 2))

    def screenShot(self, path):
        try:
            # out = subprocess.Popen(
            #     ['adb', '-s', self.serial, 'shell', 'LD_LIBRARY_PATH=/data/local/tmp', '/data/local/tmp/minicap',
            #      '-i', ],
            #     stdout=subprocess.PIPE).communicate()[0]
            # m = re.search('"width": (\d+).*"height": (\d+).*"rotation": (\d+)', out, re.S)
            # w, h, r = map(int, m.groups())
            # w, h = min(w, h), max(w, h)
            params = '{x}x{y}@{x1}x{y1}/{r}'.format(x=self.WIDTH, y=self.HEIGHT, x1=self.WIDTH, y1=self.HEIGHT, r=0)

            # params = '{x}x{y}@{x1}x{y1}/{r}'.format(x=w, y=h, x1=w, y1=h, r=0)
            # cmd = 'shell LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/minicap -P %s' % params + ' -S -s > /sdcard/maintmp.png'
            # pullcmd = 'pull /sdcard/maintmp.png ./maintmp.png'

            self.raw_cmd('shell', 'LD_LIBRARY_PATH=/data/local/tmp', '/data/local/tmp/minicap', '-P %s' % params,
                         '-S -s > /sdcard/maintmp.png')
            self.raw_cmd('pull', '/sdcard/maintmp.png', str(path))

        except Exception, e:
            pass

    def swipe2(self, dir):
        try:
            if "systemui" in self.package:
                self.raw_cmd('shell', 'input', 'swipe', str(self.WIDTH / 2), "1",
                             str(self.WIDTH / 2), str(self.HEIGHT * 0.7))
                self.raw_cmd('shell', 'input', 'swipe', str(self.WIDTH - 50), str(self.HEIGHT / 2),
                             "50",
                             str(self.HEIGHT / 2))
                self.raw_cmd('shell', 'input', 'keyevent 26')
                time.sleep(0.1)
                self.raw_cmd('shell', 'input', 'keyevent 26')
                time.sleep(0.1)
                self.raw_cmd('shell', 'input', 'keyevent 4')
            elif self.scroll_xy == "m":
                pass
            else:
                if dir == "vh" or dir == "hv":
                    self.swiptDown(None)
                    self.swiptUp(None)
                    self.swiptRight(None)
                    self.swiptLeft(None)
                elif dir == "v":
                    self.swiptDown(None)
                    self.swiptUp(None)
                elif dir == "h":
                    self.swiptRight(None)
                    self.swiptLeft(None)
        finally:
            pass
            # self.screenShot(os.getcwd() + "/pic/" + self.package + str(datetime.datetime.now().second) + ".png")

    def gfxclean(self):
        results = self.raw_cmd('shell', 'dumpsys', 'gfxinfo', self.package, 'reset')

    def swipesystemui(self):
        self.raw_cmd('shell', 'input', 'swipe', str(self.WIDTH / 2), "1",
                     str(self.WIDTH / 2), str(self.HEIGHT * 0.7))
        self.raw_cmd('shell', 'input', 'swipe', str(self.WIDTH - 50), str(self.HEIGHT / 2),
                     "50",
                     str(self.HEIGHT / 2))
        self.raw_cmd('shell', 'input', 'swipe', str(self.WIDTH - 50), str(self.HEIGHT / 2),
                     "50",
                     str(self.HEIGHT / 2))
        self.raw_cmd('shell', 'input', 'keyevent', '4')

    def gfxtest(self):
        if "systemui" in self.package:
            return self.gfxtest2()
        else:
            return self.gtest(self.package)

    def gtest(self, pkg):
        try:
            my_re = re.compile(r'[A-Za-z]', re.S)
            fps = 0
            frame_count = 0
            jank_count = 0
            vsync_overtime = 0
            draw_over = 0
            render_time = []
            draw_time = []
            fps = 0
            results = self.raw_cmd('shell', 'dumpsys', 'gfxinfo', pkg)
            pt = False
            frames = []
            for i in results.split("\r"):
                if "Draw" in i and "Process" in i and "Execute" in i:
                    pt = True
                    j = 0
                    continue
                if pt and len(i) > 1:
                    resw = re.findall(my_re, i)
                    # if (j <= 120) & (i != "") & (len(i) > 1):
                    if len(resw) == 0:
                        frames.append(i.split())
                    else:
                        pt = False
            for frame in frames:
                if len(frame) == 4:
                    try:
                        if float(frame[0]) > 16.67:  # >16.67s
                            draw_time.append('%.2f' % (float(frame[0])))
                        rt = '%.2f' % (float(frame[0]) + float(frame[1]) + float(frame[2]) + float(frame[3]))
                        render_time.append(rt)
                    except Exception, e:
                        render_time = [0]
            frame_count = len(frames)
            if len(render_time) > 1:
                for j in render_time:
                    if float(j) > 16.67:
                        jank_count += 1
                        if float(j) % 16.67 == 0:
                            vsync_overtime += int(float(j) / 16.67) - 1
                        else:
                            vsync_overtime += int(float(j) / 16.67)
                if frame_count > 0:
                    fps = int(frame_count * 60 / (frame_count + vsync_overtime))
                    draw_over = '%.2f' % (len(draw_time) / float(frame_count))
                    # print "framecount=",frame_count,"fps_ave=",self.fps_ave,"fps=",fps,"vnc=",vsync_overtime
                    # fps = self.fps_ave + fps
                    # self.fps_ave = self.fps_ave / frame_count
                    # print "Frames=", frame_count, " Jank=", jank_count, " FPS=", self.fps_ave, " Draw=",float(draw_over)*100
        finally:
            return int(frame_count), int(jank_count), int(fps), int(float(draw_over) * 100)

    def gfxtest2(self):
        try:
            fps = 0
            jank_count = 0
            results = self.raw_cmd('shell', 'dumpsys', 'gfxinfo', self.package)
            frames = 0
            for i in results.split("\r"):
                if "Total frames rendered:" in i:
                    # frames = i.replace("ms", "").split()[1:-1]
                    frames = i.split()[3]
                elif "Janky frames:" in i:
                    # frames = i.replace("ms", "").split()[1:-1]
                    jank_count = i.split()[2]
                elif "Number Missed Vsync:" in i:
                    # frames = i.replace("ms", "").split()[1:-1]
                    mv = i.split()[3]
            fps = int((int(frames) * 60) / (int(frames) + int(mv)))
        finally:
            return int(frames), int(jank_count), int(fps), 0

    def testFPS2(self):
        # self.killsh()
        activity = self.getActivity()
        persion = self.raw_cmd('shell', 'getprop', 'ro.internal.build.version')
        if "8.0" in persion:
            thread.start_new_thread(
                self.raw_cmd('shell', 'sh /data/local/tmp/fps.sh -t 60 -w ' + activity + "#0",
                             stdout=subprocess.PIPE), ("Thread-1", 2,))
        else:
            thread.start_new_thread(
                self.raw_cmd('shell', 'sh /data/local/tmp/fps.sh -t 60 -w ' + activity,
                             stdout=subprocess.PIPE), ("Thread-1", 2,))

    def testFPS(self):
        try:
            self.inidevice()
            zhixingfangshi = self.radionButton_rp_value.get()
            frame_count = 0
            jank_count = 0
            fps = 0
            total_count = 0
            draw_over = 0
            # self.raw_cmd( 'shell', 'setprop', 'debug.hwui.profile', 'visual_bars',
            #              stdout=subprocess.PIPE)  # visual_bars
            # self.raw_cmd( 'shell',
            #              'monkey', '-p com.android.settings -c', 'android.intent.category.LAUNCHER', '1',
            #              stdout=subprocess.PIPE )
            # time.sleep(0.2)
            # self.raw_cmd( 'shell', 'input', 'keyevent', '4',
            #              stdout=subprocess.PIPE)
            self.scroll_xy = "v"
            self.scroll_direct = "v"
            if self.typeDirect.get() == 1:
                self.scroll_direct = "h"
            if zhixingfangshi == "m":
                self.scroll_xy = "m"
            if zhixingfangshi == "s":
                self.scroll_xy = "pa"
            if zhixingfangshi == "p":
                self.scroll_xy = "p"
            x = self.startX.get()
            y = self.startY.get()
            xy = str(x + "x" + y)
            if x != "" and y != "":
                self.raw_cmd('shell', ' input', 'tap', str(x),
                             str(y))
                # self.d.click(int(self.xy.split("x")[0]), int(self.xy.split("x")[1]))
                time.sleep(2)

            package_Edit = self.packageEdit.get()
            if package_Edit == "":
                self.package = self.getPackage()
            else:
                self.package = package_Edit
            # self.apkversion = self.getAPKVersion()

            self.textout.delete(1.0, END)
            if (self.scroll_xy == "v") and (self.scroll_direct == "h"):
                self.textout.insert(END, "FPS水平滑动" + "...\n")
            elif (self.scroll_xy == "v") and (self.scroll_direct == "v"):
                self.textout.insert(END, "FPS垂直滑动" + "...\n")
            elif self.scroll_xy == "m":
                self.textout.insert(END, "FPS手动执行" + "...\n")
            elif self.scroll_xy == "s":
                self.textout.insert(END, "自定义脚本控制" + "...\n")
            elif self.scroll_xy == "r":
                self.textout.insert(END, "录制方式" + "...\n")
            elif self.scroll_xy == "p":
                self.textout.insert(END, "FPS回放" + "...\n")
            self.textout.insert(END, "系统: " + self.buildversion + "\n")
            self.textout.insert(END, "包名: " + self.package + " version=" + self.apkversion + " sdk=" + str(
                self.targetSDK) + "\n")
            self.textout.insert(END, "-" * 53 + "\n")
            self.textout.update()

            if self.scroll_xy == "m" or self.scroll_xy == "p":
                if self.scroll_xy == "p":
                    ref = self.fileEdit.get()
                    if ref == "":
                        ref = "temp.txt"
                    for i in xrange(1, int(self.screensave) + 1):
                        if self.stop_flag:
                            return 0
                        else:
                            self.raw_cmd('shell', 'dumpsys', 'gfxinfo', self.package, 'reset')
                            self.textout.insert(END, "播放次数:" + str(i) + ", 文件:" + str(ref) + "\n")
                            self.textout.update()
                            self.replay(ref)
                            result = self.gfxtest()
                            if (result[0] > 10) & (result[2] > 0):
                                total_count += 1
                                frame_count += result[0]
                                jank_count += result[1]
                                fps = int(fps + result[2])
                                draw_over = (draw_over + result[3])
                                self.textout.insert(END,
                                                    "<" + str(i) + "> FPS=" + str(result[2]) + ", Draw=" + str(
                                                        result[3]) + "%,Total=" + str(
                                                        result[0]) + ",Janks=" + str(result[1]) + "\n")
                            else:
                                self.textout.insert(END, "滑动太少，没有足够的数据！\n")
                        self.textout.update()
                    # self.getLog(self.package)
                    self.screenShot(os.getcwd() + "/pic/" + self.package + str(
                        datetime.datetime.now().strftime("%m_%d_%H_%M_%S")) + ".png")


                elif self.scroll_xy == "m":
                    tkinter.messagebox.showinfo(title="提示框", message="现在请进入待测界面，[确认]后即进行手动滑动")
                    self.raw_cmd('shell', 'dumpsys', 'gfxinfo', self.package, 'reset')
                    time.sleep(int(self.screensave))
                    total_count = 1
                    if package_Edit == "":
                        self.package = self.getPackage()
                    else:
                        self.package = package_Edit
                    result = self.gfxtest()

                    if (result[0] > 20) & (result[2] >= 0):
                        frame_count += result[0]
                        jank_count += result[1]
                        fps = int(fps + result[2])
                        draw_over = (draw_over + result[3])
                        self.textout.insert(END, "<" + str(total_count) + "> FPS=" + str(result[2]) + " Draw=" + str(
                            result[3]) + "%,Total=" + str(
                            result[0]) + ",Janks=" + str(result[1]) + "\n")
                    else:
                        self.textout.insert(END, "滑动太少，没有足够的数据！\n")
                    # self.imagetk()
                    self.textout.update()
                    self.screenShot(os.getcwd() + "/pic/" + self.package + str(
                        datetime.datetime.now().strftime("%m_%d_%H_%M_%S")) + ".png")
            else:
                for m in xrange(0, int(self.screensave)):
                    if self.stop_flag:
                        return 0
                    else:
                        self.raw_cmd('shell', 'dumpsys', 'gfxinfo', self.package, 'reset')
                        self.swipe2(self.scroll_direct)
                        # self.root.after(20,self.swipe2(self.scroll_direct))
                        result = self.gfxtest()
                        # if (result[0] < 30):
                        #     self.swipe2(self.scroll_direct)
                        #     self.swipe2(self.scroll_direct)
                        #     result = self.gfxtest()
                        if (result[0] > 30) and (result[2] >= 0):
                            total_count += 1
                            frame_count += result[0]
                            jank_count += result[1]
                            fps += result[2]
                            draw_over += result[3]

                            self.textout.insert(END,
                                                "<" + str(total_count) + "> FPS=" + str(result[2]) + " Draw=" + str(
                                                    result[3]) + "%,Total=" + str(
                                                    result[0]) + ",Janks=" + str(result[1]) + "\n")

                        else:
                            self.textout.insert(END, "滑动太少，没有足够的数据，或者GPU测试模式未开！\n")
                        # self.imagetk()
                        self.textout.update()
                        self.screenShot(os.getcwd() + "/pic/" + self.package + str(
                            datetime.datetime.now().strftime("%m_%d_%H_%M_%S")) + ".png")

            if (total_count > 0) & (frame_count > 30):
                fps = fps / total_count
                draw_over = int((draw_over / total_count) / 0.75)

                self.textout.insert(END, "-" * 53 + "\n")
                self.textout.insert(END, str(total_count) + u"次平均FPS: " + str(fps) + u";应用丢帧: " + str(
                    draw_over) + "%," + u"\n总帧数:" + str(
                    frame_count) + u",丢帧数:" + str(jank_count) + u",丢帧率:" + str(
                    int((float(jank_count) / frame_count * 100))) + "% \n")
                self.textout.update()
            else:
                print "No enough Framers!"
                self.textout.insert(END, "滑动太少，没有足够的数据！\n")
                self.textout.update()
        except Exception, e:
            import traceback
            traceback.print_exc()
            self.textout.insert(END, "出错了\n")
            self.textout.update()
        finally:
            self.stop_flag = False
            self.textout.insert(END, "-" * 53 + "\n")
            self.textout.insert(END, "测试完成\n")
            self.textout.update()
            return fps, draw_over

    def killmonkey(self):
        try:
            serial = [self.serial]
            if tkinter.messagebox.askokcancel('提示', '停止所有设备点<是>,<否>仅仅停止选择的设备'):
                serial = self.getAdb2()
            else:
                pass
            for i in xrange(0, len(serial)):
                self.serial = serial[i]
                out = self.raw_cmd('shell', '/data/local/tmp/busybox ps | grep commands.monkey | grep -v "grep"')
                for i in out.split("\n"):
                    if " " in i:
                        ps = Popen("adb  -s " + self.serial + " shell kill " + i.split()[0], shell=True, stdout=PIPE,
                                   stderr=PIPE)
                        ps.communicate()

                out = self.raw_cmd('shell', '/data/local/tmp/busybox ps | grep AndroidJUnitRunner | grep -v "grep"')
                for i in out.split("\n"):
                    if " " in i:
                        ps = Popen("adb  -s " + self.serial + " shell kill " + i.split()[0], shell=True, stdout=PIPE,
                                   stderr=PIPE)
                        ps.communicate()
                self.textout.insert(END, str(self.serial) + ": monkey killed! \n")
                self.textout.update()
                self.raw_cmd('pull', '/mnt/sdcard/monkeylog.log', './' + self.serial + '_monkeylog.log')
                time.sleep(1)
        except Exception, e:
            # self.textout.insert(END, "出错了\n")
            # self.textout.update()
            import traceback
            traceback.print_exc()

    def killlc(self):
        try:
            serial = [self.serial]
            if tkinter.messagebox.askokcancel('提示', '停止所有设备点<是>,<否>仅仅停止选择的设备'):
                serial = self.getAdb2()
            else:
                pass
            for i in xrange(0, len(serial)):
                self.serial = serial[i]
                out = self.raw_cmd('shell', '/data/local/tmp/busybox ps | grep AndroidJUnitRunner | grep -v "grep"')
                for i in out.split("\n"):
                    if " " in i:
                        ps = Popen("adb  -s " + self.serial + " shell kill " + i.split()[0], shell=True, stdout=PIPE,
                                   stderr=PIPE)
                        ps.communicate()
                self.textout.insert(END, str(self.serial) + ": lc killed! \n")
                self.textout.update()
        except Exception, e:
            # self.textout.insert(END, "出错了\n")
            # self.textout.update()
            import traceback
            traceback.print_exc()

    def testLaunch(self):
        try:
            self.textout.delete(1.0, END)
            self.textout.insert("1.0", "Test Minicap Start!\n")
            self.textout.update()
            if self.serial == "":
                self.serial = self.radionButton_value.get()
            self.screensave = int(self.numberChosen.get())
            if self.screensave < 3:
                self.screensave = 3
            x = self.startX.get()
            y = self.startY.get()
            xy = str(x + "x" + y)
            if x == '' or y == '':
                self.textout.insert("2.0", "Please input click point!\n")
                self.textout.update()
                return
            self.textout.insert("3.0", "Click Point: " + xy + " , please wait...\n")
            self.textout.update()
            appdev = MinicapMin.TestDevice(serial=self.serial)
            appstarttime = appdev.testAppStartTime(int(self.screensave), xy)
        except Exception, e:
            self.textout.insert(END, "出错了\n")
            self.textout.update()
            # import traceback
            # traceback.print_exc()
        finally:
            self.textout.insert("5.0", "Test Minicap End!\n ")
            self.textout.update()

    def gettest(self):
        self.screensave = int(self.numberChosen.get())
        zhixingfangshi = self.radionButton_rp_value.get()

        if zhixingfangshi == "r":
            self.record()
        else:
            self.testFPS()

    def record(self):
        self.textout.delete(1.0, END)
        ref = self.fileEdit.get()

        if ref == "":
            ref = os.getcwd() + "/temp.txt"
        self.textout.insert("1.0", "Record to file:" + ref)
        self.textout.update()
        (path, shotname) = os.path.split(ref)
        cmd = "wait-for-device shell /data/local/tmp/eventrec /sdcard/" + shotname
        try:
            start = datetime.datetime.now()
            process = subprocess.Popen(['adb', '-s', [self.serial], [cmd]])
            while process.poll() is None:
                time.sleep(2)
                now = datetime.datetime.now()
                if (now - start).seconds > int(self.screensave):
                    os.kill(process.pid, signal.SIGTERM)
                    return None
        except KeyboardInterrupt:
            print "Stop:", shotname
        finally:
            self.raw_cmd('pull', '/sdcard/' + shotname, os.getcwd())  # visual_bars
            self.textout.delete(1.0, END)
            self.textout.insert("1.0", "Save to File:" + ref)
            self.textout.update()

    def replay(self, pf):
        start = datetime.datetime.now()
        (path, shotname) = os.path.split(pf)
        if path == "":
            self.raw_cmd('push', os.getcwd() + '/' + pf, '/sdcard/')
        else:
            self.raw_cmd('push', pf, '/sdcard/')
        cmd = "shell /data/local/tmp/eventrec -p /sdcard/" + shotname
        process = subprocess.Popen(['adb', '-s', [self.serial], [cmd]])

        while process.poll() is None:
            time.sleep(2)
            now = datetime.datetime.now()
            du = now - start
            if du.seconds > 600:
                try:
                    process.terminate()
                    return True
                except Exception, e:
                    self.textout.insert(END, "出错了\n")
                    self.textout.update()
                    return False

    def grantPermission(self, pkg):
        "dumpsys package com.ape.filemanager | grep granted=false"
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.ACCESS_COARSE_LOCATION")
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.READ_EXTERNAL_STORAGE")
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.WRITE_EXTERNAL_STORAGE")
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.READ_CONTACTS")
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.WRITE_CONTACTS")
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.CALL_PHONE")
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.RECORD_AUDIO")
        self.raw_cmd('shell', 'pm', 'grant', pkg,
                     "android.permission.READ_PHONE_STATE")
        out = \
            self.raw_cmd('shell', 'dumpsys', 'package', pkg,
                         '| grep granted=false |cut -d \':\' -f 1')
        if "permission" in out:
            b = out.strip().split("\r")
            print b
            for i in b:
                self.raw_cmd('shell', 'pm', 'grant', pkg, i)

    def calcufps(self, pkg):
        fps = 0
        result = self.gtest(pkg)
        if (result[0] > 0) & (result[2] > 0):
            fps = result[2]
        return fps

    def platformRun2(self):
        if tkinter.messagebox.askokcancel('提示', '要执行GO整机测试吗？'):
            import ConfigParser
            import glob
            import csv
            self.inidevice()
            self.textout.delete(1.0, END)
            self.textout.insert(END, "GO is runing...\n")
            self.textout.insert(END, "系统：" + self.buildversion + "\n")
            self.textout.insert(END, "-" * 53 + "\n")
            self.textout.update()

            persistentmem = 0

            persistent = self.raw_cmd('shell', 'dumpsys', 'meminfo', '| grep -A 10 Persistent ')

            if "Persistent" in persistent:
                persistentmem = persistent.split(":")[0]
                if "K" in persistentmem:
                    persistentmem = persistentmem.replace("K", "")
                if "," in persistentmem:
                    persistentmem = persistentmem.replace(",", "")
                    persistentmem = int(persistentmem) / 1024
            print "" + persistent
            memAv = self.raw_cmd('shell', 'cat', '/proc/meminfo', '|grep MemAvailable')
            if "kB" in memAv:
                memAv = int(memAv.split(":")[1].strip().replace("kB", "").strip()) / 1024
            print "Persistent:" + str(persistentmem) + " MB"
            print "MemAvailable:" + str(memAv) + " MB"

            self.textout.insert(END, "Persistent:" + str(persistentmem) + " MB" + "\n")
            self.textout.insert(END, "MemAvailable:" + str(memAv) + " MB" + "\n")
            self.textout.update()
            configl_files = []
            self.screensave = int(self.numberChosen.get())
            try:
                dsvf = "per_" + self.serial + "_" + str(datetime.datetime.now().hour) + "_" + str(
                    datetime.datetime.now().minute) + "_" + str(datetime.datetime.now().second) + ".csv"
                with open(dsvf, 'ab+') as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        ["Persistent", str(persistentmem), "MemAvailable", str(memAv) + " MB", "BuildVersion:",
                         self.buildversion])
                    writer.writerow(["package", "version", "starttime", "fps"])

                if self.fileEdit.get() != "":
                    configl_files = []
                    configl_files = glob.glob(self.fileEdit.get())
                else:
                    configl_files = glob.glob(os.getcwd() + '/lib/res/test_app/*.config')
                for filename in configl_files:
                    starttime = []
                    fps = []
                    fps_avg = 0
                    starttime_avg = 0
                    cf = ConfigParser.ConfigParser()
                    cf.read(filename)
                    pkg = cf.get("package", "package")
                    acv = cf.get("package", "activity")
                    self.package = pkg
                    version, buildversion, targetSDK = self.getAPKVersion()
                    self.grantPermission(pkg)

                    try:
                        for i in xrange(1, int(self.screensave) + 1):
                            print filename, u" 执行 %i 次..." % i
                            self.raw_cmd('shell', 'input', 'keyevent', '4')
                            time.sleep(0.1)
                            self.raw_cmd('shell', 'input', 'keyevent', '4')
                            time.sleep(0.1)
                            self.raw_cmd('shell', 'input', 'keyevent', '3')
                            time.sleep(0.1)
                            (path, shotname) = os.path.split(filename)
                            self.textout.insert(END, "<" + str(i) + "> 执行文件:" + str(shotname) + "\n")
                            self.textout.update()
                            out = self.raw_cmd('shell', 'am', 'start  -S -W', pkg + '/' + acv,
                                               '|grep TotalTime|cut -d \':\' -f 2')
                            time.sleep(0.2)
                            out = out.strip()
                            if out.isdigit():
                                starttime.append(int(out))

                            try:
                                come_in = cf.get("package", "goto")
                                if come_in != "":
                                    if "," in come_in:
                                        come_for = come_in.split(",")
                                        for cl in xrange(len(come_for)):
                                            if "x" in come_for[cl]:
                                                self.raw_cmd('shell', ' input', 'tap',
                                                             str(int(come_for[cl].split("x")[0])),
                                                             str(int(come_for[cl].split("x")[1])))
                                                time.sleep(0.3)
                                    else:
                                        if "/" in come_in:
                                            come_for = come_in.split("/")
                                            for cl in xrange(len(come_for)):
                                                come_for = come_in.split("/")
                                                self.d(text=come_for[cl]).click()
                                                time.sleep(1)
                                        else:
                                            self.d(text=come_in).click()
                                            time.sleep(1)
                            except Exception, e:
                                print "no goto section"

                            self.gfxclean()

                            if "ystemui" in pkg:
                                self.swipesystemui()
                            elif "etting" in pkg:
                                self.swiptDown(None)
                                self.swiptUp(None)
                                fps.append(self.calcufps(pkg))
                            elif "ialer" in pkg:
                                self.swiptDown(None)
                                self.swiptUp(None)
                                fps.append(self.calcufps(pkg))
                            elif "alculator" in pkg:
                                self.swiptUp(None)
                                self.swiptDown(None)
                                fps.append(self.calcufps(pkg))
                            else:
                                self.swiptDown(None)
                                self.swiptUp(None)
                                fps.append(self.calcufps(pkg))

                            print u"第" + str(i) + u"次<" + pkg + ">" + u"帧速FPS: " + str(fps_avg) + u" 启动时间：" + str(
                                starttime_avg)

                            self.raw_cmd('shell', 'input', 'keyevent', '4')
                            time.sleep(0.1)
                            self.raw_cmd('shell', 'input', 'keyevent', '4')
                            time.sleep(0.1)
                            self.raw_cmd('shell', 'input', 'keyevent', '3')
                            time.sleep(0.1)
                        if len(starttime) >= 3:
                            starttime.remove(max(starttime))
                            starttime.remove(min(starttime))
                            starttime_avg = sum(starttime) / len(starttime)
                        else:
                            starttime_avg = sum(starttime) / len(starttime)
                        if len(fps) >= 3:
                            fps.remove(max(fps))
                            fps.remove(min(fps))
                            fps_avg = sum(fps) / len(fps)
                        else:
                            fps_avg = sum(fps) / len(fps)
                        if "." in pkg:
                            self.textout.insert(END, "<" + pkg.split(".")[-1] + ">" + ": FPS = " + str(
                                fps_avg) + ", StartTime = " + str(starttime_avg) + "\n")
                        else:
                            self.textout.insert(END, "<" + pkg + ">" + ": FPS = " + str(
                                fps_avg) + ", StartTime = " + str(starttime_avg) + "\n")
                        self.textout.insert(END, "-" * 53 + "\n")
                        self.textout.update()
                        with open(dsvf, 'ab+') as f:
                            writer = csv.writer(f)
                            writer.writerow([pkg, version, starttime_avg, fps_avg])
                    except Exception, e:
                        # import traceback
                        # traceback.print_exc()
                        self.textout.insert(END, "platformRun2.LOOP()出错了\n")
                        self.textout.update()
                    finally:
                        self.raw_cmd('shell', 'am', 'force-stop', pkg)
                        # self.getLog(pkg)
            except Exception, e:
                self.textout.insert(END, "platformRun2()出错了\n")
                self.textout.update()
                # import traceback
                # traceback.print_exc()
            finally:
                self.textout.insert(END, "-" * 53 + "\n")
                self.textout.insert(END, "测试完成\n")
                self.textout.update()

    def killsh(self):
        ps_line = self.raw_cmd('shell', 'cat', '/data/local/tmp/FPS.pid')
        if len(ps_line) > 0:
            pid = ps_line.strip()
            self.raw_cmd('shell', 'kill', str(pid))
        time.sleep(1)

    def get_battery(self):
        output = self.raw_cmd('shell', 'dumpsys battery')
        battery2 = int(re.findall("level:.(\d+)*", output, re.S)[0])
        print battery2

    def get_cpuT(self):
        cpu = 0
        mem = 0
        try:
            d = threading.Thread(target=self.cpuThreading)
            d.setDaemon(True)
            d.start()
        except Exception, e:
            # import traceback
            # traceback.print_exc()
            self.textout.insert(END, "出错了\n")
            self.textout.update()

    def cpuThreading(self):
        cpu = 0
        mem = 0
        try:
            while self.cpu_flag:
                time.sleep(2)
                pkg = self.getPackage()
                cmd = "shell top -n 1 | grep %s" % (pkg[:13])
                process = subprocess.Popen(['adb', '-s', [self.serial], [cmd]], stdout=PIPE, stderr=PIPE)
                output = process.stdout.readline()
                mem = int(float(self.getMemInfo(pkg)))
                if pkg[:13] in output:
                    sdkout = self.raw_cmd('shell', 'getprop', 'ro.build.version.sdk')
                    sdk = int(sdkout.strip())
                    if sdk < 26:
                        cpu = int(float((output[output.find("%") - 2:output.find("%")]).strip()))
                    else:
                        cpu = int(float((output[output.find("S") + 1:output.find("S") + 7]).strip()))
                # print pkg, cpu, mem
                self.q.put([pkg, {"cpu": cpu, "mem": mem}])
                # print pkg + "[ CPU: " + str((cpu)) + "%, Memory:" + str(int(float(self.mem))), "M ]"
        except Exception, e:
            # import traceback
            # traceback.print_exc()
            self.textout.insert(END, "出错了\n")
            self.textout.update()
        finally:
            return mem, cpu

    def getMemInfo(self, pkg):
        try:
            memJava = []
            memSystem = []
            memPrivate = []
            memTotal3 = []
            memJava3 = []
            memNative3 = []
            memNative = []
            memGraphics = []
            memTotal = []
            memCode = []
            memStack = []
            getmemory = "adb -s " + self.serial + " shell \"dumpsys meminfo --package " + pkg + " | grep -A 55 \\[" + \
                        pkg + "\\] | grep -E '(TOTAL:)|(Java Heap:)|(Native Heap:)|(Code:)|(Stack:)|(Graphics:)|(Private Other:)|(System:)'\""
            pm = Popen(getmemory, shell=True, stdout=PIPE, stderr=PIPE)
            readlins = pm.stdout.readlines()
            if len(readlins) >= 7:
                readlin = readlins[-8:]
                for i in xrange(0, len(readlin)):
                    if "Java Heap" in readlin[i]:
                        javaheap = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        javaheap = round(int(re.findall(r'\d+', javaheap)[0]) / 1024.0, 2)
                        memJava.append(javaheap)
                    elif "Native Heap" in readlin[i]:
                        nativeheap = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        nativeheap = round(int(re.findall(r'\d+', nativeheap)[0]) / 1024.0, 2)
                        memNative.append(nativeheap)

                    elif "TOTAL:" in readlin[i]:
                        memtotal = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        memtotal = round(int(re.findall(r'\d+', memtotal)[0]) / 1024.0, 2)
                        memTotal.append(memtotal)
                    elif "Code:" in readlin[i]:
                        code = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        code = round(int(re.findall(r'\d+', code)[0]) / 1024.0, 2)
                        memCode.append(code)

                    elif "Stack:" in readlin[i]:
                        stack = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        stack = round(int(re.findall(r'\d+', stack)[0]) / 1024.0, 2)
                        memStack.append(stack)

                    elif "Graphics:" in readlin[i]:
                        graphics = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        graphics = round(int(re.findall(r'\d+', graphics)[0]) / 1024.0, 2)
                        memGraphics.append(graphics)

                    elif "Private:" in readlin[i]:
                        private = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        private = round(int(re.findall(r'\d+', private)[0]) / 1024.0, 2)
                        memPrivate.append(private)

                    elif "System:" in readlin[i]:
                        system = readlin[i].split(":")[1].strip(" ").strip("\r\n")
                        system = round(int(re.findall(r'\d+', system)[0]) / 1024.0, 2)
                        memSystem.append(system)

                if len(memTotal) > 0:
                    m = memTotal
                    x = [float(m) for m in m if m]
                    av = 0
                    if len(x) > 0:
                        memTotal3.append(max(x))
                        memTotal3.append(min(x))
                        mt = len(x)
                        ma = sum(x)
                        av = round(ma / mt, 2)
                    memTotal3.append(av)
                if len(memJava) > 0:
                    m = memJava
                    x = [float(m) for m in m if m]
                    av = 0
                    if len(x) > 0:
                        memJava3.append(max(x))
                        memJava3.append(min(x))
                        mt = len(x)
                        ma = sum(x)
                        av = round(ma / mt, 2)
                    memJava3.append(av)

                if len(memNative) > 0:
                    m = memNative
                    x = [float(m) for m in m if m]
                    av = 0
                    if len(x) > 0:
                        memNative3.append(max(x))
                        memNative3.append(min(x))
                        mt = len(x)
                        ma = sum(x)
                        av = round(ma / mt, 2)
                    memNative3.append(av)
                    # print self.memTotal, memJava, self.memNative,memTotal3,memJava3,memNative3,self.memCode,self.memStack,self.memGraphics,memPrivate,memSystem
        except Exception, e:
            self.textout.insert(END, "getMemInfo()出错了\n")
            self.textout.update()
        finally:
            # print "mem:",memTotal3
            # return self.memTotal, memJava, self.memNative, memTotal3, memJava3, memNative3, self.memCode, self.memStack, self.memGraphics, memPrivate, memSystem
            if len(memTotal3) > 0:
                return str(memTotal3[0])
            else:
                return 0

    def tomd5(self, node):
        return hashlib.md5(str(node)).hexdigest()

    def _parse_xml_node(self, node):
        # ['bounds', 'checkable', 'class', 'text', 'resource_id', 'package']
        __alias = {
            'class': 'class_name',
            'resource-id': 'resource_id',
            'content-desc': 'content_desc',
            'long-clickable': 'long_clickable',
        }

        def parse_bounds(text):
            m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', text)
            if m is None:
                return None
            return Bounds(*map(int, m.groups()))

        def str2bool(v):
            return v.lower() in ("yes", "true", "t", "1")

        def convstr(v):
            return v.encode('utf-8')

        parsers = {
            'bounds': parse_bounds,
            'text': convstr,
            'class_name': convstr,
            'resource_id': convstr,
            'package': convstr,
            'checkable': str2bool,
            'scrollable': str2bool,
            'focused': str2bool,
            'clickable': str2bool,
            'enabled': str2bool,
            'selected': str2bool,
            'long_clickable': str2bool,
            'focusable': str2bool,
            'password': str2bool,
            'index': int,
            'content_desc': convstr,
        }
        ks = {}
        for key, value in node.attributes.items():
            key = __alias.get(key, key)
            f = parsers.get(key)
            if value is None:
                ks[key] = None
            elif f:
                ks[key] = f(value)
        for key in parsers.keys():
            ks[key] = ks.get(key)
        ks['xml'] = node

        return UINode(**ks)

    def dumnode(self):
        try:
            allmd5 = ""
            xy = {}
            nodehas = []
            canbeclick = ["android.widget.Button", "android.widget.TextView", "android.widget.ImageButton",
                          "android.widget.ImageView", "android.widget.CompoundButton"]
            cannotbeclick = ["USB tethering", "reset", "RESET", "Factory data reset", "Start now", "Navigate up",
                             "USB connected, check to tether"]
            out = self.raw_cmd('shell', '/system/bin/uiautomator ', 'dump', '--compressed',
                               '/sdcard/gfxtest.xml')
            time.sleep(0.2)
            xmldata = self.raw_cmd('shell', 'cat', '/sdcard/gfxtest.xml')
            dom = xml.dom.minidom.parseString(xmldata)
            root = dom.documentElement
            nodes = root.getElementsByTagName('node')
            ui_nodes = []
            allnode = ""

            for node in nodes:
                ui_nodes.append(self._parse_xml_node(node))
            nodecount = len(ui_nodes)
            for i in xrange(nodecount):
                if ui_nodes[i].class_name in canbeclick:
                    # if (("ALLOW" ==ui_nodes[i].text) and(ui_nodes[i].class_name=="android.widget.Button")):
                    #     self.permissionClick(ui_nodes[i].bounds.center)
                    if (ui_nodes[i].text not in cannotbeclick) & (ui_nodes[i].content_desc not in cannotbeclick):
                        clickmd5 = self.tomd5(
                            ui_nodes[i].class_name + ui_nodes[i].content_desc + ui_nodes[i].resource_id + str(
                                ui_nodes[i].bounds.center))
                        # self.blacklist.append(clickmd5)
                        # allnode = allnode + ";" + ui_nodes[i].class_name + "," + ui_nodes[i].content_desc + "," + \
                        #           ui_nodes[i].resource_id + "," + str(ui_nodes[i].bounds.center)
                        allnode = allnode + ";" + ui_nodes[i].class_name + \
                                  ui_nodes[i].resource_id + "," + str(ui_nodes[i].bounds.center)
                        xy[clickmd5] = ui_nodes[i].bounds.center
            allmd5 = self.tomd5(allnode)
            if allmd5 not in self.md5list:
                self.md5list.append(allmd5)
        except Exception, e:
            self.textout.insert(END, "出错了\n")
            self.textout.update()
        finally:
            return allmd5, xy, allnode

    def travel2(self, pkg):
        try:
            clicklist = {}
            blacklist = {}

            nomd, xy, an = self.dumnode()
            perkey = []
            runtflat = True
            while ("packageinstaller" in an) or ("android:id/alertTitle" in an):
                for p in xrange(6):
                    for pi in xy.keys():
                        perkey.append(xy.get(pi))
                self.permissionClick(max(perkey))
                nomd, xy, an = self.dumnode()

            base = xy
            nomdo = nomd
            ct = 0
            timeNow = time.time()
            packagenow = pkg
            while ct <= int(590) and (len(xy) > 0) and runtflat:
                ct = time.time() - timeNow
                ky = xy.keys()[random.randint(0, len(xy) - 1)]
                cxy = xy.pop(ky)
                if ky not in blacklist:
                    if ky in clicklist:
                        clicklist[ky] += 1
                    else:
                        clicklist[ky] = 1
                    if (clicklist[ky]) < 10:
                        self.raw_cmd('shell', ' input', 'tap', str(cxy[0]),
                                     str(cxy[1]))
                    packagenow = self.getPackage()
                    if pkg not in packagenow:
                        blacklist[ky] = cxy
                        if pkg != "":
                            self.raw_cmd('shell', 'am', 'force-stop', pkg)
                        self.raw_cmd('shell', 'input', 'keyevent', '3')
                        self.raw_cmd('shell',
                                     'monkey', '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1')
                    time.sleep(1)
                    nomdn, xy, an = self.dumnode()
                    if nomdn == nomdo:
                        blacklist[ky] = cxy
                        continue
                    else:
                        nomdo = nomdn
                inter = dict.fromkeys([x for x in base if x in blacklist])
                df = list(set(base.keys()).difference(set(inter.keys())))
                if df == []:
                    # print  pkg + "-->over!"
                    break
                elif len(xy) == 0:
                    if pkg != "":
                        self.raw_cmd('shell', 'am', 'force-stop', pkg)
                    time.sleep(0.2)
                    self.raw_cmd('shell',
                                 'monkey', '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1')
                    time.sleep(1)
                    nomdn, xy, an = self.dumnode()
                    runtflat = False
                    self.raw_cmd('shell', 'input', 'keyevent', '4')
                    self.raw_cmd('shell', 'input', 'keyevent', '3')
                    print  pkg + "-->End!"
        except Exception, e:
            self.cpu_flag = False
            # import traceback
            # traceback.print_exc()
            self.textout.insert(END, "出错了\n")
            self.textout.update()
        finally:
            self.cpu_flag = False

    def permissionClick(self, xy):
        os.system('adb -s ' + self.serial + " wait-for-device shell input tap " + str(xy[0]) + " " + str(xy[1]))
        time.sleep(0.2)

    def coverfile(self):
        inputevent = self.getpad()
        orx = 480
        ory = 960
        nowx = self.WIDTH
        nowy = self.HEIGHT
        x = 0
        y = 0
        with open('a.txt', 'a+') as f:
            lines = f.read()
        with open('b.txt', 'w') as f:
            for line in lines.split("\n"):
                if line != "":
                    line = line.replace(line[line.find("/dev/input"):line.find(":")], inputevent)
                    if "0035" == line.split()[4]:
                        x = line.split()[5]
                        print "ox:", x
                        x = int(str('0x' + x), 16)  # 16 to 10
                        if orx > nowx:
                            x = int(x) * orx / nowx
                        else:
                            x = int(x) * nowx / orx
                        x = hex(x)
                        x = str(x).split("0x")[1].zfill(8)
                        print "nx:", x

                        f.write(line[:-8] + x + "\n")
                    elif "0036" == line.split()[4]:
                        y = line.split()[5]
                        print "oy:", y
                        y = int(str('0x' + y), 16)  # 16 to 10
                        if ory > nowy:
                            y = int(y) * ory / nowy
                        else:
                            y = int(y) * nowy / ory
                        y = hex(y)
                        y = str(y).split("0x")[1].zfill(8)
                        print "oy:", y
                        f.write(line[:-8] + y + "\n")
                    else:
                        f.write(line + "\n")

    def getpad(self):
        try:
            out = self.raw_cmd('shell', 'getevent -p  | grep -B 15 \"0035\"')
            outl = out.split("\n")
            inputevent = ""
            for i in xrange(len(outl)):
                if len(outl) > 0:
                    outlo = outl[-1]
                    if "/dev/input/event" in outlo:
                        inputevent = outlo[outlo.find("/dev/input"):]
                        inputevent = inputevent.strip()
                        break
                    else:
                        if len(outl) > 0:
                            outl.remove(outl[-1])
        except Exception, e:
            self.textout.insert(END, "出错了\n")
            self.textout.update()
        finally:
            return inputevent

    def recordatx(self):
        try:
            getfile = raw_input("Please input save file name: ")
            if getfile == "":
                print "Please input the record file name!"
                sys.exit(1)
            if os.path.isfile(os.getcwd() + "/" + getfile):
                os.remove(os.getcwd() + "/" + getfile)
            p = subprocess.Popen(['adb', '-s', self.serial, 'shell', 'getevent', '-l'], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

            self.recordmain(p.stdout, getfile)
        except KeyboardInterrupt:
            p.kill()
        finally:
            print "save to file!"

    def recordmain(self, pipe, filename):
        xs, ys = [], []
        lastOper = ''
        touchStart = 0
        start = time.time()
        begin = time.time()
        DEVSCREEN = self.getpad()

        def record(fmt, *args):
            outstr = fmt % args
            if filename:
                with open(filename, 'a+') as file:
                    file.write(outstr + '\n')

        record('display:' + str(self.WIDTH) + '_' + str(self.HEIGHT))
        while True:
            line = pipe.readline()
            if not line.startswith(DEVSCREEN):
                continue
            channel, event, oper, value = line.split()
            # print value#int(value, 16)
            if "DOWN" in value:
                continue
            else:
                # if oper == 'SYN_REPORT':
                #     continue
                if oper == 'ABS_MT_POSITION_X':
                    value = int(value, 16)
                    xs.append(value)
                elif oper == 'ABS_MT_POSITION_Y':
                    value = int(value, 16)
                    ys.append(value)
                elif value == 'UP' or oper == "SYN_REPORT":
                    if 1 == 1:
                        # xs = map(lambda x: x / self.WIDTH, xs)
                        # ys = map(lambda y: y / self.HEIGHT, ys)
                        if len(xs) != 0 and len(ys) != 0:  # every thing is OK
                            (x1, y1), (x2, y2) = (xs[0], ys[0]), (xs[-1], ys[-1])
                            dist = ((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1)) ** 0.5

                            duration = time.time() - touchStart
                            # touch up
                            if dist < 50:
                                print "click:", x1, y1
                                record('clickscreen:%dx%d', x1, y1)
                            else:
                                print "drag:", x1, y1, x2, y2
                                record('drag:%d, %d, %d, %d,30', x1, y1, x2, y2)
                        xs, ys = [], []
                    else:
                        if len(xs) == 1:
                            # touch down
                            record('app.sleep(%.2f)', float(time.time() - start))
                            start = time.time()
                            touchStart = time.time()
                lastOper = oper

    def playatxthread(self, playfile, device, devicemin):
        t = threading.Thread(target=self.playatxfile, args=(playfile, device, devicemin,))
        t.setDaemon(True)
        t.start()
        t.join()

    def playatxfile(self, playfile, device, devicemin):
        try:
            with open(playfile, 'a+') as f:
                lines = f.read()
                readline = lines.split("\n")
                rt = self.playatxcontent(readline, device, devicemin)

        except Exception, e:
            import traceback
            traceback.print_exc()
            self.textout.insert(END, "控制出错了\n")
            self.textout.update()
        finally:
            return rt

    def playatxcontent(self, playcontent, device, devicemin):
        playscreenx = self.WIDTH
        playscreeny = self.HEIGHT
        restricscreen = self.getShape()
        resx = restricscreen[0]
        resy = restricscreen[1]
        d = device
        self.result = "True"
        op = ""
        loopflag=False
        sub_content=[]
        sub_content_times =0
        try:
            for index, line in enumerate(playcontent):
                if line != "":
                    if loopflag and "end" not in line:
                        sub_content.append(line)
                        continue
                    elif loopflag and "end" in line:
                        loopflag = False
                        for i in xrange(0,sub_content_times):
                            self.playatxcontent(sub_content,device,devicemin)

                    elif "display:" in line:
                        playscreenx = int(line.split(":")[1].split("_")[0])
                        playscreeny = int(line.split(":")[1].split("_")[1])
                    elif "clickscreen" in line:
                        op = "clickscreen"
                        par = line.split(":")[1]
                        x = int(par.split("x")[0])
                        y = int(par.split("x")[1])
                        # print playscreenx,playscreeny
                        if playscreenx > self.WIDTH:
                            x = int(x) * playscreenx / self.WIDTH
                        else:
                            x = int(x) * self.WIDTH / playscreenx
                        if playscreeny > self.HEIGHT:
                            y = int(y) * playscreeny / self.HEIGHT
                        else:
                            y = int(y) * self.HEIGHT / playscreeny
                        # print int(x),int(y),resx,resy
                        if int(y) > int(resy):
                            if (int(x)) < self.WIDTH / 3:
                                d.press.back()
                                time.sleep(0.5)
                            elif (int(x)) > self.WIDTH * 0.7:
                                self.result = d.press.recent()
                                time.sleep(1)
                            else:
                                self.result = d.press.home()
                                time.sleep(0.5)
                        else:
                            self.result = d.click(x, y)
                            time.sleep(0.5)
                    elif "drag" in line or "swipe" in line:
                        op = "drag"
                        par = line.split(":")[1]
                        x = int(par.split(",")[0])
                        y = int(par.split(",")[1])
                        x1 = int(par.split(",")[2])
                        y1 = int(par.split(",")[3])

                        if playscreenx > self.WIDTH:
                            x = int(x) * playscreenx / self.WIDTH
                            x1 = int(x1) * playscreenx / self.WIDTH
                        else:
                            x = int(x) * self.WIDTH / playscreenx
                            x1 = int(x1) * self.WIDTH / playscreenx
                        if playscreeny > self.HEIGHT:
                            y = int(y) * playscreeny / self.HEIGHT
                            y1 = int(y1) * playscreeny / self.HEIGHT
                        else:
                            y = int(y) * self.HEIGHT / playscreeny
                            y1 = int(y1) * playscreeny / self.HEIGHT
                        if "drag" in line:
                            self.result = d.drag(x, y, x1, y1, 30)
                        else:
                            self.result = d.swipe(x, y, x1, y1, 30)

                    elif "checktext" in line:
                        op = "checktext"
                        x = line.split(":")[1]
                        p = d(text=x).wait.exists(timeout=5000)
                        if p:
                            self.result = "True"
                            self.textout.insert(END, "Text <" + x + ">" + " < Found!> \n")
                            self.textout.update()
                            d.screenshot(
                                "pic/checktext_Found_" + time.strftime("%m%d%H%M%S", time.localtime()) + ".png")

                        else:
                            self.result = "False"
                            self.textout.insert(END, "Text <" + x + ">" + " < Not Found!>\n")
                            self.textout.update()
                            d.screenshot(
                                "pic/checktext_NotFound_" + time.strftime("%m%d%H%M%S", time.localtime()) + ".png")

                    elif "checkimage" in line:
                        op = "checkimage"
                        x = line.split(":")[1]
                        getORno = devicemin.wait(x, timeout=10)
                        if getORno is None:
                            self.result = "False"
                            self.textout.insert(END, "Image <" + x + ">" + " < Not Found! " + " >\n")
                            self.textout.update()
                            d.screenshot(
                                "pic/checkimage_nf_" + time.strftime("%m%d%H%M%S", time.localtime()) + ".png")
                        elif getORno.matched:
                            self.result = "Found at:" + str(getORno[0])
                            self.textout.insert(END,
                                                "Image <" + x + ">" + " < Found at: " + str(getORno[0]) + " >\n")
                            d.screenshot(
                                "pic/checkimage_f_" + time.strftime("%m%d%H%M%S", time.localtime()) + ".png")

                    elif "ocrtext" in line:
                        op = "ocrtext"
                        self.screenShot(os.getcwd())
                        x = line.split(":")[1]
                        result = MYOCRTest.repara()
                        print result
                        for i in xrange(len(result)):
                            if x[1:-1] in result[i].get("words"):
                                self.logger.info("<" + x + ">" + " < Found! >")
                                self.result = "True"
                                break
                            elif i == len(result) - 1:
                                self.result = "False"
                                self.logger.info("<" + x + ">" + " < Not Found! >")
                                d.screenshot(
                                    "pic/ocrtext_nf_" + time.strftime("%m%d%H%M%S", time.localtime()) + ".png")

                    elif "ocrface" in line:
                        print u"人脸识别"
                        self.result = MYOCRTest.repface()

                    elif "sleep" in line:
                        if ":" in line:
                            x = line.split(":")[1]
                            time.sleep(int(x))
                        else:
                            time.sleep(1)

                    elif "pressback" in line:
                        if ":" in line:
                            x = line.split(":")[1]
                            for i in xrange(0,int(x)):
                                d.press.back()
                                time.sleep(0.2)
                        else:
                            d.press.back()

                    elif "orientation" in line:

                        op = "orientation"
                        x = line.split(":")[1]
                        if "l" in x or "r" in x or "n" in x:
                            d.orientation = x

                    elif "reboot" in line:
                        self.raw_cmd('shell', 'reboot')
                        time.sleep(30)
                        out = self.raw_cmd('shell', 'get-state')
                        if "device" in out:
                            print "reboot ok"

                    elif "presshome" in line:
                        d.press.home()
                    elif "input" in line:
                        x = line.split(":")[1]
                        self.shell_cmd('input text ' + x)
                    elif "pressrecent" in line:
                        d.press.recent()
                    elif "loop:" in line:
                        loopflag=True
                        x = line.split(":")[1]
                        sub_content_times = int(x)

                    elif "clicktext" in line:
                        try:
                            op = "clicktext"
                            x = line.split(":")[1]
                            d(text=x).click()
                        except Exception, jc:
                            self.result = "False"
                            self.textout.insert(END, "点击文字出错：" + x + "\n")
                            self.textout.update()
                            d.screenshot(
                                "pic/clicktext_ERROR_" + time.strftime("%m%d%H%M%S", time.localtime()) + ".png")

                    elif "playrecord" in line:
                        op = "playrecord"
                        file = line.split(":")[1]
                        self.result = self.replay(file)
                    elif "clickimage" in line:
                        op = "clickimage"
                        x = line.split(":")[1]
                        getORno = devicemin.wait(x, timeout=12)
                        if getORno is None:
                            self.result = "False"
                            # self.logger.error("<" + x + ">" + " < Not Found! >")
                            d.screenshot(
                                "pic/imagenotfound_" + time.strftime("%m%d%H%M%S", time.localtime()) + ".png")
                        elif getORno.matched:
                            d.click(getORno[0][0], getORno[0][1])
                            time.sleep(0.2)
                            self.result = "True"
                            # self.logger.info("Image <" + x + ">" + " < Found at: " + str(getORno[0]) + ">")
        except Exception, e:
            import traceback
            traceback.print_exc()
            self.textout.insert(END, "控制出错了\n")
            self.textout.update()
        finally:
            self.screenShot(
                os.getcwd() + "/pic/" + op + "_" + str(
                    datetime.datetime.now().strftime("%m_%d_%H_%M_%S")) + ".png")
            return self.result

    def getPackageAllActivitys(self, pkg):
        pkgs = []
        cmds = 'dumpsys package ' + pkg + '| grep ' + pkg + '/'
        out = self.shell_cmd(cmds)
        for i in out.split("\n"):
            j = i.split()
            if len(j) > 1:
                if "/." in j[1] or "/com" in j[1]:
                    k = j[1]
                    if "}" in k:
                        k = k.replace("}", "")
                    elif "{" in k:
                        k = k.replace("{", "")
                    if "/." in k:
                        act = pkg + k.split("/")[1]
                    else:
                        act = k.split("/")[1]
                    pkgs.append(act)
        return pkgs

    def getCurrentActivitys(self):
        out = self.shell_cmd('getprop ro.build.version.sdk')
        sdk = int(out.strip())
        if sdk < 26:
            getp = self.shell_cmd('dumpsys activity |grep mFocusedActivity')
        else:
            getp = self.shell_cmd('dumpsys activity |grep mResumedActivity')
        out = self.shell_cmd('')
        start = getp.find("com")
        end = getp.find('}')
        package = getp[start:end].strip().split()[0]  # 'com.ape.launcher/com.myos.MyosLauncher'
        activity = package.split("/")[1]  # 'com.myos.MyosLauncher'
        if "/." in package:
            activity = package.split("/")[0] + activity

        # apkversion = self.raw_cmd( 'shell', 'dumpsys', "package", package, "|", "grep",'versionName', '|head -n 1')
        return activity

    def getShape(self):
        rsRE = re.compile('\s*mRestrictedScreen=\(\d+,\d+\) (?P<w>\d+)x(?P<h>\d+)')
        for line in subprocess.check_output('adb -s ' + self.serial + ' shell dumpsys window', shell=True).splitlines():
            m = rsRE.match(line)
            if m:
                return m.groups()
        raise RuntimeError('Couldn\'t find mRestrictedScreen in dumpsys')

    def shell_cmd(self, cmd):
        cmds = 'adb ' + ' -s ' + self.serial + ' wait-for-device shell ' + "\"" + cmd + "\""
        return os.popen(cmds).read()

    def travelApp(self, pkg):
        try:
            clicklist = {}
            blacklist = {}
            allActivits = self.getPackageAllActivitys(pkg)
            for p in allActivits:
                clicklist[p] = []
            perkey = []
            runtflat = True
            self.shell_cmd('am force-stop ' + pkg)
            self.shell_cmd('input keyevent 4')
            self.shell_cmd('input keyevent 4')
            self.shell_cmd('input keyevent 4')
            self.raw_cmd('shell',
                         'monkey', '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1')

            time.sleep(1)
            nomd, xy, an = self.dumnode()
            if pkg not in self.getPackage():
                for pi in xy.keys():
                    perkey.append(xy.get(pi))
                for i in xrange(0, 6):
                    if pkg not in self.getPackage():
                        self.permissionClick(max(perkey))
            time.sleep(2)
            nomd, xy, an = self.dumnode()
            base = xy
            nomdo = nomd
            ct = 0
            timeNow = time.time()
            packagenow = pkg
            activityOld = self.getCurrentActivitys()
            while ct <= int(590) and (len(xy) > 0) and runtflat:
                ct = time.time() - timeNow
                ky = xy.keys()[random.randint(0, len(xy) - 1)]  # point "md5":"100x200",ky is key
                cxy = xy.pop(ky)  # point "md5":"100x200",cxy is value
                os.system(
                    'adb -s ' + self.serial + " wait-for-device shell input tap " + str(cxy[0]) + " " + str(cxy[1]))
                time.sleep(0.2)
                nomdn, xy, an = self.dumnode()
                activityNow = self.getCurrentActivitys()
                if cxy not in clicklist[activityOld]:
                    clicklist[activityOld].append(ky)

                if activityNow not in allActivits:
                    clicklist[ky] = cxy
                    self.shell_cmd('input keyevent 4')
                    if self.getCurrentActivitys() not in allActivits:
                        self.shell_cmd('input keyevent 4')
                    if self.getCurrentActivitys() not in allActivits:
                        self.shell_cmd('input keyevent 4')
                    if self.getCurrentActivitys() not in allActivits:
                        self.raw_cmd('shell',
                                     'monkey', '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1')
                else:
                    if activityOld != activityNow:  # come to new activity
                        if cxy in clicklist[activityOld]:
                            clicklist[activityOld].remove(cxy)
                        activityOld = activityNow
        except Exception, e:
            self.cpu_flag = False
            # import traceback
            # traceback.print_exc()
            self.textout.insert(END, "出错了\n")
            self.textout.update()
        finally:
            self.cpu_flag = False

    def killMinicap(self):
        out = \
            self.raw_cmd('wait-for-device', 'shell', 'ps', '|grep', 'minicap')
        out = out.strip().split('\n')
        if len(out[0]) > 11:
            idx = out[0].split()[1]
            # pid = out[1].split()[idx]
            # print 'minicap is running, killing', idx
            self.raw_cmd('wait-for-device', 'shell', 'kill', '-9', idx)
        time.sleep(2)

    def imagetk(self):
        try:
            if self.minicap_ins is not None:
                img = self.minicap_ins.crop_image()
                # img = Image.open(os.getcwd() + '/maintmp.png')  # 打开图片
                w, h = img.size
                img = img.resize((360, 720), Image.ANTIALIAS)
                # photo = ImageTk.PhotoImage(img)  # 用PIL模块的PhotoImage打开
                # self.imglabel = Label(self.root, image=photo)
                # self.imglabel.place(x=700, y=0, width=324, height=600)

                image = img.copy()
                # image.thumbnail((360, 720), Image.ANTIALIAS)
                tkimage = ImageTk.PhotoImage(image)
                self._tkimage = tkimage  # keep a reference

                self.canvas.config(width=w, height=h)
                self.canvas.create_image(0, 0, anchor=tkinter.NW, image=tkimage)

        except Exception, e:
            pass

    def _mouse_click(self, event):
        self._moved = False
        c = self.canvas
        st = datetime.datetime.now()
        self._mouse_motion_xy.append([event.x, event.y])
        self.cavas_x_y[st] = (int(c.canvasx(event.x)), int(c.canvasy(event.y)))
        self._mouse_motion = "click"
        # print "_mouse_click", event.x, event.y
        # click_y = cavas_x
        # click_x = cavas_y
        # if int(self.WIDTH) > 360:
        #     click_x = cavas_x * (self.WIDTH / 360)
        # else:
        #     click_x = cavas_x * (360 / self.WIDTH)
        # if int(self.HEIGHT) > 720:
        #     click_y = cavas_y * (self.HEIGHT / 720)
        # else:
        #     click_y = cavas_y * (720 / self.HEIGHT)
        # print ('_mouse_click,mouse position: %s', (cavas_x, cavas_y, self.WIDTH, self.HEIGHT))
        #
        # self.raw_cmd( 'shell', ' input', 'tap', str(click_x), str(click_y))
        # # self.d.click(int(self.xy.split("x")[0]), int(self.xy.split("x")[1]))
        # time.sleep(2)
        # self.imagetk()

    def _stroke_move(self, event):
        # print "_stroke_move", event.x, event.y
        self._mouse_motion_xy.append([event.x, event.y])
        self._mouse_motion = "move"
        # self._moved = True
        # self._reset()
        # c = self.canvas
        # x, y = c.canvasx(event.x), c.canvasy(event.y)
        # self._bounds = (self._lastx, self._lasty, x, y)
        # self._center = (self._lastx + x) / 2, (self._lasty + y) / 2
        # self._draw_lines()

    def _mouse_move(self, event):
        print "_mouse_move", event.x, event.y

    def _stroke_done(self, event):
        try:
            x_start = 0
            x_end = 0
            y_start = 0
            y_end = 0
            c = self.canvas
            click_x = 0
            click_y = 0
            cavas_x, cavas_y = (int(c.canvasx(event.x)), int(c.canvasy(event.y)))
            # print "stroke done->", cavas_x, cavas_y
            # print "_stroke_done", "event:", event.x, event.y, "cavas:", cavas_x, cavas_y
            if self._mouse_motion == "click":
                # cavas_x, cavas_y = (int(c.canvasx(event.x)), int(c.canvasy(event.y)))
                stend = datetime.datetime.now()
                ststart = self.cavas_x_y.keys()

                click_x = cavas_x
                click_y = cavas_y
                if int(self.WIDTH) > 360:
                    click_x *= self.WIDTH / 360.0
                else:
                    click_x *= 360.0 / self.WIDTH
                if int(self.HEIGHT) > 720:
                    click_y *= self.HEIGHT / 720.0
                else:
                    click_y *= 720.0 / self.HEIGHT
                # print ('_mouse_click position: %s', (cavas_x, cavas_y, self.WIDTH, self.HEIGHT))
                # print "wait:", (stend - ststart[0]).total_seconds()
                if ((stend - ststart[0]).total_seconds() > 0.6) and (len(ststart) > 0):
                    self.raw_cmd('shell', ' input', 'swipe', str(click_x), str(click_y), str(click_x), str(click_y),
                                 '500')
                else:
                    self.raw_cmd('shell', ' input', 'tap', str(click_x), str(click_y))

                self.canvas.itemconfigure('select-bounds', width=2)
                if int(click_y) / float(self.HEIGHT) > 0.95:
                    if int(click_x) < self.WIDTH / 3:
                        self.textout.insert(END, "pressback:1\n")
                    elif int(click_x) > self.WIDTH * 0.6:
                        self.textout.insert(END, "pressrecent:1\n")
                    else:
                        self.textout.insert(END, "presshome:1\n")
                else:
                    self.textout.insert(END, "clickscreen:" + str(int(click_x)) + "x" + str(int(click_y)) + "\n")
                self.textout.update()
                # self.imagetk()
                # print "---",[int(cavas_x), int(cavas_y), int(cavas_x) + 5, int(cavas_y) + 5],cavas_x,cavas_y
                self._draw_bounds([int(cavas_x) - 10, int(cavas_y) - 10, int(cavas_x) + 10, int(cavas_y) + 10])


            elif self._mouse_motion == "move":
                self._mouse_motion = ""
                cavas_x, cavas_y = (int(c.canvasx(event.x)), int(c.canvasy(event.y)))
                click_x = cavas_x
                click_y = cavas_y
                if len(self._mouse_motion_xy) >= 2:
                    x_start = self._mouse_motion_xy[0][0]
                    y_start = self._mouse_motion_xy[0][1]
                    x_end = self._mouse_motion_xy[-1][0]
                    y_end = self._mouse_motion_xy[-1][1]
                    if int(self.WIDTH) > 360:
                        x_start *= self.WIDTH / 360.0
                        x_end *= self.WIDTH / 360.0
                    else:
                        x_start *= 360.0 / self.WIDTH
                        x_end *= 360.0 / self.WIDTH
                    if int(self.HEIGHT) > 720:
                        y_start *= self.HEIGHT / 720.0
                        y_end *= self.HEIGHT / 720.0
                    else:
                        y_start *= 720.0 / self.HEIGHT
                        y_end *= 720.0 / self.HEIGHT
                    # print ('_mouse_move cavas: %s', (self._mouse_motion_xy))
                    # print ('_mouse_move actural: %s', (x_start, y_start, x_end, y_end))

                    # print "---",[int(cavas_x), int(cavas_y), int(cavas_x) + 5, int(cavas_y) + 5],cavas_x,cavas_y
                    # self._draw_bounds([int(cavas_x) - 10, int(cavas_y) - 10, int(cavas_x) + 10, int(cavas_y) + 10])
                    if self._mouse_motion_crop == "crop":
                        # self.crop_box = [self._mouse_motion_xy[0][0], self._mouse_motion_xy[0][1], self._mouse_motion_xy[-1][0],
                        #                  self._mouse_motion_xy[-1][1]]
                        ti = c.create_rectangle(self._mouse_motion_xy[0][0], self._mouse_motion_xy[0][1],
                                                self._mouse_motion_xy[-1][0],
                                                self._mouse_motion_xy[-1][1], outline='red', tags='select-bounds',
                                                width=2)
                        if ti > 3:
                            c.delete(ti - 1)
                        # img = Image.open(os.getcwd() + '/maintmp.png')  # 打开图片
                        img = self.minicap_ins.crop_image()
                        # print ('_mouse_crop position: %s', (x_start, y_start, x_end, y_end))
                        try:
                            img.crop([x_start, y_start, x_end, y_end]).save(os.getcwd() + '/maintmp_crop.png')
                            self.textout.insert(END, "截图保存在:" + os.getcwd() + "/maintmp_crop.png \n")
                            self.textout.update()
                            self._mouse_motion_crop = ""
                        except Exception, e:
                            import traceback
                            traceback.print_exc()
                    else:
                        if y_end - y_start > 200 and x_end - x_start < 100:
                            # self.d.open.notification()
                            self.raw_cmd_nowait('shell', ' input', 'swipe', str(x_start), "1", str(x_end), str(y_end))

                            print "maybe notification"
                        else:
                            self.raw_cmd_nowait('shell', ' input', 'swipe', str(x_start), str(y_start),
                                                str(x_end),
                                                str(y_end))

                            # self.imagetk()

        except Exception, e:
            pass
            # import traceback
            # traceback.print_exc()
        finally:
            self._mouse_motion_xy = []
            self.cavas_x_y = {}

    def _draw_bounds(self, bounds, color='red', tags='select-bounds'):
        try:
            c = self.canvas
            (x0, y0, x1, y1) = bounds
            i = c.create_oval(x0, y0, x1, y1, fill="red")
            if i > 3:
                c.delete(i - 1)
        except Exception, e:
            pass

    def _draw_cycle(self):
        try:
            c = self.status_canvas
            x = 0
            y = 0
            x1 = 0
            y1 = 0
            while True:

                if not self.q.empty():
                    if self.q.get_nowait()[0] == self.package:
                        pqget = self.q.get_nowait()[1]
                        self.mem = pqget.get("mem")
                        self.cpu = pqget.get("cpu")
                        print self.cpu, self.mem

                xt = random.randint(0, 20)
                yt = random.randint(80, 100)
                i = c.create_line(x1, y1, x1 + xt, yt)
                x1 = x1 + xt
                y1 = yt
                print x1
                if x1 > 500:
                    for k in xrange(0, i + 1):
                        c.delete(k)
                        x1 = 0
                        y1 = 0
                time.sleep(0.1)
        except Exception, e:
            pass

    def draw_threading(self):
        # self.get_cpuT()
        t = threading.Thread(target=self._draw_cycle)
        t.setDaemon(True)
        t.start()

    def crop_image_show(self):
        self._mouse_motion_crop = "crop"
        # tkinter.messagebox.showinfo(title="提示框", message="用鼠标在右侧屏幕上画出要截取的位置，方框内图像即可保存到本地文件maintmp_crop.png")

        # if self._bounds is None:
        #     return
        # bounds = self.select_bounds
        # # ext = '.%dx%d.png' % tuple(self._size)
        # # tkFileDialog doc: http://tkinter.unpythonic.net/wiki/tkFileDialog
        # save_to = tkFileDialog.asksaveasfilename(**dict(
        #     initialdir=self._save_parent_dir,
        #     defaultextension=".png",
        #     filetypes=[('PNG', ".png")],
        #     title='Select file'))
        # if not save_to:
        #     return
        # save_to = self._fix_path(save_to)
        # # force change extention with info (resolution and offset)
        # save_to = os.path.splitext(save_to)[0] + self._fileext_text.get()
        #
        # self._save_parent_dir = os.path.dirname(save_to)
        #
        # self._image.crop(bounds).save(save_to)
        # self._genfile_name.set(os.path.basename(save_to))
        # self._gencode_text.set('d.click_image(r"%s")' % save_to)

    def inputStr(self):
        r = dl.askstring('输入要点击的文字', '输入文字', initialvalue='')
        print(r)

    def control_edit(self, mode="clicktext"):

        if mode == "clicktext":
            self.textout.insert(END, "clicktext:Settings\n")
        elif mode == "clickscreen":
            self.textout.insert(END, "clickscreen:200x300\n")
        elif mode == "clickimage":
            self.textout.insert(END, "clickimage:maintmp_crop.png\n")
        elif mode == "checktext":
            self.textout.insert(END, "checktext:Settings\n")
        elif mode == "checkimage":
            self.textout.insert(END, "checkimage:maintmp_crop.png\n")
        elif mode == "pressback":
            self.textout.insert(END, "pressback:1\n")
        elif mode == "pressrecent":
            self.textout.insert(END, "pressrecent:1\n")
        elif mode == "presshome":
            self.textout.insert(END, "presshome:1\n")
        elif mode == "playrecord":
            self.textout.insert(END, "playrecord:recordfile.txt\n")
        self.textout.update()

    def control_clear(self):
        self.textout.unbind("<KeyPress-Return>")
        self.textout.delete("1.0", END)
        self.textout.update()

    def control_openfile(self):
        self.control_clear()
        ref = self.fileEdit.get()
        if ref == "":
            ref = dl.askstring('文件打开', '输入要打开的文件名', initialvalue='')

        with open(ref, 'a+') as f:
            lines = f.read()
            for line in lines:
                self.textout.insert(END, line)
            self.textout.update()

    def control_save(self):
        try:
            content = self.textout.get("1.0", END)
            ref = self.fileEdit.get()
            if ref == "":
                ref = dl.askstring('文件保存', '输入要保存的文件名', initialvalue='')
            with open(ref, 'w+') as file:
                file.write(content + '\n')
        except UnicodeEncodeError, e:
            import traceback
            traceback.print_exc()
            tkinter.messagebox.showinfo(title="提示框",
                                        message="不能包含中文！\n")
        except Exception, e:
            import traceback
            traceback.print_exc()
            tkinter.messagebox.showinfo(title="提示框",
                                        message="出错了！\n")

    def enable_root(self):
        try:
            rooturl = r"http://osgroup.jstinno.com:8082/encrypt/key/encrypt"
            serial = [self.serial]
            if tkinter.messagebox.askokcancel('提示', 'root所有设备点<是>,<否>仅仅root当前设备:' + self.serial):
                serial = self.getAdb2()
            else:
                pass
            for i in xrange(0, len(serial)):
                self.serial = serial[i]
                data = {"keyString": self.serial}
                r = requests.post(rooturl, data=data)  # 在一些post请求中，还需要用到headers部分，此处未加，在下文中会说到
                out = "OK"
                ency = ""
                if "encryptString" in r.content:
                    ency = r.json().get("encryptString").encode()
                    out = self.raw_cmd('shell', 'setprop', 'persist.tinno.debug', str(ency))
                    self.raw_cmd('shell', 'setprop', 'persist.qiku.adb.input', '1')
                    self.raw_cmd('root')
                    self.raw_cmd('remount')
                self.textout.insert(END, "Root :" + self.serial + " -> " + str(ency) + " \n")
                self.textout.update()
        except Exception, e:
            self.textout.insert(END, "Root Fail! \n")
            self.textout.update()

    def enable_wifi(self):
        try:
            self.inidevice()
            serial = [self.serial]
            if tkinter.messagebox.askokcancel('提示', '连接所有设备wifi点<是>,<否>仅连接当前设备:' + self.serial):
                serial = self.getAdb2()
            else:
                pass
            for i in xrange(0, len(serial)):
                self.serial = serial[i]
                d = Device(self.serial)
                try:
                    cmds = ['adb'] + ['-s'] + [self.serial] + ['wait-for-device', 'shell', 'svc', 'wifi', 'enable']
                    p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0]
                    time.sleep(0.5)
                    cmds = ['adb'] + ['-s'] + [self.serial] + ['wait-for-device', 'shell', 'am', 'start', '-S', '-W',
                                                               'com.android.settings/com.android.settings.Settings']
                    p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0]
                    time.sleep(2)
                    if d(textContains="WLAN").exists:
                        d(textContains="WLAN").click()
                        time.sleep(1)
                        d(text="WLAN").click()
                    elif d(textContains="Network").exists:
                        d(textContains="Network").click()
                        time.sleep(1)
                        d(text="Wi‑Fi").click()
                    time.sleep(2)
                    d(scrollable=True).scroll.to(text="PENGUIN")
                    time.sleep(1)
                    d(text="PENGUIN").click()
                    time.sleep(1)
                    if not d(textContains="FORGET").exists:
                        d(className="android.widget.EditText").set_text("NA@789_wifi@27")
                        d(resourceId="android:id/button1").click()
                        time.sleep(0.5)
                        print self.serial + " OK"
                    self.textout.insert(END, self.serial + " connect wifi OK! \n")
                    self.textout.update()
                except Exception, e:
                    import traceback
                    traceback.print_exc()
                finally:
                    self.raw_cmd('shell', 'input', 'keyevent', '4')
                    time.sleep(0.1)
                    self.raw_cmd('shell', 'input', 'keyevent', '4')
                    time.sleep(0.1)
                    self.raw_cmd('shell', 'input', 'keyevent', '3')
                    time.sleep(0.1)

        except Exception, e:
            import traceback
            traceback.print_exc()
            self.textout.insert(END, self.serial + " connect wifi Fail! \n")
            self.textout.update()

    def push_res(self):
        try:
            serial = [self.serial]
            if tkinter.messagebox.askokcancel('提示', 'push到所有设备sdcard点<是>,<否>仅仅push到当前设备:' + self.serial):
                serial = self.getAdb2()
            else:
                pass
            res = dl.askstring('PUSH文件到手机sdcard', '输入要PUSH的文件', initialvalue='')
            for i in xrange(0, len(serial)):
                self.serial = serial[i]
                self.raw_cmd('push', res, '/sdcard/')
                self.textout.insert(END, "PUSH文件到:" + self.serial + " OK! \n")
                self.textout.update()
        except UnicodeEncodeError, e:
            # import traceback
            # traceback.print_exc()
            tkinter.messagebox.showinfo(title="提示框",
                                        message="不能包含中文！\n")
        except Exception, e:
            import traceback
            traceback.print_exc()
            tkinter.messagebox.showinfo(title="提示框",
                                        message="出错了！\n")

    def net_flow_tool(self):
        self.emmc_start = {}
        st = datetime.datetime.now()
        getp = self.shell_cmd('cat /proc/net/dev')
        if (len(getp) > 0) and ('No such file' not in getp):
            line = getp.strip().split("\n")
            for i in line:
                if 'wlan0:' in i:
                    wlan_r = '%.2f' % (float(i.split(":")[1].strip().split()[0]) / 1024 / 1024)
                    wlan_x = '%.2f' % (float(i.split(":")[1].strip().split()[8]) / 1024 / 1024)
                    self.textout.insert(END, "wlan0 接受数据：" + str(wlan_r) + " M \n")
                    self.textout.insert(END, "wlan0 发送数据：" + str(wlan_x) + " M \n")
                    self.textout.update()
                elif 'rmnet_data0:' in i:
                    net_r = '%.2f' % (float(i.split(":")[1].strip().split()[0]) / 1024 / 1024)
                    net_x = '%.2f' % (float(i.split(":")[1].strip().split()[8]) / 1024 / 1024)
                    self.textout.insert(END, "移动数据接受：" + str(net_r) + " M \n")
                    self.textout.insert(END, "移动数据发送：" + str(net_x) + " M \n")
                    self.textout.update()

    def emmc_start_tool(self):
        self.emmc_start = {}
        st = datetime.datetime.now()
        getp = self.shell_cmd('cat /proc/diskstats | grep -w mmcblk0')
        if "mmcblk0" in getp:
            getp = getp.split("mmcblk0")[1].strip().split()[6]
            self.emmc_start[st] = float(getp)
            self.textout.insert(END,
                                "EMMC 起始数据：" + str(datetime.datetime.now().strftime("%m/%d-%H:%M:%S")) + " < " + str(
                                    getp) + " >\n")
            self.textout.update()

    def emmc_end_tool(self):
        try:
            st = datetime.datetime.now()
            getp = self.shell_cmd('cat /proc/diskstats | grep -w mmcblk0')
            if "mmcblk0" in getp:
                getp = getp.split("mmcblk0")[1].strip().split()[6]
                self.emmc_end[st] = float(getp)
            if len(self.emmc_start) == 1 and len(self.emmc_end) == 1:
                del_time = (self.emmc_end.keys()[0] - self.emmc_start.keys()[0]).total_seconds()
                del_data = self.emmc_end.get(self.emmc_end.keys()[0]) - self.emmc_start.get(self.emmc_start.keys()[0])
                del_data_per_min = del_data * 512 / 1024 / 1024 / (del_time / 60)
                self.textout.insert(END, "EMMC 此刻数据：" + str(
                    datetime.datetime.now().strftime("%m/%d-%H:%M:%S")) + " < " + str(
                    getp) + " > \n")
                self.textout.insert(END, "EMMC 每分钟写入：" + str('%.2f' % del_data_per_min) + " M \n")
                self.textout.update()
        except Exception, e:
            pass
        finally:
            self.emmc_end = {}

    def emmc_tool(self):
        try:
            import schedule
            import time
            # schedule.every(10).minutes.do(job)
            schedule.every().hour.do(self.schedule_job)
            # schedule.every().day.at("10:30").do(job)
            # schedule.every(5).to(10).days.do(job)
            # schedule.every().monday.do(job)
            # schedule.every().wednesday.at("13:15").do(job)
            if self.job_plan:
                self.job_plan = not self.job_plan

            while self.job_plan:
                schedule.run_pending()
                time.sleep(1)
            self.textout.insert(END, "EMMC OK! \n")
            self.textout.update()
        except UnicodeEncodeError, e:
            # import traceback
            # traceback.print_exc()
            tkinter.messagebox.showinfo(title="提示框",
                                        message="不能包含中文！\n")
        except Exception, e:
            import traceback
            traceback.print_exc()
            tkinter.messagebox.showinfo(title="提示框",
                                        message="出错了！\n")

    def command_shell(self, serial):
        res = dl.askstring('执行命令', '输入如install,pull,push,ls,rm...', initialvalue='')
        if len(res) >= 2:
            if len(serial) > 1:
                if tkinter.messagebox.askokcancel('提示', '所有设备执行点<是>,<否>仅仅执行当前设备:' + self.serial):
                    pass
                else:
                    serial = [self.serial]
            for i in xrange(0, len(serial)):
                cmd = res.split()
                # out = self.raw_cmd('shell', res)
                if res.strip().split()[0] == "install":
                    cmds = ['adb'] + ['-s'] + [serial[i]] + cmd
                else:
                    cmds = ['adb'] + ['-s'] + [serial[i]] + ['shell'] + cmd
                p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out = p.communicate()[0]
                self.textout.insert(1.0, '-' * 52 + '\n')
                self.textout.insert(1.0, 'adb -s ' + serial[i] + ' ' + str(cmd) + '\n')
                self.textout.insert(1.0, out + '\n')
                self.textout.insert(1.0, '-' * 52 + '\n')
                self.textout.update()

    def clear_textout(self, event):
        self.textout.delete("1.0", END)

    def adb_log(self):
        out = self.raw_cmd('shell', 'logcat', '-d')
        self.textout.insert(1.0, 'adb -s ' + self.serial + ' shell logcat -d \n')
        self.textout.insert(1.0, '-' * 70 + '\n')
        self.textout.insert(1.0, out)
        self.textout.insert(1.0, '-' * 70 + '\n')
        self.textout.update()

    def adb_mode(self, event):
        content = self.textout.get(1.0, END).lower()

        cmd = content.split()
        if content.strip().split()[0] == "install":
            cmds = ['adb'] + ['-s'] + [self.serial] + cmd
        else:
            cmds = ['adb'] + ['-s'] + [self.serial] + ['shell'] + cmd

        p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = p.communicate()[0]
        self.textout.insert(1.0, '-' * 52 + '\n')
        self.textout.insert(1.0, 'adb -s ' + self.serial + ' ' + str(content) + '\n')
        self.textout.insert(1.0, out + '\n')
        self.textout.insert(1.0, '-' * 52 + '\n')
        self.textout.update()


if __name__ == "__main__":
    test = GFXTest()
    test.gettk()

    # test.travelApp("com.android.settings")
    # test.grantPermission("com.myos.camera")
    # test.platformRun2()
    # test.travel2("com.qiku.smartkey")
    # test.recordatx()
