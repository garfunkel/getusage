#!/usr/bin/env python

from distutils.core import setup
from glob import glob
from sys import platform

packageName = "getusage"
packageVersion = "1.9"
packageAuthor = "Simon Allen"
authorEmail = "its.simon.a@gmail.com"
URL = "http://www.simonallen.org"
licenseInfo = "GNU General Public License (GPL)"
desc = "GetUsage allows you to check your Telstra Bigpond internet quota usage."
packageDir = {'': 'src'}

def setupLinux():
	setup(name = packageName, version = packageVersion, author = packageAuthor,
		author_email = authorEmail, url = URL, license = licenseInfo, description = desc,
		package_dir = packageDir, scripts = ["src/getusage.py"],
		data_files = [("/usr/share/applications", glob(r"usr/share/applications/*")),
			("/usr/share/menu", glob(r"usr/share/menu/*")),
			("/usr/share/pixmaps", glob(r"usr/share/pixmaps/*"))])

def setupWin():
	import py2exe

	setup(name = packageName, version = packageVersion, author = packageAuthor,
		author_email = authorEmail, url = URL, license = licenseInfo, description = desc,
		package_dir = packageDir, packages = ["resources"],
		data_files = [("Microsoft.VC90.CRT", glob(r'releases\Windows\MSVC_runtime\*')),
                              ("imageformats", glob(r"C:\Python27\Lib\site-packages\PyQt4\plugins\imageformats/*"))],
		windows = [{"script": "src\getusage.py", "icon_resources": [(1, "releases\Windows\getusage.ico")]},],
		options = {"py2exe": {"includes": ["sip", "PyQt4.QtXml"], "bundle_files": 3, "optimize": 2,
                                      "dll_excludes": ["MSVCP90.dll"]}})

if platform == "linux2":
	setupLinux()

else:
	setupWin()
	
