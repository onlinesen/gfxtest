#!/usr/bin/end python
# -*- coding: utf-8 -*-
from uiautomator import Device
from uiautomator2 import DEBUG
from PIL import Image
import sys
import time,subprocess


try:
    cmd = ('adb  forward tcp:9008 tcp:9008')
    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.Popen(['adb', '-s', '586609d3', 'shell', "am", "instrument", "-w",
                      "com.tinno.uiautomator.test/android.support.test.runner.AndroidJUnitRunner"],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   # cmds = 'adb -s ' + '586609d3' + ' shell am start -W com.tinno.uiautomator/.MainActivity'
    #subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    d = Device()
    print d.info
    # subprocess.Popen(['adb', '-s', '586609d3', 'shell', 'input', 'keyevent', '4'],
    #                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # time.sleep(1)
    d(text="Wiko features").click()
    time.sleep(1)

    pass
except Exception,e:
    print d.info
finally:
    print d.dump("test.xml")
    d.screenshot("wiko.png")
    img = Image.open("wiko.png")
    #count = d(resourceId="android:id/icon").count
    count = d(className="android.widget.LinearLayout").count
    for j in xrange(0,2):
        for i in xrange(0,count):
            b = d(className="android.widget.LinearLayout")[i].bounds
            box = [b['left'],b['top'],b['right'],b['bottom']]
            print box
            img1 = img.crop(box)
            name= d(className="android.widget.LinearLayout")[i].child(resourceId="android:id/title").text
            name = name.replace(" ","")
            #name = d(resourceId = "android:id/title")
            reload(sys)
            sys.setdefaultencoding('utf8')
            img1.save("pic/wiko_settings_8_Sound_"+str(name) + ".720x1512.png")






