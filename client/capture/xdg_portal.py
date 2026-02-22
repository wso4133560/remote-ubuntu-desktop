"""XDG Desktop Portal 屏幕捕获实现 (GNOME)"""
import asyncio
from typing import Optional
from gi.repository import GLib, Gio
import dbus
from dbus.mainloop.glib import DBusGMainLoop


class XDGPortalCapture:
    """XDG Desktop Portal 屏幕捕获"""

    def __init__(self):
        DBusGMainLoop(set_as_default=True)
        self.session_bus = dbus.SessionBus()
        self.portal = None
        self.session_handle = None
        self.pipewire_node_id = None

    async def initialize(self) -> bool:
        """初始化 Portal 捕获"""
        try:
            self.portal = self.session_bus.get_object(
                'org.freedesktop.portal.Desktop',
                '/org/freedesktop/portal/desktop'
            )

            screencast = dbus.Interface(
                self.portal,
                'org.freedesktop.portal.ScreenCast'
            )

            session_path = screencast.CreateSession({
                'session_handle_token': 'remote_control_session'
            })

            self.session_handle = session_path
            print(f"XDG Portal session created: {session_path}")
            return True

        except Exception as e:
            print(f"Failed to initialize XDG Portal: {e}")
            return False

    async def select_sources(self) -> bool:
        """选择捕获源"""
        try:
            screencast = dbus.Interface(
                self.portal,
                'org.freedesktop.portal.ScreenCast'
            )

            screencast.SelectSources(
                self.session_handle,
                {
                    'types': dbus.UInt32(1),  # 1 = Monitor
                    'multiple': dbus.Boolean(False),
                    'cursor_mode': dbus.UInt32(2)  # 2 = Embedded
                }
            )

            print("Source selection requested")
            return True

        except Exception as e:
            print(f"Failed to select sources: {e}")
            return False

    async def start_capture(self) -> Optional[int]:
        """开始捕获"""
        try:
            screencast = dbus.Interface(
                self.portal,
                'org.freedesktop.portal.ScreenCast'
            )

            result = screencast.Start(
                self.session_handle,
                '',
                {}
            )

            if result:
                streams = result.get('streams', [])
                if streams:
                    self.pipewire_node_id = streams[0][0]
                    print(f"Capture started, PipeWire node: {self.pipewire_node_id}")
                    return self.pipewire_node_id

        except Exception as e:
            print(f"Failed to start capture: {e}")

        return None

    async def stop_capture(self):
        """停止捕获"""
        if self.session_handle:
            try:
                screencast = dbus.Interface(
                    self.portal,
                    'org.freedesktop.portal.ScreenCast'
                )
                screencast.Stop(self.session_handle)
                print("Capture stopped")
            except Exception as e:
                print(f"Failed to stop capture: {e}")

    def get_pipewire_node_id(self) -> Optional[int]:
        """获取 PipeWire 节点 ID"""
        return self.pipewire_node_id
