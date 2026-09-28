import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    visible: true
    width: 1120
    height: 760
    minimumWidth: 860
    minimumHeight: 620
    title: "Iris"
    color: "#07080C"

    property color textMain: "#F6F7FA"
    property color textMuted: "#969CA8"
    property color panel: "#11141A"
    property color panel2: "#161A21"
    property color border: "#292E37"

    onClosing: iris.stop()

    Rectangle {
        anchors.fill: parent
        color: root.color

        // Ambient lights
        Rectangle {
            width: 460; height: 460; radius: 230
            x: -160; y: -190; opacity: 0.09
            gradient: Gradient {
                GradientStop { position: 0; color: "#FF2D55" }
                GradientStop { position: 0.45; color: "#7A5CFF" }
                GradientStop { position: 1; color: "#00C8FF" }
            }
        }
        Rectangle {
            width: 430; height: 430; radius: 215
            x: root.width - 220; y: root.height - 220; opacity: 0.075
            gradient: Gradient {
                GradientStop { position: 0; color: "#00E58B" }
                GradientStop { position: 0.5; color: "#00B6FF" }
                GradientStop { position: 1; color: "#9E5CFF" }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 18

            // Header
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 52

                ColumnLayout {
                    spacing: 2
                    Text {
                        text: "IRIS"
                        color: textMain
                        font.pixelSize: 21
                        font.bold: true
                        font.letterSpacing: 3
                    }
                    Text {
                        text: iris.status
                        color: textMuted
                        font.pixelSize: 12
                    }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    Layout.preferredWidth: 108
                    Layout.preferredHeight: 36
                    radius: 18
                    color: "#12161D"
                    border.width: 1
                    border.color: border
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8
                        Rectangle {
                            Layout.preferredWidth: 8
                            Layout.preferredHeight: 8
                            radius: 4
                            color: iris.listening ? "#42F58A" : (iris.modelReady ? "#65D6FF" : "#FFB84A")
                        }
                        Text {
                            text: iris.listening ? "LISTENING" : (iris.modelReady ? "READY" : "STARTING")
                            color: textMain
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 18

                // Main visual panel
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 30
                    color: Qt.rgba(0.07, 0.08, 0.11, 0.82)
                    border.width: 1
                    border.color: border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 22
                        spacing: 8

                        Text {
                            Layout.fillWidth: true
                            text: iris.busy ? "Thinking..." : (iris.listening ? "I'm listening" : "What can I help you with?")
                            color: textMain
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: 28
                            font.bold: true
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Ask naturally. Iris keeps the conversation in context."
                            color: textMuted
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: 14
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            Rectangle {
                                id: ring
                                anchors.centerIn: parent
                                width: 260; height: 260; radius: 130
                                color: "transparent"
                                border.width: 3
                                opacity: 0.35
                                gradient: Gradient {
                                    GradientStop { position: 0.00; color: "#FF2D55" }
                                    GradientStop { position: 0.16; color: "#FF9500" }
                                    GradientStop { position: 0.33; color: "#FFD60A" }
                                    GradientStop { position: 0.50; color: "#30D158" }
                                    GradientStop { position: 0.67; color: "#32ADE6" }
                                    GradientStop { position: 0.84; color: "#5856D6" }
                                    GradientStop { position: 1.00; color: "#FF2D55" }
                                }
                                RotationAnimation on rotation {
                                    running: true
                                    from: 0; to: 360
                                    duration: iris.listening ? 2600 : (iris.busy ? 4200 : 8000)
                                    loops: Animation.Infinite
                                }
                            }

                            Rectangle {
                                id: orb
                                anchors.centerIn: parent
                                width: 205; height: 205; radius: 102.5
                                scale: iris.listening ? 1.09 : (iris.busy ? 1.05 : 1.0)
                                gradient: Gradient {
                                    GradientStop { position: 0.00; color: "#FF375F" }
                                    GradientStop { position: 0.18; color: "#FF9F0A" }
                                    GradientStop { position: 0.36; color: "#FFD60A" }
                                    GradientStop { position: 0.53; color: "#34C759" }
                                    GradientStop { position: 0.70; color: "#0A84FF" }
                                    GradientStop { position: 0.86; color: "#5E5CE6" }
                                    GradientStop { position: 1.00; color: "#FF2D55" }
                                }
                                Behavior on scale {
                                    NumberAnimation { duration: 280; easing.type: Easing.OutCubic }
                                }
                                SequentialAnimation on opacity {
                                    running: true
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 0.87; duration: 700 }
                                    NumberAnimation { to: 1.00; duration: 900 }
                                }
                                RotationAnimation on rotation {
                                    running: true
                                    from: 360; to: 0
                                    duration: iris.listening ? 3000 : 11000
                                    loops: Animation.Infinite
                                }
                            }

                            Rectangle {
                                anchors.centerIn: orb
                                width: 148; height: 148; radius: 74
                                color: "#FFFFFF"
                                opacity: 0.09
                                border.width: 1
                                border.color: "#FFFFFF"
                            }

                            Text {
                                anchors.centerIn: orb
                                text: iris.listening ? "LISTENING" : (iris.busy ? "THINKING" : "IRIS")
                                color: "white"
                                font.pixelSize: iris.listening || iris.busy ? 13 : 22
                                font.bold: true
                                font.letterSpacing: iris.listening || iris.busy ? 1.3 : 3
                            }

                            // Orbiting lights
                            Repeater {
                                model: 10
                                Rectangle {
                                    width: 7; height: 7; radius: 3.5
                                    color: ["#FF375F", "#FF9F0A", "#FFD60A", "#34C759", "#32ADE6", "#0A84FF", "#5E5CE6", "#AF52DE", "#FF2D55", "#FFFFFF"][index]
                                    x: parent.width/2 + Math.cos((index * 36) * Math.PI/180) * 158 - width/2
                                    y: parent.height/2 + Math.sin((index * 36) * Math.PI/180) * 158 - height/2
                                    opacity: 0.65
                                    SequentialAnimation on opacity {
                                        running: true
                                        loops: Animation.Infinite
                                        PauseAnimation { duration: index * 55 }
                                        NumberAnimation { to: 0.18; duration: 450 }
                                        NumberAnimation { to: 0.75; duration: 650 }
                                    }
                                }
                            }
                        }

                        // Latest answer preview
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 96
                            radius: 24
                            color: panel
                            border.width: 1
                            border.color: border
                            clip: true

                            Text {
                                id: liveText
                                anchors.fill: parent
                                anchors.margins: 18
                                text: ""
                                color: textMain
                                font.pixelSize: 14
                                wrapMode: Text.Wrap
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                // Conversation panel
                Rectangle {
                    Layout.preferredWidth: 410
                    Layout.fillHeight: true
                    radius: 30
                    color: panel
                    border.width: 1
                    border.color: border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10

                        Text {
                            text: "Conversation"
                            color: textMain
                            font.pixelSize: 15
                            font.bold: true
                        }

                        ListModel { id: chatModel }

                        ListView {
                            id: chatView
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            model: chatModel
                            spacing: 10
                            clip: true
                            delegate: Rectangle {
                                width: chatView.width
                                radius: 18
                                color: model.role === "user" ? "#1A1F28" : "#151920"
                                border.width: 1
                                border.color: "#252A33"
                                implicitHeight: messageText.implicitHeight + 26

                                Text {
                                    id: messageText
                                    anchors.fill: parent
                                    anchors.margins: 13
                                    text: model.text
                                    color: textMain
                                    font.pixelSize: 13
                                    wrapMode: Text.Wrap
                                }
                            }
                            onCountChanged: {
                                Qt.callLater(function() { chatView.positionViewAtEnd() })
                            }
                        }
                    }
                }
            }

            // Composer
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 76
                radius: 30
                color: panel
                border.width: 1
                border.color: border

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 9

                    TextField {
                        id: input
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        placeholderText: "Ask Iris anything..."
                        placeholderTextColor: "#707783"
                        color: textMain
                        font.pixelSize: 16
                        leftPadding: 16
                        rightPadding: 16
                        background: Rectangle { color: "transparent" }

                        Keys.onReturnPressed: {
                            iris.sendMessage(text)
                            text = ""
                        }
                    }

                    Button {
                        Layout.preferredWidth: 50
                        Layout.preferredHeight: 50
                        text: "🎙"
                        font.pixelSize: 18
                        background: Rectangle {
                            radius: 25
                            color: iris.listening ? "#23402F" : "#1A1F28"
                            border.width: 1
                            border.color: iris.listening ? "#3F8B5D" : "#303641"
                        }
                        onClicked: iris.toggleVoice()
                    }

                    Button {
                        Layout.preferredWidth: 86
                        Layout.preferredHeight: 50
                        text: "SEND"
                        font.bold: true
                        background: Rectangle {
                            radius: 25
                            color: "#F2F3F5"
                        }
                        contentItem: Text {
                            text: "SEND"
                            color: "#090B0F"
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: {
                            iris.sendMessage(input.text)
                            input.text = ""
                        }
                    }
                }
            }
        }

        Connections {
            target: iris
            function onMessageAdded(role, text) {
                chatModel.append({"role": role, "text": text})
            }
            function onStreamText(text) {
                liveText.text = text
            }
            function onAnswerFinished(text) {
                liveText.text = text
            }
        }
    }
}
