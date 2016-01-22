#!/usr/bin/python2
#-*- coding: utf-8 -*-

"""
Copyright 2010 - 2011 Simon Allen <its.simon.a@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import urllib, urllib2
from PyQt4 import QtCore, QtGui, QtSvg
import time, os, sys, re
from datetime import datetime
from math import ceil
from ctypes import cdll, byref, create_string_buffer

GETUSAGE_VERSION = "1.9"

if sys.platform == "linux2":
	GETUSAGE_ICON = "/usr/share/pixmaps/getusage.svg"

elif sys.platform == "win32":
	from resources import resources
	
	GETUSAGE_ICON = ":/getusage.svg"

# Sets the process name to something other than 'python'.
def setProcName(newName):
	libc = cdll.LoadLibrary('libc.so.6')
	buff = create_string_buffer(len(newName) + 1)
	buff.value = newName
	libc.prctl(15, byref(buff), 0, 0, 0)

# Checks internet quota usage.
class UsageChecker(QtCore.QThread):
	checkComplete = QtCore.pyqtSignal()
	loginPageURL = "https://signon.bigpond.com/login"
	usagePageURL = "https://usagemeter.bigpond.com/daily.do"
	USAGE_DAY_RE = re.compile(ur'<tr class="((odd)|(even))Volume">.+?<!-- date column -->.+?<th scope="row" class="a_left">(?P<date>\d{2} [A-Za-z]{3} \d{4,})</th>.+?<td>((?P<downloaded>\d+(\.\d+)?)|-)?</td>.+?<td>((?P<uploaded>\d+(\.\d+)?)|-)?</td>.+?<td><b>((?P<total>\d+(\.\d+)?)|-)?</b></td>.+?<td>((?P<additional>\d+(\.\d+)?)|-)?</td>.+?<td>((?P<slowed>\d+(\.\d+)?)|-)?</td>.+?<td>((?P<unmetered>\d+(\.\d+)?)|-)?</td>.+?<td>((?P<unrated>\d+(\.\d+)?)|-)?</td>.+?</tr>', re.DOTALL | re.MULTILINE)
	USAGE_ACCOUNT_RE = re.compile(ur'<!-- account name -->\s*<tr>\s*<th>Account name</th>\s*<td>\s*(?P<name>.*?)\s*</td>\s*</tr>.*?<!-- ban -->\s*<tr>\s*<th> Bigpond account number</th>\s*<td>\s*(?P<num>.*?)\s*</td>\s*</tr>.*?<!-- current plan -->\s*<tr>\s*<th>Current plan</th>\s*<td>\s*(?P<plan>.*?)\s*</td>\s*</tr>.*?<!-- monthly plan allowance -->\s*<tr>\s*<th>Monthly plan allowance</th>\s*<td>\s*(?P<allowance>.*?)<a .*?</td>\s*</tr>.*?<!-- account usage -->\s*<tr>\s*<th>Account usage status</th>\s*<td>\s*(?P<status>.*?)\s*</td>\s*</tr>', re.DOTALL | re.MULTILINE)

	def __init__(self, username, password, refreshInterval):
		QtCore.QThread.__init__(self)
		
		self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())

		self.opener.addheaders = [('Referer', 'https://my.bigpond.com/mybigpond/myaccount/myusage/daily/default.do?rememberMe=true')]

		urllib2.install_opener(self.opener)

		self.username = None
		self.password = None
		self.refreshInterval = None
		self.params = None
		self.currentUsage = None
		self.quota = None
		self.balance = None
		self.cycleStart = None
		self.cycleEnd = None
		self.daysInCycle = None
		self.calculated = False
		self.usage = {}

		self.setSettings(username, password, refreshInterval)

	# Initialise UsageChecker fields. Called each time usage is calculated.
	def init(self):
		self.currentUsage = None
		self.quota = None
		self.balance = None
		self.cycleStart = None
		self.cycleEnd = None
		self.daysInCycle = None
		self.calculated = False
		self.usage = {}

	# Sets ISP login details and refresh interval.
	def setSettings(self, username, password, refreshInterval):
		self.username = username
		self.password = password
		self.refreshInterval = refreshInterval
		
		self.params = urllib.urlencode({"username": self.username, "password": self.password})

	# Loops, checking current usage continuously after interval.
	def run(self):
		try:
			while True:
				self.calculate()

				time.sleep(self.refreshInterval * 60)
		
		except Exception as e:
			print >> sys.stderr, "ERROR: %s" % e
	
	# Calculates current usage and fills in attributes.
	def calculate(self):
		self.init()

		self.opener.open(self.loginPageURL, self.params)

		usagePage = self.opener.open(self.usagePageURL)

		text = usagePage.read()

		usagePage.close()

		self.currentUsage = {}
		self.cycleStart, self.cycleEnd = None, None

		for match in self.USAGE_DAY_RE.finditer(text):
			usageDict = match.groupdict()

			date = datetime.strptime(usageDict['date'], "%d %b %Y")

			if self.cycleStart is None:
				self.cycleStart = date

			self.cycleEnd = date
			self.usage[date] = {}

			for key in usageDict.keys():
				if key == 'date':
					continue

				if key not in self.currentUsage:
					self.currentUsage[key] = 0

				if usageDict[key] is None:
					self.usage[date][key] = 0

				else:
					self.usage[date][key] = float(usageDict[key])
					self.currentUsage[key] += self.usage[date][key]

		match = self.USAGE_ACCOUNT_RE.search(text)

		accountInfoDict = match.groupdict()

		self.quota = float(accountInfoDict['allowance'][: accountInfoDict['allowance'].find('GB')]) * 1000

		cycleDelta = self.cycleEnd - self.cycleStart		
		currentDelta = datetime.now() - self.cycleStart
		
		self.daysInCycle = cycleDelta.days
		self.balance = self.currentUsage['total'] / max(1, currentDelta.total_seconds() * 1000000) * (cycleDelta.total_seconds() * 1000000)

		self.calculated = True
		self.checkComplete.emit()

# Dialog for checking ISP quota usage.
class GetUsage(QtGui.QDialog):
	# Setup attributes and tray icon.
	def __init__(self, parent = None):
		QtGui.QDialog.__init__(self, parent)
		
		self.usageChecker = None
		self.dailyUsage = None
		self.about = None
		self.preferences = Preferences(self)
		self.quotaProgress = QtGui.QProgressBar(self)
		self.periodLabel = QtGui.QLabel(self)
		self.currentUsageLabel = QtGui.QLabel(self)
		self.quotaLabel = QtGui.QLabel(self)
		self.currentUsagePercentLabel = QtGui.QLabel(self)
		self.predictedBalanceLabel = QtGui.QLabel(self)
		self.trayIcon = QtGui.QSystemTrayIcon(QtGui.QIcon(GETUSAGE_ICON), QtGui.qApp)
	
		self.setFixedSize(400, 210)
		self.center()
		self.setWindowTitle("GetUsage")
		self.setWindowIcon(QtGui.QIcon(GETUSAGE_ICON))
	
		statsWidget = QtGui.QWidget(self)	
		layout = QtGui.QVBoxLayout()
		statsGrid = QtGui.QGridLayout(statsWidget)
		self.trayMenu = QtGui.QMenu()
		
		self.trayMenu.addAction(QtGui.QIcon.fromTheme("view-refresh", QtGui.QIcon(":/trolltech/styles/commonstyle/images/refresh-32.png" 
)), "Refresh")
		self.trayMenu.addAction(QtGui.QIcon.fromTheme("modem", QtGui.QIcon(":/trolltech/styles/commonstyle/images/networkdrive-32.png" 
)), "Daily Usage")
		self.trayMenu.addAction(QtGui.QIcon.fromTheme("preferences-other", QtGui.QIcon(":/trolltech/styles/commonstyle/images/computer-32.png" 
)), "Preferences")
		self.trayMenu.addAction(QtGui.QIcon.fromTheme("help-about", QtGui.QIcon(":/trolltech/styles/commonstyle/images/standardbutton-help-32.png" 
)), "About")
		self.trayMenu.addAction(QtGui.QIcon.fromTheme("application-exit", QtGui.QIcon(":/trolltech/styles/commonstyle/images/standardbutton-close-32.png" 
)), "Quit")
		
		self.trayIcon.setContextMenu(self.trayMenu)
		self.trayIcon.show()
		
		statsGrid.addWidget(QtGui.QLabel("Billing period:"), 0, 0)
		statsGrid.addWidget(self.periodLabel, 0, 1)
		statsGrid.addWidget(QtGui.QLabel("Current usage:"), 1, 0)
		statsGrid.addWidget(self.currentUsageLabel, 1, 1)
		statsGrid.addWidget(QtGui.QLabel("Quota:"), 2, 0)
		statsGrid.addWidget(self.quotaLabel, 2, 1)
		statsGrid.addWidget(QtGui.QLabel("Percentage used:"), 3, 0)
		statsGrid.addWidget(self.currentUsagePercentLabel, 3, 1)
		statsGrid.addWidget(QtGui.QLabel("Predicted balance:"), 4, 0)
		statsGrid.addWidget(self.predictedBalanceLabel, 4, 1)
		
		layout.addWidget(statsWidget)
		layout.addWidget(self.quotaProgress)
		
		self.setLayout(layout)
		
		self.quotaProgress.setTextVisible(True)
		
		self.trayMenu.triggered.connect(self.trayIconEvent)
		self.trayIcon.activated.connect(self.trayIconClicked)
		self.trayIcon.messageClicked.connect(self.show)
		self.preferences.accepted.connect(self.refreshUsageChecker)

		self.refreshUsageChecker()
	
	# Centre window on screen.
	def center(self):
		screen = QtGui.QDesktopWidget().screenGeometry()
		size =  self.geometry()
		self.move((screen.width() - size.width()) / 2, (screen.height() - size.height()) / 2)
	
	# Refresh usage information fields.
	def refreshUsageChecker(self):
		# If required info not available, prompt the user to enter them.
		if self.preferences.username.text().isEmpty() or self.preferences.password.text().isEmpty() \
		   or self.preferences.refreshInterval.value() == 0:
			self.preferences.show()
		
			return
		
		self.setWindowTitle("GetUsage")
		
		self.periodLabel.setText("<i>Loading...</i>")
		self.currentUsageLabel.setText("<i>Loading...</i>")
		self.quotaLabel.setText("<i>Loading...</i>")
		self.currentUsagePercentLabel.setText("<i>Loading...</i>")
		self.predictedBalanceLabel.setText("<i>Loading...</i>")

		if sys.platform == "win32":
			self.trayIcon.setToolTip("Usage: Loading...")

		else:
			self.trayIcon.setToolTip("Usage: <i>Loading...</i>")

		self.quotaProgress.setMinimum(0)
		self.quotaProgress.setMaximum(0)

		# Terminate the current check, ready for a refresh.
		if self.usageChecker != None:
			self.usageChecker.calculated = False
			self.usageChecker.terminate()
			self.usageChecker.wait()
	
		# Begin update.
		if (self.dailyUsage):
			self.dailyUsage.updateUsage(self.usageChecker)
	
		self.usageChecker = UsageChecker(self.preferences.username.text(),
						 self.preferences.password.text(),
						 self.preferences.refreshInterval.value())
		
		self.usageChecker.checkComplete.connect(self.updateUsage)
				 
		self.usageChecker.start()
	
	# Show daily usage information dialog.
	def showDailyUsage(self):
		if self.dailyUsage == None:
			self.dailyUsage = DailyUsage(self)
			
		self.dailyUsage.show()
		
		if self.usageChecker != None:
			self.dailyUsage.updateUsage(self.usageChecker)
	
	# Process tray icon events.
	def trayIconEvent(self, action):
		if action.text() == "Refresh":
			self.refreshUsageChecker()
			
		elif action.text() == "Daily Usage":
			self.showDailyUsage()
	
		elif action.text() == "Preferences":
			self.preferences.show()
			
		elif action.text() == "About":
			self.showAbout()
	
		elif action.text() == "Quit":
			QtGui.qApp.quit()
	
	# Process hiding/showing window when tray icon clicked.
	def trayIconClicked(self, reason):
		if reason == QtGui.QSystemTrayIcon.Trigger:
			self.setVisible(not self.isVisible())
	
	# Update usage information.
	def updateUsage(self):		
		billingPeriod = self.usageChecker.cycleStart.strftime("%d %b %Y") + " - " + \
				self.usageChecker.cycleEnd.strftime("%d %b %Y")
		
		self.quotaProgress.setMinimum(0)
		self.quotaProgress.setMaximum(100)
		
		self.periodLabel.setText(billingPeriod)
		self.currentUsageLabel.setText(str(self.usageChecker.currentUsage['total']) + "MB")
		self.quotaLabel.setText(str(self.usageChecker.quota) + "MB")
		self.currentUsagePercentLabel.setText(str(round(self.usageChecker.currentUsage['total']
							  / self.usageChecker.quota * 100, 4, )) + "%")
			
		balanceColour = "green"
			
		if self.usageChecker.balance > self.usageChecker.quota:
			balanceColour = "red"
		
		self.predictedBalanceLabel.setText("<font color=" + balanceColour +  ">"
						+ str(round(self.usageChecker.balance, 1)) + "MB" + "</font>")
		
		self.setWindowTitle("GetUsage: " + str(round(self.usageChecker.currentUsage['total']
						       / self.usageChecker.quota * 100, 4)) + "%")
		
		self.quotaProgress.setFormat(str(round(self.usageChecker.currentUsage['total']
						       / self.usageChecker.quota * 100, 4)) + "%")
		
		self.quotaProgress.setValue(min(100, self.usageChecker.currentUsage['total'] / self.usageChecker.quota * 100))
		
		self.trayIcon.setToolTip("Usage: " + str(round(self.usageChecker.currentUsage['total']
		                         / self.usageChecker.quota * 100, 4)) + "%")

		if sys.platform == "linux2":
			os.system("notify-send -t 10000 --hint=int:transient:1 \"GetUsage\" \"Usage is at "
			          + str(round(self.usageChecker.currentUsage['total']
			          / self.usageChecker.quota * 100, 4)) + "%\" -i " + GETUSAGE_ICON)

		else:
			self.trayIcon.showMessage("GetUsage", "Usage is at "
			                          + str(round(self.usageChecker.currentUsage['total']
			                          / self.usageChecker.quota * 100, 4)) + "%")
		
		if self.dailyUsage != None:
			self.dailyUsage.updateUsage(self.usageChecker)
		
	# Show about dialog box.
	def showAbout(self):
		if self.about == None:
			self.about = About(self)
			
		self.about.show()
	
	# When closing program, simply minimise it to the tray instead.
	def closeEvent(self, event):
		self.hide()
		self.trayIcon.show()
		event.ignore()

# Dialog used to show daily usage information.
class DailyUsage(QtGui.QDialog):
	def __init__(self, parent = None):
		QtGui.QDialog.__init__(self, parent)
		
		self.usageChecker = None
		
		self.setWindowTitle("Daily Usage")
		self.setMinimumSize(800, 400)
		self.setWindowIcon(QtGui.QIcon(GETUSAGE_ICON))
	
	# Update daily usage.
	def updateUsage(self, usageChecker):
		self.usageChecker = usageChecker
		
		self.repaint()

	# Process paint events, drawing the graph on the screen.
	def paintEvent(self, event):
		QtGui.QDialog.paintEvent(self, event)
	
		painter = QtGui.QPainter(self)
		painter.setPen(QtCore.Qt.black)
	
		if not self.usageChecker or not self.usageChecker.calculated:
			painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Loading...")
			
			return
		
		columnWidth = (self.rect().width() - 125) / self.usageChecker.daysInCycle
		
		painter.drawLine(100, 25, 100, self.rect().height() - 55)
		painter.drawLine(95, self.rect().height() - 60, self.rect().width() - 25,
				 self.rect().height() - 60)
		
		x = 99 + columnWidth
		
		for day in range(self.usageChecker.daysInCycle):
			painter.drawLine(x + 1, self.rect().height() - 55, x + 1, self.rect().height() - 60)
			
			x = x + columnWidth
		
		x = 118
		start = self.usageChecker.cycleStart
		end = self.usageChecker.cycleEnd
		maxUsage = max([self.usageChecker.usage[date]['total'] for date in self.usageChecker.usage])
		dayIndex = 0
		maxColumnHeight = self.rect().height() - 100
		unitY = self.rect().height() - 60
		
		painter.drawText(25, unitY + 5, "0MB")
		
		for i in range(1, 11):
			unitY = unitY - ((self.rect().height() - 95) / 10)
		
			painter.drawText(25, unitY + 5, str(int(maxUsage / 10.0 * i)) + "MB")
			painter.drawLine(95, unitY, self.rect().width() - 25, unitY)
		
		while start != end:
			font = QtGui.QFont()
			painter.setFont(font)
			
			painter.drawText(x - 15, self.rect().height() - 40, start.strftime("%d"))
			
			font = QtGui.QFont()
			font.setPointSize(8)

			painter.setFont(font)
			painter.drawText(x - 16, self.rect().height() - 25, start.strftime("%b"))
			
			try:
				todayTotalRate = maxUsage / float(self.usageChecker.usage[start]['total'])
			
				height = maxColumnHeight / todayTotalRate
				painter.fillRect(x - 18, (self.rect().height() - 60 - height),
						 columnWidth, ceil(height), QtGui.QColor("#6DC4F2"))
				painter.drawRect(x - 18, (self.rect().height() - 60 - height),
						 columnWidth, ceil(height))

			except ZeroDivisionError:
				todayTotalRate = 0
			
			x = x + columnWidth
			
			try:
				start = start.replace(day = start.day + 1)
			
			except ValueError:
				try:
					start = start.replace(day = 1)
					start = start.replace(month = start.month + 1)

				except ValueError:
					start = start.replace(month = 1)
					start = start.replace(year = start.year + 1)
			
			dayIndex = dayIndex + 1

# Preferences dialog. Stores ISP login details and refresh interval. 
class Preferences(QtGui.QDialog):
	def __init__(self, parent = None):
		QtGui.QDialog.__init__(self, parent)
		
		self.username = QtGui.QLineEdit(self)
		self.password = QtGui.QLineEdit(self)
		self.refreshInterval = QtGui.QSpinBox(self)
		self.settings = QtCore.QSettings("GetUsage", "GetUsage", self)
		
		prefsWidget = QtGui.QWidget(self)
		buttonWidget = QtGui.QWidget(self)
		
		self.setWindowTitle("Preferences")
		self.setFixedSize(400, 200)
		self.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
		self.setWindowIcon(QtGui.QIcon(GETUSAGE_ICON))
		
		prefsWidget.setLayout(QtGui.QGridLayout())
		buttonWidget.setLayout(QtGui.QHBoxLayout())
		
		buttonBox = QtGui.QDialogButtonBox(self)
		buttonBox.setOrientation(QtCore.Qt.Horizontal)
		buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Ok)
		
		self.password.setEchoMode(QtGui.QLineEdit.Password)
		
		self.refreshInterval.setMinimum(0)
		self.refreshInterval.setMaximum(10080)
		
		self.setLayout(QtGui.QVBoxLayout())
		self.layout().addWidget(prefsWidget)
		self.layout().addWidget(buttonBox)
		
		prefsWidget.layout().addWidget(QtGui.QLabel("Username:", self), 0, 0)
		prefsWidget.layout().addWidget(QtGui.QLabel("Password:", self), 1, 0)
		prefsWidget.layout().addWidget(QtGui.QLabel("Refresh interval\n(minutes):", self))
		prefsWidget.layout().addWidget(self.username, 0, 1)
		prefsWidget.layout().addWidget(self.password, 1, 1)
		prefsWidget.layout().addWidget(self.refreshInterval, 2, 1)
		
		self.readSettings()
		
		self.finished.connect(self.readSettings)
		buttonBox.accepted.connect(self.writeSettings)
		buttonBox.accepted.connect(self.accept)
		
	# Read settings from file.
	def readSettings(self):
		self.username.setText(self.settings.value("username", str()).toString())
		self.password.setText(self.settings.value("password", str()).toString())
		self.refreshInterval.setValue(self.settings.value("refreshInterval", 0).toInt()[0])
		
	# Write settings to file.
	def writeSettings(self):
		self.settings.setValue("username", self.username.text())
		self.settings.setValue("password", self.password.text())
		self.settings.setValue("refreshInterval", self.refreshInterval.value())
	
# About dialog box.
class About(QtGui.QDialog):
	def __init__(self, parent = None):
		QtGui.QDialog.__init__(self, parent)

		self.setWindowTitle("About")		
		self.setFixedSize(300, 220)
		self.setWindowIcon(QtGui.QIcon(GETUSAGE_ICON))

		self.setLayout(QtGui.QVBoxLayout())
		
		buttonBox = QtGui.QDialogButtonBox(self)
		buttonBox.setOrientation(QtCore.Qt.Horizontal)
		buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Ok)
		
		logoLabel = QtGui.QLabel(self)
		renderer = QtSvg.QSvgRenderer()
		renderer.load(GETUSAGE_ICON)
		self.image = QtGui.QPixmap(71, 91)
		self.image.fill(QtCore.Qt.transparent)
		painter = QtGui.QPainter(self.image)
		renderer.render(painter)
		logoLabel.setPixmap(self.image)
		logoLabel.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
		
		self.layout().addWidget(QtGui.QLabel("<center><h2>GetUsage " + GETUSAGE_VERSION + "</h2></center>", self))
		self.layout().addWidget(logoLabel)
		self.layout().addWidget(QtGui.QLabel("<center>Copyright 2010 - 2011 Simon Allen</center>", self))
		self.layout().addWidget(buttonBox)
		
		buttonBox.accepted.connect(self.accept)
		
def main():
	app = QtGui.QApplication(sys.argv)

	# Stop program quitting when closing about/preferences/daily usage dialogs.
	app.setQuitOnLastWindowClosed(False)

	getUsage = GetUsage()
	
	getUsage.show()
	
	os._exit(app.exec_())

if __name__ == "__main__":
	if sys.platform == "linux2":
		setProcName('getusage')

	elif sys.platform == "win32":
		from ctypes import windll
                
		try:
			windll.shell32.SetCurrentProcessExplicitAppUserModelID('SimonAllen.GetUsage.' + GETUSAGE_VERSION)

			# Catching this exception will fix execution on wine as the above method is not defined in wine ATM.
		except AttributeError:
			pass

	main()

