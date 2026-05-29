# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.9.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QPlainTextEdit, QProgressBar,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QStatusBar, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1107, 866)
        icon = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.VideoDisplay))
        MainWindow.setWindowIcon(icon)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_2 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_2.setSpacing(6)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(10, 8, 10, 6)
        self.topBarLayout = QHBoxLayout()
        self.topBarLayout.setObjectName(u"topBarLayout")
        self.hardwareStatusLabel = QLabel(self.centralwidget)
        self.hardwareStatusLabel.setObjectName(u"hardwareStatusLabel")
        font = QFont()
        font.setFamilies([u"Tuffy"])
        font.setPointSize(11)
        self.hardwareStatusLabel.setFont(font)

        self.topBarLayout.addWidget(self.hardwareStatusLabel)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.topBarLayout.addItem(self.horizontalSpacer_2)

        self.settingsButton = QPushButton(self.centralwidget)
        self.settingsButton.setObjectName(u"settingsButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.settingsButton.sizePolicy().hasHeightForWidth())
        self.settingsButton.setSizePolicy(sizePolicy)
        font1 = QFont()
        font1.setFamilies([u"Tuffy"])
        self.settingsButton.setFont(font1)
        icon1 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.SystemLockScreen))
        self.settingsButton.setIcon(icon1)
        self.settingsButton.setIconSize(QSize(20, 20))

        self.topBarLayout.addWidget(self.settingsButton)


        self.verticalLayout_2.addLayout(self.topBarLayout)

        self.mainVSplitter = QSplitter(self.centralwidget)
        self.mainVSplitter.setObjectName(u"mainVSplitter")
        self.mainVSplitter.setOrientation(Qt.Orientation.Vertical)
        self.topAreaWidget = QWidget(self.mainVSplitter)
        self.topAreaWidget.setObjectName(u"topAreaWidget")
        self.horizontalLayout_2 = QHBoxLayout(self.topAreaWidget)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 5)
        self.mainHSplitter = QSplitter(self.topAreaWidget)
        self.mainHSplitter.setObjectName(u"mainHSplitter")
        self.mainHSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.leftPaneWidget = QWidget(self.mainHSplitter)
        self.leftPaneWidget.setObjectName(u"leftPaneWidget")
        self.verticalLayout_3 = QVBoxLayout(self.leftPaneWidget)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(0, 0, 5, 0)
        self.filesHeaderLayout = QHBoxLayout()
        self.filesHeaderLayout.setObjectName(u"filesHeaderLayout")
        self.browseFilesButton = QPushButton(self.leftPaneWidget)
        self.browseFilesButton.setObjectName(u"browseFilesButton")
        self.browseFilesButton.setFont(font1)
        icon2 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.DocumentOpen))
        self.browseFilesButton.setIcon(icon2)
        self.browseFilesButton.setIconSize(QSize(24, 24))

        self.filesHeaderLayout.addWidget(self.browseFilesButton)

        self.clearFilesButton = QPushButton(self.leftPaneWidget)
        self.clearFilesButton.setObjectName(u"clearFilesButton")
        font2 = QFont()
        font2.setFamilies([u".Apple Color Emoji UI"])
        self.clearFilesButton.setFont(font2)
        icon3 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.EditDelete))
        self.clearFilesButton.setIcon(icon3)
        self.clearFilesButton.setIconSize(QSize(24, 24))

        self.filesHeaderLayout.addWidget(self.clearFilesButton)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.filesHeaderLayout.addItem(self.horizontalSpacer_3)


        self.verticalLayout_3.addLayout(self.filesHeaderLayout)

        self.filesMetaSplitter = QSplitter(self.leftPaneWidget)
        self.filesMetaSplitter.setObjectName(u"filesMetaSplitter")
        self.filesMetaSplitter.setOrientation(Qt.Orientation.Vertical)
        self.filesListWidget = QListWidget(self.filesMetaSplitter)
        self.filesListWidget.setObjectName(u"filesListWidget")
        self.filesListWidget.setFrameShape(QFrame.Shape.WinPanel)
        self.filesListWidget.setFrameShadow(QFrame.Shadow.Sunken)
        self.filesListWidget.setLineWidth(3)
        self.filesListWidget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.filesMetaSplitter.addWidget(self.filesListWidget)
        self.metadataGroupBox = QGroupBox(self.filesMetaSplitter)
        self.metadataGroupBox.setObjectName(u"metadataGroupBox")
        self.metadataGroupBox.setFont(font1)
        self.metadataGroupBox.setFlat(False)
        self.verticalLayout_4 = QVBoxLayout(self.metadataGroupBox)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.metadataTreeWidget = QTreeWidget(self.metadataGroupBox)
        self.metadataTreeWidget.setObjectName(u"metadataTreeWidget")
        self.metadataTreeWidget.setMouseTracking(False)
        self.metadataTreeWidget.setTabletTracking(False)
        self.metadataTreeWidget.setAlternatingRowColors(True)
        self.metadataTreeWidget.setRootIsDecorated(False)

        self.verticalLayout_4.addWidget(self.metadataTreeWidget)

        self.filesMetaSplitter.addWidget(self.metadataGroupBox)

        self.verticalLayout_3.addWidget(self.filesMetaSplitter)

        self.filesStatusLabel = QLabel(self.leftPaneWidget)
        self.filesStatusLabel.setObjectName(u"filesStatusLabel")
        self.filesStatusLabel.setFont(font1)
        self.filesStatusLabel.setVisible(False)

        self.verticalLayout_3.addWidget(self.filesStatusLabel)

        self.mainHSplitter.addWidget(self.leftPaneWidget)
        self.rightPaneWidget = QWidget(self.mainHSplitter)
        self.rightPaneWidget.setObjectName(u"rightPaneWidget")
        self.verticalLayout = QVBoxLayout(self.rightPaneWidget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(5, 0, 0, 0)
        self.builderTabWidget = QTabWidget(self.rightPaneWidget)
        self.builderTabWidget.setObjectName(u"builderTabWidget")
        self.builderTabWidget.setFont(font1)
        self.templatesTab = QWidget()
        self.templatesTab.setObjectName(u"templatesTab")
        self.verticalLayout_5 = QVBoxLayout(self.templatesTab)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.newTemplateButton = QPushButton(self.templatesTab)
        self.newTemplateButton.setObjectName(u"newTemplateButton")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.newTemplateButton.sizePolicy().hasHeightForWidth())
        self.newTemplateButton.setSizePolicy(sizePolicy1)

        self.horizontalLayout_3.addWidget(self.newTemplateButton)

        self.horizontalSpacer_5 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_3.addItem(self.horizontalSpacer_5)


        self.verticalLayout_5.addLayout(self.horizontalLayout_3)

        self.templatesDetailsSplitter = QSplitter(self.templatesTab)
        self.templatesDetailsSplitter.setObjectName(u"templatesDetailsSplitter")
        self.templatesDetailsSplitter.setOrientation(Qt.Orientation.Vertical)
        self.catTemplateSplitter = QSplitter(self.templatesDetailsSplitter)
        self.catTemplateSplitter.setObjectName(u"catTemplateSplitter")
        self.catTemplateSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.catTemplateSplitter.setHandleWidth(10)
        self.categoriesListWidget = QListWidget(self.catTemplateSplitter)
        self.categoriesListWidget.setObjectName(u"categoriesListWidget")
        self.categoriesListWidget.setMinimumSize(QSize(90, 0))
        font3 = QFont()
        font3.setFamilies([u"Tuffy"])
        font3.setPointSize(14)
        self.categoriesListWidget.setFont(font3)
        self.catTemplateSplitter.addWidget(self.categoriesListWidget)
        self.templatesListWidget = QListWidget(self.catTemplateSplitter)
        self.templatesListWidget.setObjectName(u"templatesListWidget")
        self.templatesListWidget.setFont(font3)
        self.templatesListWidget.setProperty(u"showDropIndicator", True)
        self.templatesListWidget.setDragEnabled(True)
        self.templatesListWidget.setDragDropOverwriteMode(False)
        self.templatesListWidget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.templatesListWidget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.templatesListWidget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.catTemplateSplitter.addWidget(self.templatesListWidget)
        self.templatesDetailsSplitter.addWidget(self.catTemplateSplitter)
        self.templateDetailsGroupBox = QGroupBox(self.templatesDetailsSplitter)
        self.templateDetailsGroupBox.setObjectName(u"templateDetailsGroupBox")
        font4 = QFont()
        font4.setFamilies([u"Tuffy"])
        font4.setStyleStrategy(QFont.PreferAntialias)
        font4.setHintingPreference(QFont.PreferFullHinting)
        self.templateDetailsGroupBox.setFont(font4)
        self.templateDetailsGroupBox.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.templateDetailsGroupBox.setFlat(False)
        self.verticalLayout_6 = QVBoxLayout(self.templateDetailsGroupBox)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.verticalLayout_6.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.verticalLayout_6.setContentsMargins(-1, -1, -1, 12)
        self.templateDescriptionLabel = QLabel(self.templateDetailsGroupBox)
        self.templateDescriptionLabel.setObjectName(u"templateDescriptionLabel")
        self.templateDescriptionLabel.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        self.templateDescriptionLabel.setWordWrap(True)

        self.verticalLayout_6.addWidget(self.templateDescriptionLabel)

        self.templatesDetailsSplitter.addWidget(self.templateDetailsGroupBox)

        self.verticalLayout_5.addWidget(self.templatesDetailsSplitter)

        self.outputGroupBox = QGroupBox(self.templatesTab)
        self.outputGroupBox.setObjectName(u"outputGroupBox")
        self.outputGroupBox.setEnabled(True)
        self.outputGroupBox.setFont(font1)
        self.outputGroupBox.setTabletTracking(False)
        self.outputGroupBox.setAutoFillBackground(False)
        self.outputGroupBox.setFlat(False)
        self.gridLayout = QGridLayout(self.outputGroupBox)
        self.gridLayout.setObjectName(u"gridLayout")
        self.outputFileLabelContainer = QWidget(self.outputGroupBox)
        self.outputFileLabelContainer.setObjectName(u"outputFileLabelContainer")
        self.outputFileLabelContainer.setMinimumSize(QSize(100, 0))
        self.outputFileLabel = QLabel(self.outputFileLabelContainer)
        self.outputFileLabel.setObjectName(u"outputFileLabel")
        self.outputFileLabel.setGeometry(QRect(0, 0, 120, 24))

        self.gridLayout.addWidget(self.outputFileLabelContainer, 0, 0, 1, 1)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.outputPathLineEdit = QLineEdit(self.outputGroupBox)
        self.outputPathLineEdit.setObjectName(u"outputPathLineEdit")

        self.horizontalLayout.addWidget(self.outputPathLineEdit)

        self.browseOutputButton = QPushButton(self.outputGroupBox)
        self.browseOutputButton.setObjectName(u"browseOutputButton")
        self.browseOutputButton.setIcon(icon2)
        self.browseOutputButton.setIconSize(QSize(16, 16))

        self.horizontalLayout.addWidget(self.browseOutputButton)


        self.gridLayout.addLayout(self.horizontalLayout, 0, 1, 1, 2)

        self.formatLabelContainer = QWidget(self.outputGroupBox)
        self.formatLabelContainer.setObjectName(u"formatLabelContainer")
        self.formatLabelContainer.setMinimumSize(QSize(120, 24))
        self.formatLabel = QLabel(self.formatLabelContainer)
        self.formatLabel.setObjectName(u"formatLabel")
        self.formatLabel.setGeometry(QRect(0, 0, 120, 24))

        self.gridLayout.addWidget(self.formatLabelContainer, 1, 0, 1, 1)

        self.outputFormatComboBox = QComboBox(self.outputGroupBox)
        self.outputFormatComboBox.setObjectName(u"outputFormatComboBox")

        self.gridLayout.addWidget(self.outputFormatComboBox, 1, 1, 1, 1)

        self.formatDescriptionLabel = QLabel(self.outputGroupBox)
        self.formatDescriptionLabel.setObjectName(u"formatDescriptionLabel")

        self.gridLayout.addWidget(self.formatDescriptionLabel, 1, 2, 1, 1)


        self.verticalLayout_5.addWidget(self.outputGroupBox)

        self.builderTabWidget.addTab(self.templatesTab, "")
        self.queueTab = QWidget()
        self.queueTab.setObjectName(u"queueTab")
        self.queueLayout = QVBoxLayout(self.queueTab)
        self.queueLayout.setObjectName(u"queueLayout")
        self.queueStatusLabel = QLabel(self.queueTab)
        self.queueStatusLabel.setObjectName(u"queueStatusLabel")

        self.queueLayout.addWidget(self.queueStatusLabel)

        self.queueButtonLayout = QHBoxLayout()
        self.queueButtonLayout.setObjectName(u"queueButtonLayout")
        self.queueClearButton = QPushButton(self.queueTab)
        self.queueClearButton.setObjectName(u"queueClearButton")
        self.queueClearButton.setIcon(icon3)
        self.queueClearButton.setIconSize(QSize(24, 24))

        self.queueButtonLayout.addWidget(self.queueClearButton)

        self.queueButtonSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.queueButtonLayout.addItem(self.queueButtonSpacer)


        self.queueLayout.addLayout(self.queueButtonLayout)

        self.queueTreeWidget = QTreeWidget(self.queueTab)
        self.queueTreeWidget.setObjectName(u"queueTreeWidget")
        self.queueTreeWidget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.queueTreeWidget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self.queueLayout.addWidget(self.queueTreeWidget)

        self.queueButtonLayout_2 = QHBoxLayout()
        self.queueButtonLayout_2.setObjectName(u"queueButtonLayout_2")
        self.queueButtonSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.queueButtonLayout_2.addItem(self.queueButtonSpacer_2)

        self.queueStartButton = QPushButton(self.queueTab)
        self.queueStartButton.setObjectName(u"queueStartButton")

        self.queueButtonLayout_2.addWidget(self.queueStartButton)

        self.queueStopButton = QPushButton(self.queueTab)
        self.queueStopButton.setObjectName(u"queueStopButton")

        self.queueButtonLayout_2.addWidget(self.queueStopButton)


        self.queueLayout.addLayout(self.queueButtonLayout_2)

        self.builderTabWidget.addTab(self.queueTab, "")

        self.verticalLayout.addWidget(self.builderTabWidget)

        self.mainHSplitter.addWidget(self.rightPaneWidget)

        self.horizontalLayout_2.addWidget(self.mainHSplitter)

        self.mainVSplitter.addWidget(self.topAreaWidget)
        self.bottomPreviewWidget = QWidget(self.mainVSplitter)
        self.bottomPreviewWidget.setObjectName(u"bottomPreviewWidget")
        self.verticalLayout_8 = QVBoxLayout(self.bottomPreviewWidget)
        self.verticalLayout_8.setSpacing(0)
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.verticalLayout_8.setContentsMargins(0, 5, 0, 5)
        self.previewTitleLabel = QLabel(self.bottomPreviewWidget)
        self.previewTitleLabel.setObjectName(u"previewTitleLabel")
        self.previewTitleLabel.setFont(font1)

        self.verticalLayout_8.addWidget(self.previewTitleLabel)

        self.commandPreviewTextEdit = QPlainTextEdit(self.bottomPreviewWidget)
        self.commandPreviewTextEdit.setObjectName(u"commandPreviewTextEdit")
        self.commandPreviewTextEdit.setFont(font3)

        self.verticalLayout_8.addWidget(self.commandPreviewTextEdit)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.copyCommandButton = QPushButton(self.bottomPreviewWidget)
        self.copyCommandButton.setObjectName(u"copyCommandButton")
        self.copyCommandButton.setFont(font1)

        self.horizontalLayout_4.addWidget(self.copyCommandButton)

        self.clearCommandButton = QPushButton(self.bottomPreviewWidget)
        self.clearCommandButton.setObjectName(u"clearCommandButton")
        self.clearCommandButton.setFont(font1)

        self.horizontalLayout_4.addWidget(self.clearCommandButton)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_4.addItem(self.horizontalSpacer)

        self.visualEditorButton = QPushButton(self.bottomPreviewWidget)
        self.visualEditorButton.setObjectName(u"visualEditorButton")
        sizePolicy1.setHeightForWidth(self.visualEditorButton.sizePolicy().hasHeightForWidth())
        self.visualEditorButton.setSizePolicy(sizePolicy1)

        self.horizontalLayout_4.addWidget(self.visualEditorButton)


        self.verticalLayout_8.addLayout(self.horizontalLayout_4)

        self.mainVSplitter.addWidget(self.bottomPreviewWidget)

        self.verticalLayout_2.addWidget(self.mainVSplitter)

        MainWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        self.statusbar.setMinimumSize(QSize(0, 32))
        self.statusbar.setSizeGripEnabled(False)
        self.statusBarContentWidget = QWidget()
        self.statusBarContentWidget.setObjectName(u"statusBarContentWidget")
        self.statusBarContentLayout = QHBoxLayout(self.statusBarContentWidget)
        self.statusBarContentLayout.setSpacing(8)
        self.statusBarContentLayout.setObjectName(u"statusBarContentLayout")
        self.statusBarContentLayout.setContentsMargins(10, 0, 4, 0)
        self.statusFilesLabel = QLabel(self.statusBarContentWidget)
        self.statusFilesLabel.setObjectName(u"statusFilesLabel")

        self.statusBarContentLayout.addWidget(self.statusFilesLabel)

        self.statusRunProgressBar = QProgressBar(self.statusBarContentWidget)
        self.statusRunProgressBar.setObjectName(u"statusRunProgressBar")
        self.statusRunProgressBar.setMinimumSize(QSize(200, 14))
        self.statusRunProgressBar.setMaximumSize(QSize(400, 14))
        self.statusRunProgressBar.setValue(0)

        self.statusBarContentLayout.addWidget(self.statusRunProgressBar)

        self.statusEbuProgressBar = QProgressBar(self.statusBarContentWidget)
        self.statusEbuProgressBar.setObjectName(u"statusEbuProgressBar")
        self.statusEbuProgressBar.setMinimumSize(QSize(200, 14))
        self.statusEbuProgressBar.setMaximumSize(QSize(320, 14))
        self.statusEbuProgressBar.setValue(0)
        self.statusEbuProgressBar.setTextVisible(True)

        self.statusBarContentLayout.addWidget(self.statusEbuProgressBar)

        self.statusBarSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.statusBarContentLayout.addItem(self.statusBarSpacer)

        self.runCommandButton = QPushButton(self.statusBarContentWidget)
        self.runCommandButton.setObjectName(u"runCommandButton")
        self.runCommandButton.setAutoDefault(False)
        self.runCommandButton.setMaximumWidth(100)

        self.statusBarContentLayout.addWidget(self.runCommandButton)

        MainWindow.setStatusBar(self.statusbar)
        self.statusbar.addWidget(self.statusBarContentWidget, 1)

        self.retranslateUi(MainWindow)

        self.builderTabWidget.setCurrentIndex(0)
        self.runCommandButton.setDefault(True)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"FFBuilder", None))
        self.hardwareStatusLabel.setText(QCoreApplication.translate("MainWindow", u"Detecting hardware...", None))
        self.settingsButton.setText(QCoreApplication.translate("MainWindow", u"Settings", None))
        self.browseFilesButton.setText(QCoreApplication.translate("MainWindow", u"Open", None))
        self.clearFilesButton.setText("")
        self.filesListWidget.setAccessibleIdentifier("")
        self.metadataGroupBox.setTitle(QCoreApplication.translate("MainWindow", u"File metadata", None))
        ___qtreewidgetitem = self.metadataTreeWidget.headerItem()
        ___qtreewidgetitem.setText(1, QCoreApplication.translate("MainWindow", u"Value", None));
        ___qtreewidgetitem.setText(0, QCoreApplication.translate("MainWindow", u"Field", None));
        self.filesStatusLabel.setText(QCoreApplication.translate("MainWindow", u"No files loaded", None))
        self.newTemplateButton.setText(QCoreApplication.translate("MainWindow", u"New template", None))
        self.templateDetailsGroupBox.setTitle(QCoreApplication.translate("MainWindow", u"Description", None))
        self.templateDescriptionLabel.setText(QCoreApplication.translate("MainWindow", u"Select a template.", None))
        self.outputGroupBox.setTitle(QCoreApplication.translate("MainWindow", u"Output", None))
        self.outputFileLabel.setText(QCoreApplication.translate("MainWindow", u"Output file", None))
        self.browseOutputButton.setText("")
        self.formatLabel.setText(QCoreApplication.translate("MainWindow", u"Format", None))
        self.formatDescriptionLabel.setText(QCoreApplication.translate("MainWindow", u"[Format description]", None))
        self.builderTabWidget.setTabText(self.builderTabWidget.indexOf(self.templatesTab), QCoreApplication.translate("MainWindow", u"Templates", None))
        self.queueStatusLabel.setText(QCoreApplication.translate("MainWindow", u"0 items in queue", None))
        self.queueClearButton.setText("")
        ___qtreewidgetitem1 = self.queueTreeWidget.headerItem()
        ___qtreewidgetitem1.setText(3, QCoreApplication.translate("MainWindow", u"Progress", None));
        ___qtreewidgetitem1.setText(2, QCoreApplication.translate("MainWindow", u"Status", None));
        ___qtreewidgetitem1.setText(1, QCoreApplication.translate("MainWindow", u"Output", None));
        ___qtreewidgetitem1.setText(0, QCoreApplication.translate("MainWindow", u"File", None));
        self.queueStartButton.setText(QCoreApplication.translate("MainWindow", u"Start", None))
        self.queueStopButton.setText(QCoreApplication.translate("MainWindow", u"Stop", None))
        self.builderTabWidget.setTabText(self.builderTabWidget.indexOf(self.queueTab), QCoreApplication.translate("MainWindow", u"Queue", None))
        self.previewTitleLabel.setText(QCoreApplication.translate("MainWindow", u"Command preview (editable)", None))
        self.commandPreviewTextEdit.setPlainText(QCoreApplication.translate("MainWindow", u"ffmpeg -i input.mp4 -c:v libx264 -preset fast -crf 28 output.mp4", None))
        self.copyCommandButton.setText(QCoreApplication.translate("MainWindow", u"Copy", None))
        self.clearCommandButton.setText(QCoreApplication.translate("MainWindow", u"Clear", None))
#if QT_CONFIG(tooltip)
        self.visualEditorButton.setToolTip(QCoreApplication.translate("MainWindow", u"You can configure FFmpeg parameters visually and generate a command.", None))
#endif // QT_CONFIG(tooltip)
        self.visualEditorButton.setText(QCoreApplication.translate("MainWindow", u"Visual editor...", None))
        self.statusFilesLabel.setText(QCoreApplication.translate("MainWindow", u"No files loaded", None))
        self.statusEbuProgressBar.setFormat(QCoreApplication.translate("MainWindow", u"EBU: %p%", None))
        self.runCommandButton.setText(QCoreApplication.translate("MainWindow", u"Run", None))
    # retranslateUi

