from uiautomator import Device
from uiautomator2 import DEBUG



d=Device()
try:
    print d.info
except Exception,e:
    print d.info
finally:
    count = d(resourceId="android:id/icon").count
    for i in xrange(0,count):
        print d(resourceId="android:id/icon")[i].bounds

