"""GNOME RemoteDesktop 输入注入实现"""
import asyncio
from typing import Optional
from gi.repository import GLib, Gio
import dbus
from dbus.mainloop.glib import DBusGMainLoop


class GNOMERemoteDesktopInjector:
    """GNOME RemoteDesktop 输入注入器"""

    def __init__(self):
        DBusGMainLoop(set_as_default=True)
        self.session_bus = dbus.SessionBus()
        self.remote_desktop = None
        self.session_path = None

    async def initialize(self) -> bool:
        """初始化 RemoteDesktop"""
        try:
            self.remote_desktop = self.session_bus.get_object(
                'org.gnome.Mutter.RemoteDesktop',
                '/org/gnome/Mutter/RemoteDesktop'
            )

            interface = dbus.Interface(
                self.remote_desktop,
                'org.gnome.Mutter.RemoteDesktop'
            )

            self.session_path = interface.CreateSession()
            print(f"GNOME RemoteDesktop session created: {self.session_path}")

            session = self.session_bus.get_object(
                'org.gnome.Mutter.RemoteDesktop',
                self.session_path
            )

            session_interface = dbus.Interface(
                session,
                'org.gnome.Mutter.RemoteDesktop.Session'
            )

            session_interface.Start()
            print("RemoteDesktop session started")
            return True

        except Exception as e:
            print(f"Failed to initialize GNOME RemoteDesktop: {e}")
            return False

    async def inject_mouse_move(self, x: float, y: float):
        """注入鼠标移动"""
        try:
            session = self.session_bus.get_object(
                'org.gnome.Mutter.RemoteDesktop',
                self.session_path
            )

            session_interface = dbus.Interface(
                session,
                'org.gnome.Mutter.RemoteDesktop.Session'
            )

            session_interface.NotifyPointerMotionAbsolute(
                '',
                dbus.Double(x),
                dbus.Double(y)
            )

        except Exception as e:
            print(f"Failed to inject mouse move: {e}")

    async def inject_mouse_button(self, button: int, pressed: bool):
        """注入鼠标按键"""
        try:
            session = self.session_bus.get_object(
                'org.gnome.Mutter.RemoteDesktop',
                self.session_path
            )

            session_interface = dbus.Interface(
                session,
                'org.gnome.Mutter.RemoteDesktop.Session'
            )

            button_map = {0: 0x110, 1: 0x111, 2: 0x112}
            evdev_button = button_map.get(button, 0x110)

            if pressed:
                session_interface.NotifyPointerButton(
                    '',
                    dbus.Int32(evdev_button),
                    dbus.UInt32(1)
                )
            else:
                session_interface.NotifyPointerButton(
                    '',
                    dbus.Int32(evdev_button),
                    dbus.UInt32(0)
                )

        except Exception as e:
            print(f"Failed to inject mouse button: {e}")

    async def inject_key(self, keycode: int, pressed: bool):
        """注入键盘按键"""
        try:
            session = self.session_bus.get_object(
                'org.gnome.Mutter.RemoteDesktop',
                self.session_path
            )

            session_interface = dbus.Interface(
                session,
                'org.gnome.Mutter.RemoteDesktop.Session'
            )

            if pressed:
                session_interface.NotifyKeyboardKeycode(
                    '',
                    dbus.Int32(keycode),
                    dbus.UInt32(1)
                )
            else:
                session_interface.NotifyKeyboardKeycode(
                    '',
                    dbus.Int32(keycode),
                    dbus.UInt32(0)
                )

        except Exception as e:
            print(f"Failed to inject key: {e}")

    async def cleanup(self):
        """清理资源"""
        if self.session_path:
            try:
                session = self.session_bus.get_object(
                    'org.gnome.Mutter.RemoteDesktop',
                    self.session_path
                )

                session_interface = dbus.Interface(
                    session,
                    'org.gnome.Mutter.RemoteDesktop.Session'
                )

                session_interface.Stop()
                print("RemoteDesktop session stopped")
            except Exception as e:
                print(f"Failed to cleanup: {e}")
